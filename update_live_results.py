#!/usr/bin/env python3
"""Fetch only market values attached to exact DPBOSS market headings."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "results.json"
LIVE_URL = "https://dpbossss.com/"
MARKETS = {
    "time-bazar": ("Time Bazar", ("TIME BAZAR",)),
    "milan-day": ("Milan Day", ("MILAN DAY",)),
    "rajdhani-day": ("Rajdhani Day", ("RAJDHANI DAY",)),
    "kalyan": ("Kalyan", ("KALYAN",)),
    "milan-night": ("Milan Night", ("MILAN NIGHT",)),
    "kalyan-night": ("Kalyan Night", ("KALYAN NIGHT",)),
    "rajdhani-night": ("Rajdhani Night", ("RAJDHANI NIGHT",)),
    "main-bazar": ("Main Bazar", ("MAIN BAZAR",)),
    "sridevi": ("Sridevi", ("SRIDEVI",)),
    "sridevi-night": ("Sridevi Night", ("SRIDEVI NIGHT",)),
}
RESULT_RE = re.compile(r"(?<!\d)(\d{3}\s*[-–]\s*\d{1,2}(?:\s*[-–]\s*\d{3})?)(?!\d)")
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

def fetch_html():
    request = Request(LIVE_URL, headers={
        "User-Agent": "Mozilla/5.0 (compatible; DP777PublicResults/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urlopen(request, timeout=25) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read().decode("utf-8", errors="replace")

def norm(value):
    return re.sub(r"\s+", " ", value or "").strip().upper()

def extract_results(html):
    soup = BeautifulSoup(html, "html.parser")
    results = {}
    headings = [tag for tag in soup.find_all(HEADING_TAGS)]

    for market_id, (name, aliases) in MARKETS.items():
        for heading in headings:
            label = norm(heading.get_text(" ", strip=True))
            if label not in aliases:
                continue

            # Read the complete result card text, not individual text nodes.
            # The old parser could stop at a fragment such as "366-5" when
            # the remaining digits were rendered in adjacent spans.
            value = None
            for container in heading.parents:
                if getattr(container, "name", None) in {"body", "html", "[document]"}:
                    break
                nested_headings = [
                    h for h in container.find_all(HEADING_TAGS)
                    if norm(h.get_text(" ", strip=True)) in {
                        alias for _, market_aliases in MARKETS.values()
                        for alias in market_aliases
                    }
                ]
                # A card should contain this market heading only; do not read
                # a grid/container containing several markets.
                if len(nested_headings) > 1:
                    break
                combined = norm(container.get_text(" ", strip=True))
                label_pos = combined.find(label)
                if label_pos < 0:
                    continue
                tail = combined[label_pos + len(label):]
                match = RESULT_RE.search(tail)
                if match:
                    candidate = re.sub(r"\\s*[-–]\\s*", "-", match.group(1))
                    # Prefer a full panel result (xxx-xx-xxx) over a partial
                    # OPEN result (xxx-x); keep searching upward only while
                    # the container remains a single-card container.
                    value = candidate
                    if candidate.count("-") == 2:
                        break

            if value:
                results[market_id] = {
                    "name": name, "result": value, "source": LIVE_URL,
                    "source_label": label,
                }
                break

    values = [item["result"] for item in results.values()]
    if len(values) >= 4 and len(set(values)) == 1:
        raise RuntimeError("Repeated-value extraction rejected; previous feed preserved")
    return results

def main():
    try:
        current = extract_results(fetch_html())
    except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as error:
        print(f"Live source fetch failed: {error}")
        raise SystemExit(1)

    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old = {}
    old.setdefault("site", "DP 777")
    old.setdefault("charts", {})
    old.setdefault("updated_at", None)
    old.setdefault("updated_charts", 0)
    old["live_source"] = LIVE_URL
    old["latest_results"] = current
    old["live_fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    old["live_status"] = "ok" if len(current) == len(MARKETS) else "partial" if current else "no-labelled-results"
    print(f"Found {len(current)}/{len(MARKETS)} exact-heading markets; absent markets will display as not published.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    live_feed = {
        "latest_results": current,
        "live_fetched_at": old["live_fetched_at"],
        "live_source": LIVE_URL,
        "live_status": old["live_status"],
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (ROOT / "data" / "latest_results.json").write_text(
        json.dumps(live_feed, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print("Wrote compact live feed with", len(current), "market entries.")

if __name__ == "__main__":
    main()

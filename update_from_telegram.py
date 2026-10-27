#!/usr/bin/env python3
"""Supplement DP 777 live results from the public Telegram channel preview.

Only public posts are read. A result is accepted only when a market name and a
valid result pattern occur in the same Telegram message. If Telegram is
unavailable or its markup changes, the existing result feed is left untouched.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "data" / "latest_results.json"
ARCHIVE = ROOT / "data" / "results.json"
CHANNEL = "KMFAMILYRESULTS"
CHANNEL_URL = f"https://t.me/s/{CHANNEL}"
MARKETS = {
    "time-bazar": ("Time Bazar", (r"TIME\s*BAZAR",)),
    "milan-day": ("Milan Day", (r"MILAN\s*DAY",)),
    "rajdhani-day": ("Rajdhani Day", (r"RAJDHANI\s*DAY",)),
    "kalyan": ("Kalyan", (r"\bKALYAN\b(?!\s*NIGHT)",)),
    "sridevi": ("Sridevi", (r"\bSRIDEVI\s*DAY\b", r"\bSRIDEVI\b(?!\s*NIGHT)")),
    "sridevi-night": ("Sridevi Night", (r"\bSRIDEVI\s*NIGHT\b",)),
    "milan-night": ("Milan Night", (r"MILAN\s*NIGHT",)),
    "kalyan-night": ("Kalyan Night", (r"KALYAN\s*NIGHT",)),
    "rajdhani-night": ("Rajdhani Night", (r"RAJDHANI\s*NIGHT",)),
    "main-bazar": ("Main Bazar", (r"MAIN\s*BAZAR",)),
}
RESULT_RE = re.compile(r"(?<!\d)(\d{3})\s*[-–]\s*(\d{1,2})(?:\s*[-–]\s*(\d{3}))?(?!\d)")
STANDALONE_THREE_RE = re.compile(r"(?<!\d)(\d{3})(?!\d)")
STAGE_RE = re.compile(r"\b(OPEN|CLOSE)\b\s*[:=-]?\s*(\d{3})\b", re.I)
MARKET_PATTERNS = {key: [re.compile(p, re.I) for p in aliases] for key, (_n, aliases) in MARKETS.items()}

def fetch_page():
    request = Request(CHANNEL_URL, headers={
        "User-Agent": "Mozilla/5.0 (compatible; DP777PublicResults/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Telegram returned HTTP {response.status}")
        return response.read().decode("utf-8", errors="replace")

def parse_posts(html):
    soup = BeautifulSoup(html, "html.parser")
    posts = soup.select(".tgme_widget_message_wrap")
    if not posts:
        posts = soup.select("[data-post]")
    found = {}
    # Process posts in the preview's rendered order; newest posts appear last.
    # The newest result overwrites older results for the same market, and this
    # allows later CLOSE posts to combine with earlier OPEN posts.
    for wrap in posts:
        post_node = wrap if wrap.has_attr("data-post") else wrap.select_one("[data-post]")
        if post_node is None:
            continue
        post_id = post_node.get("data-post", "")
        msg = wrap.select_one(".tgme_widget_message_text")
        if msg is None:
            continue
        # Preserve line boundaries: never assign a result from a different
        # market line just because it is close in the full message text.
        lines = [re.sub(r"\s+", " ", line).strip() for line in msg.get_text("\n", strip=True).splitlines()]
        lines = [line for line in lines if line]
        link = f"https://t.me/{post_id}" if "/" in post_id else CHANNEL_URL
        time_node = wrap.select_one("time[datetime]")
        posted_at = time_node.get("datetime") if time_node else None
        # Only use results posted on the current India calendar day.
        # Older Telegram posts must never be shown as today's live results.
        india_today = datetime.now(timezone.utc).astimezone(
            __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
        ).date()
        try:
            post_date = datetime.fromisoformat(posted_at.replace("Z", "+00:00")).astimezone(
                __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
            ).date() if posted_at else None
        except (ValueError, TypeError):
            post_date = None
        if post_date != india_today:
            continue

        candidates = []
        for line in lines:
            line_markets = [
                market_id for market_id, patterns in MARKET_PATTERNS.items()
                if any(pattern.search(line) for pattern in patterns)
            ]
            line_results = list(RESULT_RE.finditer(line))
            # Open usually arrives as 459-8; Close may arrive later as a
            # standalone three-digit number beside the same market label.
            if len(line_markets) != 1:
                continue
            if len(line_results) == 1:
                match = line_results[0]
                value = f"{match.group(1)}-{match.group(2)}"
                if match.group(3):
                    value += f"-{match.group(3)}"
                candidates.append((line_markets[0], value))
            elif not line_results:
                bare = STANDALONE_THREE_RE.findall(line)
                if len(bare) == 1:
                    candidates.append((line_markets[0], "CLOSE:" + bare[0]))

        # Some posts use one compact sentence rather than separate lines.
        # Accept that only when the entire message contains exactly one market
        # and one result; skip ambiguous multi-market/result posts.
        if not candidates:
            body = " ".join(lines)
            body_markets = [
                market_id for market_id, patterns in MARKET_PATTERNS.items()
                if any(pattern.search(body) for pattern in patterns)
            ]
            body_results = list(RESULT_RE.finditer(body))
            if len(body_markets) == 1 and len(body_results) == 1:
                match = body_results[0]
                value = f"{match.group(1)}-{match.group(2)}"
                if match.group(3):
                    value += f"-{match.group(3)}"
                candidates.append((body_markets[0], value))
            elif len(body_markets) == 1 and not body_results:
                stage_match = STAGE_RE.search(body)
                if stage_match:
                    stage, pana = stage_match.groups()
                    candidates.append((body_markets[0], stage.upper() + ":" + pana))
                else:
                    bare = STANDALONE_THREE_RE.findall(body)
                    if len(bare) == 1:
                        candidates.append((body_markets[0], "CLOSE:" + bare[0]))

        for market_id, value in candidates:
            name = MARKETS[market_id][0]
            prior = found.get(market_id, {})
            # Newest-first scan may see CLOSE before the earlier OPEN post.
            if value.startswith("CLOSE:"):
                close_panna = value.split(":", 1)[1]
                prior_value = str(prior.get("result", ""))
                open_match = re.fullmatch(r"(\d{3})-(\d)", prior_value)
                if open_match:
                    open_panna, open_ank = open_match.groups()
                    close_ank = str(sum(int(d) for d in close_panna) % 10)
                    value = f"{open_panna}-{open_ank}{close_ank}-{close_panna}"
            else:
                prior_value = str(prior.get("result", ""))
                open_match = re.fullmatch(r"(\d{3})-(\d)", value)
                if open_match and prior_value.startswith("CLOSE:"):
                    close_panna = prior_value.split(":", 1)[1]
                    open_panna, open_ank = open_match.groups()
                    close_ank = str(sum(int(d) for d in close_panna) % 10)
                    value = f"{open_panna}-{open_ank}{close_ank}-{close_panna}"
            # Posts are processed oldest-to-newest. A newer OPEN-only post
            # must replace an older complete result; otherwise the UI keeps
            # showing yesterday's close. Only preserve a complete value when
            # the incoming value is not newer (already guaranteed by order).
            found[market_id] = {
                "name": name, "result": value, "source": CHANNEL_URL,
                "source_label": f"Telegram @{CHANNEL}",
                "telegram_message_url": link, "telegram_posted_at": posted_at,
            }
    return found

def update_milan_day_archive(archive, item, today):
    """Insert today's complete Milan Day result into the weekly archive and its small chart feed."""
    match = re.fullmatch(r"(\d{3})-(\d{2})-(\d{3})", str(item.get("result", "")))
    if not match:
        return False
    open_panna, jodi, close_panna = match.groups()
    chart = archive.setdefault("charts", {}).get("milan-day")
    if not isinstance(chart, dict):
        print("Milan Day historical archive not present; latest result saved only.")
        return False
    rows = chart.setdefault("rows", [])
    day = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][today.weekday()]
    date_re = re.compile(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})")
    target_row = None
    for row in rows:
        dates = []
        for m in date_re.finditer(str(row.get("date", ""))):
            d, mo, y = map(int, m.groups())
            if y < 100:
                y += 2000
            try:
                dates.append(datetime(y, mo, d).date())
            except ValueError:
                pass
        if dates and min(dates) <= today <= max(dates):
            target_row = row
            break
    if target_row is None:
        target_row = {"date": today.strftime("%d/%m/%Y")}
        for weekday in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            target_row[f"{weekday} Open"] = ""
            target_row[f"{weekday} Jodi"] = ""
            target_row[f"{weekday} Close"] = ""
        rows.append(target_row)
    values = {f"{day} Open": open_panna, f"{day} Jodi": jodi, f"{day} Close": close_panna}
    changed = any(str(target_row.get(k, "")) != v for k, v in values.items())
    target_row.update(values)
    chart["record_count"] = len(rows)
    chart["columns"] = list(rows[0].keys()) if rows else []
    chart["status"] = "ok"
    return changed

def main():
    print("Telegram source disabled: DP 777 live market results are sourced from DPBOSS homepage only.")
    return

    try:
        updates = parse_posts(fetch_page())
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
        print(f"Telegram preview unavailable; keeping existing results: {exc}")
        updates = {}

    # Sridevi morning is always sourced from the dedicated DPBOSS homepage card.
    # Never let Telegram overwrite it with a different Sridevi-labelled result.
    # Sridevi Night remains independent and is sourced from Telegram except Sundays.
    india_now = datetime.now(timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    updates.pop("sridevi", None)
    if india_now.weekday() == 6:
        updates.pop("sridevi-night", None)

    try:
        feed = json.loads(FEED.read_text(encoding="utf-8"))
        archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read existing data; keeping it unchanged: {exc}")
        return

    # The main-site scraper can reintroduce an incomplete Milan Night value
    # before this supplement runs. Remove it on every refresh unless complete.
    invalid_removed = False
    for data in (feed, archive):
        latest = data.setdefault("latest_results", {})
        old_item = latest.get("milan-night", {})
        old_value = str(old_item.get("result", ""))
        # A two-part value such as 459-8 is a valid OPEN result when it came
        # from Telegram. Only clear malformed values; preserve Telegram OPEN
        # until the CLOSE result arrives.
        if old_value and not re.fullmatch(r"\d{3}-\d{1,2}(?:-\d{3})?", old_value):
            latest.pop("milan-night", None)
            invalid_removed = True
        elif old_value and not old_item.get("source", "").startswith("https://t.me/") and not re.fullmatch(r"\d{3}-\d{1,2}-\d{3}", old_value):
            latest.pop("milan-night", None)
            invalid_removed = True

    feed_latest = feed.setdefault("latest_results", {})
    archive_latest = archive.setdefault("latest_results", {})
    changed = []
    for market_id, item in updates.items():
        old = feed_latest.get(market_id, {})
        value = item["result"]
        if value.startswith("CLOSE:"):
            close_panna = value.split(":", 1)[1]
            open_value = str(old.get("result", ""))
            open_match = re.fullmatch(r"(\d{3})-(\d)", open_value)
            if open_match:
                open_panna, open_ank = open_match.groups()
            else:
                open_only = re.fullmatch(r"OPEN:(\d{3})", open_value)
                if not open_only:
                    # Keep close number unpublished until its matching Open is known.
                    continue
                open_panna = open_only.group(1)
                open_ank = str(sum(int(d) for d in open_panna) % 10)
            close_ank = str(sum(int(d) for d in close_panna) % 10)
            value = f"{open_panna}-{open_ank}{close_ank}-{close_panna}"
            item["result"] = value
        if old.get("result") != value or old.get("source") != item["source"]:
            changed.append(f"{item['name']}={value}")
        feed_latest[market_id] = item
        archive_latest[market_id] = item

    # Append a complete result from today's Telegram post to the Milan Day archive.
    milan_item = feed_latest.get("milan-day", {})
    india_today = datetime.now(timezone.utc).astimezone(
        __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
    ).date()
    archive_chart_changed = False
    posted_at = milan_item.get("telegram_posted_at")
    if milan_item.get("source", "").startswith("https://t.me/") and posted_at and re.fullmatch(
        r"\d{3}-\d{2}-\d{3}", str(milan_item.get("result", ""))
    ):
        try:
            posted_day = datetime.fromisoformat(posted_at.replace("Z", "+00:00")).astimezone(
                __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
            ).date()
        except ValueError:
            posted_day = None
        if posted_day == india_today:
            archive_chart_changed = update_milan_day_archive(archive, milan_item, india_today)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    feed["telegram_fetched_at"] = now
    feed["live_source"] = CHANNEL_URL
    feed["live_status"] = "telegram-updated" if changed else ("partial" if invalid_removed else feed.get("live_status", "ok"))
    archive["telegram_fetched_at"] = now
    archive["live_source"] = CHANNEL_URL
    if changed or invalid_removed:
        feed["updated_at"] = now
    FEED.write_text(json.dumps(feed, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    ARCHIVE.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if archive_chart_changed:
        chart_dir = ARCHIVE.parent / "charts"
        chart_dir.mkdir(parents=True, exist_ok=True)
        chart = archive.get("charts", {}).get("milan-day")
        if chart:
            (chart_dir / "milan-day.json").write_text(
                json.dumps({"updated_at": now, "charts": {"milan-day": chart}}, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
        print("Milan Day archive row updated for " + india_today.strftime("%d/%m/%Y"))
    if changed:
        print("Telegram result values updated: " + ", ".join(changed))
    elif invalid_removed:
        print("Removed incomplete Milan Night value; no complete new result found.")
    else:
        print("Telegram checked; no new unambiguous results found.")

if __name__ == "__main__":
    main()

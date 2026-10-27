#!/usr/bin/env python3
"""Append today's published results into each market's dated weekly chart row."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FEED = DATA / "latest_results.json"
CHARTS = DATA / "charts"
TZ = ZoneInfo("Asia/Kolkata")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MARKET_TO_CHART = {
    "sridevi": "sridevi-day",
    "sridevi-night": "sridevi",
    "time-bazar": "time-bazar",
    "milan-day": "milan-day",
    "rajdhani-day": "rajdhani-day",
    "kalyan": "kalyan",
    "milan-night": "milan-night",
    "kalyan-night": "kalyan-night",
    "rajdhani-night": "rajdhani-night",
    "main-bazar": "main-bazar",
}
RESULT_RE = re.compile(r"^(\d{3})-(\d{1,2})-(\d{3})$")

def week_bounds(today):
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)

def date_label(start, end):
    return f"{start:%d-%m-%Y} to {end:%d-%m-%Y}"

def row_for_week(rows, start, end):
    label = date_label(start, end)
    for row in rows:
        raw = str(row.get("date", ""))
        dates = re.findall(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", raw)
        if len(dates) >= 2:
            parsed = []
            try:
                for d, m, y in dates[:2]:
                    year = int(y)
                    if year < 100:
                        year += 2000
                    parsed.append(datetime(year, int(m), int(d)).date())
            except ValueError:
                # Chart files contain legacy date labels in several formats.
                # Ignore malformed matches instead of failing the entire live refresh.
                continue
            if len(parsed) == 2 and parsed[0] == start and parsed[1] == end:
                return row
    row = {"date": label}
    for day in DAYS:
        row[f"{day} Open"] = "★"
        row[f"{day} Jodi"] = "★"
        row[f"{day} Close"] = "★"
    rows.append(row)
    rows.sort(key=lambda r: _row_start(r), reverse=False)
    return next(r for r in rows if r.get("date") == label)

def _row_start(row):
    dates = re.findall(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", str(row.get("date", "")))
    if not dates:
        return datetime.min.date()
    d, m, y = dates[0]
    year = int(y) + (2000 if int(y) < 100 else 0)
    try:
        return datetime(year, int(m), int(d)).date()
    except ValueError:
        return datetime.min.date()

def main():
    today = datetime.now(TZ).date()
    start, end = week_bounds(today)
    feed = json.loads(FEED.read_text(encoding="utf-8"))
    latest = feed.get("latest_results", {})
    updated = 0
    for market_id, chart_key in MARKET_TO_CHART.items():
        path = CHARTS / f"{chart_key}.json"
        if not path.exists():
            print(f"Skip missing chart file: {path.name}")
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            chart = doc.get("charts", {}).get(chart_key, doc)
            rows = chart.get("rows")
            if not isinstance(rows, list):
                print(f"Skip chart without rows: {path.name}")
                continue
            row = row_for_week(rows, start, end)
            # Always keep the current dated week visible, even before a result is published.
            day = DAYS[today.weekday()]
            item = latest.get(market_id, {})
            posted = str(item.get("telegram_posted_at", ""))
            # Telegram items must carry a post timestamp from today. For non-Telegram
            # live cards, the current fetch timestamp can date the observation.
            source_stamp = posted if str(item.get("source", "")).startswith("https://t.me/") else str(feed.get("live_fetched_at") or "")
            try:
                stamp = datetime.fromisoformat(source_stamp.replace("Z", "+00:00")).astimezone(TZ).date()
            except (ValueError, TypeError):
                stamp = None
            if item and stamp == today:
                result_text = str(item.get("result", "")).strip()
                match = RESULT_RE.fullmatch(result_text)
                if match:
                    op, jodi, cl = match.groups()
                    row[f"{day} Open"] = op
                    row[f"{day} Jodi"] = jodi.zfill(2)
                    row[f"{day} Close"] = cl
                    updated += 1
                else:
                    # Preserve partial published results (e.g. open-panel + jodi)
                    # without inventing the close panel. Accept only clearly shaped
                    # partial formats and leave unpublished fields as their existing
                    # placeholder or blank.
                    partial = re.fullmatch(r"(\d{3})-(\d{1,2})", result_text)
                    if partial:
                        op, jodi = partial.groups()
                        row[f"{day} Open"] = op
                        row[f"{day} Jodi"] = jodi.zfill(2)
                        row[f"{day} Close"] = "★"
                        updated += 1
                    else:
                        open_only = re.fullmatch(r"(\d{3})", result_text)
                        if open_only:
                            row[f"{day} Open"] = open_only.group(1)
                            row[f"{day} Jodi"] = "★"
                            row[f"{day} Close"] = "★"
                            updated += 1
            chart["rows"] = rows
            chart["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if "charts" in doc:
                doc["charts"][chart_key] = chart
            else:
                doc = chart
            doc["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            print(f"Could not update {path.name}: {exc}")
            raise
    print(f"Ensured dated week {date_label(start, end)} exists for all charts; wrote {updated} complete results.")

if __name__ == "__main__":
    main()

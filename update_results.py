#!/usr/bin/env python3
"""Fetch public historical chart tables for DP 777.
This archives published records only; it does not generate predictions.
"""
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "results.json"
SOURCES = {
    "sridevi-day": ("Sridevi", "https://dpbossx.net/sridevi-penal-chart-record.php"),
    "time-bazar": ("Time Bazar", "https://dpbosss.tax/panel-chart-record/time-bazar.php"),
    "milan-day": ("Milan Day", "https://matkaonline.games/panel-chart/MILAN-DAY"),
    "rajdhani-day": ("Rajdhani Day", "https://dpbossss.net/panel-chart-record/rajdhani-day.php"),
    "kalyan": ("Kalyan", "https://dpbossx.net/kalyan-penal-chart.php"),
    "sridevi": ("Sridevi Night", "https://dpbossss.com/panel-chart-record/sridevi-night.php"),
    "milan-night": ("Milan Night", "https://matkaonline.games/panel-chart/MILAN-NIGHT"),
    "kalyan-night": ("Kalyan Night", "https://dpboss247.com/chart/panel/kalyan-night"),
    "rajdhani-night": ("Rajdhani Night", "https://dpboss247.com/chart/panel/rajdhani-night"),
    "main-bazar": ("Main Bazar", "https://dpboss247.com/chart/panel/main-bazar"),
}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def text_of(cell):
    return re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip()

def fetch_html(url):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read().decode("utf-8", errors="replace")

def extract_khabar_table(html):
    """Parse every weekly chart table embedded in Khabar.bet, including hidden historical-year sections."""
    soup = BeautifulSoup(html, "html.parser")
    rows_by_date = {}
    day_headers = []
    tables_seen = 0
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        local_headers = []
        local_rows = []
        for tr in trs:
            cells = tr.find_all(["th", "td"], recursive=False)
            vals = [text_of(cell) for cell in cells]
            if not vals:
                continue
            joined = " ".join(vals).lower()
            if not local_headers and ("date" in joined or any(d.lower() in joined for d in DAYS)):
                for value in vals[1:]:
                    match = re.search(r"mon|tue|wed|thu|fri|sat|sun", value, re.I)
                    if match:
                        day = match.group(0).title()
                        if day not in local_headers:
                            local_headers.append(day)
                continue
            if not re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", vals[0]):
                continue
            item = {"date": re.sub(r"\s+", " ", vals[0]).strip()}
            for idx, day in enumerate(local_headers, start=1):
                cell_text = vals[idx] if idx < len(vals) else ""
                # Source table cells may render the three panel digits on separate lines.
                compact = re.sub(r"\s+", "", cell_text)
                digits = "".join(re.findall(r"\d", compact))
                if len(digits) >= 8:
                    item[f"{day} Open"] = digits[:3]
                    item[f"{day} Jodi"] = digits[3:5]
                    item[f"{day} Close"] = digits[5:8]
                elif not digits and re.search(r"[*★☆✪]", compact):
                    item[f"{day} Open"] = item[f"{day} Jodi"] = item[f"{day} Close"] = "***"
                else:
                    item[f"{day} Open"] = item[f"{day} Jodi"] = item[f"{day} Close"] = "***"
            if local_headers and len(item) > 1:
                local_rows.append(item)
        if local_rows:
            tables_seen += 1
            if not day_headers:
                day_headers = local_headers
            for row in local_rows:
                rows_by_date[row["date"]] = row
    if not rows_by_date:
        raise RuntimeError("No dated weekly chart rows found in any Khabar.bet table; older tabs may be loaded dynamically")
    rows = list(rows_by_date.values())
    print(f"INFO Khabar.bet archive: parsed {len(rows)} unique weeks from {tables_seen} embedded table(s)")
    return day_headers or DAYS, rows

def extract_milan_panel_archive(html, chart_id=None):
    """Parse MatkaOnline weekly Milan Day/Night tables; each weekday cell contains open, jodi and close."""
    soup = BeautifulSoup(html, "html.parser")
    best = None
    best_score = 0
    for table in soup.find_all("table"):
        txt = text_of(table).lower()
        score = int("date" in txt) + sum(day.lower() in txt for day in ["mon", "tue", "wed", "thu", "fri", "sat"])
        if score > best_score and re.search(r"\b(?:2012|2013|2014|2015|2016|2017|2018|2019|2020|2021|2022|2023|2024|2025|2026)\b", txt):
            best, best_score = table, score
    if not best:
        raise RuntimeError("No historical Milan Day archive table found")
    rows = []
    for tr in best.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        vals = [text_of(c) for c in cells]
        if not vals or not re.search(r"\d{1,2}[-/]\w{3}[-/]\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", vals[0], re.I):
            continue
        # Source cells have all three fields together, for example '267 75 890'.
        item = {"date": re.sub(r"\s+", " ", vals[0]).strip()}
        for i, day in enumerate(DAYS):
            cell = vals[i+1] if i+1 < len(vals) else ""
            nums = re.findall(r"(?<!\d)\d{1,3}(?!\d)", cell)
            stars = bool(re.search(r"\*|★|☆|✪", cell))
            if len(nums) >= 3:
                item[f"{day} Open"], item[f"{day} Jodi"], item[f"{day} Close"] = nums[0].zfill(3), nums[1].zfill(2), nums[2].zfill(3)
            elif stars:
                item[f"{day} Open"] = item[f"{day} Jodi"] = item[f"{day} Close"] = "***"
            else:
                item[f"{day} Open"] = item[f"{day} Jodi"] = item[f"{day} Close"] = ""
        rows.append(item)
    if not rows:
        raise RuntimeError("Milan Day archive table has no readable dated rows")
    # Newest-first sources are okay; deduplicate by week and sort oldest-first for easy archive navigation.
    unique = {row["date"]: row for row in rows}
    rows = list(unique.values())
    return DAYS, rows

def extract_table(html, chart_id=None):
    soup = BeautifulSoup(html, "html.parser")
    best = None
    best_score = 0
    for table in soup.find_all("table"):
        txt = text_of(table).lower()
        score = int("date" in txt) + sum(day.lower() in txt for day in ["mon", "tue", "wed", "thu", "fri"])
        if score > best_score and ("20" in txt or "19" in txt):
            best, best_score = table, score
    if not best:
        raise RuntimeError("Could not find the historical date/week table; source layout may have changed")
    trs = best.find_all("tr")
    header = []
    raw_rows = []
    for tr in trs:
        cells = tr.find_all(["th", "td"], recursive=False)
        vals = [text_of(c) for c in cells]
        if not vals:
            continue
        joined = " ".join(vals).lower()
        if not raw_rows and ("date" in joined or any(d.lower() in joined for d in DAYS)):
            header = vals
            continue
        if (chart_id == "sridevi" and len(vals) >= 5 and (re.search(r"\d{2}[-/]\d{2}[-/]\d{2,4}", vals[0]) or vals[0].strip().lower() == "to")) or (chart_id != "sridevi" and re.search(r"\d{2}[-/]\d{2}[-/]\d{2,4}", vals[0])):
            raw_rows.append(vals)
    if not raw_rows:
        # Some layouts place the range in a nested element or use a separate header row.
        for tr in trs:
            cells = tr.find_all(["th", "td"], recursive=False)
            vals = [text_of(c) for c in cells]
            if vals and re.search(r"\d{2}[-/]\d{2}[-/]\d{2,4}", vals[0]) and len(vals) > 1:
                raw_rows.append(vals)
    if not raw_rows:
        raise RuntimeError("Found chart table but no dated records")
    # A weekly panel chart stores THREE cells per weekday: open panna, jodi, close panna.
    # Keep each cell separate; never infer one value by splitting another cell's text.
    max_cells = max(len(row) for row in raw_rows)
    day_headers = []
    for value in header[1:]:
        match = re.search(r"mon|tue|wed|thu|fri|sat|sun", value, re.I)
        if match:
            day = match.group(0).title()
            if day not in day_headers:
                day_headers.append(day)
    if not day_headers:
        day_headers = DAYS[:min(7, max(1, (max_cells - 1) // 3))]
    keys = ["date"]
    for day in day_headers:
        keys.extend([f"{day} Open", f"{day} Jodi", f"{day} Close"])
    rows = []
    for raw in raw_rows:
        item = {"date": raw[0]}
        for i, key in enumerate(keys[1:], start=1):
            value = raw[i] if i < len(raw) else ""
            value = re.sub(r"\s+", "", value) if key.endswith(("Open", "Close")) and re.fullmatch(r"[\d\s]+", value or "") else value.strip()
            # Star/asterisk placeholders are preserved as missing-result markers.
            if value in ("*", "**", "***"):
                value = "***"
            item[key] = value
        rows.append(item)
    # Some source pages repeat the final weekday column because their HTML
    # table has a merged/duplicated cell. Detect a systematic copy of the
    # previous day's complete Open/Jodi/Close triple and blank that suspicious
    # column rather than presenting false duplicate results as real data.
    day_names = [d for d in DAYS if any(k.startswith(d + " ") for k in rows[0])]
    if len(day_names) >= 2 and len(rows) >= 4:
        for idx in range(1, len(day_names)):
            prev_day, day = day_names[idx - 1], day_names[idx]
            comparable = 0
            same_triples = 0
            for item in rows:
                prev = tuple(item.get(f"{prev_day} {part}", "").strip() for part in ("Open", "Jodi", "Close"))
                cur = tuple(item.get(f"{day} {part}", "").strip() for part in ("Open", "Jodi", "Close"))
                if all(v and not re.fullmatch(r"\*+", v) for v in prev + cur):
                    comparable += 1
                    if cur == prev:
                        same_triples += 1
            if comparable >= 4 and same_triples / comparable >= 0.75:
                print(f"WARN {chart_id or 'chart'}: {day} column duplicates {prev_day} in {same_triples}/{comparable} rows; blanking suspicious copied values")
                for item in rows:
                    for part in ("Open", "Jodi", "Close"):
                        item[f"{day} {part}"] = ""
    # Keep original source order, but reject accidental non-chart rows.
    return header, rows

LIVE_URL = "https://dpbossg.mobi/"
LIVE_MARKETS = {
    "time-bazar": ("Time Bazar", ["TIME BAZAR"]),
    "milan-day": ("Milan Day", ["MILAN DAY"]),
    "main-mumbai": ("Main Mumbai", ["OLD MAIN MUMBAI", "MAIN MUMBAI"]),
    "sridevi": ("Sridevi Night", ["SRIDEVI NIGHT"]),
    "milan-night": ("Milan Night", ["MILAN NIGHT"]),
    "rajdhani-day": ("Rajdhani Day", ["RAJDHANI DAY"]),
    "rajdhani-night": ("Rajdhani Night", ["RAJDHANI NIGHT"]),
}

def extract_live_results(html):
    """Extract only complete published open-jodi-close triples from labelled cards."""
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    result_re = re.compile(r"(?<!\d)(\d{3}\s*[-–]\s*\d{1,2}(?:\s*[-–]\s*\d{3})?)(?!\d)")
    for chart_id, (name, aliases) in LIVE_MARKETS.items():
        for alias in aliases:
            for label in soup.find_all(string=lambda s: s and re.sub(r"\s+", " ", s).strip().upper() == alias):
                node = label.parent
                for _ in range(5):
                    if node is None:
                        break
                    text = re.sub(r"\\s+", " ", node.get_text(" ", strip=True))
                    match = result_re.search(text)
                    # Avoid grabbing a result from a large page/container with many markets.
                    if match and len(text) <= 700:
                        found[chart_id] = {
                            "name": name,
                            "result": re.sub(r"\s*[-–]\s*", "-", match.group(1)),
                            "source": LIVE_URL,
                            "source_label": alias,
                        }
                        break
                    node = node.parent
                if chart_id in found:
                    break
            if chart_id in found:
                break
    return found

def fetch_live_results():
    html = fetch_html(LIVE_URL)
    results = extract_live_results(html)
    if not results:
        raise RuntimeError("Public page returned no labelled complete results; live values were not guessed")
    return results

def week_start_key(value):
    """Normalize a weekly range to its start date so alternate date formats don't duplicate a week."""
    match = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", str(value or ""))
    if not match:
        match = re.search(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", str(value or ""), re.I)
        if match:
            try:
                from datetime import datetime
                return datetime.strptime("-".join(match.groups()), "%d-%b-%Y").date().isoformat()
            except ValueError:
                return None
        return None
    day, month, year = map(int, match.groups())
    if year < 100:
        year += 2000
    try:
        from datetime import date
        return date(year, month, day).isoformat()
    except ValueError:
        return None

def deduplicate_overlapping_weeks(rows, chart_id):
    """Collapse rows with the same week-start date, keeping the most complete values."""
    by_start = {}
    order = []
    for row in rows:
        key = week_start_key(row.get("date"))
        if not key:
            key = "raw:" + str(row.get("date", ""))
        if key not in by_start:
            by_start[key] = dict(row)
            order.append(key)
            continue
        current = by_start[key]
        incoming_score = sum(bool(str(v).strip()) and not re.fullmatch(r"[★☆*\s—-]+", str(v).strip()) for k,v in row.items() if k != "date")
        current_score = sum(bool(str(v).strip()) and not re.fullmatch(r"[★☆*\s—-]+", str(v).strip()) for k,v in current.items() if k != "date")
        preferred, other = (dict(row), current) if incoming_score > current_score else (current, row)
        # Preserve the better populated date label, then fill any missing/star cells
        # from the overlapping row without replacing a real result with a placeholder.
        for key_name, value in other.items():
            existing = str(preferred.get(key_name, "")).strip()
            candidate = str(value).strip()
            placeholder = not candidate or bool(re.fullmatch(r"[★☆*\s—-]+", candidate))
            existing_placeholder = not existing or bool(re.fullmatch(r"[★☆*\s—-]+", existing))
            if key_name != "date" and existing_placeholder and not placeholder:
                preferred[key_name] = value
        by_start[key] = preferred
        print(f"WARN {chart_id}: merged overlapping duplicate week rows for {key}")
    return [by_start[key] for key in order]

def merge_rows_preserving_results(old_rows, new_rows, chart_id):
    """Merge rows by week; blank/star values never erase previously saved results."""
    def is_placeholder(value):
        value = str(value or "").strip()
        return not value or bool(re.fullmatch(r"[★☆*\s—-]+", value))

    merged = {}
    order = []
    for row in list(old_rows or []) + list(new_rows or []):
        key = week_start_key(row.get("date")) or ("raw:" + str(row.get("date", "")))
        if key not in merged:
            merged[key] = dict(row)
            order.append(key)
            continue
        target = merged[key]
        # Prefer a useful date label from the incoming row.
        if row.get("date"):
            target["date"] = row["date"]
        for field, value in row.items():
            if field == "date":
                continue
            current = target.get(field)
            # Preserve an existing real value if the new scrape is blank or a star.
            if is_placeholder(value) and not is_placeholder(current):
                continue
            if not is_placeholder(value) or is_placeholder(current):
                target[field] = value
    if len(merged) < len(list(old_rows or [])):
        print(f"INFO {chart_id}: collapsed duplicate weeks while preserving real values")
    return [merged[key] for key in order]

def main():
    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            old = {}
    charts = dict(old.get("charts", {}))
    # results.json may be empty or unavailable after a previous failed run.
    # Recover each market's last known-good archive from its individual chart file
    # before fetching anything, so a bad scrape cannot wipe the public chart data.
    chart_dir = OUT.parent / "charts"
    for chart_id, (name, url) in SOURCES.items():
        if chart_id in charts:
            continue
        backup_path = chart_dir / f"{chart_id}.json"
        if not backup_path.exists():
            continue
        try:
            backup = json.loads(backup_path.read_text(encoding="utf-8"))
            saved_chart = backup.get("charts", {}).get(chart_id)
            if not saved_chart and isinstance(backup.get("rows"), list):
                saved_chart = backup
            if saved_chart and isinstance(saved_chart.get("rows"), list):
                charts[chart_id] = saved_chart
                print(f"INFO {name}: recovered {len(saved_chart['rows'])} saved rows from {backup_path.name}")
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARN {name}: could not read backup {backup_path.name}: {exc}")
    updated_count = 0
    for chart_id, (name, url) in SOURCES.items():
        try:
            html = fetch_html(url)
            header, rows = extract_milan_panel_archive(html, chart_id) if chart_id in ("milan-day", "milan-night") else extract_table(html)
            rows = deduplicate_overlapping_weeks(rows, chart_id)
            rows = merge_rows_preserving_results(charts.get(chart_id, {}).get("rows", []), rows, chart_id)
            if chart_id == "milan-day" and not any(re.search(r"201[0-9]|202[0-5]", str(row.get("date", ""))) for row in rows):
                raise RuntimeError("Milan Day archive did not expose older historical rows; keeping previous archive rather than replacing it with recent-only data")
            charts[chart_id] = {
                "title": f"{name} historical records",
                "source": url,
                "rows": rows,
                "columns": list(rows[0].keys()) if rows else [],
                "record_count": len(rows),
                "status": "ok",
            }
            print(f"OK {name}: {len(rows)} rows")
            updated_count += 1
        except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as exc:
            print(f"WARN {name}: {exc}")
            # Keep the last successful data instead of replacing it with empty data.
            if chart_id in charts:
                charts[chart_id]["status"] = "stale"
                charts[chart_id]["last_error"] = str(exc)
            else:
                charts[chart_id] = {
                    "title": f"{name} historical records",
                    "source": url,
                    "rows": [],
                    "columns": [],
                    "record_count": 0,
                    "status": "unavailable",
                    "last_error": str(exc),
                }
        time.sleep(1)  # be considerate to the source website
    # Avoid a commit every hour when source rows have not changed.
    previous_charts = old.get("charts", {})
    changed = any(
        previous_charts.get(chart_id, {}).get("rows") != charts.get(chart_id, {}).get("rows")
        or previous_charts.get(chart_id, {}).get("source") != charts.get(chart_id, {}).get("source")
        for chart_id in SOURCES
    )
    updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds") if changed or not old.get("updated_at") else old["updated_at"]
    payload = {
        "site": "DP 777",
        "updated_at": updated_at,
        "updated_charts": updated_count,
        "latest_results": old.get("latest_results", {}),
        "live_fetched_at": old.get("live_fetched_at"),
        "live_source": old.get("live_source", "https://dpbossg.mobi/"),
        "live_status": old.get("live_status", "unknown"),
        "charts": charts,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    chart_dir = OUT.parent / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    for chart_id, chart in charts.items():
        (chart_dir / f"{chart_id}.json").write_text(
            json.dumps({"updated_at": updated_at, "charts": {chart_id: chart}}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    if updated_count == 0:
        raise SystemExit("No source charts could be updated; existing data was preserved where available")

if __name__ == "__main__":
    main()

# Recovery run: rebuild the ten configured charts after repairing the JSON archive.

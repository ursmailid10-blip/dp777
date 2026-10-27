# DP 777

Mobile-friendly historical chart archive for these seven charts:

- Time Bazar
- Milan Day
- Main Mumbai
- Sridevi
- Milan Night
- Rajdhani Day
- Rajdhani Night

## Website

If GitHub Pages is enabled for the parent repository, this folder is available at:

https://raghucse99-collab.github.io/sulabham/dp777/

## Automatic refresh

The workflow at `.github/workflows/dp777-update.yml` runs hourly and can also be started manually from **Actions → DP 777 historical chart refresh → Run workflow**. It reads public historical chart pages from Khabar.bet, updates `data/results.json`, and commits changes to the repository.

The updater is best-effort: it preserves the last successful chart data if a source is temporarily unavailable or changes its HTML. Check the Actions run log if a chart is missing or stale.

## Data notes

- This is a historical archive, not a prediction service.
- The original source link is shown for each chart.
- The updater depends on the source pages being publicly reachable and their chart table markup remaining compatible.
- The current implementation refreshes the historical table snapshots. It does not guarantee a result will be published by the source at a specific time.
- Do not add private credentials or API keys to this repository.

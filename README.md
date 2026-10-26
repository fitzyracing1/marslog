# marslog

A [knoblog](https://github.com/fitzyracing1/knoblog)-style changelog for Mars: a daily GitHub Actions job caches **public NASA rover metadata** (Perseverance + Curiosity raw images, plus weather) into this repo and publishes a per-sol changelog site, like [knobs-watch](https://github.com/fitzyracing1/knobs-watch).

Site: https://fitzyracing1.github.io/marslog/ · [data.json](https://fitzyracing1.github.io/marslog/data.json) · [Atom](https://fitzyracing1.github.io/marslog/feed.xml) · [images.csv.gz](https://fitzyracing1.github.io/marslog/data/images.csv.gz)

## Sources (public, no API key)
| data | endpoint |
|---|---|
| Perseverance raw images | `https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020&feedtype=json` (filter `condition_2=<sol>:sol:gte&condition_3=<sol>:sol:lte`, 100/page) |
| Curiosity raw images | `https://mars.nasa.gov/api/v1/raw_image_items/?condition_1=msl:mission` (same sol conditions) |
| Perseverance MEDA weather | `https://mars.nasa.gov/rss/api/?feed=weather&category=mars2020&feedtype=json` |
| Curiosity REMS weather | `https://mars.nasa.gov/rss/api/?feed=weather&category=msl&feedtype=json` |

Only metadata and URLs are stored (no image binaries). Images: NASA/JPL-Caltech. REMS weather is from CAB and intended for outreach; for science-grade data use [PDS](https://pds-atmospheres.nmsu.edu/). Weather feeds lag and have gaps.

## Layout
- `data/<mission>/<sol>.json` – every image (id, camera, filter, timestamps UTC/LMST, site/drive, mast az/el, URLs) + that sol's weather
- `data/<mission>/weather.json` – full weather series
- `data/<mission>/changes.json` – the changes layer: per-sol counts per camera, Δ vs previous sol, instruments new to the cache, weather deltas
- `data/images.csv.gz` – combined flat dataset (all missions)
- `site/` (built, not committed) – index, page per sol, `data.json`, `feed.xml`, `sitemap.xml`, `robots.txt`

## Run
```sh
python -m marslog.fetch --backfill 30   # ensure last 30 sols cached; re-fetches last 3 (late downlinks)
python -m marslog.build                 # changes + site
pip install pandas matplotlib && python study/study.py   # study starter -> study/out/
```
Deeper backfill: Actions → daily → Run workflow → `backfill` = e.g. 400 (time budget 30 min/run; rerun to continue).

## Traverse / slope driving
`python -m marslog.traverse` caches end-of-drive localizations (sol, lat/lon, easting/northing, geoid elevation, tilt, drive length, odometer) from NASA's public MMGIS feeds
([M20_waypoints.json](https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json), [MSL_waypoints.json](https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json)) into `data/traverse/`, refreshed daily.
Sol pages show a Traverse table; all points with per-drive Δelev/grade are in [`traverse.json`](https://fitzyracing1.github.io/marslog/traverse.json).
`python study/traverse_study.py` computes per-drive grade, uphill/flat/downhill behaviour, extremes, and the REMS pressure-vs-altitude fit (charts in `study/charts/traverse/`).
The feeds carry no per-drive timing, so speed is not available; distance per drive / per driving sol is used instead.

## Heat model
A small ML model of Curiosity's daily **max/min air temperature** (REMS), retrained and re-predicted by the daily workflow.
Features: Ls season (sin/cos, 2 harmonics), Mars year, traverse elevation interpolated by sol, last pressure, lagged temps (last obs, 7-obs mean, gap). Models: Ridge seasonal baseline + scikit-learn HistGradientBoosting, time-based split (last 20% of sols held out), MAE vs persistence/climatology.
- Latest forecast: https://fitzyracing1.github.io/marslog/heat.json
- Everything it learned: https://fitzyracing1.github.io/marslog/heat/learned.md (also `study/heat/learned.{md,json}`)
```sh
curl -s https://fitzyracing1.github.io/marslog/heat.json | python -m json.tool
pip install scikit-learn pandas numpy
python -m marslog.heat train            # retrain + write reports
python -m marslog.heat predict --sol 5100
```

## Plans

This project is free, and its license stays as is. Support it through [GitHub Sponsors](https://github.com/sponsors/fitzyracing1):

- **Free**: use the code, community support.
- **Pro ($49/month)**: priority issues and support.
- **Team ($199/month)**: priority support for your team plus early access.

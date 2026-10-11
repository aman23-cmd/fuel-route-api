# Fuel Route API (Django 6.1)

Given a start and finish in the USA, returns the driving route (GeoJSON + a map page),
the cost‑optimal fuel stops along it, and the total fuel spend
(500‑mile max range, 10 mpg → 50 gal tank).

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py load_stations      # one‑off: loads + geocodes the CSV (~2s)
python manage.py runserver
python manage.py test               # planner is checked against an exact DP
```

## API

`POST /api/route/`
```json
{"start": "Dallas, TX", "finish": "Chicago, IL"}
```
(`GET /api/route/?start=...&finish=...` also works.) Inputs may be `"City, ST"`,
`"City, State Name"`, or `"lat,lng"`. Anything else falls back to Nominatim (free text).

Response: `route` (distance, duration, GeoJSON LineString), `fuel_stops[]`
(name, address, price, gallons bought, cost, mile marker, distance off route),
`summary.total_fuel_cost`, `map_url`, and `meta` (external call count, timing, cache hit).

`GET /api/route/map/?start=...&finish=...` renders the route and stops on a Leaflet/OSM map.

## How it meets the brief

| Requirement | Approach |
|---|---|
| Few calls to the map API | **One** OSRM call per route (`overview=full`). Start/finish are geocoded offline from a bundled gazetteer ("City, ST" / coordinates), so no geocoding call either. Nominatim is only a fallback for free text (→ max 3 calls). Results are cached, so a repeat request makes **zero** calls. |
| Fast | Stations are geocoded once at load time and held in memory as numpy arrays. Per request: resample route → KD‑tree → vectorised nearest‑point lookup of ~6.6k stations → O(n) planner. ≈ 5–15 ms of our own compute; latency is dominated by the single OSRM call. |
| Cost‑optimal | Exact greedy "next‑cheaper‑station" algorithm for the refuelling problem (buy only enough to reach a cheaper station, otherwise fill up and go to the cheapest station in range). `routing/tests.py` verifies it equals a brute‑force DP on 300 random instances. |

## Design / assumptions (worth knowing)

* **The CSV has no coordinates.** Stations are placed at the centroid of their city/state
  (bundled US gazetteer, 99.8 % match). So a station can be several miles from its real
  position; the search corridor is therefore 10 mi (widened to 20/35 mi only if no feasible
  plan exists, e.g. the sparse West). `miles_from_route` is reported for each stop.
  Upgrade path: batch‑geocode exact addresses once and re‑run `load_stations`.
* The vehicle **leaves the origin with an empty tank**, so the first purchase is at the first
  station on the route and total gallons = distance ÷ 10. This makes the total cost the true
  cost of all fuel burned. (Remove this if you'd rather assume a pre‑paid full tank.)
* Detours to stations off the highway are not added to the distance (they're ≤ the corridor width).
* Duplicate OPIS IDs (same station listed under two names) are merged, keeping the cheapest
  price; Canadian provinces in the CSV are dropped; lower‑48 only.
* A trip where a >500‑mile stretch has no station returns HTTP 422.
* Minimising cost can mean more, shorter stops than a human would choose; that's by design.

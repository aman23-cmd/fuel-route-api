import hashlib
import time

import numpy as np
from django.conf import settings
from django.core.cache import cache
from scipy.spatial import cKDTree

from . import geocoding, osrm, planner
from .geometry import cumulative_miles, decimate, resample, to_xyz
from .stations import get_index


class TripError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def _corridor_stations(route_pts_xyz, route_miles, radius):
    """Stations within `radius` miles of the route -> (station_idx, route_mile, offset)."""
    idx = get_index()
    dist, nearest = cKDTree(route_pts_xyz).query(idx.xyz, distance_upper_bound=radius)
    hit = np.isfinite(dist)
    sel = np.flatnonzero(hit)
    mile = route_miles[nearest[sel]]
    order = np.argsort(mile, kind="stable")
    return sel[order], mile[order], dist[sel][order]


def plan_trip(start_text, finish_text):
    t0 = time.perf_counter()
    cfg = settings.FUEL_ROUTE
    external_calls = []

    try:
        start = geocoding.geocode(start_text, external_calls)
        finish = geocoding.geocode(finish_text, external_calls)
    except geocoding.GeocodingError as exc:
        raise TripError(str(exc), 400)

    key = "trip:" + hashlib.md5(
        f"{start.lat:.4f},{start.lng:.4f}|{finish.lat:.4f},{finish.lng:.4f}".encode()).hexdigest()
    cached = cache.get(key)
    if cached:
        result = dict(cached)
        result["meta"] = {"cached": True, "external_api_calls": 0,
                          "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1)}
        return result

    try:
        route = osrm.fetch_route((start.lat, start.lng), (finish.lat, finish.lng))
        external_calls.append("osrm")
    except osrm.RoutingError as exc:
        raise TripError(str(exc), 502)

    # distance along the route (scaled so it agrees with the routing engine's figure)
    cum = cumulative_miles(route.lat, route.lng)
    scale = route.distance_miles / cum[-1] if cum[-1] > 0 else 1.0
    d, rlat, rlng = resample(route.lat, route.lng, cum, step=0.5)
    route_miles, route_xyz = d * scale, to_xyz(rlat, rlng)

    idx = get_index()
    max_range, mpg = cfg["MAX_RANGE_MILES"], cfg["MPG"]
    plan_stops, radius_used = None, None
    for radius in cfg["CORRIDOR_MILES"]:
        sel, mile, offset = _corridor_stations(route_xyz, route_miles, radius)
        if len(sel) == 0:
            continue
        nodes = [planner.Node(pos=0.0 if i == 0 else float(mile[i]), price=float(idx.price[sel[i]]),
                              ref=(int(sel[i]), float(offset[i])), shown_mile=float(mile[i]))
                 for i in range(len(sel))]
        try:
            plan_stops = planner.plan(nodes, route.distance_miles, max_range, mpg)
            radius_used = radius
            break
        except planner.NoFeasiblePlan:
            continue
    if plan_stops is None:
        raise TripError("No feasible fuelling plan: there is a stretch longer than "
                        f"{max_range:.0f} miles with no fuel station near the route.")

    stops = []
    for s in plan_stops:
        i, offset = s.ref
        name, address, city, state = idx.meta[i]
        stops.append({
            "name": name, "address": address, "city": city, "state": state,
            "latitude": round(float(idx.lat[i]), 5), "longitude": round(float(idx.lng[i]), 5),
            "route_mile": round(s.mile, 1), "miles_from_route": round(offset, 1),
            "price_per_gallon": round(s.price, 4), "gallons": round(s.gallons, 2),
            "cost": round(s.cost, 2),
        })
    total_gal = sum(s.gallons for s in plan_stops)
    total_cost = sum(s.cost for s in plan_stops)

    dlat, dlng = decimate(route.lat, route.lng)
    result = {
        "start": {"query": start.query, "label": start.label, "latitude": start.lat, "longitude": start.lng},
        "finish": {"query": finish.query, "label": finish.label, "latitude": finish.lat, "longitude": finish.lng},
        "route": {
            "distance_miles": round(route.distance_miles, 1),
            "duration_hours": round(route.duration_hours, 2),
            "geometry": {"type": "LineString",
                         "coordinates": np.column_stack((dlng, dlat)).round(5).tolist()},
        },
        "fuel_stops": stops,
        "summary": {
            "total_fuel_cost": round(total_cost, 2),
            "total_gallons": round(total_gal, 2),
            "average_price_per_gallon": round(total_cost / total_gal, 3) if total_gal else None,
            "number_of_fuel_stops": len(stops),
            "assumptions": {"max_range_miles": max_range, "mpg": mpg,
                            "starts_with_empty_tank": True,
                            "station_search_radius_miles": radius_used},
        },
    }
    cache.set(key, result, cfg["CACHE_SECONDS"])
    result = dict(result)
    result["meta"] = {"cached": False, "external_api_calls": len(external_calls),
                      "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1)}
    return result

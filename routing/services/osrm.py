"""Routing via the free OSRM demo server: ONE request returns the whole route."""
from dataclasses import dataclass

import numpy as np
import requests
from django.conf import settings

M_PER_MILE = 1609.344


class RoutingError(Exception):
    pass


@dataclass
class Route:
    distance_miles: float
    duration_hours: float
    lat: np.ndarray
    lng: np.ndarray


def fetch_route(start, finish) -> Route:
    """start/finish are (lat, lng)."""
    cfg = settings.FUEL_ROUTE
    url = (f"{cfg['OSRM_URL']}/route/v1/driving/"
           f"{start[1]:.6f},{start[0]:.6f};{finish[1]:.6f},{finish[0]:.6f}")
    try:
        r = requests.get(url, params={"overview": "full", "geometries": "geojson",
                                      "steps": "false", "alternatives": "false"},
                         timeout=cfg["OSRM_TIMEOUT"], headers={"User-Agent": cfg["USER_AGENT"]})
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutingError(f"Routing service unavailable: {exc}") from exc
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(data.get("message") or f"No drivable route found ({data.get('code')}).")
    best = data["routes"][0]
    coords = np.asarray(best["geometry"]["coordinates"], float)  # [lng, lat]
    return Route(best["distance"] / M_PER_MILE, best["duration"] / 3600.0, coords[:, 1], coords[:, 0])

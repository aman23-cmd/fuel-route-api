"""
Turn user input into (lat, lng) without hitting an external API where possible.

Accepted:  "32.78,-96.80"  |  "Dallas, TX"  |  "Dallas, Texas"  |  free text (Nominatim fallback)
"""
import re
from dataclasses import dataclass

import requests
from django.conf import settings

from routing.models import City
from .text import normalize_city

# contiguous US + AK/HI is out of scope for road routing; bounding box check for the lower 48
LOWER48 = (24.4, 49.5, -125.0, -66.9)

STATE_NAMES = {
    "alabama": "AL", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY",
    "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
    "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}
_LATLNG = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*$")


class GeocodingError(ValueError):
    pass


@dataclass
class Place:
    query: str
    label: str
    lat: float
    lng: float
    source: str  # coordinates | gazetteer | nominatim


def _check_us(lat, lng, query):
    if not (LOWER48[0] <= lat <= LOWER48[1] and LOWER48[2] <= lng <= LOWER48[3]):
        raise GeocodingError(f"'{query}' is outside the contiguous USA.")


def geocode(query: str, counter=None) -> Place:
    query = (query or "").strip()
    if not query:
        raise GeocodingError("Location is empty.")

    m = _LATLNG.match(query)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        _check_us(lat, lng, query)
        return Place(query, f"{lat:.4f}, {lng:.4f}", lat, lng, "coordinates")

    # "City, ST" / "City, State Name" (optionally followed by ", USA")
    parts = [p.strip() for p in re.sub(r",?\s*(usa|us|united states)$", "", query, flags=re.I).split(",")]
    if len(parts) == 2:
        state = parts[1].upper() if len(parts[1]) == 2 else STATE_NAMES.get(parts[1].lower())
        if state:
            hit = City.objects.filter(name_key=normalize_city(parts[0]), state=state).order_by("id").first()
            if hit:
                _check_us(hit.latitude, hit.longitude, query)
                return Place(query, f"{hit.name}, {hit.state}", hit.latitude, hit.longitude, "gazetteer")

    cfg = settings.FUEL_ROUTE
    if not cfg["NOMINATIM_FALLBACK"]:
        raise GeocodingError(f"Could not resolve '{query}'. Use 'City, ST' or 'lat,lng'.")
    return _nominatim(query, counter)


def _nominatim(query, counter):
    cfg = settings.FUEL_ROUTE
    try:
        if counter is not None:
            counter.append("nominatim")
        r = requests.get(cfg["NOMINATIM_URL"], timeout=10, headers={"User-Agent": cfg["USER_AGENT"]},
                         params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "us"})
        results = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise GeocodingError(f"Could not resolve '{query}' (geocoder unavailable).") from exc
    if not results:
        raise GeocodingError(f"Could not find '{query}' in the USA.")
    lat, lng = float(results[0]["lat"]), float(results[0]["lon"])
    _check_us(lat, lng, query)
    return Place(query, results[0].get("display_name", query), lat, lng, "nominatim")

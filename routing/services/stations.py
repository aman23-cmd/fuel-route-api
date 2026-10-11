"""In-memory station index so a request never touches the DB for stations."""
from dataclasses import dataclass

import numpy as np

from routing.models import FuelStation
from .geometry import to_xyz


@dataclass
class StationIndex:
    ids: np.ndarray
    lat: np.ndarray
    lng: np.ndarray
    price: np.ndarray
    xyz: np.ndarray
    meta: list  # (name, address, city, state) per row


_index = None


def get_index() -> StationIndex:
    global _index
    if _index is None:
        rows = list(FuelStation.objects.values_list(
            "id", "latitude", "longitude", "price", "name", "address", "city", "state"))
        if not rows:
            raise RuntimeError("No stations loaded. Run: python manage.py load_stations")
        lat = np.array([r[1] for r in rows]); lng = np.array([r[2] for r in rows])
        _index = StationIndex(
            ids=np.array([r[0] for r in rows]), lat=lat, lng=lng,
            price=np.array([float(r[3]) for r in rows]), xyz=to_xyz(lat, lng),
            meta=[r[4:] for r in rows])
    return _index


def clear_cache():
    global _index
    _index = None

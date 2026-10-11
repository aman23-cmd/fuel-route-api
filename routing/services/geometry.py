import numpy as np

EARTH_RADIUS_MI = 3958.7613


def to_xyz(lat, lng):
    """Lat/lng (degrees) -> 3D points on the earth (miles). Straight-line distance
    between two of these is a very good proxy for short great-circle distances and
    lets us use a KD-tree instead of per-pair haversine."""
    lat, lng = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lng, float))
    c = np.cos(lat)
    return EARTH_RADIUS_MI * np.column_stack((c * np.cos(lng), c * np.sin(lng), np.sin(lat)))


def haversine_miles(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(a))


def cumulative_miles(lat, lng):
    seg = haversine_miles(lat[:-1], lng[:-1], lat[1:], lng[1:])
    return np.concatenate(([0.0], np.cumsum(seg)))


def resample(lat, lng, cum, step=0.5):
    """Evenly space points along the polyline (so a long straight highway segment
    can't hide a station from the nearest-point search)."""
    total = cum[-1]
    d = np.append(np.arange(0.0, total, step), total)
    return d, np.interp(d, cum, lat), np.interp(d, cum, lng)


def decimate(lat, lng, min_gap_miles=0.3):
    """Thin a polyline for display. Keeps first/last point."""
    cum = cumulative_miles(lat, lng)
    keep = np.zeros(len(lat), bool)
    keep[0] = keep[-1] = True
    last = 0.0
    for i in range(1, len(lat) - 1):
        if cum[i] - last >= min_gap_miles:
            keep[i] = True
            last = cum[i]
    return lat[keep], lng[keep]

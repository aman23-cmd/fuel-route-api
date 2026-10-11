import re

_ABBREV = {"st": "saint", "ste": "sainte", "ft": "fort", "mt": "mount", "mtn": "mountain",
           "pt": "point", "spgs": "springs", "spg": "spring", "hts": "heights", "jct": "junction",
           "n": "north", "s": "south", "e": "east", "w": "west"}


def normalize_city(name: str) -> str:
    """'St. Louis' -> 'saint louis', 'Ft Worth' -> 'fort worth' (for offline matching)."""
    s = re.sub(r"[^a-z0-9 ]", " ", name.lower().replace("'", ""))
    return " ".join(_ABBREV.get(tok, tok) for tok in s.split())

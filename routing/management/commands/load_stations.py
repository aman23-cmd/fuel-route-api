"""
Load the fuel-price CSV into the DB, geocoded offline.

The CSV has no coordinates, and geocoding ~8k addresses per request would be far
too slow, so this is done ONCE here: each station is placed at the centroid of its
(city, state) using a bundled US city gazetteer. Requests then never geocode stations.

    python manage.py load_stations
"""
import csv
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from routing.models import City, FuelStation
from routing.services import stations as station_service
from routing.services.text import normalize_city


class Command(BaseCommand):
    help = "Load fuel stations (+ city gazetteer) into the database."

    def add_arguments(self, parser):
        data = Path(settings.BASE_DIR) / "data"
        parser.add_argument("--prices", default=str(data / "fuel-prices.csv"))
        parser.add_argument("--cities", default=str(data / "us_cities.csv"))

    @transaction.atomic
    def handle(self, *args, **opts):
        # 1. Gazetteer ------------------------------------------------------
        City.objects.all().delete()
        cities, lookup = [], {}
        with open(opts["cities"], newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                key = normalize_city(r["CITY"])
                lat, lng = float(r["LATITUDE"]), float(r["LONGITUDE"])
                cities.append(City(name=r["CITY"], name_key=key, state=r["STATE_CODE"],
                                   latitude=lat, longitude=lng))
                lookup.setdefault((key, r["STATE_CODE"]), (lat, lng))
        City.objects.bulk_create(cities, batch_size=5000)
        us_states = {s for _, s in lookup}

        # 2. Stations -------------------------------------------------------
        best = {}  # opis_id -> row (dedupe: same station listed under several names)
        skipped_non_us = skipped_nocoord = dupes = 0
        with open(opts["prices"], newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                state = r["State"].strip().upper()
                if state not in us_states:  # Canadian provinces are in the file
                    skipped_non_us += 1
                    continue
                coord = lookup.get((normalize_city(r["City"]), state))
                if coord is None:
                    skipped_nocoord += 1
                    continue
                oid, price = int(r["OPIS Truckstop ID"]), Decimal(r["Retail Price"])
                if oid in best:
                    dupes += 1
                    if price >= best[oid].price:  # keep the cheapest listing
                        continue
                best[oid] = FuelStation(
                    opis_id=oid, name=r["Truckstop Name"].strip(), address=r["Address"].strip(),
                    city=r["City"].strip(), state=state, price=price,
                    latitude=coord[0], longitude=coord[1])

        FuelStation.objects.all().delete()
        FuelStation.objects.bulk_create(best.values(), batch_size=2000)
        station_service.clear_cache()
        self.stdout.write(self.style.SUCCESS(
            f"Loaded {len(best)} stations ({dupes} duplicate rows merged, "
            f"{skipped_non_us} non-US skipped, {skipped_nocoord} un-geocodable skipped)."))

import random
from unittest import mock

import numpy as np
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, SimpleTestCase, override_settings

from .services import osrm, planner
from .services.geometry import cumulative_miles


# ---------------------------------------------------------------- planner ---
def brute_force_cost(positions, prices, total, mpg=10, tank=50):
    """Exact DP in whole-gallon units (positions are multiples of mpg miles)."""
    pts = [(p // mpg, pr) for p, pr in zip(positions, prices)] + [(total // mpg, 0)]
    INF = float("inf")
    best = {(0, 0): 0.0}  # (node, fuel) -> cost ; vehicle starts at node 0 with empty tank
    for i in range(len(pts)):
        for f in range(tank + 1):
            c = best.get((i, f), INF)
            if c == INF:
                continue
            if f < tank and i < len(pts) - 1:  # buy 1 gallon here
                k = (i, f + 1)
                best[k] = min(best.get(k, INF), c + pts[i][1])
            if i + 1 < len(pts):  # drive to next node
                need = pts[i + 1][0] - pts[i][0]
                if f >= need:
                    k = (i + 1, f - need)
                    best[k] = min(best.get(k, INF), c)
    return min(v for (i, f), v in best.items() if i == len(pts) - 1)


class PlannerTests(SimpleTestCase):
    def test_matches_exact_dp_on_random_instances(self):
        rng = random.Random(7)
        for _ in range(300):
            total = rng.randrange(40, 200) * 10
            n = rng.randrange(1, 14)
            positions = sorted({0} | {rng.randrange(1, total // 10) * 10 for _ in range(n)})
            prices = [round(rng.uniform(2.5, 5.0), 2) for _ in positions]
            nodes = [planner.Node(p, pr, ref=i) for i, (p, pr) in enumerate(zip(positions, prices))]
            try:
                stops = planner.plan(nodes, total, 500, 10)
            except planner.NoFeasiblePlan:
                continue
            got = sum(s.cost for s in stops)
            self.assertAlmostEqual(got, brute_force_cost(positions, prices, total), places=6)
            self.assertAlmostEqual(sum(s.gallons for s in stops), total / 10, places=6)

    def test_short_trip_single_stop(self):
        stops = planner.plan([planner.Node(0, 3.5, ref=0)], 100, 500, 10)
        self.assertEqual(len(stops), 1)
        self.assertAlmostEqual(stops[0].cost, 35.0)

    def test_gap_too_large_raises(self):
        with self.assertRaises(planner.NoFeasiblePlan):
            planner.plan([planner.Node(0, 3.0), planner.Node(600, 3.0)], 700, 500, 10)


# -------------------------------------------------------------------- API ---
def fake_route(start, finish):
    """Straight line, 12% longer to mimic roads, dense enough to look like a road geometry."""
    lat = np.linspace(start[0], finish[0], 2000)
    lng = np.linspace(start[1], finish[1], 2000)
    dist = cumulative_miles(lat, lng)[-1] * 1.12
    return osrm.Route(dist, dist / 62, lat, lng)


class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_stations", verbosity=0)

    def setUp(self):
        cache.clear()

    @override_settings(FUEL_ROUTE={**__import__("django.conf").conf.settings.FUEL_ROUTE, "NOMINATIM_FALLBACK": False})
    def test_long_trip(self):
        with mock.patch("routing.services.osrm.fetch_route", side_effect=fake_route) as m:
            r = self.client.post("/api/route/", {"start": "Los Angeles, CA", "finish": "New York, NY"},
                                 content_type="application/json")
            self.assertEqual(r.status_code, 200, r.content)
            d = r.json()
            self.assertEqual(m.call_count, 1)  # exactly one routing call
            self.assertGreater(len(d["fuel_stops"]), 4)
            miles = [s["route_mile"] for s in d["fuel_stops"]]
            self.assertEqual(miles, sorted(miles))
            self.assertAlmostEqual(d["summary"]["total_gallons"], d["route"]["distance_miles"] / 10, delta=0.1)
            self.assertAlmostEqual(sum(s["cost"] for s in d["fuel_stops"]), d["summary"]["total_fuel_cost"], delta=0.1)
            # never more than 500 miles between consecutive purchases that matter for range
            for a, b in zip(miles, miles[1:]):
                self.assertLessEqual(b - a, 500.5)
            # repeat -> served from cache, zero external calls
            r2 = self.client.post("/api/route/", {"start": "Los Angeles, CA", "finish": "New York, NY"},
                                  content_type="application/json").json()
            self.assertTrue(r2["meta"]["cached"])
            self.assertEqual(m.call_count, 1)

    @override_settings(FUEL_ROUTE={**__import__("django.conf").conf.settings.FUEL_ROUTE, "NOMINATIM_FALLBACK": False})
    def test_validation_and_errors(self):
        self.assertEqual(self.client.post("/api/route/", {"start": "Dallas, TX"},
                                          content_type="application/json").status_code, 400)
        r = self.client.get("/api/route/", {"start": "Nowhereville", "finish": "Dallas, TX"})
        self.assertEqual(r.status_code, 400)
        r = self.client.get("/api/route/", {"start": "51.5,-0.12", "finish": "Dallas, TX"})  # London
        self.assertEqual(r.status_code, 400)

    @override_settings(FUEL_ROUTE={**__import__("django.conf").conf.settings.FUEL_ROUTE, "NOMINATIM_FALLBACK": False})
    def test_map_page(self):
        with mock.patch("routing.services.osrm.fetch_route", side_effect=fake_route):
            r = self.client.get("/api/route/map/", {"start": "Dallas, TX", "finish": "Chicago, IL"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "leaflet")

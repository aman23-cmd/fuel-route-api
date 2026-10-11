from django.shortcuts import render
from django.urls import reverse
from django.utils.http import urlencode
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import TripRequestSerializer
from .services.trip import TripError, plan_trip


def _run(request, data):
    ser = TripRequestSerializer(data=data)
    ser.is_valid(raise_exception=True)
    return plan_trip(ser.validated_data["start"], ser.validated_data["finish"]), ser.validated_data


class RoutePlanView(APIView):
    """
    POST /api/route/  {"start": "Dallas, TX", "finish": "Chicago, IL"}
    GET  /api/route/?start=Dallas,TX&finish=Chicago,IL      (same thing, handy in a browser)
    """

    def _handle(self, request, data):
        try:
            result, valid = _run(request, data)
        except TripError as exc:
            return Response({"error": str(exc)}, status=exc.status)
        qs = urlencode({"start": valid["start"], "finish": valid["finish"]})
        result["map_url"] = request.build_absolute_uri(reverse("route-map") + "?" + qs)
        return Response(result)

    def post(self, request):
        return self._handle(request, request.data)

    def get(self, request):
        return self._handle(request, request.query_params)


def route_map(request):
    """HTML page with the route + fuel stops drawn on a Leaflet/OpenStreetMap map."""
    ser = TripRequestSerializer(data=request.GET)
    if not ser.is_valid():
        return render(request, "routing/map.html", {"error": "Provide ?start=...&finish=..."}, status=400)
    try:
        result = plan_trip(ser.validated_data["start"], ser.validated_data["finish"])
    except TripError as exc:
        return render(request, "routing/map.html", {"error": str(exc)}, status=exc.status)
    return render(request, "routing/map.html", {"result": result})

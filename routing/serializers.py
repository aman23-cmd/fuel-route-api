from rest_framework import serializers


class TripRequestSerializer(serializers.Serializer):
    start = serializers.CharField(max_length=200, help_text="'City, ST' or 'lat,lng'")
    finish = serializers.CharField(max_length=200, help_text="'City, ST' or 'lat,lng'")

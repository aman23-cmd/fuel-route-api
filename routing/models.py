from django.db import models


class FuelStation(models.Model):
    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, db_index=True)
    price = models.DecimalField(max_digits=6, decimal_places=4)  # $/gallon
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.price}"


class City(models.Model):
    """Offline gazetteer used to geocode stations and 'City, ST' inputs."""

    name = models.CharField(max_length=100)
    name_key = models.CharField(max_length=100)  # normalised for lookup
    state = models.CharField(max_length=2)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        indexes = [models.Index(fields=["name_key", "state"])]

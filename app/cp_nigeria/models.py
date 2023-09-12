from django.conf import settings
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from datetime import timedelta
from django.forms.models import model_to_dict
from django.utils.translation import gettext_lazy as _
from projects.models.base_models import Timeseries


class Project(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    date_start = models.DateTimeField()
    date_end = models.DateTimeField()

    def __str__(self):
        return self.name


class ConsumerType(models.Model):
    consumer_type = models.CharField(max_length=50)

    def __str__(self):
        return self.consumer_type


class DemandTimeseries(Timeseries):
    consumer_type = models.ForeignKey(ConsumerType, on_delete=models.CASCADE, null=True)


class ConsumerGroup(models.Model):
    consumer_type = models.ForeignKey(ConsumerType, on_delete=models.CASCADE, null=True)
    timeseries = models.ForeignKey(
        DemandTimeseries, on_delete=models.CASCADE, null=True
    )
    number_consumers = models.IntegerField()

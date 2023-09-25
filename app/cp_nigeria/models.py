from django.conf import settings
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from datetime import timedelta
from django.forms.models import model_to_dict
from django.utils.translation import gettext_lazy as _
from projects.models.base_models import Timeseries, Project
import uuid


class ConsumerType(models.Model):
    consumer_type = models.CharField(max_length=50)

    def __str__(self):
        return self.consumer_type


class DemandTimeseries(Timeseries):
    consumer_type = models.ForeignKey(ConsumerType, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return self.name


class ConsumerGroup(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, blank=True, null=True)
    group_id = models.IntegerField(blank=True, null=True)
    consumer_type = models.ForeignKey(ConsumerType, on_delete=models.CASCADE, null=True)
    timeseries = models.ForeignKey(
        DemandTimeseries, on_delete=models.CASCADE, null=True
    )
    number_consumers = models.IntegerField()
    expected_consumer_increase = models.FloatField(blank=True, null=True)
    expected_demand_increase = models.FloatField(blank=True, null=True)

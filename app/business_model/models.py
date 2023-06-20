import copy
import json
import jsonschema
import traceback
import logging
import numpy as np
import plotly.graph_objects as go
import pandas as pd


from django.utils.translation import ugettext_lazy as _
from django.shortcuts import get_object_or_404
from django.db import models
from projects.models import Scenario
from django.db.models import Value, Q, F, Case, When
from django.db.models.functions import Concat, Replace


class BusinessModel(models.Model):
    # def save(self, *args, **kwargs):
    #     super().save(*args, **kwargs)

    scenario = models.ForeignKey(
        Scenario, on_delete=models.CASCADE, null=True, blank=False
    )

    grid_connection = models.BooleanField(
        choices=((False, "no"), (True, "yes")), null=True, default=False, blank=False
    )
    regional_active_disco = models.BooleanField(
        choices=((False, "no"), (True, "yes")), null=True, default=False, blank=False
    )

    model_name = models.CharField(
        max_length=60,
        null=True,
        blank=False,
        choices=(
            ("Operator led", "Operator led"),
            ("Cooperative Model", "Cooperative Model"),
            (
                "Co-op / Project Developer hybrid model",
                "Co-op / Project Developer hybrid model",
            ),
        ),
    )

    @property
    def total_score(self):
        total_score = 0
        for answer in self.capacitiesanswer_set.all():
            total_score += answer.score * answer.criteria.weight
        return total_score
        # print(qs)

    # process_step = models.IntegerField(
    #     null=False, blank=False,
    # )
    # process_step_label = models.CharField(
    #     max_length=60, null=False, blank=False,
    # )
    #
    # # models.SmallIntegerField
    # question = models.TextField(
    #     null=True, blank=False,
    # )
    # answer = models.TextField(
    #     null=True, blank=False,
    # )


class Capacities(models.Model):
    description = models.TextField(null=False)
    weight = models.FloatField(null=False, verbose_name="Criteria weight")
    score_allowed_values = models.TextField(null=True)
    weighted_score = models.FloatField(null=True, verbose_name="Weighted Score")
    category = models.CharField(
        max_length=60,
        null=True,
        blank=False,
        choices=(("financial", "Financial"), ("institutional", "Intitutional")),
    )


class CapacitiesAnswer(models.Model):
    criteria = models.ForeignKey(
        Capacities, on_delete=models.CASCADE, null=True, blank=False
    )
    business_model = models.ForeignKey(
        BusinessModel, on_delete=models.CASCADE, null=True, blank=False
    )
    score = models.FloatField(null=True, verbose_name="Score")

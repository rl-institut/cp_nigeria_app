import copy
import json
import jsonschema
import traceback
import logging
import numpy as np
import plotly.graph_objects as go
import pandas as pd


from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from projects.models import Scenario
from django.db.models import Value, Q, F, Case, When
from django.db.models.functions import Concat, Replace
from business_model.helpers import B_MODELS, BM_QUESTIONS_CATEGORIES, BM_FATE_DEFAULT_VALUES


class BusinessModel(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, null=True, blank=True)

    grid_condition = models.CharField(
        max_length=14,
        choices=(("interconnected", "Interconnected"), ("isolated", "Isolated")),
        null=True,
        default=False,
        blank=True,
    )
    decision_tree = models.TextField(null=True, blank=True)

    model_name = models.CharField(
        max_length=60, null=True, blank=False, choices=[(k, k.replace("_", " ").capitalize()) for k in B_MODELS]
    )

    @property
    def total_score(self):
        total_score = 0
        user_answers = self.user_answers.all()
        if user_answers:
            for answer in user_answers:
                if answer.score is not None:
                    total_score += answer.score * answer.question.criteria_weight
                else:
                    total_score = None
                    break
        else:
            total_score = None

        return total_score

    @property
    def default_fate_values(self):
        return BM_FATE_DEFAULT_VALUES.get(self.model_name, {})


class BMQuestion(models.Model):
    question_for_user = models.TextField(null=False)
    criteria = models.TextField(null=False)
    criteria_weight = models.FloatField(null=False, verbose_name="Criteria weight")
    score_allowed_values = models.TextField(null=True)
    weighted_score = models.FloatField(null=True, verbose_name="Weighted Score")
    category = models.CharField(
        max_length=60, null=True, blank=False, choices=[(k, v) for k, v in BM_QUESTIONS_CATEGORIES.items()]
    )
    description = models.TextField(null=False)


class BMAnswer(models.Model):
    question = models.ForeignKey(BMQuestion, on_delete=models.CASCADE, null=True, blank=False)
    business_model = models.ForeignKey(
        BusinessModel, on_delete=models.CASCADE, null=True, blank=False, related_name="user_answers"
    )
    score = models.FloatField(null=True, verbose_name="Score")


class EquityData(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, null=True, blank=True)
    debt_start = models.IntegerField()
    fuel_price_increase = models.FloatField(
        verbose_name=_("Yearly increase of fuel price (%)"),
        default=0,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
    )
    grant_share = models.FloatField(
        verbose_name=_("Share of grant for assets (%)"), validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    debt_share = models.FloatField(
        verbose_name=_("Share of the external debt (%)"), validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    debt_interest_MG = models.FloatField(
        verbose_name=_("Interest rate for external loan: mini-grid (%)"),
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
    )
    debt_interest_SHS = models.FloatField(
        verbose_name=_("Interest rate for external loan: SHS (%)"),
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        null=True,
    )
    equity_interest_MG = models.FloatField(
        verbose_name=_("Interest rate for external equity: mini-grid (%)"),
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
    )
    equity_interest_SHS = models.FloatField(
        verbose_name=_("Interest rate for external equity: SHS (%)"),
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        null=True,
    )

    def compute_average_fuel_price(self, initial_fuel_price, project_duration):
        """
        Compute the average fuel price over the project lifetime
        project_duration: in years
        """
        annual_increase = np.array(
            [np.power(1 + (self.fuel_price_increase / 100.0), n) for n in range(project_duration)]
        )
        return initial_fuel_price * annual_increase.mean()

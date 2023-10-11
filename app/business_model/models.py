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
from django.db import models
from projects.models import Scenario
from django.db.models import Value, Q, F, Case, When
from django.db.models.functions import Concat, Replace
from dashboard.helpers import B_MODELS


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
        max_length=60, null=True, blank=False, choices=[(k, k.replace("_", " ")) for k in B_MODELS]
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


class BMQuestion(models.Model):
    question_for_user = models.TextField(null=False)
    criteria = models.TextField(null=False)
    criteria_weight = models.FloatField(null=False, verbose_name="Criteria weight")
    score_allowed_values = models.TextField(null=True)
    weighted_score = models.FloatField(null=True, verbose_name="Weighted Score")
    category = models.CharField(
        max_length=60,
        null=True,
        blank=False,
        choices=(
            ("dialogue", "Engagement, dialogue, and co-determination"),
            ("steering", "Steering capacities"),
            ("control", "Asserting control and credibility"),
            ("institutional", "Supporting Institutional structures"),
            ("economic", "Potential for economic co-benefits"),
            ("financial", "Financial capacities"),
        ),
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
    grant_share = models.FloatField()
    debt_share = models.FloatField()
    debt_interest_MG = models.FloatField()
    debt_interest_SHS = models.FloatField(null=True)
    equity_interest_MG = models.FloatField()
    equity_interest_SHS = models.FloatField(null=True)

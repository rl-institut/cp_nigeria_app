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
from business_model.helpers import B_MODELS, BM_QUESTIONS_CATEGORIES, BM_DEFAULT_ECONOMIC_VALUES, validate_percent


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
        max_length=60, null=True, blank=False, choices=[(k, B_MODELS[k]["Verbose"]) for k in B_MODELS]
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
    def default_economic_model_values(self):
        return BM_DEFAULT_ECONOMIC_VALUES.get(self.model_name, {})

    @property
    def is_operator_led(self):
        return "operator" in self.model_name


class BMQuestion(models.Model):
    question_for_user = models.TextField(null=False)
    sub_question_to = models.IntegerField(null=True)
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

    @property
    def default_economic_model_values(self):
        """Default economic model values

        If it is the answer to the financial question "With a rough estimation, how much financial
        resources (equity) could the community itself mobilize and provide for investing in
        a mini-grid installation (in NGN)?" then the equity default values are based on user answer
        """
        default_values = self.business_model.default_economic_model_values
        if self.question.id == 24:
            # See app/static/business_model_questions.csv file for the values
            if self.score == 0.3:
                default_values["equity_community_amount"] = 2.5
            elif self.score == 0.6:
                default_values["equity_community_amount"] = 7.5
            elif self.score == 0.8:
                default_values["equity_community_amount"] = 15
            elif self.score == 0.9:
                default_values["equity_community_amount"] = 35
            elif self.score == 1:
                default_values["equity_community_amount"] = 50

            if self.business_model.is_operator_led:
                default_values["equity_developer_amount"] = 2 * default_values["equity_community_amount"]
            else:
                default_values["equity_developer_amount"] = 5

        return default_values


class EquityData(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, null=True, blank=True)
    debt_start = models.IntegerField()
    fuel_price_increase = models.FloatField(
        help_text=_("Assumed yearly increase of fuel price (%)"),
        default=0,
        blank=True,
        validators=[validate_percent],
    )
    grant_share = models.FloatField(
        verbose_name=_("Grant share (%)"),
        help_text=_("Share of grant for assets provided by REA or other institutions"),
        default=0.6,
        validators=[validate_percent],
    )
    debt_share = models.FloatField(
        verbose_name=_("Share of the external debt (%)"),
        default=0,
        validators=[validate_percent],
    )
    debt_interest_MG = models.FloatField(
        verbose_name=_("Interest rate for external loan (%)"),
        help_text=_("Assumed interest rate for loan at project start"),
        default=0.11,
        validators=[validate_percent],
    )
    debt_interest_replacement = models.FloatField(
        verbose_name=_("Interest rate for replacement loan (%)"),
        help_text=_("Assumed interest rate for loan used for asset replacement"),
        default=0.11,
        validators=[validate_percent],
    )
    debt_interest_SHS = models.FloatField(
        verbose_name=_("Interest rate for external loan: SHS (%)"),
        validators=[validate_percent],
        null=True,
    )
    loan_maturity = models.IntegerField(
        help_text=_("Number of years to repay the loan"),
        validators=[MinValueValidator(0)],
        default=10,
    )
    grace_period = models.IntegerField(
        help_text=_("Number of years to the first repayment of principal"),
        validators=[MinValueValidator(0.0)],
        default=1,
    )
    equity_interest_MG = models.FloatField(
        verbose_name=_("Interest rate for external equity: mini-grid (%)"),
        default=0,
        validators=[validate_percent],
    )
    equity_interest_SHS = models.FloatField(
        verbose_name=_("Interest rate for external equity: SHS (%)"),
        validators=[validate_percent],
        null=True,
    )
    equity_community_amount = models.FloatField(
        verbose_name=_("Community equity (Million NGN)"),
        help_text=_("Amount of equity the community would be able to mobilize"),
        default=0,
    )
    equity_developer_amount = models.FloatField(
        verbose_name=_("Mini-grid company equity (Million NGN)"),
        help_text=_("Amount of equity the mini-grid company would be able to mobilize"),
        default=0,
    )
    estimated_tariff = models.FloatField(blank=True, null=True)

    def compute_average_fuel_price(self, initial_fuel_price, project_duration):
        """
        Compute the average fuel price over the project lifetime
        project_duration: in years
        """
        annual_increase = np.array([np.power(1 + self.fuel_price_increase, n) for n in range(project_duration)])
        return initial_fuel_price * annual_increase.mean()

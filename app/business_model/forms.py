from crispy_forms.helper import FormHelper
import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.forms import ModelForm
from .models import *
from .helpers import available_models
from projects.forms import OpenPlanForm, OpenPlanModelForm, set_parameter_info
from cp_nigeria.helpers import FINANCIAL_PARAMS


class ModelSuggestionForm(ModelForm):
    class Meta:
        model = BusinessModel
        fields = ["model_name"]

    def __init__(self, *args, **kwargs):
        score = kwargs.pop("score", None)
        grid_condition = kwargs.pop("grid_condition", None)

        if "instance" in kwargs:
            if grid_condition is None:
                grid_condition = kwargs["instance"].grid_condition
            if score is None:
                score = kwargs["instance"].total_score
        super().__init__(*args, **kwargs)
        choices = self.fields["model_name"].choices

        default_choices = [choices[0]] + [
            ("help_select", _("Assess whether your community is suitable for a community-led approach"))
        ]
        updated_choices = available_models(score, grid_condition)
        self.fields["model_name"].choices = default_choices + updated_choices
        if len(updated_choices) == 1:
            self.fields["model_name"].initial = updated_choices[0]


class BMQuestionForm(forms.Form):
    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("qs", None)
        super().__init__(*args, **kwargs)
        for criteria in qs.order_by("question"):
            alv = criteria.question.score_allowed_values
            opts = {"label": criteria.question.question_for_user}
            if criteria.score is not None:
                opts["initial"] = criteria.score

            if criteria.question.sub_question_to is not None:
                print(criteria.question.sub_question_to)
                opts["required"] = False  # Set the zero score value
            if alv is not None:
                try:
                    opts["choices"] = [["", "----------"]] + json.loads(alv)

                    self.fields[f"criteria_{criteria.question.id}"] = forms.ChoiceField(**opts)
                except json.decoder.JSONDecodeError:
                    self.fields[f"criteria_{criteria.question.id}"] = forms.FloatField(**opts)
            else:
                self.fields[f"criteria_{criteria.question.id}"] = forms.FloatField(**opts)

            # treat sub question differently:
            # - links to onchange of supra question
            # - hide the sub question if the supra question's answer is not "Yes"
            if criteria.question.sub_question_to is not None:
                disable_sub_question = True
                supra_question = BMQuestion.objects.get(id=criteria.question.sub_question_to)

                self.fields[f"criteria_{supra_question.id}"].widget.attrs.update(
                    {"onchange": f"triggerSubQuestion(new_value=this.value,subQuestionId={criteria.question.id})"}
                )

                supra_answer = qs.get(question=supra_question)
                if supra_answer.score is not None:
                    # assuming the subquestion is triggered only if answer to supraquestion is yes
                    if supra_answer.score == 1.0:
                        disable_sub_question = False
                    else:
                        self.fields[f"criteria_{criteria.question.id}"].initial = ""

                if disable_sub_question is True:
                    self.fields[f"criteria_{criteria.question.id}"].widget.attrs.update(
                        {"class": "sub_question disabled"}
                    )
                else:
                    self.fields[f"criteria_{criteria.question.id}"].widget.attrs.update({"class": "sub_question"})

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data:
            for record in cleaned_data:
                if cleaned_data[record] != "":
                    cleaned_data[record] = float(cleaned_data[record])
                else:
                    question = BMQuestion.objects.get(id=int(record.split("_")[1]))
                    if question.sub_question_to is None:
                        raise ValidationError("This field cannot be blank")
                    else:
                        # assuming the subquestion is triggered only if answer to supraquestion is yes
                        cleaned_data[record] = 0.0

        else:
            raise ValidationError("This form cannot be blank")
        return cleaned_data


class EquityDataForm(forms.ModelForm):
    percentage_fields = [
        "fuel_price_increase",
        "grant_share",
        "debt_share",
        "debt_interest_MG",
        "debt_interest_replacement",
        "debt_interest_SHS",
        "equity_interest_MG",
        "equity_interest_SHS",
    ]
    million_fields = ["equity_community_amount", "equity_developer_amount"]

    class Meta:
        model = EquityData
        exclude = [
            "scenario",
            "debt_start",
            "debt_share",
            "estimated_tariff",
            "equity_interest_MG",
            "fuel_price_increase",
        ]

    def __init__(self, *args, **kwargs):
        default = kwargs.pop("default", None)
        include_shs = kwargs.pop("include_shs", False)
        instance = kwargs.get("instance", None)
        initial = kwargs.get("initial", {})

        if instance is not None:
            for field in self.percentage_fields:
                initial_value = getattr(instance, field)
                if initial_value is not None:
                    initial[field] = initial_value * 100.0

            for field in self.million_fields:
                initial[field] = getattr(instance, field) / 1000000.0

            kwargs["initial"] = initial

        super().__init__(*args, **kwargs)
        if default is not None:
            for field, default_value in default.items():
                if field in self.fields:
                    self.fields[field].widget.attrs.update(
                        {"placeholder": f"your current model suggests {default_value}"}
                    )

        if not include_shs:
            for field in self.fields:
                if "SHS" in field:
                    self.fields[field].widget = forms.HiddenInput()
                    self.fields[field].required = False

    def clean(self):
        """Convert the percentage values into values ranging from 0 to 1 (for further calculations)"""
        super().clean()
        for field, value in self.cleaned_data.items():
            if value is not None:
                if field in self.million_fields:
                    self.cleaned_data[field] = value * 1000000.0
                elif field in self.percentage_fields:
                    self.cleaned_data[field] = value / 100.0

        return self.cleaned_data


class FinancialToolInputForm(forms.Form):
    def __init__(self, *args, **kwargs):
        category = kwargs.pop("category", None)

        super().__init__(*args, **kwargs)
        for param, value in FINANCIAL_PARAMS.items():
            if category is None:
                self.fields[param] = forms.FloatField()
            else:
                if isinstance(value, dict) and value["Category"] == category:
                    self.fields[param] = forms.FloatField()

        for fieldname, field in self.fields.items():
            set_parameter_info(fieldname, field, parameters=FINANCIAL_PARAMS)

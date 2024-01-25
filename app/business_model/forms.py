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

            if alv is not None:
                try:
                    opts["choices"] = [["", "----------"]] + json.loads(alv)

                    self.fields[f"criteria_{criteria.question.id}"] = forms.ChoiceField(**opts)
                except json.decoder.JSONDecodeError:
                    self.fields[f"criteria_{criteria.question.id}"] = forms.FloatField(**opts)
            else:
                self.fields[f"criteria_{criteria.question.id}"] = forms.FloatField(**opts)

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data:
            for record in cleaned_data:
                if cleaned_data[record] != "":
                    cleaned_data[record] = float(cleaned_data[record])
                else:
                    raise ValidationError("This field cannot be blank")
        else:
            raise ValidationError("This form cannot be blank")
        return cleaned_data


class EquityDataForm(forms.ModelForm):
    class Meta:
        model = EquityData
        exclude = ["scenario", "debt_start", "debt_share"]

    def __init__(self, *args, **kwargs):
        default = kwargs.pop("default", None)
        include_shs = kwargs.pop("include_shs", False)
        instance = kwargs.pop("instance", None)
        super().__init__(*args, **kwargs)
        if default is not None:
            for field, default_value in default.items():
                if field in self.fields:
                    self.fields[field].widget.attrs.update(
                        {"placeholder": f"your current model suggests {default_value}"}
                    )

        if instance is not None:
            for field in self.fields:
                initial_value = getattr(instance, field)
                if initial_value is not None:
                    if "amount" in field:
                        self.fields[field].initial = initial_value / 1000000
                    else:
                        self.fields[field].initial = initial_value * 100

        if not include_shs:
            for field in self.fields:
                if "SHS" in field:
                    self.fields[field].widget = forms.HiddenInput()
                    self.fields[field].required = False

    def clean(self):
        """Convert the percentage values into values ranging from 0 to 1 (for further calculations)"""
        super().clean()
        for record, value in self.cleaned_data.items():
            if value is not None:
                if "amount" in record:
                    self.cleaned_data[record] = value * 1000000
                else:
                    self.cleaned_data[record] = value / 100

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

from crispy_forms.helper import FormHelper
import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.forms import ModelForm
from .models import *
from .helpers import model_score_mapping, available_models


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
            self.fields["model_name"].initial = updated_choices[0][0]


class BMQuestionForm(forms.Form):
    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("qs", None)
        super().__init__(*args, **kwargs)
        for criteria in qs:
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

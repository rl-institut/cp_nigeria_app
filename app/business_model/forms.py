from crispy_forms.helper import FormHelper
import json

from django import forms
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
        super().__init__(*args, **kwargs)
        choices = self.fields["model_name"].choices
        print(B_MODELS)
        updated_choices = [choices[0]] + [
            ("help_select", _("Assess whether your community is suitable for a community-led approach"))
        ]
        self.fields["model_name"].choices = updated_choices + available_models(grid_condition)
        if score is not None:
            self.fields["model_name"].initial = model_score_mapping(score)


class BMQuestionForm(forms.Form):
    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("qs", None)
        super().__init__(*args, **kwargs)
        for criteria in qs:
            alv = criteria.question.score_allowed_values
            opts = {"required": True, "label": criteria.question.question_for_user}

            if criteria.score is not None:
                opts["initial"] = criteria.score

            if alv is not None:
                # import pdb;pdb.set_trace()
                try:
                    opts["choices"] = json.loads(alv)

                    self.fields[f"criteria_{criteria.question.id}"] = forms.ChoiceField(**opts)
                except json.decoder.JSONDecodeError:
                    self.fields[f"criteria_{criteria.question.id}"] = forms.FloatField(**opts)
            else:
                self.fields[f"criteria_{criteria.question.id}"] = forms.FloatField(**opts)

    def clean(self):
        cleaned_data = super().clean()

        for record in cleaned_data:
            cleaned_data[record] = float(cleaned_data[record])

        return cleaned_data

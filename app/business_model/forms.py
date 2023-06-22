from crispy_forms.helper import FormHelper
import json

from django import forms
from django.utils.translation import ugettext_lazy as _
from django.forms import ModelForm
from .models import *
from .helpers import model_score_mapping


class GridQuestionForm(ModelForm):
    class Meta:
        model = BusinessModel
        fields = ["grid_connection"]


class EdiscoQuestionForm(ModelForm):
    class Meta:
        model = BusinessModel
        fields = ["regional_active_disco"]


class RegulationQuestionForm(forms.Form):
    regulations = forms.ChoiceField(choices=((True, True),))


class ModelSuggestionForm(ModelForm):
    class Meta:
        model = BusinessModel
        fields = ["model_name"]

    def __init__(self, *args, **kwargs):
        score = kwargs.pop("score", None)
        super().__init__(*args, **kwargs)

        if score is not None:
            self.fields["model_name"].initial = model_score_mapping(score)


class CapacitiesForm(forms.Form):
    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("qs", None)
        super().__init__(*args, **kwargs)
        for criteria in qs:
            alv = criteria.criteria.score_allowed_values
            opts = {"required": True, "label": criteria.criteria.description}

            if criteria.score is not None:
                opts["initial"] = criteria.score

            if alv is not None:
                try:
                    opts["choices"] = json.loads(alv)

                    self.fields[f"criteria_{criteria.criteria.id}"] = forms.ChoiceField(
                        **opts
                    )
                except json.decoder.JSONDecodeError:
                    self.fields[f"criteria_{criteria.criteria.id}"] = forms.FloatField(
                        **opts
                    )
            else:
                self.fields[f"criteria_{criteria.criteria.id}"] = forms.FloatField(
                    **opts
                )

    def clean(self):
        cleaned_data = super().clean()

        for record in cleaned_data:
            cleaned_data[record] = float(cleaned_data[record])

        return cleaned_data

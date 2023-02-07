from django import forms
from django.utils.translation import ugettext_lazy as _
from projects.forms import OpenPlanModelForm, ProjectCreateForm
from .models import Project
from projects.forms import StorageForm, AssetCreateForm

CURVES = (("Evening Peak", "Evening Peak"),
          ("Midday Peak", "Midday Peak"))

TIERS = (("Tier 1", "Tier 1"),
         ("Tier 2", "Tier 2"),
         ("Tier 3", "Tier 3"))


class ProjectForm(OpenPlanModelForm):
    class Meta:
        model = Project
        fields = "__all__"


class CPNLocationForm(ProjectCreateForm):
    weather = forms.FileField(
        label=_("Upload weather data"),
        required=False
    )


class CPNLoadProfileForm(ProjectCreateForm):
    households = forms.IntegerField(
        label=_("Number of households"),
    )
    tier = forms.ChoiceField(
        label=_("Demand Tier"),
        choices=TIERS,
        widget=forms.Select(
            attrs={
                "data-bs-toggle": "tooltip",
                "title": _("Electricity demand tier"),
            }
        ),
    )
    curve = forms.ChoiceField(
        label=_("Load curve"),
        choices=CURVES,
        widget=forms.Select(
            attrs={
                "data-bs-toggle": "tooltip",
                "title": _("Load curve"),
            }
        ),
    )


class PVForm(AssetCreateForm):
    def __init__(self, *args, **kwargs):

        super().__init__(*args, asset_type="pv_plant", **kwargs)
        # which fields exists in the form are decided upon AssetType saved in the db
        self.prefix = self.asset_type_name

        # for field in self.fields:
        #     self.fields[field].required = False

        self.fields["input_timeseries"].required = False

        for field, value in zip(
            ("name", "renewable_asset"), (self.asset_type_name, True)
        ):
            self.fields[field].widget = forms.HiddenInput()
            self.fields[field].initial = value


class DieselForm(AssetCreateForm):
    def __init__(self, *args, **kwargs):

        super().__init__(*args, asset_type="diesel_generator", **kwargs)
        # which fields exists in the form are decided upon AssetType saved in the db
        self.prefix = self.asset_type_name

        # for field in self.fields:
        #     self.fields[field].required = False

        for field, value in zip(("name",), (self.asset_type_name,)):
            self.fields[field].widget = forms.HiddenInput()
            self.fields[field].initial = value


class BessForm(StorageForm):
    def __init__(self, *args, **kwargs):

        super().__init__(*args, asset_type="bess", **kwargs)
        # which fields exists in the form are decided upon AssetType saved in the db
        self.prefix = self.asset_type_name

        # for field in self.fields:
        #     self.fields[field].required = False

        for field, value in zip(("name",), (self.asset_type_name,)):
            self.fields[field].widget = forms.HiddenInput()
            self.fields[field].initial = value


class DummyForm(forms.Form):
    some_input = forms.ChoiceField(
        label=_("Some INput"),
        choices=(("a","a"), ("b", "b")),
    )


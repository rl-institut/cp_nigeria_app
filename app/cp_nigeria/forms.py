from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from projects.forms import OpenPlanForm, OpenPlanModelForm, ProjectCreateForm

from projects.forms import StorageForm, AssetCreateForm, UploadTimeseriesForm
from projects.models import Project, EconomicData, Scenario
from .models import *
from projects.helpers import PARAMETERS


CURVES = (("Evening Peak", "Evening Peak"), ("Midday Peak", "Midday Peak"))


class ProjectForm(OpenPlanModelForm):

    start_date = forms.DateField(
        label=_("Simulation start"),
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "class": "TestDateClass",
                "placeholder": "Select a start date",
                "type": "date",
            },
        ),
    )
    duration = forms.IntegerField(label=_("Project lifetime"))

    class Meta:
        model = Project
        exclude = ("country", "user", "viewers", "economic_data")

    def save(self, *args, **kwargs):
        user = kwargs.pop("user")
        kwargs["commit"] = False
        pr = super().save(*args, **kwargs)

        # The project does not exist yet so we created it as well as a scenario
        if pr.id is None:
            economic_data = EconomicData.objects.create(
                duration=self.cleaned_data["duration"],
                currency="NGN",
                discount=0,
                tax=0,
            )
            pr.economic_data = economic_data
            pr.user = user
            pr.country = "NIGERIA"
            pr.save()
            Scenario.objects.create(
                name=f'{self.cleaned_data["name"]}_scenario',
                start_date=self.cleaned_data["start_date"],
                time_step=60,
                evaluated_period=365,  # TODO this depends on the year
                project=pr,
            )
        # The project does exist and we update simply its values
        else:
            economic_data = EconomicData.objects.filter(id=pr.economic_data.id)
            economic_data.update(duration=self.cleaned_data["duration"])

            scenario = Scenario.objects.filter(project=pr)
            scenario.update(start_date=self.cleaned_data["start_date"])
            pr.save()

        return pr


class EconomicDataForm(OpenPlanModelForm):

    capex_fix = forms.FloatField(
        label=_("Fix project costs"), validators=[MinValueValidator(0.0)]
    )

    class Meta:
        model = EconomicData
        exclude = ("tax",)

    def save(self, *args, **kwargs):
        ed = super().save(*args, **kwargs)
        scenario = Scenario.objects.filter(project__economic_data=ed)
        scenario.update(capex_fix=self.cleaned_data["capex_fix"])


class CPNLocationForm(ProjectCreateForm):
    weather = forms.FileField(label=_("Upload weather data"), required=False)


class DemandProfileForm(OpenPlanForm):
    consumer_type = forms.ModelChoiceField(queryset=ConsumerType.objects.all())
    facility_type = forms.ModelChoiceField(queryset=ConsumerType.objects.all())
    curve = forms.ChoiceField(
        label=_("Load curve"),
        choices=CURVES,
        widget=forms.Select(
            attrs={"data-bs-toggle": "tooltip", "title": _("Load curve")}
        ),
    )
    households = forms.IntegerField(label=_("Number of households"))


class UploadDemandForm(UploadTimeseriesForm):
    class Meta:
        model = DemandTimeseries
        exclude = ["id", "user", "scenario", "ts_type"]
        widgets = {
            "start_date": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "class": "TestDateClass",
                    "placeholder": "Select a start date",
                    "type": "date",
                },
            )
        }


class PVForm(AssetCreateForm):
    def __init__(self, *args, **kwargs):

        super().__init__(*args, asset_type="pv_plant", **kwargs)
        # which fields exists in the form are decided upon AssetType saved in the db
        self.prefix = self.asset_type_name

        # for field in self.fields:
        #     self.fields[field].required = False

        self.fields["input_timeseries"].required = False
        self.fields["optimize_cap"].initial = True

        for field, value in zip(
            ("name", "renewable_asset", "capex_fix", "opex_var"), (self.asset_type_name, True, 0, 0)
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

        for field, value in zip(("name", "capex_fix"), (self.asset_type_name, 0)):
            self.fields[field].widget = forms.HiddenInput()
            self.fields[field].initial = value

        # TODO right now only added as a form field for demonstration purposes but no changes to the db
        self.fields["fuel_price"] = forms.DecimalField(initial=0.65, decimal_places=2)
        self.fields["fuel_price"].label = "Fuel price (€/l)"


class BessForm(StorageForm):
    def __init__(self, *args, **kwargs):

        super().__init__(*args, asset_type="bess", **kwargs)
        # which fields exists in the form are decided upon AssetType saved in the db
        self.prefix = self.asset_type_name

        # for field in self.fields:
        #     self.fields[field].required = False
        self.fields["optimize_cap"].initial = True

        for field, value in zip(("name", "capex_fix", "opex_var"), (self.asset_type_name, 0, 0)):
            self.fields[field].widget = forms.HiddenInput()
            self.fields[field].initial = value

        # TODO this is a patchy fix to get the tooltips even with the changed labels (copied code from forms), fix properly later
        for field, value in zip(("crate", "soc_min", "efficiency"), ("C-Rate", "Depth of Discharge (DOD)", "Round-trip efficiency")):
            RTD_url = "https://open-plan-documentation.readthedocs.io/en/latest/model/input_parameters.html#"
            #import pdb; pdb.set_trace()
            if field in PARAMETERS:
                param_ref = PARAMETERS[field]["ref"]
                help_text = PARAMETERS[field][":Definition_Short:"]
            elif "c-rate" in PARAMETERS:
                param_ref = PARAMETERS["c-rate"]["ref"]
                help_text = PARAMETERS["c-rate"][":Definition_Short:"]
            else:
                param_ref = ""
            if field != "name":
                question_icon = f'<a href="{RTD_url}{param_ref}"><span class="icon icon-question" data-bs-toggle="tooltip" title="{help_text}"></span></a>'
            else:
                question_icon = ""
            self.fields[field].label = value + question_icon


class DummyForm(forms.Form):
    some_input = forms.ChoiceField(
        label=_("Some INput"), choices=(("a", "a"), ("b", "b"))
    )


class ConsumerGroupForm(OpenPlanModelForm):
    class Meta:
        model = ConsumerGroup
        fields = "__all__"

    def __init__(self, *args, **kwargs):

        advanced_opt = kwargs.pop("advanced_view", False)
        super().__init__(*args, **kwargs)
        self.fields["timeseries"].queryset = DemandTimeseries.objects.none()

        if advanced_opt is False:
            for field in ["expected_consumer_increase", "expected_demand_increase"]:
                self.fields[field].widget = forms.HiddenInput()

        # Prevent automatic labels from being generated (to avoid issues with table display)
        for field_name, field in self.fields.items():
            field.label = ""

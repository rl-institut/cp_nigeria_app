from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.forms.models import modelformset_factory
from projects.forms import OpenPlanForm, OpenPlanModelForm, ProjectCreateForm

from projects.forms import StorageForm, AssetCreateForm, UploadTimeseriesForm
from projects.models import Project, EconomicData, Scenario
from projects.constants import CURRENCY_SYMBOLS, ENERGY_DENSITY_DIESEL
from .models import *
from projects.helpers import PARAMETERS

CURVES = (("Evening Peak", "Evening Peak"), ("Midday Peak", "Midday Peak"))


class ProjectForm(OpenPlanModelForm):
    community = forms.ModelChoiceField(
        queryset=Community.objects.all(), required=False, label="Pre-select a community (optional)"
    )
    start_date = forms.DateField(
        label=_("Simulation start"),
        initial=f"{timezone.now().year}-01-01",
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = False

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
    capex_fix = forms.FloatField(label=_("Fix project costs"), validators=[MinValueValidator(0.0)])

    class Meta:
        model = EconomicData
        exclude = ("tax", "currency", "duration")

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
        widget=forms.Select(attrs={"data-bs-toggle": "tooltip", "title": _("Load curve")}),
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
            ),
        }


class PVForm(AssetCreateForm):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, asset_type="pv_plant", **kwargs)
        # which fields exists in the form are decided upon AssetType saved in the db
        self.prefix = self.asset_type_name

        asset = kwargs.get("instance", None)
        if asset is None:
            default_values = {"lifetime": 8, "capex_var": 368606.52, "opex_fix": 7727.6}
            for field, initial_value in default_values.items():
                self.initial[field] = initial_value

        self.initial["optimize_cap"] = True
        self.fields["input_timeseries"].widget = forms.HiddenInput()
        self.fields["input_timeseries"].required = False

        self.fields["capex_var"].label = self.fields["capex_var"].label.replace(
            "(CAPEX)", "(CAPEX). It should include inverter costs."
        )

        for field, value in zip(
            ("name", "renewable_asset", "capex_fix", "opex_var"), (self.asset_type_name, True, 0, 0)
        ):
            self.fields[field].widget = forms.HiddenInput()
            self.initial[field] = value


class DieselForm(AssetCreateForm):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, asset_type="diesel_generator", **kwargs)
        # which fields exists in the form are decided upon AssetType saved in the db
        self.prefix = self.asset_type_name

        self.initial["optimize_cap"] = True

        asset = kwargs.get("instance", None)
        if asset is not None:
            self.initial["opex_var"] = round(asset.opex_var * ENERGY_DENSITY_DIESEL, 3)
        else:
            default_values = {
                "lifetime": 8,
                "capex_var": 309104,
                "opex_fix": 19319,
                "opex_var_extra": 23.18,
                "efficiency": 0.25,
            }
            for field, initial_value in default_values.items():
                self.initial[field] = initial_value
        visible_fields = ["opex_var"]
        for field in self.fields:
            if field not in visible_fields:
                pass  # self.fields[field].widget = forms.HiddenInput()

        for field, value in zip(("name", "capex_fix"), (self.asset_type_name, 0)):
            self.fields[field].widget = forms.HiddenInput()
            self.initial[field] = value

        qs = Project.objects.filter(id=kwargs.get("proj_id", -1))
        if qs.exists():
            currency = qs.values_list("economic_data__currency", flat=True).get()
            currency = CURRENCY_SYMBOLS[currency]
        else:
            currency = "currency"

        help_text = "Average fuel price."
        question_icon = f'<span class="icon icon-question" data-bs-toggle="tooltip" title="{help_text}"></span>'
        self.fields["opex_var"].label = f"Fuel price ({currency}/l)" + question_icon
        help_text = "Costs such as lubricant for motor."
        question_icon = f'<span class="icon icon-question" data-bs-toggle="tooltip" title="{help_text}"></span>'
        self.fields["opex_var_extra"].label = f"Operational variable costs ({currency}/kWh)" + question_icon

        self.fields["efficiency"].label = self.fields["efficiency"].label.replace("Efficiency", "Average efficiency")

    def clean_opex_var(self):
        return self.cleaned_data["opex_var"] / ENERGY_DENSITY_DIESEL


class BessForm(StorageForm):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # which fields exists in the form are decided upon AssetType saved in the db
        self.prefix = self.asset_type_name

        asset = kwargs.get("instance", None)
        if asset is not None:
            self.initial["soc_min"] = round(1 - asset.soc_min, 3)
        else:
            default_values = {
                "lifetime": 8,
                "capex_var": 255783.56,
                "opex_fix": 7727.6,
                "crate": 1,
                "soc_min": 0.8,
                "soc_max": 1,
                "efficiency": 0.9,
            }
            for field, initial_value in default_values.items():
                self.initial[field] = initial_value

        self.initial["optimize_cap"] = True
        for field, value in zip(("name", "capex_fix", "opex_var"), (self.asset_type_name, 0, 0)):
            self.fields[field].widget = forms.HiddenInput()
            self.initial[field] = value
        self.fields["capex_var"].label = self.fields["capex_var"].label.replace(
            "(CAPEX)", "(CAPEX). It should include inverter costs."
        )

        # TODO this is a patchy fix to get the tooltips even with the changed labels (copied code from forms), fix properly later
        for field, value in zip(
            ("crate", "soc_min", "efficiency"), ("C-Rate", "Depth of Discharge (DOD)", "Round-trip efficiency")
        ):
            RTD_url = "https://open-plan-documentation.readthedocs.io/en/latest/model/input_parameters.html#"
            if field in PARAMETERS:
                param_ref = PARAMETERS[field]["ref"]
                help_text = PARAMETERS[field][":Definition_Short:"]
            elif "c-rate" in PARAMETERS:
                param_ref = PARAMETERS["c-rate"]["ref"]
                help_text = PARAMETERS["c-rate"][":Definition_Short:"]
            else:
                param_ref = ""
            if field == "soc_min":
                help_text = "The fraction of the battery's capacity that is discharged from the battery with regard to its fully charged state."  # source: Wikipedia
            if field != "name":
                question_icon = f'<a href="{RTD_url}{param_ref}"><span class="icon icon-question" data-bs-toggle="tooltip" title="{help_text}"></span></a>'
            else:
                question_icon = ""
            self.fields[field].label = value + question_icon

    def clean_soc_min(self):
        return round(1 - self.cleaned_data["soc_min"], 3)


class DummyForm(forms.Form):
    some_input = forms.ChoiceField(label=_("Some INput"), choices=(("a", "a"), ("b", "b")))


class ConsumerGroupForm(OpenPlanModelForm):
    class Meta:
        model = ConsumerGroup
        exclude = ["project", "community"]

    def __init__(self, *args, **kwargs):
        advanced_opt = kwargs.pop("advanced_view", False)
        instance = kwargs.pop("instance", None)
        allow_edition = kwargs.pop("allow_edition", True)
        super().__init__(*args, **kwargs)

        if allow_edition is False:
            for field in self.fields:
                self.fields[field].disabled = True

        if instance is None:
            self.fields["timeseries"].queryset = DemandTimeseries.objects.none()
        else:
            consumer_type_id = instance.consumer_type_id
            self.fields["timeseries"].queryset = DemandTimeseries.objects.filter(consumer_type_id=consumer_type_id)

        if advanced_opt is False:
            for field in ["expected_consumer_increase", "expected_demand_increase"]:
                self.fields[field].widget = forms.HiddenInput()

        # Prevent automatic labels from being generated (to avoid issues with table display)
        for _field_name, field in self.fields.items():
            field.label = ""


ConsumerGroupFormSet = modelformset_factory(ConsumerGroup, form=ConsumerGroupForm, extra=1, can_delete=True)

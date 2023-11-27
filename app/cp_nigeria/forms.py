from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.forms.models import modelformset_factory
from django.core.exceptions import ValidationError

from projects.forms import OpenPlanForm, OpenPlanModelForm, ProjectCreateForm

from projects.forms import StorageForm, AssetCreateForm, UploadTimeseriesForm
from projects.models import Project, EconomicData, Scenario
from projects.constants import CURRENCY_SYMBOLS, ENERGY_DENSITY_DIESEL
from .models import *
from projects.helpers import PARAMETERS
from cp_nigeria.helpers import HOUSEHOLD_TIERS

CURVES = (("Evening Peak", "Evening Peak"), ("Midday Peak", "Midday Peak"))


def validate_not_zero(value):
    if value == 0:
        raise ValidationError(_("This field cannot be equal to 0"))


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
    duration = forms.IntegerField(label=_("Project lifetime"), initial=25)

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["discount"].validators.append(validate_not_zero)
        self.initial["discount"] = 0.12

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


class MainGridForm(AssetCreateForm):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, asset_type="dso", **kwargs)
        # which fields exists in the form are decided upon AssetType saved in the db
        self.prefix = self.asset_type_name

        self.fields["feedin_tariff"] = forms.FloatField()
        asset = kwargs.get("instance", None)
        if asset is None:
            default_values = {"name": self.asset_type_name, "energy_price": "23", "feedin_tariff": 0}
            for field, initial_value in default_values.items():
                self.initial[field] = initial_value

        show_fields = ["energy_price", "renewable_share"]

        for field in self.fields:
            if field not in show_fields:
                self.fields[field].widget = forms.HiddenInput()


class PVForm(AssetCreateForm):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, asset_type="pv_plant", **kwargs)
        # which fields exists in the form are decided upon AssetType saved in the db
        self.prefix = self.asset_type_name

        asset = kwargs.get("instance", None)
        if asset is None:
            default_values = {"lifetime": 25, "capex_var": 369198, "opex_fix": 7740}
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
            self.initial["opex_var_extra"] = round(asset.opex_var_extra * ENERGY_DENSITY_DIESEL, 3)
            if self.initial["soc_min"] is None:
                self.initial["soc_min"] = 0.0
            if self.initial["soc_max"] is None:
                self.initial["soc_max"] = 1.0
        else:
            default_values = {
                "lifetime": 8,
                "capex_var": 309600,
                "opex_fix": 19350,
                "opex_var": 23.22,
                "opex_var_extra": 626.7,  # TODO connect to https://www.globalpetrolprices.com/Nigeria/diesel_prices/ and use this as value once per day
                # ie solution with entry in the DB because the date needs to be linked to the price to be updated if the date is different
                "efficiency": 0.25,
                "soc_min": 0.0,
                "soc_max": 1.0,
            }
            for field, initial_value in default_values.items():
                self.initial[field] = initial_value

        for field, value in zip(("name", "capex_fix", "maximum_capacity"), (self.asset_type_name, 0, 0.0)):
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
        self.fields["opex_var_extra"].label = f"Fuel price ({currency}/l)" + question_icon
        help_text = "Costs such as lubricant for motor."
        question_icon = f'<span class="icon icon-question" data-bs-toggle="tooltip" title="{help_text}"></span>'
        self.fields["opex_var"].label = f"Operational variable costs ({currency}/kWh)" + question_icon
        self.fields["soc_min"].label = "Minimal load"
        self.fields["soc_max"].label = "Maximal load"

        self.fields["efficiency"].label = self.fields["efficiency"].label.replace("Efficiency", "Average efficiency")

    def clean_opex_var_extra(self):
        return self.cleaned_data["opex_var_extra"] / ENERGY_DENSITY_DIESEL


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
                "capex_var": 256194,
                "opex_fix": 7740,
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
                help_text = ""
            if field == "soc_min":
                help_text = "The fraction of the battery's capacity that is discharged from the battery with regard to its fully charged state."  # source: Wikipedia
            if field != "name":
                question_icon = f'<a href="{RTD_url}{param_ref}"><span class="icon icon-question" data-bs-toggle="tooltip" title="{help_text}"></span></a>'
            else:
                question_icon = ""
            self.fields[field].label = value + question_icon

    def clean_soc_min(self):
        return round(1 - self.cleaned_data["soc_min"], 3)


class SHSTiersForm(forms.Form):
    help_text = "All households assigned to the selected tier or below will be served by solar home systems."
    question_icon = f'<span class="icon icon-question" data-bs-toggle="tooltip" title="{help_text}"></span>'

    shs_threshold = forms.ChoiceField(
        widget=forms.Select(attrs={"data-bs-toggle": "tooltip"}),
        required=False,
        choices=HOUSEHOLD_TIERS,
        label="Select a threshold for SHS users" + question_icon
    )


class ConsumerGroupForm(OpenPlanModelForm):
    class Meta:
        model = ConsumerGroup
        exclude = ["project", "community"]

    def __init__(self, *args, **kwargs):
        advanced_opt = kwargs.pop("advanced_view", False)
        instance = kwargs.pop("instance", None)
        allow_edition = kwargs.pop("allow_edition", True)
        super().__init__(*args, **kwargs)

        self.fields["timeseries"].queryset = DemandTimeseries.objects.none()

        if advanced_opt is False:
            for field in ["expected_consumer_increase", "expected_demand_increase"]:
                self.fields[field].widget = forms.HiddenInput()

        # Prevent automatic labels from being generated (to avoid issues with table display)
        for _field_name, field in self.fields.items():
            field.label = ""


ConsumerGroupFormSet = modelformset_factory(ConsumerGroup, form=ConsumerGroupForm, extra=1, can_delete=True)

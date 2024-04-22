from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.forms.models import modelformset_factory
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404

from projects.forms import OpenPlanForm, OpenPlanModelForm, ProjectCreateForm

from projects.forms import StorageForm, AssetCreateForm, UploadTimeseriesForm
from projects.models import Project, EconomicData, Scenario
from business_model.models import EquityData
from business_model.helpers import validate_percent
from projects.constants import CURRENCY_SYMBOLS, ENERGY_DENSITY_DIESEL
from .models import *
from projects.helpers import PARAMETERS
from projects.requests import request_exchange_rate
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
            scenario = Scenario.objects.filter(project=pr)
            scenario.update(start_date=self.cleaned_data["start_date"])
            pr.save()

        return pr


class EconomicProjectForm(OpenPlanModelForm):
    class Meta:
        model = EconomicData
        fields = ["duration", "currency", "exchange_rate"]

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance", None)
        super().__init__(*args, **kwargs)
        self.fields["currency"].initial = "NGN"

        if instance is None:
            self.fields["exchange_rate"].initial = request_exchange_rate("NGN")


class EconomicDataForm(OpenPlanModelForm):
    capex_fix = forms.FloatField(
        label=_("Fix project costs"),
        help_text=_("Expected additional costs, e.g. for project planning, land purchase etc."),
        validators=[MinValueValidator(0.0)],
    )

    class Meta:
        model = EconomicData
        exclude = ("currency", "duration", "exchange_rate")

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance", None)
        initial = kwargs.get("initial", {})
        if instance is not None:
            for field in ["discount", "tax"]:
                initial_value = getattr(instance, field)
                if initial_value is not None:
                    initial[field] = initial_value * 100

        kwargs["initial"] = initial

        super().__init__(*args, **kwargs)
        self.fields["discount"].validators.append(validate_not_zero)
        self.initial["discount"] = 12.0
        self.initial["tax"] = 7.5

    # def save(self, *args, **kwargs):
    #     ed = super().save(*args, **kwargs)
    #     scenario = Scenario.objects.filter(project__economic_data=ed)
    #     scenario.update(capex_fix=self.cleaned_data["capex_fix"])

    def clean(self):
        """Convert the percentage values into values ranging from 0 to 1 (for further calculations)"""
        super().clean()
        for field, value in self.cleaned_data.items():
            if field in ["discount", "tax"]:
                self.cleaned_data[field] = value / 100

        return self.cleaned_data


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
        proj_id = kwargs.get("proj_id", None)
        exchange_rate = get_object_or_404(Project, id=proj_id).economic_data.exchange_rate
        if asset is None:
            default_values = {
                "name": self.asset_type_name,
                "energy_price": str(round((0.03 * exchange_rate), 2)),
                "feedin_tariff": 0,
            }
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
        # add fuel price increase field to form and set form field immediately after fuel price field
        field_order = [field for field in self.fields]
        field_order.insert((field_order.index("opex_var_extra") + 1), "fuel_price_increase")
        ed = EquityData.objects.filter(scenario__project_id=kwargs.get("proj_id"))
        initial_increase = (ed.first().fuel_price_increase * 100) if ed.exists() else 0
        self.fields["fuel_price_increase"] = forms.FloatField(
            help_text=_("Estimated annual fuel price increase (%)"),
            initial=initial_increase,
            validators=[MinValueValidator(0.0)],
        )
        self.order_fields(field_order=field_order)
        # which fields exists in the form are decided upon AssetType saved in the db
        self.prefix = self.asset_type_name
        self.initial["optimize_cap"] = True

        asset = kwargs.get("instance", None)
        if asset is not None:
            if self.initial["soc_min"] is None:
                self.initial["soc_min"] = 0.0
            if self.initial["soc_max"] is None:
                self.initial["soc_max"] = 1.0

        for field, value in zip(("name", "capex_fix", "maximum_capacity"), (self.asset_type_name, 0, 0.0)):
            self.fields[field].widget = forms.HiddenInput()
            self.initial[field] = value

        self.proj_id = kwargs.get("proj_id", -1)
        qs = Project.objects.filter(id=self.proj_id)
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

    def save(self, *args, **kwargs):
        asset = super().save(*args, **kwargs)
        qs = Scenario.objects.filter(project__id=self.proj_id)
        if qs.exists():
            scenario = qs.first()
        else:
            scenario = None

        equity_data, created = EquityData.objects.get_or_create(
            scenario=scenario,
            defaults={"debt_start": scenario.start_date.year if scenario is not None else None, "scenario": scenario},
        )
        equity_data.fuel_price_increase = self.cleaned_data["fuel_price_increase"] / 100
        equity_data.save()

        return asset


class BessForm(StorageForm):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # which fields exists in the form are decided upon AssetType saved in the db
        self.prefix = self.asset_type_name

        asset = kwargs.get("instance", None)

        if asset is not None:
            self.initial["soc_min"] = round(1 - asset.soc_min, 3)

        self.initial["optimize_cap"] = True
        for field, value in zip(("name", "capex_fix", "opex_var"), (self.asset_type_name, 0, 1e-9)):
            if field != "opex_var":
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


class DemandOptionsForm(forms.Form):
    help_text_shs = "All households assigned to the selected tier or below will be served by solar home systems."
    help_text_demand = "Select the percentage of demand you want to fulfill, the rest might be fulfilled if the optimization allows it. For example if you select 80%, then 80% of the demand of your community will be fulfilled for sure and the remaining 20% is optional, thus the total fulfilled demand after optimization will lie between 80% and 100%. Currently this only apply on the demand of the households."
    question_icon = '<span class="icon icon-question" data-bs-toggle="tooltip" title="{}"></span>'

    shs_threshold = forms.ChoiceField(
        widget=forms.Select(attrs={"data-bs-toggle": "tooltip"}),
        required=False,
        choices=HOUSEHOLD_TIERS,
        label="Select a threshold for SHS users" + question_icon.format(help_text_shs),
    )
    demand_coverage_factor = forms.FloatField(
        required=False,
        label="Minimal percentage of the demand to fulfill" + question_icon.format(help_text_demand),
    )

    def __init__(self, *args, **kwargs):
        super(DemandOptionsForm, self).__init__(*args, **kwargs)
        self.fields["demand_coverage_factor"].widget.attrs["min"] = 0
        self.fields["demand_coverage_factor"].widget.attrs["max"] = 100

    def clean_demand_coverage_factor(self):
        """method which gets called upon form validation"""
        demand_coverage_factor = self.cleaned_data["demand_coverage_factor"] / 100.0
        validate_percent(demand_coverage_factor)
        return demand_coverage_factor


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

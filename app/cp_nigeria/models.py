from django.conf import settings
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from datetime import timedelta
from django.forms.models import model_to_dict
from django.utils.translation import gettext_lazy as _
from projects.models import Timeseries, Project, Scenario, Asset, Bus, UseCase
from projects.scenario_topology_helpers import assign_assets, assign_busses


class ConsumerTypeManager(models.Manager):
    def get_by_natural_key(self, consumer_type):
        return self.get(consumer_type=consumer_type)


class ConsumerType(models.Model):
    consumer_type = models.CharField(max_length=50)
    objects = ConsumerTypeManager()

    def __str__(self):
        return self.consumer_type

    def natural_key(self):
        return (self.consumer_type,)


class DemandTimeseries(Timeseries):
    consumer_type = models.ForeignKey(ConsumerType, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return self.name


class CommunityManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class Community(models.Model):
    name = models.CharField(max_length=50)
    pv_timeseries = models.ForeignKey(Timeseries, on_delete=models.SET_NULL, null=True)
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)
    objects = CommunityManager()

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.name,)


class ConsumerGroup(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, blank=True, null=True)
    consumer_type = models.ForeignKey(ConsumerType, on_delete=models.CASCADE, null=True)
    timeseries = models.ForeignKey(DemandTimeseries, on_delete=models.SET_NULL, null=True)
    number_consumers = models.IntegerField()
    expected_consumer_increase = models.FloatField(blank=True, null=True)
    expected_demand_increase = models.FloatField(blank=True, null=True)
    community = models.ForeignKey(Community, on_delete=models.CASCADE, null=True, blank=True)


class Options(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, blank=True, null=True)
    user_case = models.TextField(default="")
    main_grid = models.BooleanField(null=True)
    community = models.ForeignKey(Community, on_delete=models.CASCADE, blank=True, null=True)
    shs_threshold = models.TextField(default="very_low", blank=True)

    @property
    def schema_name(self):
        name = ""
        if "diesel" in self.user_case:
            name += "D"
        if "pv" in self.user_case:
            name += "PV"
        if "bess" in self.user_case:
            name += "B"
        if name != "":
            name = f"{name}_case.png"
        return name

    @property
    def component_list(self):
        components = []
        if "diesel" in self.user_case:
            components.append("Diesel generator")
        if "pv" in self.user_case:
            components.append("PV Panels")
        if "bess" in self.user_case:
            components.append("Battery storage")
        return ("a {}, " * (len(components) - 2) + "a {}" * (len(components) > 1) + " and a {}").format(*components)

    @property
    def has_diesel(self):
        return "diesel" in self.user_case


class ImplementationPlanContent(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, blank=True, null=True)
    demand_table = models.TextField()
    cost_table = models.TextField()
    capex_table = models.TextField()
    system_table = models.TextField()
    financial_kpi_table = models.TextField()
    financing_structure_table = models.TextField()
    stacked_timeseries_graph = models.TextField()
    mini_grid_demand_graph = models.TextField()
    capex_graph = models.TextField()
    cash_flow_graph = models.TextField()
    system_costs_graph = models.TextField()


def copy_energy_system_from_usecase(usecase_name, scenario):
    """Given a scenario, copy the topology of the usecase"""
    # Filter the name of the project and the usecasename within this project
    usecase_scenario = Scenario.objects.get(project=UseCase.objects.get(name="cp_usecases"), name=usecase_name)
    dm = usecase_scenario.export()
    assets = dm.pop("assets")
    busses = dm.pop("busses")
    # delete pre-existing energy system
    qs_assets = Asset.objects.filter(scenario=scenario)
    qs_busses = Bus.objects.filter(scenario=scenario)
    if qs_busses.exists() or qs_assets.exists():
        qs_assets.delete()
        qs_busses.delete()
    # assign the assets and busses to the given scenario
    assign_assets(scenario, assets)
    assign_busses(scenario, busses)

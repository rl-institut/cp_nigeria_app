from django.contrib.auth.decorators import login_required
import json
import logging
import numpy as np
import os
from django.http import JsonResponse
from jsonview.decorators import json_view
from django.utils.translation import gettext_lazy as _
from django.shortcuts import *
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db.models import Q
from epa.settings import MVS_GET_URL, MVS_LP_FILE_URL
from .forms import *
from business_model.forms import *
from projects.requests import fetch_mvs_simulation_results
from projects.models import *
from projects.views import project_duplicate, project_delete
from business_model.models import *
from cp_nigeria.models import ConsumerGroup
from cp_nigeria.helpers import ReportHandler
from projects.forms import UploadFileForm, ProjectShareForm, ProjectRevokeForm, UseCaseForm
from projects.services import RenewableNinjas
from projects.constants import DONE, PENDING, ERROR
from projects.views import request_mvs_simulation, simulation_cancel
from business_model.helpers import B_MODELS
from dashboard.models import KPIScalarResults, KPICostsMatrixResults, FancyResults
from dashboard.helpers import KPI_PARAMETERS

logger = logging.getLogger(__name__)


def get_aggregated_cgs(project=None, community=None):
    results_dict = {}
    # list according to ConsumerType object ids in database
    consumer_types = ["households", "enterprises", "public", "machinery"]
    for consumer_type_id, consumer_type in enumerate(consumer_types, 1):
        results_dict[consumer_type] = {}
        total_demand = 0
        total_consumers = 0

        if community is None:
            # filter consumer group objects for project based on consumer type
            group_qs = ConsumerGroup.objects.filter(project=project, consumer_type_id=consumer_type_id)
        else:
            group_qs = ConsumerGroup.objects.filter(community=community, consumer_type_id=consumer_type_id)
        # calculate total consumers and total demand as sum of array elements in kWh
        for group in group_qs:
            ts = DemandTimeseries.objects.get(pk=group.timeseries_id)
            total_demand += sum(np.array(ts.values) * group.number_consumers) / 1000
            total_consumers = sum(group.number_consumers for group in group_qs)

        # add machinery total demand to enterprise demand without increasing nr. of consumers
        if consumer_type == "machinery":
            del results_dict[consumer_type]
            results_dict["enterprises"]["total_demand"] += total_demand
        else:
            results_dict[consumer_type]["nr_consumers"] = total_consumers
            results_dict[consumer_type]["total_demand"] = round(total_demand, 2)

    return results_dict


def get_aggregated_demand(proj_id=None, community=None):
    total_demand = []
    if community is not None:
        cg_qs = ConsumerGroup.objects.filter(community=community)
    elif proj_id is not None:
        cg_qs = ConsumerGroup.objects.filter(project__id=proj_id)
    else:
        cg_qs = []

    for cg in cg_qs:
        timeseries_values = np.array(cg.timeseries.values)
        nr_consumers = cg.number_consumers
        if cg.timeseries.units == "Wh":
            timeseries_values = timeseries_values / 1000
        total_demand.append(timeseries_values * nr_consumers)
    return np.vstack(total_demand).sum(axis=0).tolist()


STEP_MAPPING = {
    "choose_location": 1,
    "grid_conditions": 2,
    "demand_profile": 3,
    "scenario_setup": 4,
    "business_model": 5,
    "economic_params": 6,
    "simulation": 7,
    "outputs": 8,
}

CPN_STEP_VERBOSE = {
    "choose_location": _("Choose location"),
    "grid_conditions": _("Grid conditions"),
    "demand_profile": _("Demand load profile selection"),
    "scenario_setup": _("Supply system setup"),
    "economic_params": _("Economic parameters"),
    "simulation": _("Simulation"),
    "business_model": _("Business Model"),
    "outputs": _("Outputs"),
}

# sorts the step names based on the order defined in STEP_MAPPING (for ribbon)
CPN_STEP_VERBOSE = [CPN_STEP_VERBOSE[k] for k, v in sorted(STEP_MAPPING.items(), key=lambda x: x[1])]


@require_http_methods(["GET"])
def home_cpn(request):
    return render(request, "cp_nigeria/index_cpn.html")


@login_required
@require_http_methods(["GET"])
def projects_list_cpn(request, proj_id=None):
    combined_projects_list = (
        Project.objects.filter(Q(user=request.user) | Q(viewers__user__email=request.user.email))
        .distinct()
        .order_by("date_created")
        .reverse()
    )
    # combined_projects_list = Project.objects.filter(
    #     (Q(user=request.user) | Q(viewers__user=request.user)) & Q(country="NIGERIA")
    # ).distinct()

    scenario_upload_form = UploadFileForm(labels=dict(name=_("New scenario name"), file=_("Scenario file")))
    project_upload_form = UploadFileForm(labels=dict(name=_("New project name"), file=_("Project file")))
    project_share_form = ProjectShareForm()
    project_revoke_form = ProjectRevokeForm(proj_id=proj_id)
    usecase_form = UseCaseForm(usecase_qs=UseCase.objects.all(), usecase_url=reverse("usecase_search"))

    return render(
        request,
        "cp_nigeria/project_display.html",
        {
            "project_list": combined_projects_list,
            "proj_id": proj_id,
            "scenario_upload_form": scenario_upload_form,
            "project_upload_form": project_upload_form,
            "project_share_form": project_share_form,
            "project_revoke_form": project_revoke_form,
            "usecase_form": usecase_form,
            "translated_text": {
                "showScenarioText": _("Show scenarios"),
                "hideScenarioText": _("Hide scenarios"),
            },
        },
    )


@login_required
@require_http_methods(["POST"])
def cpn_project_delete(request, proj_id):
    project_delete(request, proj_id)
    return HttpResponseRedirect(reverse("projects_list_cpn"))


@login_required
@require_http_methods(["POST"])
def cpn_project_duplicate(request, proj_id):
    """Duplicates the selected project along with its associated scenarios"""

    answer = project_duplicate(request, proj_id)
    new_proj_id = answer.url.split("/")[-1]
    options, created = Options.objects.get_or_create(project__id=proj_id)
    if created is False:
        options.pk = None
        options.project = Project.objects.get(pk=new_proj_id)
        options.save()

    return HttpResponseRedirect(reverse("projects_list_cpn", args=[new_proj_id]))


@login_required
@require_http_methods(["GET", "POST"])
def cpn_grid_conditions(request, proj_id, scen_id, step_id=STEP_MAPPING["grid_conditions"]):
    # TODO in the future, pre-load the questions instead of written out in the template
    project = get_object_or_404(Project, id=proj_id)

    if (project.user != request.user) and (
        project.viewers.filter(user__email=request.user.email, share_rights="edit").exists() is False
    ):
        raise PermissionDenied

    page_information = "Please include information about your connection to the grid."

    bm_qs = BusinessModel.objects.filter(scenario=project.scenario)
    if bm_qs.exists():
        grid_condition = bm_qs.get().grid_condition
    else:
        grid_condition = ""

    return render(
        request,
        "cp_nigeria/steps/business_model_tree.html",
        {
            "proj_id": proj_id,
            "proj_name": project.name,
            "grid_condition": grid_condition,
            "step_id": step_id,
            "scen_id": scen_id,
            "step_list": CPN_STEP_VERBOSE,
            "page_information": page_information,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def cpn_scenario_create(request, proj_id=None, step_id=STEP_MAPPING["choose_location"]):
    qs_project = Project.objects.filter(id=proj_id)

    proj_name = ""
    if qs_project.exists():
        project = qs_project.get()
        if (project.user != request.user) and (
            project.viewers.filter(user__email=request.user.email, share_rights="edit").exists() is False
        ):
            raise PermissionDenied

    else:
        project = None

    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project) if project is not None else ProjectForm(request.POST)

        if form.is_valid():
            project = form.save(user=request.user)
            options, _ = Options.objects.get_or_create(project=project)
            options.community = form.cleaned_data["community"]
            options.save()

            return HttpResponseRedirect(reverse("cpn_steps", args=[project.id, step_id + 1]))

    elif request.method == "GET":
        if project is not None:
            scenario = Scenario.objects.filter(project=project).last()
            form = ProjectForm(instance=project, initial={"start_date": scenario.start_date})
            qs_options = Options.objects.filter(project=project)
            if qs_options.exists():
                form["community"].initial = qs_options.get(project=project).community

        else:
            form = ProjectForm()
    page_information = "Please input basic project information, such as name, location and duration. You can input geographical data by clicking on the desired project location on the map."
    if project is not None:
        proj_name = project.name
    return render(
        request,
        "cp_nigeria/steps/scenario_create.html",
        {
            "form": form,
            "proj_id": proj_id,
            "proj_name": proj_name,
            "step_id": step_id,
            "step_list": CPN_STEP_VERBOSE,
            "page_information": page_information,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def cpn_demand_params(request, proj_id, step_id=STEP_MAPPING["demand_profile"]):
    project = get_object_or_404(Project, id=proj_id)

    if (project.user != request.user) and (
        project.viewers.filter(user__email=request.user.email, share_rights="edit").exists() is False
    ):
        raise PermissionDenied

    options = get_object_or_404(Options, project=project)
    allow_edition = True

    # TODO change DB default value to 1
    # TODO include the possibility to display the "expected_consumer_increase", "expected_demand_increase" fields
    # with option advanced_view set by user choice
    if request.method == "POST":
        qs_demand = Asset.objects.filter(
            scenario=project.scenario, asset_type__asset_type="demand", name="electricity_demand"
        )

        formset_qs = ConsumerGroup.objects.filter(project=project)
        if options.community is not None:
            formset_qs = ConsumerGroup.objects.filter(community=options.community)
            allow_edition = False

        if allow_edition is False:
            if qs_demand.exists():
                total_demand = get_aggregated_demand(community=options.community)
                demand = qs_demand.get()
                demand.input_timeseries = json.dumps(total_demand)
                demand.save()

            step_id = STEP_MAPPING["demand_profile"] + 1
            return HttpResponseRedirect(reverse("cpn_steps", args=[proj_id, step_id]))
        else:
            formset = ConsumerGroupFormSet(request.POST, queryset=formset_qs, initial=[{"number_consumers": 1}])

            for form in formset:
                # set timeseries queryset so form doesn't throw a validation error
                if f"{form.prefix}-consumer_type" in form.data:
                    try:
                        consumer_type_id = int(form.data.get(f"{form.prefix}-consumer_type"))
                        form.fields["timeseries"].queryset = DemandTimeseries.objects.filter(
                            consumer_type_id=consumer_type_id
                        )
                    except (ValueError, TypeError):
                        pass

                if form.is_valid():
                    # update consumer group if already in database and create new entry if not
                    try:
                        group_id = form.cleaned_data["id"].id
                        consumer_group = ConsumerGroup.objects.get(id=group_id)
                        if form.cleaned_data["DELETE"] is True:
                            consumer_group.delete()
                        else:
                            for field_name, field_value in form.cleaned_data.items():
                                if field_name == "id":
                                    continue
                            setattr(consumer_group, field_name, field_value)
                            consumer_group.save()

                    # AttributeError gets thrown when form id field is empty -> not yet in db
                    except AttributeError:
                        if form.cleaned_data["DELETE"] is True:
                            continue

                        consumer_group = form.save(commit=False)
                        consumer_group.project = project
                        consumer_group.save()

            if formset.is_valid():
                # update demand if exists

                if qs_demand.exists():
                    total_demand = get_aggregated_demand(proj_id=project.id)
                    demand = qs_demand.get()
                    demand.input_timeseries = json.dumps(total_demand)
                    demand.save()

                step_id = STEP_MAPPING["demand_profile"] + 1
                return HttpResponseRedirect(reverse("cpn_steps", args=[proj_id, step_id]))

    elif request.method == "GET":
        options_qs = Options.objects.filter(project=project)
        formset_qs = ConsumerGroup.objects.filter(project=proj_id)
        if options_qs.exists() and options.community is not None:
            formset_qs = ConsumerGroup.objects.filter(community=options_qs.get().community)
            allow_edition = False
        formset = ConsumerGroupFormSet(
            queryset=formset_qs, initial=[{"number_consumers": 1}], form_kwargs={"allow_edition": allow_edition}
        )

        for form, obj in zip(formset, formset_qs):
            for field in form.fields:
                if field != "DELETE":
                    form[field].initial = getattr(obj, field)

        if formset_qs.exists():
            if options.community is not None:
                total_demand = get_aggregated_demand(community=options.community)
            else:
                total_demand = get_aggregated_demand(proj_id=proj_id)
        else:
            total_demand = []

    page_information = "Please input user group data. This includes user type information about households, enterprises and facilities and predicted energy demand tiers as collected from survey data or available information about the community."

    return render(
        request,
        "cp_nigeria/steps/scenario_demand.html",
        {
            "formset": formset,
            "proj_id": proj_id,
            "proj_name": project.name,
            "step_id": step_id,
            "scen_id": project.scenario.id,
            "step_list": CPN_STEP_VERBOSE,
            "allow_edition": allow_edition,
            "total_demand": total_demand,
            "page_information": page_information,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def cpn_scenario(request, proj_id, step_id=STEP_MAPPING["scenario_setup"]):
    project = get_object_or_404(Project, id=proj_id)

    if (project.user != request.user) and (
        project.viewers.filter(user__email=request.user.email, share_rights="edit").exists() is False
    ):
        raise PermissionDenied

    scenario = project.scenario

    if request.method == "GET":
        page_information = "Select the energy system components you would like to include in the simulation. The system can be comprised of a diesel generator, a PV-system, and a battery system (storage) in any combination."

        qs_options = Options.objects.filter(project=project)
        if qs_options.exists():
            options = qs_options.get()
            es_schema_name = options.schema_name
            grid_availability = options.main_grid

        else:
            es_schema_name = None
            grid_availability = False

        context = {
            "proj_id": proj_id,
            "proj_name": project.name,
            "step_id": step_id,
            "scen_id": scenario.id,
            "step_list": CPN_STEP_VERBOSE,
            "es_assets": [],
            "es_schema_name": es_schema_name,
            "page_information": page_information,
            "grid_availability": grid_availability,
        }

        asset_type_name = "bess"

        qs = Asset.objects.filter(scenario=scenario.id, asset_type__asset_type=asset_type_name)

        if qs.exists():
            existing_ess_asset = qs.get()
            ess_asset_children = Asset.objects.filter(parent_asset=existing_ess_asset.id)
            ess_capacity_asset = ess_asset_children.get(asset_type__asset_type="capacity")
            ess_charging_power_asset = ess_asset_children.get(asset_type__asset_type="charging_power")
            ess_discharging_power_asset = ess_asset_children.get(asset_type__asset_type="discharging_power")
            # also get all child assets
            context["es_assets"].append(asset_type_name)
            context["form_bess"] = BessForm(
                proj_id=project.id,
                instance=ess_capacity_asset,
            )
        else:
            context["form_bess"] = BessForm(proj_id=project.id)

        for asset_type_name, form in zip(["dso", "pv_plant", "diesel_generator"], [MainGridForm, PVForm, DieselForm]):
            qs = Asset.objects.filter(scenario=scenario.id, asset_type__asset_type=asset_type_name)

            if qs.exists():
                existing_asset = qs.get()
                context["es_assets"].append(asset_type_name)
                context[f"form_{asset_type_name}"] = form(instance=existing_asset, proj_id=project.id)

            else:
                context[f"form_{asset_type_name}"] = form(proj_id=project.id)

        return render(request, "cp_nigeria/steps/scenario_components.html", context)

    if request.method == "POST":
        asset_forms = dict(bess=BessForm, pv_plant=PVForm, diesel_generator=DieselForm, dso=MainGridForm)
        # collect the assets selected by the user
        user_assets = request.POST.getlist("es_choice", [])

        grid_availability = request.POST.get("grid_availability", "off")
        grid_availability = True if grid_availability == "on" else False

        # Options
        options, _ = Options.objects.get_or_create(project=project)
        options.user_case = json.dumps(user_assets)
        options.main_grid = grid_availability
        options.save()

        qs = Bus.objects.filter(scenario=scenario, type="Electricity")

        if qs.filter(Q(name__contains="ac") & Q(name__contains="dc")).exists():
            ac_bus = qs.get(name="ac_bus")
            dc_bus = qs.get(name="dc_bus")
        else:
            qs.delete()
            ac_bus = Bus(type="Electricity", scenario=scenario, name="ac_bus")
            dc_bus = Bus(type="Electricity", scenario=scenario, name="dc_bus")

        ac_bus.pos_x = 700
        ac_bus.pos_y = 100
        dc_bus.pos_x = 700
        dc_bus.pos_y = 450
        ac_bus.save()
        dc_bus.save()

        # Delete potential existing rectifiers
        Asset.objects.filter(
            scenario=scenario, asset_type=AssetType.objects.get(asset_type="transformer_station_in"), name="rectifier"
        ).delete()

        inverter, created = Asset.objects.get_or_create(
            scenario=scenario,
            asset_type=AssetType.objects.get(asset_type="transformer_station_in"),
            name="inverter",
        )
        if created is True:
            inverter.age_installed = 0
            inverter.installed_capacity = 0
            inverter.capex_fix = 0
            inverter.capex_var = 321210
            inverter.opex_fix = 6424.2
            inverter.opex_var = 0
            inverter.lifetime = 15  # project.economic_data.duration,
            inverter.optimize_cap = True
            inverter.efficiency = 0.95

        inverter.pos_x = dc_bus.pos_x + 175
        inverter.pos_y = dc_bus.pos_y
        inverter.save()

        ConnectionLink.objects.get_or_create(
            bus=dc_bus, bus_connection_port="output_1", asset=inverter, flow_direction="B2A", scenario=scenario
        )
        ConnectionLink.objects.get_or_create(
            bus=ac_bus, bus_connection_port="input_1", asset=inverter, flow_direction="A2B", scenario=scenario
        )

        asset_type_name = "demand"

        demand, created = Asset.objects.get_or_create(
            scenario=scenario, asset_type=AssetType.objects.get(asset_type=asset_type_name), name="electricity_demand"
        )
        demand.pos_x = 900
        demand.pos_y = ac_bus.pos_y
        demand.save()
        if created is True:
            if options.community is not None:
                total_demand = get_aggregated_demand(community=options.community)
            else:
                total_demand = get_aggregated_demand(project.id)
            demand.input_timeseries = json.dumps(total_demand)
            demand.save()

        peak_demand = round(np.array(json.loads(demand.input_timeseries)).max(), 1)

        ConnectionLink.objects.get_or_create(
            bus=ac_bus, bus_connection_port="output_1", asset=demand, flow_direction="B2A", scenario=scenario
        )

        for i, asset_name in enumerate(user_assets):
            qs = Asset.objects.filter(
                scenario=scenario, asset_type__asset_type=asset_name if asset_name != "bess" else "capacity"
            )
            if qs.exists():
                form = asset_forms[asset_name](request.POST, instance=qs.first(), proj_id=project.id)

            else:
                form = asset_forms[asset_name](request.POST, proj_id=project.id)

            if form.is_valid():
                asset_type = get_object_or_404(AssetType, asset_type=asset_name)

                asset = form.save(commit=False)
                # TODO the form save should do some specific things to save the storage correctly
                asset.scenario = scenario

                if asset_name != "bess":
                    asset.asset_type = asset_type
                else:
                    asset.asset_type = get_object_or_404(AssetType, asset_type="capacity")

                if asset_name == "diesel_generator":
                    asset.pos_x = 400
                    asset.pos_y = 200

                    # set the maximum diesel generator capacity to the peak demand
                    asset.maximum_capacity = peak_demand
                    asset.save()

                    bus_diesel, _ = Bus.objects.get_or_create(type="Gas", scenario=scenario, name="diesel_bus")
                    bus_diesel.pos_x = 225
                    bus_diesel.pos_y = asset.pos_y
                    bus_diesel.save()

                    equity_data_qs = EquityData.objects.filter(scenario=scenario)
                    if equity_data_qs.exists():
                        equity_data = equity_data_qs.get()
                        diesel_price_kWh = equity_data.compute_average_fuel_price(
                            initial_fuel_price=asset.opex_var_extra, project_duration=project.economic_data.duration
                        )
                    else:
                        diesel_price_kWh = asset.opex_var_extra

                    dso_diesel, created = Asset.objects.get_or_create(
                        renewable_share=0,
                        peak_demand_pricing_period=1,
                        peak_demand_pricing=0,
                        scenario=scenario,
                        asset_type=AssetType.objects.get(asset_type="gas_dso"),
                        name="diesel_fuel",
                    )
                    dso_diesel.feedin_tariff = 0
                    dso_diesel.energy_price = diesel_price_kWh
                    dso_diesel.pos_x = 50
                    dso_diesel.pos_y = asset.pos_y
                    dso_diesel.save()
                    # connect the diesel generator to the diesel bus and the electricity bus
                    ConnectionLink.objects.get_or_create(
                        bus=bus_diesel,
                        bus_connection_port="input_1",
                        asset=dso_diesel,
                        flow_direction="A2B",
                        scenario=scenario,
                    )
                    ConnectionLink.objects.get_or_create(
                        bus=bus_diesel,
                        bus_connection_port="output_1",
                        asset=asset,
                        flow_direction="B2A",
                        scenario=scenario,
                    )

                    # connect the asset to the electricity bus
                    ConnectionLink.objects.get_or_create(
                        bus=ac_bus, bus_connection_port="input_1", asset=asset, flow_direction="A2B", scenario=scenario
                    )

                if asset_name == "dso":
                    asset.pos_x = 50
                    asset.pos_y = 50
                    asset.save()

                    # delete existing direct connection from dso to ac_bus
                    ConnectionLink.objects.filter(
                        bus=ac_bus,
                        bus_connection_port="input_1",
                        asset=asset,
                        flow_direction="A2B",
                        scenario=scenario,
                    ).delete()

                    bus_dso, _ = Bus.objects.get_or_create(type="Electricity", scenario=scenario, name="dso_bus")
                    bus_dso.pos_x = 225
                    bus_dso.pos_y = asset.pos_y
                    bus_dso.save()

                    dso_availability, created = Asset.objects.get_or_create(
                        scenario=scenario,
                        asset_type=AssetType.objects.get(asset_type="transformer_station_in"),
                        name="dso_availability",
                    )
                    if created is True:
                        dso_availability.age_installed = 0
                        dso_availability.installed_capacity = 0
                        # 300 USD * 774 --> NGN
                        dso_availability.capex_fix = 232200 * peak_demand
                        dso_availability.capex_var = 0
                        dso_availability.opex_fix = 0
                        dso_availability.opex_var = 0
                        dso_availability.lifetime = 100
                        dso_availability.optimize_cap = True
                        dso_availability.efficiency = 1

                    if grid_availability is True:
                        pass  # TODO here affect the efficiency based on user input

                    dso_availability.pos_x = 400
                    dso_availability.pos_y = asset.pos_y
                    dso_availability.save()

                    # connect the asset to the electricity bus
                    ConnectionLink.objects.get_or_create(
                        bus=ac_bus,
                        bus_connection_port="input_1",
                        asset=dso_availability,
                        flow_direction="A2B",
                        scenario=scenario,
                    )
                    ConnectionLink.objects.get_or_create(
                        bus=bus_dso,
                        bus_connection_port="output_1",
                        asset=dso_availability,
                        flow_direction="B2A",
                        scenario=scenario,
                    )
                    ConnectionLink.objects.get_or_create(
                        bus=bus_dso,
                        bus_connection_port="input_1",
                        asset=asset,
                        flow_direction="A2B",
                        scenario=scenario,
                    )
                    # else:
                    #     # delete potential dso availability transformer and bus
                    #     bus_dso = Bus.objects.filter(scenario=scenario, name="dso_bus").delete()
                    #     dso_availability = Asset.objects.filter(
                    #         scenario=scenario,
                    #         name="dso_availability",
                    #     ).delete()
                    #     ConnectionLink.objects.get_or_create(
                    #         bus=ac_bus,
                    #         bus_connection_port="input_1",
                    #         asset=asset,
                    #         flow_direction="A2B",
                    #         scenario=scenario,
                    #     )

                if asset_name == "pv_plant":
                    asset.pos_x = 350
                    asset.pos_y = 350
                    asset.save()
                    if options.community is not None:
                        community = options.community
                        asset.input_timeseries = community.pv_timeseries.values
                        asset.save()
                    else:
                        if asset.input_timeseries == []:
                            qs_pv = Timeseries.objects.filter(scenario=project.scenario)
                            if qs_pv.exists():
                                values = qs_pv.get().values
                            else:
                                values = get_pv_output(project.id)
                            asset.input_timeseries = json.dumps(values)
                            asset.save()

                    # connect the asset to the electricity bus
                    ConnectionLink.objects.get_or_create(
                        bus=dc_bus, bus_connection_port="input_1", asset=asset, flow_direction="A2B", scenario=scenario
                    )

                if asset_name == "bess":
                    ess_asset, _ = Asset.objects.get_or_create(
                        name="battery",
                        asset_type=get_object_or_404(AssetType, asset_type=asset_name),
                        scenario=scenario,
                    )
                    qs_ac = Asset.objects.filter(parent_asset=asset)
                    # Create the ess charging power
                    ess_charging_power_asset, _ = Asset.objects.get_or_create(
                        name=f"{ess_asset.name} input power",
                        asset_type=get_object_or_404(AssetType, asset_type="charging_power"),
                        scenario=scenario,
                        parent_asset=ess_asset,
                    )
                    # Create the ess discharging power
                    ess_discharging_power_asset, _ = Asset.objects.get_or_create(
                        name=f"{ess_asset.name} output power",
                        asset_type=get_object_or_404(AssetType, asset_type="discharging_power"),
                        scenario=scenario,
                        parent_asset=ess_asset,
                    )
                    # Create the ess capacity
                    ess_capacity_asset = asset
                    ess_capacity_asset.name = f"{ess_asset.name} capacity"
                    ess_capacity_asset.parent_asset = ess_asset
                    # remove name property from the form
                    form.cleaned_data.pop("name", None)
                    # Populate all subassets properties
                    for param, value in form.cleaned_data.items():
                        setattr(ess_capacity_asset, param, value)

                        # split efficiency between charge and discharge
                        if param == "efficiency":
                            value = np.sqrt(float(value))
                        # for the charge and discharge set all costs to 0
                        if param in ["capex_fix", "capex_var", "opex_fix"]:
                            value = 0

                        if ess_discharging_power_asset.has_parameter(param):
                            setattr(ess_discharging_power_asset, param, value)

                        # set dispatch price to 0 only for charging power
                        if param == "opex_var":
                            value = 0
                        if ess_charging_power_asset.has_parameter(param):
                            setattr(ess_charging_power_asset, param, value)

                    ess_capacity_asset.save()
                    ess_charging_power_asset.save()
                    ess_discharging_power_asset.save()

                    ess_asset.pos_x = 700
                    ess_asset.pos_y = dc_bus.pos_y + 150
                    ess_asset.save()

                    # connect the battery to the electricity bus
                    ConnectionLink.objects.get_or_create(
                        bus=dc_bus,
                        bus_connection_port="input_1",
                        asset=ess_asset,
                        flow_direction="A2B",
                        scenario=scenario,
                    )
                    ConnectionLink.objects.get_or_create(
                        bus=dc_bus,
                        bus_connection_port="output_1",
                        asset=ess_asset,
                        flow_direction="B2A",
                        scenario=scenario,
                    )

        # Remove unselected assets
        for asset in Asset.objects.filter(
            scenario=scenario.id, asset_type__asset_type__in=["bess", "pv_plant", "diesel_generator", "dso"]
        ):
            if asset.asset_type.asset_type not in user_assets:
                if asset.asset_type.asset_type == "diesel_generator":
                    Asset.objects.filter(asset_type__asset_type="gas_dso").delete()
                    Bus.objects.filter(scenario=scenario, type="Gas").delete()
                asset.delete()

        return HttpResponseRedirect(reverse("cpn_steps", args=[proj_id, step_id + 1]))


@login_required
@require_http_methods(["GET", "POST"])
def cpn_constraints(request, proj_id, step_id=STEP_MAPPING["economic_params"]):
    project = get_object_or_404(Project, id=proj_id)

    if (project.user != request.user) and (
        project.viewers.filter(user__email=request.user.email, share_rights="edit").exists() is False
    ):
        raise PermissionDenied

    scenario = project.scenario
    page_information = (
        "Please review the following values which are suggested for tariff evaluations based on the model you chose."
    )

    # TODO if the energy supply options did not select any component warn the user
    qs_options = Options.objects.filter(project=project)
    if qs_options.exists():
        options = qs_options.get()
        es_schema_name = options.schema_name
        if es_schema_name == "":
            messages.warning(
                request,
                "You haven't selected any component to your energy system. Please select at least one and click on the 'next' button below.",
            )
            return HttpResponseRedirect(reverse("cpn_steps", args=[proj_id, STEP_MAPPING["scenario_setup"]]))

    context = {
        "proj_id": proj_id,
        "proj_name": project.name,
        "step_id": step_id,
        "scen_id": scenario.id,
        "es_schema_name": es_schema_name,
        "step_list": CPN_STEP_VERBOSE,
        "page_information": page_information,
    }

    if request.method == "POST":
        form = EconomicDataForm(request.POST, instance=project.economic_data, prefix="economic")
        try:
            equity_data = EquityData.objects.get(scenario=scenario)
            equity_form = EquityDataForm(request.POST, instance=equity_data, prefix="equity")
        except EquityData.DoesNotExist:
            equity_form = EquityDataForm(request.POST, prefix="equity")

        form_errors = False
        if form.is_valid():
            form.save()
        else:
            form_errors = True

        if equity_form.is_valid():
            equity_data = equity_form.save(commit=False)
            equity_data.debt_start = scenario.start_date.year
            equity_data.scenario = scenario
            equity_data.save()

            # compute the new price and set it to the diesel dso
            if options.has_diesel is True:
                diesel_generator = Asset.objects.get(scenario=scenario, asset_type__asset_type="diesel_generator")
                new_diesel_price_kWh = equity_data.compute_average_fuel_price(
                    initial_fuel_price=diesel_generator.opex_var_extra, project_duration=project.economic_data.duration
                )

                dso_diesel = Asset.objects.get(
                    scenario=scenario,
                    asset_type__asset_type="gas_dso",
                    name="diesel_fuel",
                )
                dso_diesel.energy_price = new_diesel_price_kWh
                dso_diesel.save()

        else:
            form_errors = True

        if form_errors is False:
            answer = HttpResponseRedirect(reverse("cpn_steps", args=[proj_id, step_id + 1]))
        else:
            qs_bm = BusinessModel.objects.filter(scenario=project.scenario)

            try:
                equity_data = EquityData.objects.get(scenario=scenario)
                equity_form = EquityDataForm(instance=equity_data, prefix="equity")
            except EquityData.DoesNotExist:
                initial = {}
                if qs_bm.exists():
                    initial = qs_bm.first().default_fate_values
                equity_form = EquityDataForm(prefix="equity", initial=initial)

            qs_demand = Asset.objects.filter(scenario=project.scenario, asset_type__asset_type="demand")
            if qs_demand.exists():
                demand = json.loads(qs_demand.get().input_timeseries)
                demand_np = np.array(demand)
                peak_demand = round(demand_np.max(), 1)
                daily_demand = round(demand_np.sum() / 365, 1)
            else:
                demand = None
                peak_demand = None
                daily_demand = None

            qs_pv = Asset.objects.filter(scenario=project.scenario, asset_type__asset_type="pv_plant")
            if qs_pv.exists():
                pv_timeseries = json.loads(qs_pv.get().input_timeseries)
            else:
                pv_timeseries = None

            if qs_bm.exists():
                bm = qs_bm.get()
                model_name = B_MODELS[bm.model_name]["Verbose"]
            else:
                model_name = None

            context.update(
                {
                    "form": form,
                    "equity_form": equity_form,
                    "timestamps": [
                        i for i in range(len(demand))
                    ],  # json.dumps(project.scenario.get_timestamps(json_format=True)),
                    "demand": demand,
                    "pv_timeseries": pv_timeseries,
                    "daily_demand": daily_demand,
                    "peak_demand": peak_demand,
                    "model_name": model_name,
                }
            )

            answer = render(
                request,
                "cp_nigeria/steps/scenario_system_params.html",
                context,
            )
    elif request.method == "GET":
        form = EconomicDataForm(
            instance=project.economic_data, initial={"capex_fix": scenario.capex_fix}, prefix="economic"
        )
        qs_bm = BusinessModel.objects.filter(scenario=project.scenario)

        initial = {}
        if qs_bm.exists():
            initial = qs_bm.first().default_fate_values

        try:
            equity_data = EquityData.objects.get(scenario=scenario)
            equity_form = EquityDataForm(instance=equity_data, prefix="equity", default=initial)
        except EquityData.DoesNotExist:
            equity_form = EquityDataForm(prefix="equity", initial=initial)

        qs_demand = Asset.objects.filter(scenario=project.scenario, asset_type__asset_type="demand")
        if qs_demand.exists():
            demand = json.loads(qs_demand.get().input_timeseries)
            demand_np = np.array(demand)
            peak_demand = round(demand_np.max(), 1)
            daily_demand = round(demand_np.sum() / 365, 1)
        else:
            demand = None
            peak_demand = None
            daily_demand = None

        qs_pv = Asset.objects.filter(scenario=project.scenario, asset_type__asset_type="pv_plant")
        if qs_pv.exists():
            pv_timeseries = json.loads(qs_pv.get().input_timeseries)
        else:
            pv_timeseries = None

        if qs_bm.exists():
            bm = qs_bm.get()
            model_name = B_MODELS[bm.model_name]["Verbose"]
        else:
            model_name = None

        context.update(
            {
                "form": form,
                "equity_form": equity_form,
                "timestamps": [
                    i for i in range(len(demand))
                ],  # json.dumps(project.scenario.get_timestamps(json_format=True)),
                "demand": demand,
                "pv_timeseries": pv_timeseries,
                "daily_demand": daily_demand,
                "peak_demand": peak_demand,
                "model_name": model_name,
            }
        )

        answer = render(
            request,
            "cp_nigeria/steps/scenario_system_params.html",
            context,
        )
    return answer


@login_required
@require_http_methods(["GET", "POST"])
def cpn_review(request, proj_id, step_id=STEP_MAPPING["simulation"]):
    project = get_object_or_404(Project, id=proj_id)

    if (project.user != request.user) and (
        project.viewers.filter(user__email=request.user.email, share_rights="edit").exists() is False
    ):
        raise PermissionDenied

    if request.method == "GET":
        html_template = "cp_nigeria/steps/simulation/no-status.html"
        context = {
            "scenario": project.scenario,
            "scen_id": project.scenario.id,
            "proj_id": proj_id,
            "proj_name": project.name,
            "step_id": step_id,
            "step_list": CPN_STEP_VERBOSE,
            "MVS_GET_URL": MVS_GET_URL,
            "MVS_LP_FILE_URL": MVS_LP_FILE_URL,
        }

        qs = Simulation.objects.filter(scenario=project.scenario)

        if qs.exists():
            simulation = qs.first()

            if simulation.status == PENDING:
                fetch_mvs_simulation_results(simulation)

            context.update(
                {
                    "sim_id": simulation.id,
                    "simulation_status": simulation.status,
                    "secondsElapsed": simulation.elapsed_seconds,
                    "rating": simulation.user_rating,
                    "mvs_token": simulation.mvs_token,
                }
            )

            if simulation.status == ERROR:
                context.update({"simulation_error_msg": simulation.errors})
                html_template = "cp_nigeria/steps/simulation/error.html"
            elif simulation.status == PENDING:
                html_template = "cp_nigeria/steps/simulation/pending.html"
            elif simulation.status == DONE:
                html_template = "cp_nigeria/steps/simulation/success.html"

        else:
            print("no simulation existing")

        return render(request, html_template, context)
    return None


@login_required
@require_http_methods(["GET", "POST"])
def cpn_model_choice(request, proj_id, step_id=STEP_MAPPING["business_model"]):
    project = get_object_or_404(Project, id=proj_id)

    if (project.user != request.user) and (
        project.viewers.filter(user__email=request.user.email, share_rights="edit").exists() is False
    ):
        raise PermissionDenied
    context = {
        "scenario": project.scenario,
        "scen_id": project.scenario.id,
        "proj_id": proj_id,
        "proj_name": project.name,
        "step_id": step_id,
        "step_list": CPN_STEP_VERBOSE,
    }

    html_template = "cp_nigeria/steps/scenario_model_choice.html"

    if request.method == "GET":
        bm, created = BusinessModel.objects.get_or_create(
            scenario=project.scenario, defaults={"scenario": project.scenario}
        )
        context["form"] = ModelSuggestionForm(instance=bm)
        context["bm"] = bm
        context["score"] = bm.total_score

        recommended = context["form"].fields["model_name"].initial
        if recommended is not None:
            context["recommended_model"] = recommended
            context["form"] = ModelSuggestionForm(instance=bm, initial={"model_name": recommended})
        answer = render(request, html_template, context)

    if request.method == "POST":
        bm = BusinessModel.objects.get(scenario=project.scenario)
        form = ModelSuggestionForm(request.POST, instance=bm)
        if form.is_valid():
            form.save()
            answer = HttpResponseRedirect(reverse("cpn_steps", args=[proj_id, STEP_MAPPING["business_model"] + 1]))
        else:
            answer = HttpResponseRedirect(reverse("cpn_steps", args=[proj_id, STEP_MAPPING["business_model"] + 1]))

    return answer


@login_required
@require_http_methods(["GET", "POST"])
def cpn_model_suggestion(request, bm_id):
    bm = get_object_or_404(BusinessModel, pk=bm_id)
    proj_id = bm.scenario.project.id
    return HttpResponseRedirect(reverse("cpn_model_choice", args=[proj_id]))


@login_required
@require_http_methods(["GET", "POST"])
def cpn_outputs(request, proj_id, step_id=STEP_MAPPING["outputs"]):
    project = get_object_or_404(Project, id=proj_id)
    options = get_object_or_404(Options, project=project)

    if (project.user != request.user) and (
        project.viewers.filter(user__email=request.user.email, share_rights="edit").exists() is False
    ):
        raise PermissionDenied
    user_scenarios = [project.scenario]

    # TODO here workout the results of the scenario and base diesel scenario

    # get community characteristics
    if options.community is not None:
        aggregated_cgs = get_aggregated_cgs(community=options.community)
    else:
        aggregated_cgs = get_aggregated_cgs(project=project)

    # get optimized capacities
    qs_res = FancyResults.objects.filter(simulation__scenario=project.scenario)
    opt_caps = qs_res.filter(
        optimized_capacity__gt=0, asset__in=["pv_plant", "battery", "inverter", "diesel_generator"], direction="in"
    ).values("asset", "optimized_capacity", "total_flow")
    # TODO here if there is no simulation or supply setup, tell the user they should define one first

    # get total flows
    qs_busses = Bus.objects.filter(scenario=project.scenario, type="Electricity")
    if qs_busses.count() == 1:
        el_bus = qs_busses.get()
        unused_pv = qs_res.filter(asset=f"{el_bus.name}_excess")

    elif qs_busses.filter(Q(name__contains="ac") | Q(name__contains="dc")).exists():
        ac_bus = qs_busses.get(name="ac_bus")
        dc_bus = qs_busses.get(name="dc_bus")
        unused_pv = qs_res.filter(asset=f"{dc_bus.name}_excess")
        unused_diesel = qs_res.filter(asset=f"{ac_bus.name}_excess")

    if unused_pv.exists():
        unused_pv = unused_pv.get().total_flow
    else:
        unused_pv = 0

    if unused_diesel.exists():
        unused_diesel = unused_diesel.get().total_flow
    else:
        unused_diesel = 0

    excess = {"inverter": unused_pv, "diesel_generator": unused_diesel}

    total_demand = np.sum([vals["total_demand"] for cg, vals in aggregated_cgs.items()])
    for cap in opt_caps:
        if cap["asset"] == "pv_plant":
            cap["total_supply"] = cap["total_flow"] - unused_pv
        elif cap["asset"] == "diesel_generator":
            cap["total_supply"] = cap["total_flow"] - unused_diesel
        else:
            cap["total_supply"] = cap["total_flow"]

        cap["unit"] = AssetType.objects.get(
            asset_type__contains="capacity" if cap["asset"] == "battery" else cap["asset"]
        ).unit
        cap["supply_percentage"] = cap["total_supply"] / total_demand * 100

    # diesel fuel values
    if qs_res.filter(asset="diesel_fuel_consumption").exists():
        diesel_consumption_liter = (
            qs_res.filter(asset="diesel_fuel_consumption").get().total_flow / ENERGY_DENSITY_DIESEL
        )
    # costs values
    kpi_cost_results = json.loads(KPICostsMatrixResults.objects.get(simulation__scenario=project.scenario).cost_values)
    asset_costs = {asset: costs for asset, costs in kpi_cost_results.items() if costs.get("costs_total") > 0}
    asset_costs_df = pd.DataFrame.from_dict(asset_costs, orient="index")
    asset_costs["total"] = {col: np.sum(asset_costs_df[col]) for col in asset_costs_df}
    for asset, costs in asset_costs.items():
        costs["unit"] = project.economic_data.currency_symbol

    bm = BusinessModel.objects.get(scenario__project=project)
    model = bm.model_name
    html_template = "cp_nigeria/steps/scenario_outputs.html"

    qs_options = Options.objects.filter(project=project)
    if qs_options.exists():
        es_schema_name = qs_options.get().schema_name
    else:
        es_schema_name = None

    # FATE graphs for demo, will be implemented properly later
    fate_data = pd.read_csv("static/fate_graphs.csv", sep=";", header=0, index_col=0)
    fate_figs = {}
    for col in fate_data:
        x_data = fate_data[col].index.tolist()
        y_data = fate_data[col]
        trace = go.Scatter(x=x_data, y=y_data, name=col)

        layout = go.Layout(title=col, xaxis={"title": "Year"}, yaxis={"title": "NGN"}, template="simple_white")

        fig = go.Figure(data=trace, layout=layout)
        fate_figs[col] = fig.to_html()

    # dict for community characteristics table
    if options.community is not None:
        aggregated_cgs = get_aggregated_cgs(community=options.community)
    else:
        aggregated_cgs = get_aggregated_cgs(project=project)

    # plot for diesel load curve (for debugging minimal load of genset)
    dies_ld = qs_res.filter(energy_vector="Electricity", asset_type="diesel_generator").get()
    genset_asset = Asset.objects.filter(scenario=project.scenario, name="diesel_generator").get()
    print(dies_ld.load_duration)

    # Sort the power generated by the diesel genset in descending order.
    diesel_genset_duration_curve = np.sort(dies_ld.load_duration)[::-1]
    capacity_diesel_genset = opt_caps.filter(asset="diesel_generator").get()["optimized_capacity"]
    min_load = genset_asset.soc_min
    max_load = genset_asset.soc_max

    percentage = 100 * np.arange(1, len(diesel_genset_duration_curve) + 1) / len(diesel_genset_duration_curve)

    # Create a scatter plot for the duration curve
    scatter_trace = go.Scatter(
        x=percentage,
        y=diesel_genset_duration_curve,
        mode="markers + lines",
        name="Duration Curve",
    )

    # Create horizontal lines for minimum and maximum load
    min_load_trace = go.Scatter(
        x=[0, 100],
        y=[min_load * capacity_diesel_genset, min_load * capacity_diesel_genset],
        mode="lines",
        line=dict(color="crimson", dash="dash"),
        name="Minimum Load",
    )

    max_load_trace = go.Scatter(
        x=[0, 100],
        y=[max_load * capacity_diesel_genset, max_load * capacity_diesel_genset],
        mode="lines",
        line=dict(color="crimson", dash="dash"),
        name="Maximum Load",
    )

    # Add annotations for minimum and maximum load
    annotations = [
        dict(
            x=100,
            y=min_load * capacity_diesel_genset,
            xref="x",
            yref="y",
            text=f"minimum load: {min_load * capacity_diesel_genset:0.2f} kW",
            showarrow=True,
            arrowhead=0,
            ax=0,
            ay=-15,
        ),
        dict(
            x=100,
            y=max_load * capacity_diesel_genset,
            xref="x",
            yref="y",
            text=f"maximum load: {max_load * capacity_diesel_genset:0.2f} kW",
            showarrow=True,
            arrowhead=0,
            ax=0,
            ay=15,
        ),
    ]

    # Create the layout
    layout = dict(
        title="Duration Curve for the Diesel Genset Electricity Production",
        xaxis=dict(title="percentage of annual operation [%]"),
        yaxis=dict(title="diesel genset production [kW]"),
        template="simple_white",
    )

    # Create the figure
    fig = go.Figure(data=[scatter_trace, min_load_trace, max_load_trace], layout=layout)

    # Add annotations to the figure
    fig.update_layout(annotations=annotations)

    # Show the figure or save it to a file
    diesel_curve_fig = fig.to_html()

    context = {
        "proj_id": proj_id,
        "capacities": opt_caps,
        "asset_costs": asset_costs,
        "diesel_consumption": diesel_consumption_liter,
        "excess": excess,
        "scen_id": project.scenario.id,
        "scenario_list": user_scenarios,
        "model_description": B_MODELS[model]["Description"],
        "model_name": B_MODELS[model]["Verbose"],
        "model_image": B_MODELS[model]["Graph"],
        "model_image_resp": B_MODELS[model]["Responsibilities"],
        "fate_figs": fate_figs["Net Cash Flow"],
        "fate_cum_net_cash_flow": fate_figs["Cummulated Net Cash Flow"],
        "diesel_curve_fig": diesel_curve_fig,
        "aggregated_cgs": aggregated_cgs,
        "es_schema_name": es_schema_name,
        "proj_name": project.name,
        "step_id": step_id,
        "step_list": CPN_STEP_VERBOSE,
    }

    return render(request, html_template, context)


# TODO for later create those views instead of simply serving the html templates
CPN_STEPS = {
    "choose_location": cpn_scenario_create,
    "grid_conditions": cpn_grid_conditions,
    "demand_profile": cpn_demand_params,
    "scenario_setup": cpn_scenario,
    "economic_params": cpn_constraints,
    "simulation": cpn_review,
    "business_model": cpn_model_choice,
    "outputs": cpn_outputs,
}

# sorts the order in which the views are served in cpn_steps (defined in STEP_MAPPING)
CPN_STEPS = [CPN_STEPS[k] for k, v in sorted(STEP_MAPPING.items(), key=lambda x: x[1]) if k in CPN_STEPS]


@login_required
@require_http_methods(["GET", "POST"])
def cpn_steps(request, proj_id, step_id=None):
    if step_id is None:
        return HttpResponseRedirect(reverse("cpn_steps", args=[proj_id, 1]))

    return CPN_STEPS[step_id - 1](request, proj_id, step_id)


@login_required
@require_http_methods(["GET"])
def cpn_simulation_cancel(request, proj_id):
    project = get_object_or_404(Project, id=proj_id)

    if (project.user != request.user) and (request.user not in project.viewers.all()):
        raise PermissionDenied

    simulation_cancel(request, project.scenario.id)

    return HttpResponseRedirect(reverse("cpn_steps", args=[project.id, STEP_MAPPING["simulation"]]))


@login_required
@require_http_methods(["GET", "POST"])
def cpn_simulation_request(request, proj_id=0):
    project = get_object_or_404(Project, id=proj_id)

    if (project.user != request.user) and (request.user not in project.viewers.all()):
        raise PermissionDenied

    request_mvs_simulation(request, project.scenario.id)

    return HttpResponseRedirect(reverse("cpn_steps", args=[project.id, STEP_MAPPING["simulation"]]))


def get_pv_output(proj_id):
    project = Project.objects.get(id=proj_id)
    coordinates = {"lat": project.latitude, "lon": project.longitude}
    location = RenewableNinjas()
    location.get_pv_output(coordinates)
    pv_ts, _ = Timeseries.objects.get_or_create(scenario=project.scenario, open_source=True, ts_type="source")

    pv_ts.values = np.squeeze(location.data.values).tolist()
    pv_ts.start_time = location.data.index[0]
    pv_ts.end_time = location.data.index[-1]
    pv_ts.time_step = 60
    pv_ts.save()

    return pv_ts.values


@login_required
@json_view
@require_http_methods(["GET", "POST"])
def get_community_details(request):
    community_id = request.GET.get("community_id")
    community = Community.objects.get(pk=community_id)
    data = {"name": community.name, "latitude": community.lat, "longitude": community.lon}
    return JsonResponse(data)


@login_required
@json_view
@require_http_methods(["POST"])
def ajax_consumergroup_form(request, scen_id=None, user_group_id=None):
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # TODO change DB default value to 1
        # TODO include the possibility to display the "expected_consumer_increase", "expected_demand_increase" fields
        # with option advanced_view set by user choice
        form_ug = ConsumerGroupForm(initial={"number_consumers": 1}, advanced_view=False)
        return render(
            request,
            "cp_nigeria/steps/consumergroup_form.html",
            context={"form": form_ug, "scen_id": scen_id, "unique_id": request.POST.get("ug_id")},
        )
    return None


@login_required
@json_view
@require_http_methods(["GET", "POST"])
def ajax_bmodel_infos(request):
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        model = request.GET.get("model_choice")

        return render(
            request,
            "cp_nigeria/steps/b_models.html",
            context={
                "model_description": B_MODELS[model]["Description"],
                "model_name": B_MODELS[model]["Verbose"],
                "model_image": B_MODELS[model]["Graph"],
                "model_image_resp": B_MODELS[model]["Responsibilities"],
                "model_advantages": B_MODELS[model]["Advantages"],
                "model_disadvantages": B_MODELS[model]["Disadvantages"],
            },
        )
    return None


@login_required
@json_view
@require_http_methods(["GET", "POST"])
def ajax_load_timeseries(request):
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        consumer_type_id = request.GET.get("consumer_type")
        timeseries_qs = DemandTimeseries.objects.filter(consumer_type_id=consumer_type_id)
        return render(
            request, "cp_nigeria/steps/timeseries_dropdown_options.html", context={"timeseries_qs": timeseries_qs}
        )
    return None


@login_required
@json_view
@require_http_methods(["POST"])
def ajax_update_graph(request):
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        timeseries_id = request.POST.get("timeseries")
        timeseries = DemandTimeseries.objects.get(id=timeseries_id)

        if timeseries.units == "Wh":
            timeseries_values = timeseries.values
        elif timeseries.units == "kWh":
            timeseries_values = [value / 1000 for value in timeseries.values]
        else:
            return JsonResponse({"error": "timeseries has unsupported unit"}, status=403)

        return JsonResponse({"timeseries_values": timeseries_values})

    return JsonResponse({"error": request})


@login_required
@json_view
@require_http_methods(["GET"])
def cpn_kpi_results(request, proj_id=None):
    project = get_object_or_404(Project, id=proj_id)
    options = get_object_or_404(Options, project=project)

    if (project.user != request.user) and (
        project.viewers.filter(user__email=request.user.email, share_rights="edit").exists() is False
    ):
        raise PermissionDenied

    qs = Simulation.objects.filter(scenario=project.scenario)
    if qs.exists():
        sim = qs.get()
        kpi_scalar_results_obj = KPIScalarResults.objects.get(simulation=sim)
        json.loads(kpi_scalar_results_obj.scalar_values)
        kpi_cost_results_obj = KPICostsMatrixResults.objects.get(simulation=sim)
        json.loads(kpi_cost_results_obj.cost_values)

        qs_res = FancyResults.objects.filter(simulation=sim)
        opt_caps = qs_res.filter(optimized_capacity__gt=0).values_list("asset", "asset_type", "optimized_capacity")

        kpis_of_interest = [
            # "costs_total",
            "levelized_costs_of_electricity_equivalent",
            # "total_emissions",
            "renewable_factor",
        ]
        kpis_of_comparison_diesel = ["costs_total", "levelized_costs_of_electricity_equivalent", "total_emissions"]

        # diesel_results = json.loads(KPIScalarResults.objects.get(simulation__scenario__id=230).scalar_values)
        scenario_results = json.loads(KPIScalarResults.objects.get(simulation__scenario=project.scenario).scalar_values)

        kpis = []
        for kpi in kpis_of_interest:
            unit = KPI_PARAMETERS[kpi]["unit"].replace("currency", project.economic_data.currency_symbol)
            if "Factor" in KPI_PARAMETERS[kpi]["unit"]:
                factor = 100.0
                unit = "%"
                # TODO quick fix for renewable share, fix properly later (this also doesnt include possible renewable share from grid)
                if options.community is not None:
                    scen_values = [
                        round(
                            qs_res.filter(optimized_capacity__gt=0, asset="inverter").get().total_flow
                            / np.sum(get_aggregated_demand(community=options.community))
                            * factor,
                            2,
                        )
                    ]
                else:
                    scen_values = [
                        round(
                            qs_res.filter(optimized_capacity__gt=0, asset="inverter").get().total_flow
                            / np.sum(get_aggregated_demand(proj_id=proj_id))
                            * factor,
                            2,
                        )
                    ]

            else:
                factor = 1.0
                scen_values = [round(scenario_results[kpi] * factor, 2)]  # , round(diesel_results[kpi] * factor, 2)]

            # if kpi not in kpis_of_comparison_diesel:
            #     scen_values[1] = ""

            kpis.append(
                {
                    "name": KPI_PARAMETERS[kpi]["verbose"],
                    "id": kpi,
                    "unit": unit,
                    "scen_values": scen_values,
                    "description": KPI_PARAMETERS[kpi]["definition"],
                }
            )
        table = {"General": kpis}

        # TODO once diesel comparison is enabled replace by "hdrs": ["Indicator", "Scen1", "Diesel only"]
        answer = JsonResponse({"data": table, "hdrs": ["Indicator", ""]}, status=200, content_type="application/json")

    return answer


@json_view
@login_required
@require_http_methods(["GET", "POST"])
def upload_demand_timeseries(request):
    if request.method == "GET":
        n = DemandTimeseries.objects.count()
        form = UploadDemandForm(
            initial={
                "name": f"test_timeserie{n}",
                "ts_type": "source",
                "start_time": "2023-01-01",
                "end_time": "2023-01-31",
                "open_source": True,
                "units": "kWh",
            }
        )
        context = {"form": form}

        return render(request, "asset/upload_timeseries.html", context)

    elif request.method == "POST":
        qs = request.POST
        form = UploadDemandForm(qs)

        if form.is_valid():
            ts = form.save(commit=True)
            ts.user = request.user
            return None
        return None
    return None


def cpn_business_model(request):
    # TODO process this data
    if request.method == "POST":
        grid_condition = request.POST.get("grid_condition")
        proj_id = int(request.POST.get("proj_id"))
        project = get_object_or_404(Project, id=proj_id)
        bm, created = BusinessModel.objects.get_or_create(
            scenario=project.scenario, defaults={"scenario": project.scenario}
        )
        bm.grid_condition = grid_condition.lower()
        bm.save()
        return JsonResponse({"message": f"{grid_condition} model type"})

    return JsonResponse({"message": "Invalid request method"})


@login_required
@require_http_methods(["GET", "POST"])
def download_report(request, proj_id):
    project = get_object_or_404(Project, id=proj_id)
    logging.info("downloading implementation plan")
    implementation_plan = ReportHandler()
    implementation_plan.create_cover_sheet(project)
    implementation_plan.create_report_content(project)
    # implementation_plan.add_paragraph("For now, this is just a demo")
    # implementation_plan.add_paragraph("Here are some graphs:")
    #
    # graph_dir = "static/assets/cp_nigeria/FATE_graphs"
    # for graph in os.listdir(graph_dir):
    #     implementation_plan.add_image(os.path.join(graph_dir, graph))

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    response["Content-Disposition"] = "attachment; filename=report.docx"
    implementation_plan.save(response)

    return response

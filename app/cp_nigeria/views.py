from django.contrib.auth.decorators import login_required
import json
import logging
import numpy as np
from django.http import JsonResponse
from jsonview.decorators import json_view
from django.utils.translation import gettext_lazy as _
from django.shortcuts import *
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from epa.settings import MVS_GET_URL, MVS_LP_FILE_URL
from .forms import *
from business_model.forms import *
from projects.requests import fetch_mvs_simulation_results
from projects.models import *
from business_model.models import *
from cp_nigeria.models import ConsumerGroup
from projects.services import RenewableNinjas
from projects.constants import DONE, PENDING, ERROR
from projects.views import request_mvs_simulation, simulation_cancel
from business_model.helpers import model_score_mapping, B_MODELS
from dashboard.models import KPIScalarResults, KPICostsMatrixResults, FancyResults
from dashboard.helpers import KPI_PARAMETERS

logger = logging.getLogger(__name__)


def get_aggregated_demand(proj_id=None, community=None):
    total_demand = []
    if proj_id:
        cg_qs = ConsumerGroup.objects.filter(project__id=proj_id)
    elif community:
        cg_qs = ConsumerGroup.objects.filter(community=community)
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
    "scenario_setup": _("Scenario setup"),
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
@require_http_methods(["GET", "POST"])
def cpn_grid_conditions(request, proj_id, scen_id, step_id=STEP_MAPPING["grid_conditions"]):
    # TODO in the future, pre-load the questions instead of written out in the template
    project = get_object_or_404(Project, id=proj_id)
    messages.info(request, "Please include information about your connection to the grid.")

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
            # import pdb;pdb.set_trace()
            options.community = form.cleaned_data["community"]
            options.save()

            return HttpResponseRedirect(reverse("cpn_steps", args=[project.id, step_id + 1]))

    elif request.method == "GET":
        if project is not None:
            scenario = Scenario.objects.filter(project=project).last()
            form = ProjectForm(instance=project, initial={"start_date": scenario.start_date})
            form["community"].initial = Options.objects.get(project=project).community

        else:
            form = ProjectForm()
    messages.info(
        request,
        "Please input basic project information, such as name, location and duration. You can "
        "input geographical data by clicking on the desired project location on the map.",
    )
    if project is not None:
        proj_name = project.name
    return render(
        request,
        "cp_nigeria/steps/scenario_create.html",
        {"form": form, "proj_id": proj_id, "proj_name": proj_name, "step_id": step_id, "step_list": CPN_STEP_VERBOSE},
    )


@login_required
@require_http_methods(["GET", "POST"])
def cpn_demand_params(request, proj_id, step_id=STEP_MAPPING["demand_profile"]):
    project = get_object_or_404(Project, id=proj_id)
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

    messages.info(
        request,
        "Please input user group data. This includes user type information about "
        "households, enterprises and facilities and predicted energy demand tiers as collected from "
        "survey data or available information about the community.",
    )

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
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def cpn_scenario(request, proj_id, step_id=STEP_MAPPING["scenario_setup"]):
    project = get_object_or_404(Project, id=proj_id)
    scenario = project.scenario

    if request.method == "GET":
        messages.info(
            request,
            "Select the energy system components you would like to include in the simulation. The "
            "system can be comprised of a diesel generator, a PV-system, and a battery system (storage) "
            "in any combination.",
        )

        qs_options = Options.objects.filter(project=project)
        if qs_options.exists():
            es_schema_name = qs_options.get().schema_name
        else:
            es_schema_name = None

        context = {
            "proj_id": proj_id,
            "proj_name": project.name,
            "step_id": step_id,
            "scen_id": scenario.id,
            "step_list": CPN_STEP_VERBOSE,
            "es_assets": [],
            "es_schema_name": es_schema_name,
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
            context["form_storage"] = BessForm(
                proj_id=project.id,
                initial={
                    "name": existing_ess_asset.name,
                    "installed_capacity": ess_capacity_asset.installed_capacity,
                    "age_installed": ess_capacity_asset.age_installed,
                    "capex_fix": ess_capacity_asset.capex_fix,
                    "capex_var": ess_capacity_asset.capex_var,
                    "opex_fix": ess_capacity_asset.opex_fix,
                    "opex_var": ess_capacity_asset.opex_var,
                    "lifetime": ess_capacity_asset.lifetime,
                    "crate": ess_capacity_asset.crate,
                    "efficiency": ess_capacity_asset.efficiency,
                    "dispatchable": ess_capacity_asset.dispatchable,
                    "optimize_cap": ess_capacity_asset.optimize_cap,
                    "soc_max": ess_capacity_asset.soc_max,
                    "soc_min": ess_capacity_asset.soc_min,
                },
            )
        else:
            context["form_bess"] = BessForm(proj_id=project.id)

        for asset_type_name, form in zip(["pv_plant", "diesel_generator"], [PVForm, DieselForm]):
            qs = Asset.objects.filter(scenario=scenario.id, asset_type__asset_type=asset_type_name)

            if qs.exists():
                existing_asset = qs.get()
                context["es_assets"].append(asset_type_name)
                context[f"form_{asset_type_name}"] = form(instance=existing_asset, proj_id=project.id)

            else:
                context[f"form_{asset_type_name}"] = form(proj_id=project.id)

        return render(request, "cp_nigeria/steps/scenario_components.html", context)

    if request.method == "POST":
        asset_forms = dict(bess=BessForm, pv_plant=PVForm, diesel_generator=DieselForm)
        # collect the assets selected by the user
        user_assets = request.POST.getlist("es_choice", [])

        # Options
        options, _ = Options.objects.get_or_create(project=project)
        options.user_case = json.dumps(user_assets)
        options.save()

        # TODO add the grid option here
        grid_option = request.POST.getlist("grid_option", [])
        # add a form for energy price etc...

        qs = Bus.objects.filter(scenario=scenario, type="Electricity")

        if qs.exists():
            bus_el = qs.get()
        else:
            bus_el = Bus(type="Electricity", scenario=scenario, pos_x=600, pos_y=150, name="electricity_bus")
            bus_el.save()

        asset_type_name = "demand"

        demand, created = Asset.objects.get_or_create(
            scenario=scenario, asset_type=AssetType.objects.get(asset_type=asset_type_name), name="electricity_demand"
        )
        if created is True:
            if options.community is not None:
                total_demand = get_aggregated_demand(community=options.community)
            else:
                total_demand = get_aggregated_demand(project.id)
            demand.input_timeseries = json.dumps(total_demand)
            demand.save()
            ConnectionLink.objects.create(
                bus=bus_el, bus_connection_port="output_1", asset=demand, flow_direction="B2A", scenario=scenario
            )

        for i, asset_name in enumerate(user_assets):
            qs = Asset.objects.filter(scenario=scenario, asset_type__asset_type=asset_name)
            if qs.exists():
                form = asset_forms[asset_name](request.POST, instance=qs.first(), proj_id=project.id)
                if asset_name == "diesel_generator":
                    form["opex_var"].initial = asset.opex_var * ENERGY_DENSITY_DIESEL

            else:
                form = asset_forms[asset_name](request.POST, proj_id=project.id)

            if form.is_valid():
                asset_type = get_object_or_404(AssetType, asset_type=asset_name)

                asset = form.save(commit=False)
                # TODO the form save should do some specific things to save the storage correctly

                asset.scenario = scenario
                asset.asset_type = asset_type
                asset.pos_x = 400
                asset.pos_y = 150 + i * 150
                asset.save()

                if asset_name == "diesel_generator":
                    bus_diesel, _ = Bus.objects.get_or_create(
                        type="Gas", scenario=scenario, pos_x=300, pos_y=50, name="diesel_bus"
                    )

                    dso_diesel, _ = Asset.objects.get_or_create(
                        energy_price="0",
                        feedin_tariff="0",
                        renewable_share=0,
                        peak_demand_pricing_period=1,
                        peak_demand_pricing=0,
                        scenario=scenario,
                        asset_type=AssetType.objects.get(asset_type="gas_dso"),
                        name="diesel_fuel",
                    )
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

                if asset_name == "pv_plant":
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

                if asset_name == "bess":
                    # Create the ess charging power
                    ess_charging_power_asset = Asset(
                        name=f"{asset.name} input power",
                        asset_type=get_object_or_404(AssetType, asset_type="charging_power"),
                        scenario=scenario,
                        parent_asset=asset,
                    )
                    # Create the ess discharging power
                    ess_discharging_power_asset = Asset(
                        name=f"{asset.name} output power",
                        asset_type=get_object_or_404(AssetType, asset_type="discharging_power"),
                        scenario=scenario,
                        parent_asset=asset,
                    )
                    # Create the ess capacity
                    ess_capacity_asset = Asset(
                        name=f"{asset.name} capacity",
                        asset_type=get_object_or_404(AssetType, asset_type="capacity"),
                        scenario=scenario,
                        parent_asset=asset,
                    )
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
                    asset.name = "battery"
                    asset.save()

                    # connect the battery to the electricity bus
                    ConnectionLink.objects.get_or_create(
                        bus=bus_el, bus_connection_port="input_1", asset=asset, flow_direction="A2B", scenario=scenario
                    )
                    ConnectionLink.objects.get_or_create(
                        bus=bus_el, bus_connection_port="output_1", asset=asset, flow_direction="B2A", scenario=scenario
                    )
                else:
                    # connect the asset to the electricity bus
                    ConnectionLink.objects.get_or_create(
                        bus=bus_el, bus_connection_port="input_1", asset=asset, flow_direction="A2B", scenario=scenario
                    )

        # Remove unselected assets
        for asset in Asset.objects.filter(
            scenario=scenario.id, asset_type__asset_type__in=["bess", "pv_plant", "diesel_generator"]
        ):
            if asset.asset_type.asset_type not in user_assets:
                if asset.asset_type.asset_type == "diesel_generator":
                    Asset.objects.filter(asset_type__asset_type="gas_dso").delete()
                    Bus.objects.filter(scenario=scenario, type="Gas").delete()
                asset.delete()

        #     if form.is_valid():
        #         # check whether the constraint is already associated to the scenario
        #         if qs.exists():
        #             if len(qs) == 1:
        #                 for name, value in form.cleaned_data.items():
        #                     if getattr(constraint_instance, name) != value:
        #                         if qs_sim.exists():
        #
        #
        #         if constraint_type == "net_zero_energy":
        #
        #
        return HttpResponseRedirect(reverse("cpn_steps", args=[proj_id, step_id + 1]))


@login_required
@require_http_methods(["GET", "POST"])
def cpn_constraints(request, proj_id, step_id=STEP_MAPPING["economic_params"]):
    project = get_object_or_404(Project, id=proj_id)
    scenario = project.scenario
    messages.info(request, "Please include any relevant constraints for the optimization.")

    qs_options = Options.objects.filter(project=project)
    if qs_options.exists():
        options = qs_options.get()
        es_schema_name = options.schema_name
        demand = np.array(get_aggregated_demand(community=options.community))
        peak_demand = demand.max() / 1000
        daily_demand = demand.sum() / 365 / 1000

    else:
        es_schema_name = None
        peak_demand = None
        daily_demand = None

    context = {
        "proj_id": proj_id,
        "proj_name": project.name,
        "step_id": step_id,
        "scen_id": scenario.id,
        "daily_demand": daily_demand,
        "peak_demand": peak_demand,
        "es_schema_name": es_schema_name,
        "step_list": CPN_STEP_VERBOSE,
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
        else:
            form_errors = True

        if form_errors is False:
            answer = HttpResponseRedirect(reverse("cpn_steps", args=[proj_id, step_id + 1]))
        else:
            context.update(
                {
                    "form": form,
                    "equity_form": equity_form,
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
        try:
            equity_data = EquityData.objects.get(scenario=scenario)
            equity_form = EquityDataForm(instance=equity_data, prefix="equity")
        except EquityData.DoesNotExist:
            equity_form = EquityDataForm(prefix="equity")

        context.update(
            {
                "form": form,
                "equity_form": equity_form,
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

    if (project.user != request.user) and (request.user not in project.viewers.all()):
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
def cpn_model_choice(request, proj_id, step_id=6):
    project = get_object_or_404(Project, id=proj_id)

    if (project.user != request.user) and (request.user not in project.viewers.all()):
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
            context["recommanded_model"] = recommended
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

    if (project.user != request.user) and (request.user not in project.viewers.all()):
        raise PermissionDenied
    user_scenarios = [project.scenario]

    # TODO here workout the results of the scenario and base diesel scenario

    qs_res = FancyResults.objects.filter(simulation__scenario=project.scenario)
    opt_caps = qs_res.filter(optimized_capacity__gt=0)
    bus_el_name = Bus.objects.filter(scenario=project.scenario, type="Electricity").values_list("name", flat=True).get()
    unused_pv = qs_res.filter(asset=f"{bus_el_name}_excess")
    if unused_pv.exists():
        unused_pv = unused_pv.get().total_flow
    unused_diesel = qs_res.filter(energy_vector="Gas", asset_type="excess")
    if unused_diesel.exists():
        unused_diesel = unused_diesel.get().total_flow

    bm = BusinessModel.objects.get(scenario__project=project)
    model = bm.model_name
    html_template = "cp_nigeria/steps/scenario_outputs.html"

    qs_options = Options.objects.filter(project=project)
    if qs_options.exists():
        es_schema_name = qs_options.get().schema_name
    else:
        es_schema_name = None

    context = {
        "proj_id": proj_id,
        "capacities": opt_caps,
        "pv_excess": round(unused_pv, 2),
        "scen_id": project.scenario.id,
        "scenario_list": user_scenarios,
        "model_description": B_MODELS[model]["Description"],
        "model_name": B_MODELS[model]["Name"],
        "model_image": B_MODELS[model]["Graph"],
        "model_image_resp": B_MODELS[model]["Responsibilities"],
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
                "model_name": B_MODELS[model]["Name"],
                "model_image": B_MODELS[model]["Graph"],
                "model_image_resp": B_MODELS[model]["Responsibilities"],
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

    if (project.user != request.user) and (request.user not in project.viewers.all()):
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
        bus_el_name = (
            Bus.objects.filter(scenario=project.scenario, type="Electricity").values_list("name", flat=True).get()
        )
        unused_pv = qs_res.filter(asset=f"{bus_el_name}_excess")
        if unused_pv.exists():
            unused_pv = unused_pv.get().total_flow
        unused_diesel = qs_res.filter(energy_vector="Gas", asset_type="excess")
        if unused_diesel.exists():
            unused_diesel = unused_diesel.get().total_flow

        kpis_of_interest = [
            "costs_total",
            "levelized_costs_of_electricity_equivalent",
            "total_emissions",
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

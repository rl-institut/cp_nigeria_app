from django.contrib.auth.decorators import login_required
import json
import logging
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
from projects.services import RenewableNinjas
from projects.constants import DONE, PENDING, ERROR
from business_model.helpers import model_score_mapping
from dashboard.models import KPIScalarResults, KPICostsMatrixResults, FancyResults
from dashboard.helpers import KPI_PARAMETERS, B_MODELS

logger = logging.getLogger(__name__)

STEP_MAPPING = {
    "choose_location": 1,
    "grid_conditions": 2,
    "demand_profile": 3,
    "scenario_setup": 4,
    "economic_params": 5,
    "simulation": 6,
    "business_model": 7,
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
    messages.info(request, "Please include information about your connection to the grid.")
    return render(
        request,
        "cp_nigeria/steps/business_model_tree.html",
        {"proj_id": proj_id, "step_id": step_id, "scen_id": scen_id, "step_list": CPN_STEP_VERBOSE},
    )


@login_required
@require_http_methods(["GET", "POST"])
def cpn_scenario_create(request, proj_id=None, step_id=STEP_MAPPING["choose_location"]):
    qs_project = Project.objects.filter(id=proj_id)
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
            return HttpResponseRedirect(reverse("cpn_scenario_demand", args=[project.id]))
    elif request.method == "GET":
        if project is not None:
            scenario = Scenario.objects.filter(project=project).last()
            form = ProjectForm(instance=project, initial={"start_date": scenario.start_date})
        else:
            form = ProjectForm()
    messages.info(
        request,
        "Please input basic project information, such as name, location and duration. You can "
        "input geographical data by clicking on the desired project location on the map.",
    )

    return render(
        request,
        "cp_nigeria/steps/scenario_create.html",
        {"form": form, "proj_id": proj_id, "step_id": step_id, "step_list": CPN_STEP_VERBOSE},
    )


@login_required
@require_http_methods(["GET", "POST"])
def cpn_demand_params(request, proj_id, step_id=STEP_MAPPING["demand_profile"]):
    project = get_object_or_404(Project, id=proj_id)

    # TODO change DB default value to 1
    # TODO include the possibility to display the "expected_consumer_increase", "expected_demand_increase" fields
    # with option advanced_view set by user choice
    if request.method == "POST":
        formset_qs = ConsumerGroup.objects.filter(project=project)
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
            step_id = STEP_MAPPING["demand_profile"] + 1
            return HttpResponseRedirect(reverse("cpn_steps", args=[proj_id, step_id]))

    elif request.method == "GET":
        formset_qs = ConsumerGroup.objects.filter(project=proj_id)
        formset = ConsumerGroupFormSet(queryset=formset_qs, initial=[{"number_consumers": 1}])

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
            "step_id": step_id,
            "scen_id": project.scenario.id,
            "step_list": CPN_STEP_VERBOSE,
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

        context = {
            "proj_id": proj_id,
            "step_id": step_id,
            "scen_id": scenario.id,
            "step_list": CPN_STEP_VERBOSE,
            "es_assets": [],
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
                }
            )
        else:
            context["form_bess"] = BessForm()

        for asset_type_name, form in zip(["pv_plant", "diesel_generator"], [PVForm, DieselForm]):
            qs = Asset.objects.filter(scenario=scenario.id, asset_type__asset_type=asset_type_name)

            if qs.exists():
                existing_asset = qs.get()
                context["es_assets"].append(asset_type_name)
                context[f"form_{asset_type_name}"] = form(instance=existing_asset)

            else:
                context[f"form_{asset_type_name}"] = form()

        return render(request, "cp_nigeria/steps/scenario_components.html", context)
    if request.method == "POST":
        asset_forms = dict(bess=BessForm, pv_plant=PVForm, diesel_generator=DieselForm)
        assets = request.POST.getlist("es_choice", [])

        qs = Bus.objects.filter(scenario=scenario)

        if qs.exists():
            bus_el = qs.get()
        else:
            bus_el = Bus(type="Electricity", scenario=scenario, pos_x=600, pos_y=150, name="el_bus")
            bus_el.save()

        for i, asset_name in enumerate(assets):
            qs = Asset.objects.filter(scenario=scenario, asset_type__asset_type=asset_name)
            if qs.exists():
                form = asset_forms[asset_name](request.POST, instance=qs.first())
            else:
                form = asset_forms[asset_name](request.POST)

            if form.is_valid():
                asset_type = get_object_or_404(AssetType, asset_type=asset_name)

                asset = form.save(commit=False)
                # TODO the form save should do some specific things to save the storage correctly

                asset.scenario = scenario
                asset.asset_type = asset_type
                asset.pos_x = 400
                asset.pos_y = 150 + i * 150
                asset.save()
                if asset_name == "bess":
                    ConnectionLink.objects.create(
                        bus=bus_el, bus_connection_port="input_1", asset=asset, flow_direction="A2B", scenario=scenario
                    )
                    ConnectionLink.objects.create(
                        bus=bus_el, bus_connection_port="output_1", asset=asset, flow_direction="B2A", scenario=scenario
                    )
                else:
                    ConnectionLink.objects.create(
                        bus=bus_el, bus_connection_port="input_1", asset=asset, flow_direction="A2B", scenario=scenario
                    )

        # Remove unselected assets
        for asset in Asset.objects.filter(
            scenario=scenario.id, asset_type__asset_type__in=["bess", "pv_plant", "diesel_generator"]
        ):
            if asset.asset_type.asset_type not in assets:
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
        return HttpResponseRedirect(reverse("cpn_steps", args=[proj_id, 4]))


@login_required
@require_http_methods(["GET", "POST"])
def cpn_constraints(request, proj_id, step_id=STEP_MAPPING["economic_params"]):
    project = get_object_or_404(Project, id=proj_id)
    scenario = project.scenario
    messages.info(request, "Please include any relevant constraints for the optimization.")

    if request.method == "POST":
        form = EconomicDataForm(request.POST, instance=project.economic_data)

        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse("cpn_constraints", args=[proj_id]))
        return None
    elif request.method == "GET":
        form = EconomicDataForm(instance=project.economic_data, initial={"capex_fix": scenario.capex_fix})

        return render(
            request,
            "cp_nigeria/steps/scenario_system_params.html",
            {
                "proj_id": proj_id,
                "step_id": step_id,
                "scen_id": scenario.id,
                "form": form,
                "step_list": CPN_STEP_VERBOSE,
            },
        )
    return None


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
def cpn_outputs(request, proj_id, step_id=6):
    project = get_object_or_404(Project, id=proj_id)

    if (project.user != request.user) and (request.user not in project.viewers.all()):
        raise PermissionDenied
    user_scenarios = [project.scenario]

    # TODO here workout the results of the scenario and base diesel scenario

    qs_res = FancyResults.objects.filter(simulation__scenario=project.scenario)
    opt_caps = qs_res.filter(optimized_capacity__gt=0)
    unused_pv = qs_res.get(asset="electricity_dc_excess").total_flow
    unused_diesel = qs_res.filter(energy_vector="Gas", asset_type="excess").get().total_flow

    # TODO make this depend on the previous step user choice
    model = list(B_MODELS.keys())[3]
    html_template = "cp_nigeria/steps/scenario_outputs.html"

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
@require_http_methods(["GET", "POST"])
# TODO: make this view work with dynamic coordinates (from map)
def get_pv_output(request, proj_id):
    project = Project.objects.get(id=proj_id)
    coordinates = {"lat": project.latitude, "lon": project.longitude}
    location = RenewableNinjas()
    location.get_pv_output(coordinates)
    response = HttpResponse(
        content_type="text/csv", headers={"Content-Disposition": 'attachment; filename="pv_output.csv"'}
    )
    location.data.to_csv(response, index=False, sep=";")
    location.create_pv_graph()
    return response


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
    # 65 230 D
    # 65 232 DBPV
    # TODO get the 2 scenarios
    qs = Simulation.objects.filter(scenario=project.scenario)
    if qs.exists():
        sim = qs.get()
        kpi_scalar_results_obj = KPIScalarResults.objects.get(simulation=sim)
        json.loads(kpi_scalar_results_obj.scalar_values)
        kpi_cost_results_obj = KPICostsMatrixResults.objects.get(simulation=sim)
        json.loads(kpi_cost_results_obj.cost_values)

        qs_res = FancyResults.objects.filter(simulation=sim)
        opt_caps = qs_res.filter(optimized_capacity__gt=0).values_list("asset", "asset_type", "optimized_capacity")
        unused_pv = qs_res.get(asset="electricity_dc_excess").total_flow
        unused_diesel = qs_res.filter(energy_vector="Gas", asset_type="excess").get().total_flow

        kpis_of_interest = [
            "costs_total",
            "levelized_costs_of_electricity_equivalent",
            "total_emissions",
            "renewable_factor",
        ]
        kpis_of_comparison_diesel = ["costs_total", "levelized_costs_of_electricity_equivalent", "total_emissions"]

        diesel_results = json.loads(KPIScalarResults.objects.get(simulation__scenario__id=230).scalar_values)
        scenario_results = json.loads(KPIScalarResults.objects.get(simulation__scenario__id=232).scalar_values)

        kpis = []
        for kpi in kpis_of_interest:
            unit = KPI_PARAMETERS[kpi]["unit"].replace("currency", project.economic_data.currency_symbol)
            if "Factor" in KPI_PARAMETERS[kpi]["unit"]:
                factor = 100.0
                unit = "%"
            else:
                factor = 1.0

            scen_values = [round(scenario_results[kpi] * factor, 2), round(diesel_results[kpi] * factor, 2)]
            if kpi not in kpis_of_comparison_diesel:
                scen_values[1] = ""

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

        answer = JsonResponse(
            {"data": table, "hdrs": ["Indicator", "Scen1", "Diesel only"]}, status=200, content_type="application/json"
        )

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

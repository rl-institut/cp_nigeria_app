from django.urls import path, re_path
from .views import *

urlpatterns = [
    path("", home_cpn, name="home_cpn"),
    # steps
    path("<int:proj_id>/edit/step/<int:step_id>", cpn_steps, name="cpn_steps"),
    path(
        "<int:proj_id>/edit/<int:scen_id>/step/<int:step_id>",
        cpn_steps,
        name="cpn_steps",
    ),
    path("new/scenario", cpn_scenario_create, name="cpn_new_scenario"),
    path("<int:proj_id>/edit/create", cpn_scenario_create, name="cpn_scenario_create"),
    path("<int:proj_id>/edit/submit", cpn_scenario_create, name="cpn_scenario_create"),
    path("cpn_business_model", cpn_business_model, name="cpn_business_model"),
    path("<int:proj_id>/edit/create/solar", get_pv_output, name="get_pv_output"),
    path("<int:proj_id>/edit/demand", cpn_demand_params, name="cpn_scenario_demand"),
    path("<int:proj_id>/edit/constraints", cpn_constraints, name="cpn_constraints"),
    path(
        "<int:proj_id>/edit/scenario/<int:scen_id>", cpn_scenario, name="cpn_scenario"
    ),
    path("<int:proj_id>/review", cpn_review, name="cpn_review"),
    path(
        "<int:proj_id>/scenario/<int:scen_id>/model/choice",
        cpn_model_choice,
        name="cpn_model_choice",
    ),
    path("<int:bm_id>/model/choice", cpn_model_suggestion, name="cpn_model_suggestion"),
    # path("<int:proj_id>/update/energy/system/<int:scen_id>", update_energy_system, name="update_energy_system"),
    path(
        "ajax/consumergroup/form/<int:scen_id>",
        ajax_consumergroup_form,
        name="ajax_consumergroup_form",
    ),
    path("ajax/load-timeseries", ajax_load_timeseries, name="ajax_load_timeseries"),
    path("ajax/update-graph", ajax_update_graph, name="ajax_update_graph"),
    path(
        "consumergroup/create/<int:scen_id>",
        create_consumergroup,
        name="create_consumergroup",
    ),
    path(
        "consumergroup/delete/<int:scen_id>",
        delete_consumergroup,
        name="delete_consumergroup",
    ),
    path(
        "upload/timeseries", upload_demand_timeseries, name="upload_demand_timeseries"
    ),
]

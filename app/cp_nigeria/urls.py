from django.urls import path, re_path
from .views import *

urlpatterns = [
    path("", home_cpn, name="home_cpn"),
    # steps
    path("<int:proj_id>/edit/step/<int:step_id>", cpn_steps, name="cpn_steps"),
    path("<int:proj_id>/edit/<int:community_id>/step/<int:step_id>", cpn_steps, name="cpn_steps"),
    path("new/scenario", cpn_scenario_create, name="cpn_new_scenario"),
    path("<int:proj_id>/edit/create", cpn_scenario_create, name="cpn_scenario_create"),
    path("<int:proj_id>/edit/submit", cpn_scenario_create, name="cpn_scenario_create"),
    path("cpn_business_model", cpn_business_model, name="cpn_business_model"),
    path("<int:proj_id>/edit/demand", cpn_demand_params, name="cpn_scenario_demand"),
    path("<int:proj_id>/edit/constraints", cpn_constraints, name="cpn_constraints"),
    path("<int:proj_id>/edit/scenario", cpn_scenario, name="cpn_scenario"),
    path("<int:proj_id>/review", cpn_review, name="cpn_review"),
    path("<int:proj_id>/scenario/model/choice", cpn_model_choice, name="cpn_model_choice"),
    path("<int:bm_id>/model/choice", cpn_model_suggestion, name="cpn_model_suggestion"),
    path("<int:proj_id>/outputs", cpn_outputs, name="cpn_outputs"),
    # path("<int:proj_id>/update/energy/system/<int:scen_id>", update_energy_system, name="update_energy_system"),
    path("ajax/consumergroup/form/<int:scen_id>", ajax_consumergroup_form, name="ajax_consumergroup_form"),
    path("ajax/load-timeseries", ajax_load_timeseries, name="ajax_load_timeseries"),
    path("ajax/update-graph", ajax_update_graph, name="ajax_update_graph"),
    path("ajax/bmodel/infos", ajax_bmodel_infos, name="ajax_bmodel_infos"),
    path("ajax/community/details", get_community_details, name="get_community_details"),
    path("upload/timeseries", upload_demand_timeseries, name="upload_demand_timeseries"),
    path("ajax/<int:proj_id>/cpn_kpi_results", cpn_kpi_results, name="cpn_kpi_results"),
    path("simulation/cancel/<int:proj_id>", cpn_simulation_cancel, name="cpn_simulation_cancel"),
    path("simulation/request/<int:proj_id>", cpn_simulation_request, name="cpn_simulation_request"),
]

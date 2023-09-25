from django.urls import path, re_path
from business_model.views import *

urlpatterns = [
    path("<int:scen_id>", index, name="business_model"),
    path("<int:scen_id>/<int:bm_id>", index, name="business_model"),
    path("<int:bm_id>/grid/connection", grid_question, name="grid_question"),
    path("<int:bm_id>/edisco", edisco_question, name="edisco_question"),
    path("<int:bm_id>/regulation", regulation_question, name="regulation_question"),
    path("<int:bm_id>/capacities", capacities_question, name="capacities_question"),
    path("<int:bm_id>/model/suggestion", model_suggestion, name="model_suggestion"),
    # path(
    #     "ajax/get-graph-parameters-form/<int:proj_id>",
    #     ajax_get_graph_parameters_form,
    #     name="ajax_get_graph_parameters_form",
    # ),
]

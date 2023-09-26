from django.urls import path, re_path
from business_model.views import *

urlpatterns = [
    path("<int:bm_id>/help/select/questions", help_select_questions, name="help_select_questions"),
    path("<int:bm_id>/model/suggestion", model_suggestion, name="model_suggestion"),
]

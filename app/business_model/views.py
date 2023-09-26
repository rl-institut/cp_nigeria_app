import pandas as pd

from django.contrib.auth.decorators import login_required
import json
import logging
import traceback
from django.http import HttpResponseForbidden, JsonResponse
from django.http.response import Http404
from jsonview.decorators import json_view
from django.utils.translation import gettext_lazy as _
from django.shortcuts import *
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from epa.settings import MVS_GET_URL, MVS_LP_FILE_URL
from .forms import *
from projects.models import Scenario
import logging
import traceback
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib.staticfiles.storage import staticfiles_storage

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def help_select_questions(request, bm_id):
    bm = get_object_or_404(BusinessModel, id=bm_id)
    if request.method == "POST":
        form = BMQuestionForm(request.POST, qs=BMAnswer.objects.filter(business_model=bm))

        if form.is_valid():
            qs = BMAnswer.objects.filter(business_model=bm)

            for criteria_num, score in form.cleaned_data.items():
                crit = qs.get(question__id=int(criteria_num.replace("criteria_", "")))
                crit.score = score
                crit.save(update_fields=["score"])
            answer = HttpResponseRedirect(reverse("cpn_model_suggestion", args=[bm.id]))
    else:
        qs = BMAnswer.objects.filter(business_model=bm)

        criterias = BMQuestion.objects.all()
        if qs.exists() is False:
            for criteria in criterias:
                criteria_params = {}

                criteria_params["business_model"] = bm
                criteria_params["question"] = criteria

                # if qs.exists() is False:

                new_criteria = BMAnswer(**criteria_params)
                new_criteria.save()
                # else:
                #     if update_assets is True:
                #         qs.update(**criteria_params)

        categories_map = [cat for cat in criterias.values_list("category", flat=True)]
        categories = [cat for cat in criterias.values_list("category", flat=True).distinct()]
        form = BMQuestionForm(qs=BMAnswer.objects.filter(business_model=bm))

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            answer = render(
                request,
                "cp_nigeria/business_model/help_select_questions.html",
                {"form": form, "categories_map": categories_map, "categories": categories},
            )

    return answer


@login_required
@require_http_methods(["GET", "POST"])
def model_suggestion(request, bm_id):
    bm = get_object_or_404(BusinessModel, id=bm_id)

    if request.method == "GET":
        form = ModelSuggestionForm(score=bm.total_score)

        answer = render(request, "business_model/model_choice.html", {"bm": bm, "form": form})
    if request.method == "POST":
        pass

    return answer

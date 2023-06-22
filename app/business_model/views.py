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
@require_http_methods(["GET"])
def index(request, scen_id, bm_id=None):

    scenario = get_object_or_404(Scenario, id=scen_id)
    qs_bm = BusinessModel.objects.filter(scenario=scenario)
    if qs_bm.exists():
        bm_id = qs_bm.get().id
    if bm_id is None:
        bm = BusinessModel()
        bm.scenario = scenario
        bm.save()
        answer = HttpResponseRedirect(reverse("business_model", args=[scen_id, bm.id]))
    else:
        bm = get_object_or_404(BusinessModel, id=bm_id)
        form = GridQuestionForm(instance=bm)
        answer = render(request, "cp_nigeria/business_model/index.html", {"bm": bm, "form": form})
    return answer


@login_required
@require_http_methods(["GET", "POST"])
def grid_question(request, bm_id):

    bm = get_object_or_404(BusinessModel, id=bm_id)

    if request.method == "GET":

        form = GridQuestionForm(instance=bm)

        answer = render(request, "cp_nigeria/business_model/index.html", {"bm": bm, "form": form})

    if request.method == "POST":
        form = GridQuestionForm(request.POST, instance=bm)
        if form.is_valid():

            bm = form.save(commit=False)
            bm.save(update_fields=["grid_connection"])

            grid_connection = form.cleaned_data["grid_connection"]
            if grid_connection is True:
                answer = render(
                    request,
                    "cp_nigeria/business_model/grid_connection.html",
                    {"bm": bm, "form": form},
                )
            else:
                answer = HttpResponseRedirect(reverse("edisco_question", args=[bm.id]))

    return answer


@login_required
@require_http_methods(["GET", "POST"])
def edisco_question(request, bm_id):

    bm = get_object_or_404(BusinessModel, id=bm_id)

    if request.method == "GET":

        form = EdiscoQuestionForm(instance=bm)

        answer = render(
            request, "cp_nigeria/business_model/edisco_question.html", {"bm": bm, "form": form}
        )

    if request.method == "POST":
        form = EdiscoQuestionForm(request.POST, instance=bm)

        if form.is_valid():

            bm = form.save(commit=False)
            bm.save(update_fields=["regional_active_disco"])

            edisco = form.cleaned_data["regional_active_disco"]
            if edisco is True:
                answer = render(
                    request, "cp_nigeria/business_model/edisco.html", {"bm": bm, "form": form}
                )
            else:
                answer = HttpResponseRedirect(
                    reverse("regulation_question", args=[bm.id])
                )

    return answer


@login_required
@require_http_methods(["GET", "POST"])
def regulation_question(request, bm_id):

    bm = get_object_or_404(BusinessModel, id=bm_id)

    if request.method == "GET":

        form = RegulationQuestionForm()

        answer = render(
            request, "cp_nigeria/business_model/regulation_question.html", {"bm": bm, "form": form}
        )

    if request.method == "POST":
        form = RegulationQuestionForm(request.POST)  # , instance=bm)
        if form.is_valid():

            # bm = form.save(commit=False)
            # bm.save(update_fields=["regulation"])

            # regulation = form.cleaned_data["regulation"]
            answer = HttpResponseRedirect(reverse("capacities_question", args=[bm.id]))

    return answer


@login_required
@require_http_methods(["GET", "POST"])
def capacities_question(request, bm_id):

    bm = get_object_or_404(BusinessModel, id=bm_id)

    if request.method == "GET":

        qs = CapacitiesAnswer.objects.filter(business_model=bm)
        print(qs.exists())
        print(qs)
        if qs.exists() is False:
            criterias = Capacities.objects.all()
            for criteria in criterias:
                criteria_params = {}

                criteria_params["business_model"] = bm
                criteria_params["criteria"] = criteria

                # if qs.exists() is False:

                new_criteria = CapacitiesAnswer(**criteria_params)
                new_criteria.save()
                # else:
                #     if update_assets is True:
                #         qs.update(**criteria_params)
        form = CapacitiesForm(qs=CapacitiesAnswer.objects.filter(business_model=bm))

        answer = render(
            request, "cp_nigeria/business_model/capacities_question.html", {"bm": bm, "form": form}
        )

    if request.method == "POST":
        form = CapacitiesForm(
            request.POST, qs=CapacitiesAnswer.objects.filter(business_model=bm)
        )  # , instance=bm)

        if form.is_valid():
            qs = CapacitiesAnswer.objects.filter(business_model=bm)

            for criteria_num, score in form.cleaned_data.items():
                crit = qs.get(criteria__id=int(criteria_num.replace("criteria_", "")))
                crit.score = score
                crit.save(update_fields=["score"])
            # regulation = form.cleaned_data["capacities"]
            answer = HttpResponseRedirect(reverse("cpn_model_suggestion", args=[bm.id]))

    return answer


@login_required
@require_http_methods(["GET", "POST"])
def model_suggestion(request, bm_id):

    bm = get_object_or_404(BusinessModel, id=bm_id)

    if request.method == "GET":
        form = ModelSuggestionForm(score=bm.total_score)

        answer = render(
            request, "business_model/model_choice.html", {"bm": bm, "form": form}
        )
    if request.method == "POST":
        pass

    return answer

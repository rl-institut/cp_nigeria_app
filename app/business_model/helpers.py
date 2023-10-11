import os
import csv
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.translation import gettext_lazy as _

BM_QUESTIONS_CATEGORIES = {
    "dialogue": _("Engagement, dialogue, and co-determination"),
    "steering": _("Steering capacities"),
    "control": _("Asserting control and credibility"),
    "institutional": _("Supporting Institutional structures"),
    "economic": _("Potential for economic co-benefits"),
    "financial": _("Financial capacities"),
}

B_MODELS = {}

if os.path.exists(staticfiles_storage.path("business_model_list.csv")) is True:
    with open(staticfiles_storage.path("business_model_list.csv"), encoding="utf-8") as csvfile:
        csvreader = csv.reader(csvfile, delimiter=",", quotechar='"')
        for i, row in enumerate(csvreader):
            if i == 0:
                hdr = row
                # Name,Category,Description,Graph,Responsibilities
                label_idx = hdr.index("Name")
                graph_idx = hdr.index("Graph")
                description_idx = hdr.index("Description")
                cat_idx = hdr.index("Category")
                resp_idx = hdr.index("Responsibilities")
            else:
                label = row[label_idx]

                B_MODELS[label] = {k: v for k, v in zip(hdr, row)}


def model_score_mapping(score):
    if 0.3 > score >= 0:
        answer = "Operator led"
    elif 0.6 > score >= 0.3:
        answer = "Co-op / Project Developer hybrid model"
    elif 1 >= score >= 0.6:
        answer = "Cooperative Model"
    return answer


def available_models(score, grid_condition):
    models = []
    for k in B_MODELS:
        if B_MODELS[k]["Category"] == grid_condition:
            if score is None:
                models.append((k, k.replace("_", " ")))
            elif score >= 0.7:
                if "cooperative" in B_MODELS[k]["Name"]:
                    models.append((k, k.replace("_", " ")))
            else:
                if "cooperative" not in B_MODELS[k]["Name"]:
                    models.append((k, k.replace("_", " ")))
    return models

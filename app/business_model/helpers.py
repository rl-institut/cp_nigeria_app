import os
import csv
import json
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

BM_FATE_DEFAULT_VALUES = {
    "isolated_cooperative_led": {
        "grant_share": 70,
        "debt_share": 30,
        "equity_share": 0,
        "debt_interest_MG": 11,
        "debt_interest_SHS": 0,
        "equity_interest_MG": 0,
    },
    "isolated_operator_led": {
        "grant_share": 0,
        "debt_share": 80,
        "equity_share": 20,
        "debt_interest_MG": 11,
        "debt_interest_SHS": 0,
        "equity_interest_MG": 15,
    },
    "interconnected_cooperative_led": {
        "grant_share": 70,
        "debt_share": 30,
        "equity_share": 0,
        "debt_interest_MG": 11,
        "debt_interest_SHS": 0,
        "equity_interest_MG": 0,
    },
    "interconnected_operator_led": {
        "grant_share": 0,
        "debt_share": 80,
        "equity_share": 20,
        "debt_interest_MG": 11,
        "debt_interest_SHS": 0,
        "equity_interest_MG": 15,
    },
    "interconnected_spv_led": {
        "grant_share": 0,
        "debt_share": 50,
        "equity_share": 50,
        "debt_interest_MG": 11,
        "debt_interest_SHS": 0,
        "equity_interest_MG": 5,
    },
    "interconnected_collaborative_spv_led": {
        "grant_share": 30,
        "debt_share": 40,
        "equity_share": 30,
        "debt_interest_MG": 11,
        "debt_interest_SHS": 0,
        "equity_interest_MG": 15,
    },
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
                # adv_idx = hdr.index("Advantages")
                # disadv_idx = hdr.index("Disadvantages")
            else:
                label = row[label_idx]
                B_MODELS[label] = {}
                for k, v in zip(hdr, row):
                    if k not in ("Advantages", "Disadvantages"):
                        B_MODELS[label][k] = v
                    else:
                        B_MODELS[label][k] = json.loads(v)


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

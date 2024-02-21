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

BM_DEFAULT_ECONOMIC_VALUES = {
    "isolated_cooperative_led": {
        "grant_share": 60,
        # "debt_share": 30,
        # "equity_share": 0,
        "debt_interest_MG": 11,
        "debt_interest_replacement": 11,
        "debt_interest_SHS": 0,
        "equity_interest_MG": 0,
        "equity_community_amount": 5,
        "equity_developer_amount": 5,
    },
    "isolated_operator_led": {
        "grant_share": 60,
        # "debt_share": 80,
        # "equity_share": 20,
        "debt_interest_MG": 11,
        "debt_interest_replacement": 11,
        "debt_interest_SHS": 0,
        "equity_interest_MG": 15,
        "equity_community_amount": 0,
        "equity_developer_amount": 10,
    },
    "interconnected_cooperative_led": {
        "grant_share": 60,
        # "debt_share": 30,
        # "equity_share": 0,
        "debt_interest_MG": 11,
        "debt_interest_replacement": 11,
        "debt_interest_SHS": 0,
        "equity_interest_MG": 0,
        "equity_community_amount": 5,
        "equity_developer_amount": 5,
    },
    "interconnected_operator_led": {
        "grant_share": 60,
        # "debt_share": 80,
        # "equity_share": 20,
        "debt_interest_MG": 11,
        "debt_interest_replacement": 11,
        "debt_interest_SHS": 0,
        "equity_interest_MG": 15,
        "equity_community_amount": 0,
        "equity_developer_amount": 10,
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
                verbose_idx = hdr.index("Verbose")
                graph_idx = hdr.index("Graph")
                description_idx = hdr.index("Description")
                cat_idx = hdr.index("Category")
                resp_idx = hdr.index("Responsibilities")
                adv_idx = hdr.index("Advantages")
                disadv_idx = hdr.index("Disadvantages")
            else:
                label = row[label_idx]
                B_MODELS[label] = {}
                for k, v in zip(hdr, row):
                    if k not in ("Advantages", "Disadvantages"):
                        B_MODELS[label][k] = v
                    else:
                        B_MODELS[label][k] = json.loads(v)


def available_models(score, grid_condition):
    models = []
    for k in B_MODELS:
        if B_MODELS[k]["Category"] == grid_condition:
            if score is None:
                models.append((k, B_MODELS[k]["Verbose"]))
            elif score >= 0.7:
                if "cooperative" in B_MODELS[k]["Name"]:
                    models.append((k, B_MODELS[k]["Verbose"]))
            else:
                if "cooperative" not in B_MODELS[k]["Name"]:
                    models.append((k, B_MODELS[k]["Verbose"]))
    return models

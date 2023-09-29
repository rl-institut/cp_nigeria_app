from dashboard.helpers import B_MODELS


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

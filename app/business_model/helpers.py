

def model_score_mapping(score):
    if 0.3 > score >= 0:
        answer = "Operator led"
    elif 0.6 > score >= 0.3:
        answer = "Co-op / Project Developer hybrid model"
    elif 1 >= score >= 0.6:
        answer = "Cooperative Model"
    return answer
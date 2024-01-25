from math import floor
import pandas as pd
from django.utils.safestring import mark_safe

from django import template
from django.db.models import Q
from projects.models import Project

register = template.Library()


@register.filter(name="beautiful_seconds")
def convert_seconds_to_intuitive_string(value):
    try:
        convert = lambda divisor, mod: floor(value / divisor % mod)
        days = convert(86400, 1)
        hours = convert(3600, 24)
        mins = convert(60, 60)
        secs = convert(1, 60)

        return f"{days}d {hours}h {mins}m {secs}s"

    except Exception as e:
        return str(e)


@register.filter(name="df_to_html")
def df_to_html(df: pd.DataFrame):
    return mark_safe(df.to_html())


@register.filter(name="fill_spaces")
def fill_spaces(string: str):
    return string.replace(" ", "_")


@register.filter(name="scenario_list")
def get_scenario_list_from_project(project):
    return project.scenario_set.all().order_by("name")


@register.filter
def has_viewer_edit_rights(proj_id, user):
    try:
        project = Project.objects.get(pk=proj_id)
    except Project.DoesNotExist:
        project = None
    answer = False
    if project is not None:
        if project.user == user:
            answer = True
        else:
            qs = project.viewers.filter(Q(user__email=user.email) & Q(share_rights="edit"))
            if qs.exists():
                answer = True
    return answer


@register.filter
def has_viewer_read_rights(proj_id, user):
    try:
        project = Project.objects.get(pk=proj_id)
    except Project.DoesNotExist:
        project = None
    answer = False
    if project is not None:
        if project.user == user:
            answer = True
        else:
            qs = project.viewers.filter(Q(user__email=user.email) & Q(share_rights="read"))
            if qs.exists():
                answer = True
    return answer


@register.filter
def pdb(element):
    import pdb

    pdb.set_trace()
    return element


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def get_field(form, key):
    return form.fields[key].get_bound_field(form, key)


@register.filter
def has_field(form, key):
    return key in form.fields


@register.filter
def has_economical_parameters(form):
    answer = False
    for field in form.fields:
        if is_economical_parameter(field):
            answer = True
            break
    return answer


@register.filter
def has_technical_parameters(form):
    answer = False
    for field in form.fields:
        if is_technical_parameter(field):
            answer = True
            break
    return answer


@register.filter
def is_economical_parameter(param):
    return param in [
        "capex_fix",
        "capex_var",
        "opex_fix",
        "opex_var",
        "energy_price",
        "feedin_tariff",
    ]


@register.filter
def is_technical_parameter(param):
    if param == "name":
        return False
    else:
        return not is_economical_parameter(param)


@register.filter
def get_selected_scenarios(request, proj_id):
    return request.session.get("selected_scenarios", {}).get(str(proj_id))


@register.filter
def get_category(field_id, categories):
    question_id = int(field_id.split("_")[1]) - 1
    return categories[question_id]


@register.filter
def get_index(a_list, index):
    return a_list[index]


@register.filter
def is_current_category(field_category, current_category):
    return field_category == current_category

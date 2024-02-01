from django import template

register = template.Library()


@register.simple_tag
def setvar(val=None):
    return val


@register.filter
def getfield(value, arg):
    """Gets an attribute of an object dynamically from a string name"""
    if hasattr(value, "fields"):
        fields = getattr(value, "fields")
        if str(arg) in fields:
            return str(fields[str(arg)])


@register.filter
def getkey(mapping, key):
    return mapping.get(key, "")


@register.filter
def field_to_title(value):
    if isinstance(value, str):
        value = value.replace("_", " ")
        return value.title()
    else:
        return value

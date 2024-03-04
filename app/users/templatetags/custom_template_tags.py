from django import template
import re

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
        # Define words to exclude from capitalization
        lowercase_words = ["per"]
        uppercase_words = ["pv", "shs"]
        value = value.replace("_", " ")
        words = value.split()

        # Check each word and capitalize it if it's not in the excluded list
        for i, word in enumerate(words):
            if re.match(r"\((.*?)\)$", word):  # Check if the word contains a unit in parentheses at the end
                # If there's a unit at the end, keep it as it is
                continue
            elif word.lower() not in lowercase_words:
                if word.lower() in uppercase_words:
                    words[i] = word.upper()
                else:
                    words[i] = word.title()

        # Join the words back into a string
        value = " ".join(words)

        return value
    else:
        return value

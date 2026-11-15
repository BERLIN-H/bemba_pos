from django import template

register = template.Library()


@register.filter
def split(value, separator=','):
    return [item.strip() for item in str(value).split(separator) if item.strip()]


@register.filter
def get_field(form, name):
    try:
        return form[name]
    except (KeyError, TypeError):
        return ''


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key, False)
    except AttributeError:
        return False

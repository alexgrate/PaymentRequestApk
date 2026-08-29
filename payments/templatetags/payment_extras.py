"""Small template helpers.

Django templates cannot subscript a dict with a variable key, which the sort
links and page-size links both need.
"""

from django import template

register = template.Library()


@register.filter
def dictkey(mapping, key):
    """Look up `key` in `mapping`, returning "" when absent."""
    if hasattr(mapping, "get"):
        return mapping.get(key, "")
    return ""

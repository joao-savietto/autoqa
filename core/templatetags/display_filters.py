from django import template

register = template.Library()


@register.filter
def strip_severity_prefix(value):
    """Strip severity prefixes (LOW:, MEDIUM:, HIGH:) from incident summaries."""
    if not value:
        return value
    prefixes = ("HIGH:", "MEDIUM:", "LOW:")
    for prefix in prefixes:
        if value.startswith(prefix):
            remainder = value[len(prefix):].lstrip()
            # Capitalize the first letter
            return remainder[0].upper() + remainder[1:] if remainder else remainder
    return value

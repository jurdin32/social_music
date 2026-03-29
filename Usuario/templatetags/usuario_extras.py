from django import template

register = template.Library()


@register.filter
def get_item(value, key):
    try:
        return value.get(key)
    except Exception:
        return None


@register.filter
def poll_option(options, opcion):
    try:
        idx = int(opcion) - 1
        if idx < 0:
            return ''
        return options[idx] if idx < len(options) else ''
    except Exception:
        return ''


@register.filter
def encuesta_votos_opcion(pub, opcion):
    try:
        return pub.encuesta_votos_opcion(int(opcion))
    except Exception:
        return 0

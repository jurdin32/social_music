import re
import pathlib

# ── 1. Leer author-page.html ─────────────────────────────────────────────────
src = pathlib.Path('templates/author-page.html').read_text(encoding='utf-8')
lines = src.splitlines(keepends=True)

# Encontrar índices clave
def find_line(pattern, start=0):
    for i, l in enumerate(lines[start:], start):
        if pattern in l:
            return i
    return -1

main_content_start = find_line('<!-- main content -->', find_line('<!-- navigation left -->', find_line('</nav>')))
main_content_end   = find_line('<!-- main content -->', main_content_start + 1)

# ── 2. Construir base template ────────────────────────────────────────────────
before_content = ''.join(lines[:main_content_start + 1])  # hasta <!-- main content -->
after_content  = ''.join(lines[main_content_end:])         # desde el segundo <!-- main content -->

# Ajustar nav: avatar con usuario real + logout
before_content = before_content.replace(
    '<a href="default-settings.html" class="p-0 ms-3 menu-icon"><img src="{% static \'sociala/images/profile-4.png\' %}" alt="user" class="w40 mt--1"></a>',
    '''<form method="POST" action="{% url 'account_logout' %}" class="d-inline">{% csrf_token %}<button type="submit" class="p-0 ms-3 menu-icon border-0 bg-transparent"><img src="{% if user.socialaccount_set.all %}{{ user.socialaccount_set.all.0.get_avatar_url }}{% else %}{% static 'sociala/images/profile-4.png' %}{% endif %}" alt="user" class="w40 mt--1 rounded-circle"></button></form>'''
)

# Añadir {% block extra_css %} y {% block title %}
before_content = before_content.replace(
    '<title>Sociala - Social Network App HTML Template </title>',
    '<title>{% block title %}Sociala{% endblock %}</title>'
)
before_content = before_content.replace(
    '    <link rel="stylesheet" href="{% static \'sociala/css/lightbox.css\' %}">\n\n\n</head>',
    '    <link rel="stylesheet" href="{% static \'sociala/css/lightbox.css\' %}">\n    {% block extra_css %}{% endblock %}\n</head>'
)

# Añadir {% block extra_js %} antes del cierre body
after_content = after_content.replace(
    '    <script src="{% static \'sociala/js/plugin.js\' %}">',
    '    {% block extra_js %}{% endblock %}\n    <script src="{% static \'sociala/js/plugin.js\' %}">'
)

base = (
    before_content
    + '\n        <div class="main-content right-chat-active">\n\n'
    + '            <div class="middle-sidebar-bottom">\n\n'
    + '                <div class="middle-sidebar-left">\n\n'
    + '{% block content %}{% endblock %}\n\n'
    + '                </div>\n'
    + '            </div>\n'
    + '        </div>\n\n'
    + after_content
)

pathlib.Path('templates/base.html').write_text(base, encoding='utf-8')
print('base.html OK - lineas:', base.count('\n'))

# ── 3. Transformar default-badge.html ────────────────────────────────────────
badge_src = pathlib.Path('static/sociala/default-badge.html').read_text(encoding='utf-8')

# Extraer solo el contenido del middle-sidebar-left (entre las dos primeras <div class="row"> del main)
match = re.search(r'(<div class="middle-sidebar-left">)(.*?)(</div>\s*</div>\s*</div>\s*<!-- main content -->)', badge_src, re.S)
if match:
    content_block = match.group(2)
    # Convertir rutas de imágenes
    content_block = re.sub(r'src="images/([^"]+)"', lambda m: "src=\"{% static 'sociala/images/" + m.group(1) + "' %}\"", content_block)
    content_block = re.sub(r'url\(images/([^)]+)\)', lambda m: "url({% static 'sociala/images/" + m.group(1) + "' %})", content_block)
    content_block = re.sub(r'href="(?!http|#|/|{%|mailto)([^"]+\.html)"', 'href="#"', content_block)
else:
    # Fallback: extraer el body entero
    body_match = re.search(r'<body[^>]*>(.*?)</body>', badge_src, re.S)
    content_block = body_match.group(1) if body_match else badge_src
    content_block = re.sub(r'src="images/([^"]+)"', lambda m: "src=\"{% static 'sociala/images/" + m.group(1) + "' %}\"", content_block)
    content_block = re.sub(r'url\(images/([^)]+)\)', lambda m: "url({% static 'sociala/images/" + m.group(1) + "' %})", content_block)

badge_template = (
    "{% extends 'base.html' %}\n"
    "{% load static %}\n\n"
    "{% block title %}Badges - Sociala{% endblock %}\n\n"
    "{% block content %}\n"
    + content_block.strip()
    + "\n{% endblock %}\n"
)

pathlib.Path('templates/default-badge.html').write_text(badge_template, encoding='utf-8')
print('default-badge.html OK - lineas:', badge_template.count('\n'))

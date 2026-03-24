from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/feed/$', consumers.FeedConsumer.as_asgi()),
    re_path(r'ws/perfil/(?P<username>\w+)/$', consumers.PerfilConsumer.as_asgi()),
    re_path(r'ws/global/$', consumers.GlobalConsumer.as_asgi()),
]

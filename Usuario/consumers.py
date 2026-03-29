import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

# ── Presencia online (dict en memoria — single-process Daphne) ────────────
# {user_id: username}
_ONLINE_USERS = {}


class FeedConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket para el feed de inicio — recibe notificaciones de nuevos álbumes."""

    async def connect(self):
        user = self.scope.get('user')
        if not user or user.is_anonymous:
            await self.close()
            return
        self.user_group = f'feed_{user.id}'
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    async def nuevo_album(self, event):
        await self.send_json(event['data'])

    async def nueva_publicacion(self, event):
        await self.send_json(event['data'])


class PerfilConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket para la página de perfil — recibe actualizaciones en tiempo real."""

    async def connect(self):
        self.username = self.scope['url_route']['kwargs']['username']
        self.perfil_group = f'perfil_{self.username}'
        await self.channel_layer.group_add(self.perfil_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'perfil_group'):
            await self.channel_layer.group_discard(self.perfil_group, self.channel_name)

    async def perfil_update(self, event):
        await self.send_json(event['data'])


class GlobalConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket global — recibe eventos de nuevos usuarios, follows, notificaciones, presencia."""

    async def connect(self):
        user = self.scope.get('user')
        if not user or user.is_anonymous:
            await self.close()
            return
        self.user_id = user.id
        self.username = user.username
        # Grupo global para todos los usuarios conectados
        await self.channel_layer.group_add('global', self.channel_name)
        # Grupo personal para notificaciones individuales
        self.personal_group = f'user_{user.id}'
        await self.channel_layer.group_add(self.personal_group, self.channel_name)
        await self.accept()
        # Registrar presencia
        _ONLINE_USERS[user.id] = user.username
        # Notificar a todos que este usuario está en línea
        await self.channel_layer.group_send('global', {
            'type': 'user_presence',
            'data': {
                'event': 'user_presence',
                'user_id': user.id,
                'username': user.username,
                'online': True,
            },
        })

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard('global', self.channel_name)
        if hasattr(self, 'personal_group'):
            await self.channel_layer.group_discard(self.personal_group, self.channel_name)
        if hasattr(self, 'user_id'):
            _ONLINE_USERS.pop(self.user_id, None)
            # Notificar a todos que este usuario se desconectó
            await self.channel_layer.group_send('global', {
                'type': 'user_presence',
                'data': {
                    'event': 'user_presence',
                    'user_id': self.user_id,
                    'username': getattr(self, 'username', ''),
                    'online': False,
                },
            })

    async def nuevo_usuario(self, event):
        await self.send_json(event['data'])

    async def follow_update(self, event):
        await self.send_json(event['data'])

    async def nuevo_album_global(self, event):
        await self.send_json(event['data'])

    async def like_update(self, event):
        await self.send_json(event['data'])

    async def notificacion(self, event):
        await self.send_json(event['data'])

    async def user_presence(self, event):
        await self.send_json(event['data'])

    async def historia_nueva(self, event):
        await self.send_json(event['data'])

    async def historia_like_update(self, event):
        await self.send_json(event['data'])

    async def historia_comentario_nuevo(self, event):
        await self.send_json(event['data'])

    async def publicacion_comentario_nuevo(self, event):
        await self.send_json(event['data'])


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket de chat directo entre dos usuarios."""

    async def connect(self):
        user = self.scope.get('user')
        if not user or user.is_anonymous:
            await self.close()
            return
        self.me = user
        self.otro_username = self.scope['url_route']['kwargs']['username']
        # La sala es la misma independientemente de quién conecta primero
        nombres = sorted([user.username, self.otro_username])
        self.room_group = 'chat___' + '__'.join(nombres)
        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group'):
            await self.channel_layer.group_discard(self.room_group, self.channel_name)

    async def receive_json(self, content):
        # ── Indicador de escritura ──────────────────────────────────────
        if content.get('event') == 'typing':
            await self.channel_layer.group_send(self.room_group, {
                'type': 'chat_typing',
                'data': {
                    'event': 'typing',
                    'emisor': self.me.username,
                    'escribiendo': bool(content.get('escribiendo', False)),
                },
            })
            return

        mensaje = (content.get('mensaje') or '').strip()
        if not mensaje:
            return
        msg_obj = await self._guardar_mensaje(mensaje)
        foto = await self._get_foto()
        nombre = await self._get_nombre()
        # Broadcast del mensaje a la sala
        await self.channel_layer.group_send(self.room_group, {
            'type': 'chat_message',
            'data': {
                'event': 'mensaje',
                'emisor': self.me.username,
                'emisor_id': self.me.id,
                'mensaje': mensaje,
                'tipo': 'texto',
                'archivo_url': '',
                'archivo_nombre': '',
                'enviado': timezone.localtime(msg_obj.enviado).strftime('%H:%M'),
                'emisor_foto': foto,
                'id': msg_obj.pk,
            },
        })
        # Notificar al receptor por su canal personal (campanita)
        receptor_id = await self._get_receptor_id()
        if receptor_id:
            await self.channel_layer.group_send(f'user_{receptor_id}', {
                'type': 'notificacion',
                'data': {
                    'event': 'chat_mensaje',
                    'emisor': self.me.username,
                    'emisor_id': self.me.id,
                    'emisor_nombre': nombre,
                    'emisor_foto': foto,
                    'mensaje': mensaje,
                    'url': f'/chat/{self.me.username}/',
                },
            })

    @database_sync_to_async
    def _guardar_mensaje(self, contenido):
        from django.contrib.auth.models import User as DjangoUser
        from .models import MensajeChat
        receptor = DjangoUser.objects.get(username=self.otro_username)
        return MensajeChat.objects.create(
            emisor=self.me,
            receptor=receptor,
            contenido=contenido,
            tipo='texto',
        )

    @database_sync_to_async
    def _get_foto(self):
        try:
            return self.me.perfil.get_foto() or ''
        except Exception:
            return ''

    @database_sync_to_async
    def _get_nombre(self):
        try:
            return self.me.perfil.nombre_completo()
        except Exception:
            return self.me.username

    @database_sync_to_async
    def _get_receptor_id(self):
        from django.contrib.auth.models import User as DjangoUser
        try:
            return DjangoUser.objects.get(username=self.otro_username).id
        except Exception:
            return None

    async def chat_message(self, event):
        await self.send_json(event['data'])

    async def chat_typing(self, event):
        # Solo reenviar al otro usuario (no al emisor)
        if event['data'].get('emisor') != self.me.username:
            await self.send_json(event['data'])


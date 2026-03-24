import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer


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
    """WebSocket global — recibe eventos de nuevos usuarios, follows, etc."""

    async def connect(self):
        user = self.scope.get('user')
        if not user or user.is_anonymous:
            await self.close()
            return
        self.user_id = user.id
        # Grupo global para todos los usuarios conectados
        await self.channel_layer.group_add('global', self.channel_name)
        # Grupo personal para notificaciones individuales
        self.personal_group = f'user_{user.id}'
        await self.channel_layer.group_add(self.personal_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard('global', self.channel_name)
        if hasattr(self, 'personal_group'):
            await self.channel_layer.group_discard(self.personal_group, self.channel_name)

    async def nuevo_usuario(self, event):
        await self.send_json(event['data'])

    async def follow_update(self, event):
        await self.send_json(event['data'])

    async def nuevo_album_global(self, event):
        await self.send_json(event['data'])

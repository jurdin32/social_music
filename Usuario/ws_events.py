from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def _send(group, message):
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(group, message)


def notificar_nuevo_album(album):
    """Envía el nuevo álbum al feed de cada seguidor del artista."""
    from .models import Perfil
    perfil_artista, _ = Perfil.objects.get_or_create(usuario=album.artista)
    data = {
        'type': 'nuevo_album',
        'album_id': album.pk,
        'titulo': album.titulo,
        'genero': album.get_genero_display(),
        'portada': album.portada.url if album.portada else '',
        'artista_username': album.artista.username,
        'artista_nombre': album.artista.get_full_name() or album.artista.username,
        'num_canciones': album.num_canciones(),
        'duracion': album.duracion_total(),
        'descripcion': album.descripcion[:80] if album.descripcion else '',
    }
    # Notificar a cada seguidor en su feed personal
    for seguidor in perfil_artista.seguidores.select_related('usuario').all():
        _send(f'feed_{seguidor.usuario.id}', {
            'type': 'nuevo_album',
            'data': {**data, 'event': 'nuevo_album'},
        })
    # Evento global (para la página de usuarios)
    _send('global', {
        'type': 'nuevo_album_global',
        'data': {**data, 'event': 'nuevo_album_global'},
    })


def notificar_follow(seguidor_user, objetivo_user, ahora_sigue):
    """Notifica al perfil del objetivo y a global sobre follow/unfollow."""
    from .models import Perfil
    perfil_seguidor, _ = Perfil.objects.get_or_create(usuario=seguidor_user)
    perfil_objetivo, _ = Perfil.objects.get_or_create(usuario=objetivo_user)
    data_perfil = {
        'event': 'follow_update',
        'seguidor_username': seguidor_user.username,
        'seguidor_nombre': perfil_seguidor.nombre_completo(),
        'seguidor_foto': perfil_seguidor.foto.url if perfil_seguidor.foto else (perfil_seguidor.get_foto() or ''),
        'objetivo_username': objetivo_user.username,
        'ahora_sigue': ahora_sigue,
        'nuevo_total_seguidores': perfil_objetivo.num_seguidores(),
        'nuevo_total_siguiendo_seguidor': perfil_seguidor.num_siguiendo(),
    }
    # Notificar la página de perfil del objetivo
    _send(f'perfil_{objetivo_user.username}', {
        'type': 'perfil_update',
        'data': data_perfil,
    })
    # Notificar la página de perfil del seguidor (actualizar su contador "siguiendo")
    _send(f'perfil_{seguidor_user.username}', {
        'type': 'perfil_update',
        'data': data_perfil,
    })
    # Global: actualizar contadores en la página de usuarios
    _send('global', {
        'type': 'follow_update',
        'data': data_perfil,
    })


def notificar_perfil_actualizado(user):
    """Notifica que un perfil se actualizó (foto, portada, bio, etc.)."""
    from .models import Perfil
    perfil, _ = Perfil.objects.get_or_create(usuario=user)
    data = {
        'event': 'perfil_editado',
        'username': user.username,
        'nombre': perfil.nombre_completo(),
        'foto': perfil.foto.url if perfil.foto else (perfil.get_foto() or ''),
        'portada': perfil.portada.url if perfil.portada else '',
        'bio': perfil.bio,
    }
    _send(f'perfil_{user.username}', {
        'type': 'perfil_update',
        'data': data,
    })

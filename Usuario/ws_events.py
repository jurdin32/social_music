from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone


def _send(group, message):
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(group, message)


def _crear_y_enviar_notificacion(destinatario_user, remitente_user, tipo, mensaje, url=''):
    """Crea registro DB de notificación y lo envía por WS al destinatario."""
    from .models import Notificacion, Perfil
    notif = Notificacion.objects.create(
        destinatario=destinatario_user,
        remitente=remitente_user,
        tipo=tipo,
        mensaje=mensaje,
        url=url,
    )
    perfil_rem, _ = Perfil.objects.get_or_create(usuario=remitente_user)
    data = {
        'event': 'notificacion',
        'id': notif.pk,
        'tipo': tipo,
        'mensaje': mensaje,
        'url': url,
        'remitente_nombre': perfil_rem.nombre_completo(),
        'remitente_foto': perfil_rem.foto.url if perfil_rem.foto else (perfil_rem.get_foto() or ''),
        'remitente_username': remitente_user.username,
        'creado': timezone.localtime(notif.creado).isoformat(),
    }
    _send(f'user_{destinatario_user.id}', {
        'type': 'notificacion',
        'data': data,
    })
    return notif

def notificar_nuevo_album(album):
    """Envía el nuevo álbum al feed del artista y de cada seguidor."""
    from .models import Perfil
    perfil_artista, _ = Perfil.objects.get_or_create(usuario=album.artista)
    base_data = {
        'event': 'nuevo_album',
        'album_id': album.pk,
        'titulo': album.titulo,
        'genero': album.get_genero_display(),
        'portada': album.portada.url if album.portada else '',
        'artista_username': album.artista.username,
        'artista_nombre': album.artista.get_full_name() or album.artista.username,
        'artista_foto': perfil_artista.foto.url if perfil_artista.foto else (perfil_artista.get_foto() or ''),
        'num_canciones': album.num_canciones(),
        'duracion': album.duracion_total(),
        'descripcion': album.descripcion[:80] if album.descripcion else '',
    }
    # Notificar al propio artista en su feed
    _send(f'feed_{album.artista.id}', {
        'type': 'nuevo_album',
        'data': base_data,
    })
    # Notificar a cada seguidor en su feed personal + crear notificación
    for seguidor in perfil_artista.seguidores.select_related('usuario').all():
        _send(f'feed_{seguidor.usuario.id}', {
            'type': 'nuevo_album',
            'data': base_data,
        })
        _crear_y_enviar_notificacion(
            destinatario_user=seguidor.usuario,
            remitente_user=album.artista,
            tipo='album',
            mensaje=f'{base_data["artista_nombre"]} publicó un nuevo álbum: {album.titulo}',
            url=f'/albumes/{album.pk}/',
        )
    # Evento global (para la página de usuarios)
    _send('global', {
        'type': 'nuevo_album_global',
        'data': {**base_data, 'event': 'nuevo_album_global'},
    })


def notificar_nuevas_canciones(album, cantidad=1):
    """Notifica a los seguidores cuando un álbum recibe nuevas canciones."""
    from .models import Perfil

    perfil_artista, _ = Perfil.objects.get_or_create(usuario=album.artista)
    titulo = album.titulo
    msg = (
        f'{perfil_artista.nombre_completo()} agregó {cantidad} nueva cancion a {titulo}'
        if cantidad == 1 else
        f'{perfil_artista.nombre_completo()} agregó {cantidad} nuevas canciones a {titulo}'
    )

    for seguidor in perfil_artista.seguidores.select_related('usuario').all():
        _crear_y_enviar_notificacion(
            destinatario_user=seguidor.usuario,
            remitente_user=album.artista,
            tipo='album',
            mensaje=msg,
            url=f'/albumes/{album.pk}/',
        )


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
    # Notificación solo cuando ahora_sigue (no al dejar de seguir)
    if ahora_sigue:
        perfil_seguidor2, _ = Perfil.objects.get_or_create(usuario=seguidor_user)
        _crear_y_enviar_notificacion(
            destinatario_user=objetivo_user,
            remitente_user=seguidor_user,
            tipo='follow',
            mensaje=f'{perfil_seguidor2.nombre_completo()} comenzó a seguirte',
            url=f'/usuario/{seguidor_user.username}/',
        )


def notificar_like(tipo, obj_id, total, user_foto, user_username):
    """Difunde el nuevo conteo de likes a todos los seguidores que tengan el item en su feed."""
    # Usamos el grupo global para que cualquier usuario conectado actualice el contador
    _send('global', {
        'type': 'like_update',
        'data': {
            'event': 'like_update',
            'tipo': tipo,          # 'publicacion' o 'album'
            'obj_id': obj_id,
            'total': total,
            'user_foto': user_foto,
            'user_username': user_username,
        },
    })


def notificar_nueva_publicacion(pub):
    """Envía la nueva publicación al feed del autor y de cada seguidor."""
    from .models import Perfil
    perfil_autor, _ = Perfil.objects.get_or_create(usuario=pub.autor)
    base_data = {
        'event': 'nueva_publicacion',
        'pub_id': pub.pk,
        'contenido': pub.contenido,
        'imagen': pub.imagen.url if pub.imagen else '',
        'encuesta_pregunta': pub.encuesta_pregunta,
        'encuesta_opcion1': pub.encuesta_opcion1,
        'encuesta_opcion2': pub.encuesta_opcion2,
        'encuesta_opcion3': pub.encuesta_opcion3,
        'encuesta_opcion4': pub.encuesta_opcion4,
        'encuesta_opciones': pub.encuesta_opciones(),
        'encuesta_fin': timezone.localtime(pub.encuesta_fin).isoformat() if pub.encuesta_fin else '',
        'encuesta_expirada': pub.encuesta_expirada,
        'comentarios_total': pub.num_comentarios(),
        'autor_username': pub.autor.username,
        'autor_nombre': pub.autor.get_full_name() or pub.autor.username,
        'autor_foto': perfil_autor.foto.url if perfil_autor.foto else (perfil_autor.get_foto() or ''),
        'url_eliminar': f'/publicaciones/{pub.pk}/eliminar/',
        'url_like': f'/publicaciones/{pub.pk}/like/',
        'url_perfil': f'/usuario/{pub.autor.username}/',
    }
    # Notificar al propio autor
    _send(f'feed_{pub.autor.id}', {
        'type': 'nueva_publicacion',
        'data': {**base_data, 'es_propio': True},
    })
    # Notificar a cada seguidor + crear notificación
    for seguidor in perfil_autor.seguidores.select_related('usuario').all():
        _send(f'feed_{seguidor.usuario.id}', {
            'type': 'nueva_publicacion',
            'data': {**base_data, 'es_propio': False},
        })
        _crear_y_enviar_notificacion(
            destinatario_user=seguidor.usuario,
            remitente_user=pub.autor,
            tipo='publicacion',
            mensaje=f'{base_data["autor_nombre"]} hizo una nueva publicación',
            url=f'/inicio/',
        )


def notificar_publicacion_eliminada(pub_id, autor):
    """Notifica al autor y sus seguidores que la publicación fue eliminada."""
    from .models import Perfil
    perfil_autor, _ = Perfil.objects.get_or_create(usuario=autor)
    msg = {
        'type': 'nueva_publicacion',
        'data': {'event': 'publicacion_eliminada', 'pub_id': pub_id},
    }
    # Notificar al autor
    _send(f'feed_{autor.id}', msg)
    # Notificar a cada seguidor para que desaparezca de su feed tambien
    for seguidor in perfil_autor.seguidores.select_related('usuario').all():
        _send(f'feed_{seguidor.usuario.id}', msg)


def notificar_voto_encuesta_publicacion(pub, resultados, total_votos, mi_voto, votos_detalle, user):
    from .models import Perfil
    perfil_user, _ = Perfil.objects.get_or_create(usuario=user)
    data = {
        'event': 'publicacion_encuesta_voto',
        'pub_id': pub.id,
        'resultados': resultados,
        'total_votos': total_votos,
        'user_username': user.username,
        'user_nombre': perfil_user.nombre_completo(),
        'user_foto': perfil_user.foto.url if perfil_user.foto else (perfil_user.get_foto() or ''),
        'mi_voto': mi_voto,
        'votos_detalle': votos_detalle,
    }

    _send(f'feed_{pub.autor_id}', {'type': 'nueva_publicacion', 'data': data})

    perfil_autor, _ = Perfil.objects.get_or_create(usuario=pub.autor)
    for seguidor in perfil_autor.seguidores.select_related('usuario').all():
        _send(f'feed_{seguidor.usuario.id}', {'type': 'nueva_publicacion', 'data': data})

    _send('global', {'type': 'nueva_publicacion', 'data': data})


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


def notificar_historia_nueva(historia):
    from django.contrib.auth.models import User
    from .models import Perfil
    perfil_autor, _ = Perfil.objects.get_or_create(usuario=historia.autor)
    data = {
        'event': 'historia_nueva',
        'historia_id': historia.id,
        'autor_id': historia.autor_id,
        'autor_username': historia.autor.username,
        'autor_nombre': perfil_autor.nombre_completo(),
        'autor_foto': perfil_autor.foto.url if perfil_autor.foto else (perfil_autor.get_foto() or ''),
        'tipo': historia.tipo,
        'archivo_url': historia.archivo.url if historia.archivo else '',
        'texto': historia.texto,
        'creado': timezone.localtime(historia.creado).isoformat(),
    }

    # Entregar en tiempo real segun privacidad.
    destinatarios_ids = {historia.autor_id}
    if historia.privacidad == 'publica':
        destinatarios_ids = set(User.objects.values_list('id', flat=True))
    elif historia.privacidad == 'seguidores':
        for seguidor in perfil_autor.seguidores.select_related('usuario').all():
            if seguidor.usuario_id:
                destinatarios_ids.add(seguidor.usuario_id)
    elif historia.privacidad == 'mejores_amigos':
        destinatarios_ids.update(perfil_autor.amigos_cercanos.values_list('id', flat=True))

    # Excluir usuarios ocultos por el autor.
    ocultos_ids = set(historia.ocultar_a.values_list('id', flat=True))
    destinatarios_ids.difference_update(ocultos_ids)

    for user_id in destinatarios_ids:
        _send(f'user_{user_id}', {'type': 'historia_nueva', 'data': data})

    # Crear notificación campana para seguidores (segun solicitud de negocio).
    nombre_autor = perfil_autor.nombre_completo()
    for seguidor in perfil_autor.seguidores.select_related('usuario').all():
        if seguidor.usuario_id in ocultos_ids:
            continue
        _crear_y_enviar_notificacion(
            destinatario_user=seguidor.usuario,
            remitente_user=historia.autor,
            tipo='publicacion',
            mensaje=f'{nombre_autor} publicó una historia nueva',
            url='/historias/',
        )


def notificar_like_historia(historia, user):
    from .models import Perfil
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=user)
    _send('global', {
        'type': 'historia_like_update',
        'data': {
            'event': 'historia_like_update',
            'historia_id': historia.id,
            'total': historia.num_likes(),
            'user_foto': perfil_obj.foto.url if perfil_obj.foto else (perfil_obj.get_foto() or ''),
            'user_username': user.username,
        },
    })


def notificar_comentario_historia(comentario):
    from .models import Perfil
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=comentario.autor)
    _send('global', {
        'type': 'historia_comentario_nuevo',
        'data': {
            'event': 'historia_comentario_nuevo',
            'historia_id': comentario.historia_id,
            'comentario_id': comentario.id,
            'autor_username': comentario.autor.username,
            'autor_nombre': perfil_obj.nombre_completo(),
            'autor_foto': perfil_obj.foto.url if perfil_obj.foto else (perfil_obj.get_foto() or ''),
            'contenido': comentario.contenido,
            'creado': timezone.localtime(comentario.creado).strftime('%H:%M'),
        },
    })


def notificar_comentario_publicacion(comentario):
    from .models import Perfil
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=comentario.autor)
    _send('global', {
        'type': 'publicacion_comentario_nuevo',
        'data': {
            'event': 'publicacion_comentario_nuevo',
            'pub_id': comentario.publicacion_id,
            'comentario_id': comentario.id,
            'autor_username': comentario.autor.username,
            'autor_nombre': perfil_obj.nombre_completo(),
            'autor_foto': perfil_obj.foto.url if perfil_obj.foto else (perfil_obj.get_foto() or ''),
            'contenido': comentario.contenido,
            'creado': timezone.localtime(comentario.creado).strftime('%H:%M'),
            'total_comentarios': comentario.publicacion.num_comentarios(),
        },
    })

import json
from datetime import timedelta, datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone
from django.db.models import Q
from .models import (
    Perfil, Album, Cancion, Publicacion, PreferenciasUsuario, Historia,
    GrupoMusical, GrupoMiembro, EventoMusical, EventoAsistente,
    InvitacionGrupo, InvitacionEvento,
    PublicacionEncuestaVoto,
)
from .forms import EditarPerfilForm, AlbumForm, CancionForm, PublicacionForm, HistoriaForm


def _parse_usernames(raw):
    if not raw:
        return []
    return [u.strip().lstrip('@') for u in raw.split(',') if u.strip()]


def _puede_ver_historia(usuario, historia, desde=None):
    if historia.autor_id == usuario.id:
        return True
    if desde and historia.creado < desde:
        return False
    if historia.ocultar_a.filter(pk=usuario.pk).exists():
        return False
    if historia.privacidad == 'publica':
        return True

    perfil_autor, _ = Perfil.objects.get_or_create(usuario=historia.autor)
    mi_perfil, _ = Perfil.objects.get_or_create(usuario=usuario)

    if historia.privacidad == 'seguidores':
        return perfil_autor.seguidores.filter(pk=mi_perfil.pk).exists()
    if historia.privacidad == 'mejores_amigos':
        return perfil_autor.amigos_cercanos.filter(pk=usuario.pk).exists()
    return False


def verificacion_exitosa(request):
    return render(request, 'account/verification_success.html')


def home(request):
    if request.user.is_authenticated:
        return redirect('inicio')
    return redirect('account_login')


@login_required
def inicio(request):
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    # Perfiles que sigo
    siguiendo_perfiles = Perfil.objects.filter(seguidores=perfil_obj)
    usuarios_seguidos = [p.usuario for p in siguiendo_perfiles]

    # Incluir mis propias publicaciones también
    usuarios_feed = list(usuarios_seguidos) + [request.user]

    # Publicaciones de seguidos + propias
    publicaciones = (
        Publicacion.objects
        .filter(autor__in=usuarios_feed)
        .select_related('autor', 'autor__perfil')
        .prefetch_related('likes', 'comentarios', 'comentarios__autor', 'comentarios__autor__perfil')
        .order_by('-creado')
    )

    # Álbumes públicos de los que sigo, más recientes primero
    feed_albumes = Album.objects.filter(
        artista__in=usuarios_seguidos, es_publico=True
    ).select_related('artista').prefetch_related('canciones').order_by('-creado')

    # Combinar publicaciones y álbumes en un único feed ordenado por fecha
    feed = []
    for p in publicaciones:
        feed.append({'tipo': 'publicacion', 'obj': p, 'fecha': p.creado})
    for a in feed_albumes:
        feed.append({'tipo': 'album', 'obj': a, 'fecha': a.creado})
    feed.sort(key=lambda x: x['fecha'], reverse=True)

    # IDs de álbumes y publicaciones que el usuario ya dio like (para estado inicial)
    mis_likes_albumes = set(Album.objects.filter(likes=request.user).values_list('pk', flat=True))
    mis_likes_pubs = set(Publicacion.objects.filter(likes=request.user).values_list('pk', flat=True))
    publicaciones_feed_ids = [p.id for p in publicaciones]
    mis_votos_qs = PublicacionEncuestaVoto.objects.filter(
        usuario=request.user,
        publicacion_id__in=publicaciones_feed_ids,
    ).values('publicacion_id', 'opcion')
    publicaciones_encuesta_votadas = {v['publicacion_id'] for v in mis_votos_qs}
    publicaciones_encuesta_mi_voto = {v['publicacion_id']: v['opcion'] for v in mis_votos_qs}

    # Formulario para nueva publicación
    form_pub = PublicacionForm()

    contexto = {
        'user': request.user,
        'perfil': perfil_obj,
        'feed': feed,
        'form_pub': form_pub,
        'mis_likes_albumes': list(mis_likes_albumes),
        'mis_likes_pubs': list(mis_likes_pubs),
        'publicaciones_encuesta_votadas': list(publicaciones_encuesta_votadas),
        'publicaciones_encuesta_mi_voto': publicaciones_encuesta_mi_voto,
        'mis_albumes': request.user.albumes.all()[:5],
    }
    return render(request, 'default.html', contexto)


@login_required
def perfil(request):
    return redirect('pagina_usuario', username=request.user.username)


@login_required
def editar_perfil(request):
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    if request.method == 'POST':
        form = EditarPerfilForm(
            request.POST, request.FILES,
            instance=perfil_obj, user=request.user
        )
        if form.is_valid():
            form.save()
            form.save_user(request.user)
            from .ws_events import notificar_perfil_actualizado
            notificar_perfil_actualizado(request.user)
            return redirect('pagina_usuario', username=request.user.username)
    else:
        form = EditarPerfilForm(instance=perfil_obj, user=request.user)
    contexto = {
        'user': request.user,
        'perfil': perfil_obj,
        'form': form,
    }
    return render(request, 'editar-perfil.html', contexto)


@login_required
def insignias(request):
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    contexto = {'user': request.user, 'perfil': perfil_obj}
    return render(request, 'default-badge.html', contexto)


@login_required
def historias(request):
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)

    if request.method == 'POST':
        form = HistoriaForm(request.POST, request.FILES)
        if form.is_valid():
            historia = form.save(commit=False)
            historia.autor = request.user
            
            # Detectar tipo: primero por content_type, luego por extensión
            ctype = (getattr(historia.archivo, 'content_type', '') or '').lower()
            nombre_archivo = str(historia.archivo.name).lower()
            
            if ctype.startswith('video/'):
                historia.tipo = 'video'
            elif ctype.startswith('image/'):
                historia.tipo = 'imagen'
            # Fallback: detectar por extensión si content_type no es confiable
            elif any(nombre_archivo.endswith(ext) for ext in ['.mp4', '.webm', '.ogg', '.mov', '.m4v', '.avi', '.mkv']):
                historia.tipo = 'video'
            else:
                historia.tipo = 'imagen'
            
            historia.save()

            ocultar_usernames = _parse_usernames(form.cleaned_data.get('ocultar_usernames'))
            if ocultar_usernames:
                usuarios_ocultos = User.objects.filter(username__in=ocultar_usernames).exclude(pk=request.user.pk)
                historia.ocultar_a.set(usuarios_ocultos)

            if historia.privacidad == 'mejores_amigos':
                amigos_usernames = _parse_usernames(form.cleaned_data.get('amigos_cercanos_usernames'))
                amigos = User.objects.filter(username__in=amigos_usernames).exclude(pk=request.user.pk)
                perfil_obj.amigos_cercanos.set(amigos)

            from .ws_events import notificar_historia_nueva
            notificar_historia_nueva(historia)
            return redirect('historias')
    else:
        form = HistoriaForm()

    desde = timezone.now() - timedelta(hours=24)
    mi_perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
    siguiendo_ids = set(
        Perfil.objects.filter(seguidores=mi_perfil).values_list('usuario_id', flat=True)
    )
    amigos_cercanos_de_ids = set(
        Perfil.objects.filter(amigos_cercanos=request.user).values_list('usuario_id', flat=True)
    )
    usuarios_ids = set(siguiendo_ids | amigos_cercanos_de_ids | {request.user.id})

    historias_qs = (
        Historia.objects
        .filter(Q(autor_id__in=usuarios_ids) | Q(privacidad='publica'))
        .select_related('autor', 'autor__perfil')
        .prefetch_related('visto_por', 'ocultar_a')
        .order_by('-creado')
    )

    historias_por_usuario = []
    agrupadas = {}
    for h in historias_qs:
        if h.autor_id != request.user.id and h.creado < desde:
            continue
        if not _puede_ver_historia(request.user, h, desde):
            continue
        bucket = agrupadas.setdefault(h.autor_id, {
            'usuario': h.autor,
            'historias': [],
            'no_vistas': 0,
        })
        bucket['historias'].append(h)

    for _, item in agrupadas.items():
        for h in item['historias']:
            if request.user != h.autor and not h.visto_por.filter(pk=request.user.pk).exists():
                item['no_vistas'] += 1
        item['ultima'] = item['historias'][0]
        historias_por_usuario.append(item)

    historias_por_usuario.sort(key=lambda x: x['ultima'].creado, reverse=True)

    contexto = {
        'user': request.user,
        'perfil': perfil_obj,
        'form_historia': form,
        'historias_por_usuario': historias_por_usuario,
    }
    return render(request, 'default-storie.html', contexto)


@login_required
def historia_detalle_api(request, historia_id):
    historia = get_object_or_404(Historia.objects.select_related('autor', 'autor__perfil'), pk=historia_id)
    desde = timezone.now() - timedelta(hours=24)
    if not _puede_ver_historia(request.user, historia, desde):
        return JsonResponse({'ok': False, 'error': 'No permitido'}, status=403)

    historias_usuario_qs = Historia.objects.filter(autor=historia.autor).order_by('creado')
    if historia.autor != request.user:
        historias_usuario_qs = historias_usuario_qs.filter(creado__gte=desde)

    historias_usuario = []
    for h in historias_usuario_qs:
        if not _puede_ver_historia(request.user, h, desde):
            continue
        archivo_url = h.archivo.url if h.archivo else ''
        lower_url = (archivo_url or '').lower().split('?', 1)[0]
        tipo_resuelto = h.tipo
        if any(lower_url.endswith(ext) for ext in ['.mp4', '.webm', '.ogg', '.mov', '.m4v', '.avi', '.mkv']):
            tipo_resuelto = 'video'
        elif any(lower_url.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.avif']):
            tipo_resuelto = 'imagen'
        historias_usuario.append({
            'id': h.id,
            'tipo': tipo_resuelto,
            'archivo_url': archivo_url,
            'texto': h.texto,
            'hora': timezone.localtime(h.creado).strftime('%H:%M'),
            'liked': h.likes.filter(pk=request.user.pk).exists(),
            'likes_total': h.num_likes(),
            'comentarios_total': h.num_comentarios(),
            'vistas_total': h.visto_por.count(),
        })

    comentarios_qs = historia.comentarios.select_related('autor', 'autor__perfil').order_by('creado')[:80]
    comentarios = []
    for c in comentarios_qs:
        comentarios.append({
            'id': c.id,
            'autor_username': c.autor.username,
            'autor_nombre': c.autor.perfil.nombre_completo(),
            'autor_foto': c.autor.perfil.foto.url if c.autor.perfil.foto else (c.autor.perfil.get_foto() or ''),
            'contenido': c.contenido,
            'creado': timezone.localtime(c.creado).strftime('%H:%M'),
        })

    vistas = []
    if historia.autor_id == request.user.id:
        for u in historia.visto_por.select_related('perfil').all()[:200]:
            vistas.append({
                'username': u.username,
                'nombre': u.perfil.nombre_completo(),
                'foto': u.perfil.foto.url if u.perfil.foto else (u.perfil.get_foto() or ''),
            })

    return JsonResponse({
        'ok': True,
        'autor_es_propietario': historia.autor_id == request.user.id,
        'autor': {
            'username': historia.autor.username,
            'nombre': historia.autor.perfil.nombre_completo(),
            'foto': historia.autor.perfil.foto.url if historia.autor.perfil.foto else (historia.autor.perfil.get_foto() or ''),
        },
        'historias': historias_usuario,
        'current_id': historia.id,
        'comentarios': comentarios,
        'vistas': vistas,
    })


@login_required
@require_POST
def marcar_historia_vista(request, historia_id):
    desde = timezone.now() - timedelta(hours=24)
    historia = get_object_or_404(Historia, pk=historia_id)
    if not _puede_ver_historia(request.user, historia, desde):
        return JsonResponse({'ok': False, 'error': 'No permitido'}, status=403)

    if historia.autor != request.user:
        historia.visto_por.add(request.user)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def like_historia(request, historia_id):
    historia = get_object_or_404(Historia, pk=historia_id)
    desde = timezone.now() - timedelta(hours=24)
    if not _puede_ver_historia(request.user, historia, desde):
        return JsonResponse({'ok': False, 'error': 'No permitido'}, status=403)

    if historia.likes.filter(pk=request.user.pk).exists():
        historia.likes.remove(request.user)
        liked = False
    else:
        historia.likes.add(request.user)
        liked = True

    from .ws_events import notificar_like_historia
    notificar_like_historia(historia, request.user)
    return JsonResponse({'ok': True, 'liked': liked, 'total': historia.num_likes()})


@login_required
@require_POST
def comentar_historia(request, historia_id):
    historia = get_object_or_404(Historia, pk=historia_id)
    desde = timezone.now() - timedelta(hours=24)
    if not _puede_ver_historia(request.user, historia, desde):
        return JsonResponse({'ok': False, 'error': 'No permitido'}, status=403)

    contenido = (request.POST.get('contenido') or '').strip()
    if not contenido:
        return JsonResponse({'ok': False, 'error': 'Comentario vacío'}, status=400)

    comentario = historia.comentarios.create(autor=request.user, contenido=contenido)
    from .ws_events import notificar_comentario_historia
    notificar_comentario_historia(comentario)
    return JsonResponse({'ok': True, 'comentario_id': comentario.id, 'total': historia.num_comentarios()})


@login_required
@require_POST
def comentar_publicacion(request, pub_id):
    pub = get_object_or_404(Publicacion, pk=pub_id)
    contenido = (request.POST.get('contenido') or '').strip()
    if not contenido:
        return JsonResponse({'ok': False, 'error': 'Comentario vacío'}, status=400)

    comentario = pub.comentarios.create(autor=request.user, contenido=contenido)
    from .ws_events import notificar_comentario_publicacion
    notificar_comentario_publicacion(comentario)
    return JsonResponse({'ok': True, 'comentario_id': comentario.id, 'total': pub.num_comentarios()})


@login_required
def obtener_comentarios_publicacion(request, pub_id):
    """Obtiene todos los comentarios de una publicación en formato JSON."""
    pub = get_object_or_404(Publicacion, pk=pub_id)
    comentarios = []
    for c in pub.comentarios.all().order_by('creado'):
        perfil, _ = Perfil.objects.get_or_create(usuario=c.autor)
        comentarios.append({
            'id': c.id,
            'autor_username': c.autor.username,
            'autor_nombre': perfil.nombre_completo(),
            'autor_foto': perfil.foto.url if perfil.foto else (perfil.get_foto() or ''),
            'contenido': c.contenido,
            'creado': c.creado.strftime('%H:%M'),
        })
    return JsonResponse({'ok': True, 'comentarios': comentarios})


@login_required
def grupos(request):
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()

        if action == 'crear_grupo':
            nombre = (request.POST.get('nombre') or '').strip()
            if nombre:
                grupo = GrupoMusical.objects.create(
                    creador=request.user,
                    nombre=nombre,
                    descripcion=(request.POST.get('descripcion') or '').strip(),
                    genero=(request.POST.get('genero') or 'otro'),
                    ciudad=(request.POST.get('ciudad') or '').strip(),
                    es_privado=(request.POST.get('es_privado') == 'on'),
                )
                GrupoMiembro.objects.get_or_create(grupo=grupo, usuario=request.user, defaults={'rol': 'admin'})

        elif action == 'crear_evento':
            titulo = (request.POST.get('titulo') or '').strip()
            fecha_raw = (request.POST.get('fecha_evento') or '').strip()
            if titulo and fecha_raw:
                try:
                    fecha_evento = timezone.make_aware(datetime.strptime(fecha_raw, '%Y-%m-%dT%H:%M'))
                    EventoMusical.objects.create(
                        creador=request.user,
                        titulo=titulo,
                        descripcion=(request.POST.get('descripcion') or '').strip(),
                        genero=(request.POST.get('genero') or 'otro'),
                        lugar=(request.POST.get('lugar') or '').strip(),
                        fecha_evento=fecha_evento,
                        cupo=int(request.POST.get('cupo')) if (request.POST.get('cupo') or '').strip().isdigit() else None,
                        es_privado=(request.POST.get('es_privado') == 'on'),
                    )
                except Exception:
                    pass

        elif action == 'unirse_grupo':
            grupo_id = request.POST.get('grupo_id')
            grupo = GrupoMusical.objects.filter(pk=grupo_id).first()
            if grupo:
                if not grupo.es_privado or InvitacionGrupo.objects.filter(grupo=grupo, invitado=request.user, estado='pendiente').exists():
                    GrupoMiembro.objects.get_or_create(grupo=grupo, usuario=request.user)

        elif action == 'unirse_evento':
            evento_id = request.POST.get('evento_id')
            evento = EventoMusical.objects.filter(pk=evento_id).first()
            if evento:
                if not evento.es_privado or InvitacionEvento.objects.filter(evento=evento, invitado=request.user, estado='pendiente').exists():
                    EventoAsistente.objects.get_or_create(evento=evento, usuario=request.user, defaults={'estado': 'asistire'})

        elif action == 'invitar_grupo':
            grupo_id = request.POST.get('grupo_id')
            username = (request.POST.get('username') or '').strip().lstrip('@')
            grupo = GrupoMusical.objects.filter(pk=grupo_id).first()
            invitado = User.objects.filter(username=username).first()
            es_admin = GrupoMiembro.objects.filter(grupo=grupo, usuario=request.user, rol='admin').exists() if grupo else False
            if grupo and invitado and invitado != request.user and es_admin:
                InvitacionGrupo.objects.get_or_create(grupo=grupo, invitador=request.user, invitado=invitado)

        elif action == 'invitar_evento':
            evento_id = request.POST.get('evento_id')
            username = (request.POST.get('username') or '').strip().lstrip('@')
            evento = EventoMusical.objects.filter(pk=evento_id).first()
            invitado = User.objects.filter(username=username).first()
            if evento and invitado and invitado != request.user and evento.creador_id == request.user.id:
                InvitacionEvento.objects.get_or_create(evento=evento, invitador=request.user, invitado=invitado)

        elif action == 'aceptar_inv_grupo':
            inv_id = request.POST.get('inv_id')
            invitacion = InvitacionGrupo.objects.filter(pk=inv_id, invitado=request.user, estado='pendiente').first()
            if invitacion:
                invitacion.estado = 'aceptada'
                invitacion.save(update_fields=['estado'])
                GrupoMiembro.objects.get_or_create(grupo=invitacion.grupo, usuario=request.user)

        elif action == 'aceptar_inv_evento':
            inv_id = request.POST.get('inv_id')
            invitacion = InvitacionEvento.objects.filter(pk=inv_id, invitado=request.user, estado='pendiente').first()
            if invitacion:
                invitacion.estado = 'aceptada'
                invitacion.save(update_fields=['estado'])
                EventoAsistente.objects.get_or_create(evento=invitacion.evento, usuario=request.user, defaults={'estado': 'asistire'})

        return redirect('grupos')

    grupos_qs = GrupoMusical.objects.select_related('creador', 'creador__perfil').prefetch_related('miembros__usuario')
    eventos_qs = EventoMusical.objects.select_related('creador', 'creador__perfil').prefetch_related('asistentes__usuario').filter(
        fecha_evento__gte=timezone.now() - timedelta(days=1)
    )

    mis_grupos_ids = set(GrupoMiembro.objects.filter(usuario=request.user).values_list('grupo_id', flat=True))
    mis_eventos_ids = set(EventoAsistente.objects.filter(usuario=request.user).values_list('evento_id', flat=True))
    mis_admin_grupos_ids = set(GrupoMiembro.objects.filter(usuario=request.user, rol='admin').values_list('grupo_id', flat=True))

    invitaciones_grupo = InvitacionGrupo.objects.filter(invitado=request.user, estado='pendiente').select_related('grupo', 'invitador')
    invitaciones_evento = InvitacionEvento.objects.filter(invitado=request.user, estado='pendiente').select_related('evento', 'invitador')

    contexto = {
        'user': request.user,
        'perfil': perfil_obj,
        'grupos': grupos_qs[:18],
        'eventos': eventos_qs[:18],
        'mis_grupos_ids': mis_grupos_ids,
        'mis_eventos_ids': mis_eventos_ids,
        'mis_admin_grupos_ids': mis_admin_grupos_ids,
        'invitaciones_grupo': invitaciones_grupo,
        'invitaciones_evento': invitaciones_evento,
        'generos': GrupoMusical.GENERO_CHOICES,
    }
    return render(request, 'default-group.html', contexto)


@login_required
def api_usuarios(request):
    from django.db.models import Count
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    offset = int(request.GET.get('offset', 0))
    limit = int(request.GET.get('limit', 6))
    usuarios = User.objects.exclude(pk=request.user.pk).annotate(
        total_seguidores=Count('perfil__seguidores')
    ).order_by('-total_seguidores')[offset:offset + limit]
    data = []
    for u in usuarios:
        p, _ = Perfil.objects.get_or_create(usuario=u)
        ya_sigo = p.seguidores.filter(pk=perfil_obj.pk).exists()
        data.append({
            'username': u.username,
            'nombre': p.nombre_completo(),
            'email': u.email,
            'foto': p.foto.url if p.foto else (p.get_foto() or ''),
            'portada': p.portada.url if p.portada else '',
            'seguidores': p.num_seguidores(),
            'siguiendo': p.num_siguiendo(),
            'ya_sigo': ya_sigo,
        })
    return JsonResponse({'usuarios': data})


@login_required
def buscar_usuarios_api(request):
    """Busca usuarios por nombre o username para el autocomplete."""
    q = (request.GET.get('q') or '').strip()
    if not q or len(q) < 1:
        return JsonResponse({'usuarios': []})
    
    # Buscar por username o nombre_completo
    usuarios = User.objects.filter(
        Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
    ).exclude(pk=request.user.pk)[:20]
    
    data = []
    for u in usuarios:
        p, _ = Perfil.objects.get_or_create(usuario=u)
        data.append({
            'username': u.username,
            'nombre': p.nombre_completo(),
            'foto': p.foto.url if p.foto else (p.get_foto() or ''),
        })
    return JsonResponse({'usuarios': data})


@login_required
def actualizar_imagen(request):
    if request.method == 'POST':
        perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
        campo = request.POST.get('campo', '')
        if campo == 'foto' and 'foto' in request.FILES:
            perfil_obj.foto = request.FILES['foto']
            perfil_obj.save()
        elif campo == 'portada' and 'portada' in request.FILES:
            perfil_obj.portada = request.FILES['portada']
            perfil_obj.save()
        from .ws_events import notificar_perfil_actualizado
        notificar_perfil_actualizado(request.user)
    return redirect('pagina_usuario', username=request.user.username)


@login_required
def pagina_usuario(request, username):
    usuario_obj = get_object_or_404(User, username=username)
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=usuario_obj)
    es_propio = (request.user == usuario_obj)
    mi_perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
    ya_sigo = perfil_obj.seguidores.filter(pk=mi_perfil.pk).exists() if not es_propio else False
    if es_propio and request.method == 'POST':
        form = EditarPerfilForm(
            request.POST, request.FILES,
            instance=perfil_obj, user=request.user
        )
        if form.is_valid():
            form.save()
            form.save_user(request.user)
            return redirect('pagina_usuario', username=request.user.username)
    else:
        form = EditarPerfilForm(instance=perfil_obj, user=request.user) if es_propio else None
    albumes = usuario_obj.albumes.all() if es_propio else usuario_obj.albumes.filter(es_publico=True)
    # Fotos: publicaciones con imagen de este usuario
    fotos = Publicacion.objects.filter(
        autor=usuario_obj
    ).exclude(imagen='').exclude(imagen__isnull=True).order_by('-creado')
    # Seguidores y siguiendo (perfiles)
    lista_seguidores = perfil_obj.seguidores.select_related('usuario').all()
    lista_siguiendo = Perfil.objects.filter(seguidores=perfil_obj).select_related('usuario')
    total_canciones = sum(a.num_canciones() for a in albumes)
    # Usernames que yo sigo (para botones Seguir/Siguiendo en la lista)
    mis_seguidos = Perfil.objects.filter(seguidores=mi_perfil).select_related('usuario')
    seguidos_usernames = [p.usuario.username for p in mis_seguidos]
    contexto = {
        'user': request.user,
        'perfil_visto': perfil_obj,
        'usuario_visto': usuario_obj,
        'es_propio': es_propio,
        'ya_sigo': ya_sigo,
        'form': form,
        'albumes': albumes,
        'fotos': fotos,
        'lista_seguidores': lista_seguidores,
        'lista_siguiendo': lista_siguiendo,
        'total_canciones': total_canciones,
        'seguidos_usernames': seguidos_usernames,
    }
    return render(request, 'user-page.html', contexto)


@login_required
def lista_seguidores(request, username):
    usuario_obj = get_object_or_404(User, username=username)
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=usuario_obj)
    mi_perfil, _ = Perfil.objects.get_or_create(usuario=request.user)

    perfiles = perfil_obj.seguidores.select_related('usuario').all()
    mis_seguidos = set(
        Perfil.objects.filter(seguidores=mi_perfil).values_list('usuario__username', flat=True)
    )

    contexto = {
        'user': request.user,
        'perfil_objetivo': perfil_obj,
        'usuario_objetivo': usuario_obj,
        'tipo_lista': 'seguidores',
        'titulo_lista': f'Seguidores de {perfil_obj.nombre_completo()}',
        'perfiles': perfiles,
        'mis_seguidos_usernames': mis_seguidos,
    }
    return render(request, 'seguidores_lista.html', contexto)


@login_required
def explorar_usuarios(request):
    """Página para explorar y buscar usuarios registrados."""
    from django.db.models import Count, Q
    mi_perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
    q = request.GET.get('q', '').strip()

    usuarios_qs = User.objects.exclude(pk=request.user.pk).select_related('perfil')
    if q:
        usuarios_qs = usuarios_qs.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )
    usuarios_qs = usuarios_qs.annotate(
        total_seguidores=Count('perfil__seguidores')
    ).order_by('-total_seguidores')

    perfiles = []
    for u in usuarios_qs[:50]:
        p, _ = Perfil.objects.get_or_create(usuario=u)
        perfiles.append(p)

    mis_seguidos = set(
        Perfil.objects.filter(seguidores=mi_perfil).values_list('usuario__username', flat=True)
    )

    return render(request, 'explorar_usuarios.html', {
        'perfiles': perfiles,
        'mis_seguidos_usernames': mis_seguidos,
        'query': q,
    })


@login_required
def lista_siguiendo(request, username):
    usuario_obj = get_object_or_404(User, username=username)
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=usuario_obj)
    mi_perfil, _ = Perfil.objects.get_or_create(usuario=request.user)

    perfiles = Perfil.objects.filter(seguidores=perfil_obj).select_related('usuario')
    mis_seguidos = set(
        Perfil.objects.filter(seguidores=mi_perfil).values_list('usuario__username', flat=True)
    )

    contexto = {
        'user': request.user,
        'perfil_objetivo': perfil_obj,
        'usuario_objetivo': usuario_obj,
        'tipo_lista': 'siguiendo',
        'titulo_lista': f'{perfil_obj.nombre_completo()} sigue a',
        'perfiles': perfiles,
        'mis_seguidos_usernames': mis_seguidos,
    }
    return render(request, 'seguidores_lista.html', contexto)


# aqui el registro de canciones y albumes 

@login_required
def mis_albumes(request):
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    albumes = request.user.albumes.all()
    contexto = {
        'user': request.user,
        'perfil': perfil_obj,
        'albumes': albumes,
    }
    return render(request, 'albumes/mis_albumes.html', contexto)


@login_required
def crear_album(request):
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    if request.method == 'POST':
        form = AlbumForm(request.POST, request.FILES)
        if form.is_valid():
            album = form.save(commit=False)
            album.artista = request.user
            album.save()
            if album.es_publico:
                from .ws_events import notificar_nuevo_album
                notificar_nuevo_album(album)
            return redirect('agregar_cancion', album_id=album.pk)
    else:
        form = AlbumForm()
    contexto = {
        'user': request.user,
        'perfil': perfil_obj,
        'form': form,
    }
    return render(request, 'albumes/crear_album.html', contexto)


@login_required
def editar_album(request, album_id):
    album = get_object_or_404(Album, pk=album_id, artista=request.user)
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    if request.method == 'POST':
        form = AlbumForm(request.POST, request.FILES, instance=album)
        if form.is_valid():
            form.save()
            return redirect('detalle_album', album_id=album.pk)
    else:
        form = AlbumForm(instance=album)
    contexto = {
        'user': request.user,
        'perfil': perfil_obj,
        'form': form,
        'album': album,
    }
    return render(request, 'albumes/editar_album.html', contexto)


@login_required
def eliminar_album(request, album_id):
    album = get_object_or_404(Album, pk=album_id, artista=request.user)
    if request.method == 'POST':
        album.delete()
        return redirect('mis_albumes')
    return redirect('detalle_album', album_id=album.pk)


def detalle_album(request, album_id):
    album = get_object_or_404(Album, pk=album_id)
    if not album.es_publico and (not request.user.is_authenticated or request.user != album.artista):
        return redirect('home')
    perfil_artista, _ = Perfil.objects.get_or_create(usuario=album.artista)
    perfil_obj = None
    if request.user.is_authenticated:
        perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    es_propietario = request.user.is_authenticated and request.user == album.artista
    cancion_form = CancionForm(initial={'numero': album.canciones.count() + 1}) if es_propietario else None
    mis_likes_canciones = set()
    if request.user.is_authenticated:
        mis_likes_canciones = set(
            Cancion.objects.filter(likes=request.user).values_list('pk', flat=True)
        )
    contexto = {
        'user': request.user,
        'perfil': perfil_obj,
        'album': album,
        'canciones': album.canciones.all(),
        'perfil_artista': perfil_artista,
        'es_propietario': es_propietario,
        'cancion_form': cancion_form,
        'mis_likes_canciones': list(mis_likes_canciones),
    }
    return render(request, 'albumes/detalle_album.html', contexto)


@login_required
def agregar_cancion(request, album_id):
    album = get_object_or_404(Album, pk=album_id, artista=request.user)
    if request.method == 'POST':
        archivos = request.FILES.getlist('archivos')
        if archivos:
            creadas = 0
            siguiente = album.canciones.count() + 1
            for i, archivo in enumerate(archivos):
                titulo = archivo.name.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title()
                cancion = Cancion(
                    album=album,
                    titulo=titulo,
                    archivo=archivo,
                    numero=siguiente + i,
                )
                cancion.save()
                creadas += 1
                try:
                    from mutagen import File as MutagenFile
                    audio = MutagenFile(cancion.archivo.path)
                    if audio and audio.info:
                        cancion.duracion = int(audio.info.length)
                    else:
                        from mutagen.mp3 import MP3
                        audio = MP3(cancion.archivo.path)
                        cancion.duracion = int(audio.info.length)
                    cancion.save(update_fields=['duracion'])
                except Exception:
                    pass
            if album.es_publico and creadas > 0:
                from .ws_events import notificar_nuevas_canciones
                notificar_nuevas_canciones(album, creadas)
            return redirect('detalle_album', album_id=album.pk)
        else:
            form = CancionForm(request.POST, request.FILES)
            if form.is_valid():
                cancion = form.save(commit=False)
                cancion.album = album
                cancion.save()
                try:
                    from mutagen import File as MutagenFile
                    audio = MutagenFile(cancion.archivo.path)
                    if audio and audio.info:
                        cancion.duracion = int(audio.info.length)
                    else:
                        from mutagen.mp3 import MP3
                        audio = MP3(cancion.archivo.path)
                        cancion.duracion = int(audio.info.length)
                    cancion.save(update_fields=['duracion'])
                except Exception:
                    pass
                if album.es_publico:
                    from .ws_events import notificar_nuevas_canciones
                    notificar_nuevas_canciones(album, 1)
                return redirect('detalle_album', album_id=album.pk)
    else:
        form = CancionForm(initial={'numero': album.canciones.count() + 1})
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    canciones_actuales = album.canciones.all()
    contexto = {
        'user': request.user,
        'perfil': perfil_obj,
        'form': form,
        'album': album,
        'canciones': canciones_actuales,
    }
    return render(request, 'albumes/agregar_cancion.html', contexto)


@login_required
def eliminar_cancion(request, cancion_id):
    cancion = get_object_or_404(Cancion, pk=cancion_id, album__artista=request.user)
    album_id = cancion.album.pk
    if request.method == 'POST':
        cancion.delete()
    return redirect('detalle_album', album_id=album_id)


@login_required
def toggle_seguir(request, username):
    usuario_objetivo = get_object_or_404(User, username=username)
    if usuario_objetivo == request.user:
        return redirect('pagina_usuario', username=username)
    mi_perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
    perfil_objetivo, _ = Perfil.objects.get_or_create(usuario=usuario_objetivo)
    if perfil_objetivo.seguidores.filter(pk=mi_perfil.pk).exists():
        perfil_objetivo.seguidores.remove(mi_perfil)
        ahora_sigue = False
    else:
        perfil_objetivo.seguidores.add(mi_perfil)
        ahora_sigue = True
    from .ws_events import notificar_follow
    notificar_follow(request.user, usuario_objetivo, ahora_sigue)
    return redirect('pagina_usuario', username=username)


# ── Vistas de Publicaciones ────────────────────────────────────────────────

@login_required
def crear_publicacion(request):
    if request.method == 'POST':
        form = PublicacionForm(request.POST, request.FILES)
        accept = (request.headers.get('Accept') or '').lower()
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in accept
        if form.is_valid():
            pub = form.save(commit=False)
            pub.autor = request.user

            def parse_extra_options(prefix):
                extras = []
                idx = 5
                while True:
                    value = (request.POST.get(f'{prefix}_opcion{idx}') or '').strip()
                    if not value:
                        break
                    extras.append(value)
                    idx += 1
                return extras

            pregunta = (request.POST.get('encuesta_pregunta') or '').strip()
            op1 = (request.POST.get('encuesta_opcion1') or '').strip()
            op2 = (request.POST.get('encuesta_opcion2') or '').strip()
            op3 = (request.POST.get('encuesta_opcion3') or '').strip()
            op4 = (request.POST.get('encuesta_opcion4') or '').strip()
            ops_extra = parse_extra_options('encuesta')

            pregunta2 = (request.POST.get('encuesta2_pregunta') or '').strip()
            op21 = (request.POST.get('encuesta2_opcion1') or '').strip()
            op22 = (request.POST.get('encuesta2_opcion2') or '').strip()
            op23 = (request.POST.get('encuesta2_opcion3') or '').strip()
            op24 = (request.POST.get('encuesta2_opcion4') or '').strip()
            ops2_extra = parse_extra_options('encuesta2')

            duracion_raw = (request.POST.get('encuesta_duracion_min') or '').strip()
            duracion = int(duracion_raw) if duracion_raw.isdigit() else 1440
            encuesta_fin = timezone.now() + timedelta(minutes=max(1, duracion))

            if pregunta:
                if not op1 or not op2:
                    if is_ajax:
                        return JsonResponse({'ok': False, 'errors': {'encuesta': [{'message': 'La encuesta requiere al menos 2 opciones.'}]}}, status=400)
                    return redirect('inicio')
                pub.encuesta_pregunta = pregunta
                pub.encuesta_opcion1 = op1
                pub.encuesta_opcion2 = op2
                pub.encuesta_opcion3 = op3
                pub.encuesta_opcion4 = op4
                pub.encuesta_opciones_extra = ops_extra
                pub.encuesta_fin = encuesta_fin

            pub.save()
            from .ws_events import notificar_nueva_publicacion
            try:
                notificar_nueva_publicacion(pub)
            except Exception:
                # Si falla el WS/notificación, no bloqueamos la publicación ya guardada.
                pass

            # Pregunta adicional: crear una publicación-encuesta extra (mismo autor) en el mismo envío.
            if pregunta2:
                if not op21 or not op22:
                    if is_ajax:
                        return JsonResponse({'ok': False, 'errors': {'encuesta2': [{'message': 'La pregunta adicional requiere al menos 2 opciones.'}]}}, status=400)
                else:
                    pub2 = Publicacion.objects.create(
                        autor=request.user,
                        contenido='',
                        encuesta_pregunta=pregunta2,
                        encuesta_opcion1=op21,
                        encuesta_opcion2=op22,
                        encuesta_opcion3=op23,
                        encuesta_opcion4=op24,
                        encuesta_opciones_extra=ops2_extra,
                        encuesta_fin=encuesta_fin,
                    )
                    try:
                        notificar_nueva_publicacion(pub2)
                    except Exception:
                        pass
            if is_ajax:
                return JsonResponse({'ok': True})
        elif is_ajax:
            errors = {f: e.get_json_data() for f, e in form.errors.items()}
            return JsonResponse({'ok': False, 'errors': errors}, status=400)
    return redirect('inicio')


@login_required
def eliminar_publicacion(request, pub_id):
    pub = Publicacion.objects.filter(pk=pub_id).first()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if not pub:
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'La publicación no existe.'}, status=404)
        return redirect('inicio')
    if pub.autor_id != request.user.id:
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'No tienes permiso para eliminar esta publicación.'}, status=403)
        return redirect('inicio')
    if request.method == 'POST':
        autor = pub.autor
        pub.delete()
        from .ws_events import notificar_publicacion_eliminada
        try:
            notificar_publicacion_eliminada(pub_id, autor)
        except Exception:
            # Si falla WS no bloqueamos la eliminación en DB.
            pass
        if is_ajax:
            return JsonResponse({'ok': True, 'pub_id': pub_id})
    return redirect('inicio')


@login_required
def editar_publicacion(request, pub_id):
    pub = get_object_or_404(Publicacion, pk=pub_id, autor=request.user)

    if request.method == 'GET':
        encuesta_fin_iso = ''
        encuesta_duracion_min = 1440
        if pub.encuesta_fin:
            encuesta_fin_iso = timezone.localtime(pub.encuesta_fin).isoformat()
            remaining = int((pub.encuesta_fin - timezone.now()).total_seconds() / 60)
            if remaining > 0:
                allowed_durations = [30, 60, 180, 720, 1440, 4320]
                encuesta_duracion_min = min(allowed_durations, key=lambda x: abs(x - remaining))
        return JsonResponse({
            'ok': True,
            'pub_id': pub.id,
            'contenido': pub.contenido,
            'imagen': pub.imagen.url if pub.imagen else '',
            'encuesta': {
                'tiene': pub.tiene_encuesta(),
                'pregunta': pub.encuesta_pregunta,
                'opciones': pub.encuesta_opciones(),
                'encuesta_fin': encuesta_fin_iso,
                'encuesta_duracion_min': encuesta_duracion_min,
            },
        })

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)

    contenido = (request.POST.get('contenido') or '').strip()

    def parse_extra_options(prefix):
        extras = []
        idx = 5
        while True:
            value = (request.POST.get(f'{prefix}_opcion{idx}') or '').strip()
            if not value:
                break
            extras.append(value)
            idx += 1
        return extras

    pregunta = (request.POST.get('encuesta_pregunta') or '').strip()
    op1 = (request.POST.get('encuesta_opcion1') or '').strip()
    op2 = (request.POST.get('encuesta_opcion2') or '').strip()
    op3 = (request.POST.get('encuesta_opcion3') or '').strip()
    op4 = (request.POST.get('encuesta_opcion4') or '').strip()
    ops_extra = parse_extra_options('encuesta')
    remove_encuesta = (request.POST.get('remove_encuesta') or '').strip() in ('1', 'true', 'on')
    duracion_raw = (request.POST.get('encuesta_duracion_min') or '').strip()
    duracion = int(duracion_raw) if duracion_raw.isdigit() else 1440
    encuesta_fin = timezone.now() + timedelta(minutes=max(1, duracion))
    eliminar_imagen = (request.POST.get('eliminar_imagen') or '').strip() in ('1', 'true', 'on')
    nueva_imagen = request.FILES.get('imagen')

    # Aplicar cambios de imagen antes de validar contenido mínimo.
    if eliminar_imagen and pub.imagen and not nueva_imagen:
        pub.imagen.delete(save=False)
        pub.imagen = None
    if nueva_imagen:
        pub.imagen = nueva_imagen

    tiene_imagen = bool(pub.imagen)

    if not contenido and not tiene_imagen and not pub.tiene_encuesta() and not (pregunta and op1 and op2) and not remove_encuesta:
        return JsonResponse({'ok': False, 'error': 'La publicación no puede quedar vacía.'}, status=400)

    pub.contenido = contenido

    if remove_encuesta:
        pub.encuesta_pregunta = ''
        pub.encuesta_opcion1 = ''
        pub.encuesta_opcion2 = ''
        pub.encuesta_opcion3 = ''
        pub.encuesta_opcion4 = ''
        pub.encuesta_opciones_extra = []
        pub.encuesta_fin = None
        pub.encuesta_votos.all().delete()
    else:
        # Si se envía encuesta, actualizarla también.
        if pregunta or pub.tiene_encuesta():
            if not pregunta or not op1 or not op2:
                return JsonResponse({'ok': False, 'error': 'La encuesta requiere pregunta y al menos 2 opciones.'}, status=400)
            pub.encuesta_pregunta = pregunta
            pub.encuesta_opcion1 = op1
            pub.encuesta_opcion2 = op2
            pub.encuesta_opcion3 = op3
            pub.encuesta_opcion4 = op4
            pub.encuesta_opciones_extra = ops_extra
            pub.encuesta_fin = encuesta_fin

    pub.save()

    total = pub.encuesta_total_votos() if pub.tiene_encuesta() else 0
    resultados = []
    if pub.tiene_encuesta():
        for idx, texto in enumerate(pub.encuesta_opciones(), start=1):
            votos = pub.encuesta_votos_opcion(idx)
            porcentaje = round((votos * 100.0 / total), 1) if total else 0
            resultados.append({'opcion': idx, 'texto': texto, 'votos': votos, 'porcentaje': porcentaje})

    return JsonResponse({
        'ok': True,
        'pub_id': pub_id,
        'contenido': pub.contenido,
        'imagen': pub.imagen.url if pub.imagen else '',
        'encuesta': {
            'tiene': pub.tiene_encuesta(),
            'pregunta': pub.encuesta_pregunta,
            'opciones': pub.encuesta_opciones(),
            'resultados': resultados,
            'total_votos': total,
            'encuesta_fin': timezone.localtime(pub.encuesta_fin).isoformat() if pub.encuesta_fin else '',
            'encuesta_duracion_min': duracion if pub.tiene_encuesta() else 0,
        },
    })


@login_required
def like_publicacion(request, pub_id):
    pub = get_object_or_404(Publicacion, pk=pub_id)
    if pub.likes.filter(pk=request.user.pk).exists():
        pub.likes.remove(request.user)
        liked = False
    else:
        pub.likes.add(request.user)
        liked = True
    total = pub.num_likes()
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    from .ws_events import notificar_like
    notificar_like('publicacion', pub_id, total,
                   perfil_obj.foto.url if perfil_obj.foto else (perfil_obj.get_foto() or ''),
                   request.user.username)
    return JsonResponse({'liked': liked, 'total': total})


@login_required
@require_POST
def votar_encuesta_publicacion(request, pub_id):
    pub = get_object_or_404(Publicacion, pk=pub_id)
    if not pub.tiene_encuesta():
        return JsonResponse({'ok': False, 'error': 'Esta publicación no tiene encuesta.'}, status=400)
    if pub.encuesta_expirada:
        return JsonResponse({'ok': False, 'error': 'La encuesta ya finalizó.'}, status=400)

    opcion_raw = (request.POST.get('opcion') or '').strip()
    if not opcion_raw.isdigit():
        return JsonResponse({'ok': False, 'error': 'Opción inválida.'}, status=400)

    opcion = int(opcion_raw)
    opciones = pub.encuesta_opciones()
    if opcion < 1 or opcion > len(opciones):
        return JsonResponse({'ok': False, 'error': 'Opción inválida.'}, status=400)

    PublicacionEncuestaVoto.objects.update_or_create(
        publicacion=pub,
        usuario=request.user,
        defaults={'opcion': opcion},
    )

    total = pub.encuesta_total_votos()
    resultados = []
    for idx, texto in enumerate(opciones, start=1):
        votos = pub.encuesta_votos_opcion(idx)
        porcentaje = round((votos * 100.0 / total), 1) if total else 0
        resultados.append({'opcion': idx, 'texto': texto, 'votos': votos, 'porcentaje': porcentaje})

    votos_detalle = []
    votos_qs = pub.encuesta_votos.select_related('usuario', 'usuario__perfil').order_by('-creado')
    for v in votos_qs:
        perfil_v, _ = Perfil.objects.get_or_create(usuario=v.usuario)
        texto_opcion = opciones[v.opcion - 1] if 1 <= v.opcion <= len(opciones) else f'Opción {v.opcion}'
        votos_detalle.append({
            'username': v.usuario.username,
            'nombre': perfil_v.nombre_completo(),
            'foto': perfil_v.foto.url if perfil_v.foto else (perfil_v.get_foto() or ''),
            'opcion': v.opcion,
            'opcion_texto': texto_opcion,
        })

    from .ws_events import notificar_voto_encuesta_publicacion
    try:
        notificar_voto_encuesta_publicacion(pub, resultados, total, opcion, votos_detalle, request.user)
    except Exception:
        pass

    return JsonResponse({
        'ok': True,
        'pub_id': pub.id,
        'total_votos': total,
        'mi_voto': opcion,
        'resultados': resultados,
        'votos_detalle': votos_detalle,
    })


@login_required
def like_album(request, album_id):
    album = get_object_or_404(Album, pk=album_id)
    if album.likes.filter(pk=request.user.pk).exists():
        album.likes.remove(request.user)
        liked = False
    else:
        album.likes.add(request.user)
        liked = True
    total = album.num_likes()
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    from .ws_events import notificar_like
    notificar_like('album', album_id, total,
                   perfil_obj.foto.url if perfil_obj.foto else (perfil_obj.get_foto() or ''),
                   request.user.username)
    return JsonResponse({'liked': liked, 'total': total})


@login_required
def like_cancion(request, cancion_id):
    cancion = get_object_or_404(Cancion, pk=cancion_id)
    if cancion.likes.filter(pk=request.user.pk).exists():
        cancion.likes.remove(request.user)
        liked = False
    else:
        cancion.likes.add(request.user)
        liked = True
    total = cancion.num_likes()
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    from .ws_events import notificar_like
    notificar_like('cancion', cancion_id, total,
                   perfil_obj.foto.url if perfil_obj.foto else (perfil_obj.get_foto() or ''),
                   request.user.username)
    return JsonResponse({'liked': liked, 'total': total})


# ── Vistas de Notificaciones ───────────────────────────────────────────────

@login_required
def pagina_notificaciones(request):
    from .models import Notificacion
    notifs = (
        Notificacion.objects
        .filter(destinatario=request.user)
        .select_related('remitente', 'remitente__perfil')
        .order_by('-creado')[:50]
    )
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    return render(request, 'default-notification.html', {
        'notificaciones': notifs,
        'perfil': perfil_obj,
    })


@login_required
def marcar_notificaciones_leidas(request):
    if request.method != 'POST':
        return redirect('notificaciones')

    from .models import Notificacion
    Notificacion.objects.filter(destinatario=request.user, leida=False).update(leida=True)

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        return JsonResponse({'ok': True})
    return redirect('notificaciones')


@login_required
def abrir_notificacion(request, notif_id):
    from .models import Notificacion

    notif = get_object_or_404(Notificacion, pk=notif_id, destinatario=request.user)
    if not notif.leida:
        notif.leida = True
        notif.save(update_fields=['leida'])
    return redirect(notif.url or 'notificaciones')


@login_required
@require_POST
def guardar_preferencias(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    prefs, _ = PreferenciasUsuario.objects.get_or_create(usuario=request.user)
    if 'color_tema' in data:
        colores_validos = [c[0] for c in PreferenciasUsuario.COLORES]
        if data['color_tema'] in colores_validos:
            prefs.color_tema = data['color_tema']
    if 'modo_oscuro' in data:
        prefs.modo_oscuro = bool(data['modo_oscuro'])
    if 'fondo_header' in data:
        prefs.fondo_header = bool(data['fondo_header'])
    if 'menu_lateral' in data:
        prefs.menu_lateral = bool(data['menu_lateral'])
    prefs.save()
    return JsonResponse({'ok': True})


def _chat_room_group(user_a, user_b):
    nombres = sorted([user_a.username, user_b.username])
    return 'chat___' + '__'.join(nombres)


def _detectar_tipo_archivo(file_obj):
    content_type = (getattr(file_obj, 'content_type', '') or '').lower()
    if content_type.startswith('image/'):
        return 'imagen'
    if content_type.startswith('video/'):
        return 'video'
    if content_type.startswith('audio/'):
        return 'audio'
    return 'archivo'


@login_required
def chat_enviar_adjunto(request, username):
    from .models import MensajeChat

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    otro = get_object_or_404(User, username=username)
    if otro == request.user:
        return JsonResponse({'ok': False, 'error': 'No permitido'}, status=400)

    texto = (request.POST.get('mensaje') or '').strip()
    archivo = request.FILES.get('archivo')
    if not texto and not archivo:
        return JsonResponse({'ok': False, 'error': 'Mensaje vacío'}, status=400)

    tipo = _detectar_tipo_archivo(archivo) if archivo else 'texto'
    mensaje = MensajeChat.objects.create(
        emisor=request.user,
        receptor=otro,
        contenido=texto,
        tipo=tipo,
        archivo=archivo if archivo else None,
    )

    try:
        emisor_foto = request.user.perfil.get_foto() or ''
        emisor_nombre = request.user.perfil.nombre_completo()
    except Exception:
        emisor_foto = ''
        emisor_nombre = request.user.username

    payload = {
        'event': 'mensaje',
        'id': mensaje.pk,
        'emisor': request.user.username,
        'emisor_id': request.user.id,
        'mensaje': mensaje.contenido,
        'tipo': mensaje.tipo,
        'archivo_url': mensaje.archivo.url if mensaje.archivo else '',
        'archivo_nombre': mensaje.archivo.name.split('/')[-1] if mensaje.archivo else '',
        'enviado': timezone.localtime(mensaje.enviado).strftime('%H:%M'),
        'emisor_foto': emisor_foto,
    }

    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(_chat_room_group(request.user, otro), {
            'type': 'chat_message',
            'data': payload,
        })
        async_to_sync(layer.group_send)(f'user_{otro.id}', {
            'type': 'notificacion',
            'data': {
                'event': 'chat_mensaje',
                'emisor': request.user.username,
                'emisor_id': request.user.id,
                'emisor_nombre': emisor_nombre,
                'emisor_foto': emisor_foto,
                'mensaje': texto or f'[{mensaje.get_tipo_display()}]',
                'url': f'/chat/{request.user.username}/',
            },
        })

    return JsonResponse({'ok': True, 'mensaje': payload})


# ── Vistas de Chat ────────────────────────────────────────────────────────

@login_required
def chat_inbox(request):
    """Bandeja de entrada del chat — lista de conversaciones."""
    from .models import MensajeChat
    from django.db.models import Q

    mensajes = (
        MensajeChat.objects
        .filter(Q(emisor=request.user) | Q(receptor=request.user))
        .order_by('-enviado')
        .select_related('emisor', 'emisor__perfil', 'receptor', 'receptor__perfil')
    )
    # Agrupar por contacto (una sola entrada por conversación)
    contactos_vistos = {}
    for msg in mensajes:
        otro = msg.receptor if msg.emisor == request.user else msg.emisor
        if otro.id not in contactos_vistos:
            no_leidos = MensajeChat.objects.filter(
                emisor=otro, receptor=request.user, leido=False
            ).count()
            contactos_vistos[otro.id] = {
                'usuario': otro,
                'ultimo_mensaje': msg,
                'no_leidos': no_leidos,
            }
        if len(contactos_vistos) >= 30:
            break

    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    return render(request, 'chat.html', {
        'conversaciones': list(contactos_vistos.values()),
        'perfil': perfil_obj,
    })


@login_required
def chat_conversacion(request, username):
    """Página de conversación con un usuario específico."""
    from .models import MensajeChat
    from django.db.models import Q

    otro_user = get_object_or_404(User, username=username)
    if otro_user == request.user:
        return redirect('chat_inbox')

    # Marcar como leídos los mensajes recibidos
    MensajeChat.objects.filter(
        emisor=otro_user, receptor=request.user, leido=False
    ).update(leido=True)

    mensajes = (
        MensajeChat.objects
        .filter(
            Q(emisor=request.user, receptor=otro_user) |
            Q(emisor=otro_user, receptor=request.user)
        )
        .order_by('enviado')
        .select_related('emisor')[:200]
    )

    try:
        otro_perfil = otro_user.perfil
    except Exception:
        otro_perfil = Perfil.objects.get_or_create(usuario=otro_user)[0]

    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    return render(request, 'chat_conversacion.html', {
        'otro_usuario': otro_user,
        'otro_perfil': otro_perfil,
        'mensajes': mensajes,
        'perfil': perfil_obj,
    })


@login_required
def chat_historial_api(request, username):
    """API JSON: últimos mensajes con un usuario (para el popup de chat)."""
    from .models import MensajeChat
    from django.db.models import Q

    otro = get_object_or_404(User, username=username)
    # Marcar como leídos al cargar
    MensajeChat.objects.filter(
        emisor=otro, receptor=request.user, leido=False
    ).update(leido=True)

    mensajes = (
        MensajeChat.objects
        .filter(
            Q(emisor=request.user, receptor=otro) |
            Q(emisor=otro, receptor=request.user)
        )
        .order_by('enviado')
        .select_related('emisor')[:100]
    )
    return JsonResponse({
        'mensajes': [
            {
                'id': m.pk,
                'emisor': m.emisor.username,
                'mensaje': m.contenido,
                'tipo': m.tipo,
                'archivo_url': m.archivo.url if m.archivo else '',
                'archivo_nombre': m.archivo.name.split('/')[-1] if m.archivo else '',
                'enviado': timezone.localtime(m.enviado).strftime('%H:%M'),
                'soy_yo': m.emisor_id == request.user.id,
            }
            for m in mensajes
        ]
    })


@login_required
def buscar_usuarios_api(request):
    """API JSON: busca usuarios por nombre/username para el dropdown de chat nuevo."""
    q = request.GET.get('q', '').strip()
    if len(q) < 1:
        return JsonResponse({'usuarios': []})
    from django.db.models import Q as DQ

    scope_tipo = (request.GET.get('tipo') or '').strip().lower()
    scope_id = (request.GET.get('id') or '').strip()

    usuarios = (
        User.objects
        .filter(
            DQ(username__icontains=q) | DQ(first_name__icontains=q) | DQ(last_name__icontains=q)
        )
        .exclude(pk=request.user.pk)
        .select_related('perfil')
    )

    if scope_tipo == 'grupo' and scope_id.isdigit():
        grupo = GrupoMusical.objects.filter(pk=int(scope_id)).first()
        es_admin = GrupoMiembro.objects.filter(grupo=grupo, usuario=request.user, rol='admin').exists() if grupo else False
        if not grupo or not es_admin:
            return JsonResponse({'usuarios': []})

        ids_miembros = GrupoMiembro.objects.filter(grupo=grupo).values_list('usuario_id', flat=True)
        ids_invitados = InvitacionGrupo.objects.filter(grupo=grupo, estado='pendiente').values_list('invitado_id', flat=True)
        usuarios = usuarios.exclude(pk__in=ids_miembros).exclude(pk__in=ids_invitados)

    elif scope_tipo == 'evento' and scope_id.isdigit():
        evento = EventoMusical.objects.filter(pk=int(scope_id)).first()
        if not evento or evento.creador_id != request.user.id:
            return JsonResponse({'usuarios': []})

        ids_asistentes = EventoAsistente.objects.filter(evento=evento).values_list('usuario_id', flat=True)
        ids_invitados = InvitacionEvento.objects.filter(evento=evento, estado='pendiente').values_list('invitado_id', flat=True)
        usuarios = usuarios.exclude(pk__in=ids_asistentes).exclude(pk__in=ids_invitados)

    usuarios = usuarios[:12]

    result = []
    for u in usuarios:
        try:
            foto = u.perfil.get_foto() or ''
            nombre = u.perfil.nombre_completo()
        except Exception:
            foto = ''
            nombre = u.username
        result.append({'username': u.username, 'nombre': nombre, 'foto': foto})
    return JsonResponse({'usuarios': result})
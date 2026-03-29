from datetime import timedelta

from django.utils import timezone

from .models import Notificacion


def notificaciones_ctx(request):
    """Inyecta notificaciones, contactos y estado online en todos los templates."""
    if not request.user.is_authenticated:
        return {}

    from .models import MensajeChat, Perfil, Historia
    from django.contrib.auth.models import User

    # ── Notificaciones ──────────────────────────────────────────────────
    notifs = (
        Notificacion.objects
        .filter(destinatario=request.user)
        .select_related('remitente', 'remitente__perfil')
        .order_by('-creado')[:10]
    )
    no_leidas = Notificacion.objects.filter(
        destinatario=request.user, leida=False
    ).count()

    # ── Usuarios online ──────────────────────────────────────────────────
    try:
        from .consumers import _ONLINE_USERS
        online_ids = set(_ONLINE_USERS.keys())
    except Exception:
        online_ids = set()

    # ── Contactos sidebar (seguidos + seguidores) ────────────────────────
    contactos_sidebar = []
    usuarios_sugeridos = []
    try:
        mi_perfil = request.user.perfil
        # Usuarios que yo sigo (perfiles que tienen mi_perfil en sus seguidores)
        siguiendo_ids = set(
            Perfil.objects.filter(seguidores=mi_perfil)
            .values_list('usuario_id', flat=True)
        )
        # Usuarios que me siguen
        seguidores_ids = set(
            mi_perfil.seguidores
            .values_list('usuario__id', flat=True)
        )
        contactos_ids = list((siguiendo_ids | seguidores_ids) - {request.user.id})[:20]
        contactos_usuarios = (
            User.objects
            .filter(id__in=contactos_ids)
            .select_related('perfil')
        )
        contactos_sidebar = sorted(
            [{'usuario': u, 'online': u.id in online_ids} for u in contactos_usuarios],
            key=lambda c: not c['online'],
        )
        # Usuarios sugeridos: no los sigo ni me siguen, max 5
        from django.db.models import Count
        excluir_ids = (siguiendo_ids | seguidores_ids | {request.user.id})
        usuarios_sugeridos = list(
            User.objects
            .exclude(id__in=excluir_ids)
            .select_related('perfil')
            .annotate(total_seg=Count('perfil__seguidores'))
            .order_by('-total_seg')[:5]
        )
    except Exception:
        pass

    # ── Mensajes no leídos ───────────────────────────────────────────────
    try:
        mensajes_no_leidos = MensajeChat.objects.filter(
            receptor=request.user, leido=False
        ).count()
    except Exception:
        mensajes_no_leidos = 0

    # ── Conversaciones recientes (para dropdown en navbar) ───────────────
    conversaciones_recientes = []
    try:
        from django.db.models import Q, Max
        # Obtener IDs de los últimos interlocutores con quien se ha chateado
        mensajes_recientes = (
            MensajeChat.objects
            .filter(Q(emisor=request.user) | Q(receptor=request.user))
            .order_by('-enviado')
        )
        seen = {}
        for msg in mensajes_recientes:
            partner = msg.receptor if msg.emisor == request.user else msg.emisor
            if partner.id not in seen:
                no_leidos_conv = MensajeChat.objects.filter(
                    emisor=partner, receptor=request.user, leido=False
                ).count()
                seen[partner.id] = {
                    'usuario': partner,
                    'online': partner.id in online_ids,
                    'ultimo_mensaje': msg.contenido,
                    'no_leidos': no_leidos_conv,
                }
            if len(seen) >= 6:
                break
        conversaciones_recientes = list(seen.values())
    except Exception:
        pass

    # ── Historias activas (24h) para modal global ─────────────────────────
    historias_preview = []
    try:
        limite = timezone.now() - timedelta(hours=24)
        mi_perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
        siguiendo_ids = list(
            Perfil.objects.filter(seguidores=mi_perfil).values_list('usuario_id', flat=True)
        )
        usuarios_ids = set(siguiendo_ids + [request.user.id])
        base_qs = (
            Historia.objects
            .filter(autor_id__in=usuarios_ids)
            .select_related('autor', 'autor__perfil')
            .order_by('-creado')
        )
        historias_preview = []
        for h in base_qs:
            if h.autor_id != request.user.id and h.creado < limite:
                continue
            historias_preview.append(h)
            if len(historias_preview) >= 10:
                break
    except Exception:
        pass

    return {
        'notificaciones_dropdown': notifs,
        'notificaciones_no_leidas': no_leidas,
        'contactos_sidebar': contactos_sidebar,
        'contactos_online_count': sum(1 for c in contactos_sidebar if c['online']),
        'usuarios_sugeridos': usuarios_sugeridos,
        'online_users_ids': online_ids,
        'mensajes_no_leidos': mensajes_no_leidos,
        'conversaciones_recientes': conversaciones_recientes,
        'historias_preview': historias_preview,
        'user_prefs': _get_prefs(request.user),
    }


def _get_prefs(user):
    from .models import PreferenciasUsuario
    prefs, _ = PreferenciasUsuario.objects.get_or_create(usuario=user)
    return prefs

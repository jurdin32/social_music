from django.urls import path
from . import views

urlpatterns = [
    path('verificacion-exitosa/', views.verificacion_exitosa, name='verificacion_exitosa'),
    path('', views.home, name='home'),
    path('inicio/', views.inicio, name='inicio'),
    path('perfil/', views.perfil, name='perfil'),
    path('perfil/editar/', views.editar_perfil, name='editar_perfil'),
    path('perfil/imagen/', views.actualizar_imagen, name='actualizar_imagen'),
    path('insignias/', views.insignias, name='insignias'),
    path('historias/', views.historias, name='historias'),
    path('historias/<int:historia_id>/detalle/', views.historia_detalle_api, name='historia_detalle_api'),
    path('historias/<int:historia_id>/vista/', views.marcar_historia_vista, name='marcar_historia_vista'),
    path('historias/<int:historia_id>/like/', views.like_historia, name='like_historia'),
    path('historias/<int:historia_id>/comentar/', views.comentar_historia, name='comentar_historia'),
    path('grupos/', views.grupos, name='grupos'),
    path('usuario/<str:username>/', views.pagina_usuario, name='pagina_usuario'),   
    path('usuario/<str:username>/seguidores/', views.lista_seguidores, name='lista_seguidores'),
    path('usuario/<str:username>/siguiendo/', views.lista_siguiendo, name='lista_siguiendo'),
    # Álbumes
    path('albumes/', views.mis_albumes, name='mis_albumes'),
    path('albumes/crear/', views.crear_album, name='crear_album'),
    path('albumes/<int:album_id>/', views.detalle_album, name='detalle_album'),
    path('albumes/<int:album_id>/editar/', views.editar_album, name='editar_album'),
    path('albumes/<int:album_id>/eliminar/', views.eliminar_album, name='eliminar_album'),
    path('albumes/<int:album_id>/canciones/agregar/', views.agregar_cancion, name='agregar_cancion'),
    path('canciones/<int:cancion_id>/eliminar/', views.eliminar_cancion, name='eliminar_cancion'),
    path('usuario/<str:username>/seguir/', views.toggle_seguir, name='toggle_seguir'),
    path('explorar/', views.explorar_usuarios, name='explorar_usuarios'),
    path('api/usuarios/', views.api_usuarios, name='api_usuarios'),
    # Publicaciones
    path('publicaciones/crear/', views.crear_publicacion, name='crear_publicacion'),
    path('publicaciones/<int:pub_id>/editar/', views.editar_publicacion, name='editar_publicacion'),
    path('publicaciones/<int:pub_id>/eliminar/', views.eliminar_publicacion, name='eliminar_publicacion'),
    path('publicaciones/<int:pub_id>/like/', views.like_publicacion, name='like_publicacion'),
    path('publicaciones/<int:pub_id>/encuesta/votar/', views.votar_encuesta_publicacion, name='votar_encuesta_publicacion'),
    path('publicaciones/<int:pub_id>/comentar/', views.comentar_publicacion, name='comentar_publicacion'),
    path('publicaciones/<int:pub_id>/comentarios/', views.obtener_comentarios_publicacion, name='obtener_comentarios_publicacion'),
    path('albumes/<int:album_id>/like/', views.like_album, name='like_album'),
    path('canciones/<int:cancion_id>/like/', views.like_cancion, name='like_cancion'),
    # Notificaciones
    path('notificaciones/', views.pagina_notificaciones, name='notificaciones'),
    path('notificaciones/marcar-leidas/', views.marcar_notificaciones_leidas, name='marcar_notificaciones_leidas'),
    path('notificaciones/abrir/<int:notif_id>/', views.abrir_notificacion, name='abrir_notificacion'),
    path('preferencias/guardar/', views.guardar_preferencias, name='guardar_preferencias'),
    # Chat
    path('chat/', views.chat_inbox, name='chat_inbox'),
    path('chat/historial/<str:username>/', views.chat_historial_api, name='chat_historial_api'),
    path('chat/enviar-adjunto/<str:username>/', views.chat_enviar_adjunto, name='chat_enviar_adjunto'),
    path('chat/<str:username>/', views.chat_conversacion, name='chat_conversacion'),
    # Búsqueda de usuarios para chat
    path('usuarios/buscar/', views.buscar_usuarios_api, name='buscar_usuarios_api'),
]

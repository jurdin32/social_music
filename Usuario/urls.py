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
    path('grupos/', views.grupos, name='grupos'),
    path('usuario/<str:username>/', views.pagina_usuario, name='pagina_usuario'),   
    # Álbumes
    path('albumes/', views.mis_albumes, name='mis_albumes'),
    path('albumes/crear/', views.crear_album, name='crear_album'),
    path('albumes/<int:album_id>/', views.detalle_album, name='detalle_album'),
    path('albumes/<int:album_id>/editar/', views.editar_album, name='editar_album'),
    path('albumes/<int:album_id>/eliminar/', views.eliminar_album, name='eliminar_album'),
    path('albumes/<int:album_id>/canciones/agregar/', views.agregar_cancion, name='agregar_cancion'),
    path('canciones/<int:cancion_id>/eliminar/', views.eliminar_cancion, name='eliminar_cancion'),
]

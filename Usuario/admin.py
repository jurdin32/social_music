from django.contrib import admin
from .models import (
    Perfil, Album, Cancion, Historia, ComentarioPublicacion, ComentarioHistoria,
    GrupoMusical, GrupoMiembro, EventoMusical, EventoAsistente, InvitacionGrupo, InvitacionEvento,
    PublicacionEncuestaVoto,
)


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display  = ('usuario', 'nombre_completo', 'ubicacion', 'ocupacion', 'es_privado')
    search_fields = ('usuario__email', 'usuario__first_name', 'usuario__last_name', 'ubicacion')
    list_filter   = ('es_privado',)
    raw_id_fields = ('usuario',)


class CancionInline(admin.TabularInline):
    model = Cancion
    extra = 1


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display  = ('titulo', 'artista', 'genero', 'num_canciones', 'es_publico', 'creado')
    list_filter   = ('genero', 'es_publico')
    search_fields = ('titulo', 'artista__username', 'artista__first_name')
    raw_id_fields = ('artista',)
    inlines       = [CancionInline]


@admin.register(Historia)
class HistoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'autor', 'tipo', 'creado')
    list_filter = ('tipo', 'creado')
    search_fields = ('autor__username', 'autor__first_name', 'texto')
    raw_id_fields = ('autor',)


@admin.register(ComentarioPublicacion)
class ComentarioPublicacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'publicacion', 'autor', 'creado')
    list_filter = ('creado',)
    search_fields = ('contenido', 'autor__username', 'publicacion__id')


@admin.register(ComentarioHistoria)
class ComentarioHistoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'historia', 'autor', 'creado')
    list_filter = ('creado',)
    search_fields = ('contenido', 'autor__username', 'historia__id')


@admin.register(GrupoMusical)
class GrupoMusicalAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'creador', 'genero', 'es_privado', 'creado')
    list_filter = ('genero', 'es_privado', 'creado')
    search_fields = ('nombre', 'creador__username', 'ciudad')


@admin.register(GrupoMiembro)
class GrupoMiembroAdmin(admin.ModelAdmin):
    list_display = ('id', 'grupo', 'usuario', 'rol', 'unido_en')
    list_filter = ('rol', 'unido_en')
    search_fields = ('grupo__nombre', 'usuario__username')


@admin.register(EventoMusical)
class EventoMusicalAdmin(admin.ModelAdmin):
    list_display = ('id', 'titulo', 'creador', 'genero', 'fecha_evento', 'es_privado')
    list_filter = ('genero', 'es_privado', 'fecha_evento')
    search_fields = ('titulo', 'creador__username', 'lugar')


@admin.register(EventoAsistente)
class EventoAsistenteAdmin(admin.ModelAdmin):
    list_display = ('id', 'evento', 'usuario', 'estado', 'unido_en')
    list_filter = ('estado', 'unido_en')
    search_fields = ('evento__titulo', 'usuario__username')


@admin.register(InvitacionGrupo)
class InvitacionGrupoAdmin(admin.ModelAdmin):
    list_display = ('id', 'grupo', 'invitador', 'invitado', 'estado', 'creado')
    list_filter = ('estado', 'creado')
    search_fields = ('grupo__nombre', 'invitador__username', 'invitado__username')


@admin.register(InvitacionEvento)
class InvitacionEventoAdmin(admin.ModelAdmin):
    list_display = ('id', 'evento', 'invitador', 'invitado', 'estado', 'creado')
    list_filter = ('estado', 'creado')
    search_fields = ('evento__titulo', 'invitador__username', 'invitado__username')


@admin.register(PublicacionEncuestaVoto)
class PublicacionEncuestaVotoAdmin(admin.ModelAdmin):
    list_display = ('id', 'publicacion', 'usuario', 'opcion', 'creado')
    list_filter = ('opcion', 'creado')
    search_fields = ('publicacion__id', 'usuario__username')

from django.contrib import admin
from .models import Perfil, Album, Cancion


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

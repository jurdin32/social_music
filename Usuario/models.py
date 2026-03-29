from datetime import timedelta
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from PIL import Image


# Tamaños finales aplicados automáticamente al guardar
FOTO_SIZE    = (300, 300)   # cuadrado
PORTADA_SIZE = (1200, 400)  # banner panorámico


def _recortar_centrado(imagen_pil, ancho, alto):
    """Recorta y redimensiona manteniendo proporciones (crop centrado)."""
    img = imagen_pil.convert('RGB')
    ratio_objetivo = ancho / alto
    ratio_actual   = img.width / img.height

    if ratio_actual > ratio_objetivo:
        # La imagen es más ancha → recortamos los lados
        nuevo_ancho = int(img.height * ratio_objetivo)
        offset = (img.width - nuevo_ancho) // 2
        img = img.crop((offset, 0, offset + nuevo_ancho, img.height))
    else:
        # La imagen es más alta → recortamos arriba y abajo
        nuevo_alto = int(img.width / ratio_objetivo)
        offset = (img.height - nuevo_alto) // 2
        img = img.crop((0, offset, img.width, offset + nuevo_alto))

    img = img.resize((ancho, alto), Image.LANCZOS)
    return img


class Perfil(models.Model):
    usuario   = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    foto      = models.ImageField(upload_to='perfiles/', blank=True, null=True)
    portada   = models.ImageField(upload_to='portadas/', blank=True, null=True)
    bio       = models.TextField(blank=True, max_length=500, default='')
    ubicacion = models.CharField(max_length=100, blank=True, default='')
    sitio_web = models.URLField(blank=True, default='')
    ocupacion = models.CharField(max_length=100, blank=True, default='')
    es_privado = models.BooleanField(default=False)
    seguidores = models.ManyToManyField(
        'self', symmetrical=False, related_name='siguiendo_a', blank=True
    )
    amigos_cercanos = models.ManyToManyField(
        User, related_name='en_lista_amigos_cercanos', blank=True
    )

    # ── Helpers ────────────────────────────────────────────────────────────

    def get_foto(self):
        if self.foto:
            return self.foto.url
        try:
            social = self.usuario.socialaccount_set.first()
            if social:
                return social.get_avatar_url()
        except Exception:
            pass
        return None

    def get_portada(self):
        return self.portada.url if self.portada else None

    def nombre_completo(self):
        nombre = self.usuario.get_full_name().strip()
        return nombre if nombre else self.usuario.email.split('@')[0]

    def num_seguidores(self):
        return self.seguidores.count()

    def num_siguiendo(self):
        return Perfil.objects.filter(seguidores=self).count()

    def __str__(self):
        return f'Perfil de {self.nombre_completo()}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._procesar_imagen('foto', FOTO_SIZE)
        self._procesar_imagen('portada', PORTADA_SIZE)

    def _procesar_imagen(self, campo, size):
        field = getattr(self, campo)
        if not field:
            return
        try:
            img = Image.open(field.path)
            if img.width != size[0] or img.height != size[1]:
                img_proc = _recortar_centrado(img, size[0], size[1])
                buffer = BytesIO()
                img_proc.save(buffer, format='JPEG', quality=90)
                field.save(field.name, ContentFile(buffer.getvalue()), save=False)
                # save=False para no entrar en bucle; actualizamos campo directamente
                Perfil.objects.filter(pk=self.pk).update(**{campo: field.name})
        except Exception:
            pass


# ── Señal: crear / sincronizar perfil automáticamente ─────────────────────

@receiver(post_save, sender=User)
def gestionar_perfil(sender, instance, created, **kwargs):
    if created:
        Perfil.objects.create(usuario=instance)
    else:
        Perfil.objects.get_or_create(usuario=instance)


# ── Modelos de Música ─────────────────────────────────────────────────────

PORTADA_ALBUM_SIZE = (500, 500)


class Album(models.Model):
    GENERO_CHOICES = [
        ('pop', 'Pop'), ('rock', 'Rock'), ('hiphop', 'Hip Hop'),
        ('reggaeton', 'Reggaetón'), ('electronica', 'Electrónica'),
        ('latina', 'Latina'), ('rb', 'R&B'), ('jazz', 'Jazz'),
        ('clasica', 'Clásica'), ('country', 'Country'),
        ('metal', 'Metal'), ('indie', 'Indie'), ('folk', 'Folk'),
        ('blues', 'Blues'), ('otro', 'Otro'),
    ]

    artista    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='albumes')
    titulo     = models.CharField(max_length=200)
    portada    = models.ImageField(upload_to='albumes/portadas/', blank=True, null=True)
    descripcion = models.TextField(blank=True, max_length=1000, default='')
    genero     = models.CharField(max_length=30, choices=GENERO_CHOICES, default='otro')
    fecha_lanzamiento = models.DateField(blank=True, null=True)
    es_publico = models.BooleanField(default=True)
    likes      = models.ManyToManyField(User, related_name='albumes_liked', blank=True)
    creado     = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'Álbum'
        verbose_name_plural = 'Álbumes'

    def __str__(self):
        return f'{self.titulo} — {self.artista.get_full_name() or self.artista.username}'

    def num_canciones(self):
        return self.canciones.count()

    def num_likes(self):
        return self.likes.count()

    def duracion_total(self):
        total = sum(c.duracion for c in self.canciones.all() if c.duracion)
        if total == 0:
            return '0:00'
        mins, secs = divmod(total, 60)
        return f'{mins}:{secs:02d}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.portada:
            try:
                img = Image.open(self.portada.path)
                img = img.convert('RGB')
                max_dim = max(PORTADA_ALBUM_SIZE)
                if img.width > max_dim or img.height > max_dim:
                    img.thumbnail(PORTADA_ALBUM_SIZE, Image.LANCZOS)
                    buffer = BytesIO()
                    img.save(buffer, format='JPEG', quality=90)
                    self.portada.save(self.portada.name, ContentFile(buffer.getvalue()), save=False)
                    Album.objects.filter(pk=self.pk).update(portada=self.portada.name)
            except Exception:
                pass


class Cancion(models.Model):
    album    = models.ForeignKey(Album, on_delete=models.CASCADE, related_name='canciones')
    titulo   = models.CharField(max_length=200)
    archivo  = models.FileField(upload_to='albumes/canciones/')
    numero   = models.PositiveIntegerField(default=1)
    duracion = models.PositiveIntegerField(default=0, help_text='Duración en segundos')
    likes    = models.ManyToManyField(User, related_name='canciones_liked', blank=True)
    creado   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['numero']
        verbose_name = 'Canción'
        verbose_name_plural = 'Canciones'

    def __str__(self):
        return f'{self.numero}. {self.titulo}'

    def duracion_formato(self):
        if not self.duracion:
            return '0:00'
        mins, secs = divmod(self.duracion, 60)
        return f'{mins}:{secs:02d}'

    def num_likes(self):
        return self.likes.count()


# ── Publicaciones del feed ────────────────────────────────────────────────

class Publicacion(models.Model):
    autor     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='publicaciones')
    contenido = models.TextField(max_length=2000, blank=True, default='')
    imagen    = models.ImageField(upload_to='publicaciones/', blank=True, null=True)
    encuesta_pregunta = models.CharField(max_length=220, blank=True, default='')
    encuesta_opcion1 = models.CharField(max_length=140, blank=True, default='')
    encuesta_opcion2 = models.CharField(max_length=140, blank=True, default='')
    encuesta_opcion3 = models.CharField(max_length=140, blank=True, default='')
    encuesta_opcion4 = models.CharField(max_length=140, blank=True, default='')
    encuesta_opciones_extra = models.JSONField(blank=True, default=list)
    encuesta_fin = models.DateTimeField(blank=True, null=True)
    creado    = models.DateTimeField(auto_now_add=True)
    likes     = models.ManyToManyField(User, related_name='publicaciones_liked', blank=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'Publicación'
        verbose_name_plural = 'Publicaciones'

    def __str__(self):
        return f'{self.autor.username}: {self.contenido[:50]}'

    def num_likes(self):
        return self.likes.count()

    def num_comentarios(self):
        return self.comentarios.count()

    def tiene_encuesta(self):
        return bool(self.encuesta_pregunta and self.encuesta_opcion1 and self.encuesta_opcion2)

    def encuesta_opciones(self):
        base = [
            self.encuesta_opcion1,
            self.encuesta_opcion2,
            self.encuesta_opcion3,
            self.encuesta_opcion4,
        ]
        extras = self.encuesta_opciones_extra if isinstance(self.encuesta_opciones_extra, list) else []
        return [o for o in [*base, *extras] if o]

    def encuesta_total_votos(self):
        return self.encuesta_votos.count()

    def encuesta_votos_opcion(self, opcion):
        return self.encuesta_votos.filter(opcion=opcion).count()

    @property
    def encuesta_votos_opcion1(self):
        return self.encuesta_votos_opcion(1)

    @property
    def encuesta_votos_opcion2(self):
        return self.encuesta_votos_opcion(2)

    @property
    def encuesta_votos_opcion3(self):
        return self.encuesta_votos_opcion(3)

    @property
    def encuesta_votos_opcion4(self):
        return self.encuesta_votos_opcion(4)

    @property
    def encuesta_expirada(self):
        return bool(self.encuesta_fin and timezone.now() >= self.encuesta_fin)

    @property
    def encuesta_ganadora_texto(self):
        if not self.tiene_encuesta():
            return ''
        opciones = self.encuesta_opciones()
        if not opciones:
            return ''
        max_votos = -1
        ganador = opciones[0]
        for idx, texto in enumerate(opciones, start=1):
            votos = self.encuesta_votos_opcion(idx)
            if votos > max_votos:
                max_votos = votos
                ganador = texto
        return ganador

    @property
    def encuesta_ganadora_votos(self):
        if not self.tiene_encuesta():
            return 0
        opciones = self.encuesta_opciones()
        if not opciones:
            return 0
        return max(self.encuesta_votos_opcion(i) for i in range(1, len(opciones) + 1))


class PublicacionEncuestaVoto(models.Model):
    publicacion = models.ForeignKey(Publicacion, on_delete=models.CASCADE, related_name='encuesta_votos')
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='votos_encuesta_publicacion')
    opcion = models.PositiveSmallIntegerField()
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('publicacion', 'usuario')
        ordering = ['-creado']
        verbose_name = 'Voto encuesta publicación'
        verbose_name_plural = 'Votos encuesta publicaciones'

    def __str__(self):
        return f'{self.usuario.username} voto opcion {self.opcion} en pub {self.publicacion_id}'


# ── Notificaciones ────────────────────────────────────────────────────────

class Notificacion(models.Model):
    TIPO_CHOICES = [
        ('publicacion', 'Publicación'),
        ('album',       'Álbum'),
        ('follow',      'Seguidor'),
    ]
    destinatario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notificaciones')
    remitente    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notificaciones_enviadas')
    tipo         = models.CharField(max_length=20, choices=TIPO_CHOICES)
    mensaje      = models.CharField(max_length=200)
    url          = models.CharField(max_length=200, blank=True, default='')
    leida        = models.BooleanField(default=False)
    creado       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'

    def __str__(self):
        return f'[{self.tipo}] {self.remitente} → {self.destinatario}'


# ── Mensajes de Chat ──────────────────────────────────────────────────────

class MensajeChat(models.Model):
    TIPO_CHOICES = [
        ('texto', 'Texto'),
        ('imagen', 'Imagen'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('archivo', 'Archivo'),
    ]

    emisor    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mensajes_enviados')
    receptor  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mensajes_recibidos')
    contenido = models.TextField(blank=True, default='')
    tipo      = models.CharField(max_length=10, choices=TIPO_CHOICES, default='texto')
    archivo   = models.FileField(upload_to='chat/adjuntos/', blank=True, null=True)
    enviado   = models.DateTimeField(auto_now_add=True)
    leido     = models.BooleanField(default=False)

    class Meta:
        ordering = ['enviado']
        verbose_name = 'Mensaje'
        verbose_name_plural = 'Mensajes'

    def __str__(self):
        resumen = self.contenido[:40] if self.contenido else f'[{self.get_tipo_display()}]'
        return f'{self.emisor.username} → {self.receptor.username}: {resumen}'

    def vista_previa(self):
        if self.tipo == 'texto':
            return self.contenido
        if self.tipo == 'imagen':
            return 'Imagen'
        if self.tipo == 'video':
            return 'Video'
        if self.tipo == 'audio':
            return 'Audio'
        return 'Archivo adjunto'


class PreferenciasUsuario(models.Model):
    COLORES = [
        ('red', 'Rojo'), ('green', 'Verde'), ('blue', 'Azul'),
        ('pink', 'Rosa'), ('yellow', 'Amarillo'), ('orange', 'Naranja'),
        ('gray', 'Gris'), ('brown', 'Marrón'), ('darkgreen', 'Verde oscuro'),
        ('deeppink', 'Rosa claro'), ('cadetblue', 'Azul cadet'),
        ('darkorchid', 'Orquídea'),
    ]
    usuario      = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferencias')
    color_tema   = models.CharField(max_length=20, choices=COLORES, default='blue')
    modo_oscuro  = models.BooleanField(default=False)
    fondo_header = models.BooleanField(default=False)
    menu_lateral = models.BooleanField(default=False)

    def __str__(self):
        return f'Preferencias de {self.usuario.username}'


class Historia(models.Model):
    TIPO_CHOICES = [
        ('imagen', 'Imagen'),
        ('video', 'Video'),
    ]
    PRIVACIDAD_CHOICES = [
        ('publica', 'Pública'),
        ('seguidores', 'Solo seguidores'),
        ('mejores_amigos', 'Mejores amigos'),
    ]

    autor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='historias')
    archivo = models.FileField(upload_to='historias/')
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    texto = models.CharField(max_length=280, blank=True, default='')
    privacidad = models.CharField(max_length=20, choices=PRIVACIDAD_CHOICES, default='seguidores')
    creado = models.DateTimeField(auto_now_add=True)
    visto_por = models.ManyToManyField(User, related_name='historias_vistas', blank=True)
    likes = models.ManyToManyField(User, related_name='historias_liked', blank=True)
    ocultar_a = models.ManyToManyField(User, related_name='historias_ocultadas', blank=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'Historia'
        verbose_name_plural = 'Historias'

    def __str__(self):
        return f'Historia de {self.autor.username} ({self.tipo})'

    @property
    def expira_en(self):
        return self.creado + timedelta(hours=24)

    @property
    def activa(self):
        return timezone.now() < self.expira_en

    def num_likes(self):
        return self.likes.count()

    def num_comentarios(self):
        return self.comentarios.count()


class GrupoMusical(models.Model):
    GENERO_CHOICES = [
        ('pop', 'Pop'), ('rock', 'Rock'), ('hiphop', 'Hip Hop'),
        ('reggaeton', 'Reggaeton'), ('electronica', 'Electronica'),
        ('latina', 'Latina'), ('rb', 'R&B'), ('jazz', 'Jazz'),
        ('clasica', 'Clasica'), ('indie', 'Indie'), ('otro', 'Otro'),
    ]

    creador = models.ForeignKey(User, on_delete=models.CASCADE, related_name='grupos_creados')
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(max_length=1200, blank=True, default='')
    genero = models.CharField(max_length=30, choices=GENERO_CHOICES, default='otro')
    ciudad = models.CharField(max_length=120, blank=True, default='')
    es_privado = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'Grupo musical'
        verbose_name_plural = 'Grupos musicales'

    def __str__(self):
        return self.nombre

    def total_miembros(self):
        return self.miembros.count()


class GrupoMiembro(models.Model):
    ROL_CHOICES = [
        ('admin', 'Admin'),
        ('miembro', 'Miembro'),
    ]

    grupo = models.ForeignKey(GrupoMusical, on_delete=models.CASCADE, related_name='miembros')
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='grupos_miembro')
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default='miembro')
    unido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('grupo', 'usuario')
        ordering = ['unido_en']
        verbose_name = 'Miembro de grupo'
        verbose_name_plural = 'Miembros de grupos'

    def __str__(self):
        return f'{self.usuario.username} en {self.grupo.nombre}'


class EventoMusical(models.Model):
    GENERO_CHOICES = GrupoMusical.GENERO_CHOICES

    creador = models.ForeignKey(User, on_delete=models.CASCADE, related_name='eventos_creados')
    titulo = models.CharField(max_length=140)
    descripcion = models.TextField(max_length=1600, blank=True, default='')
    genero = models.CharField(max_length=30, choices=GENERO_CHOICES, default='otro')
    lugar = models.CharField(max_length=180)
    fecha_evento = models.DateTimeField()
    cupo = models.PositiveIntegerField(blank=True, null=True)
    es_privado = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['fecha_evento']
        verbose_name = 'Evento musical'
        verbose_name_plural = 'Eventos musicales'

    def __str__(self):
        return self.titulo

    def total_asistentes(self):
        return self.asistentes.count()


class EventoAsistente(models.Model):
    ESTADO_CHOICES = [
        ('asistire', 'Asistire'),
        ('interesado', 'Interesado'),
    ]

    evento = models.ForeignKey(EventoMusical, on_delete=models.CASCADE, related_name='asistentes')
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='eventos_asistente')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='asistire')
    unido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('evento', 'usuario')
        ordering = ['unido_en']
        verbose_name = 'Asistente de evento'
        verbose_name_plural = 'Asistentes de eventos'

    def __str__(self):
        return f'{self.usuario.username} en {self.evento.titulo}'


class InvitacionGrupo(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('aceptada', 'Aceptada'),
        ('rechazada', 'Rechazada'),
    ]

    grupo = models.ForeignKey(GrupoMusical, on_delete=models.CASCADE, related_name='invitaciones')
    invitador = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invitaciones_grupo_enviadas')
    invitado = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invitaciones_grupo_recibidas')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('grupo', 'invitado')
        ordering = ['-creado']
        verbose_name = 'Invitacion a grupo'
        verbose_name_plural = 'Invitaciones a grupos'

    def __str__(self):
        return f'Invitacion a {self.invitado.username} para {self.grupo.nombre}'


class InvitacionEvento(models.Model):
    ESTADO_CHOICES = InvitacionGrupo.ESTADO_CHOICES

    evento = models.ForeignKey(EventoMusical, on_delete=models.CASCADE, related_name='invitaciones')
    invitador = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invitaciones_evento_enviadas')
    invitado = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invitaciones_evento_recibidas')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('evento', 'invitado')
        ordering = ['-creado']
        verbose_name = 'Invitacion a evento'
        verbose_name_plural = 'Invitaciones a eventos'

    def __str__(self):
        return f'Invitacion a {self.invitado.username} para {self.evento.titulo}'


class ComentarioPublicacion(models.Model):
    publicacion = models.ForeignKey(Publicacion, on_delete=models.CASCADE, related_name='comentarios')
    autor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comentarios_publicacion')
    contenido = models.CharField(max_length=500)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado']
        verbose_name = 'Comentario de publicación'
        verbose_name_plural = 'Comentarios de publicaciones'

    def __str__(self):
        return f'{self.autor.username}: {self.contenido[:40]}'


class ComentarioHistoria(models.Model):
    historia = models.ForeignKey(Historia, on_delete=models.CASCADE, related_name='comentarios')
    autor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comentarios_historia')
    contenido = models.CharField(max_length=500)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado']
        verbose_name = 'Comentario de historia'
        verbose_name_plural = 'Comentarios de historias'

    def __str__(self):
        return f'{self.autor.username}: {self.contenido[:40]}'


@receiver(post_save, sender=User)
def crear_preferencias_usuario(sender, instance, created, **kwargs):
    if created:
        PreferenciasUsuario.objects.get_or_create(usuario=instance)

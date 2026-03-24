from io import BytesIO

from django.core.files.base import ContentFile
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
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
                if img.width != PORTADA_ALBUM_SIZE[0] or img.height != PORTADA_ALBUM_SIZE[1]:
                    img_proc = _recortar_centrado(img, *PORTADA_ALBUM_SIZE)
                    buffer = BytesIO()
                    img_proc.save(buffer, format='JPEG', quality=90)
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

from django import forms
from django.contrib.auth.models import User
from .models import Perfil, Album, Cancion, Publicacion, Historia


class EditarPerfilForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=50, required=False, label='Nombre',
        widget=forms.TextInput(attrs={
            'class': 'form-control style2-input ps-5 fw-600 font-xsss mb-2',
            'placeholder': 'Tu nombre',
        }),
    )
    last_name = forms.CharField(
        max_length=50, required=False, label='Apellido',
        widget=forms.TextInput(attrs={
            'class': 'form-control style2-input ps-5 fw-600 font-xsss mb-2',
            'placeholder': 'Tu apellido',
        }),
    )

    class Meta:
        model  = Perfil
        fields = ['foto', 'portada', 'bio', 'ubicacion', 'sitio_web', 'ocupacion', 'es_privado']
        widgets = {
            'foto':      forms.FileInput(attrs={
                'class': 'form-control', 'accept': 'image/*',
            }),
            'portada':   forms.FileInput(attrs={
                'class': 'form-control', 'accept': 'image/*',
            }),
            'bio':        forms.Textarea(attrs={
                'class': 'form-control style2-textarea ps-5 fw-500 fw-600 font-xsss',
                'rows': 3, 'placeholder': 'Cuéntanos algo sobre ti...',
            }),
            'ubicacion':  forms.TextInput(attrs={
                'class': 'form-control style2-input ps-5 fw-600 font-xsss mb-2',
                'placeholder': 'Tu ciudad o país',
            }),
            'sitio_web':  forms.URLInput(attrs={
                'class': 'form-control style2-input ps-5 fw-600 font-xsss mb-2',
                'placeholder': 'https://tuweb.com',
            }),
            'ocupacion':  forms.TextInput(attrs={
                'class': 'form-control style2-input ps-5 fw-600 font-xsss mb-2',
                'placeholder': 'Tu ocupación o rol',
            }),
            'es_privado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'foto':       'Foto de perfil',
            'portada':    'Foto de portada',
            'bio':        'Biografía',
            'ubicacion':  'Ubicación',
            'sitio_web':  'Sitio web',
            'ocupacion':  'Ocupación',
            'es_privado': 'Perfil privado',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial  = user.last_name

    def save_user(self, user):
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name  = self.cleaned_data.get('last_name', '')
        user.save()


# ── Formularios de Álbumes ────────────────────────────────────────────────

class AlbumForm(forms.ModelForm):
    class Meta:
        model  = Album
        fields = ['titulo', 'portada', 'descripcion', 'genero', 'fecha_lanzamiento', 'es_publico']
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'form-control style2-input ps-5 fw-600 font-xsss',
                'placeholder': 'Nombre del álbum',
            }),
            'portada': forms.FileInput(attrs={
                'class': 'form-control', 'accept': 'image/*',
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control style2-textarea ps-5 fw-500 font-xsss',
                'rows': 3, 'placeholder': 'Describe tu álbum...',
            }),
            'genero': forms.Select(attrs={
                'class': 'form-control style2-input ps-3 fw-600 font-xsss',
            }),
            'fecha_lanzamiento': forms.DateInput(attrs={
                'class': 'form-control style2-input ps-5 fw-600 font-xsss',
                'type': 'date',
            }),
            'es_publico': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'titulo': 'Título del álbum',
            'portada': 'Portada (500×500 px)',
            'descripcion': 'Descripción',
            'genero': 'Género musical',
            'fecha_lanzamiento': 'Fecha de lanzamiento',
            'es_publico': 'Álbum público',
        }


class CancionForm(forms.ModelForm):
    class Meta:
        model  = Cancion
        fields = ['titulo', 'archivo', 'numero']
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'form-control style2-input ps-5 fw-600 font-xsss',
                'placeholder': 'Título de la canción',
            }),
            'archivo': forms.FileInput(attrs={
                'class': 'form-control', 'accept': 'audio/*',
            }),
            'numero': forms.NumberInput(attrs={
                'class': 'form-control style2-input ps-5 fw-600 font-xsss',
                'min': 1, 'placeholder': '#',
            }),
        }
        labels = {
            'titulo': 'Título',
            'archivo': 'Archivo de audio (MP3, WAV, etc.)',
            'numero': 'Número de pista',
        }


# ── Formulario de Publicación ─────────────────────────────────────────────

class PublicacionForm(forms.ModelForm):
    class Meta:
        model = Publicacion
        fields = ['contenido', 'imagen']
        widgets = {
            'contenido': forms.Textarea(attrs={
                'class': 'form-control rounded-xxl border-0 fw-500 font-xss bg-greylight',
                'rows': 3,
                'placeholder': '¿Qué estás pensando?',
            }),
            'imagen': forms.FileInput(attrs={
                'class': 'form-control', 'accept': 'image/*',
            }),
        }
        labels = {
            'contenido': '',
            'imagen': 'Foto (opcional)',
        }

    def clean(self):
        cleaned_data = super().clean()
        contenido = cleaned_data.get('contenido', '').strip()
        imagen = cleaned_data.get('imagen')
        encuesta_pregunta = (self.data.get('encuesta_pregunta') or '').strip()
        encuesta_opcion1 = (self.data.get('encuesta_opcion1') or '').strip()
        encuesta_opcion2 = (self.data.get('encuesta_opcion2') or '').strip()
        encuesta2_pregunta = (self.data.get('encuesta2_pregunta') or '').strip()
        encuesta2_opcion1 = (self.data.get('encuesta2_opcion1') or '').strip()
        encuesta2_opcion2 = (self.data.get('encuesta2_opcion2') or '').strip()
        tiene_encuesta_valida = bool(encuesta_pregunta and encuesta_opcion1 and encuesta_opcion2)
        tiene_encuesta2_valida = bool(encuesta2_pregunta and encuesta2_opcion1 and encuesta2_opcion2)

        if not contenido and not imagen and not (tiene_encuesta_valida or tiene_encuesta2_valida):
            raise forms.ValidationError('Escribe algo o selecciona una imagen para publicar.')
        return cleaned_data


class HistoriaForm(forms.ModelForm):
    ocultar_usernames = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control style2-input ps-3 fw-500 font-xssss',
            'placeholder': 'Ocultar a (user1,user2) opcional',
        }),
        label='Ocultar a usuarios',
    )
    amigos_cercanos_usernames = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control style2-input ps-3 fw-500 font-xssss',
            'placeholder': 'Mejores amigos (user1,user2) opcional',
        }),
        label='Lista de mejores amigos',
    )

    class Meta:
        model = Historia
        fields = ['archivo', 'texto', 'privacidad']
        widgets = {
            'archivo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*,video/*',
                'required': True,
            }),
            'texto': forms.TextInput(attrs={
                'class': 'form-control style2-input ps-3 fw-500 font-xssss',
                'placeholder': 'Texto opcional para tu historia',
                'maxlength': 280,
            }),
            'privacidad': forms.Select(attrs={
                'class': 'form-control style2-input ps-3 fw-600 font-xssss',
            }),
        }
        labels = {
            'archivo': 'Foto o video',
            'texto': 'Texto (opcional)',
            'privacidad': 'Privacidad',
        }

    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        if not archivo:
            raise forms.ValidationError('Debes seleccionar un archivo.')

        ctype = (getattr(archivo, 'content_type', '') or '').lower()
        if ctype.startswith('image/'):
            return archivo
        if ctype.startswith('video/'):
            # 50MB para videos de historia
            if archivo.size > 50 * 1024 * 1024:
                raise forms.ValidationError('El video no debe superar 50MB.')
            return archivo

        raise forms.ValidationError('Formato no permitido. Usa imagen o video.')

    def clean(self):
        cleaned = super().clean()
        privacidad = cleaned.get('privacidad')
        amigos_raw = (cleaned.get('amigos_cercanos_usernames') or '').strip()
        if privacidad == 'mejores_amigos' and not amigos_raw:
            raise forms.ValidationError('Para "Mejores amigos", indica al menos un username en la lista.')
        return cleaned

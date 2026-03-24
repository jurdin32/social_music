from django import forms
from django.contrib.auth.models import User
from .models import Perfil, Album, Cancion


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

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.http import JsonResponse
from .models import Perfil, Album, Cancion
from .forms import EditarPerfilForm, AlbumForm, CancionForm


def verificacion_exitosa(request):
    return render(request, 'account/verification_success.html')


def home(request):
    if request.user.is_authenticated:
        return redirect('inicio')
    return redirect('account_login')


@login_required
def inicio(request):
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    contexto = {'user': request.user, 'perfil': perfil_obj}
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
    contexto = {'user': request.user, 'perfil': perfil_obj}
    return render(request, 'default-storie.html', contexto)


@login_required
def grupos(request):
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=request.user)
    contexto = {'user': request.user, 'perfil': perfil_obj}
    return render(request, 'default-group.html', contexto)


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
    return redirect('pagina_usuario', username=request.user.username)


@login_required
def pagina_usuario(request, username):
    usuario_obj = get_object_or_404(User, username=username)
    perfil_obj, _ = Perfil.objects.get_or_create(usuario=usuario_obj)
    es_propio = (request.user == usuario_obj)
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
    contexto = {
        'user': request.user,
        'perfil_visto': perfil_obj,
        'usuario_visto': usuario_obj,
        'es_propio': es_propio,
        'form': form,
        'albumes': usuario_obj.albumes.all(),
    }
    return render(request, 'user-page.html', contexto)


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
    contexto = {
        'user': request.user,
        'perfil': perfil_obj,
        'album': album,
        'canciones': album.canciones.all(),
        'perfil_artista': perfil_artista,
        'es_propietario': es_propietario,
        'cancion_form': cancion_form,
    }
    return render(request, 'albumes/detalle_album.html', contexto)


@login_required
def agregar_cancion(request, album_id):
    album = get_object_or_404(Album, pk=album_id, artista=request.user)
    if request.method == 'POST':
        archivos = request.FILES.getlist('archivos')
        if archivos:
            siguiente = album.canciones.count() + 1
            for i, archivo in enumerate(archivos):
                titulo = archivo.name.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title()
                cancion = Cancion(
                    album=album,
                    titulo=titulo,
                    archivo=archivo,
                    numero=siguiente + i,
                )
                try:
                    from mutagen import File as MutagenFile
                    audio = MutagenFile(archivo)
                    if audio and audio.info:
                        cancion.duracion = int(audio.info.length)
                except Exception:
                    pass
                cancion.save()
            return redirect('detalle_album', album_id=album.pk)
        else:
            form = CancionForm(request.POST, request.FILES)
            if form.is_valid():
                cancion = form.save(commit=False)
                cancion.album = album
                try:
                    from mutagen import File as MutagenFile
                    audio = MutagenFile(cancion.archivo)
                    if audio and audio.info:
                        cancion.duracion = int(audio.info.length)
                except Exception:
                    pass
                cancion.save()
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
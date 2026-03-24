"""
Script para descargar un sitio web completo con todos sus assets (CSS, JS, imágenes, etc.)
y todas las páginas HTML enlazadas dentro del mismo dominio/ruta base.
"""

import os
import re
import sys
import time
import urllib.parse
from pathlib import Path
import requests
import cloudscraper
from bs4 import BeautifulSoup

# Forzar UTF-8 en stdout para evitar UnicodeEncodeError en Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Estas variables se asignan dinámicamente al iniciar el script
BASE_URL: str = ""
BASE_DOMAIN: str = ""
BASE_PATH: str = ""
OUTPUT_DIR: Path = Path(".")

# Sesion con soporte Cloudflare + cabeceras de navegador real
session = cloudscraper.create_scraper()
session.headers.update({
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
})

visited_pages: set = set()
downloaded_assets: set = set()


def url_to_local_path(url: str) -> Path:
    """Convierte una URL a una ruta local dentro de OUTPUT_DIR."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lstrip("/")
    if not path or path.endswith("/"):
        path = path + "index.html"
    local = OUTPUT_DIR / path
    return local


def ensure_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def download_asset(url: str) -> bool:
    """Descarga un asset (CSS, JS, imagen, fuente, etc.) y lo guarda localmente."""
    if url in downloaded_assets:
        return True
    downloaded_assets.add(url)

    local_path = url_to_local_path(url)
    if local_path.exists():
        return True

    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        ensure_dir(local_path)
        local_path.write_bytes(r.content)
        print(f"  [ASSET] {url}")
        return True
    except Exception as e:
        print(f"  [ERROR asset] {url} -> {e}")
        return False


def resolve_url(base: str, href: str) -> str | None:
    """Resuelve una URL relativa o absoluta."""
    if not href or href.startswith("data:") or href.startswith("javascript:") or href.startswith("#"):
        return None
    return urllib.parse.urljoin(base, href)


def is_same_site(url: str) -> bool:
    """Verifica si la URL pertenece al mismo dominio."""
    return url.startswith(BASE_DOMAIN)


def is_html_page(url: str) -> bool:
    """Verifica si la URL apunta a una página HTML dentro de la ruta base."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    # Solo páginas dentro de BASE_PATH
    if not path.startswith(BASE_PATH):
        return False
    # Aceptar .html o rutas sin extensión
    ext = os.path.splitext(path)[1].lower()
    return ext in ("", ".html", ".htm")


def extract_urls_from_css(css_content: str, base_url: str) -> list[str]:
    """Extrae URLs de un archivo CSS (url(...))."""
    urls = []
    pattern = re.compile(r'url\(["\']?([^)"\']+)["\']?\)', re.IGNORECASE)
    for match in pattern.finditer(css_content):
        href = match.group(1).strip()
        full = resolve_url(base_url, href)
        if full and is_same_site(full):
            urls.append(full)
    return urls


def download_css_and_its_assets(url: str):
    """Descarga un CSS y todos los assets que referencia (fuentes, imágenes, etc.)."""
    if url in downloaded_assets:
        return
    downloaded_assets.add(url)

    local_path = url_to_local_path(url)
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        content = r.text
        ensure_dir(local_path)
        local_path.write_text(content, encoding="utf-8", errors="replace")
        print(f"  [CSS]   {url}")

        # Descargar assets referenciados dentro del CSS
        asset_urls = extract_urls_from_css(content, url)
        for asset_url in asset_urls:
            download_asset(asset_url)

    except Exception as e:
        print(f"  [ERROR css] {url} -> {e}")


def crawl_page(url: str):
    """Descarga una página HTML y todos sus assets, luego sigue los enlaces HTML."""
    # Normalizar URL (sin fragmento)
    url = url.split("#")[0]
    if url in visited_pages:
        return
    visited_pages.add(url)

    print(f"\n[PAGE] {url}")

    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        html_content = r.text
    except Exception as e:
        print(f"  [ERROR page] {url} -> {e}")
        return

    soup = BeautifulSoup(html_content, "html.parser")
    local_path = url_to_local_path(url)
    ensure_dir(local_path)
    local_path.write_text(html_content, encoding="utf-8", errors="replace")

    links_to_follow = []

    # --- CSS <link rel="stylesheet"> ---
    for tag in soup.find_all("link", rel=lambda v: v and "stylesheet" in v):
        href = tag.get("href")
        full = resolve_url(url, href)
        if full and is_same_site(full):
            download_css_and_its_assets(full)

    # --- Otros <link> (favicon, etc.) ---
    for tag in soup.find_all("link"):
        href = tag.get("href")
        full = resolve_url(url, href)
        if full and is_same_site(full):
            ext = os.path.splitext(urllib.parse.urlparse(full).path)[1].lower()
            if ext not in ("", ".html", ".htm", ".css"):
                download_asset(full)

    # --- Scripts <script src="..."> ---
    for tag in soup.find_all("script", src=True):
        src = tag.get("src")
        full = resolve_url(url, src)
        if full and is_same_site(full):
            download_asset(full)

    # --- Imágenes <img src="..."> y <img srcset="..."> ---
    for tag in soup.find_all("img"):
        src = tag.get("src")
        if src:
            full = resolve_url(url, src)
            if full and is_same_site(full):
                download_asset(full)
        srcset = tag.get("srcset")
        if srcset:
            for part in srcset.split(","):
                part_url = part.strip().split()[0]
                full = resolve_url(url, part_url)
                if full and is_same_site(full):
                    download_asset(full)

    # --- Sources <source src="..."> ---
    for tag in soup.find_all("source"):
        src = tag.get("src") or tag.get("srcset")
        if src:
            full = resolve_url(url, src)
            if full and is_same_site(full):
                download_asset(full)

    # --- Videos y audios ---
    for tag in soup.find_all(["video", "audio"]):
        src = tag.get("src")
        if src:
            full = resolve_url(url, src)
            if full and is_same_site(full):
                download_asset(full)

    # --- Inline style con url() ---
    for tag in soup.find_all(style=True):
        style = tag.get("style", "")
        for asset_url in extract_urls_from_css(style, url):
            download_asset(asset_url)

    # --- Estilos <style> inline ---
    for tag in soup.find_all("style"):
        content = tag.string or ""
        for asset_url in extract_urls_from_css(content, url):
            download_asset(asset_url)

    # --- Iframes ---
    for tag in soup.find_all("iframe", src=True):
        src = tag.get("src")
        full = resolve_url(url, src)
        if full and is_same_site(full) and is_html_page(full):
            links_to_follow.append(full)

    # --- Anchors <a href="..."> ---
    for tag in soup.find_all("a", href=True):
        href = tag.get("href")
        full = resolve_url(url, href)
        if full and is_same_site(full):
            full_no_frag = full.split("#")[0]
            if is_html_page(full_no_frag) and full_no_frag not in visited_pages:
                links_to_follow.append(full_no_frag)

    # Seguir enlaces HTML encontrados
    for link in links_to_follow:
        time.sleep(0.3)  # respetar al servidor
        crawl_page(link)


def solicitar_configuracion():
    """Solicita al usuario la URL y el directorio de salida."""
    global BASE_URL, BASE_DOMAIN, BASE_PATH, OUTPUT_DIR

    print("=" * 60)
    print("        DESCARGADOR DE SITIOS WEB COMPLETOS")
    print("=" * 60)

    # --- URL: desde argumento o por teclado ---
    if len(sys.argv) >= 1 and len(sys.argv) > 1:
        url = sys.argv[1].strip()
        print(f"\nURL: {url}")
    else:
        while True:
            url = input("\nIngresa la URL del sitio a descargar:\n> ").strip()
            if not url:
                print("  [!] La URL no puede estar vacía.")
                continue
            break

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc:
        print("  [!] URL inválida. Saliendo.")
        sys.exit(1)

    BASE_URL = url

    # Derivar dominio y ruta base automáticamente
    BASE_DOMAIN = f"{parsed.scheme}://{parsed.netloc}"
    path_dir = parsed.path.rsplit("/", 1)[0]
    BASE_PATH = path_dir + "/" if path_dir else "/"

    # --- Directorio de salida: argumento 2 o default automático ---
    nombre_sitio = parsed.netloc.replace("www.", "").replace(".", "_")
    default_dir = Path.cwd() / nombre_sitio

    if len(sys.argv) > 2:
        # Se pasó el directorio como segundo argumento
        OUTPUT_DIR = Path(sys.argv[2].strip())
    else:
        # Pedir solo si NO se pasó URL por argumento (modo interactivo puro)
        if len(sys.argv) == 1:
            dir_input = input(
                f"\nDirectorio de destino (Enter para usar '{default_dir}'):\n> "
            ).strip()
            OUTPUT_DIR = Path(dir_input) if dir_input else default_dir
        else:
            # URL vino como argumento → usar directorio por defecto sin preguntar
            OUTPUT_DIR = default_dir

    print(f"\nDestino  : {OUTPUT_DIR}")
    print("-" * 60 + "\n")


if __name__ == "__main__":
    solicitar_configuracion()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nDescargando sitio a: {OUTPUT_DIR}")
    print(f"URL base: {BASE_URL}\n")
    crawl_page(BASE_URL)
    print(f"\n[OK] Descarga completada.")
    print(f"  Paginas descargadas : {len(visited_pages)}")
    print(f"  Assets descargados  : {len(downloaded_assets)}")
    print(f"  Directorio          : {OUTPUT_DIR}")

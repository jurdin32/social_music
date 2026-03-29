# ============================================================
#  iniciar.ps1  --  Arranca social_music en 0.0.0.0:8000
#  Uso: .\iniciar.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function OK   { param($m) Write-Host "  [OK] $m" -ForegroundColor Green  }
function INFO { param($m) Write-Host "  [>>] $m" -ForegroundColor Cyan   }
function WARN { param($m) Write-Host "  [!]  $m" -ForegroundColor Yellow }
function ERR  { param($m) Write-Host "  [X]  $m" -ForegroundColor Red    }

Write-Host ""
Write-Host "======================================" -ForegroundColor Magenta
Write-Host "   social_music  --  iniciando...     " -ForegroundColor Magenta
Write-Host "======================================" -ForegroundColor Magenta
Write-Host ""

# 1. Entorno virtual
$venv = Join-Path $Root "venv\Scripts\Activate.ps1"
if (-not (Test-Path $venv)) {
    ERR "No se encontro el entorno virtual."
    WARN "Crealo con:  python -m venv venv"
    exit 1
}
INFO "Activando entorno virtual..."
& $venv
OK "Entorno virtual activo"

# 2. Dependencias
$req = Join-Path $Root "requirements.txt"
if (Test-Path $req) {
    INFO "Instalando/verificando dependencias..."
    pip install -r $req --quiet
    OK "Dependencias OK"
} else {
    WARN "No se encontro requirements.txt -- omitiendo"
}

# 3. Migraciones
INFO "Aplicando migraciones..."
python manage.py migrate --run-syncdb
OK "Base de datos lista"

# 4. Crear carpetas de media si no existen
$mediaDirs = @(
    "media\perfiles",
    "media\portadas",
    "media\albumes\portadas",
    "media\albumes\canciones",
    "media\publicaciones"
)
foreach ($d in $mediaDirs) {
    $full = Join-Path $Root $d
    if (-not (Test-Path $full)) {
        New-Item -ItemType Directory -Path $full | Out-Null
        OK "Creada carpeta: $d"
    }
}

# 5. Informacion
Write-Host ""
Write-Host "--------------------------------------" -ForegroundColor Magenta
INFO "Servidor : Daphne ASGI (HTTP + WebSocket)"
INFO "Estaticos: ASGIStaticFilesHandler (DEBUG)"
INFO "Media    : servidos via URL /media/"
INFO "URL      : http://0.0.0.0:8000"
INFO "Detener  : Ctrl + C"
Write-Host "--------------------------------------" -ForegroundColor Magenta
Write-Host ""

# 6. Arrancar Daphne
daphne -b 0.0.0.0 -p 8000 social_music.asgi:application
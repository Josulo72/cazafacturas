# Instalador de Cazafacturas para Windows.
#
#   powershell -ExecutionPolicy Bypass -File instalar.ps1
#
# Deja un entorno propio en .venv, así que no toca el Python del sistema ni
# le cambia versiones a nada que ya tengas instalado. Se puede volver a
# ejecutar las veces que haga falta: no rompe nada de lo que ya esté hecho.

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$PYTHON_MINIMO = [Version]'3.10'

function Paso($texto)  { Write-Host "`n$texto" -ForegroundColor White }
function Bien($texto)  { Write-Host "  OK  $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "  !   $texto" -ForegroundColor Yellow }
function Alto($texto)  { Write-Host "`n  X   $texto" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  Cazafacturas" -ForegroundColor Cyan
Write-Host "  Extrae y comprueba facturas en local. Sin IA, sin red, sin claves."

# ---------------------------------------------------------------------------
# 1. Python
# ---------------------------------------------------------------------------
Paso "1/5  Buscando Python"

# `py` es el lanzador oficial de Windows y sabe elegir versión; si no está,
# se prueba con `python` a secas.
$candidatos = @(
    @{ Orden = 'py';     Args = @('-3', '-c', 'import sys;print(sys.version.split()[0])') },
    @{ Orden = 'python'; Args = @('-c', 'import sys;print(sys.version.split()[0])') }
)

$python = $null
foreach ($c in $candidatos) {
    if (-not (Get-Command $c.Orden -ErrorAction SilentlyContinue)) { continue }
    try { $v = & $c.Orden @($c.Args) 2>$null } catch { continue }
    if (-not $v) { continue }
    if ([Version]([regex]::Match($v, '^\d+\.\d+').Value) -ge $PYTHON_MINIMO) {
        $python = $c
        Bien "Python $v ($($c.Orden))"
        break
    }
    Aviso "Python $v en '$($c.Orden)': hace falta $PYTHON_MINIMO o superior"
}

if (-not $python) {
    Alto "No hay un Python $PYTHON_MINIMO o superior. Instálalo desde python.org y marca la casilla 'Add to PATH'."
}

# ---------------------------------------------------------------------------
# 2. Entorno propio
# ---------------------------------------------------------------------------
Paso "2/5  Preparando el entorno"

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    Bien "El entorno ya existía; se reutiliza"
} else {
    $creador = $python.Args[0..($python.Args.Length - 3)]
    & $python.Orden @creador -m venv .venv
    if ($LASTEXITCODE -ne 0) { Alto "No se ha podido crear el entorno en .venv" }
    Bien "Entorno creado en .venv"
}

# ---------------------------------------------------------------------------
# 3. Dependencias
# ---------------------------------------------------------------------------
Paso "3/5  Instalando (esto tarda: el OCR trae sus modelos dentro)"

& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -e ".[ocr,muestras]"
if ($LASTEXITCODE -ne 0) { Alto "Ha fallado la instalación de dependencias" }
Bien "Dependencias instaladas"

# ---------------------------------------------------------------------------
# 4. Facturas de muestra
# ---------------------------------------------------------------------------
Paso "4/5  Generando las facturas de muestra"

if (Test-Path (Join-Path $PSScriptRoot 'dataset\pdf\ES')) {
    Bien "Ya estaban generadas"
} else {
    & $venvPython -m dataset.render_pdf | Out-Null
    if ($LASTEXITCODE -ne 0) { Aviso "No se han podido generar; la aplicación funciona igual" }
    else { Bien "74 PDF de muestra listos" }
}

# ---------------------------------------------------------------------------
# 5. Comprobación y lanzador
# ---------------------------------------------------------------------------
Paso "5/5  Comprobando la instalación"

& $venvPython cli.py --doctor
$salud = $LASTEXITCODE

$lanzador = Join-Path $PSScriptRoot 'Cazafacturas.cmd'
@"
@echo off
rem Lanzador de Cazafacturas. Doble clic y listo.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m backend.main %*
"@ | Set-Content -LiteralPath $lanzador -Encoding ASCII

Write-Host ""
if ($salud -eq 0) {
    Write-Host "  Listo." -ForegroundColor Green
} else {
    Write-Host "  Instalado, pero el diagnóstico ha encontrado algo. Míralo arriba." -ForegroundColor Yellow
}
Write-Host "  Doble clic en Cazafacturas.cmd, o:  .\Cazafacturas.cmd"
Write-Host ""

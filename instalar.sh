#!/usr/bin/env sh
# Instalador de Cazafacturas para macOS y Linux.
#
#   sh instalar.sh
#
# Deja un entorno propio en .venv, así que no toca el Python del sistema ni
# le cambia versiones a nada que ya tengas instalado. Se puede volver a
# ejecutar las veces que haga falta: no rompe nada de lo que ya esté hecho.

set -eu
cd "$(dirname "$0")"

PYTHON_MINIMO_MAYOR=3
PYTHON_MINIMO_MENOR=10

if [ -t 1 ]; then
    ROJO=$(printf '\033[31m'); VERDE=$(printf '\033[32m')
    AMBAR=$(printf '\033[33m'); CIAN=$(printf '\033[36m')
    FUERTE=$(printf '\033[1m');  FIN=$(printf '\033[0m')
else
    ROJO=''; VERDE=''; AMBAR=''; CIAN=''; FUERTE=''; FIN=''
fi

paso()  { printf '\n%s%s%s\n' "$FUERTE" "$1" "$FIN"; }
bien()  { printf '  %sOK%s  %s\n' "$VERDE" "$FIN" "$1"; }
aviso() { printf '  %s!%s   %s\n' "$AMBAR" "$FIN" "$1"; }
alto()  { printf '\n  %sX%s   %s\n\n' "$ROJO" "$FIN" "$1"; exit 1; }

printf '\n  %sCazafacturas%s\n' "$CIAN" "$FIN"
printf '  Extrae y comprueba facturas en local. Sin IA, sin red, sin claves.\n'

# ---------------------------------------------------------------------------
# 1. Python
# ---------------------------------------------------------------------------
paso "1/5  Buscando Python"

# Se prueban de más nuevo a más viejo: si hay varios, mejor el reciente.
PYTHON=''
for candidato in python3.13 python3.12 python3.11 python3.10 python3 python; do
    command -v "$candidato" >/dev/null 2>&1 || continue
    version=$("$candidato" -c 'import sys;print("%d %d"%sys.version_info[:2])' 2>/dev/null) || continue
    mayor=${version% *}; menor=${version#* }
    if [ "$mayor" -gt "$PYTHON_MINIMO_MAYOR" ] || \
       { [ "$mayor" -eq "$PYTHON_MINIMO_MAYOR" ] && [ "$menor" -ge "$PYTHON_MINIMO_MENOR" ]; }; then
        PYTHON=$candidato
        bien "Python $mayor.$menor ($candidato)"
        break
    fi
done

[ -n "$PYTHON" ] || alto "No hay un Python $PYTHON_MINIMO_MAYOR.$PYTHON_MINIMO_MENOR o superior. Instálalo y vuelve a intentarlo."

# ---------------------------------------------------------------------------
# 2. Entorno propio
# ---------------------------------------------------------------------------
paso "2/5  Preparando el entorno"

if [ -x .venv/bin/python ]; then
    bien "El entorno ya existía; se reutiliza"
else
    "$PYTHON" -m venv .venv || alto "No se ha podido crear el entorno en .venv"
    bien "Entorno creado en .venv"
fi
VENV=.venv/bin/python

# ---------------------------------------------------------------------------
# 3. Dependencias
# ---------------------------------------------------------------------------
paso "3/5  Instalando (esto tarda: el OCR trae sus modelos dentro)"

"$VENV" -m pip install --quiet --upgrade pip
"$VENV" -m pip install --quiet -e ".[ocr,muestras]" || alto "Ha fallado la instalación de dependencias"
bien "Dependencias instaladas"

# ---------------------------------------------------------------------------
# 4. Facturas de muestra
# ---------------------------------------------------------------------------
paso "4/5  Generando las facturas de muestra"

if [ -d dataset/pdf/ES ]; then
    bien "Ya estaban generadas"
elif "$VENV" -m dataset.render_pdf >/dev/null 2>&1; then
    bien "74 PDF de muestra listos"
else
    aviso "No se han podido generar; la aplicación funciona igual"
fi

# ---------------------------------------------------------------------------
# 5. Comprobación y lanzador
# ---------------------------------------------------------------------------
paso "5/5  Comprobando la instalación"

set +e
"$VENV" cli.py --doctor
SALUD=$?
set -e

cat > cazafacturas <<'LANZADOR'
#!/usr/bin/env sh
# Lanzador de Cazafacturas.
cd "$(dirname "$0")"
exec .venv/bin/python -m backend.main "$@"
LANZADOR
chmod +x cazafacturas

printf '\n'
if [ "$SALUD" -eq 0 ]; then
    printf '  %sListo.%s\n' "$VERDE" "$FIN"
else
    printf '  %sInstalado, pero el diagnóstico ha encontrado algo. Míralo arriba.%s\n' "$AMBAR" "$FIN"
fi
printf '  Arráncalo con:  ./cazafacturas\n\n'

"""Cazafacturas por línea de comandos.

    python cli.py factura.pdf otra.pdf     analiza ficheros
    python cli.py --banco                  pasa el banco de pruebas
    python cli.py --json factura.pdf       vuelca el resultado en JSON
    python cli.py --csv salida.csv *.pdf   exporta a CSV

Mismo motor que la webapp: sin red, sin claves, sin modelos.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

from backend.nucleo import historial as hist
from backend.nucleo.analizador import (
    Resultado,
    analizar_fichero,
    analizar_json,
    capacidades,
    resumir,
)
from backend.nucleo.lectura import EXTENSIONES_SOPORTADAS
from backend.nucleo.paises import PAISES

RAIZ = Path(__file__).resolve().parent
DATASET = RAIZ / "dataset"
MUESTRAS = DATASET / "pdf"

# La consola de Windows arranca en cp1252 y no admite ✓ ni ─. Se intenta
# subir a UTF-8; si no se puede, se cae a símbolos ASCII.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):  # pragma: no cover
    pass


def _admite_unicode() -> bool:
    try:
        "✓─·".encode(sys.stdout.encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


_UNICODE = _admite_unicode()
BIEN = "✓" if _UNICODE else "OK"
MAL = "✗" if _UNICODE else "X"
OJO = "!"
PUNTO = "·" if _UNICODE else "-"
RAYA = "─" if _UNICODE else "-"

# Colores ANSI. Se apagan solos si la salida no es un terminal.
_TTY = sys.stdout.isatty()
ROJO = "\033[31m" if _TTY else ""
AMBAR = "\033[33m" if _TTY else ""
VERDE = "\033[32m" if _TTY else ""
GRIS = "\033[90m" if _TTY else ""
FUERTE = "\033[1m" if _TTY else ""
FIN = "\033[0m" if _TTY else ""


def _cabecera(texto: str) -> None:
    print(f"\n{FUERTE}{texto}{FIN}")
    print(GRIS + RAYA * min(len(texto), 72) + FIN)


def _imprimir_resultado(r: Resultado, detallado: bool) -> None:
    if not r.ok:
        print(f"{ROJO}{MAL}{FIN} {r.nombre}: {r.error}")
        return

    informe = r.informe or {}
    factura = r.factura or {}
    errores = informe.get("n_errores", 0)
    avisos = informe.get("n_avisos", 0)

    if errores:
        marca, color = MAL, ROJO
    elif avisos:
        marca, color = OJO, AMBAR
    else:
        marca, color = BIEN, VERDE

    resumen_estado = "válida" if not errores else f"{errores} error(es)"
    if avisos:
        resumen_estado += f", {avisos} aviso(s)"

    print(f"{color}{marca}{FIN} {FUERTE}{r.nombre}{FIN}  {GRIS}{resumen_estado}{FIN}")

    numero = factura.get("numero") or "—"
    total = factura.get("total")
    moneda = PAISES[informe.get("pais", "ES")].moneda if informe.get("pais") in PAISES else ""
    linea = f"   {numero}   {factura.get('fecha_emision') or '—'}"
    if total is not None:
        linea += f"   {total:,.2f} {moneda}".replace(",", " ")
    emisor = (factura.get("emisor") or {}).get("nombre")
    if emisor:
        linea += f"   {emisor}"
    print(GRIS + linea + FIN)

    for h in informe.get("hallazgos", []):
        if h["gravedad"] == "error":
            c = ROJO
        elif h["gravedad"] == "aviso":
            c = AMBAR
        else:
            c = GRIS
        print(f"   {c}{PUNTO} {h['mensaje']}{FIN}")
        if detallado and h.get("esperado") is not None:
            print(f"     {GRIS}esperado {h['esperado']} · encontrado {h['encontrado']}{FIN}")

    if r.puntuacion:
        p = r.puntuacion
        print(f"   {GRIS}extracción: {p['aciertos']}/{p['evaluados']} campos "
              f"({p['precision'] * 100:.1f} %){FIN}")
        if detallado:
            for d in p["detalle"]:
                if not d["acierto"]:
                    print(f"     {AMBAR}{d['campo']}: esperaba {d['esperado']!r}, "
                          f"obtuvo {d['obtenido']!r}{FIN}")


def _casos_del_banco(pais: str | None, trampas: bool) -> list[tuple]:
    casos: list[tuple] = []
    for codigo in ([pais] if pais else list(PAISES)):
        carpeta = DATASET / codigo / "esperado"
        if not carpeta.is_dir():
            continue
        for fichero in sorted(carpeta.glob("*.json")):
            esperado = json.loads(fichero.read_text(encoding="utf-8"))
            pdf = MUESTRAS / codigo / f"{fichero.stem}.pdf"
            casos.append((pdf if pdf.is_file() else esperado,
                          pdf.name if pdf.is_file() else fichero.name,
                          esperado, codigo))
    if trampas:
        for fichero in sorted((DATASET / "trampas").glob("*_documento.json")):
            documento = json.loads(fichero.read_text(encoding="utf-8"))
            codigo = str(documento.get("pais") or "ES").upper()
            if pais and codigo != pais:
                continue
            pdf = MUESTRAS / "trampas" / f"{fichero.stem}.pdf"
            casos.append((pdf if pdf.is_file() else documento,
                          pdf.name if pdf.is_file() else fichero.name,
                          None, codigo))
    return casos


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cazafacturas-cli",
        description="Extrae y valida facturas en local. Sin IA, sin red, sin claves.",
    )
    parser.add_argument("ficheros", nargs="*",
                        help=f"PDF o imágenes ({', '.join(sorted(EXTENSIONES_SOPORTADAS))})")
    parser.add_argument("--banco", action="store_true",
                        help="Pasar el banco de pruebas del proyecto")
    parser.add_argument("--sin-trampas", action="store_true",
                        help="En el banco, omitir los casos trampa")
    parser.add_argument("--pais", choices=sorted(PAISES),
                        help="Forzar país en vez de detectarlo")
    parser.add_argument("--json", action="store_true", help="Volcar JSON en bruto")
    parser.add_argument("--csv", metavar="FICHERO", help="Exportar el lote a CSV")
    parser.add_argument("-v", "--detallado", action="store_true",
                        help="Mostrar esperado/encontrado de cada hallazgo")
    parser.add_argument("--capacidades", action="store_true",
                        help="Qué sabe hacer esta instalación")
    args = parser.parse_args()

    if args.capacidades:
        caps = capacidades()
        print(f"PDF con capa de texto : {'sí' if caps['pdf_texto'] else 'no'}")
        print(f"Escaneados e imágenes : {'sí' if caps['escaneados'] else 'no (falta OCR)'}")
        print(f"Formatos              : {', '.join(caps['formatos'])}")
        return 0

    if not args.banco and not args.ficheros:
        parser.print_help()
        return 2

    resultados: list[Resultado] = []

    if args.banco:
        casos = _casos_del_banco(args.pais, not args.sin_trampas)
        if not casos:
            print(f"{ROJO}No se ha encontrado el dataset.{FIN}", file=sys.stderr)
            return 1
        _cabecera(f"Banco de pruebas {PUNTO} {len(casos)} casos")
        for entrada, nombre, esperado, codigo in casos:
            if isinstance(entrada, Path):
                resultados.append(analizar_fichero(entrada, codigo, esperado))
            else:
                resultados.append(analizar_json(entrada, nombre, esperado))
    else:
        rutas: list[Path] = []
        for patron in args.ficheros:
            encontrados = [Path(p) for p in glob.glob(patron)] or [Path(patron)]
            rutas.extend(encontrados)
        faltan = [r for r in rutas if not r.is_file()]
        if faltan:
            for r in faltan:
                print(f"{ROJO}No existe: {r}{FIN}", file=sys.stderr)
            return 1
        _cabecera(f"Análisis {PUNTO} {len(rutas)} documento(s)")
        for ruta in rutas:
            resultados.append(analizar_fichero(ruta, args.pais))

    resumen = resumir(resultados)

    if args.json:
        print(json.dumps(resumen.a_dict(), ensure_ascii=False, indent=2))
        return 0 if resumen.fallidas == 0 else 1

    for r in resultados:
        _imprimir_resultado(r, args.detallado)

    _cabecera("Resumen")
    print(f"  Documentos       {resumen.total}")
    print(f"  {VERDE}Válidas{FIN}          {resumen.validas}")
    print(f"  {ROJO}Con errores{FIN}      {resumen.con_errores}")
    if resumen.fallidas:
        print(f"  {ROJO}Ilegibles{FIN}        {resumen.fallidas}")
    if resumen.precision_media is not None:
        print(f"  Precisión        {resumen.precision_media * 100:.1f} %")
    print(f"  Confianza        {resumen.confianza_media * 100:.1f} %")
    print(f"  Tiempo           {resumen.segundos:.2f} s")

    if resumen.hallazgos_frecuentes:
        _cabecera("Hallazgos más repetidos")
        for h in resumen.hallazgos_frecuentes:
            color = ROJO if h["gravedad"] == "error" else AMBAR
            print(f"  {color}{h['veces']:>3}×{FIN}  {h['mensaje']}")

    if args.csv:
        destino = Path(args.csv)
        destino.write_text(hist.a_csv(resumen.a_dict()), encoding="utf-8")
        print(f"\n{GRIS}CSV escrito en {destino}{FIN}")

    return 0 if resumen.fallidas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

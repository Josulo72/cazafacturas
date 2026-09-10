"""Cazafacturas por línea de comandos.

    python cli.py factura.pdf otra.pdf     analiza ficheros
    python cli.py --banco                  pasa el banco de pruebas
    python cli.py --externo                pasa el banco externo (15 maquetaciones)
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

from backend import diagnostico
from backend.nucleo import banco
from backend.nucleo import banco_externo
from backend.nucleo import historial as hist
from backend.nucleo.analizador import (
    Resultado,
    analizar_fichero,
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


def _pct(v) -> str:
    """Porcentaje a la española: coma decimal y espacio antes del signo."""
    if v is None:
        return '—'
    return f'{v * 100:.1f}'.replace('.', ',') + ' %'


def _doctor(fijar: bool = False) -> int:
    """Revisa la instalación y mide si la calidad ha caído.

    Devuelve 0 si todo está en su sitio y el banco cumple la línea base.
    Ese código de salida es lo que hace que esto sirva en integración
    continua y no solo para mirarlo.
    """
    from backend.diagnostico import Estado

    _cabecera("Instalación")
    entorno = diagnostico.revisar_entorno(hist.dir_datos(RAIZ))
    for c in entorno.comprobaciones:
        marca, color = {
            Estado.BIEN: (BIEN, VERDE),
            Estado.AVISO: (OJO, AMBAR),
            Estado.MAL: (MAL, ROJO),
        }[c.estado]
        print(f"  {color}{marca}{FIN} {c.nombre:<26} {GRIS}{c.detalle}{FIN}")
        if c.remedio:
            print(f"      {AMBAR}{c.remedio}{FIN}")

    if not entorno.sano:
        print(f"\n{ROJO}Falta algo imprescindible. Arréglalo antes de medir.{FIN}")
        return 1

    _cabecera("Banco de pruebas")
    casos = banco.casos()
    if not casos:
        print(f"{ROJO}No se ha encontrado el dataset.{FIN}", file=sys.stderr)
        return 1
    print(f"  {GRIS}{len(casos)} documentos{FIN}")
    metricas = banco.medir(banco.ejecutar())

    print(f"  Precisión de extracción   {_pct(metricas.precision)}")
    print(f"  Facturas conformes        {metricas.conformes}/{metricas.normales}")
    print(f"  Trampas cazadas           {metricas.cazadas}/{metricas.trampas}")
    print(f"  Tiempo                    {metricas.segundos:.2f} s")

    if fijar:
        if not metricas.perfecto:
            print(f"\n{ROJO}No se fija una línea base con fallos dentro.{FIN}")
            print(f"{GRIS}Arregla lo que falla y vuelve a intentarlo.{FIN}")
            return 1
        ruta = banco.escribir_linea_base(metricas, "fijada con --fijar-linea-base")
        print(f"\n{VERDE}Línea base fijada{FIN} {GRIS}en {ruta}{FIN}")
        return 0

    # El banco externo no tiene línea base: tiene que salir perfecto. Son
    # facturas que este código no ha generado, y cualquier fallo ahí es un
    # fallo de verdad.
    externo_ok = True
    if banco_externo.disponible():
        _cabecera("Banco externo")
        externo = banco_externo.ejecutar()
        ok_c, n_c = externo.conformes
        ok_d, n_d = externo.cazadas
        print(f"  Campos leídos bien        {externo.campos_ok}/{externo.campos_total}")
        print(f"  Conformes                 {ok_c}/{n_c}")
        print(f"  Defectuosas, por su motivo {ok_d}/{n_d}")
        print(f"  No legibles               {externo.no_legibles}")
        externo_ok = externo.perfecto
        if not externo_ok:
            for c in externo.casos:
                if not c.correcto:
                    print(f"  {ROJO}{MAL}{FIN} {c.fichero}  {GRIS}python cli.py --externo{FIN}")

    base = banco.leer_linea_base()
    if base is None:
        print(f"\n{AMBAR}No hay línea base con la que comparar.{FIN}")
        print(f"{GRIS}Fíjala con: python cli.py --fijar-linea-base{FIN}")
        return 0

    _cabecera(f"Comparación con la línea base {PUNTO} {base.get('fijada', '')[:10]}")
    desvios = diagnostico.comparar(base, metricas)
    if not desvios:
        print(f"  {VERDE}{BIEN}{FIN} Nada ha empeorado.")
        return 0 if externo_ok else 1

    for d in desvios:
        print(f"  {ROJO}{MAL}{FIN} {FUERTE}{d.medida}{FIN}")
        print(f"      línea base {d.base}   {ROJO}ahora {d.ahora}{FIN}")
        if d.detalle:
            print(f"      {GRIS}{d.detalle}{FIN}")
    print(f"\n{ROJO}{len(desvios)} regresión(es).{FIN}")
    return 1


def _euros(v) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _externo() -> int:
    """El banco externo, como tabla del libro: una fila por factura."""
    if not banco_externo.disponible():
        print(f"{ROJO}No está dataset/externo.{FIN}", file=sys.stderr)
        return 1
    informe = banco_externo.ejecutar()
    _cabecera(f"Banco externo {PUNTO} {len(informe.casos)} facturas")
    etiquetas = {"conforme": "Conforme", "con_avisos": "Con avisos",
                 "no_conforme": "No conforme", "no_legible": "No legible"}
    for c in informe.casos:
        obtenido = {x.nombre: x.obtenido for x in c.campos}
        color = VERDE if c.correcto else ROJO
        marca = BIEN if c.correcto else MAL
        print(f"  {color}{marca}{FIN} {c.fichero[:28]:<28} "
              f"{str(obtenido.get('numero') or '—')[:15]:<15} "
              f"{_euros(obtenido.get('base')):>13} {_euros(obtenido.get('total')):>13}  "
              f"{etiquetas.get(c.estado, c.estado)}"
              + (f" {GRIS}por {c.motivo}{FIN}" if c.motivo and c.por_su_motivo else ""))
        for x in c.campos_mal:
            print(f"      {ROJO}{x.nombre}{FIN}: esperado {x.esperado!r}, leído {x.obtenido!r}")
        if c.ruido:
            print(f"      {AMBAR}además salta: {', '.join(c.ruido)}{FIN}")

    ok_c, n_c = informe.conformes
    ok_d, n_d = informe.cazadas
    _cabecera("Resumen")
    print(f"  Campos leídos bien        {informe.campos_ok}/{informe.campos_total}")
    print(f"  Conformes                 {ok_c}/{n_c}")
    print(f"  Defectuosas, por su motivo {ok_d}/{n_d}")
    print(f"  No legibles               {informe.no_legibles}")
    print(f"  Tiempo                    {informe.segundos:.2f} s")
    return 0 if informe.perfecto else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cazafacturas-cli",
        description="Extrae y valida facturas en local. Sin IA, sin red, sin claves.",
    )
    parser.add_argument("ficheros", nargs="*",
                        help=f"PDF o imágenes ({', '.join(sorted(EXTENSIONES_SOPORTADAS))})")
    parser.add_argument("--banco", action="store_true",
                        help="Pasar el banco de pruebas del proyecto")
    parser.add_argument("--externo", action="store_true",
                        help="Pasar el banco externo: 23 facturas de 15 "
                             "maquetaciones de terceros")
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
    parser.add_argument("--doctor", action="store_true",
                        help="Revisar la instalación y comprobar que no ha "
                             "empeorado respecto de la línea base")
    parser.add_argument("--fijar-linea-base", action="store_true",
                        dest="fijar_linea_base",
                        help="Guardar el resultado actual como línea base "
                             "(solo si sale perfecto)")
    args = parser.parse_args()

    if args.doctor or args.fijar_linea_base:
        return _doctor(fijar=args.fijar_linea_base)

    if args.externo:
        return _externo()

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
        casos = banco.casos(args.pais, not args.sin_trampas)
        if not casos:
            print(f"{ROJO}No se ha encontrado el dataset.{FIN}", file=sys.stderr)
            return 1
        _cabecera(f"Banco de pruebas {PUNTO} {len(casos)} casos")
        resultados = [banco.analizar(c) for c in casos]
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

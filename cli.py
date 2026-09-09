from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from backend.api.ejecutar import ejecutar_dataset
from backend.api.motores import CatalogoMotores, crear_catalogo
from backend.nucleo.cache import CacheResultados
from backend.nucleo.dataset import Caso, cargar_dataset
from backend.nucleo.evaluador import ResultadoEvaluacion, evaluar_respuesta_json
from backend.nucleo.motores.base import EstadoMotor

I18N = {
    "es": {
        "cabecera_motores": "=== Motor o no con qué trabajar ===",
        "evaluando": "Evaluando {n} casos con motor '{motor}'...",
        "estado": "(estado: {estado})",
        "no_disponible": "\nMotor '{motor}' no disponible. Ejecuta '--listar' para ver estados.",
        "distribucion": "=== Distribución por estado ===",
        "aciertos": "  Aciertos:",
        "fallos": "  Fallos:",
        "invenciones": "  Invenciones:",
        "precision": "Precisión:",
        "tasa": "Tasa de invención:",
        "inven_por_campo": "=== Invenciones por campo ===",
        "tiempo_motor": "\nTiempo de motor: {s:.2f} s  (cacheados: {n})",
        "tiempo_total": "\nTiempo total: {s:.2f} s",
        "mensaje_error": "  ERROR: {msg}",
    },
    "en": {
        "cabecera_motores": "=== Motor availiability ===",
        "evaluando": "Evaluating {n} cases with motor '{motor}'...",
        "estado": "(state: {estado})",
        "no_disponible": "\nMotor '{motor}' not available. Run '--listar' to see states.",
        "distribucion": "=== Breakdown by state ===",
        "aciertos": "  Correct:",
        "fallos": "  Wrong:",
        "invenciones": "  Invented:",
        "precision": "Precision:",
        "tasa": "Invention rate:",
        "inven_por_campo": "=== Inventions by field ===",
        "tiempo_motor": "\nMotor time: {s:.2f} s  (cached: {n})",
        "tiempo_total": "\nTotal time: {s:.2f} s",
        "mensaje_error": "  ERROR: {msg}",
    },
}


def _motor_oraculo(caso: Caso, *_) -> str:
    return json.dumps(caso.esperado, ensure_ascii=False)


def _resumen(resultados: list[ResultadoEvaluacion], t) -> None:
    total_aciertos = sum(len(r.aciertos) for r in resultados)
    total_fallos = sum(len(r.fallos) for r in resultados)
    total_invenciones = sum(len(r.invenciones) for r in resultados)
    relevantes = total_aciertos + total_fallos
    precision = round(total_aciertos / relevantes, 4) if relevantes else 0.0
    tasa_invencion = (
        round(total_invenciones / (relevantes + total_invenciones), 4)
        if (relevantes + total_invenciones)
        else 0.0
    )

    print()
    print(t["distribucion"])
    print(f"{t['aciertos']}    {total_aciertos}")
    print(f"{t['fallos']}      {total_fallos}")
    print(f"{t['invenciones']} {total_invenciones}")
    print()
    print(f"{t['precision']}        {precision:.2%}")
    print(f"{t['tasa']} {tasa_invencion:.2%}")

    inven_por_campo: dict[str, int] = {}
    for r in resultados:
        for c in r.invenciones:
            inven_por_campo[c.campo] = inven_por_campo.get(c.campo, 0) + 1
    if inven_por_campo:
        print()
        print(t["inven_por_campo"])
        for campo, n in sorted(inven_por_campo.items(), key=lambda x: -x[1]):
            print(f"  {campo}: {n}")


def _listar_motores(catalogo: CatalogoMotores, t) -> None:
    print(t["cabecera_motores"])
    for id_motor, info in catalogo.todos_dispuestos():
        marca = {"disponible": "[X]", "no_instalado": "[ ]", "sin_configurar": "[ ]"}
        detalle = f" — {info.detalle}" if info.detalle else ""
        print(f"  {marca[info.estado.value]:10s} {id_motor:14s} {info.estado.value:<15s}{detalle}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cazafacturas — banco de evaluación de facturas (consola)"
    )
    parser.add_argument(
        "--motor",
        default="oraculo",
        help="Motor a usar: oraculo, cli, ollama, api:anthropic, api:openai, api:google. "
        "Por defecto 'oraculo' (validación del pipeline).",
    )
    parser.add_argument("--listar", action="store_true", help="Mostrar motores disponibles")
    parser.add_argument("--trampas", action="store_true", help="Incluir casos trampa")
    parser.add_argument("--no-cache", action="store_true", help="Ignorar la caché")
    parser.add_argument(
        "--idioma",
        default="es",
        choices=("es", "en"),
        help="Idioma del prompt y de los mensajes. Por defecto 'es'",
    )
    parser.add_argument(
        "--prompt-extra",
        default="",
        help="Notas adicionales que se añaden al prompt del motor",
    )
    parser.add_argument(
        "--modelo",
        default=None,
        help="Modelo para el motor CLI (ej: sonnet, opus). Requiere --motor cli",
    )
    args = parser.parse_args()

    t = I18N.get(args.idioma, I18N["es"])
    catalogo = crear_catalogo(modelo_cli=args.modelo)
    if args.listar:
        _listar_motores(catalogo, t)
        return

    dataset = cargar_dataset()
    casos = dataset.todos() if args.trampas else dataset.casos_normales()

    if args.motor == "oraculo":
        print(t["evaluando"].format(n=len(casos), motor="oraculo"))
        resultados: list[ResultadoEvaluacion] = []
        inicio = time.perf_counter()
        for caso in casos:
            respuesta = _motor_oraculo(caso)
            etiqueta = f"[trampa] {caso.id}" if caso.es_trampa else caso.id
            resultado = evaluar_respuesta_json(respuesta, caso.esperado, etiqueta)
            resultados.append(resultado)
            print(
                f"  {etiqueta:30s} precisión {resultado.precision:.2%}  "
                f"invención {resultado.tasa_invencion:.2%}"
            )
        segundos = time.perf_counter() - inicio
        _resumen(resultados, t)
        print(t["tiempo_total"].format(s=segundos))
        return

    info_cli = catalogo.cli.detectar()
    print(
        t["evaluando"].format(n=len(casos), motor=args.motor)
        + " "
        + t["estado"].format(estado=info_cli.estado.value)
    )

    if args.motor not in catalogo.disponible():
        print(t["no_disponible"].format(motor=args.motor))
        return

    cache = CacheResultados(Path(__file__).resolve().parent / "resultados" / "cache")
    resultados = ejecutar_dataset(
        casos,
        args.motor,
        catalogo,
        cache,
        progress=None,
        prompt_extra=args.prompt_extra,
        idioma=args.idioma,
        usar_cache=not args.no_cache,
    )

    cacheados = sum(1 for r in resultados if r.metadatos and r.metadatos.cacheado)
    total_seg = sum((r.metadatos.segundos for r in resultados if r.metadatos), 0.0)
    print()
    for resultado in resultados:
        extra = ""
        if resultado.fallos_validacion:
            extra = t["mensaje_error"].format(msg=resultado.fallos_validacion[0][:80])
        print(
            f"  {resultado.factura:30s} precisión {resultado.precision:.2%}  "
            f"invención {resultado.tasa_invencion:.2%}  "
            f"aciertos {len(resultado.aciertos)}  fallos {len(resultado.fallos)}  "
            f"inventa {len(resultado.invenciones)}{extra}"
        )
    _resumen(resultados, t)
    print(t["tiempo_motor"].format(s=total_seg, n=cacheados))


if __name__ == "__main__":
    main()
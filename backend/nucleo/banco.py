"""El banco de pruebas: los casos y cómo se puntúan.

Este proyecto tiene algo que casi ninguno tiene: una verdad conocida. Para
64 documentos está escrito de antemano cuál es la respuesta correcta, así
que la calidad del extractor no es una opinión, es un número.

Esto vive aparte porque lo usan tres sitios —la webapp, la línea de comandos
y el diagnóstico— y tenerlo por triplicado garantiza que los tres midan
cosas ligeramente distintas.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

from backend.nucleo.analizador import (
    Resultado,
    ResumenLote,
    analizar_bytes,
    analizar_json,
    resumir,
)
from backend.nucleo.paises import PAISES

RAIZ = Path(__file__).resolve().parents[2]
DATASET = RAIZ / "dataset"
MUESTRAS = DATASET / "pdf"
LINEA_BASE = DATASET / "linea_base.json"


@dataclass
class Caso:
    """Un documento del banco y lo que debería salir de él."""
    nombre: str
    contenido: Union[bytes, dict]     # PDF en bytes, o el documento ya estructurado
    esperado: Optional[dict]          # None en los casos trampa: no hay «correcto»
    pais: Optional[str]

    @property
    def es_trampa(self) -> bool:
        return self.esperado is None


def casos(pais: Optional[str] = None, trampas: bool = True) -> list[Caso]:
    """Los casos del banco.

    Se prefieren los PDF porque ejercitan la cadena entera —lectura,
    extracción y validación—. Si no se han generado, se cae al JSON y
    entonces solo se ponen a prueba las reglas fiscales. La distinción
    importa: sin PDF, el banco mide la mitad.
    """
    salida: list[Caso] = []
    codigos = [pais.upper()] if pais else list(PAISES)

    for codigo in codigos:
        carpeta = DATASET / codigo / "esperado"
        if not carpeta.is_dir():
            continue
        for fichero in sorted(carpeta.glob("*.json")):
            esperado = json.loads(fichero.read_text(encoding="utf-8"))
            pdf = MUESTRAS / codigo / f"{fichero.stem}.pdf"
            if pdf.is_file():
                salida.append(Caso(pdf.name, pdf.read_bytes(), esperado, codigo))
            else:
                salida.append(Caso(fichero.name, esperado, esperado, codigo))

    if trampas:
        for fichero in sorted((DATASET / "trampas").glob("*_documento.json")):
            documento = json.loads(fichero.read_text(encoding="utf-8"))
            codigo = str(documento.get("pais") or "ES").upper()
            if pais and codigo != pais.upper():
                continue
            pdf = MUESTRAS / "trampas" / f"{fichero.stem}.pdf"
            if pdf.is_file():
                salida.append(Caso(pdf.name, pdf.read_bytes(), None, codigo))
            else:
                salida.append(Caso(fichero.name, documento, None, None))

    return salida


def analizar(caso: Caso) -> Resultado:
    if isinstance(caso.contenido, dict):
        return analizar_json(caso.contenido, caso.nombre, caso.esperado)
    return analizar_bytes(caso.contenido, caso.nombre, caso.pais, caso.esperado)


def ejecutar(pais: Optional[str] = None, trampas: bool = True,
             progreso: Optional[Callable[[int, int, str], None]] = None,
             id_lote: Optional[str] = None) -> ResumenLote:
    lista = casos(pais, trampas)
    resultados: list[Resultado] = []
    for i, caso in enumerate(lista, start=1):
        if progreso:
            progreso(i, len(lista), caso.nombre)
        resultados.append(analizar(caso))
    return resumir(resultados, id_lote)


# ---------------------------------------------------------------------------
# Las métricas
# ---------------------------------------------------------------------------

@dataclass
class Metricas:
    """Lo que se mide. Cuatro números y el desglose de lo que falla."""
    precision: Optional[float]        # aciertos campo a campo sobre el esperado
    conformes: int                    # facturas normales que salen válidas
    normales: int
    cazadas: int                      # trampas en las que salta al menos una regla
    trampas: int
    segundos: float
    fallos_por_campo: dict[str, int]
    trampas_escapadas: list[str]

    @property
    def perfecto(self) -> bool:
        return (self.precision == 1.0
                and self.conformes == self.normales
                and self.cazadas == self.trampas)

    def a_dict(self) -> dict:
        return {
            "precision": self.precision,
            "conformes": self.conformes,
            "normales": self.normales,
            "cazadas": self.cazadas,
            "trampas": self.trampas,
            "segundos": round(self.segundos, 2),
            "fallos_por_campo": self.fallos_por_campo,
            "trampas_escapadas": self.trampas_escapadas,
        }


def medir(resumen: ResumenLote) -> Metricas:
    con_esperado = [r for r in resumen.resultados if r.get("puntuacion")]
    trampas = [r for r in resumen.resultados if not r.get("puntuacion")]

    fallos: dict[str, int] = {}
    for r in con_esperado:
        for d in r["puntuacion"]["detalle"]:
            if not d["acierto"]:
                fallos[d["campo"]] = fallos.get(d["campo"], 0) + 1

    escapadas = [
        r["nombre"] for r in trampas
        if not (r.get("informe") or {}).get("hallazgos")
    ]

    return Metricas(
        precision=resumen.precision_media,
        conformes=sum(1 for r in con_esperado if (r.get("informe") or {}).get("valida")),
        normales=len(con_esperado),
        cazadas=len(trampas) - len(escapadas),
        trampas=len(trampas),
        segundos=resumen.segundos,
        fallos_por_campo=dict(sorted(fallos.items(), key=lambda kv: -kv[1])),
        trampas_escapadas=sorted(escapadas),
    )


# ---------------------------------------------------------------------------
# La línea base
# ---------------------------------------------------------------------------

def leer_linea_base() -> Optional[dict]:
    if not LINEA_BASE.is_file():
        return None
    try:
        return json.loads(LINEA_BASE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def escribir_linea_base(metricas: Metricas, nota: str = "") -> Path:
    from datetime import datetime, timezone
    LINEA_BASE.write_text(json.dumps({
        "fijada": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "nota": nota,
        **metricas.a_dict(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return LINEA_BASE

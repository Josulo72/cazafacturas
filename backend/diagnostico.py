"""Diagnóstico: qué falta para que esto funcione, y si ha empeorado.

Son dos preguntas distintas y las dos importan.

La primera es de instalación: falta el OCR, falta el dataset, no hay
permisos para escribir. Eso se responde mirando el entorno y se contesta con
el comando exacto que lo arregla.

La segunda es de calidad, y es la interesante. Este proyecto tiene una
verdad conocida: para 64 documentos está escrito de antemano cuál es la
respuesta correcta. Así que se puede fijar una línea base —100 % de
precisión, 50 de 50 trampas, tanto tiempo—, dejarla en el repositorio, y
después preguntarle a la máquina si sigue cumpliéndola. Cuando un cambio en
el extractor baja la precisión al 96 %, el diagnóstico dice qué campos han
empezado a fallar. Eso no es un `try/except`: es una regresión medida.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional

from backend.nucleo import banco
from backend.nucleo.lectura import capacidades

PYTHON_MINIMO = (3, 10)

# Cuánto puede tardar de más antes de considerarlo una regresión. Un poco de
# margen, porque la máquina que mide hoy no es la que fijó la línea base.
MARGEN_TIEMPO = 2.5

# Por debajo de esto el OCR no tiene sitio para trabajar.
DISCO_MINIMO_MB = 500


class Estado(str, Enum):
    BIEN = "bien"
    AVISO = "aviso"
    MAL = "mal"


@dataclass
class Comprobacion:
    nombre: str
    estado: Estado
    detalle: str
    remedio: str = ""

    def a_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "estado": self.estado.value,
            "detalle": self.detalle,
            "remedio": self.remedio,
        }


@dataclass
class Informe:
    comprobaciones: list[Comprobacion] = field(default_factory=list)

    @property
    def peor(self) -> Estado:
        if any(c.estado is Estado.MAL for c in self.comprobaciones):
            return Estado.MAL
        if any(c.estado is Estado.AVISO for c in self.comprobaciones):
            return Estado.AVISO
        return Estado.BIEN

    @property
    def sano(self) -> bool:
        return self.peor is not Estado.MAL

    def a_dict(self) -> dict:
        return {
            "estado": self.peor.value,
            "sano": self.sano,
            "comprobaciones": [c.a_dict() for c in self.comprobaciones],
        }


# ---------------------------------------------------------------------------
# El entorno
# ---------------------------------------------------------------------------

def _version(paquete: str) -> Optional[str]:
    try:
        return version(paquete)
    except PackageNotFoundError:
        return None


def revisar_entorno(dir_datos: Optional[Path] = None) -> Informe:
    """Qué sabe hacer esta instalación, y qué le falta.

    Nada de esto ejecuta el banco: tiene que responder en milisegundos
    porque lo consulta la interfaz al arrancar.
    """
    inf = Informe()
    caps = capacidades()

    # --- Python ---------------------------------------------------------
    v = sys.version_info
    inf.comprobaciones.append(Comprobacion(
        "Python",
        Estado.BIEN if v[:2] >= PYTHON_MINIMO else Estado.MAL,
        f"{v.major}.{v.minor}.{v.micro}",
        "" if v[:2] >= PYTHON_MINIMO
        else f"Hace falta Python {PYTHON_MINIMO[0]}.{PYTHON_MINIMO[1]} o superior.",
    ))

    # --- Lectura de PDF -------------------------------------------------
    ver = _version("pdfplumber")
    inf.comprobaciones.append(Comprobacion(
        "Lectura de PDF",
        Estado.BIEN if caps["pdf_texto"] else Estado.MAL,
        f"pdfplumber {ver}" if ver else "no instalado",
        "" if caps["pdf_texto"] else 'pip install "cazafacturas"',
    ))

    # --- OCR ------------------------------------------------------------
    hay_ocr = caps["ocr"] and caps["rasterizado"]
    piezas = [f"rapidocr {_version('rapidocr-onnxruntime')}" if caps["ocr"] else None,
              f"pypdfium2 {_version('pypdfium2')}" if caps["rasterizado"] else None]
    inf.comprobaciones.append(Comprobacion(
        "OCR (escaneados y fotos)",
        Estado.BIEN if hay_ocr else Estado.AVISO,
        " · ".join(p for p in piezas if p) if hay_ocr
        else "no instalado: solo se leen PDF con capa de texto",
        "" if hay_ocr else 'pip install "cazafacturas[ocr]"',
    ))

    # --- Dataset --------------------------------------------------------
    try:
        n_normales = len([c for c in banco.casos(trampas=False)])
        n_trampas = len(banco.casos(trampas=True)) - n_normales
    except Exception:                                    # pragma: no cover
        n_normales = n_trampas = 0
    hay_dataset = n_normales > 0
    inf.comprobaciones.append(Comprobacion(
        "Banco de pruebas",
        Estado.BIEN if hay_dataset else Estado.AVISO,
        f"{n_normales} facturas y {n_trampas} casos trampa" if hay_dataset
        else "no encontrado",
        "" if hay_dataset else "python -m dataset.generador",
    ))

    # --- Muestras en PDF ------------------------------------------------
    # Sin PDF el banco solo pone a prueba las reglas, no la lectura. Es una
    # diferencia grande y merece decirse.
    n_pdf = len(list(banco.MUESTRAS.rglob("*.pdf"))) if banco.MUESTRAS.is_dir() else 0
    inf.comprobaciones.append(Comprobacion(
        "Muestras en PDF",
        Estado.BIEN if n_pdf else Estado.AVISO,
        f"{n_pdf} PDF" if n_pdf
        else "sin generar: el banco medirá las reglas, no la lectura",
        "" if n_pdf else "python -m dataset.render_pdf",
    ))

    # --- Disco y escritura ----------------------------------------------
    if dir_datos:
        escribible = True
        try:
            prueba = dir_datos / ".prueba_escritura"
            prueba.write_text("", encoding="utf-8")
            prueba.unlink()
        except OSError as e:
            escribible = False
            motivo = str(e)
        libres_mb = shutil.disk_usage(dir_datos).free // (1024 * 1024)
        if not escribible:
            estado, detalle = Estado.MAL, f"no se puede escribir: {motivo}"
        elif libres_mb < DISCO_MINIMO_MB:
            estado, detalle = Estado.AVISO, f"solo {libres_mb} MB libres"
        else:
            estado, detalle = Estado.BIEN, f"{libres_mb} MB libres en {dir_datos}"
        inf.comprobaciones.append(Comprobacion("Almacenamiento", estado, detalle))

    return inf


# ---------------------------------------------------------------------------
# La regresión
# ---------------------------------------------------------------------------

def _pct(v) -> str:
    """Porcentaje a la española: coma decimal y espacio antes del signo."""
    return '—' if v is None else f'{v * 100:.1f}'.replace('.', ',') + ' %'


@dataclass
class Desvio:
    """Una medida que ha empeorado respecto de la línea base."""
    medida: str
    base: object
    ahora: object
    detalle: str = ""


def comparar(base: dict, ahora: banco.Metricas) -> list[Desvio]:
    """Qué ha empeorado. Lo que mejora no es un desvío: es una buena noticia."""
    desvios: list[Desvio] = []

    b_prec = base.get("precision")
    if b_prec is not None and ahora.precision is not None and ahora.precision < b_prec:
        peores = ", ".join(
            f"{campo} ({veces})" for campo, veces in
            list(ahora.fallos_por_campo.items())[:5]
        )
        desvios.append(Desvio(
            "Precisión de extracción", _pct(b_prec), _pct(ahora.precision),
            f"Campos que fallan: {peores}" if peores else "",
        ))

    if ahora.conformes < base.get("conformes", 0):
        desvios.append(Desvio(
            "Facturas conformes",
            f"{base['conformes']}/{base.get('normales', '?')}",
            f"{ahora.conformes}/{ahora.normales}",
            "Facturas correctas que el validador ha empezado a rechazar.",
        ))

    if ahora.cazadas < base.get("cazadas", 0):
        desvios.append(Desvio(
            "Trampas cazadas",
            f"{base['cazadas']}/{base.get('trampas', '?')}",
            f"{ahora.cazadas}/{ahora.trampas}",
            "Se escapan: " + ", ".join(ahora.trampas_escapadas[:5])
            if ahora.trampas_escapadas else "",
        ))

    b_seg = base.get("segundos")
    if b_seg and ahora.segundos > b_seg * MARGEN_TIEMPO:
        desvios.append(Desvio(
            "Tiempo", f"{b_seg:.1f} s", f"{ahora.segundos:.1f} s",
            f"Más de {MARGEN_TIEMPO:g} veces lo esperado.",
        ))

    return desvios

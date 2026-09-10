"""Orquestador: de un fichero a un informe completo.

    fichero -> lectura (texto/OCR) -> extractor (campos) -> validador (reglas)

Y, si existe un `esperado` con el que comparar, además puntúa cuánto acierta
el extractor. Esa es la métrica honesta del proyecto: no mide un modelo
ajeno, mide este código.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.nucleo import lectura
from backend.nucleo.extractor import Extraccion, extraer
from backend.nucleo.lectura import Documento, LecturaNoSoportada, Origen
from backend.nucleo.validador import Gravedad, Hallazgo, Informe, validar

# Campos que se comparan al puntuar contra un esperado.
CAMPOS_PUNTUABLES = (
    "numero", "fecha_emision", "fecha_vencimiento",
    "base_imponible", "total", "emisor.nif", "emisor.nombre",
    "receptor.nif", "receptor.nombre",
)

TOLERANCIA_IMPORTE = 0.02


@dataclass
class Comparacion:
    campo: str
    esperado: Any
    obtenido: Any
    acierto: bool

    def a_dict(self) -> dict:
        return {
            "campo": self.campo,
            "esperado": self.esperado,
            "obtenido": self.obtenido,
            "acierto": self.acierto,
        }


@dataclass
class Puntuacion:
    aciertos: int = 0
    fallos: int = 0
    ausentes: int = 0
    detalle: list[Comparacion] = field(default_factory=list)

    @property
    def evaluados(self) -> int:
        return self.aciertos + self.fallos + self.ausentes

    @property
    def precision(self) -> float:
        return round(self.aciertos / self.evaluados, 4) if self.evaluados else 0.0

    def a_dict(self) -> dict:
        return {
            "aciertos": self.aciertos,
            "fallos": self.fallos,
            "ausentes": self.ausentes,
            "evaluados": self.evaluados,
            "precision": self.precision,
            "detalle": [c.a_dict() for c in self.detalle],
        }


@dataclass
class Resultado:
    id: str
    nombre: str
    ok: bool
    segundos: float
    documento: Optional[dict] = None
    extraccion: Optional[dict] = None
    factura: Optional[dict] = None
    informe: Optional[dict] = None
    puntuacion: Optional[dict] = None
    error: Optional[str] = None
    fecha: str = ""

    def a_dict(self) -> dict:
        return {
            "id": self.id,
            "nombre": self.nombre,
            "ok": self.ok,
            "segundos": round(self.segundos, 3),
            "fecha": self.fecha,
            "documento": self.documento,
            "extraccion": self.extraccion,
            "factura": self.factura,
            "informe": self.informe,
            "puntuacion": self.puntuacion,
            "error": self.error,
        }


# --------------------------------------------------------------------------
# Comparación contra el esperado
# --------------------------------------------------------------------------

def _leer_ruta(datos: dict, ruta: str) -> Any:
    actual: Any = datos
    for tramo in ruta.split("."):
        if not isinstance(actual, dict):
            return None
        actual = actual.get(tramo)
    return actual


def _iguales(campo: str, esperado: Any, obtenido: Any) -> bool:
    if esperado is None and obtenido is None:
        return True
    if esperado is None or obtenido is None:
        return False

    if isinstance(esperado, (int, float)) and not isinstance(esperado, bool):
        try:
            return abs(float(obtenido) - float(esperado)) <= TOLERANCIA_IMPORTE
        except (TypeError, ValueError):
            return False

    if campo.startswith("fecha"):
        def _f(v: Any) -> str:
            if isinstance(v, (date, datetime)):
                return v.isoformat()[:10]
            return str(v)[:10]
        return _f(esperado) == _f(obtenido)

    if campo.endswith("nif"):
        limpiar = lambda v: str(v).replace("-", "").replace(" ", "").upper()
        return limpiar(esperado) == limpiar(obtenido)

    # Texto: comparación laxa, que el OCR mete ruido de espacios y mayúsculas.
    normal = lambda v: " ".join(str(v).lower().split())
    return normal(esperado) == normal(obtenido)


def puntuar(factura: dict, esperado: dict) -> Puntuacion:
    p = Puntuacion()
    for campo in CAMPOS_PUNTUABLES:
        valor_esperado = _leer_ruta(esperado, campo)
        if valor_esperado is None:
            continue
        valor_obtenido = _leer_ruta(factura, campo)
        acierto = _iguales(campo, valor_esperado, valor_obtenido)
        if acierto:
            p.aciertos += 1
        elif valor_obtenido is None:
            p.ausentes += 1
        else:
            p.fallos += 1
        p.detalle.append(Comparacion(campo, valor_esperado, valor_obtenido, acierto))
    return p


# --------------------------------------------------------------------------
# Análisis
# --------------------------------------------------------------------------

def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ilegible(doc: Optional[Documento], factura: dict) -> bool:
    """¿Falta lo que hace falta para decir si la factura cuadra?

    «No conforme» afirma que la factura está mal; solo se puede afirmar con
    los importes delante. Si no se han podido leer ni la base ni el total, o
    no hay rastro del impuesto ni del total, lo honrado es decir que no se ha
    podido leer. Un número de factura o un NIF que no aparecen no cuentan
    aquí: en un documento legible, que falten es un defecto de la factura.
    """
    if doc is not None and doc.origen is Origen.VACIO:
        return True
    base, total = factura.get("base_imponible"), factura.get("total")
    if base is None and total is None:
        return True
    return not factura.get("iva") and total is None


def estado(informe: dict) -> str:
    """Conforme · con avisos · no conforme · no legible."""
    codigos = {h["codigo"] for h in informe.get("hallazgos", [])}
    if "NO_LEGIBLE" in codigos:
        return "no_legible"
    if informe.get("n_errores"):
        return "no_conforme"
    if informe.get("n_avisos"):
        return "con_avisos"
    return "conforme"


def _analizar_documento(doc: Documento, pais: Optional[str],
                        esperado: Optional[dict], inicio: float) -> Resultado:
    ex: Extraccion = extraer(doc, pais)
    factura = ex.a_factura()
    informe: Informe = validar(factura, ex.pais)
    if _ilegible(doc, factura):
        informe.hallazgos.insert(0, Hallazgo(
            "NO_LEGIBLE", Gravedad.ERROR, "documento",
            "No se han podido leer los importes: falta la base, el impuesto "
            "o el total. No se puede decir si la factura cuadra; revísala a mano.",
        ))
    dict_informe = informe.a_dict()
    dict_informe["estado"] = estado(dict_informe)

    return Resultado(
        id=uuid.uuid4().hex[:12],
        nombre=doc.nombre,
        ok=True,
        segundos=time.perf_counter() - inicio,
        fecha=_ahora(),
        documento=doc.a_dict(),
        extraccion=ex.a_dict(),
        factura=factura,
        informe=dict_informe,
        puntuacion=puntuar(factura, esperado).a_dict() if esperado else None,
    )


def analizar_bytes(contenido: bytes, nombre: str, pais: Optional[str] = None,
                   esperado: Optional[dict] = None,
                   permitir_ocr: bool = True) -> Resultado:
    inicio = time.perf_counter()
    try:
        doc = lectura.leer_bytes(contenido, nombre, permitir_ocr)
    except LecturaNoSoportada as e:
        return Resultado(
            id=uuid.uuid4().hex[:12], nombre=nombre, ok=False,
            segundos=time.perf_counter() - inicio, fecha=_ahora(), error=str(e),
        )
    except Exception as e:  # pragma: no cover - PDF corrupto, imagen ilegible…
        return Resultado(
            id=uuid.uuid4().hex[:12], nombre=nombre, ok=False,
            segundos=time.perf_counter() - inicio, fecha=_ahora(),
            error=f"No se ha podido leer el fichero: {e}",
        )
    return _analizar_documento(doc, pais, esperado, inicio)


def analizar_fichero(ruta: str | Path, pais: Optional[str] = None,
                     esperado: Optional[dict] = None,
                     permitir_ocr: bool = True) -> Resultado:
    ruta = Path(ruta)
    return analizar_bytes(ruta.read_bytes(), ruta.name, pais, esperado, permitir_ocr)


def analizar_json(datos: dict, nombre: str = "documento.json",
                  esperado: Optional[dict] = None) -> Resultado:
    """Valida una factura que ya viene estructurada.

    Sirve para el dataset del proyecto, donde los casos son JSON y lo que se
    pone a prueba son las reglas fiscales, no la lectura del papel.
    """
    inicio = time.perf_counter()
    pais = str(datos.get("pais") or "ES").upper()
    informe = validar(datos, pais).a_dict()
    informe["estado"] = estado(informe)
    return Resultado(
        id=uuid.uuid4().hex[:12],
        nombre=nombre,
        ok=True,
        segundos=time.perf_counter() - inicio,
        fecha=_ahora(),
        documento={"nombre": nombre, "paginas": 0, "origen": "json",
                   "confianza": 1.0, "caracteres": 0, "avisos": []},
        extraccion=None,
        factura=datos,
        informe=informe,
        puntuacion=puntuar(datos, esperado).a_dict() if esperado else None,
    )


# --------------------------------------------------------------------------
# Lote
# --------------------------------------------------------------------------

@dataclass
class ResumenLote:
    id: str
    total: int
    validas: int
    con_errores: int
    fallidas: int
    segundos: float
    precision_media: Optional[float]
    confianza_media: float
    hallazgos_frecuentes: list[dict]
    resultados: list[dict]
    no_legibles: int = 0

    def a_dict(self) -> dict:
        return self.__dict__


def resumir(resultados: list[Resultado], id_lote: Optional[str] = None) -> ResumenLote:
    ok = [r for r in resultados if r.ok]
    validas = sum(1 for r in ok if r.informe and r.informe["valida"])
    fallidas = len(resultados) - len(ok)

    conteo: dict[str, dict] = {}
    for r in ok:
        for h in (r.informe or {}).get("hallazgos", []):
            entrada = conteo.setdefault(
                h["codigo"],
                {"codigo": h["codigo"], "gravedad": h["gravedad"],
                 "mensaje": h["mensaje"], "veces": 0},
            )
            entrada["veces"] += 1

    precisiones = [r.puntuacion["precision"] for r in ok if r.puntuacion]
    confianzas = [
        r.extraccion["confianza"] for r in ok
        if r.extraccion and r.extraccion.get("confianza") is not None
    ]

    return ResumenLote(
        id=id_lote or uuid.uuid4().hex[:12],
        total=len(resultados),
        validas=validas,
        con_errores=len(ok) - validas,
        fallidas=fallidas,
        segundos=round(sum(r.segundos for r in resultados), 3),
        precision_media=(
            round(sum(precisiones) / len(precisiones), 4) if precisiones else None
        ),
        confianza_media=(
            round(sum(confianzas) / len(confianzas), 4) if confianzas else 0.0
        ),
        hallazgos_frecuentes=sorted(
            conteo.values(), key=lambda h: h["veces"], reverse=True
        )[:10],
        resultados=[r.a_dict() for r in resultados],
        no_legibles=sum(1 for r in resultados
                        if not r.ok or (r.informe or {}).get("estado") == "no_legible"),
    )


def capacidades() -> dict:
    """Qué sabe hacer esta instalación. La interfaz lo enseña al arrancar."""
    caps = lectura.capacidades()
    return {
        **caps,
        "formatos": sorted(lectura.EXTENSIONES_SOPORTADAS),
        "escaneados": caps["ocr"] and caps["rasterizado"],
    }

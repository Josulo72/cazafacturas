"""El banco externo: 23 facturas de 15 maquetaciones que no hizo este proyecto.

El banco interno (`banco.py`) sale del mismo generador que luego las lee, con
una sola maquetación: su 100 % solo demostraba que el extractor sabía leer su
propia plantilla. Este sale de plantillas de terceros rellenadas con datos
ficticios, y trae su verdad en `dataset/externo/manifest.json`.

Quince deben salir conformes con cada campo en su sitio. Ocho traen un
defecto deliberado y deben caer, cada una por su motivo y sin arrastrar
ningún otro error: caer «por descuadre general» no vale.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from backend.nucleo.analizador import analizar_fichero

RAIZ = Path(__file__).resolve().parents[2]
CARPETA = RAIZ / "dataset" / "externo"
MANIFIESTO = CARPETA / "manifest.json"

# El motivo por el que debe caer cada defectuosa: el código del hallazgo.
MOTIVOS = {
    "f16_base_no_suma": "BASE_NO_CUADRA",
    "f17_cuota_iva_erronea": "CUOTA_NO_CUADRA",
    "f18_sin_numero_factura": "SIN_NUMERO",
    "f19_total_no_cuadra": "TOTAL_NO_CUADRA",
    "f20_nif_emisor_invalido": "EMISOR_ID_INVALIDO",
    "f21_irpf_mal_calculado": "RETENCION_NO_CUADRA",
    "f22_falta_nif_cliente": "RECEPTOR_SIN_ID",
    "f23_iva_en_exenta": "IVA_EN_EXENTA",
}

TOLERANCIA = 0.01

# Cada calidad del banco y su extensión: el PDF limpio, y lo que genera
# `dataset/degradar.py`.
EXTENSIONES = {"limpio": "pdf", "escaneado": "png", "foto": "jpg"}


@dataclass
class Campo:
    nombre: str
    esperado: Any
    obtenido: Any
    acierto: bool


@dataclass
class Caso:
    fichero: str
    esperado: str                 # «Conforme» o «No conforme», del manifest
    estado: str                   # conforme · con_avisos · no_conforme · no_legible
    campos: list[Campo]
    errores: list[str]
    motivo: Optional[str]         # el código que debe saltar, si es defectuosa

    @property
    def ruido(self) -> list[str]:
        """Errores que no son el motivo: en una conforme, todos."""
        return [e for e in self.errores if e != self.motivo]

    @property
    def por_su_motivo(self) -> bool:
        return self.motivo is not None and self.motivo in self.errores

    @property
    def campos_mal(self) -> list[Campo]:
        return [c for c in self.campos if not c.acierto]

    @property
    def correcto(self) -> bool:
        if self.campos_mal:
            return False
        if self.motivo is None:
            return self.estado == "conforme"
        return self.estado == "no_conforme" and self.por_su_motivo and not self.ruido


@dataclass
class Informe:
    casos: list[Caso] = field(default_factory=list)
    segundos: float = 0.0

    @property
    def campos_ok(self) -> int:
        return sum(1 for c in self.casos for x in c.campos if x.acierto)

    @property
    def campos_total(self) -> int:
        return sum(len(c.campos) for c in self.casos)

    @property
    def conformes(self) -> tuple[int, int]:
        normales = [c for c in self.casos if c.motivo is None]
        return sum(1 for c in normales if c.correcto), len(normales)

    @property
    def cazadas(self) -> tuple[int, int]:
        defectuosas = [c for c in self.casos if c.motivo is not None]
        return sum(1 for c in defectuosas if c.correcto), len(defectuosas)

    @property
    def no_legibles(self) -> int:
        return sum(1 for c in self.casos if c.estado == "no_legible")

    @property
    def perfecto(self) -> bool:
        return all(c.correcto for c in self.casos) and bool(self.casos)


# ---------------------------------------------------------------------------
# La verdad y lo leído, en la misma forma
# ---------------------------------------------------------------------------

def _texto(v: Any) -> str:
    """Para comparar razones sociales: sin tildes, sin mayúsculas, sin
    espacios ni puntuación. El manifest escribe «Grafica» y el papel
    «Gráfica»; es la misma empresa."""
    plano = unicodedata.normalize("NFD", str(v or ""))
    plano = "".join(c for c in plano if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", plano.lower())


def _iso(fecha: Optional[str]) -> Optional[str]:
    if not fecha:
        return None
    return datetime.strptime(fecha, "%d/%m/%Y").date().isoformat()


def _esperados(m: dict) -> dict[str, Any]:
    e: dict[str, Any] = {}
    if "numero" in m:
        e["numero"] = m["numero"]
    e["fecha"] = _iso(m.get("fecha"))
    e["emisor"] = m.get("emisor")
    nif = m.get("nif_emisor") or m.get("nif_declarado")
    if nif:
        e["nif_emisor"] = nif
    e["base"] = m.get("base", m.get("base_declarada"))
    if "desglose_iva" in m:
        e["cuota"] = round(sum(t["cuota"] for t in m["desglose_iva"]), 2)
    elif "cuota_declarada" in m:
        e["cuota"] = m["cuota_declarada"]
    irpf = m.get("irpf") or m.get("irpf_declarado")
    if irpf:
        e["irpf"] = irpf["importe"]
    if "recargo_equivalencia" in m:
        e["recargo"] = m["recargo_equivalencia"]["importe"]
    if "suplidos" in m:
        e["suplidos"] = m["suplidos"]
    e["total"] = m.get("total", m.get("total_declarado"))
    return {k: v for k, v in e.items() if v is not None or k == "numero"}


def _obtenidos(f: dict) -> dict[str, Any]:
    emisor = f.get("emisor") or {}
    ret = f.get("retencion") or {}
    return {
        "numero": f.get("numero"),
        "fecha": f.get("fecha_emision"),
        "emisor": emisor.get("nombre"),
        "nif_emisor": emisor.get("nif"),
        "base": f.get("base_imponible"),
        "cuota": (round(sum(float(t.get("cuota") or 0) for t in f.get("iva") or []), 2)
                  if f.get("iva") else None),
        "irpf": -abs(ret["cuota"]) if ret.get("cuota") is not None else None,
        "recargo": (round(sum(float(t.get("cuota") or 0) for t in f.get("recargo") or []), 2)
                    if f.get("recargo") else None),
        "suplidos": f.get("suplidos"),
        "total": f.get("total"),
    }


def _igual(nombre: str, esperado: Any, obtenido: Any) -> bool:
    if esperado is None or obtenido is None:
        return esperado is None and obtenido is None
    if isinstance(esperado, (int, float)):
        try:
            return abs(float(obtenido) - float(esperado)) <= TOLERANCIA
        except (TypeError, ValueError):
            return False
    if nombre == "emisor":
        return _texto(esperado) == _texto(obtenido)
    return str(esperado).strip().upper() == str(obtenido).strip().upper()


# ---------------------------------------------------------------------------
# Pasarlo
# ---------------------------------------------------------------------------

def disponible(calidad: str = "limpio") -> bool:
    return MANIFIESTO.is_file() and (CARPETA / calidad).is_dir()


def ejecutar(calidad: str = "limpio") -> Informe:
    manifiesto = json.loads(MANIFIESTO.read_text(encoding="utf-8"))
    informe = Informe()
    inicio = time.perf_counter()
    for m in manifiesto["facturas"]:
        pdf = CARPETA / calidad / f"{m['fichero']}_{calidad}.{EXTENSIONES[calidad]}"
        if not pdf.is_file():
            continue
        r = analizar_fichero(pdf)          # sin forzar país: también se mide eso
        factura = r.factura or {}
        inf = r.informe or {}
        esperados = _esperados(m)
        obtenidos = _obtenidos(factura)
        informe.casos.append(Caso(
            fichero=m["fichero"],
            esperado=m["esperado"],
            estado=inf.get("estado") or ("no_legible" if not r.ok else ""),
            campos=[Campo(k, v, obtenidos.get(k), _igual(k, v, obtenidos.get(k)))
                    for k, v in esperados.items()],
            errores=[h["codigo"] for h in inf.get("hallazgos", [])
                     if h["gravedad"] == "error"],
            motivo=MOTIVOS.get(m["fichero"]),
        ))
    informe.segundos = time.perf_counter() - inicio
    return informe

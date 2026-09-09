from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.nucleo.evaluador import ResultadoEvaluacion


def resultado_a_dict(resultado: ResultadoEvaluacion) -> dict:
    return {
        "factura": resultado.factura,
        "precision": resultado.precision,
        "tasa_invencion": resultado.tasa_invencion,
        "aciertos": len(resultado.aciertos),
        "fallos": len(resultado.fallos),
        "invenciones": len(resultado.invenciones),
        "fallos_validacion": resultado.fallos_validacion,
        "segundos": resultado.metadatos.segundos if resultado.metadatos else 0.0,
        "cacheado": resultado.metadatos.cacheado if resultado.metadatos else False,
        "campos": [
            {
                "campo": c.campo,
                "estado": c.estado.value,
                "esperado": _simple(c.esperado),
                "obtenido": _simple(c.obtenido),
            }
            for c in resultado.campos
        ],
    }


def _simple(valor):
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    if isinstance(valor, list):
        return [_simple(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _simple(v) for k, v in valor.items()}
    return str(valor)


@dataclass
class ResumenEjecucion:
    id_ejecucion: str
    id_motor: str
    modelo: str
    fecha: str
    n_casos: int
    precision: float
    tasa_invencion: float
    segundos: float
    cacheados: int


class AlmacenResultados:
    def __init__(self, directorio: Path):
        self.directorio = directorio
        self.directorio.mkdir(parents=True, exist_ok=True)

    def _ruta(self, id_ejecucion: str) -> Path:
        return self.directorio / f"{id_ejecucion}.json"

    def crear_ejecucion(self, id_motor: str, modelo: str) -> str:
        id_ejecucion = uuid.uuid4().hex[:12]
        fecha = datetime.now(timezone.utc).isoformat()
        self._ruta(id_ejecucion).write_text(
            json.dumps(
                {
                    "id": id_ejecucion,
                    "id_motor": id_motor,
                    "modelo": modelo,
                    "fecha": fecha,
                    "resultados": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return id_ejecucion

    def guardar_resultado(self, id_ejecucion: str, resultado: dict) -> None:
        ruta = self._ruta(id_ejecucion)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["resultados"].append(resultado)
        ruta.write_text(
            json.dumps(datos, ensure_ascii=False), encoding="utf-8"
        )

    def leer(self, id_ejecucion: str) -> dict | None:
        ruta = self._ruta(id_ejecucion)
        if not ruta.exists():
            return None
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def listar(self) -> list[ResumenEjecucion]:
        resumenes = []
        for ruta in sorted(self.directorio.glob("*.json")):
            try:
                datos = json.loads(ruta.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            resultados = datos.get("resultados", [])
            relevantes = sum(1 for r in resultados if (r["aciertos"] + r["fallos"]) > 0)
            total_ac = sum(r["aciertos"] for r in resultados)
            total_fa = sum(r["fallos"] for r in resultados)
            total_in = sum(r["invenciones"] for r in resultados)
            precision = round(total_ac / (total_ac + total_fa), 4) if (total_ac + total_fa) else 0.0
            invencion = (
                round(total_in / (total_ac + total_fa + total_in), 4)
                if (total_ac + total_fa + total_in)
                else 0.0
            )
            resumenes.append(
                ResumenEjecucion(
                    id_ejecucion=datos["id"],
                    id_motor=datos["id_motor"],
                    modelo=datos["modelo"],
                    fecha=datos.get("fecha", ""),
                    n_casos=len(resultados),
                    precision=precision,
                    tasa_invencion=invencion,
                    segundos=round(sum(r.get("segundos", 0) for r in resultados), 2),
                    cacheados=sum(1 for r in resultados if r.get("cacheado")),
                )
            )
        return sorted(resumenes, key=lambda r: r.fecha, reverse=True)

    def comparativa(self) -> list[dict]:
        """Una entrada por motor: campo aciertos acumulados, invención, segundos."""
        por_motor: dict[str, dict] = {}
        for resumen in self.listar():
            datos = self.leer(resumen.id_ejecucion)
            if datos is None:
                continue
            clave = f"{datos['id_motor']}:{datos['modelo']}"
            if clave not in por_motor:
                por_motor[clave] = {
                    "id_motor": datos["id_motor"],
                    "modelo": datos["modelo"],
                    "aciertos": 0,
                    "fallos": 0,
                    "invenciones": 0,
                    "segundos": 0.0,
                    "n_casos": 0,
                    "inventa_por_campo": {},
                    "ejecuciones": [],
                }
            agregado = por_motor[clave]
            for r in datos.get("resultados", []):
                agregado["aciertos"] += r["aciertos"]
                agregado["fallos"] += r["fallos"]
                agregado["invenciones"] += r["invenciones"]
                agregado["segundos"] += r.get("segundos", 0)
                agregado["n_casos"] += 1
                for campo in r.get("campos", []):
                    if campo["estado"] == "invencion":
                        nombre = campo["campo"]
                        agregado["inventa_por_campo"][nombre] = (
                            agregado["inventa_por_campo"].get(nombre, 0) + 1
                        )
            agregado["ejecuciones"].append(resumen.id_ejecucion)

        salida = []
        for clave, a in por_motor.items():
            relevantes = a["aciertos"] + a["fallos"]
            salida.append(
                {
                    "id_motor": a["id_motor"],
                    "modelo": a["modelo"],
                    "precision": round(a["aciertos"] / relevantes, 4) if relevantes else 0.0,
                    "tasa_invencion": round(
                        a["invenciones"] / (relevantes + a["invenciones"]), 4
                    )
                    if (relevantes + a["invenciones"])
                    else 0.0,
                    "aciertos": a["aciertos"],
                    "fallos": a["fallos"],
                    "invenciones": a["invenciones"],
                    "segundos": round(a["segundos"], 2),
                    "n_casos": a["n_casos"],
                    "inventa_por_campo": a["inventa_por_campo"],
                    "ejecuciones": a["ejecuciones"],
                }
            )
        return sorted(salida, key=lambda x: (-x["precision"], x["tasa_invencion"]))
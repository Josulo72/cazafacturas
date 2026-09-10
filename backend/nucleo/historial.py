"""Persistencia de los análisis: un fichero JSON por lote.

Sin base de datos y sin servicio: la aplicación tiene que arrancar con un
`pip install` y un comando, así que el disco es el almacén. Los ficheros se
quedan en el directorio de datos del usuario, no dentro del repositorio.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.nucleo.analizador import ResumenLote

# Cuántos lotes se conservan antes de ir tirando los más viejos.
MAX_LOTES = 100


def dir_datos(raiz: Optional[Path] = None) -> Path:
    """Dónde viven los datos.

    `CAZAFACTURAS_HOME` manda sobre todo. Dentro de un checkout se usa
    `resultados/` para no ensuciar el home de quien está desarrollando;
    instalado con pip, va al home del usuario.
    """
    env = os.environ.get("CAZAFACTURAS_HOME")
    if env:
        ruta = Path(env)
    elif raiz and (raiz / ".git").exists():
        ruta = raiz / "resultados"
    else:
        ruta = Path.home() / ".cazafacturas"
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


@dataclass
class Entrada:
    """La ficha corta de un lote, para listarlo sin abrirlo entero."""
    id: str
    fecha: str
    origen: str
    total: int
    validas: int
    con_errores: int
    fallidas: int
    precision_media: Optional[float]
    confianza_media: float
    segundos: float

    def a_dict(self) -> dict:
        return self.__dict__


class Historial:
    def __init__(self, directorio: Path):
        self.directorio = directorio
        self.directorio.mkdir(parents=True, exist_ok=True)

    def _ruta(self, id_lote: str) -> Path:
        # El id lo generamos nosotros (hex), pero nunca se construye una ruta
        # con texto que venga de fuera sin limpiarlo antes.
        seguro = "".join(c for c in id_lote if c.isalnum() or c in "-_")[:64]
        return self.directorio / f"{seguro}.json"

    def guardar(self, resumen: ResumenLote, origen: str = "subida") -> str:
        datos = resumen.a_dict()
        datos["origen"] = origen
        datos["fecha"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._ruta(resumen.id).write_text(
            json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._podar()
        return resumen.id

    def leer(self, id_lote: str) -> Optional[dict]:
        ruta = self._ruta(id_lote)
        if not ruta.is_file():
            return None
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def listar(self) -> list[Entrada]:
        entradas: list[Entrada] = []
        for ruta in self.directorio.glob("*.json"):
            try:
                d = json.loads(ruta.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            entradas.append(Entrada(
                id=d.get("id", ruta.stem),
                fecha=d.get("fecha", ""),
                origen=d.get("origen", "subida"),
                total=d.get("total", 0),
                validas=d.get("validas", 0),
                con_errores=d.get("con_errores", 0),
                fallidas=d.get("fallidas", 0),
                precision_media=d.get("precision_media"),
                confianza_media=d.get("confianza_media", 0.0),
                segundos=d.get("segundos", 0.0),
            ))
        entradas.sort(key=lambda e: e.fecha, reverse=True)
        return entradas

    def borrar(self, id_lote: str) -> bool:
        ruta = self._ruta(id_lote)
        if not ruta.is_file():
            return False
        ruta.unlink()
        return True

    def _podar(self) -> None:
        entradas = self.listar()
        for sobrante in entradas[MAX_LOTES:]:
            self._ruta(sobrante.id).unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Exportación
# --------------------------------------------------------------------------

CABECERA_CSV = (
    "fichero", "pais", "valida", "errores", "avisos", "numero",
    "fecha_emision", "fecha_vencimiento", "emisor", "emisor_nif",
    "receptor", "receptor_nif", "base_imponible", "total", "confianza", "origen",
    # Añadidas en 1.1.0, al final para no mover las de antes.
    "estado", "cuota_impuesto", "irpf", "recargo_equivalencia", "suplidos",
)


def _celda(valor) -> str:
    if valor is None:
        return ""
    texto = str(valor)
    if any(c in texto for c in ',";\n'):
        return '"' + texto.replace('"', '""') + '"'
    return texto


def a_csv(lote: dict) -> str:
    """El lote en CSV, una fila por factura. Para abrirlo en Excel."""
    filas = [",".join(CABECERA_CSV)]
    for r in lote.get("resultados", []):
        factura = r.get("factura") or {}
        informe = r.get("informe") or {}
        documento = r.get("documento") or {}
        emisor = factura.get("emisor") or {}
        receptor = factura.get("receptor") or {}
        cuota = sum(float(t.get("cuota") or 0) for t in factura.get("iva") or [])
        recargo = sum(float(t.get("cuota") or 0) for t in factura.get("recargo") or [])
        retencion = (factura.get("retencion") or {}).get("cuota")
        filas.append(",".join(_celda(v) for v in (
            r.get("nombre"),
            informe.get("pais"),
            "sí" if informe.get("valida") else "no",
            informe.get("n_errores"),
            informe.get("n_avisos"),
            factura.get("numero"),
            factura.get("fecha_emision"),
            factura.get("fecha_vencimiento"),
            emisor.get("nombre"),
            emisor.get("nif"),
            receptor.get("nombre"),
            receptor.get("nif"),
            factura.get("base_imponible"),
            factura.get("total"),
            (r.get("extraccion") or {}).get("confianza"),
            documento.get("origen"),
            informe.get("estado") or ("no_legible" if not r.get("ok") else ""),
            round(cuota, 2) if factura.get("iva") else None,
            -abs(float(retencion)) if retencion else None,
            round(recargo, 2) if factura.get("recargo") else None,
            factura.get("suplidos"),
        )))
    return "\n".join(filas)


def limpiar(directorio: Path) -> int:
    """Vacía el historial. Devuelve cuántos lotes se han borrado."""
    if not directorio.is_dir():
        return 0
    n = len(list(directorio.glob("*.json")))
    shutil.rmtree(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    return n

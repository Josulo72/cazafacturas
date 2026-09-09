from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _normalizar_documento(documento: dict) -> str:
    return json.dumps(documento, sort_keys=True, ensure_ascii=False)


def hash_contenido(
    documento: dict,
    id_motor: str,
    prompt_extra: str = "",
    version_prompt: str = "1",
    idioma: str = "es",
) -> str:
    material = (
        version_prompt
        + "\n"
        + id_motor
        + "\n"
        + idioma
        + "\n"
        + _normalizar_documento(documento)
        + "\n"
        + str(prompt_extra)
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class CacheResultados:
    """Caché de respuestas por hash de documento + motor."""

    def __init__(self, directorio: Path):
        self.directorio = directorio
        self.directorio.mkdir(parents=True, exist_ok=True)

    def _ruta(self, clave: str) -> Path:
        return self.directorio / f"{clave}.json"

    def obtener(self, clave: str) -> dict | None:
        ruta = self._ruta(clave)
        if not ruta.exists():
            return None
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def guardar(self, clave: str, respuesta: str, segundos: float) -> None:
        self._ruta(clave).write_text(
            json.dumps(
                {
                    "respuesta": respuesta,
                    "segundos": segundos,
                    "cacheado": True,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
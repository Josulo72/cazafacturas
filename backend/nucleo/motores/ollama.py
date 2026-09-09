from __future__ import annotations

import json
import os
import time

import urllib.error
import urllib.request

from backend.nucleo.motores.base import (
    EstadoMotor,
    InfoMotor,
    MotorProcesador,
    RespuestaMotor,
)
from backend.nucleo.motores.prompt import generar_prompt


class MotorOllama(MotorProcesador):
    nombre = "ollama"

    def __init__(self, url: str | None = None, modelo: str | None = None):
        self.url = (url or os.environ.get("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.modelo = modelo or os.environ.get("OLLAMA_MODEL", "")

    def _endpoint(self, recurso: str) -> str:
        return f"{self.url}/{recurso}"

    def _listar_modelos(self) -> list[str]:
        try:
            with urllib.request.urlopen(
                self._endpoint("api/tags"), timeout=3
            ) as resp:
                datos = json.loads(resp.read().decode("utf-8"))
            return [m.get("name", "") for m in datos.get("models", [])]
        except Exception:
            return []

    def detectar(self) -> InfoMotor:
        analisis = self._detectar()
        return InfoMotor(
            nombre=self.nombre,
            estado=analisis[0],
            modelo=analisis[1] or self.modelo or None,
            detalle=analisis[2],
        )

    def _detectar(self) -> tuple[EstadoMotor, str | None, str | None]:
        try:
            modelos = self._listar_modelos()
        except Exception as e:
            return (
                EstadoMotor.NO_INSTALADO,
                None,
                f"No responde en {self.url}: {type(e).__name__}",
            )
        if not modelos:
            return (
                EstadoMotor.SIN_CONFIGURAR,
                None,
                f"Ollama responde en {self.url} pero sin modelos descargados",
            )
        if self.modelo:
            disponible = self.modelo in modelos or any(
                m.startswith(self.modelo) for m in modelos
            )
            if not disponible:
                return (
                    EstadoMotor.SIN_CONFIGURAR,
                    self.modelo,
                    f"Modelo '{self.modelo}' no está descargado",
                )
            return EstadoMotor.DISPONIBLE, self.modelo, None
        return EstadoMotor.DISPONIBLE, modelos[0], None

    def procesar(
        self, documento: dict, prompt_extra: str = "", idioma: str = "es"
    ) -> RespuestaMotor:
        estado, modelo, _ = self._detectar()
        if estado != EstadoMotor.DISPONIBLE:
            raise RuntimeError(f"Ollama no disponible: {modelo or estado.value}")
        modelo = modelo or self.modelo

        prompt = generar_prompt(documento, idioma)
        if prompt_extra:
            prompt += "\n\nNotas adicionales:\n" + prompt_extra

        cuerpo = json.dumps(
            {
                "model": modelo,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0},
            }
        ).encode("utf-8")

        solicitud = urllib.request.Request(
            self._endpoint("api/generate"),
            data=cuerpo,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        inicio = time.perf_counter()
        try:
            with urllib.request.urlopen(solicitud, timeout=300) as resp:
                datos = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Ollama devolvió HTTP {e.code}: {e.read().decode()[:300]}")
        except Exception as e:
            raise RuntimeError(f"Error llamando a Ollama: {type(e).__name__}: {e}")

        texto = datos.get("response", "")
        return RespuestaMotor(texto=texto, segundos=time.perf_counter() - inicio)
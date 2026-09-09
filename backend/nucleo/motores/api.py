from __future__ import annotations

import json
import os
import time
from typing import Callable

from backend.nucleo.motores.base import (
    EstadoMotor,
    InfoMotor,
    MotorProcesador,
    RespuestaMotor,
)
from backend.nucleo.motores.prompt import generar_prompt

PROVEEDORES = {
    "anthropic": {
        "clave": "ANTHROPIC_API_KEY",
        "modelo": "claude-3-5-sonnet-latest",
        "sdk": "anthropic",
    },
    "openai": {
        "clave": "OPENAI_API_KEY",
        "modelo": "gpt-4o",
        "sdk": "openai",
    },
    "google": {
        "clave": "GOOGLE_API_KEY",
        "modelo": "gemini-1.5-pro",
        "sdk": "google.generativeai",
    },
}


class MotorAPI(MotorProcesador):
    nombre = "api"

    def __init__(self, proveedor: str):
        if proveedor not in PROVEEDORES:
            raise ValueError(
                f"Proveedor desconocido: {proveedor}. "
                f"Opciones: {', '.join(PROVEEDORES)}"
            )
        self.proveedor = proveedor
        self._cfg = PROVEEDORES[proveedor]

    def _clave(self) -> str | None:
        return os.environ.get(self._cfg["clave"]) or None

    def detectar(self) -> InfoMotor:
        clave = self._clave()
        if not clave:
            return InfoMotor(
                nombre=f"api:{self.proveedor}",
                estado=EstadoMotor.SIN_CONFIGURAR,
                detalle=f"Falta {self._cfg['clave']}",
            )
        try:
            __import__(self._cfg["sdk"])
        except ImportError:
            return InfoMotor(
                nombre=f"api:{self.proveedor}",
                estado=EstadoMotor.SIN_CONFIGURAR,
                detalle=f"Falta la librería {self._cfg['sdk']}",
            )
        return InfoMotor(
            nombre=f"api:{self.proveedor}",
            estado=EstadoMotor.DISPONIBLE,
            modelo=self._cfg["modelo"],
        )

    def procesar(
        self, documento: dict, prompt_extra: str = "", idioma: str = "es"
    ) -> RespuestaMotor:
        clave = self._clave()
        if not clave:
            raise RuntimeError(f"Falta la clave {self._cfg['clave']}")
        prompt = generar_prompt(documento, idioma)
        if prompt_extra:
            prompt += "\n\nNotas adicionales:\n" + prompt_extra

        inicio = time.perf_counter()
        texto = self._llamar(prompt, clave)
        return RespuestaMotor(texto=texto, segundos=time.perf_counter() - inicio)

    def _llamar(self, prompt: str, clave: str) -> str:
        if self.proveedor == "anthropic":
            return self._llamar_anthropic(prompt, clave)
        if self.proveedor == "openai":
            return self._llamar_openai(prompt, clave)
        if self.proveedor == "google":
            return self._llamar_google(prompt, clave)
        raise RuntimeError(f"Proveedor sin implementación: {self.proveedor}")

    def _llamar_anthropic(self, prompt: str, clave: str) -> str:
        import anthropic

        cliente = anthropic.Anthropic(api_key=clave)
        respuesta = cliente.messages.create(
            model=self._cfg["modelo"],
            max_tokens=4096,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            b.text for b in respuesta.content if getattr(b, "type", None) == "text"
        )

    def _llamar_openai(self, prompt: str, clave: str) -> str:
        from openai import OpenAI

        cliente = OpenAI(api_key=clave)
        respuesta = cliente.responses.create(
            model=self._cfg["modelo"],
            temperature=0,
            input=[{"role": "user", "content": prompt}],
        )
        return respuesta.output_text

    def _llamar_google(self, prompt: str, clave: str) -> str:
        import google.generativeai as genai

        genai.configure(api_key=clave)
        modelo = genai.GenerativeModel(self._cfg["modelo"], generation_config={"temperature": 0})
        respuesta = modelo.generate_content(prompt)
        return respuesta.text or ""


def obtener_motores_api() -> list[MotorAPI]:
    return [MotorAPI(p) for p in PROVEEDORES]
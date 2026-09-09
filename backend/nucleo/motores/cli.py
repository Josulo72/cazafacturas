from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

from backend.nucleo.esquema import Factura
from backend.nucleo.motores.base import (
    EstadoMotor,
    InfoMotor,
    MotorProcesador,
    RespuestaMotor,
)
from backend.nucleo.motores.prompt import PROMPT_VERSION, generar_prompt


class MotorCLI(MotorProcesador):
    nombre = "cli"

    def __init__(self, binario: str | None = None, modelo: str | None = None):
        self.binario = binario or os.environ.get("MOTOR_CLI_DEFAULT", "claude")
        self.modelo = modelo or os.environ.get("MOTOR_CLI_MODEL") or "sonnet"

    def _ruta(self) -> str | None:
        return shutil.which(self.binario)

    def detectar(self) -> InfoMotor:
        ruta = self._ruta()
        if not ruta:
            return InfoMotor(
                nombre=self.nombre,
                estado=EstadoMotor.NO_INSTALADO,
                detalle=f"'{self.binario}' no encontrado en PATH",
            )
        return InfoMotor(
            nombre=self.nombre,
            estado=EstadoMotor.DISPONIBLE,
            modelo=self.modelo or self.binario,
            detalle=f"Ejecutable: {ruta}" + (f", modelo: {self.modelo}" if self.modelo else ""),
        )

    def procesar(
        self, documento: dict, prompt_extra: str = "", idioma: str = "es"
    ) -> RespuestaMotor:
        ruta = self._ruta()
        if not ruta:
            raise RuntimeError(
                f"Motor CLI '{self.binario}' no está instalado o no está en PATH"
            )

        prompt = generar_prompt(documento, idioma)
        if prompt_extra:
            prompt += "\n\nNotas adicionales:\n" + prompt_extra

        comando = [ruta, "-p", prompt]
        if self.modelo:
            comando += ["--model", self.modelo]

        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        inicio = time.perf_counter()
        try:
            proceso = subprocess.Popen(
                comando,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
            try:
                salida, error = proceso.communicate(timeout=180)
            except subprocess.TimeoutExpired:
                self._matar_arbol(proceso)
                raise RuntimeError(
                    f"Motor CLI '{self.binario}' agotó el tiempo (180 s)"
                )
        except OSError as e:
            raise RuntimeError(f"No se pudo invocar '{self.binario}': {e}")

        segundos = time.perf_counter() - inicio
        texto = (salida or "").strip()
        if not texto:
            texto = (error or "").strip()

        if proceso.returncode != 0:
            raise RuntimeError(
                f"Motor CLI '{self.binario}' falló (código {proceso.returncode}): "
                f"{texto[:500]}"
            )

        return RespuestaMotor(texto=texto, segundos=segundos)

    def _matar_arbol(self, proceso: subprocess.Popen) -> None:
        proceso.kill()
        proceso.wait(timeout=5)
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(proceso.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                )
            except Exception:
                pass


def obtener_prompt_base() -> str:
    return generar_prompt({"pais": "ES"}, "es")


def contrato_resaltado() -> str:
    return str(Factura.model_json_schema())
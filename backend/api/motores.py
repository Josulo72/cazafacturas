from __future__ import annotations

import os
from dataclasses import dataclass

from backend.nucleo.motores.api import MotorAPI, obtener_motores_api
from backend.nucleo.motores.base import EstadoMotor, InfoMotor
from backend.nucleo.motores.cli import MotorCLI
from backend.nucleo.motores.ollama import MotorOllama


@dataclass
class CatalogoMotores:
    cli: MotorCLI
    api: list[MotorAPI]
    ollama: MotorOllama

    def todos_dispuestos(self) -> list[tuple[str, InfoMotor]]:
        """Una lista plana (id, info) con todos los motores para la UI."""
        salida: list[tuple[str, InfoMotor]] = []
        info = self.cli.detectar()
        salida.append(("cli", info))
        for motor in self.api:
            salida.append((f"api:{motor.proveedor}", motor.detectar()))
        info_ollama = self.ollama.detectar()
        salida.append(("ollama", info_ollama))
        return salida

    def disponible(self) -> list[str]:
        return [
            id_motor
            for id_motor, info in self.todos_dispuestos()
            if info.estado == EstadoMotor.DISPONIBLE
        ]

    def get(self, id_motor: str) -> MotorCLI | MotorAPI | MotorOllama:
        if id_motor == "cli":
            return self.cli
        if id_motor == "ollama":
            return self.ollama
        if id_motor.startswith("api:"):
            proveedor = id_motor.split(":", 1)[1]
            for motor in self.api:
                if motor.proveedor == proveedor:
                    return motor
        raise KeyError(f"Motor desconocido: {id_motor}")


def crear_catalogo(modelo_cli: str | None = None) -> CatalogoMotores:
    return CatalogoMotores(
        cli=MotorCLI(modelo=modelo_cli),
        api=obtener_motores_api(),
        ollama=MotorOllama(),
    )
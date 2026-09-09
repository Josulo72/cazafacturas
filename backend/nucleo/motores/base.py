from __future__ import annotations

import abc
from dataclasses import dataclass
from enum import Enum


class EstadoMotor(str, Enum):
    DISPONIBLE = "disponible"
    NO_INSTALADO = "no_instalado"
    SIN_CONFIGURAR = "sin_configurar"


@dataclass
class InfoMotor:
    nombre: str
    estado: EstadoMotor
    modelo: str | None = None
    detalle: str | None = None


class RespuestaMotor:
    def __init__(self, texto: str, segundos: float, cacheado: bool = False):
        self.texto = texto
        self.segundos = segundos
        self.cacheado = cacheado


class MotorProcesador(abc.ABC):
    """Interfaz común de los tres tipos de motor."""

    nombre: str = ""

    @abc.abstractmethod
    def detectar(self) -> InfoMotor:
        """Devuelve el estado del motor sin gastar nada."""

    @abc.abstractmethod
    def procesar(
        self, documento: dict, prompt_extra: str = "", idioma: str = "es"
    ) -> RespuestaMotor:
        """Pasa el documento al modelo y devuelve la respuesta en bruto."""
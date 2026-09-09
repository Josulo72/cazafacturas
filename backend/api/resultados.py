from __future__ import annotations

from pathlib import Path

from backend.nucleo.almacen import (
    AlmacenResultados,
    ResumenEjecucion,
    resultado_a_dict,
)
from backend.nucleo.evaluador import ResultadoEvaluacion


class GestionResultados:
    def __init__(self, directorio: Path):
        self.almacen = AlmacenResultados(directorio)

    def nueva_ejecucion(self, id_motor: str, modelo: str) -> str:
        return self.almacen.crear_ejecucion(id_motor, modelo)

    def registrar(self, id_ejecucion: str, resultado: ResultadoEvaluacion) -> None:
        self.almacen.guardar_resultado(id_ejecucion, resultado_a_dict(resultado))

    def historial(self) -> list[ResumenEjecucion]:
        return self.almacen.listar()

    def detalle(self, id_ejecucion: str) -> dict | None:
        return self.almacen.leer(id_ejecucion)

    def comparativa(self) -> list[dict]:
        return self.almacen.comparativa()


def crear_gestion(directorio: Path | None = None) -> GestionResultados:
    base = directorio or (
        Path(__file__).resolve().parent.parent.parent / "resultados" / "ejecuciones"
    )
    base.mkdir(parents=True, exist_ok=True)
    return GestionResultados(base)
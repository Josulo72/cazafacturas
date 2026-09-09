from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.nucleo.paises import PAISES


@dataclass
class Caso:
    id: str
    documento: dict
    esperado: dict
    es_trampa: bool = False
    ruta_documento: Path | None = None
    ruta_esperado: Path | None = None
    pais: str = "ES"


def _cargar_json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


class Dataset:
    def __init__(self, raiz: Path):
        self.raiz = raiz

    def _cargar_pais(self, pais: str, trampas: bool) -> list[Caso]:
        cfg = PAISES[pais.upper()]
        base = self.raiz / cfg.codigo
        facturas_dir = base / "facturas"
        esperado_dir = base / "esperado"
        casos = []
        if facturas_dir.exists():
            for doc in sorted(facturas_dir.glob("*.json")):
                esperado = esperado_dir / doc.name
                if not esperado.exists():
                    continue
                casos.append(
                    Caso(
                        id=doc.stem,
                        documento=_cargar_json(doc),
                        esperado=_cargar_json(esperado),
                        ruta_documento=doc,
                        ruta_esperado=esperado,
                        pais=pais.upper(),
                    )
                )
        if trampas:
            trampas_dir = self.raiz / "trampas"
            sufijo = f"_{pais.lower()}_documento.json"
            for doc in sorted(trampas_dir.glob(f"*{sufijo}")):
                nombre = doc.name.replace(sufijo, "")
                esperado = trampas_dir / f"{nombre}_{pais.lower()}_esperado.json"
                if not esperado.exists():
                    continue
                casos.append(
                    Caso(
                        id=nombre,
                        documento=_cargar_json(doc),
                        esperado=_cargar_json(esperado),
                        es_trampa=True,
                        ruta_documento=doc,
                        ruta_esperado=esperado,
                        pais=pais.upper(),
                    )
                )
        return casos

    def casos_normales(self, pais: Optional[str] = None) -> list[Caso]:
        if pais:
            return self._cargar_pais(pais, trampas=False)
        todos = []
        for codigo in PAISES:
            todos.extend(self._cargar_pais(codigo, trampas=False))
        return todos

    def casos_trampa(self, pais: Optional[str] = None) -> list[Caso]:
        if pais:
            return self._cargar_pais(pais, trampas=True)
        todos = []
        for codigo in PAISES:
            todos.extend(self._cargar_pais(codigo, trampas=True))
        return todos

    def todos(self, pais: Optional[str] = None) -> list[Caso]:
        if pais:
            return self._cargar_pais(pais, trampas=True) + self._cargar_pais(pais, trampas=False)
        return self.casos_normales(pais) + self.casos_trampa(pais)


def cargar_dataset(raiz: Path | None = None) -> Dataset:
    base = raiz or Path(__file__).resolve().parent.parent.parent / "dataset"
    return Dataset(base)
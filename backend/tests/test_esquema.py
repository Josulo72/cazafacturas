"""El esquema de `esquema.py`, que es lo que construye el dataset.

A diferencia del validador —que informa— el esquema rechaza: si una factura
del dataset no cuadra, no llega a escribirse. Los dos guardan la puerta, pero
en direcciones distintas.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from backend.nucleo.esquema import (
    DesgloseIVA,
    Direccion,
    Empresa,
    Factura,
    LineaFactura,
    TipoFactura,
)


def _empresa(nombre: str = "Tecnología del Sur S.L.",
             nif: str = "B12345674") -> Empresa:
    return Empresa(
        nombre=nombre,
        nif=nif,
        direccion=Direccion(
            calle="Calle Gran Vía 42", ciudad="Madrid",
            provincia="Madrid", codigo_postal="28001", pais="ES",
        ),
    )


def _factura(**cambios) -> Factura:
    datos = dict(
        pais="ES",
        numero="F/2025/0001",
        fecha_emision=date(2025, 3, 14),
        emisor=_empresa(),
        receptor=_empresa("Alimentos del Norte S.A.", "A87654323"),
        lineas=[LineaFactura(descripcion="Licencia software anual",
                             cantidad=2, precio_unitario=450.0, importe=900.0)],
        base_imponible=900.0,
        iva=[DesgloseIVA(porcentaje=21.0, base_imponible=900.0, cuota=189.0)],
        total=1089.0,
    )
    datos.update(cambios)
    return Factura(**datos)


def test_factura_valida():
    factura = _factura()
    assert factura.total == 1089.0
    assert factura.tipo is TipoFactura.COMPLETA


def test_importe_de_linea_incoherente_se_rechaza():
    with pytest.raises(ValidationError, match="no coincide"):
        LineaFactura(descripcion="X", cantidad=2, precio_unitario=450.0,
                     importe=950.0)


def test_base_que_no_suma_las_lineas_se_rechaza():
    with pytest.raises(ValidationError, match="Base imponible"):
        _factura(base_imponible=800.0)


def test_total_incoherente_se_rechaza():
    with pytest.raises(ValidationError, match="Total"):
        _factura(total=1200.0)


def test_factura_completa_exige_receptor():
    with pytest.raises(ValidationError, match="receptor"):
        _factura(receptor=None)


def test_simplificada_no_exige_receptor():
    factura = _factura(tipo=TipoFactura.SIMPLIFICADA, receptor=None)
    assert factura.receptor is None


def test_pais_desconocido_se_rechaza():
    with pytest.raises(ValidationError, match="No soportado|no soportado"):
        _factura(pais="FR")


def test_hace_falta_al_menos_una_linea():
    with pytest.raises(ValidationError):
        _factura(lineas=[])

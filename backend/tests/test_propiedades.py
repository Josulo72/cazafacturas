"""Tests de propiedades.

Un test de ejemplo comprueba que `1.234,56` se lee como 1234.56. Eso está
bien, pero solo cubre lo que a uno se le ocurrió escribir, y en un parser lo
que te hunde es siempre el caso que no se te ocurrió.

Aquí se enuncia la *propiedad* —«todo importe que yo mismo escriba, lo tengo
que saber volver a leer»— y Hypothesis busca el contraejemplo. Cuando lo
encuentra, además lo reduce al caso mínimo que falla.

Es la técnica que corresponde a este código: un parser de formatos numéricos
y de fechas de cuatro países, y unos dígitos de control con aritmética
modular. Tres sitios donde los ejemplos escritos a mano se quedan cortos.
"""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from backend.nucleo.extractor import _a_fecha, _a_numero
from backend.nucleo.paises import PAISES
from backend.nucleo.validador import validar_id_fiscal
from dataset.generador import _cif_es, _nif_aleatorio, _ustid_de, _vat_uk

# ---------------------------------------------------------------------------
# Importes
# ---------------------------------------------------------------------------

importes = st.floats(min_value=0, max_value=9_999_999, allow_nan=False,
                     allow_infinity=False).map(lambda v: round(v, 2))


def _a_la_espanola(v: float) -> str:
    """1234.5 -> '1.234,50'. Punto de millares, coma decimal."""
    entero, dec = f"{v:.2f}".split(".")
    grupos = f"{int(entero):,}".replace(",", ".")
    return f"{grupos},{dec}"


def _a_la_americana(v: float) -> str:
    """1234.5 -> '1,234.50'. Coma de millares, punto decimal."""
    return f"{v:,.2f}"


@given(importes)
def test_lo_que_escribo_a_la_espanola_lo_se_leer(v):
    assert _a_numero(_a_la_espanola(v)) == pytest.approx(v, abs=0.005)


@given(importes)
def test_lo_que_escribo_a_la_americana_lo_se_leer(v):
    assert _a_numero(_a_la_americana(v)) == pytest.approx(v, abs=0.005)


@given(importes)
def test_los_dos_formatos_dan_el_mismo_numero(v):
    """La misma cantidad escrita a la europea y a la americana tiene que
    leerse igual. Es toda la dificultad del parser en una línea."""
    assert _a_numero(_a_la_espanola(v)) == _a_numero(_a_la_americana(v))


@given(importes, st.sampled_from(["€", "$", "£", " EUR", ""]))
def test_la_moneda_no_estorba(v, moneda):
    assert _a_numero(_a_la_espanola(v) + " " + moneda) == pytest.approx(v, abs=0.005)


@given(st.text(alphabet=st.characters(blacklist_categories=("Nd",)), max_size=30))
def test_sin_cifras_no_hay_numero(basura):
    """Cualquier texto sin dígitos tiene que devolver None, no reventar ni
    inventarse un cero."""
    assert _a_numero(basura) is None


@given(st.text(max_size=40))
def test_nunca_revienta(basura):
    resultado = _a_numero(basura)
    assert resultado is None or isinstance(resultado, float)


# ---------------------------------------------------------------------------
# Fechas
# ---------------------------------------------------------------------------

fechas = st.dates(min_value=date(1990, 1, 1), max_value=date(2099, 12, 31))


@given(fechas, st.sampled_from(sorted(PAISES)))
def test_la_fecha_que_escribo_en_su_pais_la_leo_igual(d, pais):
    """Cada país escribe la fecha a su manera y hay que leerla en la suya:
    05/03 es 5 de marzo en España y 3 de mayo en Estados Unidos."""
    escrita = d.strftime(PAISES[pais].fecha_formatos[0])
    assert _a_fecha(escrita, pais) == d


@given(fechas, st.sampled_from(sorted(PAISES)))
def test_la_etiqueta_delante_no_estorba(d, pais):
    escrita = d.strftime(PAISES[pais].fecha_formatos[0])
    assert _a_fecha(f"Fecha de factura: {escrita}", pais) == d


@given(st.text(max_size=40))
def test_la_fecha_ilegible_no_revienta(basura):
    resultado = _a_fecha(basura, "ES")
    assert resultado is None or isinstance(resultado, date)


# ---------------------------------------------------------------------------
# Identificadores fiscales
# ---------------------------------------------------------------------------

@given(st.integers(min_value=0, max_value=9_999_999),
       st.sampled_from(list("ABEHPQRSNW")))
def test_todo_cif_que_genero_es_valido(numero, tipo):
    """El generador y el validador tienen que estar de acuerdo. Si no, el
    dataset del proyecto lo rechaza su propio validador —que es exactamente
    lo que pasaba antes de arreglarlo—."""
    assert validar_id_fiscal(_cif_es(f"{numero:07d}", tipo), "ES")


@given(st.integers(min_value=0, max_value=9_999_999))
def test_todo_vat_britanico_que_genero_es_valido(numero):
    assert validar_id_fiscal(_vat_uk(f"{numero:07d}"), "UK")


@given(st.integers(min_value=0, max_value=99_999_999))
def test_toda_ustid_alemana_que_genero_es_valida(numero):
    assert validar_id_fiscal(_ustid_de(f"{numero:08d}"), "DE")


@given(st.integers(min_value=0, max_value=9_999_999),
       st.sampled_from(list("ABEH")),
       st.integers(min_value=1, max_value=9))
def test_tocar_el_digito_de_control_lo_invalida(numero, tipo, desvio):
    """La prueba de que el dígito de control sirve para algo: cambiarlo
    tiene que romper el identificador, siempre."""
    bueno = _cif_es(f"{numero:07d}", tipo)
    control = int(bueno[-1])
    malo = bueno[:-1] + str((control + desvio) % 10)
    assume(malo != bueno)
    assert not validar_id_fiscal(malo, "ES")


@given(st.sampled_from(sorted(PAISES)))
@settings(max_examples=40)
def test_el_generador_de_cada_pais_produce_identificadores_validos(pais):
    for _ in range(20):
        assert validar_id_fiscal(_nif_aleatorio(pais), pais)


@given(st.text(alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-", max_size=15),
       st.sampled_from(sorted(PAISES)))
def test_validar_identificadores_nunca_revienta(texto, pais):
    assert isinstance(validar_id_fiscal(texto, pais), bool)

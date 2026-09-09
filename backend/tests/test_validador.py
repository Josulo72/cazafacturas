"""Reglas fiscales: identificadores, aritmética y coherencia del documento."""

from __future__ import annotations

import glob
import json
from datetime import date, timedelta

import pytest

from backend.nucleo.validador import Gravedad, validar, validar_id_fiscal


def _factura_base(**cambios) -> dict:
    """Una factura española correcta. Cada test rompe solo lo que le interesa."""
    datos = {
        "tipo_documento": "factura",
        "pais": "ES",
        "numero": "F/2025/0001",
        "fecha_emision": "2025-03-14",
        "fecha_vencimiento": "2025-04-13",
        "emisor": {"nombre": "Tecnología del Sur S.L.", "nif": "B12345674"},
        "receptor": {"nombre": "Alimentos del Norte S.A.", "nif": "A87654323"},
        "lineas": [
            {"descripcion": "Licencia software anual",
             "cantidad": 2, "precio_unitario": 450.0, "importe": 900.0},
        ],
        "base_imponible": 900.0,
        "iva": [{"porcentaje": 21.0, "base_imponible": 900.0, "cuota": 189.0}],
        "retencion": None,
        "total": 1089.0,
    }
    datos.update(cambios)
    return datos


def _codigos(datos: dict) -> set[str]:
    return {h.codigo for h in validar(datos).hallazgos}


# ---------------------------------------------------------------- identificadores

@pytest.mark.parametrize("valor,pais", [
    ("12345678Z", "ES"),      # DNI
    ("X1234567L", "ES"),      # NIE
    ("B12345674", "ES"),      # CIF con control numérico
    ("DE136695976", "DE"),    # USt-IdNr. real
    ("12-3456789", "US"),     # EIN con prefijo asignado
])
def test_identificadores_validos(valor, pais):
    assert validar_id_fiscal(valor, pais)


@pytest.mark.parametrize("valor,pais", [
    ("12345678A", "ES"),      # letra de DNI incorrecta
    ("B12345678", "ES"),      # dígito de control de CIF incorrecto
    ("DE136695970", "DE"),    # módulo 11 incorrecto
    ("00-1234567", "US"),     # prefijo que el IRS no asigna
    ("GB123456789", "UK"),    # módulo 97 incorrecto
    ("", "ES"),
])
def test_identificadores_invalidos(valor, pais):
    assert not validar_id_fiscal(valor, pais)


def test_formato_correcto_pero_control_malo_se_rechaza():
    """El formato de paises.py lo cumple; el dígito de control no. Es el caso
    que separa una comprobación seria de un `re.match`."""
    assert not validar_id_fiscal("B99999999", "ES")


# ---------------------------------------------------------------- caso correcto

def test_factura_correcta_no_tiene_errores():
    informe = validar(_factura_base())
    assert informe.valida, [h.mensaje for h in informe.errores]
    assert informe.errores == []


# ---------------------------------------------------------------- aritmética

def test_linea_que_no_cuadra():
    datos = _factura_base()
    datos["lineas"][0]["importe"] = 950.0
    assert "LINEA_NO_CUADRA" in _codigos(datos)


def test_base_distinta_de_la_suma_de_lineas():
    assert "BASE_NO_CUADRA" in _codigos(_factura_base(base_imponible=800.0))


def test_cuota_de_iva_mal_calculada():
    datos = _factura_base()
    datos["iva"][0]["cuota"] = 200.0
    assert "CUOTA_NO_CUADRA" in _codigos(datos)


def test_total_que_no_es_base_mas_impuestos():
    assert "TOTAL_NO_CUADRA" in _codigos(_factura_base(total=1200.0))


def test_tolerancia_de_redondeo_no_da_falso_positivo():
    """Un céntimo de diferencia es redondeo, no un error."""
    assert validar(_factura_base(total=1089.01)).valida


def test_retencion_descuenta_del_total():
    datos = _factura_base(
        retencion={"porcentaje": 15.0, "base_imponible": 900.0, "cuota": 135.0},
        total=954.0,
    )
    assert validar(datos).valida


def test_cantidad_cero():
    datos = _factura_base()
    datos["lineas"][0].update(cantidad=0, precio_unitario=450.0, importe=0.0)
    datos.update(base_imponible=0.0,
                 iva=[{"porcentaje": 21.0, "base_imponible": 0.0, "cuota": 0.0}])
    assert "LINEA_CANTIDAD_INVALIDA" in _codigos(datos)


# ---------------------------------------------------------------- coherencia

def test_vencimiento_anterior_a_emision():
    assert "VENCIMIENTO_ANTERIOR" in _codigos(
        _factura_base(fecha_vencimiento="2025-02-01")
    )


def test_emision_futura_es_aviso_no_error():
    """Sospechoso, pero no invalida la factura por sí solo."""
    futuro = (date.today() + timedelta(days=30)).isoformat()
    informe = validar(_factura_base(fecha_emision=futuro, fecha_vencimiento=None))
    assert informe.valida
    assert any(h.codigo == "EMISION_FUTURA" and h.gravedad is Gravedad.AVISO
               for h in informe.hallazgos)


def test_emisor_y_receptor_con_el_mismo_nif():
    datos = _factura_base()
    datos["receptor"]["nif"] = datos["emisor"]["nif"]
    assert "EMISOR_IGUAL_RECEPTOR" in _codigos(datos)


def test_factura_sin_numero():
    assert "SIN_NUMERO" in _codigos(_factura_base(numero=""))


def test_albaran_presentado_como_factura():
    assert "DOC_NO_ES_FACTURA" in _codigos(
        _factura_base(tipo_documento="factura", observaciones="Albarán de entrega")
    )


def test_tipo_de_iva_inexistente_en_espana():
    datos = _factura_base()
    datos["iva"] = [{"porcentaje": 17.0, "base_imponible": 900.0, "cuota": 153.0}]
    datos["total"] = 1053.0
    assert "TIPO_IMPUESTO_INEXISTENTE" in _codigos(datos)


def test_tipo_valido_en_alemania_no_lo_es_en_espana():
    """El 19% es correcto en Alemania y no existe en España."""
    aleman = {
        **_factura_base(pais="DE"),
        "emisor": {"nombre": "Nord GmbH", "nif": "DE136695976"},
        "receptor": {"nombre": "Süd GmbH", "nif": "DE811907980"},
        "iva": [{"porcentaje": 19.0, "base_imponible": 900.0, "cuota": 171.0}],
        "total": 1071.0,
    }
    assert "TIPO_IMPUESTO_INEXISTENTE" not in _codigos(aleman)

    espanol = _factura_base(
        iva=[{"porcentaje": 19.0, "base_imponible": 900.0, "cuota": 171.0}],
        total=1071.0,
    )
    assert "TIPO_IMPUESTO_INEXISTENTE" in _codigos(espanol)


def test_pais_no_soportado():
    assert "PAIS_NO_SOPORTADO" in _codigos(_factura_base(pais="FR"))


def test_nada_lanza_excepcion_con_basura():
    """Un documento destrozado tiene que dar informe, no traza."""
    for basura in ({}, {"pais": "ES"}, {"lineas": "no soy una lista"},
                   {"total": "abc", "iva": 5}):
        informe = validar(basura)
        assert not informe.valida


# ---------------------------------------------------------------- dataset

def test_todas_las_facturas_del_dataset_son_validas():
    ficheros = sorted(glob.glob("dataset/*/esperado/*.json"))
    assert ficheros, "No se ha encontrado el dataset"
    invalidas = []
    for ruta in ficheros:
        datos = json.load(open(ruta, encoding="utf-8"))
        informe = validar(datos)
        if not informe.valida:
            invalidas.append((ruta, [h.codigo for h in informe.errores]))
    assert not invalidas, invalidas


def test_todas_las_trampas_del_dataset_se_detectan():
    ficheros = sorted(glob.glob("dataset/trampas/*_esperado.json"))
    assert ficheros, "No se han encontrado los casos trampa"
    mudas = [r for r in ficheros
             if not validar(json.load(open(r, encoding="utf-8"))).hallazgos]
    assert not mudas, mudas

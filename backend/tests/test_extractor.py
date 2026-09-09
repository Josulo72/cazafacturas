"""Extracción: de PDF a campos, y la cadena completa contra el dataset."""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

from backend.nucleo.analizador import analizar_fichero, resumir
from backend.nucleo.extractor import _a_fecha, _a_numero, _detectar_pais
from backend.nucleo.lectura import capacidades

RAIZ = Path(__file__).resolve().parents[2]
PDFS = RAIZ / "dataset" / "pdf"

requiere_pdf = pytest.mark.skipif(
    not capacidades()["pdf_texto"],
    reason="pdfplumber no está instalado",
)
requiere_muestras = pytest.mark.skipif(
    not (PDFS / "ES").is_dir(),
    reason="faltan los PDF de muestra: ejecuta `python -m dataset.render_pdf`",
)


# ---------------------------------------------------------------- importes

@pytest.mark.parametrize("texto,esperado", [
    ("1.234,56 €", 1234.56),      # España y Alemania
    ("$1,234.56", 1234.56),       # Estados Unidos y Reino Unido
    ("1234.56", 1234.56),
    ("2.250,00 €", 2250.00),
    ("189,00", 189.00),
    ("1,234", 1234.0),            # millares sin decimales
    ("0,00 €", 0.0),
    ("(1.234,56)", -1234.56),     # negativo contable
    ("Total:", None),
    ("", None),
])
def test_lectura_de_importes(texto, esperado):
    assert _a_numero(texto) == esperado


def test_el_separador_decimal_es_el_de_mas_a_la_derecha():
    """El mismo número escrito a la europea y a la americana da lo mismo."""
    assert _a_numero("1.234,56") == _a_numero("1,234.56") == 1234.56


# ---------------------------------------------------------------- fechas

@pytest.mark.parametrize("texto,pais,iso", [
    ("24/11/2025", "ES", "2025-11-24"),
    ("24.11.2025", "DE", "2025-11-24"),
    ("11/24/2025", "US", "2025-11-24"),
    ("2025-11-24", "ES", "2025-11-24"),
    ("Fecha de factura: 24/11/2025", "ES", "2025-11-24"),
    ("24 de noviembre de 2025", "ES", "2025-11-24"),
])
def test_lectura_de_fechas(texto, pais, iso):
    assert _a_fecha(texto, pais).isoformat() == iso


def test_misma_cifra_distinto_pais_distinta_fecha():
    """05/03 es 5 de marzo en España y 3 de mayo en Estados Unidos."""
    assert _a_fecha("05/03/2025", "ES").isoformat() == "2025-03-05"
    assert _a_fecha("05/03/2025", "US").isoformat() == "2025-05-03"


def test_fecha_ilegible():
    assert _a_fecha("no soy una fecha", "ES") is None


# ---------------------------------------------------------------- país

@pytest.mark.parametrize("texto,pais", [
    ("FACTURA Base imponible IVA 21% NIF: B12345674", "ES"),
    ("RECHNUNG Nettobetrag MwSt 19% Gesamtbetrag", "DE"),
    ("INVOICE Amount due £1,200.00 VAT Reg No", "UK"),
])
def test_deteccion_de_pais(texto, pais):
    assert _detectar_pais(texto) == pais


# ---------------------------------------------------------------- extremo a extremo

@requiere_pdf
@requiere_muestras
def test_extraccion_exacta_sobre_los_pdf_del_dataset():
    """La prueba que de verdad importa: PDF de entrada, campos de salida,
    comparados uno a uno contra el esperado."""
    resultados = []
    for pais in ("ES", "UK", "US", "DE"):
        for pdf in sorted((PDFS / pais).glob("*.pdf")):
            esperado = json.loads(
                (RAIZ / "dataset" / pais / "esperado" / f"{pdf.stem}.json")
                .read_text(encoding="utf-8")
            )
            resultados.append(analizar_fichero(pdf, pais, esperado))

    assert resultados, "No se ha analizado ningún PDF"
    resumen = resumir(resultados)

    fallos = [
        (r.nombre, d["campo"], d["esperado"], d["obtenido"])
        for r in resultados
        for d in r.puntuacion["detalle"] if not d["acierto"]
    ]
    assert not fallos, fallos
    assert resumen.precision_media == 1.0
    assert resumen.validas == resumen.total


@requiere_pdf
@requiere_muestras
def test_las_trampas_en_pdf_no_pasan_desapercibidas():
    pdfs = sorted((PDFS / "trampas").glob("*.pdf"))
    assert pdfs, "No hay PDF de casos trampa"
    mudos = [
        p.name for p in pdfs
        if not analizar_fichero(p).informe["hallazgos"]
    ]
    assert not mudos, mudos


@requiere_pdf
@requiere_muestras
def test_confianza_alta_en_documento_con_capa_de_texto():
    r = analizar_fichero(next((PDFS / "ES").glob("*.pdf")))
    assert r.documento["origen"] == "capa_texto"
    assert r.documento["confianza"] == 1.0
    assert r.extraccion["confianza"] > 0.8


def test_fichero_no_soportado_da_error_no_traza():
    from backend.nucleo.analizador import analizar_bytes
    r = analizar_bytes(b"lo que sea", "notas.txt")
    assert not r.ok
    assert "no soportada" in (r.error or "").lower()


def test_pdf_corrupto_da_error_no_traza():
    from backend.nucleo.analizador import analizar_bytes
    r = analizar_bytes(b"%PDF-1.4 basura", "roto.pdf")
    assert not r.ok
    assert r.error

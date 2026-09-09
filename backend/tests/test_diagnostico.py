"""El diagnóstico: qué falta, y si la calidad ha caído.

Lo segundo es lo que importa. El proyecto tiene una verdad conocida, así que
una regresión no es una impresión: es un número que baja. Estos tests
fabrican esa caída a propósito y comprueban que se detecta y que se explica
con nombres de campo concretos.
"""

from __future__ import annotations

import json

import pytest

from backend import diagnostico
from backend.diagnostico import Estado
from backend.nucleo import banco


# ------------------------------------------------------------------ entorno

def test_el_entorno_de_esta_maquina_esta_sano():
    inf = diagnostico.revisar_entorno()
    assert inf.sano, [c.detalle for c in inf.comprobaciones if c.estado is Estado.MAL]


def test_toda_comprobacion_floja_trae_su_remedio():
    """Un aviso sin remedio deja al usuario igual de perdido que un fallo
    silencioso. Si algo no está bien, hay que decir cómo se arregla."""
    inf = diagnostico.revisar_entorno()
    for c in inf.comprobaciones:
        if c.estado is not Estado.BIEN and c.nombre != "Almacenamiento":
            assert c.remedio, f"«{c.nombre}» avisa pero no dice cómo arreglarlo"


def test_el_informe_se_queda_con_lo_peor():
    inf = diagnostico.Informe(comprobaciones=[
        diagnostico.Comprobacion("a", Estado.BIEN, ""),
        diagnostico.Comprobacion("b", Estado.AVISO, ""),
    ])
    assert inf.peor is Estado.AVISO and inf.sano
    inf.comprobaciones.append(diagnostico.Comprobacion("c", Estado.MAL, ""))
    assert inf.peor is Estado.MAL and not inf.sano


# ------------------------------------------------------------------ banco

def test_el_banco_recoge_los_casos_de_los_cuatro_paises():
    normales = banco.casos(trampas=False)
    assert len(normales) == 24
    assert {c.pais for c in normales} == {"ES", "UK", "US", "DE"}
    assert all(not c.es_trampa for c in normales)


def test_las_trampas_no_traen_respuesta_correcta():
    """Una trampa no tiene «lo correcto»: tiene que saltar alguna regla.
    Por eso su `esperado` es None y no se puntúa como las demás."""
    trampas = [c for c in banco.casos() if c.es_trampa]
    assert len(trampas) == 50
    assert all(c.esperado is None for c in trampas)


def test_se_prefieren_los_pdf_al_json():
    """Con PDF el banco ejercita lectura, extracción y validación. Con JSON
    solo las reglas. Si hay PDF generados, hay que usarlos."""
    if not (banco.MUESTRAS / "ES").is_dir():
        pytest.skip("no se han generado los PDF de muestra")
    assert all(isinstance(c.contenido, bytes) for c in banco.casos("ES", trampas=False))


# ------------------------------------------------------------------ regresión

def _metricas(**cambios) -> banco.Metricas:
    base = dict(precision=1.0, conformes=24, normales=24, cazadas=50, trampas=50,
                segundos=6.0, fallos_por_campo={}, trampas_escapadas=[])
    base.update(cambios)
    return banco.Metricas(**base)


LINEA_BASE = {"precision": 1.0, "conformes": 24, "normales": 24,
              "cazadas": 50, "trampas": 50, "segundos": 6.0}


def test_sin_cambios_no_hay_desvio():
    assert diagnostico.comparar(LINEA_BASE, _metricas()) == []


def test_la_precision_que_baja_se_detecta_y_dice_que_campos():
    desvios = diagnostico.comparar(LINEA_BASE, _metricas(
        precision=0.96, fallos_por_campo={"emisor.nif": 4, "total": 2},
    ))
    assert len(desvios) == 1
    assert desvios[0].medida == "Precisión de extracción"
    # Lo importante no es que avise: es que diga por dónde empezar a mirar.
    assert "emisor.nif" in desvios[0].detalle
    assert "total" in desvios[0].detalle


def test_una_trampa_que_se_escapa_se_detecta_con_nombre():
    desvios = diagnostico.comparar(LINEA_BASE, _metricas(
        cazadas=49, trampas_escapadas=["albaran_no_factura_es_documento.pdf"],
    ))
    assert len(desvios) == 1
    assert "albaran_no_factura_es_documento.pdf" in desvios[0].detalle


def test_una_factura_correcta_rechazada_se_detecta():
    """La regresión más traicionera: el validador se vuelve demasiado
    estricto y empieza a tumbar facturas que están bien."""
    desvios = diagnostico.comparar(LINEA_BASE, _metricas(conformes=22))
    assert len(desvios) == 1
    assert desvios[0].medida == "Facturas conformes"


def test_el_tiempo_aguanta_variacion_pero_no_un_desmadre():
    # La máquina que mide hoy no es la que fijó la línea base.
    assert diagnostico.comparar(LINEA_BASE, _metricas(segundos=12.0)) == []
    desvios = diagnostico.comparar(LINEA_BASE, _metricas(segundos=40.0))
    assert len(desvios) == 1 and desvios[0].medida == "Tiempo"


def test_mejorar_no_es_un_desvio():
    """Que suba la precisión no es una regresión. Parece obvio y es el fallo
    clásico de comparar con `!=` en vez de con `<`."""
    assert diagnostico.comparar(
        {**LINEA_BASE, "precision": 0.9}, _metricas(precision=1.0)
    ) == []


def test_varias_caidas_a_la_vez_se_cuentan_todas():
    desvios = diagnostico.comparar(LINEA_BASE, _metricas(
        precision=0.8, conformes=20, cazadas=40, segundos=90.0,
    ))
    assert {d.medida for d in desvios} == {
        "Precisión de extracción", "Facturas conformes", "Trampas cazadas", "Tiempo",
    }


# ------------------------------------------------------------------ línea base

def test_la_linea_base_esta_en_el_repositorio():
    """Si no está commiteada, cada máquina compara contra otra cosa y la
    comparación no significa nada."""
    base = banco.leer_linea_base()
    assert base is not None, "falta dataset/linea_base.json"
    assert base["precision"] == 1.0
    assert base["cazadas"] == base["trampas"]


def test_la_linea_base_es_json_legible():
    datos = json.loads(banco.LINEA_BASE.read_text(encoding="utf-8"))
    assert "fijada" in datos and "segundos" in datos

"""Las tres defensas de una aplicación que escucha en tu máquina.

Cada test reproduce el ataque que la defensa evita, no la línea de código
que la implementa. Si mañana alguien reescribe el guardián de otra forma,
estos tests siguen valiendo; si alguien lo borra, saltan.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Los guardianes se apagan con esta variable, y varios tests necesitan
# comprobar precisamente que están encendidos. Se limpia antes de importar
# la aplicación, que es cuando se decide.
os.environ.pop("CAZAFACTURAS_ABIERTO", None)

from backend.main import TESTIGO, app  # noqa: E402
from backend.seguridad import NOMBRE_TESTIGO, _es_local  # noqa: E402

LOCAL = "http://127.0.0.1:8765"


@pytest.fixture
def cliente():
    with TestClient(app, base_url=LOCAL) as c:
        yield c


@pytest.fixture
def sellado(cliente):
    """Un cliente que ya ha entrado por la puerta y tiene su testigo."""
    cliente.get("/")
    return cliente


# ------------------------------------------------------------------ Host

@pytest.mark.parametrize("anfitrion", [
    "127.0.0.1:8765", "localhost:8765", "127.0.0.1", "[::1]:8765", "127.1.2.3",
])
def test_anfitriones_de_esta_maquina(anfitrion):
    assert _es_local(anfitrion)


@pytest.mark.parametrize("anfitrion", [
    "malicioso.example",
    "cazafacturas.malicioso.example:8765",
    "127.0.0.1.malicioso.example",       # el truco clásico de parecer local
    "192.168.1.40:8765",
    "",
])
def test_anfitriones_ajenos(anfitrion):
    assert not _es_local(anfitrion)


def test_dns_rebinding_se_rechaza(cliente):
    """El ataque de verdad contra un servidor en localhost.

    El atacante hace que su dominio resuelva a 127.0.0.1. El navegador
    entrega la petición aquí creyendo que es el mismo origen, pero la
    cabecera Host delata de dónde venía.
    """
    r = cliente.get("/api/capacidades", headers={"Host": "malicioso.example"})
    assert r.status_code == 421
    assert "Host" in r.json()["detail"]


def test_peticion_legitima_pasa(cliente):
    assert cliente.get("/", headers={"Host": "127.0.0.1:8765"}).status_code == 200


# ------------------------------------------------------------------ Testigo

def test_api_sin_testigo_se_rechaza(cliente):
    r = cliente.get("/api/capacidades")
    assert r.status_code == 403
    assert "testigo" in r.json()["detail"].lower()


def test_la_puerta_reparte_testigo(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert cliente.cookies.get(NOMBRE_TESTIGO) == TESTIGO


def test_con_testigo_la_api_responde(sellado):
    r = sellado.get("/api/capacidades")
    assert r.status_code == 200
    assert r.json()["version"]


def test_testigo_equivocado_no_cuela(cliente):
    cliente.cookies.set(NOMBRE_TESTIGO, "no-es-este")
    assert cliente.get("/api/capacidades").status_code == 403


def test_la_cookie_no_se_puede_leer_desde_javascript(cliente):
    """HttpOnly: si un XSS llegara a colarse, no se lleva el testigo."""
    r = cliente.get("/")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie


# ------------------------------------------------------------------ CSRF

def test_origen_ajeno_en_metodo_que_cambia_estado(sellado):
    """Una web abierta en otra pestaña no puede borrarte el historial."""
    r = sellado.delete(
        "/api/historial/loquesea",
        headers={"Origin": "https://malicioso.example"},
    )
    assert r.status_code == 403
    assert "Origen" in r.json()["detail"]


def test_origen_propio_pasa(sellado):
    """Con el origen bueno llega al endpoint: 404 porque el lote no existe,
    que es exactamente lo que se quiere ver —ha pasado el guardián—."""
    r = sellado.delete("/api/historial/loquesea", headers={"Origin": LOCAL})
    assert r.status_code == 404


# ------------------------------------------------------------------ Cabeceras

def test_politica_de_contenido(cliente):
    csp = cliente.get("/").headers["content-security-policy"]
    # Nada de fuera: ni scripts, ni fuentes, ni conexiones.
    assert "default-src 'self'" in csp
    assert "font-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_otras_cabeceras(cliente):
    h = cliente.get("/").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"] == "no-referrer"
    assert "camera=()" in h["permissions-policy"]


# ------------------------------------------------------------------ Ficheros

def test_travesia_de_directorios_en_muestras(sellado):
    """La ruta de muestras compone un camino con texto de la URL: es el
    sitio natural para intentar salirse de la carpeta."""
    for intento in (
        "/api/muestras/..%2f..%2f..%2fetc/passwd",
        "/api/muestras/ES/..%2f..%2f..%2fbackend%2fmain.py",
    ):
        assert sellado.get(intento).status_code in (400, 404)


def test_formato_no_admitido_se_rechaza(sellado):
    r = sellado.post(
        "/api/analizar",
        files={"ficheros": ("malicioso.exe", b"MZ\x90\x00", "application/octet-stream")},
        headers={"Origin": LOCAL},
    )
    assert r.status_code == 400
    assert "formato" in r.json()["detail"].lower()


def test_tope_de_ficheros_por_lote(sellado):
    from backend.main import MAX_FICHEROS
    ficheros = [
        ("ficheros", (f"f{i}.pdf", b"%PDF-1.4", "application/pdf"))
        for i in range(MAX_FICHEROS + 1)
    ]
    r = sellado.post("/api/analizar", files=ficheros, headers={"Origin": LOCAL})
    assert r.status_code == 400

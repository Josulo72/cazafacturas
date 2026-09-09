"""Seguridad de una aplicación que escucha en tu propia máquina.

Esto no tiene cuentas ni contraseñas, así que media lista de tópicos no
aplica: no hay sesiones que robar, ni SQL que inyectar, ni URLs que se pidan
a terceros. Lo que sí aplica son tres cosas, y son las que hay aquí.

**1. DNS rebinding.** Es *el* ataque contra los programas que escuchan en
localhost, y no lo para CORS. Una web maliciosa apunta su dominio a
127.0.0.1; a partir de ese momento el navegador considera que esta
aplicación es su mismo origen, se salta la política de origen único y lee
tus facturas. Lo que sí lo para es mirar la cabecera `Host`: la petición
reencaminada llega con el dominio del atacante, no con `127.0.0.1`.

**2. CSRF.** Cualquier página abierta en el navegador puede lanzar un POST a
este puerto. No puede leer la respuesta, pero sí llenarte el historial o
disparar trabajo. Se corta comprobando el origen en los métodos que cambian
estado.

**3. Otro proceso en la misma máquina.** Contra eso el `Host` no vale, porque
un proceso local puede poner la cabecera que quiera. Para eso está el
testigo de sesión: un secreto que se genera al arrancar y que solo conoce
quien haya abierto la aplicación por la puerta.

Los tres se pueden desactivar con `CAZAFACTURAS_ABIERTO=1`, que es lo que
usan los tests. En una máquina de verdad, no.
"""

from __future__ import annotations

import ipaddress
import os
import secrets
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

NOMBRE_TESTIGO = "cazafacturas_sesion"

# Métodos que no cambian nada: no hace falta comprobarles el origen.
METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})

# Rutas que tienen que responder sin testigo, porque son justamente por
# donde se entra a conseguirlo.
RUTAS_ABIERTAS = frozenset({"/", "/app", "/bocetos", "/favicon.ico"})


def abierto() -> bool:
    """Modo sin defensas. Solo para tests y desarrollo."""
    return os.environ.get("CAZAFACTURAS_ABIERTO") == "1"


# ---------------------------------------------------------------------------
# El testigo
# ---------------------------------------------------------------------------

def crear_testigo(directorio: Path) -> str:
    """Genera el secreto de esta ejecución y lo deja en disco.

    Se escribe a fichero para que el lanzador pueda leerlo y abrir el
    navegador por la puerta buena, y para poder recuperarlo si cierras la
    pestaña. Con permisos de solo-dueño donde el sistema lo permite.
    """
    testigo = secrets.token_urlsafe(32)
    ruta = directorio / "testigo"
    ruta.write_text(testigo, encoding="utf-8")
    try:
        ruta.chmod(0o600)
    except (OSError, NotImplementedError):
        pass          # En Windows los permisos POSIX no aplican.
    return testigo


def _es_local(anfitrion: str) -> bool:
    """¿La cabecera Host apunta a esta misma máquina?

    Se compara contra la dirección, no contra el nombre: `localhost` y
    `127.0.0.1` valen, pero `malicioso.example` no, aunque su DNS resuelva
    a 127.0.0.1. Ahí está toda la defensa contra el rebinding.
    """
    if not anfitrion:
        return False

    sin_puerto = anfitrion.rsplit(":", 1)[0] if ":" in anfitrion else anfitrion
    sin_puerto = sin_puerto.strip("[]").lower()      # IPv6 llega entre corchetes

    if sin_puerto in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(sin_puerto).is_loopback
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Los guardianes
# ---------------------------------------------------------------------------

class Guardian(BaseHTTPMiddleware):
    """Las tres comprobaciones, en el orden en que descartan más rápido."""

    def __init__(self, app, testigo: str, anfitriones_extra: frozenset[str] = frozenset()):
        super().__init__(app)
        self.testigo = testigo
        # Cuando alguien arranca a propósito en una IP de la red local,
        # esa IP pasa a ser legítima. Es una decisión suya, no un descuido.
        self.anfitriones_extra = anfitriones_extra

    def _anfitrion_valido(self, anfitrion: str) -> bool:
        if _es_local(anfitrion):
            return True
        sin_puerto = anfitrion.rsplit(":", 1)[0].strip("[]").lower()
        return sin_puerto in self.anfitriones_extra

    async def dispatch(self, peticion: Request, siguiente):
        if abierto():
            return await siguiente(peticion)

        # --- 1. Rebinding -------------------------------------------------
        anfitrion = peticion.headers.get("host", "")
        if not self._anfitrion_valido(anfitrion):
            return JSONResponse(
                status_code=421,        # Misdirected Request: es literalmente eso
                content={
                    "detail": (
                        f"Cabecera Host no admitida: «{anfitrion}». Esta "
                        "aplicación solo atiende peticiones dirigidas a esta "
                        "máquina. Ábrela en 127.0.0.1."
                    )
                },
            )

        ruta = peticion.url.path

        # --- 2. CSRF ------------------------------------------------------
        if peticion.method not in METODOS_SEGUROS:
            origen = peticion.headers.get("origin") or peticion.headers.get("referer") or ""
            if origen:
                from urllib.parse import urlparse
                if not self._anfitrion_valido(urlparse(origen).netloc):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": f"Origen no admitido: «{origen}»."},
                    )

        # --- 3. Testigo ---------------------------------------------------
        if ruta.startswith("/api/") and ruta not in RUTAS_ABIERTAS:
            if not secrets.compare_digest(
                peticion.cookies.get(NOMBRE_TESTIGO, ""), self.testigo
            ):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": (
                            "Falta el testigo de sesión. Abre la aplicación con "
                            "el comando `cazafacturas`, que la lanza por la "
                            "puerta buena."
                        )
                    },
                )

        return await siguiente(peticion)


def sellar(respuesta, testigo: str):
    """Entrega el testigo al navegador.

    `SameSite=Strict` es la segunda barrera contra CSRF: el navegador no
    manda esta cookie en peticiones que nazcan en otro sitio, así que aunque
    alguien acierte con el origen, la petición llega sin credencial.
    """
    respuesta.set_cookie(
        NOMBRE_TESTIGO,
        testigo,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return respuesta


def cabeceras_duras(app) -> None:
    """Cabeceras de respuesta que cierran lo que quede suelto."""

    @app.middleware("http")
    async def _(peticion: Request, siguiente):
        respuesta = await siguiente(peticion)
        # Todo lo que carga la página sale de aquí: ni scripts, ni fuentes,
        # ni imágenes de fuera. Si algún día alguien mete un CDN, esto lo
        # rompe en la primera prueba, que es justo lo que se quiere.
        respuesta.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "form-action 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'none'"
        )
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["Referrer-Policy"] = "no-referrer"
        # Sin permisos de dispositivo: esto lee PDF, no la cámara.
        respuesta.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        )
        return respuesta

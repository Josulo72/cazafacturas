from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.api.ejecutar import ejecutar_dataset
from backend.api.motores import crear_catalogo
from backend.api.resultados import crear_gestion
from backend.nucleo.cache import CacheResultados
from backend.nucleo.dataset import cargar_dataset

RAIZ = Path(__file__).resolve().parent.parent


def dir_datos(raiz: Path = RAIZ) -> Path:
    """Dónde se guardan los datos locales. Respetar CAZAFACTURAS_HOME;
    fuera de un checkout (pip instalado) cae en el home del usuario."""
    env = os.environ.get("CAZAFACTURAS_HOME")
    if env:
        ruta = Path(env)
    elif (raiz / ".git").exists():
        ruta = raiz / "resultados"
    else:
        ruta = Path.home() / ".cazafacturas"
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


app = FastAPI(title="Cazafacturas", version="0.4.0")

_DATOS = dir_datos()
_catalogo = crear_catalogo()
_gestion = crear_gestion(_DATOS / "ejecuciones")
_dataset = cargar_dataset(RAIZ / "dataset")
_cache = CacheResultados(_DATOS / "cache")

_estados: dict[str, dict] = {}
_estados_lock = threading.Lock()


class EjecutarRequest(BaseModel):
    id_motor: str
    modelo: str | None = None
    trampas: bool = False
    prompt_extra: str = ""
    idioma: str = "es"

    class Config:
        json_schema_extra = {"example": {"id_motor": "cli", "idioma": "es"}}


class _Progreso:
    def __init__(self, id_ejecucion: str):
        self.id_ejecucion = id_ejecucion

    def __call__(self, pos, total, caso_id, estado):
        with _estados_lock:
            _estados[self.id_ejecucion] = {
                "pos": pos,
                "total": total,
                "caso": caso_id,
                "estado": estado,
            }


@app.get("/api/estado")
def api_estado():
    return {
        "motores": [
            {"id": i, **info.__dict__} for i, info in _catalogo.todos_dispuestos()
        ]
    }


@app.get("/api/dataset")
def api_dataset(trampas: bool = Query(False), pais: str | None = Query(None)):
    casos = _dataset.todos() if trampas else _dataset.casos_normales()
    if pais:
        casos = [c for c in casos if str(c.esperado.get("pais", "ES")).upper() == pais.upper()]
    return [
        {
            "id": c.id,
            "es_trampa": c.es_trampa,
            "documento": c.documento,
            "esperado": c.esperado,
        }
        for c in casos
    ]


@app.get("/api/paises")
def api_paises():
    from backend.nucleo.paises import PAISES

    return [
        {"codigo": p.codigo, "es": p.nombre["es"], "en": p.nombre["en"], "moneda": p.moneda}
        for p in PAISES.values()
    ]


@app.post("/api/ejecutar")
def api_ejecutar(req: EjecutarRequest):
    if req.id_motor not in _catalogo.disponible():
        raise HTTPException(400, f"Motor '{req.id_motor}' no disponible")

    id_ejecucion = _gestion.nueva_ejecucion(req.id_motor, req.modelo or "")
    with _estados_lock:
        _estados[id_ejecucion] = {"pos": 0, "total": 0, "caso": "", "estado": "en_cola"}

    caso_modelo = (
        _catalogo.get(req.id_motor).modelo
        if (req.id_motor == "cli" and req.modelo)
        else req.modelo or ""
    )

    def trabajo():
        from backend.api.motores import crear_catalogo as _cc

        catalogo = _cc(modelo_cli=req.modelo)
        info = catalogo.get(req.id_motor).detectar()
        casos = _dataset.todos() if req.trampas else _dataset.casos_normales()
        try:
            ejecutar_dataset(
                casos,
                req.id_motor,
                catalogo,
                _cache,
                progress=_Progreso(id_ejecucion),
                prompt_extra=req.prompt_extra,
                registrar=lambda r: _gestion.registrar(id_ejecucion, r),
                idioma=req.idioma,
            )
        except Exception as e:
            with _estados_lock:
                _estados[id_ejecucion] = {
                    "pos": 0,
                    "total": 0,
                    "caso": "",
                    "estado": f"error: {e}",
                }
            return
        with _estados_lock:
            _estados[id_ejecucion] = {
                "pos": 0,
                "total": 0,
                "caso": "",
                "estado": "terminada",
            }

    hilo = threading.Thread(target=trabajo, daemon=True)
    hilo.start()
    return {"id_ejecucion": id_ejecucion}


@app.get("/api/ejecutar/{id_ejecucion}/estado")
def api_ejecutar_estado(id_ejecucion: str):
    with _estados_lock:
        estado = _estados.get(id_ejecucion)
    if estado is None:
        raise HTTPException(404, "Ejecución no encontrada")
    return estado


@app.get("/api/ejecutar/{id_ejecucion}/stream")
def api_ejecutar_stream(id_ejecucion: str):
    def generador():
        anterior = None
        while True:
            with _estados_lock:
                estado = _estados.get(id_ejecucion)
            if estado is None:
                yield "event: error\ndata: {\"detalle\":\"no existe\"}\n\n"
                return
            if estado != anterior:
                yield f"data: {json.dumps(estado, ensure_ascii=False)}\n\n"
                anterior = estado
            if estado.get("estado") == "terminada":
                yield f"event: fin\ndata: {json.dumps({'id_ejecucion': id_ejecucion})}\n\n"
                return
            if estado.get("estado", "").startswith("error"):
                yield f"event: error\ndata: {json.dumps(estado, ensure_ascii=False)}\n\n"
                return
            time.sleep(0.3)

    return StreamingResponse(
        generador(), media_type="text/event-stream"
    )


@app.get("/api/resultados")
def api_resultados():
    return [
        {
            "id_ejecucion": r.id_ejecucion,
            "id_motor": r.id_motor,
            "modelo": r.modelo,
            "fecha": r.fecha,
            "n_casos": r.n_casos,
            "precision": r.precision,
            "tasa_invencion": r.tasa_invencion,
            "segundos": r.segundos,
            "cacheados": r.cacheados,
        }
        for r in _gestion.historial()
    ]


@app.get("/api/resultados/{id_ejecucion}")
def api_resultados_detalle(id_ejecucion: str):
    datos = _gestion.detalle(id_ejecucion)
    if datos is None:
        raise HTTPException(404, "Ejecución no encontrada")
    return datos


@app.get("/api/comparativa")
def api_comparativa():
    return _gestion.comparativa()


@app.get("/")
def pagina():
    return FileResponse(RAIZ / "frontend" / "index.html")


app.mount(
    "/static",
    StaticFiles(directory=RAIZ / "frontend"),
    name="static",
)


def main() -> None:
    """Arranca la webapp y abre el navegador. Uso: `cazafacturas`."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Cazafacturas — banco de evaluación de facturas")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--no-browser", action="store_true", help="No abrir el navegador")
    args = parser.parse_args()

    if not args.no_browser:
        def _abrir() -> None:
            import webbrowser

            webbrowser.open(f"http://{args.host}:{args.port}")

        threading.Timer(1.0, _abrir).start()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
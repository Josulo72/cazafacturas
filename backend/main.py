"""API de Cazafacturas.

Todo ocurre en la máquina de quien la ejecuta: los documentos no salen de
aquí, no hay claves que configurar y no se llama a ningún servicio externo.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.nucleo import historial as hist
from backend.nucleo.analizador import (
    analizar_bytes,
    analizar_json,
    capacidades,
    resumir,
)
from backend.nucleo.lectura import EXTENSIONES_SOPORTADAS
from backend.nucleo.paises import PAISES

RAIZ = Path(__file__).resolve().parent.parent
DATASET = RAIZ / "dataset"
MUESTRAS = DATASET / "pdf"

# Un PDF de factura no llega a 5 MB ni escaneado a 300 ppp. El tope evita
# que una subida enorme se coma la memoria del proceso.
MAX_BYTES_FICHERO = 25 * 1024 * 1024
MAX_FICHEROS = 50

VERSION = "1.0.0"

app = FastAPI(
    title="Cazafacturas",
    version=VERSION,
    description="Extracción y validación de facturas en local, sin IA.",
)

_DATOS = hist.dir_datos(RAIZ)
_historial = hist.Historial(_DATOS / "lotes")

_trabajos: dict[str, dict] = {}
_lock = threading.Lock()


def _estado(id_trabajo: str, **campos) -> None:
    with _lock:
        _trabajos.setdefault(id_trabajo, {}).update(campos)


# --------------------------------------------------------------------------
# Estado de la instalación
# --------------------------------------------------------------------------

@app.get("/api/capacidades")
def api_capacidades():
    caps = capacidades()
    return {
        "version": VERSION,
        "pdf_texto": caps["pdf_texto"],
        "ocr": caps["ocr"],
        "escaneados": caps["escaneados"],
        "formatos": caps["formatos"],
        "max_ficheros": MAX_FICHEROS,
        "max_mb": MAX_BYTES_FICHERO // (1024 * 1024),
        "muestras": MUESTRAS.is_dir(),
    }


@app.get("/api/paises")
def api_paises():
    return [
        {
            "codigo": p.codigo,
            "es": p.nombre["es"],
            "en": p.nombre["en"],
            "moneda": p.moneda,
            "id_fiscal": p.id_fiscal["es"],
            "impuesto": p.impuesto["es"],
        }
        for p in PAISES.values()
    ]


# --------------------------------------------------------------------------
# Análisis de ficheros subidos
# --------------------------------------------------------------------------

@app.post("/api/analizar")
async def api_analizar(
    ficheros: list[UploadFile] = File(...),
    pais: Optional[str] = Form(None),
):
    if not ficheros:
        raise HTTPException(400, "No se ha enviado ningún fichero.")
    if len(ficheros) > MAX_FICHEROS:
        raise HTTPException(
            400, f"Máximo {MAX_FICHEROS} ficheros por lote; has enviado {len(ficheros)}."
        )

    # Se leen aquí, dentro del contexto de la petición; el hilo de trabajo
    # ya solo ve bytes.
    entradas: list[tuple[bytes, str]] = []
    for fichero in ficheros:
        extension = Path(fichero.filename or "").suffix.lower()
        if extension not in EXTENSIONES_SOPORTADAS:
            raise HTTPException(
                400,
                f"«{fichero.filename}» no es un formato admitido. "
                f"Admitidos: {', '.join(sorted(EXTENSIONES_SOPORTADAS))}",
            )
        contenido = await fichero.read()
        if len(contenido) > MAX_BYTES_FICHERO:
            raise HTTPException(
                400,
                f"«{fichero.filename}» pesa más de "
                f"{MAX_BYTES_FICHERO // (1024 * 1024)} MB.",
            )
        entradas.append((contenido, fichero.filename or "documento"))

    codigo = (pais or "").upper() or None
    if codigo and codigo not in PAISES:
        raise HTTPException(400, f"País no soportado: {codigo}")

    id_trabajo = uuid.uuid4().hex[:12]
    _estado(id_trabajo, pos=0, total=len(entradas), actual="", estado="en_cola",
            id_lote=None)

    def trabajo() -> None:
        resultados = []
        try:
            for i, (contenido, nombre) in enumerate(entradas, start=1):
                _estado(id_trabajo, pos=i, total=len(entradas),
                        actual=nombre, estado="analizando")
                resultados.append(analizar_bytes(contenido, nombre, codigo))
            resumen = resumir(resultados, id_trabajo)
            _historial.guardar(resumen, origen="subida")
            _estado(id_trabajo, estado="terminado", id_lote=resumen.id,
                    actual="", pos=len(entradas))
        except Exception as e:  # pragma: no cover
            _estado(id_trabajo, estado=f"error: {e}")

    threading.Thread(target=trabajo, daemon=True).start()
    return {"id_trabajo": id_trabajo, "total": len(entradas)}


# --------------------------------------------------------------------------
# Banco de pruebas contra el dataset propio
# --------------------------------------------------------------------------

@app.post("/api/banco")
def api_banco(trampas: bool = True, pais: Optional[str] = None):
    """Pasa el extractor por el dataset del proyecto y lo puntúa.

    Es la métrica honesta: no mide un modelo ajeno, mide este código contra
    facturas cuyo resultado correcto se conoce de antemano.
    """
    codigo = (pais or "").upper() or None
    if codigo and codigo not in PAISES:
        raise HTTPException(400, f"País no soportado: {codigo}")

    id_trabajo = uuid.uuid4().hex[:12]
    casos = _casos_del_banco(codigo, trampas)
    if not casos:
        raise HTTPException(404, "No se ha encontrado el dataset.")

    _estado(id_trabajo, pos=0, total=len(casos), actual="", estado="en_cola",
            id_lote=None)

    def trabajo() -> None:
        resultados = []
        try:
            for i, (nombre, contenido, esperado, pais_caso) in enumerate(casos, 1):
                _estado(id_trabajo, pos=i, total=len(casos),
                        actual=nombre, estado="analizando")
                if isinstance(contenido, dict):
                    resultados.append(analizar_json(contenido, nombre, esperado))
                else:
                    resultados.append(
                        analizar_bytes(contenido, nombre, pais_caso, esperado)
                    )
            resumen = resumir(resultados, id_trabajo)
            _historial.guardar(resumen, origen="banco")
            _estado(id_trabajo, estado="terminado", id_lote=resumen.id,
                    actual="", pos=len(casos))
        except Exception as e:  # pragma: no cover
            _estado(id_trabajo, estado=f"error: {e}")

    threading.Thread(target=trabajo, daemon=True).start()
    return {"id_trabajo": id_trabajo, "total": len(casos)}


def _casos_del_banco(pais: Optional[str], trampas: bool) -> list[tuple]:
    """Los casos del dataset. Se prefieren los PDF: ejercitan la cadena
    completa. Si no se han generado, se cae al JSON y se validan las reglas."""
    casos: list[tuple] = []
    codigos = [pais] if pais else list(PAISES)

    for codigo in codigos:
        carpeta_esperado = DATASET / codigo / "esperado"
        if not carpeta_esperado.is_dir():
            continue
        for fichero in sorted(carpeta_esperado.glob("*.json")):
            esperado = json.loads(fichero.read_text(encoding="utf-8"))
            pdf = MUESTRAS / codigo / f"{fichero.stem}.pdf"
            if pdf.is_file():
                casos.append((pdf.name, pdf.read_bytes(), esperado, codigo))
            else:
                casos.append((fichero.name, esperado, esperado, codigo))

    if trampas:
        carpeta = DATASET / "trampas"
        for fichero in sorted(carpeta.glob("*_documento.json")):
            documento = json.loads(fichero.read_text(encoding="utf-8"))
            if pais and str(documento.get("pais", "ES")).upper() != pais:
                continue
            pdf = MUESTRAS / "trampas" / f"{fichero.stem}.pdf"
            if pdf.is_file():
                casos.append((pdf.name, pdf.read_bytes(), None,
                              str(documento.get("pais") or "ES").upper()))
            else:
                casos.append((fichero.name, documento, None, None))

    return casos


# --------------------------------------------------------------------------
# Progreso
# --------------------------------------------------------------------------

@app.get("/api/trabajos/{id_trabajo}")
def api_trabajo(id_trabajo: str):
    with _lock:
        estado = _trabajos.get(id_trabajo)
    if estado is None:
        raise HTTPException(404, "Trabajo no encontrado")
    return estado


@app.get("/api/trabajos/{id_trabajo}/stream")
def api_trabajo_stream(id_trabajo: str):
    def generador():
        anterior = None
        limite = time.monotonic() + 900          # corta a los 15 minutos
        while time.monotonic() < limite:
            with _lock:
                estado = _trabajos.get(id_trabajo)
            if estado is None:
                yield 'event: error\ndata: {"detalle":"no existe"}\n\n'
                return
            if estado != anterior:
                yield f"data: {json.dumps(estado, ensure_ascii=False)}\n\n"
                anterior = dict(estado)
            situacion = str(estado.get("estado", ""))
            if situacion == "terminado":
                yield f"event: fin\ndata: {json.dumps(estado, ensure_ascii=False)}\n\n"
                return
            if situacion.startswith("error"):
                yield f"event: error\ndata: {json.dumps(estado, ensure_ascii=False)}\n\n"
                return
            time.sleep(0.25)

    return StreamingResponse(
        generador(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------
# Historial
# --------------------------------------------------------------------------

@app.get("/api/historial")
def api_historial():
    return [e.a_dict() for e in _historial.listar()]


@app.get("/api/historial/{id_lote}")
def api_historial_detalle(id_lote: str):
    lote = _historial.leer(id_lote)
    if lote is None:
        raise HTTPException(404, "Lote no encontrado")
    return lote


@app.get("/api/historial/{id_lote}/csv")
def api_historial_csv(id_lote: str):
    lote = _historial.leer(id_lote)
    if lote is None:
        raise HTTPException(404, "Lote no encontrado")
    return PlainTextResponse(
        hist.a_csv(lote),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="cazafacturas-{id_lote}.csv"'
        },
    )


@app.delete("/api/historial/{id_lote}")
def api_historial_borrar(id_lote: str):
    if not _historial.borrar(id_lote):
        raise HTTPException(404, "Lote no encontrado")
    return {"borrado": id_lote}


# --------------------------------------------------------------------------
# Muestras
# --------------------------------------------------------------------------

@app.get("/api/muestras")
def api_muestras():
    if not MUESTRAS.is_dir():
        return []
    salida = []
    for carpeta in sorted(MUESTRAS.iterdir()):
        if not carpeta.is_dir():
            continue
        for pdf in sorted(carpeta.glob("*.pdf")):
            salida.append({
                "grupo": carpeta.name,
                "nombre": pdf.name,
                "es_trampa": carpeta.name == "trampas",
                "url": f"/api/muestras/{carpeta.name}/{pdf.name}",
                "kb": round(pdf.stat().st_size / 1024, 1),
            })
    return salida


@app.get("/api/muestras/{grupo}/{nombre}")
def api_muestra(grupo: str, nombre: str):
    ruta = (MUESTRAS / grupo / nombre).resolve()
    # Nunca servir fuera de la carpeta de muestras, venga lo que venga en la URL.
    if not str(ruta).startswith(str(MUESTRAS.resolve())) or not ruta.is_file():
        raise HTTPException(404, "Muestra no encontrada")
    return FileResponse(ruta, media_type="application/pdf", filename=nombre)


# --------------------------------------------------------------------------
# Frontend
# --------------------------------------------------------------------------

@app.get("/")
def portada():
    """La presentación cuando exista; mientras tanto, la aplicación."""
    presentacion = RAIZ / "frontend" / "presentacion.html"
    if presentacion.is_file():
        return FileResponse(presentacion)
    return FileResponse(RAIZ / "frontend" / "index.html")


@app.get("/app")
def aplicacion():
    return FileResponse(RAIZ / "frontend" / "index.html")


@app.get("/bocetos")
def bocetos():
    """Los bocetos de la animación, para decidir cuál se desarrolla."""
    return FileResponse(RAIZ / "frontend" / "bocetos.html")


app.mount("/static", StaticFiles(directory=RAIZ / "frontend"), name="static")


def main() -> None:
    """Arranca la webapp y abre el navegador. Uso: `cazafacturas`."""
    import argparse
    import os

    import uvicorn

    parser = argparse.ArgumentParser(
        description="Cazafacturas — extracción y validación de facturas en local"
    )
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--no-browser", action="store_true",
                        help="No abrir el navegador al arrancar")
    args = parser.parse_args()

    if not args.no_browser:
        def _abrir() -> None:
            import webbrowser
            webbrowser.open(f"http://{args.host}:{args.port}")

        threading.Timer(1.0, _abrir).start()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

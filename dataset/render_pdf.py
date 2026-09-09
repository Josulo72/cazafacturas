"""Convierte las facturas del dataset en PDF imprimibles.

Sirve para dos cosas: dar facturas de muestra que arrastrar a la aplicación
sin tener que enseñar las tuyas, y ejercitar la cadena completa
lectura -> extractor -> validador contra un PDF de verdad y no contra un
diccionario de laboratorio.

El diseño imita el de una factura real —cabecera, dos bloques de partes,
tabla de líneas, totales a la derecha— porque el extractor se apoya en esa
disposición.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

# --- Reproducibilidad ------------------------------------------------------
# Un PDF lleva por dentro la fecha en que se creó y un identificador único,
# así que el mismo dataset generaba 74 ficheros distintos cada vez: el
# repositorio se ensuciaba solo y no había forma de comprobar que los
# generadores siguen siendo deterministas. `invariant` congela ambas cosas,
# y `SOURCE_DATE_EPOCH` es el convenio que usan las construcciones
# reproducibles para decir «haz como si fuera esta fecha».
os.environ.setdefault("SOURCE_DATE_EPOCH", "1735689600")   # 2025-01-01 UTC

from reportlab import rl_config

rl_config.invariant = 1

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas

from backend.nucleo.paises import PAISES

ANCHO, ALTO = A4
MARGEN = 20 * mm

# Etiquetas por país, en el idioma en que saldría impresa la factura.
TEXTOS: dict[str, dict[str, str]] = {
    "ES": {
        "titulo": "FACTURA", "numero": "Nº Factura", "emision": "Fecha de factura",
        "vencimiento": "Fecha de vencimiento", "emisor": "Emisor",
        "receptor": "Cliente", "descripcion": "Descripción", "cantidad": "Cantidad",
        "precio": "Precio unitario", "importe": "Importe",
        "base": "Base imponible", "total": "Total a pagar", "retencion": "Retención IRPF",
    },
    "UK": {
        "titulo": "INVOICE", "numero": "Invoice No", "emision": "Invoice date",
        "vencimiento": "Due date", "emisor": "From", "receptor": "Bill to",
        "descripcion": "Description", "cantidad": "Qty", "precio": "Unit price",
        "importe": "Amount", "base": "Net amount", "total": "Amount due",
        "retencion": "Withholding",
    },
    "US": {
        "titulo": "INVOICE", "numero": "Invoice No", "emision": "Invoice date",
        "vencimiento": "Due date", "emisor": "From", "receptor": "Bill to",
        "descripcion": "Description", "cantidad": "Qty", "precio": "Rate",
        "importe": "Amount", "base": "Subtotal", "total": "Amount due",
        "retencion": "Withholding",
    },
    "DE": {
        "titulo": "RECHNUNG", "numero": "Rechnungsnummer", "emision": "Rechnungsdatum",
        "vencimiento": "Fälligkeitsdatum", "emisor": "Rechnungssteller",
        "receptor": "Kunde", "descripcion": "Bezeichnung", "cantidad": "Menge",
        "precio": "Einzelpreis", "importe": "Betrag", "base": "Nettobetrag",
        "total": "Gesamtbetrag", "retencion": "Einbehalt",
    },
}

# Cómo se escribe un importe en cada sitio.
_COMA_DECIMAL = {"ES", "DE"}


def _importe(valor: float, pais: str) -> str:
    moneda = PAISES[pais].moneda
    texto = f"{valor:,.2f}"
    if pais in _COMA_DECIMAL:
        texto = texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
        return f"{texto} {moneda}"
    return f"{moneda}{texto}"


def _fecha(valor: Any, pais: str) -> str:
    if not valor:
        return ""
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor[:10]).date()
        except ValueError:
            return valor
    if not isinstance(valor, date):
        return str(valor)
    return valor.strftime(PAISES[pais].fecha_formatos[0])


def _texto_derecha(c: rl_canvas.Canvas, x: float, y: float, texto: str) -> None:
    c.drawRightString(x, y, texto)


def render(factura: dict, destino: Path) -> Path:
    """Dibuja una factura y devuelve la ruta del PDF."""
    pais = str(factura.get("pais") or "ES").upper()
    if pais not in PAISES:
        pais = "ES"
    t = TEXTOS[pais]

    destino.parent.mkdir(parents=True, exist_ok=True)
    c = rl_canvas.Canvas(str(destino), pagesize=A4)
    c.setTitle(f"{t['titulo']} {factura.get('numero', '')}")

    y = ALTO - MARGEN

    # ---- Cabecera -------------------------------------------------------
    # Un albarán se imprime como albarán. Si el PDF pusiera "FACTURA" en la
    # cabecera, el caso trampa dejaría de serlo.
    titulos_alternativos = {
        "albaran": {"ES": "ALBARÁN DE ENTREGA", "UK": "DELIVERY NOTE",
                    "US": "PACKING SLIP", "DE": "LIEFERSCHEIN"},
        "presupuesto": {"ES": "PRESUPUESTO", "UK": "QUOTATION",
                        "US": "ESTIMATE", "DE": "ANGEBOT"},
        "pedido": {"ES": "PEDIDO", "UK": "PURCHASE ORDER",
                   "US": "PURCHASE ORDER", "DE": "BESTELLUNG"},
        "proforma": {"ES": "FACTURA PROFORMA", "UK": "PROFORMA INVOICE",
                     "US": "PROFORMA INVOICE", "DE": "PROFORMA-RECHNUNG"},
        "recibo": {"ES": "RECIBO", "UK": "RECEIPT",
                   "US": "RECEIPT", "DE": "QUITTUNG"},
    }
    tipo = str(factura.get("tipo_documento") or "factura").lower()
    # Un documento que trae su propio encabezado manda: es lo que vería
    # cualquiera al mirar el papel.
    titulo = (
        str(factura.get("titulo") or "").strip()
        or titulos_alternativos.get(tipo, {}).get(pais, t["titulo"])
    )

    c.setFont("Helvetica-Bold", 22)
    c.drawString(MARGEN, y, titulo)

    c.setFont("Helvetica", 10)
    y_dato = y
    # Algunos documentos del dataset traen la fecha en `fecha` en vez de
    # `fecha_emision`, porque no son facturas y no tienen ese campo.
    for etiqueta, valor in (
        (t["numero"], str(factura.get("numero") or "")),
        (t["emision"], _fecha(factura.get("fecha_emision")
                              or factura.get("fecha"), pais)),
        (t["vencimiento"], _fecha(factura.get("fecha_vencimiento"), pais)),
    ):
        if not valor:
            continue
        _texto_derecha(c, ANCHO - MARGEN - 42 * mm, y_dato, f"{etiqueta}:")
        c.setFont("Helvetica-Bold", 10)
        _texto_derecha(c, ANCHO - MARGEN, y_dato, valor)
        c.setFont("Helvetica", 10)
        y_dato -= 5.5 * mm

    y = min(y - 16 * mm, y_dato - 6 * mm)

    # ---- Emisor y receptor ---------------------------------------------
    def bloque(x: float, titulo: str, parte: Optional[dict]) -> float:
        if not parte:
            return y
        yy = y
        c.setFont("Helvetica-Bold", 8)
        c.setFillGray(0.45)
        c.drawString(x, yy, titulo.upper())
        c.setFillGray(0)
        yy -= 5.5 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x, yy, str(parte.get("nombre", ""))[:44])
        yy -= 5 * mm
        c.setFont("Helvetica", 9)
        etiqueta_id = PAISES[pais].id_fiscal["es" if pais == "ES" else "en"]
        c.drawString(x, yy, f"{etiqueta_id}: {parte.get('nif', '')}")
        direccion = parte.get("direccion") or {}
        if isinstance(direccion, dict) and direccion.get("calle"):
            yy -= 4.5 * mm
            c.drawString(x, yy, str(direccion.get("calle", ""))[:48])
            yy -= 4.5 * mm
            c.drawString(x, yy, " ".join(str(direccion.get(k, "")) for k in
                                         ("codigo_postal", "ciudad", "provincia")).strip())
        return yy

    y_izq = bloque(MARGEN, t["emisor"], factura.get("emisor"))
    y_der = bloque(ANCHO / 2 + 5 * mm, t["receptor"], factura.get("receptor"))
    y = min(y_izq, y_der) - 12 * mm

    # ---- Tabla de líneas ------------------------------------------------
    col_desc = MARGEN
    col_cant = MARGEN + 96 * mm
    col_prec = MARGEN + 122 * mm
    col_imp = ANCHO - MARGEN

    c.setFillGray(0.92)
    c.rect(MARGEN - 2 * mm, y - 2 * mm, ANCHO - 2 * MARGEN + 4 * mm, 7 * mm,
           stroke=0, fill=1)
    c.setFillGray(0)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col_desc, y, t["descripcion"])
    _texto_derecha(c, col_cant, y, t["cantidad"])
    _texto_derecha(c, col_prec, y, t["precio"])
    _texto_derecha(c, col_imp, y, t["importe"])
    y -= 8 * mm

    c.setFont("Helvetica", 9)
    for linea in factura.get("lineas") or []:
        if y < MARGEN + 60 * mm:
            c.showPage()
            y = ALTO - MARGEN
            c.setFont("Helvetica", 9)
        c.drawString(col_desc, y, str(linea.get("descripcion", ""))[:58])
        cantidad = linea.get("cantidad")
        if cantidad is not None:
            texto_cant = f"{float(cantidad):g}"
            if pais in _COMA_DECIMAL:
                texto_cant = texto_cant.replace(".", ",")
            _texto_derecha(c, col_cant, y, texto_cant)
        if linea.get("precio_unitario") is not None:
            _texto_derecha(c, col_prec, y, _importe(float(linea["precio_unitario"]), pais))
        if linea.get("importe") is not None:
            _texto_derecha(c, col_imp, y, _importe(float(linea["importe"]), pais))
        y -= 5.5 * mm

    y -= 3 * mm
    c.setStrokeGray(0.75)
    c.line(ANCHO / 2, y, ANCHO - MARGEN, y)
    y -= 7 * mm

    # ---- Totales --------------------------------------------------------
    etiqueta_x = ANCHO - MARGEN - 45 * mm

    def fila(etiqueta: str, valor: float, negrita: bool = False) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if negrita else "Helvetica", 11 if negrita else 9)
        _texto_derecha(c, etiqueta_x, y, etiqueta)
        _texto_derecha(c, ANCHO - MARGEN, y, _importe(valor, pais))
        y -= 6 * mm

    if factura.get("base_imponible") is not None:
        fila(t["base"], float(factura["base_imponible"]))

    for tramo in factura.get("iva") or []:
        porcentaje = float(tramo.get("porcentaje", 0))
        texto_pct = f"{porcentaje:g}".replace(".", "," if pais in _COMA_DECIMAL else ".")
        fila(f"{PAISES[pais].impuesto['es' if pais == 'ES' else 'en']} {texto_pct}%",
             float(tramo.get("cuota", 0)))

    retencion = factura.get("retencion")
    if isinstance(retencion, dict):
        porcentaje = float(retencion.get("porcentaje", 0))
        texto_pct = f"{porcentaje:g}".replace(".", "," if pais in _COMA_DECIMAL else ".")
        fila(f"{t['retencion']} {texto_pct}%", -float(retencion.get("cuota", 0)))

    y -= 1 * mm
    c.setStrokeGray(0.3)
    c.line(etiqueta_x - 20 * mm, y + 4 * mm, ANCHO - MARGEN, y + 4 * mm)
    y -= 2 * mm
    if factura.get("total") is not None:
        fila(t["total"], float(factura["total"]), negrita=True)

    c.setFont("Helvetica", 7)
    c.setFillGray(0.55)
    c.drawString(MARGEN, MARGEN,
                 "Documento de muestra generado por Cazafacturas. "
                 "Empresas y datos ficticios.")

    c.showPage()
    c.save()
    return destino


def render_dataset(raiz: Path, destino: Path, incluir_trampas: bool = True) -> list[Path]:
    """Pasa a PDF todo el dataset. Devuelve las rutas generadas."""
    generados: list[Path] = []

    for codigo in PAISES:
        carpeta = raiz / codigo / "esperado"
        if not carpeta.is_dir():
            continue
        for fichero in sorted(carpeta.glob("*.json")):
            datos = json.loads(fichero.read_text(encoding="utf-8"))
            generados.append(render(datos, destino / codigo / f"{fichero.stem}.pdf"))

    if incluir_trampas:
        trampas = raiz / "trampas"
        for fichero in sorted(trampas.glob("*_documento.json")):
            datos = json.loads(fichero.read_text(encoding="utf-8"))
            generados.append(
                render(datos, destino / "trampas" / f"{fichero.stem}.pdf")
            )

    return generados


if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    salida = base / "pdf"
    rutas = render_dataset(base, salida)
    print(f"{len(rutas)} PDF generados en {salida}")

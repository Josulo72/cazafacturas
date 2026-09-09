"""De un fichero a texto plano, con posiciones.

Tres caminos, en este orden:

1. PDF con capa de texto  -> `pdfplumber`, extracción directa y exacta.
2. PDF escaneado          -> se rasteriza con `pypdfium2` y va a OCR.
3. Imagen suelta          -> directo a OCR.

El OCR es `rapidocr-onnxruntime`: se instala con pip y trae sus modelos
dentro, así que no hace falta Tesseract ni ningún binario del sistema.
Si no está instalado, la lectura de escaneados se degrada con un aviso
claro en vez de reventar.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

EXTENSIONES_PDF = {".pdf"}
EXTENSIONES_IMAGEN = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
EXTENSIONES_SOPORTADAS = EXTENSIONES_PDF | EXTENSIONES_IMAGEN

# Por debajo de esto damos la página por escaneada y la mandamos a OCR.
MIN_CARACTERES_CAPA_TEXTO = 40

# Escala de rasterizado para OCR. 300 ppp equivalentes; subirlo mejora
# el reconocimiento de letra pequeña a costa de memoria y tiempo.
ESCALA_RASTER = 300 / 72

# ---------------------------------------------------------------------------
# Límites de recursos
# ---------------------------------------------------------------------------
# Un PDF que llega de fuera es código hostil hasta que se demuestre lo
# contrario, y este es el único sitio del programa donde se parsea algo que
# ha escrito un tercero. Sin topes, un documento de tres mil páginas —o uno
# de una sola página de diez metros de lado— deja la máquina clavada. No hay
# que romperse la cabeza para fabricarlo: basta con un bucle.
#
# Los topes se eligen por lo que es una factura de verdad, no por lo que
# aguanta el ordenador: una factura de más de treinta páginas no existe.

MAX_PAGINAS = 30

# Presupuesto de reloj por documento. Se comprueba entre páginas, que es
# donde se puede cortar sin dejar el estado a medias.
MAX_SEGUNDOS_DOCUMENTO = 60.0

# Una página de tamaño absurdo revienta la memoria al rasterizarla, y ese es
# el vector clásico de bomba de descompresión en PDF: poco fichero, mucha
# superficie. A 300 ppp, un A4 son 8,7 millones de píxeles.
MAX_PIXELES_PAGINA = 50_000_000


class Origen(str, Enum):
    CAPA_TEXTO = "capa_texto"
    OCR = "ocr"
    MIXTO = "mixto"
    VACIO = "vacio"


@dataclass
class Palabra:
    """Una palabra con su caja, en puntos PDF y con el origen (0,0) arriba."""
    texto: str
    x0: float
    y0: float
    x1: float
    y1: float
    pagina: int
    confianza: float = 1.0


@dataclass
class Pagina:
    numero: int
    texto: str
    ancho: float
    alto: float
    origen: Origen
    palabras: list[Palabra] = field(default_factory=list)


@dataclass
class Documento:
    ruta: Optional[Path]
    nombre: str
    paginas: list[Pagina] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n".join(p.texto for p in self.paginas)

    @property
    def palabras(self) -> list[Palabra]:
        return [w for p in self.paginas for w in p.palabras]

    @property
    def origen(self) -> Origen:
        origenes = {p.origen for p in self.paginas}
        if not origenes or origenes == {Origen.VACIO}:
            return Origen.VACIO
        origenes.discard(Origen.VACIO)
        if len(origenes) == 1:
            return next(iter(origenes))
        return Origen.MIXTO

    @property
    def confianza_media(self) -> float:
        palabras = [w for w in self.palabras if w.texto.strip()]
        if not palabras:
            return 0.0
        return round(sum(w.confianza for w in palabras) / len(palabras), 4)

    def a_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "paginas": len(self.paginas),
            "origen": self.origen.value,
            "confianza": self.confianza_media,
            "caracteres": len(self.texto),
            "avisos": self.avisos,
        }


class LecturaNoSoportada(Exception):
    """El fichero no es un formato que sepamos leer."""


# ---------------------------------------------------------------------------
# Disponibilidad de las piezas opcionales
# ---------------------------------------------------------------------------

def _hay(modulo: str) -> bool:
    from importlib.util import find_spec
    try:
        return find_spec(modulo) is not None
    except (ImportError, ValueError):
        return False


def capacidades() -> dict[str, bool]:
    """Qué sabe hacer esta instalación. La interfaz lo enseña al usuario."""
    return {
        "pdf_texto": _hay("pdfplumber"),
        "rasterizado": _hay("pypdfium2"),
        "ocr": _hay("rapidocr_onnxruntime"),
    }


_ocr_motor = None


def _obtener_ocr():
    """El motor OCR se construye una sola vez: cargar los modelos es caro."""
    global _ocr_motor
    if _ocr_motor is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_motor = RapidOCR()
    return _ocr_motor


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def _ocr_imagen(datos: bytes, pagina: int, escala: float = 1.0) -> tuple[str, list[Palabra]]:
    """Pasa una imagen por OCR y devuelve texto y palabras con su caja.

    `escala` convierte de píxeles de la imagen a puntos del PDF, para que
    las coordenadas sean comparables con las de la capa de texto.
    """
    resultado, _ = _obtener_ocr()(datos)
    if not resultado:
        return "", []

    palabras: list[Palabra] = []
    for caja, texto, confianza in resultado:
        xs = [p[0] for p in caja]
        ys = [p[1] for p in caja]
        palabras.append(Palabra(
            texto=texto,
            x0=min(xs) / escala,
            y0=min(ys) / escala,
            x1=max(xs) / escala,
            y1=max(ys) / escala,
            pagina=pagina,
            confianza=float(confianza),
        ))

    # RapidOCR devuelve las cajas ya ordenadas por lectura, pero un
    # reordenado por bandas horizontales es más robusto en facturas
    # a dos columnas.
    palabras.sort(key=lambda w: (round(w.y0 / 8), w.x0))

    lineas: list[list[str]] = []
    banda_actual = -999.0
    for w in palabras:
        if abs(w.y0 - banda_actual) > 8:
            lineas.append([])
            banda_actual = w.y0
        lineas[-1].append(w.texto)

    return "\n".join(" ".join(l) for l in lineas), palabras


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _rasterizar(ruta_o_bytes, indice: int) -> tuple[bytes, float]:
    """Convierte una página de PDF en PNG. Devuelve los bytes y la escala.

    Si la página es enorme se baja la escala en vez de rechazarla: un plano
    A0 escaneado es un documento legítimo, y prefiero leerlo a menos
    resolución que negarme a leerlo.
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(ruta_o_bytes)
    try:
        pagina = pdf[indice]
        escala = ESCALA_RASTER
        pixeles = pagina.get_width() * pagina.get_height() * escala * escala
        if pixeles > MAX_PIXELES_PAGINA:
            escala *= (MAX_PIXELES_PAGINA / pixeles) ** 0.5
        imagen = pagina.render(scale=escala).to_pil()
        buffer = io.BytesIO()
        imagen.save(buffer, format="PNG")
        return buffer.getvalue(), escala
    finally:
        pdf.close()


def _leer_pdf(contenido: bytes, nombre: str, permitir_ocr: bool) -> Documento:
    import pdfplumber

    doc = Documento(ruta=None, nombre=nombre)
    caps = capacidades()
    arranque = time.monotonic()

    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        total = len(pdf.pages)
        if total > MAX_PAGINAS:
            doc.avisos.append(
                f"El documento tiene {total} páginas y solo se leen las "
                f"{MAX_PAGINAS} primeras. Una factura no las necesita."
            )

        for i, pagina in enumerate(pdf.pages[:MAX_PAGINAS]):
            # El corte va entre páginas: ahí se puede parar sin dejar el
            # documento a medio construir.
            if time.monotonic() - arranque > MAX_SEGUNDOS_DOCUMENTO:
                doc.avisos.append(
                    f"Lectura interrumpida en la página {i + 1}: el documento "
                    f"ha superado los {MAX_SEGUNDOS_DOCUMENTO:.0f} s. "
                    "Lo leído hasta aquí sí se ha analizado."
                )
                break

            texto = pagina.extract_text() or ""
            palabras: list[Palabra] = []

            if len(texto.strip()) >= MIN_CARACTERES_CAPA_TEXTO:
                for w in pagina.extract_words(use_text_flow=True):
                    palabras.append(Palabra(
                        texto=w["text"],
                        x0=w["x0"], y0=w["top"], x1=w["x1"], y1=w["bottom"],
                        pagina=i + 1,
                    ))
                origen = Origen.CAPA_TEXTO

            elif permitir_ocr and caps["ocr"] and caps["rasterizado"]:
                png, escala = _rasterizar(io.BytesIO(contenido), i)
                texto, palabras = _ocr_imagen(png, i + 1, escala)
                origen = Origen.OCR if texto.strip() else Origen.VACIO

            else:
                origen = Origen.VACIO
                if not caps["ocr"]:
                    doc.avisos.append(
                        f"Página {i + 1} sin capa de texto y OCR no instalado: "
                        "instala 'rapidocr-onnxruntime' para leer escaneados."
                    )
                elif not caps["rasterizado"]:
                    doc.avisos.append(
                        f"Página {i + 1} sin capa de texto y falta 'pypdfium2' "
                        "para rasterizarla."
                    )
                else:
                    doc.avisos.append(f"Página {i + 1} sin texto legible.")

            doc.paginas.append(Pagina(
                numero=i + 1,
                texto=texto,
                ancho=float(pagina.width),
                alto=float(pagina.height),
                origen=origen,
                palabras=palabras,
            ))

    return doc


def _leer_imagen(contenido: bytes, nombre: str) -> Documento:
    doc = Documento(ruta=None, nombre=nombre)
    if not capacidades()["ocr"]:
        doc.avisos.append(
            "Es una imagen y el OCR no está instalado: "
            "instala 'rapidocr-onnxruntime'."
        )
        doc.paginas.append(Pagina(1, "", 0, 0, Origen.VACIO))
        return doc

    texto, palabras = _ocr_imagen(contenido, 1)
    ancho = max((w.x1 for w in palabras), default=0.0)
    alto = max((w.y1 for w in palabras), default=0.0)
    doc.paginas.append(Pagina(
        numero=1,
        texto=texto,
        ancho=ancho,
        alto=alto,
        origen=Origen.OCR if texto.strip() else Origen.VACIO,
        palabras=palabras,
    ))
    return doc


# ---------------------------------------------------------------------------
# Entrada pública
# ---------------------------------------------------------------------------

def leer_bytes(contenido: bytes, nombre: str, permitir_ocr: bool = True) -> Documento:
    extension = Path(nombre).suffix.lower()

    if extension in EXTENSIONES_PDF:
        if not capacidades()["pdf_texto"]:
            raise LecturaNoSoportada(
                "Falta 'pdfplumber' para leer PDF. Instálalo con: pip install pdfplumber"
            )
        return _leer_pdf(contenido, nombre, permitir_ocr)

    if extension in EXTENSIONES_IMAGEN:
        return _leer_imagen(contenido, nombre)

    raise LecturaNoSoportada(
        f"Extensión no soportada: '{extension or nombre}'. "
        f"Admitidas: {', '.join(sorted(EXTENSIONES_SOPORTADAS))}"
    )


def leer(ruta: str | Path, permitir_ocr: bool = True) -> Documento:
    ruta = Path(ruta)
    if not ruta.is_file():
        raise LecturaNoSoportada(f"No existe el fichero: {ruta}")
    doc = leer_bytes(ruta.read_bytes(), ruta.name, permitir_ocr)
    doc.ruta = ruta
    return doc

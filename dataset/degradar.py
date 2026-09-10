"""Degradador de facturas: de PDF limpio a escaneado y a foto de móvil.

    python -m dataset.degradar                       las 23, ambos perfiles, nivel medio
    python -m dataset.degradar --perfil foto --nivel duro
    python -m dataset.degradar --solo f05            solo una factura

Las 23 facturas del banco externo llevan capa de texto y no ejercen el OCR.
Esto fabrica sus versiones sucias, para medirlo.

**Determinista, byte a byte.** La semilla sale del nombre de la factura, no
del reloj: cada una tiene su degradación propia y estable, y añadir facturas
no cambia las que ya había. Si el OCR falla en una, se sabe que es el OCR y
no que esa vez le tocó una rotación peor. El nivel no cambia la semilla: la
misma factura tuerce hacia el mismo lado y oscurece el mismo borde en los
tres niveles, solo cambia cuánto.

Rasteriza con pypdfium2, que el proyecto ya usa para el OCR y no necesita
Poppler. No mejora nada ni endereza nada: ensucia.

**El mismo píxel exige las mismas librerías.** Pillow ha cambiado sus
algoritmos de remuestreo entre versiones y NumPy no garantiza que sus
distribuciones den la misma serie de una versión a otra. Las versiones van
fijadas en `dataset/requirements-degradar.txt` y quedan grabadas en
`degradacion.json`; si las del entorno no coinciden, se avisa antes de
generar nada.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

RAIZ = Path(__file__).resolve().parent
ENTRADA = RAIZ / "externo" / "limpio"
SALIDA = RAIZ / "externo"

# «medio» son los rangos de la especificación; «suave» la mitad y «duro» el
# doble de cada magnitud. Lo que no es una magnitud de daño —resolución,
# tamaño final, calidad JPEG— no se escala.
NIVELES = {"suave": 0.5, "medio": 1.0, "duro": 2.0}
BORDES = ("arriba", "abajo", "izquierda", "derecha")
ESQUINAS = ("arriba-izquierda", "arriba-derecha", "abajo-izquierda", "abajo-derecha")


class Tirada:
    """Números aleatorios de una factura y un perfil, siempre los mismos.

    Se sortea un uniforme en [0, 1) y luego se lleva al rango escalado por el
    nivel: así el sorteo no depende del nivel y la factura conserva su
    carácter en los tres.
    """

    def __init__(self, base: str, perfil: str):
        self.semilla = int.from_bytes(
            hashlib.sha256(f"{base}|{perfil}".encode()).digest()[:8], "big")
        self.rng = np.random.Generator(np.random.PCG64(self.semilla))

    def uniforme(self) -> float:
        return float(self.rng.random())

    def rango(self, a: float, b: float, k: float = 1.0) -> float:
        return (a + (b - a) * self.uniforme()) * k

    def signo(self) -> int:
        return 1 if self.uniforme() < 0.5 else -1

    def entero(self, a: int, b: int) -> int:
        return a + int(self.uniforme() * (b - a + 1))

    def uno_de(self, opciones: tuple[str, ...]) -> str:
        return opciones[int(self.uniforme() * len(opciones))]


def _base(pdf: Path) -> str:
    return pdf.stem.removesuffix("_limpio")


def _rasterizar(pdf: Path, ppp: int) -> Image.Image:
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument(str(pdf))
    try:
        return documento[0].render(scale=ppp / 72).to_pil().convert("RGB")
    finally:
        documento.close()


def _ruido(img: Image.Image, sigma: float, t: Tirada, color: bool) -> Image.Image:
    a = np.asarray(img, dtype=np.float32)
    forma = a.shape if color or a.ndim == 2 else a.shape[:2] + (1,)
    a = a + t.rng.normal(0.0, sigma, forma).astype(np.float32)
    return Image.fromarray(np.clip(np.rint(a), 0, 255).astype(np.uint8), img.mode)


def _rampa(alto: int, ancho: int, borde: str) -> np.ndarray:
    """0 en el borde elegido, 1 en el opuesto."""
    if borde in ("arriba", "abajo"):
        r = np.linspace(0.0, 1.0, alto, dtype=np.float32)[:, None].repeat(ancho, 1)
        return r if borde == "arriba" else r[::-1]
    r = np.linspace(0.0, 1.0, ancho, dtype=np.float32)[None, :].repeat(alto, 0)
    return r if borde == "izquierda" else r[:, ::-1]


def _multiplicar(img: Image.Image, factor: np.ndarray) -> Image.Image:
    a = np.asarray(img, dtype=np.float32)
    if a.ndim == 3:
        factor = factor[:, :, None]
    return Image.fromarray(np.clip(np.rint(a * factor), 0, 255).astype(np.uint8), img.mode)


def _coeficientes(destino: list[tuple[float, float]],
                  origen: list[tuple[float, float]]) -> list[float]:
    """Los ocho coeficientes que PIL pide para una perspectiva: llevan cada
    punto de la imagen de salida al de la entrada."""
    filas, lado = [], []
    for (x, y), (u, v) in zip(destino, origen):
        filas.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        filas.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        lado += [u, v]
    return np.linalg.solve(np.array(filas, dtype=np.float64),
                           np.array(lado, dtype=np.float64)).tolist()


# ---------------------------------------------------------------------------
# Perfil «escaneado»: escáner plano de oficina
# ---------------------------------------------------------------------------

def escaneado(pdf: Path, destino: Path, nivel: str) -> dict[str, Any]:
    k = NIVELES[nivel]
    t = Tirada(_base(pdf), "escaneado")
    p = {
        "ppp": 300,
        "rotacion_grados": round(t.signo() * t.rango(0.4, 2.5, k), 3),
        "relleno_gris": t.entero(248, 252),
        "contraste": round(1 - t.rango(0.03, 0.10, k), 4),
        "brillo": round(1 + t.rango(0.00, 0.06, k), 4),
        "vineteado": round(t.rango(0.03, 0.08, k), 4),
        "vineteado_borde": t.uno_de(BORDES),
        "desenfoque_px": round(t.rango(0.3, 0.7, k), 3),
        "ruido_sigma": round(t.rango(3.0, 8.0, k), 3),
    }

    img = _rasterizar(pdf, p["ppp"]).convert("L")
    # Relleno blanco roto: un borde negro sería una referencia que un
    # escaneo de verdad no trae.
    img = img.rotate(p["rotacion_grados"], resample=Image.BICUBIC, expand=True,
                     fillcolor=p["relleno_gris"])
    img = ImageEnhance.Contrast(img).enhance(p["contraste"])
    img = ImageEnhance.Brightness(img).enhance(p["brillo"])
    # La tapa del escáner no cierra igual por todos lados: se oscurece un
    # borde, el que diga la semilla, hasta la mitad de la página.
    rampa = _rampa(img.height, img.width, p["vineteado_borde"])
    img = _multiplicar(img, 1 - p["vineteado"] * np.clip(1 - 2 * rampa, 0, 1) ** 2)
    img = img.filter(ImageFilter.GaussianBlur(p["desenfoque_px"]))
    img = _ruido(img, p["ruido_sigma"], t, color=False)

    img.save(destino, "PNG", optimize=False)
    return {"semilla": t.semilla, "perfil": "escaneado", "nivel": nivel, **p,
            "orden": ["rasterizado", "gris", "rotacion", "contraste", "brillo",
                      "vineteado", "desenfoque", "ruido"]}


# ---------------------------------------------------------------------------
# Perfil «foto»: móvil sobre una mesa
# ---------------------------------------------------------------------------

def foto(pdf: Path, destino: Path, nivel: str) -> dict[str, Any]:
    k = NIVELES[nivel]
    t = Tirada(_base(pdf), "foto")
    p: dict[str, Any] = {
        "ppp": 200,
        "lado_largo_px": t.entero(1600, 2400),
        "margen_mesa": round(t.rango(0.06, 0.12), 4),
        "fondo_rgb": [t.entero(188, 206)] * 3,
        # Cada esquina se desplaza por su cuenta: la perspectiva de verdad
        # nunca es simétrica.
        "perspectiva": [[round(t.signo() * t.rango(0.01, 0.04, k), 4),
                         round(t.signo() * t.rango(0.01, 0.04, k), 4)] for _ in range(4)],
        "rotacion_grados": round(t.signo() * t.rango(1.0, 4.0, k), 3),
        "iluminacion": round(t.rango(0.08, 0.18, k), 4),
        "iluminacion_angulo": round(t.rango(0.0, 360.0), 2),
        "sombra": round(t.rango(0.10, 0.25, k), 4),
        "sombra_esquina": t.uno_de(ESQUINAS),
        "sombra_radio": round(t.rango(0.30, 0.50), 4),
        "tinte_calido": round(t.rango(0.03, 0.07, k), 4),
        "desenfoque_px": round(t.rango(0.5, 1.2, k), 3),
        "ruido_sigma": round(t.rango(2.0, 6.0, k), 3),
        "calidad_jpeg": t.entero(70, 80),
    }
    fondo = tuple(p["fondo_rgb"])

    doc = _rasterizar(pdf, p["ppp"])
    # La factura no llena el encuadre: se deja mesa alrededor, que obliga a
    # encontrar el papel antes de leerlo.
    mx, my = int(doc.width * p["margen_mesa"]), int(doc.height * p["margen_mesa"])
    lienzo = Image.new("RGB", (doc.width + 2 * mx, doc.height + 2 * my), fondo)
    lienzo.paste(doc, (mx, my))

    esquinas = [(mx, my), (mx + doc.width, my),
                (mx + doc.width, my + doc.height), (mx, my + doc.height)]
    movidas = [(x + dx * doc.width, y + dy * doc.width)
               for (x, y), (dx, dy) in zip(esquinas, p["perspectiva"])]
    lienzo = lienzo.transform(lienzo.size, Image.PERSPECTIVE,
                              _coeficientes(movidas, esquinas),
                              resample=Image.BICUBIC, fillcolor=fondo)
    lienzo = lienzo.rotate(p["rotacion_grados"], resample=Image.BICUBIC,
                           expand=False, fillcolor=fondo)

    escala = p["lado_largo_px"] / max(lienzo.size)
    img = lienzo.resize((round(lienzo.width * escala), round(lienzo.height * escala)),
                        Image.LANCZOS)
    alto, ancho = img.height, img.width

    # Luz de ventana: un lado más oscuro que el otro, en la dirección sorteada.
    ang = np.deg2rad(p["iluminacion_angulo"])
    yy, xx = np.mgrid[0:alto, 0:ancho].astype(np.float32)
    proy = xx * np.cos(ang) + yy * np.sin(ang)
    proy = (proy - proy.min()) / max(float(proy.max() - proy.min()), 1.0)
    factor = 1 - p["iluminacion"] * proy

    # Sombra del móvil o de la mano sobre una esquina, con el borde difuso.
    cx = 0.0 if "izquierda" in p["sombra_esquina"] else float(ancho)
    cy = 0.0 if "arriba" in p["sombra_esquina"] else float(alto)
    radio = p["sombra_radio"] * float(np.hypot(ancho, alto))
    d = np.clip(1 - np.hypot(xx - cx, yy - cy) / radio, 0, 1)
    factor *= 1 - p["sombra"] * (d * d * (3 - 2 * d))
    img = _multiplicar(img, factor)

    # Balance de blancos de móvil: tira a amarillo.
    w = p["tinte_calido"]
    a = np.asarray(img, dtype=np.float32) * np.array([1 + 0.5 * w, 1 + 0.2 * w, 1 - w],
                                                      dtype=np.float32)
    img = Image.fromarray(np.clip(np.rint(a), 0, 255).astype(np.uint8), "RGB")

    img = img.filter(ImageFilter.GaussianBlur(p["desenfoque_px"]))
    img = _ruido(img, p["ruido_sigma"], t, color=True)
    img.save(destino, "JPEG", quality=p["calidad_jpeg"], optimize=False)
    return {"semilla": t.semilla, "perfil": "foto", "nivel": nivel, **p,
            "orden": ["rasterizado", "mesa", "perspectiva", "rotacion", "redimensionado",
                      "iluminacion", "sombra", "tinte", "desenfoque", "ruido", "jpeg"]}


PERFILES = {"escaneado": (escaneado, "png"), "foto": (foto, "jpg")}


def _entorno() -> dict[str, str]:
    """Lo que decide el píxel: las tres librerías que lo pintan."""
    return {nombre: version(nombre) for nombre in ("numpy", "pillow", "pypdfium2")}


# ---------------------------------------------------------------------------
# Línea de comandos
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):  # pragma: no cover
        pass

    parser = argparse.ArgumentParser(
        prog="python -m dataset.degradar",
        description="Genera versiones escaneadas y fotografiadas de las facturas limpias.")
    parser.add_argument("--entrada", type=Path, default=ENTRADA,
                        help=f"carpeta de PDF limpios (por defecto {ENTRADA.relative_to(RAIZ.parent)})")
    parser.add_argument("--salida", type=Path, default=SALIDA,
                        help=f"carpeta del banco (por defecto {SALIDA.relative_to(RAIZ.parent)})")
    parser.add_argument("--perfil", choices=("escaneado", "foto", "ambos"), default="ambos")
    parser.add_argument("--nivel", choices=tuple(NIVELES), default="medio")
    parser.add_argument("--solo", metavar="FACTURA",
                        help="procesar solo las que empiecen así, p. ej. f05")
    args = parser.parse_args(argv)

    pdfs = sorted(args.entrada.glob("*.pdf"))
    if args.solo:
        pdfs = [f for f in pdfs if f.name.startswith(args.solo)]
    if not pdfs:
        print(f"No hay PDF en {args.entrada}" + (f" que empiecen por {args.solo}" if args.solo else ""),
              file=sys.stderr)
        return 1

    perfiles = ("escaneado", "foto") if args.perfil == "ambos" else (args.perfil,)
    # El nivel medio va a escaneado/ y foto/; los otros, a su propia carpeta,
    # para no pisar el banco de referencia.
    sufijo = "" if args.nivel == "medio" else f"_{args.nivel}"

    registro_ruta = args.salida / "degradacion.json"
    registro: dict[str, Any] = {}
    if registro_ruta.is_file():
        registro = json.loads(registro_ruta.read_text(encoding="utf-8"))

    entorno = _entorno()
    anterior = registro.get("_entorno")
    if anterior and anterior != entorno:
        print("  ! Las librerías no son las del registro: las imágenes pueden no "
              "salir idénticas.\n"
              f"    registro {anterior}\n    ahora    {entorno}\n"
              "    pip install -r dataset/requirements-degradar.txt", file=sys.stderr)
    registro["_entorno"] = entorno

    hechos = 0
    for perfil in perfiles:
        funcion, extension = PERFILES[perfil]
        carpeta = args.salida / f"{perfil}{sufijo}"
        carpeta.mkdir(parents=True, exist_ok=True)
        for pdf in pdfs:
            destino = carpeta / f"{_base(pdf)}_{perfil}.{extension}"
            parametros = funcion(pdf, destino, args.nivel)
            registro[destino.relative_to(args.salida).as_posix()] = parametros
            hechos += 1
            print(f"  {destino.relative_to(args.salida).as_posix():<52} "
                  f"{destino.stat().st_size / 1e6:5.1f} MB")

    # Sin fecha dentro y con las claves ordenadas: el registro también es
    # idéntico entre ejecuciones.
    registro_ruta.write_text(
        json.dumps(dict(sorted(registro.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"\n{hechos} ficheros · nivel {args.nivel} · registro en "
          f"{registro_ruta.relative_to(args.salida.parent).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""De texto de factura a campos estructurados. Reglas, no modelos.

La estrategia es la que usaría una persona: buscar la etiqueta ("Nº factura",
"Invoice No", "Rechnungsnummer") y leer lo que hay a su derecha o justo debajo.
Cuando hay posiciones disponibles se usa la geometría; cuando no, se cae a
expresiones regulares sobre el texto plano.

Cada campo sale con su confianza y con la pista que lo produjo, para que la
interfaz pueda enseñar *por qué* ha decidido eso y el usuario corrija con
conocimiento de causa.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Optional

from backend.nucleo.lectura import Documento, Palabra
from backend.nucleo.paises import PAISES
from backend.nucleo.validador import validar_id_fiscal

# --------------------------------------------------------------------------
# Utilidades de texto
# --------------------------------------------------------------------------

def _sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def _norm(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios colapsados: para comparar etiquetas."""
    return re.sub(r"\s+", " ", _sin_tildes(texto).lower()).strip()


def _a_numero(texto: str) -> Optional[float]:
    """Convierte un importe escrito de cualquier forma a float.

    Aguanta 1.234,56 · 1,234.56 · 1234.56 · 1 234,56 · (1.234,56) negativo
    contable · 1.234,56 € · $1,234.56
    """
    if texto is None:
        return None
    limpio = str(texto).strip()
    negativo = limpio.startswith("(") and limpio.endswith(")")
    limpio = re.sub(r"[^\d,.\-]", "", limpio)
    if not limpio or not re.search(r"\d", limpio):
        return None

    ultima_coma = limpio.rfind(",")
    ultimo_punto = limpio.rfind(".")

    if ultima_coma > -1 and ultimo_punto > -1:
        # El separador decimal es el que aparece más a la derecha.
        if ultima_coma > ultimo_punto:
            limpio = limpio.replace(".", "").replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
    elif ultima_coma > -1:
        decimales = len(limpio) - ultima_coma - 1
        # "1,234" con tres cifras detrás es separador de millares.
        limpio = limpio.replace(",", "" if decimales == 3 else ".")
    elif ultimo_punto > -1:
        decimales = len(limpio) - ultimo_punto - 1
        if decimales == 3 and limpio.count(".") >= 1 and len(limpio.replace(".", "")) > 3:
            limpio = limpio.replace(".", "")

    try:
        valor = float(limpio)
    except ValueError:
        return None
    return -valor if negativo else valor


def _a_fecha(texto: str, pais: str = "ES") -> Optional[date]:
    if not texto:
        return None
    bruto = str(texto).strip()

    formatos = list(PAISES[pais].fecha_formatos) if pais in PAISES else []
    formatos += ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d",
                 "%m/%d/%Y", "%d/%m/%y", "%m/%d/%y", "%d %b %Y", "%d %B %Y"]

    candidato = re.search(
        r"\d{1,4}[\s./-]\d{1,2}[\s./-]\d{2,4}|\d{1,2}\s+\w+\s+\d{4}", bruto
    )
    if candidato:
        bruto = candidato.group(0)

    for formato in dict.fromkeys(formatos):
        try:
            return datetime.strptime(bruto, formato).date()
        except ValueError:
            continue

    _MESES = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12,
        "januar": 1, "februar": 2, "marz": 3, "april": 4, "mai": 5, "juni": 6,
        "juli": 7, "august": 8, "september": 9, "oktober": 10,
        "november": 11, "dezember": 12,
    }
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", _norm(bruto))
    if m and _norm(m.group(2)) in _MESES:
        return date(int(m.group(3)), _MESES[_norm(m.group(2))], int(m.group(1)))
    return None


# --------------------------------------------------------------------------
# Diccionario de etiquetas
# --------------------------------------------------------------------------

# Se buscan en este orden: la primera que aparezca gana.
ETIQUETAS: dict[str, tuple[str, ...]] = {
    "numero": (
        "numero de factura", "n factura", "nº factura", "no factura", "num factura",
        "factura n", "factura numero", "invoice number", "invoice no", "invoice #",
        "rechnungsnummer", "rechnung nr", "beleg nr",
    ),
    "fecha_emision": (
        "fecha de factura", "fecha factura", "fecha de emision", "fecha emision",
        "fecha", "invoice date", "date of issue", "issue date", "dated",
        "rechnungsdatum", "belegdatum", "datum",
    ),
    "fecha_vencimiento": (
        "fecha de vencimiento", "vencimiento", "fecha limite de pago",
        "due date", "payment due", "date due", "faelligkeitsdatum",
        "zahlbar bis", "falligkeitsdatum",
    ),
    "base_imponible": (
        "base imponible", "subtotal", "suma", "importe neto", "neto",
        "net amount", "net total", "nettobetrag", "zwischensumme", "netto",
    ),
    "total": (
        "total factura", "total a pagar", "importe total", "total",
        "amount due", "grand total", "total due", "balance due",
        "gesamtbetrag", "rechnungsbetrag", "endbetrag", "zu zahlen",
    ),
}

# Etiquetas que identifican a cada parte.
ETIQUETAS_EMISOR = (
    "emisor", "datos del emisor", "vendedor", "proveedor", "expedidor",
    "from", "seller", "supplier", "bill from", "verkaufer", "lieferant",
    "rechnungssteller",
)
ETIQUETAS_RECEPTOR = (
    "receptor", "cliente", "datos del cliente", "facturar a", "destinatario",
    "bill to", "invoice to", "customer", "sold to", "client",
    "kunde", "rechnungsempfanger", "empfanger",
)

# Cabeceras que delatan el comienzo de la tabla de líneas.
CABECERAS_TABLA = {
    "descripcion": ("descripcion", "concepto", "description", "item", "articulo",
                    "bezeichnung", "beschreibung", "artikel", "leistung", "details"),
    "cantidad": ("cantidad", "cant", "uds", "unidades", "qty", "quantity",
                 "menge", "anzahl"),
    "precio_unitario": ("precio", "precio unitario", "p unit", "importe unitario",
                        "unit price", "price", "rate", "einzelpreis", "preis"),
    "importe": ("importe", "total", "subtotal", "amount", "line total",
                "betrag", "gesamt", "summe"),
}

# Cómo se nombra el impuesto en cada sitio; se usa para el desglose.
ETIQUETAS_IMPUESTO = ("iva", "i.v.a", "vat", "sales tax", "tax",
                      "mwst", "ust", "umsatzsteuer", "mehrwertsteuer")
ETIQUETAS_RETENCION = ("retencion", "irpf", "ret", "withholding")

_RE_PORCENTAJE = re.compile(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%")


# --------------------------------------------------------------------------
# Resultado
# --------------------------------------------------------------------------

@dataclass
class Campo:
    valor: Any
    confianza: float
    pista: str

    def a_dict(self) -> dict:
        valor = self.valor
        if isinstance(valor, date):
            valor = valor.isoformat()
        return {"valor": valor, "confianza": self.confianza, "pista": self.pista}


@dataclass
class Extraccion:
    pais: str
    campos: dict[str, Campo] = field(default_factory=dict)
    lineas: list[dict] = field(default_factory=list)
    iva: list[dict] = field(default_factory=list)
    retencion: Optional[dict] = None
    emisor: dict = field(default_factory=dict)
    receptor: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    def _v(self, nombre: str) -> Any:
        campo = self.campos.get(nombre)
        return campo.valor if campo else None

    def a_factura(self) -> dict:
        """El diccionario que espera `validador.validar()`."""
        return {
            "tipo_documento": self._v("tipo_documento") or "factura",
            "pais": self.pais,
            "numero": self._v("numero"),
            "fecha_emision": (
                self._v("fecha_emision").isoformat()
                if isinstance(self._v("fecha_emision"), date) else self._v("fecha_emision")
            ),
            "fecha_vencimiento": (
                self._v("fecha_vencimiento").isoformat()
                if isinstance(self._v("fecha_vencimiento"), date)
                else self._v("fecha_vencimiento")
            ),
            "emisor": self.emisor or None,
            "receptor": self.receptor or None,
            "lineas": self.lineas,
            "base_imponible": self._v("base_imponible"),
            "iva": self.iva,
            "retencion": self.retencion,
            "total": self._v("total"),
        }

    @property
    def confianza(self) -> float:
        """Confianza global: media ponderada de los campos que importan."""
        pesos = {
            "numero": 2.0, "fecha_emision": 2.0, "total": 3.0,
            "base_imponible": 2.0, "fecha_vencimiento": 0.5,
        }
        suma = peso_total = 0.0
        for nombre, peso in pesos.items():
            campo = self.campos.get(nombre)
            suma += (campo.confianza if campo else 0.0) * peso
            peso_total += peso
        if self.emisor.get("nif"):
            suma += 2.0
        peso_total += 2.0
        if self.lineas:
            suma += 2.0
        peso_total += 2.0
        return round(suma / peso_total, 3) if peso_total else 0.0

    def a_dict(self) -> dict:
        return {
            "pais": self.pais,
            "confianza": self.confianza,
            "campos": {k: v.a_dict() for k, v in self.campos.items()},
            "emisor": self.emisor,
            "receptor": self.receptor,
            "lineas": self.lineas,
            "iva": self.iva,
            "retencion": self.retencion,
            "avisos": self.avisos,
        }


# --------------------------------------------------------------------------
# Geometría: agrupar palabras en líneas visuales
# --------------------------------------------------------------------------

@dataclass
class LineaVisual:
    texto: str
    palabras: list[Palabra]
    y: float
    pagina: int


def _agrupar_lineas(palabras: Iterable[Palabra], tolerancia: float = 4.0
                    ) -> list[LineaVisual]:
    """Junta palabras que comparten banda horizontal en una línea de lectura."""
    utiles = [w for w in palabras if w.texto.strip()]
    if not utiles:
        return []

    utiles.sort(key=lambda w: (w.pagina, w.y0, w.x0))
    lineas: list[LineaVisual] = []
    grupo: list[Palabra] = []

    for w in utiles:
        if grupo and (w.pagina != grupo[0].pagina
                      or abs(w.y0 - grupo[0].y0) > tolerancia):
            lineas.append(_cerrar_linea(grupo))
            grupo = []
        grupo.append(w)
    if grupo:
        lineas.append(_cerrar_linea(grupo))
    return lineas


def _cerrar_linea(grupo: list[Palabra]) -> LineaVisual:
    ordenado = sorted(grupo, key=lambda w: w.x0)
    return LineaVisual(
        texto=" ".join(w.texto for w in ordenado),
        palabras=ordenado,
        y=min(w.y0 for w in ordenado),
        pagina=ordenado[0].pagina,
    )


# --------------------------------------------------------------------------
# Búsqueda por etiqueta
# --------------------------------------------------------------------------

def _buscar_etiqueta(lineas: list[LineaVisual], etiquetas: tuple[str, ...]
                     ) -> Optional[tuple[str, str, float]]:
    """Devuelve (valor, etiqueta_encontrada, confianza).

    Primero mira a la derecha de la etiqueta en la misma línea; si ahí no hay
    nada, mira la línea siguiente. La confianza baja cuando el valor está
    debajo en vez de al lado, porque es una lectura más discutible.
    """
    for i, linea in enumerate(lineas):
        plano = _norm(linea.texto)
        for etiqueta in etiquetas:
            pos = plano.find(etiqueta)
            if pos == -1:
                continue
            # Evitar cazar "total" dentro de "subtotal" o "total iva".
            anterior = plano[pos - 1] if pos > 0 else " "
            if anterior.isalnum():
                continue

            resto = linea.texto[_mapear_pos(linea.texto, pos + len(etiqueta)):]
            resto = resto.lstrip(" :. -\t")
            if resto.strip():
                return resto.strip(), etiqueta, 0.95

            if i + 1 < len(lineas) and lineas[i + 1].pagina == linea.pagina:
                siguiente = lineas[i + 1].texto.strip()
                if siguiente:
                    return siguiente, etiqueta, 0.7
    return None


def _mapear_pos(original: str, pos_norm: int) -> int:
    """Traduce una posición del texto normalizado al texto original.

    La normalización quita tildes y colapsa espacios, así que los índices
    se desplazan. Se recorre en paralelo para recuperar el punto exacto.
    """
    i_orig = 0
    i_norm = 0
    anterior_espacio = False
    while i_orig < len(original) and i_norm < pos_norm:
        c = original[i_orig]
        es_espacio = c.isspace()
        if es_espacio:
            if not anterior_espacio:
                i_norm += 1
            anterior_espacio = True
        else:
            base = _sin_tildes(c).lower()
            i_norm += len(base)
            anterior_espacio = False
        i_orig += 1
    return i_orig


# --------------------------------------------------------------------------
# Extracción de cada bloque
# --------------------------------------------------------------------------

def _extraer_identificadores(texto: str, pais: str) -> list[str]:
    """Todos los identificadores fiscales del documento que superan el dígito
    de control. El orden de aparición decide quién es emisor y quién receptor."""
    patron = PAISES[pais].id_fiscal_re
    encontrados: list[str] = []
    candidatos = re.finditer(
        rf"\b(?:{patron}|[A-Z]?\d{{7,8}}[A-Z]?)\b", texto.upper()
    )
    for m in candidatos:
        valor = m.group(0)
        if validar_id_fiscal(valor, pais) and valor not in encontrados:
            encontrados.append(valor)
    return encontrados


def _extraer_partes(lineas: list[LineaVisual], texto: str, pais: str
                    ) -> tuple[dict, dict]:
    """Emisor y receptor.

    Si hay etiquetas explícitas se usan. Si no, se reparte por orden: en una
    factura el emisor va arriba y el receptor debajo, casi sin excepción.
    """
    ids = _extraer_identificadores(texto, pais)
    emisor: dict = {}
    receptor: dict = {}

    def localizar(etiquetas: tuple[str, ...]) -> Optional[Palabra]:
        """La palabra donde arranca el bloque. Se queda con su x, que es lo
        que separa las dos columnas cuando emisor y cliente van en paralelo."""
        # Se prueban ventanas de una, dos y tres palabras, porque hay
        # etiquetas de varias ("Bill to", "Datos del emisor").
        for linea in lineas:
            for i, palabra in enumerate(linea.palabras):
                for ancho in (3, 2, 1):
                    trozo = linea.palabras[i:i + ancho]
                    if len(trozo) < ancho:
                        continue
                    plano = _norm(" ".join(w.texto for w in trozo)).rstrip(":")
                    if any(plano == e or plano.startswith(e) for e in etiquetas):
                        return palabra
        # Sin geometría (texto plano) no hay columnas: basta la línea.
        for linea in lineas:
            plano = _norm(linea.texto)
            if any(e in plano for e in etiquetas):
                return Palabra(linea.texto, 0.0, linea.y, 0.0, linea.y, linea.pagina)
        return None

    ancla_emisor = localizar(ETIQUETAS_EMISOR)
    ancla_receptor = localizar(ETIQUETAS_RECEPTOR)

    # Cada bloque se lee dentro de su franja vertical, para que la columna de
    # al lado no se cuele. El límite es la x de la otra etiqueta.
    anclas = sorted(
        [a for a in (ancla_emisor, ancla_receptor) if a is not None],
        key=lambda w: w.x0,
    )

    def banda(ancla: Optional[Palabra]) -> tuple[float, float]:
        if ancla is None:
            return 0.0, float("inf")
        # El límite es donde arranca la columna siguiente, no el punto medio:
        # una razón social larga puede pasarse de la mitad sin invadir nada.
        derecha = float("inf")
        for otra in anclas:
            if otra.x0 > ancla.x0 + 1:
                derecha = otra.x0 - 4.0
                break
        return ancla.x0 - 6.0, derecha

    def bloque(ancla: Optional[Palabra]) -> dict:
        if ancla is None:
            return {}
        izq, der = banda(ancla)

        crudas: list[str] = []
        for linea in lineas:
            if linea.pagina != ancla.pagina or linea.y <= ancla.y0:
                continue
            if linea.y - ancla.y0 > 40:      # el bloque de una parte es corto
                break
            if linea.palabras:
                trozo = " ".join(
                    w.texto for w in linea.palabras
                    if izq <= (w.x0 + w.x1) / 2 < der
                ).strip()
            else:
                trozo = linea.texto.strip()
            if trozo:
                crudas.append(trozo)

        nifs = _extraer_identificadores("\n".join(crudas), pais)
        nombre = ""
        for candidato in crudas:
            limpio = candidato.strip()
            # La razón social es la primera línea con letras que no sea el
            # propio identificador fiscal.
            if (limpio and re.search(r"[A-Za-zÁ-Úá-ú]{3}", limpio)
                    and not any(n in limpio.upper() for n in nifs)):
                nombre = limpio
                break

        return {"nombre": nombre, "nif": nifs[0] if nifs else ""}

    emisor = bloque(ancla_emisor)
    receptor = bloque(ancla_receptor)

    # Relleno por orden de aparición cuando no había etiquetas.
    restantes = [i for i in ids
                 if i not in (emisor.get("nif"), receptor.get("nif"))]
    if not emisor.get("nif") and restantes:
        emisor["nif"] = restantes.pop(0)
    if not receptor.get("nif") and restantes:
        receptor["nif"] = restantes.pop(0)

    # A falta de nombre, la primera línea con letras suele ser la razón social
    # del emisor: es lo que va en la cabecera del papel.
    if emisor and not emisor.get("nombre"):
        for linea in lineas[:6]:
            limpio = linea.texto.strip()
            if len(limpio) > 3 and re.search(r"[A-Za-zÁ-Úá-ú]", limpio):
                emisor["nombre"] = limpio
                break

    return {k: v for k, v in emisor.items() if v}, {k: v for k, v in receptor.items() if v}


def _localizar_tabla(lineas: list[LineaVisual]) -> Optional[tuple[int, dict[str, float]]]:
    """Encuentra la cabecera de la tabla y la posición x de cada columna."""
    for i, linea in enumerate(lineas):
        columnas: dict[str, float] = {}
        for palabra in linea.palabras:
            plano = _norm(palabra.texto)
            for columna, sinonimos in CABECERAS_TABLA.items():
                if columna in columnas:
                    continue
                if any(plano == s or plano.startswith(s) for s in sinonimos):
                    columnas[columna] = (palabra.x0 + palabra.x1) / 2
        # Con descripción y un importe ya es reconocible como tabla.
        if "descripcion" in columnas and "importe" in columnas:
            return i, columnas
    return None


def _extraer_lineas(lineas: list[LineaVisual]) -> tuple[list[dict], list[str]]:
    avisos: list[str] = []
    localizada = _localizar_tabla(lineas)
    if not localizada:
        return [], ["No se ha reconocido la tabla de líneas de detalle."]

    inicio, columnas = localizada
    orden = sorted(columnas.items(), key=lambda kv: kv[1])
    limites: list[tuple[str, float, float]] = []
    for j, (nombre, centro) in enumerate(orden):
        izq = 0.0 if j == 0 else (orden[j - 1][1] + centro) / 2
        der = float("inf") if j == len(orden) - 1 else (orden[j + 1][1] + centro) / 2
        limites.append((nombre, izq, der))

    detalle: list[dict] = []
    for linea in lineas[inicio + 1:]:
        plano = _norm(linea.texto)
        # La tabla termina donde empiezan los totales.
        if any(plano.startswith(e) for e in
               ETIQUETAS["base_imponible"] + ETIQUETAS["total"] + ETIQUETAS_IMPUESTO):
            break

        celdas: dict[str, list[str]] = {n: [] for n, _, _ in limites}
        for palabra in linea.palabras:
            centro = (palabra.x0 + palabra.x1) / 2
            for nombre, izq, der in limites:
                if izq <= centro < der:
                    celdas[nombre].append(palabra.texto)
                    break

        descripcion = " ".join(celdas.get("descripcion", [])).strip()
        importe = _a_numero(" ".join(celdas.get("importe", [])))
        if not descripcion or importe is None:
            continue

        cantidad = _a_numero(" ".join(celdas.get("cantidad", [])))
        precio = _a_numero(" ".join(celdas.get("precio_unitario", [])))
        if cantidad is None and precio is None:
            cantidad, precio = 1.0, importe
        elif cantidad is None and precio:
            cantidad = round(importe / precio, 4) if precio else 1.0
        elif precio is None and cantidad:
            precio = round(importe / cantidad, 4) if cantidad else importe

        detalle.append({
            "descripcion": descripcion,
            "cantidad": cantidad,
            "precio_unitario": precio,
            "importe": importe,
        })

    if not detalle:
        avisos.append("Se ha localizado la cabecera de la tabla pero ninguna línea legible.")
    return detalle, avisos


def _extraer_impuestos(lineas: list[LineaVisual], base: Optional[float]
                       ) -> tuple[list[dict], Optional[dict]]:
    """Desglose de impuesto y retención, tramo a tramo."""
    tramos: list[dict] = []
    retencion: Optional[dict] = None

    for linea in lineas:
        plano = _norm(linea.texto)
        es_impuesto = any(re.search(rf"\b{re.escape(e)}\b", plano)
                          for e in ETIQUETAS_IMPUESTO)
        es_retencion = any(re.search(rf"\b{re.escape(e)}\b", plano)
                           for e in ETIQUETAS_RETENCION)
        if not (es_impuesto or es_retencion):
            continue

        pct_m = _RE_PORCENTAJE.search(linea.texto)
        if not pct_m:
            continue
        porcentaje = _a_numero(pct_m.group(1))

        # El importe del tramo es el último número de la línea que no sea
        # el propio porcentaje.
        cola = linea.texto[pct_m.end():]
        numeros = [_a_numero(n) for n in
                   re.findall(r"-?[\d.,]+", cola) if _a_numero(n) is not None]
        cuota = numeros[-1] if numeros else None
        base_tramo = numeros[0] if len(numeros) > 1 else base

        if cuota is None or porcentaje is None:
            continue

        if es_retencion:
            retencion = {
                "porcentaje": porcentaje,
                "base_imponible": base_tramo if base_tramo is not None else 0.0,
                "cuota": abs(cuota),
            }
        else:
            tramos.append({
                "porcentaje": porcentaje,
                "base_imponible": base_tramo if base_tramo is not None else 0.0,
                "cuota": cuota,
            })

    return tramos, retencion


def _detectar_tipo_documento(texto: str) -> tuple[str, float]:
    cabecera = _norm(texto[:600])
    tipos = {
        "albaran": ("albaran", "delivery note", "lieferschein", "packing slip"),
        "presupuesto": ("presupuesto", "quotation", "quote", "angebot"),
        "pedido": ("pedido", "purchase order", "bestellung"),
        "proforma": ("proforma", "pro forma"),
        "recibo": ("recibo", "receipt", "quittung"),
        "factura": ("factura", "invoice", "rechnung"),
    }
    for tipo, pistas in tipos.items():
        for pista in pistas:
            if pista in cabecera:
                return tipo, 0.9
    return "factura", 0.3


def _detectar_pais(texto: str) -> str:
    """Deduce el país por identificador fiscal, moneda y vocabulario."""
    plano = _norm(texto)
    puntos = {c: 0 for c in PAISES}

    for codigo in PAISES:
        if _extraer_identificadores(texto, codigo):
            puntos[codigo] += 3

    if "£" in texto:
        puntos["UK"] += 3
    if "$" in texto:
        puntos["US"] += 3
    if "€" in texto:
        puntos["ES"] += 1
        puntos["DE"] += 1

    for codigo, palabras in {
        "ES": ("factura", "iva", "base imponible", "irpf", "nif", "cif"),
        "UK": ("invoice", "vat", "vat reg", "net amount"),
        "US": ("invoice", "sales tax", "ein", "amount due"),
        "DE": ("rechnung", "mwst", "umsatzsteuer", "netto", "gesamtbetrag"),
    }.items():
        puntos[codigo] += sum(2 for p in palabras if p in plano)

    return max(puntos, key=lambda c: puntos[c]) if any(puntos.values()) else "ES"


# --------------------------------------------------------------------------
# Entrada pública
# --------------------------------------------------------------------------

def extraer(documento: Documento, pais: Optional[str] = None) -> Extraccion:
    texto = documento.texto
    codigo = (pais or _detectar_pais(texto)).upper()
    if codigo not in PAISES:
        codigo = "ES"

    palabras = documento.palabras
    lineas = _agrupar_lineas(palabras) if palabras else [
        LineaVisual(texto=l, palabras=[], y=float(i), pagina=1)
        for i, l in enumerate(texto.splitlines()) if l.strip()
    ]

    ex = Extraccion(pais=codigo)
    ex.avisos.extend(documento.avisos)

    tipo, conf_tipo = _detectar_tipo_documento(texto)
    ex.campos["tipo_documento"] = Campo(tipo, conf_tipo, "cabecera del documento")

    for nombre in ("numero", "fecha_emision", "fecha_vencimiento",
                   "base_imponible", "total"):
        hallado = _buscar_etiqueta(lineas, ETIQUETAS[nombre])
        if not hallado:
            continue
        bruto, etiqueta, confianza = hallado

        if nombre.startswith("fecha"):
            valor = _a_fecha(bruto, codigo)
        elif nombre in ("base_imponible", "total"):
            valor = _a_numero(bruto)
        else:
            m = re.search(r"[\w/\-]+", bruto)
            valor = m.group(0) if m else None

        if valor is not None:
            ex.campos[nombre] = Campo(valor, confianza, f"etiqueta «{etiqueta}»")

    ex.emisor, ex.receptor = _extraer_partes(lineas, texto, codigo)
    ex.lineas, avisos_tabla = _extraer_lineas(lineas)
    ex.avisos.extend(avisos_tabla)

    base = ex.campos["base_imponible"].valor if "base_imponible" in ex.campos else None
    if base is None and ex.lineas:
        base = round(sum(l["importe"] for l in ex.lineas), 2)
        ex.campos["base_imponible"] = Campo(base, 0.6, "suma de las líneas")

    ex.iva, ex.retencion = _extraer_impuestos(lineas, base)

    # Último recurso para el total: base + impuestos - retención.
    if "total" not in ex.campos and base is not None and ex.iva:
        cuotas = sum(t["cuota"] for t in ex.iva)
        ret = ex.retencion["cuota"] if ex.retencion else 0.0
        ex.campos["total"] = Campo(
            round(base + cuotas - ret, 2), 0.5, "calculado desde base e impuestos"
        )

    return ex

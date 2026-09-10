"""De texto de factura a campos estructurados. Reglas, no modelos.

La estrategia es la que usaría una persona: buscar la etiqueta ("Nº factura",
"Invoice No", "Rechnungsnummer") y leer lo que hay a su derecha o justo debajo.
Cuando hay posiciones disponibles se usa la geometría; cuando no, se cae a
expresiones regulares sobre el texto plano.

Tres decisiones que salen de haberlo medido contra quince maquetaciones
distintas, no de la teoría:

- **El emisor se ancla a su NIF, no a la posición.** La primera línea del
  papel suele ser el título. Se localiza el NIF que no está bajo «Para:» o
  «Cliente» y se sube hasta la razón social.
- **Los totales se leen como conceptos, no como un orden fijo.** IVA a varios
  tipos, IRPF intercalado entre ellos, recargo de equivalencia, suplidos,
  descuento: cada renglón dice qué es y el importe va detrás.
- **Una cuota cero es un dato, no un hueco.** «IVA (EXENTO) 0,00 €» es una
  cuota legítima; confundirla con «no se ha podido leer» invalida el veredicto.

Cada campo sale con su confianza y con la pista que lo produjo, para que la
interfaz pueda enseñar *por qué* ha decidido eso.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Iterable, Optional

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


def _norm_etiqueta(texto: str) -> str:
    """Como `_norm`, y además unifica las formas de escribir «número»:
    Nº, N.º, N. º, N°."""
    return re.sub(r"\bn\s*\.?\s*[º°]", "nº", _norm(texto))


def _a_numero(texto: str) -> Optional[float]:
    """Convierte un importe escrito de cualquier forma a float.

    Aguanta 1.234,56 · 1,234.56 · 1234.56 · 1 234,56 · (1.234,56) negativo
    contable · 1.234,56 € · $1,234.56 · −649,00
    """
    if texto is None:
        return None
    limpio = str(texto).strip().replace("−", "-")
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


def _normalizar_cifras(texto: str) -> str:
    """Recose cifras que la extracción ha partido con espacios.

    Solo lo que no admite dos lecturas: el año de una fecha («31/07/2 026»),
    el tipo pegado al porcentaje («IVA2 1%»), el espacio antes del decimal
    («640 ,80») y un NIF partido cuando la unión supera el dígito de control
    («B994589 03»). Una cifra suelta delante de un importe —«1 60,00»— puede
    ser una cantidad y un precio, así que eso no se toca aquí: lo resuelve la
    geometría al agrupar palabras, que sí sabe si hay hueco entre ellas.
    """
    t = re.sub(
        r"\b(\d{1,2}[/.-]\d{1,2}[/.-])(\d{1,3}) (\d{1,3})\b",
        lambda m: (m.group(1) + m.group(2) + m.group(3)
                   if len(m.group(2) + m.group(3)) == 4 else m.group(0)),
        texto,
    )
    t = re.sub(r"(?<=\d) (?=\d\s*%)", "", t)
    t = re.sub(r"(?<=\d) (?=[.,]\d{2}\b)", "", t)

    def _nif(m: re.Match) -> str:
        unido = m.group(1) + m.group(2)
        return unido if validar_id_fiscal(unido, "ES") else m.group(0)

    return re.sub(r"\b([A-Z]?\d{4,7}) (\d{1,4}[A-Z]?)\b", _nif, t)


# Un importe: con dos decimales siempre, con símbolo de moneda opcional a
# cualquier lado. Los millares van con punto o coma, nunca con espacio: con
# espacio, «-1 649,00» (cantidad −1, precio 649) se leería como −1.649.
_IMPORTE = (
    r"(?<![\d.,])\(?[-−]?\s?[€$£]?\s?(?:\d{1,3}(?:[.,]\d{3})+|\d+)[.,]\d{2}(?!\d)\)?"
    r"(?:\s?(?:€|eur\b|£|\$))?"
)
_RE_IMPORTE = re.compile(_IMPORTE, re.IGNORECASE)
# «(10x24,00€)» dentro de una descripción: cantidad por precio unitario.
_RE_DENTRO = re.compile(r"\((\d+(?:[.,]\d+)?)\s*[x×]\s*(" + _IMPORTE + r")\)",
                        re.IGNORECASE)


# --------------------------------------------------------------------------
# Diccionario de etiquetas
# --------------------------------------------------------------------------

ETIQUETAS: dict[str, tuple[str, ...]] = {
    "numero": (
        "numero de factura", "numero factura", "nº de factura", "nº factura",
        "no de factura", "num factura", "factura nº", "factura numero",
        "invoice number", "invoice no", "invoice no.", "invoice #",
        "rechnungsnummer", "rechnung nr", "rechnung nr.", "beleg nr",
    ),
    "fecha_emision": (
        "fecha de la factura", "fecha de factura", "fecha factura",
        "fecha de emision", "fecha emision", "fecha de expedicion", "fecha",
        "invoice date", "date of issue", "issue date", "dated",
        "rechnungsdatum", "belegdatum", "datum",
    ),
    "fecha_vencimiento": (
        "fecha de vencimiento", "fecha vencimiento", "vencimiento",
        "fecha limite de pago", "due date", "payment due", "date due",
        "faelligkeitsdatum", "falligkeitsdatum", "zahlbar bis",
    ),
}

# Lo que puede seguir a «fecha» sin que sea la de emisión.
_NO_ES_EMISION = ("vencimiento", "de vencimiento", "limite", "de pago")

# Palabras que son etiquetas, no valores: si aparecen donde se esperaba un
# número de factura, es que se ha leído la celda de al lado.
_PALABRAS_ETIQUETA = {
    "fecha", "condiciones", "terminos", "id", "id.", "vencimiento", "cliente",
    "para", "factura", "numero", "nº", "importe", "total", "pago", "cantidad",
    "descripcion", "facturar", "metodo", "forma", "date", "due", "terms",
}

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

# Rótulos del bloque del cliente, por orden de fiabilidad. Los de una palabra
# genérica solo cuentan con dos puntos detrás («Para:», «A:»), para no tomar
# por rótulo el «para» de una frase.
_RECEPTOR_FUERTES = ("facturar a", "facturado a", "bill to", "invoice to",
                     "sold to", "datos del cliente", "rechnungsempfanger")
_RECEPTOR_CON_DOS_PUNTOS = ("para", "a")
_RECEPTOR_SUELTOS = ("cliente", "destinatario", "receptor", "customer",
                     "kunde", "client")

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

# Los conceptos de la zona de totales. El orden importa: ante dos que empiezan
# en el mismo sitio gana el primero de la lista.
_CONCEPTOS: tuple[tuple[str, str], ...] = (
    ("base_neta", r"subtotal menos descuento|base imponible neta|base neta"),
    ("recargo", r"recargo\s*(?:de\s*)?equiv(?:alencia)?\.?|r\.\s?e\.(?=\s*\d)"),
    ("retencion", r"retencion(?:\s+irpf)?|irpf|withholding"),
    ("descuento", r"descuento|dto\.|discount|rabatt"),
    ("suplidos", r"suplidos?"),
    ("impuesto", r"i\.v\.a\.?|iva|vat|mwst\.?|ust\.?|umsatzsteuer|mehrwertsteuer"
                 r"|sales\s+tax|tax"),
    ("base", r"base\s+imponible|subtotal|importe\s+neto|net\s+amount|net\s+total"
             r"|nettobetrag|zwischensumme|netto|suma"),
    ("total", r"total\s+a\s+pagar|coste\s+total|importe\s+total|total\s+factura"
              r"|grand\s+total|total\s+due|amount\s+due|balance\s+due|gesamtbetrag"
              r"|rechnungsbetrag|endbetrag|zu\s+zahlen|total"),
)

# Lo que va entre la etiqueta y el importe: un paréntesis («(EXENTO)»,
# «(VAT)»), el tipo («21%», «5,2 %»), dos puntos.
_COLA_CONCEPTO = re.compile(
    r"\s*(?:\((?P<par>[^)]{1,15})\))?"
    r"\s*(?:(?P<pct>\d{1,2}(?:[.,]\d{1,2})?)\s*%)?"
    r"\s*(?:\((?P<par2>[^)]{1,15})\))?"
    r"\s*:?\s*(?P<imp>" + _IMPORTE + r")(?![\d%])",
    re.IGNORECASE,
)
_SOLO_PORCENTAJE = re.compile(
    r"\s*(?:\((?P<par>[^)]{1,15})\))?\s*(?:(?P<pct>\d{1,2}(?:[.,]\d{1,2})?)\s*%)?"
    r"\s*(?:\((?P<par2>[^)]{1,15})\))?\s*:?\s*$"
)
_MOTIVOS_CERO = {"exento": "exento", "exenta": "exento", "exempt": "exento",
                 "isp": "inversión del sujeto pasivo"}

# Menciones que cambian cómo se lee una factura.
_RE_EXENCION = re.compile(
    r"exent[ao]|exencion|no sujet[ao]|inversion del sujeto pasivo"
    r"|art\.?\s*(?:20|21|22|25|84)\b|zero[- ]rated|exempt|steuerfrei"
    r"|reverse charge|steuerschuldnerschaft"
)
_RE_IVA_INCLUIDO = re.compile(
    r"iva incluido|impuestos incluidos|iva inc\.|prices include vat"
    r"|incl\.? vat|inkl\.? mwst"
)
_RE_SIMPLIFICADA = re.compile(r"factura simplificada|simplified invoice")
_RE_RECTIFICA = re.compile(r"rectifica|credit note|gutschrift")


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
    recargo: list[dict] = field(default_factory=list)
    suplidos: Optional[float] = None
    descuento: Optional[dict] = None
    base_bruta: Optional[float] = None
    menciones: dict = field(default_factory=dict)
    emisor: dict = field(default_factory=dict)
    receptor: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    def _v(self, nombre: str) -> Any:
        campo = self.campos.get(nombre)
        return campo.valor if campo else None

    def a_factura(self) -> dict:
        """El diccionario que espera `validador.validar()`."""
        def iso(v: Any) -> Any:
            return v.isoformat() if isinstance(v, date) else v

        return {
            "tipo_documento": self._v("tipo_documento") or "factura",
            "pais": self.pais,
            "numero": self._v("numero"),
            "fecha_emision": iso(self._v("fecha_emision")),
            "fecha_vencimiento": iso(self._v("fecha_vencimiento")),
            "emisor": self.emisor or None,
            "receptor": self.receptor or None,
            "lineas": self.lineas,
            "base_bruta": self.base_bruta,
            "descuento": self.descuento,
            "base_imponible": self._v("base_imponible"),
            "iva": self.iva,
            "retencion": self.retencion,
            "recargo": self.recargo,
            "suplidos": self.suplidos,
            "total": self._v("total"),
            "exencion": self.menciones.get("exencion"),
            "precios_con_iva": self.menciones.get("precios_con_iva", False),
            "simplificada": self.menciones.get("simplificada", False),
            "rectificativa": self.menciones.get("rectificativa", False),
            "rectifica_a": self.menciones.get("rectifica_a"),
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
            "recargo": self.recargo,
            "suplidos": self.suplidos,
            "descuento": self.descuento,
            "base_bruta": self.base_bruta,
            "menciones": self.menciones,
            "avisos": self.avisos,
        }


# --------------------------------------------------------------------------
# Geometría: palabras -> líneas -> segmentos
# --------------------------------------------------------------------------

# Hueco horizontal a partir del cual dos palabras de la misma línea ya no son
# la misma celda. Un espacio entre palabras son 2-3 puntos; entre columnas,
# quince o más.
HUECO_COLUMNA = 9.0


@dataclass
class LineaVisual:
    texto: str
    palabras: list[Palabra]
    y: float
    pagina: int
    girada: bool = False


@dataclass
class Segmento:
    texto: str
    palabras: list[Palabra]
    x0: float
    x1: float


def _agrupar_lineas(palabras: Iterable[Palabra], tolerancia: float = 4.0
                    ) -> list[LineaVisual]:
    """Junta palabras que comparten banda horizontal en una línea de lectura.

    Los rótulos girados van aparte: cada columna vertical es su propio
    renglón, porque mezclados con el texto horizontal meten una letra suelta
    al principio de cada línea que cruzan.
    """
    utiles = [w for w in palabras if w.texto.strip()]
    if not utiles:
        return []

    rectas = sorted((w for w in utiles if not w.girada),
                    key=lambda w: (w.pagina, w.y0, w.x0))
    lineas: list[LineaVisual] = []
    grupo: list[Palabra] = []
    for w in rectas:
        if grupo and (w.pagina != grupo[0].pagina
                      or abs(w.y0 - grupo[0].y0) > tolerancia):
            lineas.append(_cerrar_linea(grupo))
            grupo = []
        grupo.append(w)
    if grupo:
        lineas.append(_cerrar_linea(grupo))

    giradas: dict[tuple[int, float], list[Palabra]] = {}
    for w in utiles:
        if w.girada:
            giradas.setdefault((w.pagina, w.y0), []).append(w)
    for grupo_girado in giradas.values():
        linea = _cerrar_linea(grupo_girado)
        linea.girada = True
        lineas.append(linea)

    lineas.sort(key=lambda l: (l.pagina, l.y))
    return lineas


def _cerrar_linea(grupo: list[Palabra]) -> LineaVisual:
    ordenado = sorted(grupo, key=lambda w: w.x0)
    # Cifras que la extracción ha cortado sin hueco real entre los trozos:
    # se vuelven a pegar aquí, donde se sabe que no hay espacio.
    cosidas: list[Palabra] = []
    for w in ordenado:
        if cosidas:
            prev = cosidas[-1]
            alto = max(w.y1 - w.y0, 1.0)
            if (w.x0 - prev.x1 < min(1.0, 0.15 * alto)
                    and re.search(r"[\d.,/]$", prev.texto)
                    and re.match(r"[\d.,]", w.texto)):
                cosidas[-1] = Palabra(prev.texto + w.texto, prev.x0, prev.y0,
                                      w.x1, max(prev.y1, w.y1), prev.pagina,
                                      min(prev.confianza, w.confianza), prev.girada)
                continue
        cosidas.append(w)
    return LineaVisual(
        texto=_normalizar_cifras(" ".join(w.texto for w in cosidas)),
        palabras=cosidas,
        y=min(w.y0 for w in cosidas),
        pagina=cosidas[0].pagina,
    )


def _linea_de_texto(texto: str, indice: int) -> LineaVisual:
    """Una línea de texto plano con palabras de geometría ficticia, para que
    todo lo demás funcione igual cuando no hay posiciones."""
    palabras = []
    for m in re.finditer(r"\S+", texto):
        palabras.append(Palabra(m.group(0), m.start() * 5.0, indice * 12.0,
                                m.end() * 5.0, indice * 12.0 + 10, 1))
    return LineaVisual(_normalizar_cifras(texto.strip()), palabras,
                       indice * 12.0, 1)


def _segmentos(linea: LineaVisual) -> list[Segmento]:
    if not linea.palabras:
        return [Segmento(linea.texto, [], 0.0, 1e9)]
    salida: list[Segmento] = []
    actual: list[Palabra] = [linea.palabras[0]]
    for w in linea.palabras[1:]:
        if w.x0 - actual[-1].x1 > HUECO_COLUMNA:
            salida.append(_segmento(actual))
            actual = []
        actual.append(w)
    salida.append(_segmento(actual))
    return salida


def _segmento(palabras: list[Palabra]) -> Segmento:
    return Segmento(
        texto=_normalizar_cifras(" ".join(w.texto for w in palabras)),
        palabras=palabras, x0=palabras[0].x0, x1=palabras[-1].x1,
    )


# --------------------------------------------------------------------------
# Búsqueda por etiqueta
# --------------------------------------------------------------------------

def _ocurrencias(lineas: list[LineaVisual], etiquetas: tuple[str, ...]
                 ) -> Iterable[tuple[int, int, int, str]]:
    """Cada sitio donde aparece una etiqueta: (línea, palabra inicial,
    palabra final exclusiva, etiqueta). Se prueba la ventana más larga
    primero, para que «fecha de vencimiento» gane a «fecha»."""
    buscadas = {_norm_etiqueta(e) for e in etiquetas}
    for k, linea in enumerate(lineas):
        ws = linea.palabras
        i = 0
        while i < len(ws):
            for ancho in range(min(6, len(ws) - i), 0, -1):
                plano = _norm_etiqueta(" ".join(w.texto for w in ws[i:i + ancho]))
                plano = plano.rstrip(":").strip()
                if plano in buscadas:
                    yield k, i, i + ancho, plano
                    i += ancho - 1
                    break
            i += 1


def _valor_junto(lineas: list[LineaVisual], k: int, i: int, j: int,
                 leer: Callable[[str], Any]) -> Optional[tuple[Any, float, str]]:
    """El valor de una etiqueta: a su derecha en la misma línea o, si ahí no
    hay nada que sirva, en la celda de debajo."""
    linea = lineas[k]
    ws = linea.palabras

    if j < len(ws):
        grupo = [ws[j]]
        for w in ws[j + 1:]:
            if w.x0 - grupo[-1].x1 > HUECO_COLUMNA:
                break
            grupo.append(w)
        valor = leer(" ".join(w.texto for w in grupo))
        if valor is not None:
            return valor, 0.95, "a su derecha"

    x0, x1 = ws[i].x0, ws[j - 1].x1
    for kk in range(k + 1, min(k + 4, len(lineas))):
        abajo = lineas[kk]
        if abajo.girada:
            continue
        if abajo.pagina != linea.pagina or abajo.y - linea.y > 24:
            break
        candidatos = [s for s in _segmentos(abajo)
                      if s.x1 >= x0 - 15 and s.x0 <= x1 + 60]
        candidatos.sort(key=lambda s: abs(s.x0 - x0))
        for seg in candidatos:
            valor = leer(seg.texto)
            if valor is not None:
                return valor, 0.8, "debajo"
    return None


def _leer_numero(texto: str) -> Optional[str]:
    t = texto.strip().lstrip(":#º°. ").strip()
    if not t:
        return None
    primero = t.split()[0].strip(",;:")
    if _norm(primero).rstrip(".:") in _PALABRAS_ETIQUETA:
        return None
    primero = primero.lstrip("#")
    if (len(primero) < 3 or not re.search(r"\d", primero)
            or re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", primero)
            or _RE_IMPORTE.fullmatch(primero)):
        return None
    return primero


def _buscar_numero(lineas: list[LineaVisual]) -> Optional[Campo]:
    for k, i, j, etiqueta in _ocurrencias(lineas, ETIQUETAS["numero"]):
        hallado = _valor_junto(lineas, k, i, j, _leer_numero)
        if hallado:
            valor, confianza, donde = hallado
            return Campo(valor, confianza, f"etiqueta «{etiqueta}», {donde}")

    # El número en el propio título: «FACTURA RC-26-0152», o el rótulo
    # vertical «FACTURA #2026/0038». La palabra tiene que abrir su celda, para
    # no tomar el «rectifica la factura 2026-0412» del pie.
    for linea in lineas:
        ws = linea.palabras
        for i, w in enumerate(ws):
            if _norm(w.texto) not in ("factura", "invoice", "rechnung"):
                continue
            if i > 0 and w.x0 - ws[i - 1].x1 <= HUECO_COLUMNA:
                continue
            for siguiente in ws[i + 1:i + 6]:
                valor = _leer_numero(siguiente.texto)
                if valor:
                    return Campo(valor, 0.75, "en el título del documento")
    return None


def _buscar_fecha(lineas: list[LineaVisual], nombre: str, pais: str
                  ) -> Optional[Campo]:
    for k, i, j, etiqueta in _ocurrencias(lineas, ETIQUETAS[nombre]):
        if nombre == "fecha_emision":
            detras = _norm(" ".join(w.texto for w in lineas[k].palabras[j:j + 2]))
            if any(detras.startswith(n) for n in _NO_ES_EMISION):
                continue
        hallado = _valor_junto(lineas, k, i, j, lambda t: _a_fecha(t, pais))
        if hallado:
            valor, confianza, donde = hallado
            return Campo(valor, confianza, f"etiqueta «{etiqueta}», {donde}")
    return None


# --------------------------------------------------------------------------
# Emisor y receptor
# --------------------------------------------------------------------------

_RE_ID_ES = re.compile(
    r"(?<![A-Z0-9])(?:ES)?(?:[XYZ]\d{7}[A-Z]|\d{8}[A-Z]|[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J])"
    r"(?![A-Z0-9])"
)
_RE_ID_UE = re.compile(
    r"(?<![A-Z0-9])(?:FR|DE|IT|PT|NL|BE|GB|IE|AT|PL|SE|DK|FI|LU|CZ|EL|HU|RO|BG"
    r"|HR|SI|SK|LT|LV|EE|CY|MT|CH|NO)[0-9][0-9A-Z]{7,11}(?![A-Z0-9])"
)

_RE_DIRECCION = re.compile(
    r"^(?:c/|c\.|calle|av\.|avda|avenida|pol\.|poligono|plaza|pza\.?|paseo|pº"
    r"|ctra|carretera|camino|rua|muelle|ronda|travesia|glorieta|urb\.|apartado)"
    r"|\b\d{5}\b|,\s*\d|\bkm\b|\bs/n\b"
)
_RE_CONTACTO = re.compile(r"@|www\.|https?:|\b(?:tel|telf|telefono|fax|movil)\b")
_NO_ES_NOMBRE = (
    "factura", "invoice", "rechnung", "fecha", "nº", "numero", "para", "cliente",
    "facturar", "gracias", "qr", "huella", "veri", "condiciones", "terminos",
    "metodo", "forma de pago", "documento de prueba", "subtotal", "total",
    "base imponible", "iva", "irpf", "descripcion", "cantidad", "importe",
    "vencimiento", "id.", "comentarios", "instrucciones", "si tiene", "nif",
    "cif", "transferencia", "recibo", "pagado", "tarjeta", "abono",
)


def _parece_nombre(texto: str) -> bool:
    t = texto.strip()
    n = _norm(t)
    if not re.match(r"[a-z]", n) or len(re.findall(r"[a-z]", n)) < 3:
        return False
    if _RE_DIRECCION.search(n) or _RE_CONTACTO.search(n):
        return False
    if any(n.startswith(p) for p in _NO_ES_NOMBRE):
        return False
    if _RE_IMPORTE.search(t) or len(t.split()) > 7:
        return False
    if re.search(r"\b(?:art|ley|rd)\b", n) or re.search(r"[0-9a-f]{16,}", n):
        return False
    return True


def _limpiar_nombre(texto: str) -> str:
    """«Marta Olmedo Ruiz — Abogada» es Marta Olmedo Ruiz: lo de detrás de la
    raya es el oficio, no la razón social."""
    nombre = re.split(r"\s+[—–]\s+", texto.strip())[0]
    return nombre.strip(" :|·ꞏ,")


def _ids_en(texto: str, pais: str) -> list[re.Match]:
    """Identificadores con forma de tal, pasen o no el dígito de control:
    un NIF mal calculado tiene que salir para poder decir que está mal."""
    mayus = texto.upper()
    if pais == "ES":
        encontrados = list(_RE_ID_ES.finditer(mayus)) + list(_RE_ID_UE.finditer(mayus))
    else:
        patron = re.compile(rf"(?<![A-Z0-9])(?:{PAISES[pais].id_fiscal_re})(?![A-Z0-9])")
        encontrados = list(patron.finditer(mayus)) + list(_RE_ID_UE.finditer(mayus))
    return sorted(encontrados, key=lambda m: m.start())


def _extraer_identificadores(texto: str, pais: str) -> list[str]:
    """Identificadores del documento que superan el dígito de control."""
    patron = PAISES[pais].id_fiscal_re
    encontrados: list[str] = []
    for m in re.finditer(rf"\b(?:{patron}|[A-Z]?\d{{7,8}}[A-Z]?)\b", texto.upper()):
        valor = m.group(0)
        if validar_id_fiscal(valor, pais) and valor not in encontrados:
            encontrados.append(valor)
    return encontrados


def _localizar_receptor(lineas: list[LineaVisual]) -> Optional[tuple[int, int, int]]:
    """El rótulo del bloque del cliente: (línea, palabra inicial, final)."""
    def buscar(aceptar: Callable[[str, list[Palabra], int], bool],
               etiquetas: tuple[str, ...]) -> Optional[tuple[int, int, int]]:
        for k, linea in enumerate(lineas):
            if linea.girada:
                continue
            ws = linea.palabras
            for i in range(len(ws)):
                for ancho in (2, 1):
                    trozo = ws[i:i + ancho]
                    if len(trozo) < ancho:
                        continue
                    crudo = " ".join(w.texto for w in trozo)
                    plano = _norm(crudo).rstrip(":").strip()
                    if plano in etiquetas and aceptar(crudo, ws, i + ancho - 1):
                        return k, i, i + ancho
        return None

    def suelto(crudo: str, ws: list[Palabra], ultima: int) -> bool:
        previa = _norm(ws[ultima - 1].texto) if ultima > 0 else ""
        if previa in ("del", "de", "id.", "id"):
            return False             # «Id. del cliente: UE-015»
        return (crudo.rstrip().endswith(":") or ultima == len(ws) - 1
                or ws[ultima + 1].x0 - ws[ultima].x1 > HUECO_COLUMNA)

    return (
        buscar(lambda c, ws, u: True, _RECEPTOR_FUERTES)
        or buscar(lambda c, ws, u: c.rstrip().endswith(":"), _RECEPTOR_CON_DOS_PUNTOS)
        or buscar(suelto, _RECEPTOR_SUELTOS)
    )


def _bloque_receptor(lineas: list[LineaVisual]
                     ) -> tuple[set[tuple[int, int]], list[str]]:
    """Las celdas que forman el bloque del cliente y su texto, en orden."""
    ancla = _localizar_receptor(lineas)
    if ancla is None:
        return set(), []
    k, i, j = ancla
    linea = lineas[k]
    ws = linea.palabras
    celdas: set[tuple[int, int]] = set()
    textos: list[str] = []

    columna = ws[i].x0
    segs = _segmentos(linea)
    if j < len(ws):
        # El nombre puede ir en la misma línea que el rótulo: «Para: Fulano».
        for n, seg in enumerate(segs):
            resto = [w for w in seg.palabras if w.x0 >= ws[j].x0 - 0.5]
            if not resto:
                continue
            texto = " ".join(w.texto for w in resto)
            if _norm(texto.split()[0]).rstrip(":.") not in _PALABRAS_ETIQUETA:
                columna = resto[0].x0
                textos.append(texto)
                celdas.add((k, n))
            break

    if not textos:
        # Rótulo solo en su renglón: la columna la marca lo que cae debajo,
        # que a veces va sangrado respecto al rótulo.
        for kk in range(k + 1, min(k + 3, len(lineas))):
            abajo = lineas[kk]
            if abajo.girada:
                continue
            if abajo.pagina != linea.pagina or abajo.y - linea.y > 30:
                break
            cerca = [s for s in _segmentos(abajo)
                     if ws[i].x0 - 12 <= s.x0 <= ws[i].x0 + 80]
            if cerca:
                columna = min(cerca, key=lambda s: s.x0).x0
                break

    ultimo_y = linea.y
    for kk in range(k + 1, len(lineas)):
        abajo = lineas[kk]
        if abajo.girada:
            continue
        if abajo.pagina != linea.pagina or abajo.y - linea.y > 110:
            break
        if _localizar_tabla([abajo]):
            break
        suyos = [(n, s) for n, s in enumerate(_segmentos(abajo))
                 if abs(s.x0 - columna) <= 12]
        if suyos:
            for n, s in suyos:
                celdas.add((kk, n))
                textos.append(s.texto)
            ultimo_y = abajo.y
        elif abajo.y - ultimo_y > 30:
            break
    return celdas, textos


def _partes_por_nif(lineas: list[LineaVisual], pais: str) -> tuple[dict, dict]:
    """Emisor y receptor cuando el papel no rotula al emisor, que es lo normal.

    El receptor va bajo su rótulo. El emisor es el NIF que queda fuera de ese
    bloque, y su nombre se busca subiendo desde el NIF por su misma columna,
    saltando dirección, teléfono y correo.
    """
    celdas_r, textos_r = _bloque_receptor(lineas)

    receptor: dict = {}
    for t in textos_r:
        m = _ids_en(t, pais)
        if m and "nif" not in receptor:
            receptor["nif"] = m[0].group(0)
        elif not receptor.get("nombre") and _parece_nombre(t):
            receptor["nombre"] = _limpiar_nombre(t)

    # Todos los identificadores fuera del bloque del cliente.
    candidatos: list[tuple[int, Segmento, re.Match]] = []
    for k, linea in enumerate(lineas):
        if linea.girada:
            continue
        for n, seg in enumerate(_segmentos(linea)):
            if (k, n) in celdas_r:
                continue
            for m in _ids_en(seg.texto, pais):
                candidatos.append((k, seg, m))

    emisor: dict = {}
    if candidatos:
        def rotulado(c: tuple[int, Segmento, re.Match]) -> bool:
            antes = _norm(c[1].texto[:c[2].start()])
            return bool(re.search(
                r"\b(?:n\.?i\.?f|c\.?i\.?f|nie|vat|ust-idnr)\.?:?\s*$", antes))

        k, seg, m = next((c for c in candidatos if rotulado(c)), candidatos[0])
        emisor["nif"] = m.group(0)
        nombre = _nombre_junto_a_nif(lineas, k, seg, m)
        if nombre:
            emisor["nombre"] = nombre

    if not emisor.get("nombre"):
        for k, linea in enumerate(lineas):
            if linea.girada:
                continue
            for n, seg in enumerate(_segmentos(linea)):
                if (k, n) not in celdas_r and _parece_nombre(seg.texto):
                    emisor["nombre"] = _limpiar_nombre(seg.texto)
                    break
            if emisor.get("nombre"):
                break

    return emisor, receptor


def _nombre_junto_a_nif(lineas: list[LineaVisual], k: int, seg: Segmento,
                        m: re.Match) -> Optional[str]:
    # En el pie: «Estudio Lumbre Gráfica S.L. | NIF B99123408 | ...».
    for trozo in re.split(r"\s*[|·ꞏ]\s*", seg.texto):
        if m.group(0) in trozo.upper():
            break
        if _parece_nombre(trozo):
            return _limpiar_nombre(trozo)

    # Si no, subiendo por su columna.
    linea = lineas[k]
    for kk in range(k - 1, -1, -1):
        arriba = lineas[kk]
        if arriba.girada:
            continue
        if arriba.pagina != linea.pagina or linea.y - arriba.y > 130:
            break
        for s in _segmentos(arriba):
            if s.x1 >= seg.x0 - 10 and s.x0 <= seg.x1 + 10 and _parece_nombre(s.texto):
                return _limpiar_nombre(s.texto)
    return None


def _partes_rotuladas(lineas: list[LineaVisual], texto: str, pais: str
                      ) -> tuple[dict, dict]:
    """Emisor y receptor cuando los dos van rotulados, cada uno en su
    columna: «EMISOR · CLIENTE», «FROM · BILL TO»."""
    ids = _extraer_identificadores(texto, pais)

    def localizar(etiquetas: tuple[str, ...]) -> Optional[Palabra]:
        for linea in lineas:
            for i, palabra in enumerate(linea.palabras):
                for ancho in (3, 2, 1):
                    trozo = linea.palabras[i:i + ancho]
                    if len(trozo) < ancho:
                        continue
                    plano = _norm(" ".join(w.texto for w in trozo)).rstrip(":")
                    if plano in etiquetas:
                        return palabra
        return None

    ancla_emisor = localizar(ETIQUETAS_EMISOR)
    ancla_receptor = localizar(ETIQUETAS_RECEPTOR)
    anclas = sorted([a for a in (ancla_emisor, ancla_receptor) if a is not None],
                    key=lambda w: w.x0)

    def banda(ancla: Palabra) -> tuple[float, float]:
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
            if linea.y - ancla.y0 > 40:
                break
            trozo = " ".join(w.texto for w in linea.palabras
                             if izq <= (w.x0 + w.x1) / 2 < der).strip()
            if trozo:
                crudas.append(trozo)
        nifs = _extraer_identificadores("\n".join(crudas), pais)
        nombre = ""
        for candidato in crudas:
            if (re.search(r"[A-Za-zÁ-Úá-ú]{3}", candidato)
                    and not any(n in candidato.upper() for n in nifs)):
                nombre = candidato.strip()
                break
        return {"nombre": nombre, "nif": nifs[0] if nifs else ""}

    emisor = bloque(ancla_emisor)
    receptor = bloque(ancla_receptor)
    restantes = [i for i in ids if i not in (emisor.get("nif"), receptor.get("nif"))]
    if not emisor.get("nif") and restantes:
        emisor["nif"] = restantes.pop(0)
    if not receptor.get("nif") and restantes:
        receptor["nif"] = restantes.pop(0)
    return ({k: v for k, v in emisor.items() if v},
            {k: v for k, v in receptor.items() if v})


def _extraer_partes(lineas: list[LineaVisual], texto: str, pais: str
                    ) -> tuple[dict, dict]:
    """Dos maquetaciones de cabecera, dos lecturas. Si el emisor va rotulado
    («EMISOR», «FROM»), por columnas; si no, anclado a su NIF."""
    for linea in lineas:
        ws = linea.palabras
        for i in range(len(ws)):
            for ancho in (2, 1):
                plano = _norm(" ".join(w.texto for w in ws[i:i + ancho])).rstrip(":")
                if len(ws[i:i + ancho]) == ancho and plano in ETIQUETAS_EMISOR:
                    return _partes_rotuladas(lineas, texto, pais)
    return _partes_por_nif(lineas, pais)


# --------------------------------------------------------------------------
# Tabla de líneas
# --------------------------------------------------------------------------

def _localizar_tabla(lineas: list[LineaVisual]) -> Optional[tuple[int, dict[str, float]]]:
    """Encuentra la cabecera de la tabla y la posición x de cada columna."""
    for i, linea in enumerate(lineas):
        columnas: dict[str, float] = {}
        for palabra in linea.palabras:
            plano = _norm(palabra.texto).rstrip(".:")
            for columna, sinonimos in CABECERAS_TABLA.items():
                if columna in columnas:
                    continue
                if any(plano == s or plano.startswith(s) for s in sinonimos):
                    columnas[columna] = (palabra.x0 + palabra.x1) / 2
                    break
        if "descripcion" in columnas and "importe" in columnas:
            return i, columnas
    return None


def _es_numero_suelto(texto: str) -> bool:
    return bool(re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+|-?\d+(?:[.,]\d{1,3})?", texto))


def _extraer_lineas(lineas: list[LineaVisual]
                    ) -> tuple[list[dict], list[str], Optional[int]]:
    """Las líneas de detalle y el índice de la última, que es donde empieza
    la zona de totales.

    Cada renglón se lee por su contenido y no por columnas fijas: el importe
    es la última cifra con decimales, el precio la anterior, y la cantidad es
    el número suelto más cercano a la columna «Cantidad» o el «(10x24,00€)»
    de la descripción.
    """
    localizada = _localizar_tabla(lineas)
    if not localizada:
        return [], ["No se ha reconocido la tabla de líneas de detalle."], None

    inicio, columnas = localizada
    detalle: list[dict] = []
    ultima = inicio
    for k in range(inicio + 1, len(lineas)):
        linea = lineas[k]
        if linea.girada:
            continue
        if _conceptos_de(linea.texto):
            break

        # El «(10x24,00€)» de la descripción no es un importe de la línea:
        # se aparta, conservando las posiciones, antes de buscar las cifras.
        dentro = _RE_DENTRO.search(linea.texto)
        sin_dentro = linea.texto
        if dentro:
            sin_dentro = (linea.texto[:dentro.start()]
                          + " " * (dentro.end() - dentro.start())
                          + linea.texto[dentro.end():])
        importes = list(_RE_IMPORTE.finditer(sin_dentro))
        if not importes:
            continue
        ultima = k

        antes = linea.texto[:importes[0].start()]
        palabras = antes.split()
        cantidad: Optional[float] = None
        if "cantidad" in columnas and linea.palabras:
            sueltos = [w for w in linea.palabras
                       if _es_numero_suelto(w.texto) and w.texto in palabras]
            if sueltos:
                cerca = min(sueltos, key=lambda w: abs((w.x0 + w.x1) / 2
                                                      - columnas["cantidad"]))
                cantidad = _a_numero(cerca.texto)
                palabras.remove(cerca.texto)

        descripcion = " ".join(palabras).strip()
        importe = _a_numero(importes[-1].group(0))
        precio = _a_numero(importes[-2].group(0)) if len(importes) >= 2 else None

        if dentro and cantidad is None:
            cantidad = _a_numero(dentro.group(1))
            precio = _a_numero(dentro.group(2))

        if not descripcion or importe is None:
            continue
        detalle.append({
            "descripcion": descripcion,
            "cantidad": cantidad,
            "precio_unitario": precio,
            "importe": importe,
        })

    avisos = [] if detalle else [
        "Se ha localizado la cabecera de la tabla pero ninguna línea legible."]
    return detalle, avisos, ultima


# --------------------------------------------------------------------------
# Totales
# --------------------------------------------------------------------------

@dataclass
class _Concepto:
    tipo: str
    porcentaje: Optional[float]
    importe: Optional[float]
    motivo: Optional[str]


def _conceptos_de(texto: str, siguiente: Optional[str] = None) -> list[_Concepto]:
    """Los conceptos de totales de un renglón, con su tipo e importe.

    Un concepto solo cuenta si lleva un importe detrás: así «el descuento del
    10 % sobre el total» de una nota no se toma por el total. Si la etiqueta
    va sola al final del renglón y el importe cae en la línea siguiente, se
    admite esa línea cuando no trae otra cosa que el importe.
    """
    plano = _norm(texto)
    ocupado: list[tuple[int, int]] = []
    salida: list[tuple[int, _Concepto]] = []
    for tipo, patron in _CONCEPTOS:
        for m in re.finditer(rf"(?<![a-z])(?:{patron})(?![a-z])", plano):
            if any(a <= m.start() < b for a, b in ocupado):
                continue
            cola = _COLA_CONCEPTO.match(plano, m.end())
            if cola is not None:
                importe_txt, fin = cola.group("imp"), cola.end()
            else:
                cola = _SOLO_PORCENTAJE.match(plano, m.end())
                if cola is None or not siguiente \
                        or not _RE_IMPORTE.fullmatch(siguiente.strip()):
                    continue
                importe_txt, fin = siguiente.strip(), len(plano)
            motivo = None
            for par in (cola.group("par"), cola.group("par2")):
                if par and par.strip().lower() in _MOTIVOS_CERO:
                    motivo = _MOTIVOS_CERO[par.strip().lower()]
            pct = _a_numero(cola.group("pct")) if cola.group("pct") else None
            ocupado.append((m.start(), fin))
            salida.append((m.start(), _Concepto(tipo, pct, _a_numero(importe_txt), motivo)))
    salida.sort(key=lambda par: par[0])
    return [c for _, c in salida]


@dataclass
class _Totales:
    base: Optional[float] = None
    base_bruta: Optional[float] = None
    descuento: Optional[dict] = None
    iva: list[dict] = field(default_factory=list)
    retencion: Optional[dict] = None
    recargo: list[dict] = field(default_factory=list)
    suplidos: Optional[float] = None
    total: Optional[float] = None


def _deducir_base(cuota: float, pct: Optional[float]) -> Optional[float]:
    if not pct:
        return None
    return round(cuota * 100 / pct, 2)


def _extraer_totales(lineas: list[LineaVisual], desde: int) -> _Totales:
    base = base_neta = total = None
    impuestos: list[_Concepto] = []
    retenciones: list[_Concepto] = []
    recargos: list[_Concepto] = []
    descuento: Optional[_Concepto] = None
    suplidos = 0.0
    hay_suplidos = False

    utiles = [l for l in lineas[desde:] if not l.girada]
    for n, linea in enumerate(utiles):
        siguiente = None
        if (n + 1 < len(utiles) and utiles[n + 1].pagina == linea.pagina
                and utiles[n + 1].y - linea.y < 12):
            siguiente = utiles[n + 1].texto
        for c in _conceptos_de(linea.texto, siguiente):
            if c.tipo == "base" and base is None:
                base = c.importe
            elif c.tipo == "base_neta" and base_neta is None:
                base_neta = c.importe
            elif c.tipo == "total":
                total = c.importe              # vale el último que aparece
            elif c.tipo == "impuesto":
                impuestos.append(c)
            elif c.tipo == "retencion":
                retenciones.append(c)
            elif c.tipo == "recargo":
                recargos.append(c)
            elif c.tipo == "descuento" and descuento is None:
                descuento = c
            elif c.tipo == "suplidos" and c.importe is not None:
                suplidos += c.importe
                hay_suplidos = True

    t = _Totales(total=total)
    if hay_suplidos:
        t.suplidos = round(suplidos, 2)

    # El descuento se aplica sobre la base, antes del impuesto.
    if descuento is not None and descuento.importe:
        t.descuento = {"porcentaje": descuento.porcentaje,
                       "importe": -abs(descuento.importe)}
        t.base_bruta = base
        if base_neta is not None:
            t.base = base_neta
        elif base is not None:
            t.base = round(base - abs(descuento.importe), 2)
    else:
        t.base = base_neta if base_neta is not None else base
        if base is not None and base_neta is not None and base != base_neta:
            t.base_bruta = base

    for c in impuestos:
        if c.importe is None:
            continue
        pct = c.porcentaje
        if c.motivo or (pct is None and abs(c.importe) < 0.005):
            pct = 0.0
        t.iva.append({"porcentaje": pct, "base_imponible": None,
                      "cuota": c.importe, "motivo": c.motivo})
    if len(t.iva) == 1:
        t.iva[0]["base_imponible"] = t.base
    else:
        # Con varios tipos la base de cada tramo no suele estar escrita: se
        # deduce de su cuota, y el validador lo sabe y ajusta el margen.
        for tramo in t.iva:
            tramo["base_imponible"] = _deducir_base(tramo["cuota"], tramo["porcentaje"])
            tramo["base_deducida"] = True

    for c in retenciones:
        if c.importe is None or (c.porcentaje is None and abs(c.importe) < 0.005):
            continue          # «IRPF 0,00 €»: el renglón está, la retención no
        t.retencion = {"porcentaje": c.porcentaje, "base_imponible": t.base,
                       "cuota": abs(c.importe)}

    for c in recargos:
        if c.importe is None:
            continue
        tramo = {"porcentaje": c.porcentaje, "base_imponible": None, "cuota": c.importe}
        if len(recargos) == 1 and len(t.iva) <= 1:
            tramo["base_imponible"] = t.base
        else:
            tramo["base_imponible"] = _deducir_base(c.importe, c.porcentaje)
            tramo["base_deducida"] = True
        t.recargo.append(tramo)

    # Una simplificada con el IVA dentro puede no escribir la base: se
    # deduce del total cuando hay un solo tipo.
    if (t.base is None and t.total is not None and len(t.iva) == 1
            and t.iva[0]["porcentaje"] is not None):
        t.base = round(t.total / (1 + t.iva[0]["porcentaje"] / 100), 2)
        t.iva[0]["base_imponible"] = t.base
    return t


# --------------------------------------------------------------------------
# Tipo de documento, país y menciones
# --------------------------------------------------------------------------

def _detectar_tipo_documento(texto: str) -> tuple[str, float]:
    """Qué es el papel, según la primera pista que aparezca en la cabecera.

    Se busca palabra entera y gana la que sale antes: «pedidos@empresa» no
    es un pedido, y el «recibo domiciliado» de la forma de pago de una
    factura no la convierte en recibo.
    """
    cabecera = _norm(texto[:900])
    cabecera = re.sub(r"recibo (?:domiciliado|bancario)", "", cabecera)
    tipos = {
        "albaran": ("albaran", "delivery note", "lieferschein", "packing slip"),
        "presupuesto": ("presupuesto", "quotation", "quote", "angebot"),
        "pedido": ("pedido", "purchase order", "bestellung"),
        "proforma": ("proforma", "pro forma"),
        "recibo": ("recibo", "receipt", "quittung"),
        "factura": ("factura", "invoice", "rechnung"),
    }
    mejor: Optional[tuple[int, str]] = None
    for tipo, pistas in tipos.items():
        for pista in pistas:
            m = re.search(rf"(?<![a-z@.]){re.escape(pista)}(?![a-z@])", cabecera)
            if m and (mejor is None or m.start() < mejor[0]):
                mejor = (m.start(), tipo)
    if mejor:
        return mejor[1], 0.9
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


def _menciones(lineas: list[LineaVisual]) -> dict:
    """Lo que la factura dice de sí misma en sus notas: exención, IVA
    incluido, simplificada, rectificativa y a cuál rectifica."""
    salida: dict = {}
    for linea in lineas:
        if linea.girada:
            continue
        plano = _norm(linea.texto)
        if "exencion" not in salida and _RE_EXENCION.search(plano):
            salida["exencion"] = linea.texto.strip()
        if _RE_IVA_INCLUIDO.search(plano):
            salida["precios_con_iva"] = True
        if _RE_SIMPLIFICADA.search(plano):
            salida["simplificada"] = True
        if _RE_RECTIFICA.search(plano):
            salida["rectificativa"] = True
            m = re.search(
                r"rectifica\w*\s+(?:a\s+)?(?:la\s+)?factura\s+(?:n[º°]\s*)?"
                r"([A-Za-z0-9][\w/\-.]*\d)(?:\s+de\s+(\d{1,2}/\d{1,2}/\d{2,4}))?",
                linea.texto, re.IGNORECASE)
            if m:
                salida["rectifica_a"] = " de ".join(g for g in m.groups() if g)
    return salida


# --------------------------------------------------------------------------
# Entrada pública
# --------------------------------------------------------------------------

def extraer(documento: Documento, pais: Optional[str] = None) -> Extraccion:
    if documento.palabras:
        lineas = _agrupar_lineas(documento.palabras)
    else:
        lineas = [_linea_de_texto(l, i)
                  for i, l in enumerate(documento.texto.splitlines()) if l.strip()]
    texto = "\n".join(l.texto for l in lineas if not l.girada) or documento.texto

    codigo = (pais or _detectar_pais(texto)).upper()
    if codigo not in PAISES:
        codigo = "ES"

    ex = Extraccion(pais=codigo)
    ex.avisos.extend(documento.avisos)

    tipo, conf_tipo = _detectar_tipo_documento(texto)
    ex.campos["tipo_documento"] = Campo(tipo, conf_tipo, "cabecera del documento")

    numero = _buscar_numero(lineas)
    if numero:
        ex.campos["numero"] = numero
    for nombre in ("fecha_emision", "fecha_vencimiento"):
        fecha = _buscar_fecha(lineas, nombre, codigo)
        if fecha:
            ex.campos[nombre] = fecha

    ex.emisor, ex.receptor = _extraer_partes(lineas, texto, codigo)
    ex.lineas, avisos_tabla, ultima = _extraer_lineas(lineas)
    ex.avisos.extend(avisos_tabla)
    ex.menciones = _menciones(lineas)

    tot = _extraer_totales(lineas, (ultima + 1) if ultima is not None else 0)
    if tot.base is None and ex.lineas and not ex.menciones.get("precios_con_iva"):
        tot.base = round(sum(l["importe"] for l in ex.lineas), 2)
        ex.campos["base_imponible"] = Campo(tot.base, 0.6, "suma de las líneas")
        if len(tot.iva) == 1:
            tot.iva[0]["base_imponible"] = tot.base
    elif tot.base is not None:
        ex.campos["base_imponible"] = Campo(tot.base, 0.95, "zona de totales")
    if tot.total is not None:
        ex.campos["total"] = Campo(tot.total, 0.95, "zona de totales")

    ex.iva, ex.retencion, ex.recargo = tot.iva, tot.retencion, tot.recargo
    ex.suplidos, ex.descuento, ex.base_bruta = tot.suplidos, tot.descuento, tot.base_bruta

    # Último recurso para el total: la suma de lo que se ha leído.
    base = ex._v("base_imponible")
    if "total" not in ex.campos and base is not None and ex.iva:
        calculado = (base + sum(t["cuota"] for t in ex.iva)
                     + sum(r["cuota"] for r in ex.recargo)
                     - (ex.retencion["cuota"] if ex.retencion else 0.0)
                     + (ex.suplidos or 0.0))
        ex.campos["total"] = Campo(round(calculado, 2), 0.5,
                                   "calculado desde base e impuestos")
    return ex

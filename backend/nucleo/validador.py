"""Validación fiscal determinista de facturas.

Ni modelos, ni red, ni claves: solo aritmética y reglas de cada país.
A diferencia de `esquema.py` —que lanza excepciones y sirve para construir
el dataset— aquí nada revienta. Una factura con errores es justamente el
caso interesante, así que cada regla incumplida sale como un `Hallazgo`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional

from backend.nucleo.paises import PAISES

# Margen de redondeo aceptado al comparar importes (dos decimales).
TOLERANCIA = 0.02


class Gravedad(str, Enum):
    ERROR = "error"          # La factura es inválida: no cuadra o falta algo obligatorio.
    AVISO = "aviso"          # Sospechoso pero no invalida: merece revisión humana.
    INFO = "info"            # Observación sin consecuencias.


@dataclass
class Hallazgo:
    codigo: str
    gravedad: Gravedad
    campo: str
    mensaje: str
    esperado: Optional[Any] = None
    encontrado: Optional[Any] = None

    def a_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "gravedad": self.gravedad.value,
            "campo": self.campo,
            "mensaje": self.mensaje,
            "esperado": self.esperado,
            "encontrado": self.encontrado,
        }


@dataclass
class Informe:
    pais: str
    hallazgos: list[Hallazgo] = field(default_factory=list)

    @property
    def errores(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.gravedad is Gravedad.ERROR]

    @property
    def avisos(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.gravedad is Gravedad.AVISO]

    @property
    def valida(self) -> bool:
        return not self.errores

    def a_dict(self) -> dict:
        return {
            "pais": self.pais,
            "valida": self.valida,
            "n_errores": len(self.errores),
            "n_avisos": len(self.avisos),
            "hallazgos": [h.a_dict() for h in self.hallazgos],
        }


# --------------------------------------------------------------------------
# Identificadores fiscales
# --------------------------------------------------------------------------

_LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"
_LETRAS_CIF = "JABCDEFGHI"
# Sociedades y entes cuyo dígito de control es siempre una letra.
_CIF_LETRA_OBLIGATORIA = set("PQRSNW")
# Entidades cuyo dígito de control es siempre numérico.
_CIF_NUMERO_OBLIGATORIO = set("ABEH")


def _dni_valido(valor: str) -> bool:
    m = re.fullmatch(r"(\d{8})([A-Z])", valor)
    if not m:
        return False
    return _LETRAS_DNI[int(m.group(1)) % 23] == m.group(2)


def _nie_valido(valor: str) -> bool:
    m = re.fullmatch(r"([XYZ])(\d{7})([A-Z])", valor)
    if not m:
        return False
    prefijo = "XYZ".index(m.group(1))
    numero = int(f"{prefijo}{m.group(2)}")
    return _LETRAS_DNI[numero % 23] == m.group(3)


def _cif_valido(valor: str) -> bool:
    m = re.fullmatch(r"([ABCDEFGHJNPQRSUVW])(\d{7})([0-9A-J])", valor)
    if not m:
        return False
    tipo, digitos, control = m.group(1), m.group(2), m.group(3)

    # Posiciones pares se suman tal cual; las impares se duplican y se suman
    # las cifras del resultado.
    suma = 0
    for i, ch in enumerate(digitos):
        n = int(ch)
        if i % 2 == 0:
            doble = n * 2
            suma += doble // 10 + doble % 10
        else:
            suma += n
    digito = (10 - suma % 10) % 10

    if tipo in _CIF_LETRA_OBLIGATORIA:
        return control == _LETRAS_CIF[digito]
    if tipo in _CIF_NUMERO_OBLIGATORIO:
        return control == str(digito)
    # El resto admite ambas formas.
    return control in (str(digito), _LETRAS_CIF[digito])


def _vat_uk_valido(valor: str) -> bool:
    """VAT británico estándar de 9 cifras, algoritmo módulo 97."""
    digitos = valor[2:] if valor.startswith("GB") else valor
    if not re.fullmatch(r"\d{9}", digitos):
        return False
    pesos = (8, 7, 6, 5, 4, 3, 2)
    total = sum(int(d) * p for d, p in zip(digitos[:7], pesos))
    control = int(digitos[7:])
    # Se acepta el rango clásico y el rango 55 posterior.
    return any((total + control) % 97 == 0 for total in (total, total + 55))


def _ustid_de_valido(valor: str) -> bool:
    """USt-IdNr. alemana: DE + 9 cifras con dígito de control módulo 11."""
    m = re.fullmatch(r"DE(\d{9})", valor)
    if not m:
        return False
    digitos = m.group(1)
    producto = 10
    for ch in digitos[:8]:
        suma = (int(ch) + producto) % 10 or 10
        producto = (2 * suma) % 11
    control = (11 - producto) % 10
    return control == int(digitos[8])


def _ein_us_valido(valor: str) -> bool:
    """EIN: 9 cifras. No lleva dígito de control; solo se valida el prefijo."""
    m = re.fullmatch(r"(\d{2})-?(\d{7})", valor)
    if not m:
        return False
    # Prefijos nunca asignados por el IRS.
    return m.group(1) not in {"00", "07", "08", "09", "17", "18", "19",
                              "28", "29", "49", "69", "70", "78", "79", "89"}


def validar_id_fiscal(valor: str, pais: str = "ES") -> bool:
    """Comprueba el dígito de control, no solo el formato."""
    if not valor:
        return False
    limpio = re.sub(r"[\s.\-]", "", valor).upper()
    codigo = pais.upper()
    if codigo == "ES":
        limpio = limpio[2:] if limpio.startswith("ES") else limpio
        return _dni_valido(limpio) or _nie_valido(limpio) or _cif_valido(limpio)
    if codigo == "UK":
        return _vat_uk_valido(limpio)
    if codigo == "DE":
        return _ustid_de_valido(limpio)
    if codigo == "US":
        return _ein_us_valido(limpio)
    return False


# --------------------------------------------------------------------------
# Reglas sobre el documento
# --------------------------------------------------------------------------

# Palabras que delatan que el documento no es una factura.
_NO_FACTURA = {
    "albaran": ("albarán", "albaran", "delivery note", "lieferschein", "packing slip"),
    "presupuesto": ("presupuesto", "quote", "quotation", "angebot", "estimate"),
    "pedido": ("pedido", "purchase order", "bestellung", "order confirmation"),
    "proforma": ("proforma", "pro forma"),
    "recibo": ("recibo", "receipt", "quittung"),
}

# Tipos de impuesto vigentes en cada país.
_TIPOS_IMPUESTO = {
    "ES": {0.0, 2.0, 4.0, 5.0, 7.5, 10.0, 21.0},
    "UK": {0.0, 5.0, 20.0},
    "DE": {0.0, 7.0, 19.0},
}


def _num(valor: Any) -> Optional[float]:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _cuadra(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCIA


def _fecha(valor: Any) -> Optional[date]:
    if isinstance(valor, date):
        return valor
    if not isinstance(valor, str):
        return None
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        return None


_ARTICULO = {"albaran": "un albarán", "presupuesto": "un presupuesto",
             "pedido": "un pedido", "proforma": "una factura proforma",
             "recibo": "un recibo"}


def _clase_documento(datos: dict) -> Optional[str]:
    """Si el documento no es una factura, devuelve qué es.

    Se mira lo que el documento declara y también lo que dice su texto:
    un albarán que trae la palabra "ALBARÁN" en la cabecera se delata solo,
    declare lo que declare.
    """
    declarado = str(datos.get("tipo_documento") or "factura").lower()
    if declarado in _NO_FACTURA:
        return declarado

    texto = " ".join(
        str(datos.get(c, ""))
        for c in ("titulo", "observaciones", "numero")
    ).lower()
    for clase, pistas in _NO_FACTURA.items():
        if any(p in texto for p in pistas):
            return clase
    return None


def _validar_identificadores(datos: dict, pais: str, h: list[Hallazgo]) -> None:
    etiqueta = PAISES[pais].id_fiscal["es"]
    for papel, obligatorio in (("emisor", True), ("receptor", False)):
        parte = datos.get(papel)
        if not isinstance(parte, dict):
            if obligatorio:
                h.append(Hallazgo(
                    f"{papel.upper()}_AUSENTE", Gravedad.ERROR, papel,
                    f"Falta el {papel}, que es obligatorio en una factura completa.",
                ))
            continue

        nif = str(parte.get("nif") or "").strip()
        if not nif:
            h.append(Hallazgo(
                f"{papel.upper()}_SIN_ID", Gravedad.ERROR, f"{papel}.nif",
                f"El {papel} no declara {etiqueta}.",
            ))
        elif not validar_id_fiscal(nif, pais):
            h.append(Hallazgo(
                f"{papel.upper()}_ID_INVALIDO", Gravedad.ERROR, f"{papel}.nif",
                f"El {etiqueta} del {papel} no supera la comprobación "
                f"del dígito de control.",
                encontrado=nif,
            ))

        if not str(parte.get("nombre") or "").strip():
            h.append(Hallazgo(
                f"{papel.upper()}_SIN_NOMBRE", Gravedad.ERROR, f"{papel}.nombre",
                f"El {papel} no tiene razón social.",
            ))

    emisor = datos.get("emisor") or {}
    receptor = datos.get("receptor") or {}
    nif_e = str(emisor.get("nif") or "").strip().upper()
    nif_r = str(receptor.get("nif") or "").strip().upper()
    if nif_e and nif_e == nif_r:
        h.append(Hallazgo(
            "EMISOR_IGUAL_RECEPTOR", Gravedad.ERROR, "receptor.nif",
            "Emisor y receptor comparten identificador fiscal: "
            "una empresa no se factura a sí misma.",
            encontrado=nif_e,
        ))


def _validar_fechas(datos: dict, h: list[Hallazgo]) -> None:
    emision = _fecha(datos.get("fecha_emision"))
    vencimiento = _fecha(datos.get("fecha_vencimiento"))

    if emision is None:
        h.append(Hallazgo(
            "SIN_FECHA_EMISION", Gravedad.ERROR, "fecha_emision",
            "Falta la fecha de emisión o no es una fecha válida.",
            encontrado=datos.get("fecha_emision"),
        ))
        return

    if emision > date.today():
        h.append(Hallazgo(
            "EMISION_FUTURA", Gravedad.AVISO, "fecha_emision",
            "La fecha de emisión está en el futuro.",
            encontrado=emision.isoformat(),
        ))

    if vencimiento and vencimiento < emision:
        h.append(Hallazgo(
            "VENCIMIENTO_ANTERIOR", Gravedad.ERROR, "fecha_vencimiento",
            "El vencimiento es anterior a la emisión.",
            esperado=f">= {emision.isoformat()}",
            encontrado=vencimiento.isoformat(),
        ))


def _validar_lineas(datos: dict, h: list[Hallazgo]) -> float:
    """Comprueba cada línea y devuelve la suma de importes."""
    lineas = datos.get("lineas")
    if not isinstance(lineas, list) or not lineas:
        h.append(Hallazgo(
            "SIN_LINEAS", Gravedad.ERROR, "lineas",
            "La factura no tiene ninguna línea de detalle.",
        ))
        return 0.0

    suma = 0.0
    for i, linea in enumerate(lineas, start=1):
        if not isinstance(linea, dict):
            h.append(Hallazgo(
                "LINEA_MALFORMADA", Gravedad.ERROR, f"lineas[{i}]",
                "La línea no tiene la estructura esperada.",
            ))
            continue

        cantidad = _num(linea.get("cantidad"))
        precio = _num(linea.get("precio_unitario"))
        importe = _num(linea.get("importe"))

        if importe is None:
            h.append(Hallazgo(
                "LINEA_SIN_IMPORTE", Gravedad.ERROR, f"lineas[{i}].importe",
                f"La línea {i} no declara importe.",
            ))
            continue
        suma += importe

        if not str(linea.get("descripcion") or "").strip():
            h.append(Hallazgo(
                "LINEA_SIN_DESCRIPCION", Gravedad.AVISO, f"lineas[{i}].descripcion",
                f"La línea {i} no describe qué se factura.",
            ))

        if cantidad is not None and cantidad <= 0:
            h.append(Hallazgo(
                "LINEA_CANTIDAD_INVALIDA", Gravedad.ERROR, f"lineas[{i}].cantidad",
                f"La línea {i} factura una cantidad de {cantidad:g}. "
                "Una línea de factura tiene que mover unidades.",
                esperado="> 0", encontrado=cantidad,
            ))

        if precio is not None and precio < 0:
            h.append(Hallazgo(
                "LINEA_PRECIO_NEGATIVO", Gravedad.ERROR, f"lineas[{i}].precio_unitario",
                f"La línea {i} tiene precio unitario negativo. "
                "Un abono se emite como factura rectificativa, no como precio en negativo.",
                encontrado=precio,
            ))

        if cantidad is not None and precio is not None:
            esperado = round(cantidad * precio, 2)
            if not _cuadra(importe, esperado):
                h.append(Hallazgo(
                    "LINEA_NO_CUADRA", Gravedad.ERROR, f"lineas[{i}].importe",
                    f"En la línea {i}, cantidad x precio no da el importe.",
                    esperado=esperado, encontrado=importe,
                ))

    return round(suma, 2)


def _validar_impuestos(datos: dict, pais: str, suma_lineas: float,
                       h: list[Hallazgo]) -> None:
    etiqueta = PAISES[pais].impuesto["es"]
    base = _num(datos.get("base_imponible"))

    if base is None:
        h.append(Hallazgo(
            "SIN_BASE", Gravedad.ERROR, "base_imponible",
            "Falta la base imponible.",
        ))
    elif suma_lineas and not _cuadra(base, suma_lineas):
        h.append(Hallazgo(
            "BASE_NO_CUADRA", Gravedad.ERROR, "base_imponible",
            "La base imponible no coincide con la suma de las líneas.",
            esperado=suma_lineas, encontrado=base,
        ))

    desglose = datos.get("iva")
    if not isinstance(desglose, list) or not desglose:
        h.append(Hallazgo(
            "SIN_DESGLOSE_IMPUESTO", Gravedad.ERROR, "iva",
            f"No hay desglose de {etiqueta}.",
        ))
        cuota_total = 0.0
    else:
        cuota_total = 0.0
        tipos_validos = _TIPOS_IMPUESTO.get(pais)
        for i, tramo in enumerate(desglose, start=1):
            if not isinstance(tramo, dict):
                continue
            pct = _num(tramo.get("porcentaje"))
            base_t = _num(tramo.get("base_imponible"))
            cuota = _num(tramo.get("cuota"))
            if cuota is not None:
                cuota_total += cuota

            if pct is not None and tipos_validos and pct not in tipos_validos:
                h.append(Hallazgo(
                    "TIPO_IMPUESTO_INEXISTENTE", Gravedad.ERROR, f"iva[{i}].porcentaje",
                    f"El {pct}% no es un tipo de {etiqueta} vigente en "
                    f"{PAISES[pais].nombre['es']}.",
                    esperado=sorted(tipos_validos), encontrado=pct,
                ))

            if None not in (pct, base_t, cuota):
                esperado = round(base_t * pct / 100, 2)
                if not _cuadra(cuota, esperado):
                    h.append(Hallazgo(
                        "CUOTA_NO_CUADRA", Gravedad.ERROR, f"iva[{i}].cuota",
                        f"La cuota del tramo al {pct}% no sale de su base.",
                        esperado=esperado, encontrado=cuota,
                    ))
        cuota_total = round(cuota_total, 2)

    retencion = datos.get("retencion")
    cuota_ret = 0.0
    if isinstance(retencion, dict):
        pct = _num(retencion.get("porcentaje"))
        base_r = _num(retencion.get("base_imponible"))
        cuota_ret = _num(retencion.get("cuota")) or 0.0
        if not PAISES[pais].usa_retencion:
            h.append(Hallazgo(
                "RETENCION_NO_APLICABLE", Gravedad.AVISO, "retencion",
                f"Se declara retención, que no se usa en "
                f"{PAISES[pais].nombre['es']}.",
            ))
        if None not in (pct, base_r):
            esperado = round(base_r * pct / 100, 2)
            if not _cuadra(cuota_ret, esperado):
                h.append(Hallazgo(
                    "RETENCION_NO_CUADRA", Gravedad.ERROR, "retencion.cuota",
                    "La cuota de retención no sale de su base.",
                    esperado=esperado, encontrado=cuota_ret,
                ))

    total = _num(datos.get("total"))
    if total is None:
        h.append(Hallazgo(
            "SIN_TOTAL", Gravedad.ERROR, "total",
            "La factura no declara total.",
        ))
    elif base is not None:
        esperado = round(base + cuota_total - cuota_ret, 2)
        if not _cuadra(total, esperado):
            h.append(Hallazgo(
                "TOTAL_NO_CUADRA", Gravedad.ERROR, "total",
                "El total no es base + impuestos - retención.",
                esperado=esperado, encontrado=total,
            ))


def _validar_numeracion(datos: dict, h: list[Hallazgo]) -> None:
    numero = str(datos.get("numero") or "").strip()
    if not numero:
        h.append(Hallazgo(
            "SIN_NUMERO", Gravedad.ERROR, "numero",
            "La factura no tiene número, que es un requisito legal.",
        ))
    elif not re.search(r"\d", numero):
        h.append(Hallazgo(
            "NUMERO_SIN_CIFRAS", Gravedad.AVISO, "numero",
            "El número de factura no contiene ninguna cifra.",
            encontrado=numero,
        ))


def validar(datos: dict, pais: Optional[str] = None) -> Informe:
    """Pasa una factura por todas las reglas y devuelve el informe.

    `datos` es el diccionario ya extraído del documento. Nunca lanza:
    todo lo que no cuadra sale como hallazgo.
    """
    codigo = str(pais or datos.get("pais") or "ES").upper()
    if codigo not in PAISES:
        return Informe(pais=codigo, hallazgos=[Hallazgo(
            "PAIS_NO_SOPORTADO", Gravedad.ERROR, "pais",
            f"País no soportado: {codigo}.",
            esperado=sorted(PAISES), encontrado=codigo,
        )])

    h: list[Hallazgo] = []

    # Si no es una factura, decirlo y parar. Enumerar los campos de factura
    # que le faltan a un albarán no informa de nada: le faltan todos, y el
    # problema es otro.
    clase = _clase_documento(datos)
    if clase is not None:
        h.append(Hallazgo(
            "DOC_NO_ES_FACTURA", Gravedad.ERROR, "tipo_documento",
            f"Esto no es una factura: es {_ARTICULO.get(clase, f'un {clase}')}. "
            "No sirve como justificante para deducir el impuesto.",
            esperado="factura", encontrado=clase,
        ))
        _validar_identificadores(datos, codigo, h)
        return Informe(pais=codigo, hallazgos=h)

    _validar_numeracion(datos, h)
    _validar_fechas(datos, h)
    _validar_identificadores(datos, codigo, h)
    suma = _validar_lineas(datos, h)
    _validar_impuestos(datos, codigo, suma, h)
    return Informe(pais=codigo, hallazgos=h)

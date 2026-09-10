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


def _prefijo_extranjero(nif: str, pais: str) -> Optional[str]:
    """El país de un NIF-IVA de otro sitio («FR83999123456»), o None."""
    limpio = re.sub(r"[\s.\-]", "", nif).upper()
    m = re.fullmatch(r"([A-Z]{2})[0-9A-Z]{8,12}", limpio)
    if not m:
        return None
    propio = {"ES": "ES", "UK": "GB", "DE": "DE"}.get(pais)
    return None if m.group(1) == propio else m.group(1)


def _validar_identificadores(datos: dict, pais: str, h: list[Hallazgo]) -> None:
    etiqueta = PAISES[pais].id_fiscal["es"]
    for papel, obligatorio in (("emisor", True), ("receptor", False)):
        parte = datos.get(papel)
        # La simplificada no tiene por qué identificar al destinatario
        # (RD 1619/2012, art. 7): si no lo trae, no falta nada.
        if (papel == "receptor" and datos.get("simplificada")
                and not (isinstance(parte, dict) and parte.get("nif"))):
            continue
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
        elif papel == "receptor" and _prefijo_extranjero(nif, pais):
            h.append(Hallazgo(
                "RECEPTOR_ID_EXTRANJERO", Gravedad.INFO, "receptor.nif",
                f"Identificador fiscal extranjero ({_prefijo_extranjero(nif, pais)}): "
                "se comprueba el formato, no el dígito de control, que depende "
                "de cada país y del censo VIES, al que esto no se conecta.",
                encontrado=nif,
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

    # En una rectificativa las unidades devueltas van en negativo: es como
    # se anula lo facturado, no un error.
    rectificativa = bool(datos.get("rectificativa"))
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

        if cantidad is not None and (cantidad == 0 or (cantidad < 0 and not rectificativa)):
            h.append(Hallazgo(
                "LINEA_CANTIDAD_INVALIDA", Gravedad.ERROR, f"lineas[{i}].cantidad",
                f"La línea {i} factura una cantidad de {cantidad:g}. "
                "Una línea de factura tiene que mover unidades.",
                esperado="> 0", encontrado=cantidad,
            ))

        if precio is not None and precio < 0 and not rectificativa:
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


# Tipos del recargo de equivalencia (art. 161 LIVA), incluidos los reducidos
# temporales de 2023-2024 que aún aparecen en rectificativas.
_TIPOS_RECARGO = {0.0, 0.26, 0.5, 0.62, 1.4, 1.75, 5.2}


def _validar_impuestos(datos: dict, pais: str, suma_lineas: float,
                       h: list[Hallazgo]) -> None:
    etiqueta = PAISES[pais].impuesto["es"]
    base = _num(datos.get("base_imponible"))
    total = _num(datos.get("total"))
    base_bruta = _num(datos.get("base_bruta"))
    descuento = datos.get("descuento") if isinstance(datos.get("descuento"), dict) else None
    importe_dto = abs(_num(descuento.get("importe")) or 0.0) if descuento else 0.0

    # --- Las líneas contra la base --------------------------------------
    # Es lo que distingue comprobar de extraer: una base falsa con el IVA y
    # el total calculados sobre ella cuadra en todo lo demás.
    if base is None:
        h.append(Hallazgo(
            "SIN_BASE", Gravedad.ERROR, "base_imponible",
            "Falta la base imponible.",
        ))
    elif suma_lineas:
        if datos.get("precios_con_iva") and total is not None:
            if not _cuadra(total, suma_lineas):
                h.append(Hallazgo(
                    "BASE_NO_CUADRA", Gravedad.ERROR, "total",
                    "Los precios llevan el impuesto incluido y las líneas no "
                    "suman el total.",
                    esperado=suma_lineas, encontrado=total,
                ))
        elif descuento:
            bruta = base_bruta if base_bruta is not None else round(base + importe_dto, 2)
            if not _cuadra(bruta, suma_lineas):
                h.append(Hallazgo(
                    "BASE_NO_CUADRA", Gravedad.ERROR, "base_bruta",
                    "La base antes del descuento no coincide con la suma de "
                    "las líneas.",
                    esperado=suma_lineas, encontrado=bruta,
                ))
        elif not _cuadra(base, suma_lineas):
            h.append(Hallazgo(
                "BASE_NO_CUADRA", Gravedad.ERROR, "base_imponible",
                "La base imponible no coincide con la suma de las líneas.",
                esperado=suma_lineas, encontrado=base,
            ))

    # --- Descuento: sobre la base, antes del impuesto -------------------
    if descuento and base_bruta is not None:
        pct = _num(descuento.get("porcentaje"))
        if pct is not None and not _cuadra(importe_dto, round(base_bruta * pct / 100, 2)):
            h.append(Hallazgo(
                "DESCUENTO_NO_CUADRA", Gravedad.ERROR, "descuento",
                f"El descuento del {pct:g} % no sale de la base bruta.",
                esperado=round(base_bruta * pct / 100, 2), encontrado=importe_dto,
            ))
        if base is not None and not _cuadra(base, round(base_bruta - importe_dto, 2)):
            h.append(Hallazgo(
                "BASE_NETA_NO_CUADRA", Gravedad.ERROR, "base_imponible",
                "La base después del descuento no es la bruta menos el descuento.",
                esperado=round(base_bruta - importe_dto, 2), encontrado=base,
            ))

    # --- Impuesto, tramo a tramo ----------------------------------------
    desglose = datos.get("iva")
    tramos = [t for t in desglose if isinstance(t, dict)] if isinstance(desglose, list) else []
    cuota_total = 0.0
    if not tramos:
        h.append(Hallazgo(
            "SIN_DESGLOSE_IMPUESTO", Gravedad.ERROR, "iva",
            f"No hay desglose de {etiqueta}.",
        ))
    else:
        tipos_validos = _TIPOS_IMPUESTO.get(pais)
        suma_bases = 0.0
        bases_completas = True
        margen = TOLERANCIA
        for i, tramo in enumerate(tramos, start=1):
            pct = _num(tramo.get("porcentaje"))
            base_t = _num(tramo.get("base_imponible"))
            cuota = _num(tramo.get("cuota"))
            if cuota is not None:
                cuota_total += cuota
            if base_t is None:
                bases_completas = False
            else:
                suma_bases += base_t

            if pct is not None and tipos_validos and pct not in tipos_validos:
                h.append(Hallazgo(
                    "TIPO_IMPUESTO_INEXISTENTE", Gravedad.ERROR, f"iva[{i}].porcentaje",
                    f"El {pct}% no es un tipo de {etiqueta} vigente en "
                    f"{PAISES[pais].nombre['es']}.",
                    esperado=sorted(tipos_validos), encontrado=pct,
                ))

            if tramo.get("base_deducida"):
                # La base de este tramo se ha deducido de su cuota: comprobar
                # la cuota contra ella no demuestra nada. Lo que sí se puede
                # es exigir que las bases de todos los tramos sumen la base,
                # con el margen que deja redondear la cuota al céntimo.
                if pct:
                    margen += 0.005 * 100 / pct
            elif None not in (pct, base_t, cuota):
                esperado = round(base_t * pct / 100, 2)
                if not _cuadra(cuota, esperado):
                    h.append(Hallazgo(
                        "CUOTA_NO_CUADRA", Gravedad.ERROR, f"iva[{i}].cuota",
                        f"La cuota del tramo al {pct:g}% no sale de su base.",
                        esperado=esperado, encontrado=cuota,
                    ))
        cuota_total = round(cuota_total, 2)

        if len(tramos) > 1 and bases_completas and base is not None \
                and abs(suma_bases - base) > margen:
            h.append(Hallazgo(
                "TRAMOS_NO_SUMAN_BASE", Gravedad.ERROR, "iva",
                "Las bases de los tramos de impuesto no suman la base imponible.",
                esperado=base, encontrado=round(suma_bases, 2),
            ))

        # --- Exención: o se repercute, o se exime, no las dos --------------
        mencion = str(datos.get("exencion") or "").strip()
        repercutidos = [t for t in tramos
                        if (_num(t.get("porcentaje")) or 0) > 0
                        and abs(_num(t.get("cuota")) or 0) > TOLERANCIA]
        if mencion and repercutidos:
            tipos = ", ".join(f"{_num(t.get('porcentaje')):g} %" for t in repercutidos)
            h.append(Hallazgo(
                "IVA_EN_EXENTA", Gravedad.ERROR, "iva",
                f"La factura declara una operación sin {etiqueta} repercutido "
                f"(«{mencion[:90]}») y a la vez lo repercute al {tipos}. "
                "Una de las dos cosas sobra.",
                esperado=0.0,
                encontrado=round(sum(_num(t.get("cuota")) or 0 for t in repercutidos), 2),
            ))
        elif (pais == "ES" and not repercutidos and base
              and all((_num(t.get("porcentaje")) or 0) == 0 for t in tramos)
              and not mencion):
            h.append(Hallazgo(
                "EXENCION_SIN_MENCION", Gravedad.AVISO, "iva",
                f"No se repercute {etiqueta} y la factura no dice por qué. "
                "El RD 1619/2012 exige citar la exención o la inversión del "
                "sujeto pasivo.",
            ))

    # --- Retención ---------------------------------------------------------
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
                    f"La retención dice ser del {pct:g} % y no sale de su base.",
                    esperado=esperado, encontrado=cuota_ret,
                ))

    # --- Recargo de equivalencia: suma, y va aparte del IVA -----------------
    cuota_re = 0.0
    recargo = datos.get("recargo")
    for i, tramo in enumerate(recargo if isinstance(recargo, list) else [], start=1):
        if not isinstance(tramo, dict):
            continue
        pct = _num(tramo.get("porcentaje"))
        base_re = _num(tramo.get("base_imponible"))
        cuota = _num(tramo.get("cuota")) or 0.0
        cuota_re += cuota
        if pais == "ES" and pct is not None and pct not in _TIPOS_RECARGO:
            h.append(Hallazgo(
                "RECARGO_TIPO_INEXISTENTE", Gravedad.ERROR, f"recargo[{i}].porcentaje",
                f"El {pct:g} % no es un tipo de recargo de equivalencia.",
                esperado=sorted(_TIPOS_RECARGO), encontrado=pct,
            ))
        if not tramo.get("base_deducida") and None not in (pct, base_re):
            esperado = round(base_re * pct / 100, 2)
            if not _cuadra(cuota, esperado):
                h.append(Hallazgo(
                    "RECARGO_NO_CUADRA", Gravedad.ERROR, f"recargo[{i}].cuota",
                    f"El recargo del {pct:g} % no sale de su base.",
                    esperado=esperado, encontrado=cuota,
                ))
    cuota_re = round(cuota_re, 2)

    # --- Suplidos: ni base ni impuesto, pero se cobran -----------------------
    suplidos = _num(datos.get("suplidos")) or 0.0

    if total is None:
        h.append(Hallazgo(
            "SIN_TOTAL", Gravedad.ERROR, "total",
            "La factura no declara total.",
        ))
    elif base is not None:
        esperado = round(base + cuota_total + cuota_re - cuota_ret + suplidos, 2)
        if not _cuadra(total, esperado):
            formula = "base + impuestos - retención"
            if cuota_re:
                formula += " + recargo"
            if suplidos:
                formula += " + suplidos"
            h.append(Hallazgo(
                "TOTAL_NO_CUADRA", Gravedad.ERROR, "total",
                f"El total no es {formula}.",
                esperado=esperado, encontrado=total,
            ))


def _validar_rectificacion(datos: dict, h: list[Hallazgo]) -> None:
    total = _num(datos.get("total"))
    if datos.get("rectificativa"):
        if not str(datos.get("rectifica_a") or "").strip():
            h.append(Hallazgo(
                "RECTIFICATIVA_SIN_REFERENCIA", Gravedad.AVISO, "rectifica_a",
                "Es una factura rectificativa y no dice qué factura rectifica.",
            ))
    elif total is not None and total < 0:
        h.append(Hallazgo(
            "TOTAL_NEGATIVO", Gravedad.ERROR, "total",
            "El total es negativo y la factura no se declara rectificativa. "
            "Un abono se emite como rectificativa, citando la factura original.",
            encontrado=total,
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
    _validar_rectificacion(datos, h)
    suma = _validar_lineas(datos, h)
    _validar_impuestos(datos, codigo, suma, h)
    return Informe(pais=codigo, hallazgos=h)

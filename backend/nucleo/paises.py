from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pais:
    codigo: str
    nombre: dict[str, str]
    moneda: str
    id_fiscal: dict[str, str]
    id_fiscal_re: str
    impuesto: dict[str, str]
    tipo_impuesto: dict[str, str]
    fecha_formatos: tuple[str, ...]
    usa_retencion: bool = False
    usa_clave_operacion: bool = False


PAISES: dict[str, Pais] = {
    "ES": Pais(
        codigo="ES",
        nombre={"es": "España", "en": "Spain"},
        moneda="€",
        id_fiscal={"es": "NIF", "en": "Tax ID (NIF)"},
        id_fiscal_re=r"[A-Z][0-9]{8}",
        impuesto={"es": "IVA", "en": "VAT"},
        tipo_impuesto={"es": "impuesto sobre el valor añadido", "en": "value added tax"},
        fecha_formatos=("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"),
        usa_retencion=True,
        usa_clave_operacion=True,
    ),
    "UK": Pais(
        codigo="UK",
        nombre={"es": "Reino Unido", "en": "United Kingdom"},
        moneda="£",
        id_fiscal={"es": "VAT Reg No", "en": "VAT Reg No"},
        id_fiscal_re=r"(?:GB)?[0-9]{9}",
        impuesto={"es": "VAT", "en": "VAT"},
        tipo_impuesto={"es": "impuesto sobre el valor añadido", "en": "value added tax"},
        fecha_formatos=("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"),
    ),
    "US": Pais(
        codigo="US",
        nombre={"es": "Estados Unidos", "en": "United States"},
        moneda="$",
        id_fiscal={"es": "EIN / Tax ID", "en": "EIN / Tax ID"},
        id_fiscal_re=r"[0-9]{2}-?[0-9]{7}",
        impuesto={"es": "Sales Tax", "en": "Sales Tax"},
        tipo_impuesto={"es": "impuesto sobre las ventas", "en": "sales tax"},
        fecha_formatos=("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d"),
    ),
    "DE": Pais(
        codigo="DE",
        nombre={"es": "Alemania", "en": "Germany"},
        moneda="€",
        id_fiscal={"es": "USt-IdNr.", "en": "USt-IdNr."},
        id_fiscal_re=r"DE[0-9]{9}",
        impuesto={"es": "Umsatzsteuer (MwSt.)", "en": "Umsatzsteuer (VAT)"},
        tipo_impuesto={"es": "impuesto sobre el valor añadido", "en": "value added tax"},
        fecha_formatos=("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"),
    ),
}


def obtener_pais(codigo: str) -> Pais:
    return PAISES.get(codigo.upper(), PAISES["ES"])
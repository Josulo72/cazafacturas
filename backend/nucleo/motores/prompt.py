from __future__ import annotations

import json

from backend.nucleo.paises import obtener_pais

PROMPT_VERSION = "3"

_ES = """Eres un extractor de datos de facturas {nombres_pais}.
Lee el documento JSON que se te da. Debes devolver SOLO un objeto JSON, sin
texto alrededor ni bloque markdown, con esta estructura:
{esquema}
Reglas:
- El identificador fiscal ({id_fiscal}) usa su formato local; normalízalo (sin
  espacios ni guiones) y ponlo en "nif". El país de la factura va en "pais".
- No inventes campos. Si un dato falta o no se lee, es "anomalias".
- Si el documento NO es una factura (p.ej. albarán, nota de entrega), devuelve
  {{"tipo_documento": "albaran", "anomalias": ["no_es_factura"]}} y nada más.
- Comprueba coherencia: base = suma de líneas, total = base + {impuesto} - retención,
  cuota = base * porcentaje. Si algo no cuadra, añade la anomalía y devuelve los
  valores tal como aparecen en el documento.
- Las cantidades se redondean a 2 decimales. La cuota de {impuesto} se redondea a
  2 decimales; una diferencia menor de 0.01 por redondeo no es una anomalía.
- "anomalias" usa estos códigos canónicos (no los traduzcas):
  no_es_factura, cif_emisor_faltante, numero_factura_faltante,
  fecha_emision_futura, total_no_cuadra, base_imponible_no_cuadra,
  iva_faltante, receptor_igual_emisor, linea_cantidad_invalida,
  cuota_iva_no_cuadra.
- {retencion_instruccion}
Documento:
"""

_EN = """You are an invoice data extractor for invoices from {nombres_pais}.
Read the JSON document given. Return ONLY a JSON object, with no surrounding
text and no markdown fence, with this structure:
{esquema}
Rules:
- The fiscal identifier ({id_fiscal}) has a local format; normalize it (no
  spaces or dashes) and put it in "nif". Put the invoice country in "pais".
- Do not invent fields. If data is missing or unreadable, flag it in "anomalias".
- If the document is NOT an invoice (e.g. a delivery note), return
  {{"tipo_documento": "albaran", "anomalias": ["no_es_factura"]}} and nothing else.
- Check coherence: base = sum of lines, total = base + {impuesto} - withholding,
  tax amount = base * rate. If something does not add up, add the anomaly and
  return the values exactly as they appear in the document.
- Money amounts round to 2 decimals. The {impuesto} amount rounds to 2 decimals;
  a rounding difference under 0.01 is not an anomaly.
- "anomalias" uses these canonical codes (do not translate them):
  no_es_factura, cif_emisor_faltante, numero_factura_faltante,
  fecha_emision_futura, total_no_cuadra, base_imponible_no_cuadra,
  iva_faltante, receptor_igual_emisor, linea_cantidad_invalida,
  cuota_iva_no_cuadra.
- {retencion_instruccion}
Document:
"""

_ESQUEMA = """{{
  "tipo_documento": "factura",
  "pais": "{codigo}",
  "numero": "...",
  "fecha_emision": "AAAA-MM-DD",
  "fecha_vencimiento": "AAAA-MM-DD o null",
  "emisor": {{"nombre": "...", "nif": "...", "direccion": {{"calle": "...", "ciudad": "...", "provincia": "...", "codigo_postal": "...", "pais": "{codigo}"}}}},
  "receptor": {{"nombre": "...", "nif": "...", "direccion": {{...}}}} o null,
  "lineas": [{{"descripcion": "...", "cantidad": N, "precio_unitario": N, "importe": N}}],
  "base_imponible": N,
  "iva": [{{"porcentaje": N, "base_imponible": N, "cuota": N}}],
  "retencion": {{"porcentaje": N, "base_imponible": N, "cuota": N}} o null,
  "total": N,
  "observaciones": "..." o null,
  "clave_operacion": "..." o null,
  "anomalias": ["codigo_de_anomalia", ...] o []
}}"""

_RETENCION_ES = ('"retencion" solo se usa cuando el documento la indica explícitamente; '
                 'si no aparece, es null. "clave_operacion" solo si el documento la trae; si no, null.')
_RETENCION_EN = ('Use "retencion" only when the document shows withholding explicitly; '
                 'otherwise null. Set "clave_operacion" only if the document carries it; otherwise null.')


_PREFIJO_PAIS = {
    "es": {"ES": "españolas", "UK": "del Reino Unido", "US": "estadounidenses", "DE": "alemanas"},
    "en": {"ES": "from Spain", "UK": "from the United Kingdom", "US": "from the United States", "DE": "from Germany"},
}


def generar_prompt(documento: dict, idioma: str = "es") -> str:
    """Prompt completo para el motor, en el idioma y país del documento."""
    codigo = str(documento.get("pais", "ES")).upper()
    pais = obtener_pais(codigo)
    idioma_llave = "es" if idioma.lower() == "es" else "en"

    nombres_pais = _PREFIJO_PAIS[idioma_llave][pais.codigo]
    id_fiscal = pais.id_fiscal[idioma_llave]
    impuesto = pais.impuesto[idioma_llave]

    esquema = _ESQUEMA.format(codigo=codigo)
    cuerpo = _ES if idioma_llave == "es" else _EN
    cuerpo = cuerpo.format(
        nombres_pais=nombres_pais,
        id_fiscal=id_fiscal,
        impuesto=impuesto,
        retencion_instruccion=_RETENCION_ES if idioma_llave == "es" else _RETENCION_EN,
        esquema=esquema,
    )
    return cuerpo + json.dumps(documento, ensure_ascii=False, indent=2)
# Dataset

Facturas sintéticas generadas por nosotros, ninguna real. El generador está en el repo y permite producir lotes nuevos con semilla fija.

## Estructura

- `facturas/` — 15 facturas sintéticas (`factura_01.json` … `factura_15.json`). Son el documento que se pasa al motor.
- `esperado/` — la respuesta correcta para cada una, en el contrato de salida.
- `trampas/` — 10 casos trampa (documento + esperado), cada uno con la anomalía que debe detectar el motor.
- `generador.py` — produce facturas normales.
- `generar_trampas.py` — produce los casos trampa.

## Casos normales

Facturas completas con emisor, receptor, una a cinco líneas, IVA al 10% o al 21%. Un 20% de ellas (05, 10, 15) incluyen retención.

## Casos trampa

| id | qué prueba |
|----|------------|
| `albaran_no_factura` | Documento de entrega que no es factura. El motor debe decir `tipo_documento: albaran` y no extraer campos de factura donde no los hay. |
| `factura_sin_cif` | Emisor sin CIF. El motor no debe inventarlo. |
| `factura_sin_numero` | Sin número de factura. |
| `factura_emitida_futuro` | Fecha de emisión en el futuro. |
| `total_incorrecto` | El total impreso no cuadra con base + IVA. |
| `base_no_suma` | La base imponible no coincide con la suma de líneas. |
| `factura_sin_iva` | Factura completa sin desglose de IVA. |
| `receptor_igual_emisor` | Emisor y receptor con el mismo NIF (autofacturación). |
| `linea_cantidad_cero` | Línea con cantidad cero. |
| `cuota_iva_no_cuadra` | Cuota de IVA que no coincide con base × porcentaje. |

## Reglas

- Semilla fija: `42` para normales, `7` para trampas. Regenerar con el mismo comando reproduce el mismo lote.
- Los esperados se consideran la verdad de referencia: no cambiarán salvo error evidente.
- Los campos con `anomalias` en un esperado indican defectos que el motor debe detectar, no solo extraer.
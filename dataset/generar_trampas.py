from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from dataset.generador import dict_a_contrato, generar_factura


def _dump(obj: Any, ruta: Path) -> None:
    ruta.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _base_esperado(factura: dict, anomalias: Optional[list[str]] = None) -> dict:
    return dict_a_contrato(factura, anomalias=anomalias)


def generar_casos_trampa(directorio: Path, semilla: int = 7, pais: str = "ES") -> list[tuple[Path, Path]]:
    direct = directorio / "trampas"
    direct.mkdir(parents=True, exist_ok=True)
    random.seed(semilla)

    producidos: list[tuple[Path, Path]] = []

    def emitir(nombre: str, documento: dict, esperado: dict) -> None:
        doc_path = direct / f"{nombre}_{pais.lower()}_documento.json"
        esp_path = direct / f"{nombre}_{pais.lower()}_esperado.json"
        _dump(documento, doc_path)
        _dump(esperado, esp_path)
        producidos.append((doc_path, esp_path))

    fecha_base = date(2025, 6, 15)

    normal = generar_factura(fecha=fecha_base, pais=pais).model_dump(mode="json")

    emitir(
        "albaran_no_factura",
        {
            "titulo": "ALBARÁN DE ENTREGA Nº 4419",
            "fecha": "15/06/2025",
            "emisor": normal["emisor"],
            "receptor": normal["receptor"],
            "lineas": [
                {
                    "descripcion": "Monitor ultrawide 34 pulgadas",
                    "cantidad": 2,
                    "precio_unitario": 599.00,
                }
            ],
            "nota": "Documento sin validez fiscal. No constituye factura.",
        },
        {
            "tipo_documento": "albaran",
            "anomalias": ["no_es_factura"],
        },
    )

    sin_cif = generar_factura(fecha=fecha_base).model_dump(mode="json")
    del sin_cif["emisor"]["nif"]
    emitir(
        "factura_sin_cif",
        sin_cif,
        _base_esperado(
            sin_cif,
            ["cif_emisor_faltante"],
        ),
    )

    sin_numero = generar_factura(fecha=fecha_base).model_dump(mode="json")
    del sin_numero["numero"]
    emitir(
        "factura_sin_numero",
        sin_numero,
        _base_esperado(
            sin_numero,
            ["numero_factura_faltante"],
        ),
    )

    futuro = date.today() + timedelta(days=60)
    factura_futura = generar_factura(fecha=futuro).model_dump(mode="json")
    emitir(
        "factura_emitida_futuro",
        factura_futura,
        _base_esperado(
            factura_futura,
            ["fecha_emision_futura"],
        ),
    )

    total_mal = generar_factura(fecha=fecha_base).model_dump(mode="json")
    total_mal["total"] = round(total_mal["total"] * 1.5, 2)
    total_mal["_observacion"] = "El total impreso no coincide con base + IVA"
    emitir(
        "total_incorrecto",
        total_mal,
        _base_esperado(total_mal, ["total_no_cuadra"]),
    )

    base_mal = generar_factura(fecha=fecha_base).model_dump(mode="json")
    base_mal["base_imponible"] = round(base_mal["base_imponible"] + 1.0, 2)
    base_mal["_observacion"] = "La base impresa no coincide con la suma de líneas"
    # Recalcular iva y total para que el propio documento sea coherente por fuera
    base_mal["iva"][0]["base_imponible"] = base_mal["base_imponible"]
    base_mal["iva"][0]["cuota"] = round(base_mal["base_imponible"] * base_mal["iva"][0]["porcentaje"] / 100, 2)
    base_mal["total"] = round(base_mal["base_imponible"] + base_mal["iva"][0]["cuota"], 2)
    emitir(
        "base_no_suma",
        base_mal,
        _base_esperado(base_mal, ["base_imponible_no_cuadra"]),
    )

    sin_iva = generar_factura(fecha=fecha_base).model_dump(mode="json")
    sin_iva["total"] = sin_iva["base_imponible"]
    sin_iva["iva"] = []
    sin_iva["_observacion"] = "Factura completa sin desglose de IVA"
    emitir(
        "factura_sin_iva",
        sin_iva,
        _base_esperado(
            sin_iva,
            ["iva_faltante"],
        ),
    )

    receptor_emisor = generar_factura(fecha=fecha_base).model_dump(mode="json")
    receptor_emisor["receptor"]["nif"] = receptor_emisor["emisor"]["nif"]
    receptor_emisor["_observacion"] = "El receptor tiene el mismo NIF que el emisor"
    emitir(
        "receptor_igual_emisor",
        receptor_emisor,
        _base_esperado(
            receptor_emisor,
            ["receptor_igual_emisor"],
        ),
    )

    cantidad_cero = generar_factura(fecha=fecha_base).model_dump(mode="json")
    cantidad_cero["lineas"].append(
        {
            "descripcion": "Cable HDMI 2.1 3m",
            "cantidad": 0,
            "precio_unitario": 18.50,
            "importe": 0.00,
        }
    )
    cantidad_cero["_observacion"] = "Línea con cantidad cero incluida"
    emitir(
        "linea_cantidad_cero",
        cantidad_cero,
        _base_esperado(
            cantidad_cero,
            ["linea_cantidad_invalida"],
        ),
    )

    cuota_mal = generar_factura(fecha=fecha_base).model_dump(mode="json")
    cuota_mal["iva"][0]["cuota"] = round(cuota_mal["iva"][0]["cuota"] + 10, 2)
    cuota_mal["total"] = round(cuota_mal["base_imponible"] + cuota_mal["iva"][0]["cuota"], 2)
    cuota_mal["_observacion"] = "La cuota de IVA impresa no coincide con base * 21%"
    emitir(
        "cuota_iva_no_cuadra",
        cuota_mal,
        _base_esperado(
            cuota_mal,
            ["cuota_iva_no_cuadra"],
        ),
    )

    return producidos


if __name__ == "__main__":
    from dataset.generador import PAISES
    base = Path(__file__).resolve().parent
    total = 0
    for codigo in PAISES:
        archivos = generar_casos_trampa(base, semilla=7, pais=codigo)
        total += len(archivos)
        print(f"  {codigo}: {len(archivos)} casos trampa")
    print(f"Generados {total} casos trampa totales.")
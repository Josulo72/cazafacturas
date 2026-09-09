from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from backend.nucleo.esquema import (
    DesgloseIVA,
    DesgloseRetencion,
    Direccion,
    Empresa,
    Factura,
    LineaFactura,
    TipoFactura,
)
from backend.nucleo.paises import PAISES

EMPRESAS = [
    ("Tecnología del Sur S.L.", "B12345674", "Calle Gran Vía 42, Madrid"),
    ("Alimentos del Norte S.A.", "A87654323", "Avda. de la Industria 15, Bilbao"),
    ("Suministros Express", "B11223344", "Polígono Las Merindades, Valladolid"),
    ("Consultoría Integrada S.L.", "B55667786", "Paseo de Recoletos 8, Madrid"),
    ("Materiales de Construcción Hermanos", "A99887762", "Ctra. de Barcelona km 12, Valencia"),
]

PRODUCTOS = [
    ("Licencia software anual", 450.00),
    ("Servicio de hosting mensual", 29.99),
    ("Pack de memorias RAM 32GB", 89.50),
    ("Monitor ultrawide 34 pulgadas", 599.00),
    ("Teclado mecánico inalámbrico", 129.99),
    ("Disco SSD 2TB", 179.00),
    ("Ratón ergonómico vertical", 69.95),
    ("Cable HDMI 2.1 3m", 18.50),
    ("Webcam 4K con micrófono", 149.00),
    ("Altavoces de escritorio stereo", 79.99),
    ("Silla ergonómica de oficina", 349.00),
    ("Portátil ThinkPad X1 Carbon", 1899.00),
    ("Impresora láser monocromática", 249.00),
    ("NAS con 4 bahías", 499.00),
    ("Switch de red gestionable 24 puertos", 189.00),
]

CIUDADES = [
    ("Madrid", "Madrid", "28001"),
    ("Barcelona", "Barcelona", "08001"),
    ("Valencia", "Valencia", "46001"),
    ("Bilbao", "Vizcaya", "48001"),
    ("Sevilla", "Sevilla", "41001"),
    ("Zaragoza", "Zaragoza", "50001"),
    ("Málaga", "Málaga", "29001"),
    ("Murcia", "Murcia", "30001"),
    ("Las Palmas", "Las Palmas", "35001"),
    ("Palma", "Baleares", "07001"),
]


def _cif_es(digitos: str, tipo: str) -> str:
    """Añade el dígito de control a un CIF español."""
    suma = 0
    for i, ch in enumerate(digitos):
        n = int(ch)
        if i % 2 == 0:
            doble = n * 2
            suma += doble // 10 + doble % 10
        else:
            suma += n
    control = (10 - suma % 10) % 10
    # Las sociedades P, Q, R, S, N y W llevan letra; A, B, E y H llevan cifra.
    if tipo in "PQRSNW":
        return f"{tipo}{digitos}{'JABCDEFGHI'[control]}"
    return f"{tipo}{digitos}{control}"


def _vat_uk(digitos: str) -> str:
    """Completa un VAT británico de 9 cifras con control módulo 97."""
    pesos = (8, 7, 6, 5, 4, 3, 2)
    total = sum(int(d) * p for d, p in zip(digitos, pesos))
    control = (97 - total % 97) % 97
    return f"GB{digitos}{control:02d}"


def _ustid_de(digitos: str) -> str:
    """Completa una USt-IdNr. alemana con su control módulo 11."""
    producto = 10
    for ch in digitos:
        suma = (int(ch) + producto) % 10 or 10
        producto = (2 * suma) % 11
    return f"DE{digitos}{(11 - producto) % 10}"


# Prefijos de EIN que el IRS no asigna.
_EIN_NO_ASIGNADOS = {"00", "07", "08", "09", "17", "18", "19",
                     "28", "29", "49", "69", "70", "78", "79", "89"}


def _nif_aleatorio(pais: str = "ES") -> str:
    """Identificador fiscal inventado pero **válido**: el dígito de control
    se calcula, no se sortea. Si no, el propio validador del proyecto
    rechazaría su dataset."""
    cfg = PAISES[pais.upper()]
    if cfg.codigo == "ES":
        tipo = random.choice("ABEHPQRSNW")
        return _cif_es(f"{random.randint(0, 9999999):07d}", tipo)
    if cfg.codigo == "UK":
        return _vat_uk(f"{random.randint(0, 9999999):07d}")
    if cfg.codigo == "US":
        prefijo = random.choice(
            [f"{n:02d}" for n in range(10, 100)
             if f"{n:02d}" not in _EIN_NO_ASIGNADOS]
        )
        return f"{prefijo}-{random.randint(1000000, 9999999)}"
    if cfg.codigo == "DE":
        return _ustid_de(f"{random.randint(0, 99999999):08d}")
    return f"{random.randint(10000000, 99999999)}"


def _direccion_aleatoria(pais: str = "ES") -> Direccion:
    ciudad, provincia, cp = random.choice(CIUDADES)
    calle = f"Calle {random.choice(['Alcalá', 'Serrano', 'Cataluña', 'Fernán Gómez', 'Velázquez'])} {random.randint(1, 200)}"
    return Direccion(calle=calle, ciudad=ciudad, provincia=provincia, codigo_postal=cp, pais=pais.upper())


def _empresa_aleatoria(pais: str = "ES") -> Empresa:
    nombre, nif, direccion_str = random.choice(EMPRESAS)
    ciudad, provincia, cp = random.choice(CIUDADES)
    return Empresa(
        nombre=nombre,
        nif=_nif_aleatorio(pais) if pais.upper() != "ES" else nif,
        direccion=Direccion(
            calle=direccion_str,
            ciudad=ciudad,
            provincia=provincia,
            codigo_postal=cp,
            pais=pais.upper(),
        ),
    )


def generar_numero_serie(pais: str = "ES") -> str:
    year = date.today().year
    serie = random.randint(1, 9999)
    prefijo = PAISES[pais.upper()].codigo if pais.upper() != "ES" else "F"
    return f"{prefijo}/{year}/{serie:04d}"


def _empresa_diferente_a(nif: str, pais: str = "ES") -> Empresa:
    """Empresa aleatoria con NIF distinto al dado (para emisor != receptor)."""
    while True:
        empresa = _empresa_aleatoria(pais)
        if empresa.nif != nif:
            return empresa


def generar_factura(
    *,
    fecha: Optional[date] = None,
    incluir_retencion: bool = False,
    es_simplificada: bool = False,
    pais: str = "ES",
) -> Factura:
    fecha = fecha or date.today()
    num_lineas = random.randint(1, 5)
    productos_elegidos = random.sample(PRODUCTOS, num_lineas)

    lineas = []
    base = 0.0
    for desc, precio_unit in productos_elegidos:
        cantidad = random.randint(1, 10)
        importe = round(cantidad * precio_unit, 2)
        lineas.append(
            LineaFactura(
                descripcion=desc,
                cantidad=cantidad,
                precio_unitario=precio_unit,
                importe=importe,
            )
        )
        base += importe

    base = round(base, 2)
    cfg = PAISES[pais.upper()]
    # tasas de impuesto por país (simplificadas)
    if cfg.codigo == "ES":
        porcentaje_iva = random.choice([4.0, 10.0, 21.0])
    elif cfg.codigo == "UK":
        porcentaje_iva = random.choice([5.0, 20.0])
    elif cfg.codigo == "US":
        # US sales tax varía por estado; usamos una tasa genérica
        porcentaje_iva = random.choice([6.0, 7.0, 8.25, 9.0])
    elif cfg.codigo == "DE":
        porcentaje_iva = random.choice([7.0, 19.0])
    else:
        porcentaje_iva = 21.0
    cuota_iva = round(base * porcentaje_iva / 100, 2)

    retencion = None
    if incluir_retencion and cfg.usa_retencion:
        porcentaje_ret = round(random.uniform(1, 7), 2)
        cuota_ret = round(base * porcentaje_ret / 100, 2)
        retencion = DesgloseRetencion(
            porcentaje=porcentaje_ret,
            base_imponible=base,
            cuota=cuota_ret,
        )

    cuota_ret_val = retencion.cuota if retencion else 0
    total = round(base + cuota_iva - cuota_ret_val, 2)

    emisor = _empresa_aleatoria(pais)
    receptor = (
        _empresa_diferente_a(emisor.nif, pais) if not es_simplificada else None
    )
    tipo = TipoFactura.SIMPLIFICADA if es_simplificada else TipoFactura.COMPLETA

    return Factura(
        tipo=tipo,
        pais=cfg.codigo,
        numero=generar_numero_serie(pais),
        fecha_emision=fecha,
        fecha_vencimiento=fecha + timedelta(days=30),
        emisor=emisor,
        receptor=receptor,
        lineas=lineas,
        base_imponible=base,
        iva=[DesgloseIVA(porcentaje=porcentaje_iva, base_imponible=base, cuota=cuota_iva)],
        retencion=retencion,
        total=total,
    )


def dict_a_contrato(
    datos: dict,
    anomalias: list[str] | None = None,
    tipo_documento: str = "factura",
) -> dict:
    """Convierte un dict de factura al contrato de salida que se le pide al motor."""
    resultado = {k: v for k, v in datos.items() if not k.startswith("_")}
    resultado.pop("tipo", None)
    resultado["tipo_documento"] = tipo_documento
    resultado["pais"] = datos.get("pais", "ES")
    resultado["anomalias"] = anomalias or []
    return resultado


def generar_dataset(
    directorio: Path, n: int = 15, semilla: int = 42, pais: str = "ES"
) -> list[tuple[Path, Path]]:
    random.seed(semilla)
    directorio.mkdir(parents=True, exist_ok=True)
    facturas_dir = directorio / "facturas"
    esperado_dir = directorio / "esperado"
    facturas_dir.mkdir(exist_ok=True)
    esperado_dir.mkdir(exist_ok=True)

    generadas = []
    for i in range(1, n + 1):
        fecha_base = date(2025, 1, 1) + timedelta(days=random.randint(0, 364))
        factura = generar_factura(fecha=fecha_base, incluir_retencion=(i % 5 == 0), pais=pais)

        archivo_factura = facturas_dir / f"factura_{pais.lower()}_{i:02d}.json"
        archivo_esperado = esperado_dir / f"factura_{pais.lower()}_{i:02d}.json"

        documento = factura.model_dump(mode="json")
        archivo_factura.write_text(
            json.dumps(documento, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        archivo_esperado.write_text(
            json.dumps(
                dict_a_contrato(documento), indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        generadas.append((archivo_factura, archivo_esperado))

    return generadas


def generar_dataset_multipais(
    directorio_base: Path, n_por_pais: int = 6, semilla: int = 42
) -> None:
    """Genera n casos para cada país soportado."""
    for codigo in PAISES:
        directorio = directorio_base / codigo
        generar_dataset(directorio, n=n_por_pais, semilla=semilla, pais=codigo)
        print(f"  {codigo}: {n_por_pais} facturas en {directorio}")


if __name__ == "__main__":
    from pathlib import Path

    base = Path(__file__).resolve().parent
    # Generar 6 por país para ES, UK, US, DE
    generar_dataset_multipais(base, n_por_pais=6, semilla=42)
    print("Dataset multipaís generado.")

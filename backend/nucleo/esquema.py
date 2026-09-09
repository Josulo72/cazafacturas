from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from backend.nucleo.paises import PAISES


class TipoFactura(str, Enum):
    COMPLETA = "completa"
    SIMPLIFICADA = "simplificada"


class Direccion(BaseModel):
    calle: str
    ciudad: str
    provincia: str
    codigo_postal: str = Field(min_length=2, max_length=12)
    pais: str = "ES"


class Empresa(BaseModel):
    nombre: str
    nif: str
    direccion: Direccion


class LineaFactura(BaseModel):
    descripcion: str
    cantidad: float = Field(gt=0)
    precio_unitario: float = Field(gt=0)
    importe: float = Field(gt=0)

    @field_validator("importe")
    @classmethod
    def importe_cuantidad_precio(cls, v: float, info) -> float:
        cantidad = info.data.get("cantidad")
        precio = info.data.get("precio_unitario")
        if cantidad is not None and precio is not None:
            esperado = round(cantidad * precio, 2)
            if abs(v - esperado) > 0.02:
                raise ValueError(
                    f"Importe {v} no coincide con cantidad*precio ({esperado})"
                )
        return v


class DesgloseIVA(BaseModel):
    porcentaje: float = Field(ge=0, le=100)
    base_imponible: float = Field(ge=0)
    cuota: float = Field(ge=0)


class DesgloseRetencion(BaseModel):
    porcentaje: float = Field(ge=0, le=100)
    base_imponible: float = Field(ge=0)
    cuota: float = Field(ge=0)


class Factura(BaseModel):
    tipo: TipoFactura = TipoFactura.COMPLETA
    pais: str = "ES"
    numero: str
    fecha_emision: date
    fecha_vencimiento: Optional[date] = None
    emisor: Empresa
    receptor: Optional[Empresa] = None
    lineas: list[LineaFactura] = Field(min_length=1)
    base_imponible: float = Field(ge=0)
    iva: list[DesgloseIVA] = Field(min_length=1)
    retencion: Optional[DesgloseRetencion] = None
    total: float = Field(gt=0)
    observaciones: Optional[str] = None
    clave_operacion: Optional[str] = None

    @field_validator("pais")
    @classmethod
    def pais_conocido(cls, v: str) -> str:
        if v.upper() not in PAISES:
            raise ValueError(f"País no soportado: {v}. Válidos: {', '.join(sorted(PAISES))}")
        return v.upper()

    @field_validator("receptor")
    @classmethod
    def receptor_obligatorio_si_completa(cls, v, info) -> Optional[Empresa]:
        tipo = info.data.get("tipo")
        if tipo == TipoFactura.COMPLETA and v is None:
            raise ValueError("Factura completa requiere receptor")
        return v

    @field_validator("base_imponible")
    @classmethod
    def base_coherente_con_lineas(cls, v: float, info) -> float:
        lineas = info.data.get("lineas")
        if lineas:
            suma = round(sum(l.importe for l in lineas), 2)
            if abs(v - suma) > 0.02:
                raise ValueError(
                    f"Base imponible {v} no coincide con suma de líneas ({suma})"
                )
        return v

    @field_validator("total")
    @classmethod
    def total_coherente(cls, v: float, info) -> float:
        base = info.data.get("base_imponible")
        iva_list = info.data.get("iva")
        retencion = info.data.get("retencion")
        if base is not None and iva_list:
            cuotas_iva = sum(i.cuota for i in iva_list)
            cuota_ret = retencion.cuota if retencion else 0
            esperado = round(base + cuotas_iva - cuota_ret, 2)
            if abs(v - esperado) > 0.02:
                raise ValueError(
                    f"Total {v} no coincide con base+iva-retencion ({esperado})"
                )
        return v

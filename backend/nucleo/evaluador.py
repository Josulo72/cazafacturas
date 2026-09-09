from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from backend.nucleo.paises import obtener_pais


class EstadoCampo(str, Enum):
    ACIERTO = "acierto"
    FALLO = "fallo"
    INVENCION = "invencion"
    AUSENTE = "ausente"


@dataclass
class ResultadoCampo:
    campo: str
    esperado: Any = None
    obtenido: Any = None
    estado: EstadoCampo = EstadoCampo.AUSENTE


@dataclass
class ResultadoFactura:
    aciertos: list[ResultadoCampo] = field(default_factory=list)
    fallos: list[ResultadoCampo] = field(default_factory=list)
    invenciones: list[ResultadoCampo] = field(default_factory=list)

    @property
    def total_campos(self) -> int:
        return len(self.aciertos) + len(self.fallos) + len(self.invenciones)

    @property
    def precision(self) -> float:
        total = self.total_campos
        if total == 0:
            return 0.0
        return round(len(self.aciertos) / total, 4)

    @property
    def tasa_invencion(self) -> float:
        total = len(self.invenciones)
        if total == 0:
            return 0.0
        denominador = len(self.aciertos) + len(self.fallos) + total
        return round(total / denominador, 4)


@dataclass
class MetadatosEjecucion:
    nombre_motor: str
    modelo: str
    temperatura: float
    segundos: float
    cacheado: bool = False


@dataclass
class ResultadoEvaluacion:
    factura: str
    esperado: dict
    obtenido: dict
    campos: list[ResultadoCampo] = field(default_factory=list)
    fallos_validacion: list[str] = field(default_factory=list)
    metadatos: Optional[MetadatosEjecucion] = None

    @property
    def aciertos(self) -> list[ResultadoCampo]:
        return [c for c in self.campos if c.estado == EstadoCampo.ACIERTO]

    @property
    def fallos(self) -> list[ResultadoCampo]:
        return [c for c in self.campos if c.estado == EstadoCampo.FALLO]

    @property
    def invenciones(self) -> list[ResultadoCampo]:
        return [c for c in self.campos if c.estado == EstadoCampo.INVENCION]

    @property
    def precision(self) -> float:
        relevantes = [c for c in self.campos if c.estado != EstadoCampo.INVENCION]
        if not relevantes:
            return 0.0
        return round(
            sum(1 for c in relevantes if c.estado == EstadoCampo.ACIERTO)
            / len(relevantes),
            4,
        )

    @property
    def tasa_invencion(self) -> float:
        relevantes = [
            c
            for c in self.campos
            if c.estado in (EstadoCampo.ACIERTO, EstadoCampo.FALLO)
        ]
        total_inventados = len(self.invenciones)
        if relevantes:
            return round(total_inventados / (len(relevantes) + total_inventados), 4)
        return round(1.0 if total_inventados else 0.0, 4)


def _normalizar_numero(valor: Any) -> Optional[float]:
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        limpio = valor.strip().replace(",", ".")
        limpio = re.sub(r"[^\d.-]", "", limpio)
        if not limpio:
            return None
        try:
            return float(limpio)
        except ValueError:
            return None
    return None


def _normalizar_texto(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    return re.sub(r"\s+", " ", str(valor).strip().lower())


def _normalizar_fecha(valor: Any, pais: str = "ES") -> Optional[str]:
    if valor is None or valor == "":
        return None
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    texto = _normalizar_texto(valor) or ""
    formatos = obtener_pais(pais).fecha_formatos
    for formato in formatos:
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    return texto


def _normalizar_codigo(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    return re.sub(r"[\s\-/.]+", "", str(valor)).upper()


def _coinciden_de_dicts(esperado: dict, obtenido: dict, pais: str) -> bool:
    if set(esperado.keys()) != set(obtenido.keys()):
        return False
    return all(_coinciden(v, obtenido[k], pais) for k, v in esperado.items())


def _coinciden(esperado: Any, obtenido: Any, pais: str = "ES") -> bool:
    if esperado is None:
        return False
    if isinstance(esperado, list) or isinstance(obtenido, list):
        if isinstance(esperado, list) and isinstance(obtenido, list):
            if len(esperado) != len(obtenido):
                return False
            if all(isinstance(x, dict) for x in esperado) and all(
                isinstance(x, dict) for x in obtenido
            ):
                return all(
                    _coinciden_de_dicts(e, o, pais) for e, o in zip(esperado, obtenido)
                )
            e = [_normalizar_texto(x) for x in esperado]
            o = [_normalizar_texto(x) for x in obtenido]
            return sorted(e) == sorted(o)
    if isinstance(esperado, (int, float)) or isinstance(obtenido, (int, float)):
        e = _normalizar_numero(esperado)
        o = _normalizar_numero(obtenido)
        if e is not None and o is not None:
            return abs(e - o) <= 0.02
        return str(e) == str(o)
    if isinstance(esperado, str):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", esperado.strip()):
            return _normalizar_fecha(esperado, pais) == _normalizar_fecha(obtenido, pais)
        e_codigo = _normalizar_codigo(esperado)
        o_codigo = _normalizar_codigo(obtenido)
        if e_codigo and o_codigo and e_codigo == o_codigo:
            return True
        e_txt = _normalizar_texto(esperado)
        o_txt = _normalizar_texto(obtenido)
        return e_txt == o_txt
    return esperado == obtenido


CAMPOS_ANIDADOS = ("direccion", "emisor", "receptor")


def _es_vacio(valor: Any) -> bool:
    if valor is None:
        return True
    if isinstance(valor, str):
        return not valor.strip()
    if isinstance(valor, (list, dict)):
        return len(valor) == 0
    return False


def _aplanar_esperado(esperado: dict, prefijo: str = "") -> dict[str, Any]:
    plano = {}
    for clave, valor in esperado.items():
        clave_con_prefijo = f"{prefijo}.{clave}" if prefijo else clave
        if isinstance(valor, dict):
            plano.update(_aplanar_esperado(valor, clave_con_prefijo))
        else:
            plano[clave_con_prefijo] = valor
    return plano


def evaluar_factura(
    esperado: dict,
    obtenido: dict,
) -> ResultadoEvaluacion:
    factura_nombre = str(esperado.get("_factura", ""))
    pais = str(esperado.get("pais", "ES"))
    plano_esperado = _aplanar_esperado(esperado)
    plano_obtenido = _aplanar_esperado(obtenido)

    campos: list[ResultadoCampo] = []

    for campo, valor_esperado in plano_esperado.items():
        if campo.startswith("_"):
            continue
        if _es_vacio(valor_esperado):
            if campo in plano_obtenido and not _es_vacio(plano_obtenido.get(campo)):
                campos.append(
                    ResultadoCampo(
                        campo=campo,
                        esperado=valor_esperado,
                        obtenido=plano_obtenido.get(campo),
                        estado=EstadoCampo.INVENCION,
                    )
                )
            continue

        presente = campo in plano_obtenido
        valor_obtenido = plano_obtenido.get(campo)

        if presente and not _es_vacio(valor_obtenido):
            estado = (
                EstadoCampo.ACIERTO
                if _coinciden(valor_esperado, valor_obtenido, pais)
                else EstadoCampo.FALLO
            )
        elif presente and _es_vacio(valor_obtenido):
            estado = EstadoCampo.FALLO
        else:
            estado = EstadoCampo.FALLO

        campos.append(
            ResultadoCampo(
                campo=campo,
                esperado=valor_esperado,
                obtenido=valor_obtenido,
                estado=estado,
            )
        )

    for campo, valor_obtenido in plano_obtenido.items():
        if campo.startswith("_") or campo in plano_esperado:
            continue
        if _es_vacio(valor_obtenido):
            continue
        campos.append(
            ResultadoCampo(
                campo=campo,
                esperado=None,
                obtenido=valor_obtenido,
                estado=EstadoCampo.INVENCION,
            )
        )

    return ResultadoEvaluacion(
        factura=factura_nombre,
        esperado=esperado,
        obtenido=obtenido,
        campos=campos,
    )


def evaluar_respuesta_json(
    respuesta_texto: str,
    esperado: dict,
    factura_nombre: str = "",
) -> ResultadoEvaluacion:
    obtenido: dict = {}
    fallos_validacion: list[str] = []
    texto = respuesta_texto.strip()

    try:
        bloc = re.search(r"```(?:json)?\s*(.*?)```", texto, re.DOTALL)
        if bloc:
            texto = bloc.group(1)
        obtenido = json.loads(texto)
        if not isinstance(obtenido, dict):
            fallos_validacion.append("La respuesta no es un objeto JSON")
            obtenido = {}
    except json.JSONDecodeError as e:
        fallos_validacion.append(f"JSON inválido: {e}")
        obtenido = {"_error": respuesta_texto}
        obtenido["_factura"] = factura_nombre

    resultado = evaluar_factura(esperado, obtenido)
    resultado.fallos_validacion = fallos_validacion
    resultado.factura = factura_nombre or resultado.factura
    return resultado
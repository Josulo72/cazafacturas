from __future__ import annotations

from typing import Callable

from backend.api.motores import CatalogoMotores
from backend.nucleo.cache import CacheResultados, hash_contenido
from backend.nucleo.dataset import Caso
from backend.nucleo.evaluador import (
    MetadatosEjecucion,
    ResultadoEvaluacion,
    evaluar_respuesta_json,
)
from backend.nucleo.motores.base import EstadoMotor, RespuestaMotor
from backend.nucleo.motores.prompt import PROMPT_VERSION


def documento_publico(documento: dict) -> dict:
    """Quita los campos internos del banco (prefijo _) antes de enviar al motor."""
    return {k: v for k, v in documento.items() if not k.startswith("_")}


def ejecutar_caso(
    caso: Caso,
    id_motor: str,
    catalogo: CatalogoMotores,
    cache: CacheResultados | None = None,
    usar_cache: bool = True,
    prompt_extra: str = "",
    idioma: str = "es",
) -> ResultadoEvaluacion:
    motor = catalogo.get(id_motor)
    info = motor.detectar()
    if info.estado != EstadoMotor.DISPONIBLE:
        raise RuntimeError(
            f"Motor '{id_motor}' no disponible: {info.detalle or info.estado.value}"
        )

    documento = documento_publico(caso.documento)
    modelo = info.modelo or ""
    clave = hash_contenido(
        documento,
        f"{id_motor}:{modelo}",
        prompt_extra,
        version_prompt=PROMPT_VERSION,
        idioma=idioma,
    )
    try:
        if usar_cache and cache is not None:
            guardado = cache.obtener(clave)
            if guardado is not None:
                texto = guardado["respuesta"]
                resp = RespuestaMotor(
                    texto=texto,
                    segundos=float(guardado["segundos"]),
                    cacheado=True,
                )
            else:
                resp = motor.procesar(documento, prompt_extra=prompt_extra, idioma=idioma)
                cache.guardar(clave, resp.texto, resp.segundos)
        else:
            resp = motor.procesar(documento, prompt_extra=prompt_extra, idioma=idioma)
    except RuntimeError as e:
        resultado = ResultadoEvaluacion(
            factura=caso.id,
            esperado=caso.esperado,
            obtenido={},
            fallos_validacion=[str(e)],
        )
        return resultado

    resultado = evaluar_respuesta_json(
        resp.texto, caso.esperado, factura_nombre=caso.id
    )
    resultado.metadatos = MetadatosEjecucion(
        nombre_motor=id_motor,
        modelo=info.modelo or "",
        temperatura=0.0,
        segundos=resp.segundos,
        cacheado=resp.cacheado,
    )
    return resultado


def ejecutar_dataset(
    lista_casos: list[Caso],
    id_motor: str,
    catalogo: CatalogoMotores,
    cache: CacheResultados,
    progress: Callable[[int, int, str, str], None] | None = None,
    prompt_extra: str = "",
    registrar: Callable[[ResultadoEvaluacion], None] | None = None,
    idioma: str = "es",
) -> list[ResultadoEvaluacion]:
    resultados: list[ResultadoEvaluacion] = []
    for i, caso in enumerate(lista_casos):
        if progress:
            progress(i, len(lista_casos), caso.id, "analizando")
        resultado = ejecutar_caso(
            caso,
            id_motor,
            catalogo,
            cache=cache,
            prompt_extra=prompt_extra,
            idioma=idioma,
        )
        if registrar:
            registrar(resultado)
        resultados.append(resultado)
        if progress:
            estado = "resuelta" if not resultado.fallos else "fallada"
            progress(i + 1, len(lista_casos), caso.id, estado)
    return resultados
"""Ejecutor de Archy (pasos "Actuar" y "deshacer").

Mueve y renombra SOLO las acciones aprobadas, una por una:
1. el origen y el destino pasan otra vez por el guardián;
2. el archivo debe seguir siendo el mismo que se planeó (mismo SHA-256);
3. nunca se sobrescribe: si el destino ya existe, se usa `_2`, `_3`...;
4. si algo falla (archivo abierto, sin permisos...), se salta y se sigue;
5. todo queda en la bitácora.

En simulación no se toca nada: solo se registra lo que pasaría.
**Aquí no existe ninguna función para borrar.** Deshacer regresa cada archivo
a su lugar solo si su huella coincide y el lugar original está libre. Las
carpetas que se hayan creado se quedan (vacías), porque Archy no borra nada.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .bitacora import Bitacora
from .escaner import calcular_sha256
from .guardian import AccesoDenegado, Guardian
from .planificador import Accion, con_sufijo

__all__ = ["Resultado", "aplicar", "deshacer", "MOVIDO", "SIMULADO", "OMITIDO", "ERROR"]

MOVIDO, SIMULADO, OMITIDO, ERROR = "movido", "simulado", "omitido", "error"
MAX_SUFIJO = 999


@dataclass(frozen=True)
class Resultado:
    origen: str
    destino: str | None
    estado: str          # movido | simulado | omitido | error
    detalle: str


def _relativa(guardian: Guardian, ruta: Path) -> str:
    return ruta.relative_to(guardian.raiz).as_posix()


def _destino_libre(guardian: Guardian, destino_relativo: str) -> Path:
    """Primer nombre libre (`_2`, `_3`...) para no sobrescribir nunca."""
    relativo = PurePosixPath(destino_relativo)
    for n in range(1, MAX_SUFIJO + 1):
        candidato = guardian.validar(str(relativo.parent / con_sufijo(relativo.name, n)))
        if not candidato.exists():
            return candidato
    raise OSError(f"no hay un nombre libre para {destino_relativo}")


def _mover(origen: Path, destino: Path) -> None:
    """Mueve sin sobrescribir. Crea las carpetas que falten.

    Se usa `os.rename` y no `shutil.move`: dentro de Trabajos (un mismo disco)
    es lo mismo, pero `shutil.move` entre discos copia y luego BORRA el
    original, y Archy no borra nunca. En Windows `os.rename` además falla si
    el destino ya existe.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():           # se revisa otra vez justo antes de mover
        raise FileExistsError(f"ya existe {destino.name}")
    os.rename(origen, destino)


def _validar(guardian: Guardian, bitacora: Bitacora | None, ruta: str) -> Path:
    try:
        return guardian.validar(ruta)
    except AccesoDenegado as error:
        if bitacora is not None:
            bitacora.registrar_bloqueo(ruta, error.motivo)
        raise


def aplicar(acciones: list[Accion], guardian: Guardian, bitacora: Bitacora | None,
            simular: bool = True) -> tuple[int | None, list[Resultado]]:
    """Ejecuta las acciones aprobadas. Devuelve (id de la operación en la bitácora, resultados)."""
    aprobadas = [a for a in acciones if a.aprobada]
    operacion = (bitacora.iniciar_operacion("aplicar", simular, str(guardian.raiz))
                 if bitacora is not None and aprobadas else None)
    resultados = []
    for orden, accion in enumerate(aprobadas, start=1):
        resultado = _aplicar_una(accion, guardian, bitacora, simular)
        resultados.append(resultado)
        if operacion is not None:
            bitacora.registrar_movimiento(
                operacion, orden, accion.origen, resultado.destino, resultado.estado, resultado.detalle,
                sha256=accion.sha256, materia=accion.materia, tipo=accion.tipo,
                confianza=accion.confianza, motivo=accion.motivo)
    return operacion, resultados


def _aplicar_una(accion: Accion, guardian: Guardian, bitacora: Bitacora | None, simular: bool) -> Resultado:
    try:
        origen = _validar(guardian, bitacora, accion.origen)
        if not origen.is_file():
            return Resultado(accion.origen, None, OMITIDO, "ya no está en su lugar")
        if accion.sha256 and calcular_sha256(origen) != accion.sha256:
            return Resultado(accion.origen, None, OMITIDO, "cambió desde que se hizo el plan; vuelve a pedir el plan")
        _validar(guardian, bitacora, accion.destino)
        destino = _destino_libre(guardian, accion.destino)
        relativo = _relativa(guardian, destino)
        nota = "" if relativo == accion.destino else f" (ya existía {accion.destino}: no se sobrescribió)"
        if simular:
            return Resultado(accion.origen, relativo, SIMULADO, "se movería" + nota)
        _mover(origen, destino)
        if accion.sha256 and calcular_sha256(destino) != accion.sha256:
            return Resultado(accion.origen, relativo, ERROR, "la huella no coincide después de mover")
        return Resultado(accion.origen, relativo, MOVIDO, "movido" + nota)
    except AccesoDenegado as error:
        return Resultado(accion.origen, None, ERROR, f"bloqueado por el guardián: {error.motivo}")
    except OSError as error:
        return Resultado(accion.origen, None, ERROR, f"no se pudo mover (¿archivo abierto?): {error}")


def deshacer(bitacora: Bitacora, guardian: Guardian, id_operacion: int) -> tuple[int | None, list[Resultado]]:
    """Regresa a su lugar los archivos de una operación, en orden inverso."""
    operacion = bitacora.operacion(id_operacion)
    if operacion is None or not operacion.deshacible:
        return None, [Resultado("", None, OMITIDO, "esa operación no se puede deshacer (no existe, "
                                "fue una simulación o ya se deshizo)")]
    if operacion.raiz != str(guardian.raiz):
        return None, [Resultado("", None, OMITIDO, f"esa operación fue en otra carpeta ({operacion.raiz})")]

    nueva = bitacora.iniciar_operacion("deshacer", False, str(guardian.raiz), deshace=id_operacion)
    movidos = [m for m in bitacora.movimientos(id_operacion) if m.estado == MOVIDO]
    resultados, errores = [], 0
    for orden, m in enumerate(reversed(movidos), start=1):
        resultado = _regresar(m.destino, m.origen, m.sha256, guardian, bitacora)
        errores += resultado.estado == ERROR
        resultados.append(resultado)
        bitacora.registrar_movimiento(nueva, orden, m.destino, m.origen, resultado.estado, resultado.detalle,
                                      sha256=m.sha256, materia=m.materia, tipo=m.tipo)
    if not errores:
        bitacora.marcar_deshecha(id_operacion, nueva)
    return nueva, resultados


def _regresar(actual: str, original: str, sha256: str | None, guardian: Guardian,
              bitacora: Bitacora) -> Resultado:
    try:
        desde = _validar(guardian, bitacora, actual)
        hacia = _validar(guardian, bitacora, original)
        if not desde.is_file():
            if hacia.is_file() and sha256 and calcular_sha256(hacia) == sha256:
                return Resultado(actual, original, OMITIDO, "ya estaba en su lugar original")
            return Resultado(actual, original, ERROR, "ya no está donde Archy lo dejó")
        if sha256 and calcular_sha256(desde) != sha256:
            return Resultado(actual, original, ERROR, "cambió después de moverlo; no se regresa")
        if hacia.exists():
            return Resultado(actual, original, ERROR, "su lugar original ya está ocupado; no se sobrescribe")
        _mover(desde, hacia)
        return Resultado(actual, original, MOVIDO, "regresado")
    except AccesoDenegado as error:
        return Resultado(actual, original, ERROR, f"bloqueado por el guardián: {error.motivo}")
    except OSError as error:
        return Resultado(actual, original, ERROR, f"no se pudo regresar (¿archivo abierto?): {error}")

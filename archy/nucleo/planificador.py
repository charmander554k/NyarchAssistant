"""Planificador de Archy (paso "Planear").

Convierte la clasificación en un plan: un renglón por archivo con su destino
`Materia/Tipo/Nombre` (o `_Por revisar/Nombre`). El plan se puede editar
(aprobar o no cada archivo, cambiar la materia, renombrar o no) y después de
cada cambio se vuelven a calcular los destinos con `asignar_destinos`.

Reglas:
- Nunca se propone sobrescribir: si el destino ya existe, o dos archivos
  irían al mismo lugar, se agrega `_2`, `_3`...
- Archivos con el mismo contenido (SHA-256) se marcan como duplicados y no
  se aprueban por defecto (Archy nunca borra; decide el estudiante).
- Aprobados por defecto: solo los que el clasificador propone mover con
  confianza. Los que van con advertencia o a _Por revisar quedan sin marcar.
- `permitir_renombrar`: nunca -> no se renombra; preguntar -> se propone y el
  estudiante puede quitarlo; siempre -> se renombra si hay nombre propuesto.

Solo calcula: no toca ningún archivo.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Iterable

from .clasificador import MOVER, REVISAR
from .configuracion import Config
from .escaner import ArchivoEscaneado
from .reporte import FilaReporte

__all__ = ["Accion", "Plan", "crear_plan", "asignar_destinos", "con_sufijo", "resumen_plan"]


@dataclass
class Accion:
    origen: str                 # ruta relativa actual (con "/")
    nombre_original: str
    nombre_propuesto: str       # nombre si se renombra (igual al original si no hay propuesta)
    tipo: str
    materia: str                # materia elegida o carpeta de dudas (editable)
    materia_propuesta: str      # lo que propuso el clasificador
    decision: str               # mover | advertir | revisar
    confianza: float
    motivo: str
    sha256: str
    aprobada: bool = False      # editable
    renombrar: bool = False     # editable (si puede_renombrar)
    puede_renombrar: bool = False
    duplicado_de: str | None = None
    destino: str = ""           # ruta relativa calculada
    nota: str | None = None     # ej. "el destino ya existe: se usa _2"

    @property
    def nombre_final(self) -> str:
        return self.nombre_propuesto if (self.renombrar and self.puede_renombrar) else self.nombre_original


@dataclass
class Plan:
    acciones: list[Accion] = field(default_factory=list)

    @property
    def aprobadas(self) -> list[Accion]:
        return [a for a in self.acciones if a.aprobada]


def con_sufijo(nombre: str, n: int) -> str:
    """'Tarea.py', 2 -> 'Tarea_2.py' (regla: nunca sobrescribir)."""
    ruta = PurePosixPath(nombre)
    return f"{ruta.stem}_{n}{ruta.suffix}" if n > 1 else nombre


def _carpeta_destino(accion: Accion, config: Config) -> str:
    if accion.materia == config.carpeta_dudas:
        return config.carpeta_dudas
    return f"{accion.materia}/{accion.tipo}"


def asignar_destinos(plan: Plan, config: Config, ocupadas: Iterable[str]) -> Plan:
    """Calcula el destino de cada acción sin pisar archivos existentes ni a otras acciones.

    `ocupadas`: rutas relativas que ya existen en Trabajos. Se comparan sin
    mayúsculas (en Windows y en /mnt/c "Tarea.py" y "tarea.py" son el mismo).
    Las aprobadas reservan su destino primero, para que una no aprobada nunca
    cambie el nombre de una aprobada.
    """
    reservadas = {r.casefold() for r in ocupadas}
    orden = sorted(plan.acciones, key=lambda a: not a.aprobada)   # estable: aprobadas primero
    for accion in orden:
        carpeta = _carpeta_destino(accion, config)
        base = accion.nombre_final
        n = 1
        while f"{carpeta}/{con_sufijo(base, n)}".casefold() in reservadas:
            n += 1
        accion.destino = f"{carpeta}/{con_sufijo(base, n)}"
        reservadas.add(accion.destino.casefold())
        notas = []
        if n > 1:
            notas.append(f"ya existe un archivo con ese nombre: se usa {con_sufijo(base, n)}")
        if accion.duplicado_de:
            notas.append(f"mismo contenido que {accion.duplicado_de}")
        accion.nota = "; ".join(notas) or None
    return plan


def crear_plan(filas: list[FilaReporte], archivos: Iterable[ArchivoEscaneado], config: Config,
               ocupadas: Iterable[str] | None = None) -> Plan:
    """Arma el plan a partir de la clasificación.

    `archivos`: todo lo que devolvió el escáner (para los hashes y para
    detectar duplicados de archivos que ya estaban organizados).
    `ocupadas`: rutas que ya existen; por defecto, las de `archivos`.
    """
    archivos = list(archivos)
    por_ruta = {a.ruta_relativa: a for a in archivos}
    if ocupadas is None:
        ocupadas = [a.ruta_relativa for a in archivos]
    hash_visto: dict[str, str] = {a.sha256: a.ruta_relativa for a in archivos if a.ubicacion != "suelto"}

    plan = Plan()
    for fila in filas:
        archivo = por_ruta.get(fila.ruta_relativa)
        sha = archivo.sha256 if archivo else ""
        duplicado = hash_visto.get(sha) if sha else None
        if sha and duplicado is None:
            hash_visto[sha] = fila.ruta_relativa
        puede = (config.permitir_renombrar != "nunca" and fila.renombrar
                 and fila.nombre_propuesto != fila.nombre)
        plan.acciones.append(Accion(
            origen=fila.ruta_relativa, nombre_original=fila.nombre,
            nombre_propuesto=fila.nombre_propuesto if puede else fila.nombre,
            tipo=fila.tipo, materia=fila.materia, materia_propuesta=fila.materia,
            decision=fila.decision, confianza=fila.confianza, motivo=fila.motivo, sha256=sha,
            aprobada=fila.decision == MOVER and duplicado is None,
            renombrar=puede and fila.decision != REVISAR,
            puede_renombrar=puede, duplicado_de=duplicado,
        ))
    return asignar_destinos(plan, config, ocupadas)


def resumen_plan(plan: Plan, config: Config) -> str:
    """Texto corto para el modelo (solo datos)."""
    if not plan.acciones:
        return "No hay archivos sin organizar en la carpeta Trabajos."
    destinos = Counter(a.materia for a in plan.acciones)
    return "\n".join([
        f"Plan con {len(plan.acciones)} archivos sin organizar; {len(plan.aprobadas)} marcados para mover "
        "(el estudiante revisa, edita y aplica con los botones de la tarjeta).",
        "Por materia: " + ", ".join(f"{m}: {n}" for m, n in destinos.most_common()) + ".",
        f"Con advertencia: {sum(a.decision != MOVER and a.materia != config.carpeta_dudas for a in plan.acciones)}. "
        f"Renombres propuestos: {sum(a.renombrar for a in plan.acciones)}. "
        f"Duplicados: {sum(a.duplicado_de is not None for a in plan.acciones)}.",
    ])

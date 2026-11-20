"""Reportes de Archy para las herramientas del chat (pasos "Razonar" y "Planear").

Une escáner, extractor, clasificador y nombrador, y prepara dos salidas:
- filas con todo el detalle, para la tabla que ve el estudiante en el chat;
- un resumen corto en texto, para el modelo (Qwen no tiene que repetir la tabla).

También mide el clasificador contra un archivo de etiquetas (solo en modo
desarrollo). Nada de aquí mueve, renombra ni escribe archivos, y el texto de
los archivos nunca sale de aquí, salvo un extracto corto en `ver_archivo`.
"""

from __future__ import annotations

import csv
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .clasificador import MOVER, REVISAR, ADVERTIR, Clasificacion, Clasificador
from .configuracion import Config
from .escaner import ArchivoEscaneado
from .extractor import Extraccion, extraer
from .guardian import Guardian
from .nombrador import proponer_nombre, validar_nombre

__all__ = [
    "FilaReporte", "Medicion", "clasificar_archivos", "resumen_clasificacion",
    "buscar_archivo", "leer_etiquetas", "archivos_del_dataset", "medir", "resumen_medicion",
    "TEXTO_DECISION",
]

TEXTO_DECISION = {MOVER: "se propone mover", ADVERTIR: "se propone con advertencia",
                  REVISAR: "va a _Por revisar"}
MAX_EN_RESUMEN = 8        # archivos que se nombran en el resumen para el modelo
AVISO_MODELO = "el modelo no respondió"

Progreso = Callable[[int, int], None]


@dataclass(frozen=True)
class FilaReporte:
    ruta_relativa: str
    nombre: str
    tipo: str
    materia: str               # materia propuesta o carpeta de dudas
    confianza: float
    decision: str              # mover | advertir | revisar
    motivo: str
    etapa: str                 # reglas | embeddings | qwen
    consulto_qwen: bool
    nombre_propuesto: str
    renombrar: bool
    motivo_nombre: str
    aviso: str | None = None   # lectura con problemas o Ollama caído


def _fila(archivo: ArchivoEscaneado, c: Clasificacion, extraccion: Extraccion | None,
          vocabulario: set[str], aviso: str | None) -> FilaReporte:
    propuesta = proponer_nombre(archivo.nombre, extraccion, sugerencia=c.nombre_sugerido,
                                palabras_clave=vocabulario)
    avisos = [a for a in (extraccion.aviso if extraccion else None, aviso) if a]
    return FilaReporte(
        ruta_relativa=archivo.ruta_relativa, nombre=archivo.nombre, tipo=c.tipo,
        materia=c.materia, confianza=c.confianza, decision=c.decision, motivo=c.motivo,
        etapa=c.etapa, consulto_qwen=c.consulto_qwen, nombre_propuesto=propuesta.nombre,
        renombrar=propuesta.renombrar, motivo_nombre=propuesta.motivo,
        aviso="; ".join(avisos) or None,
    )


def clasificar_uno(guardian: Guardian, config: Config, archivo: ArchivoEscaneado,
                   clasificador: Clasificador, respaldo: Clasificador | None = None
                   ) -> tuple[FilaReporte, Extraccion]:
    """Lee y clasifica un archivo. Si el modelo falla, usa `respaldo` (solo reglas)."""
    vocabulario = {p for m in config.materias for p in m.palabras_clave}
    extraccion = extraer(guardian, config, archivo.ruta)
    aviso = None
    try:
        c = clasificador.clasificar(archivo.nombre, extraccion)
    except Exception as error:  # Ollama caído o respuesta rara: no detener todo
        if respaldo is None:
            raise
        c = respaldo.clasificar(archivo.nombre, extraccion)
        aviso = f"{AVISO_MODELO} ({type(error).__name__}); se usaron solo reglas"
    return _fila(archivo, c, extraccion, vocabulario, aviso), extraccion


def clasificar_archivos(guardian: Guardian, config: Config, archivos: Iterable[ArchivoEscaneado],
                        clasificador: Clasificador, respaldo: Clasificador | None = None,
                        progreso: Progreso | None = None) -> list[FilaReporte]:
    """Clasifica cada archivo y propone su nombre. Solo lee."""
    archivos = list(archivos)
    filas = []
    for i, archivo in enumerate(archivos, start=1):
        fila = clasificar_uno(guardian, config, archivo, clasificador, respaldo)[0]
        filas.append(fila)
        if respaldo is not None and fila.aviso and AVISO_MODELO in fila.aviso:
            # Si el modelo falló una vez, no esperar su tiempo límite en cada archivo.
            clasificador = respaldo
        if progreso is not None:
            progreso(i, len(archivos))
    return filas


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def resumen_clasificacion(filas: list[FilaReporte], config: Config, otros: int = 0,
                          nota: str | None = None) -> str:
    """Texto corto para el modelo. La tabla completa ya la ve el estudiante."""
    if not filas:
        texto = "No hay archivos sin organizar en la carpeta Trabajos."
        if otros:
            texto += f" Hay {_plural(otros, 'archivo ya organizado', 'archivos ya organizados')}."
        return texto
    decisiones = Counter(f.decision for f in filas)
    por_materia = Counter(f.materia for f in filas)
    lineas = [
        f"Se clasificaron {_plural(len(filas), 'archivo', 'archivos')} sin organizar "
        "(modo simulación: no se movió ni renombró nada).",
        f"Decisiones: {decisiones[MOVER]} se proponen mover, {decisiones[ADVERTIR]} con advertencia, "
        f"{decisiones[REVISAR]} a {config.carpeta_dudas}.",
        "Por materia: " + ", ".join(f"{m}: {n}" for m, n in por_materia.most_common()) + ".",
        f"Nombres nuevos propuestos: {sum(f.renombrar for f in filas)}. "
        f"Consultas a Qwen: {sum(f.consulto_qwen for f in filas)}.",
    ]
    dudosos = [f for f in filas if f.decision != MOVER][:MAX_EN_RESUMEN]
    if dudosos:
        lineas.append("Archivos que el estudiante debe revisar: " + "; ".join(
            f"{f.nombre} ({f.materia}, {f.confianza:.2f})" for f in dudosos) + ".")
    if otros:
        lineas.append(f"Además hay {_plural(otros, 'archivo ya organizado', 'archivos ya organizados')} que no se clasificaron.")
    if nota:
        lineas.append(nota)
    lineas.append("La tabla completa ya se muestra al estudiante en el chat: no la repitas, "
                  "resume en 2 o 3 frases y ofrece explicar un archivo con ver_archivo.")
    return "\n".join(lineas)


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto.strip().casefold())
    return "".join(c for c in sin_acentos if not unicodedata.combining(c)).replace("\\", "/")


def buscar_archivo(archivos: Iterable[ArchivoEscaneado], consulta: str
                   ) -> tuple[ArchivoEscaneado | None, list[str]]:
    """Busca un archivo por nombre o ruta relativa (sin importar mayúsculas ni acentos).

    Devuelve (archivo, []) si hay uno solo; (None, candidatos) si hay varios o ninguno.
    """
    archivos = list(archivos)
    buscado = _normalizar(consulta)
    if not buscado:
        return None, []
    for criterio in (
        # Un nombre repetido en dos carpetas es ambiguo, aunque uno esté en la raíz.
        lambda a: buscado in (_normalizar(a.ruta_relativa), _normalizar(a.nombre)),
        lambda a: _normalizar(Path(a.nombre).stem) == buscado,
        lambda a: buscado in _normalizar(a.ruta_relativa),
    ):
        encontrados = [a for a in archivos if criterio(a)]
        if len(encontrados) == 1:
            return encontrados[0], []
        if encontrados:
            return None, [a.ruta_relativa for a in encontrados]
    return None, []


# -- Medición (solo modo desarrollo) ---------------------------------------------

def leer_etiquetas(ruta: str | Path) -> list[dict]:
    """Lee etiquetas.csv (archivo, materia, tipo, nombre_descriptivo, dificultad, caso)."""
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def archivos_del_dataset(archivos: Iterable[ArchivoEscaneado], nombres: set[str]) -> list[ArchivoEscaneado]:
    """Los archivos etiquetados de UNA sola carpeta: la que tiene más del dataset.

    Las etiquetas solo traen el nombre del archivo; si en Trabajos hay otro
    archivo con el mismo nombre en otra carpeta, no debe contarse en la medición.
    """
    por_carpeta: dict[str, list[ArchivoEscaneado]] = {}
    for a in archivos:
        if a.nombre in nombres:
            carpeta = a.ruta_relativa.rpartition("/")[0]
            por_carpeta.setdefault(carpeta, []).append(a)
    if not por_carpeta:
        return []
    return max(por_carpeta.values(), key=len)


@dataclass
class Medicion:
    total: int = 0
    aciertos: int = 0
    graves: list[FilaReporte] = field(default_factory=list)
    errores: list[tuple[FilaReporte, str]] = field(default_factory=list)   # (fila, materia esperada)
    por_dificultad: dict[str, list[int]] = field(default_factory=dict)     # dificultad -> [aciertos, total]
    decisiones: Counter = field(default_factory=Counter)
    consultas_qwen: int = 0
    aciertos_qwen: int = 0
    nombres_propuestos: int = 0
    nombres_validos: int = 0
    sin_etiqueta: list[str] = field(default_factory=list)
    faltantes: list[str] = field(default_factory=list)                    # etiquetados pero no están

    @property
    def exactitud(self) -> float:
        return self.aciertos / self.total if self.total else 0.0


def medir(filas: list[FilaReporte], etiquetas: list[dict]) -> Medicion:
    """Compara cada fila con su etiqueta (por nombre de archivo)."""
    por_nombre = {e["archivo"]: e for e in etiquetas}
    vistos = set()
    m = Medicion()
    for fila in filas:
        etiqueta = por_nombre.get(fila.nombre)
        if etiqueta is None:
            m.sin_etiqueta.append(fila.ruta_relativa)
            continue
        vistos.add(fila.nombre)
        esperada = etiqueta["materia"]
        acierto = fila.materia == esperada
        m.total += 1
        m.aciertos += acierto
        grupo = m.por_dificultad.setdefault(etiqueta.get("dificultad") or "sin dato", [0, 0])
        grupo[0] += acierto
        grupo[1] += 1
        m.decisiones[fila.decision] += 1
        if fila.consulto_qwen:
            m.consultas_qwen += 1
            m.aciertos_qwen += acierto
        if not acierto:
            m.errores.append((fila, esperada))
            if fila.decision == MOVER:
                m.graves.append(fila)
        if fila.renombrar:
            m.nombres_propuestos += 1
            m.nombres_validos += not validar_nombre(fila.nombre_propuesto)
    m.faltantes = sorted(set(por_nombre) - vistos)
    return m


def resumen_medicion(m: Medicion, etapas: str, meta: float = 0.85) -> str:
    """Texto corto para el modelo con el resultado de la medición."""
    if not m.total:
        return ("No se encontró ningún archivo etiquetado sin organizar en Trabajos. "
                "Copia el dataset con: python dataset/verificar_dataset.py --copiar-a <carpeta Trabajos>.")
    lineas = [
        f"Medición del clasificador ({etapas}) con {m.total} archivos etiquetados.",
        f"Exactitud en materia: {m.aciertos}/{m.total} ({m.exactitud:.0%}); meta {meta:.0%}: "
        f"{'cumplida' if m.exactitud >= meta else 'no cumplida'}.",
        f"Errores graves (se movería con confianza a la materia equivocada): {len(m.graves)}.",
        f"Consultas a Qwen: {m.consultas_qwen}. Nombres propuestos válidos en PascalCase: "
        f"{m.nombres_validos}/{m.nombres_propuestos}.",
    ]
    if m.faltantes:
        lineas.append(f"Faltan {len(m.faltantes)} archivos etiquetados en Trabajos.")
    lineas.append("Advertencia: el dataset lo escribió el mismo equipo, así que las cifras son optimistas. "
                  "La tabla completa ya se muestra en el chat: no la repitas.")
    return "\n".join(lineas)

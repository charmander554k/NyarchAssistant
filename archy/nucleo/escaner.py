"""Escáner de Archy (paso "Percibir" del ciclo del agente).

Recorre la carpeta autorizada y devuelve qué archivos hay, sin leer su
contenido (solo calcula el hash SHA-256 para detectar duplicados y comprobar
el "deshacer"). Toda ruta pasa por el guardián antes de tocarse.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .configuracion import Config
from .guardian import Guardian

__all__ = [
    "ArchivoEscaneado",
    "Omitido",
    "ResultadoEscaneo",
    "calcular_sha256",
    "escanear",
    "LIMITE_ARCHIVOS",
]

LIMITE_ARCHIVOS = 2000
_BLOQUE = 1024 * 1024

# Dónde está un archivo respecto a la estructura Materia/Tipo.
SUELTO = "suelto"
ORGANIZADO = "organizado"
POR_REVISAR = "por_revisar"


@dataclass(frozen=True)
class ArchivoEscaneado:
    ruta: str              # ruta absoluta
    ruta_relativa: str     # relativa a la carpeta raíz, con "/"
    nombre: str
    extension: str         # en minúsculas, con punto ("" si no tiene)
    tipo: str              # tipo según config.yaml (Codigo, Documentos, ...)
    tamano_bytes: int
    modificado: str        # fecha ISO 8601, hora local
    sha256: str
    ubicacion: str         # suelto | organizado | por_revisar
    materia_actual: str | None = None
    tipo_actual: str | None = None


@dataclass(frozen=True)
class Omitido:
    ruta_relativa: str
    motivo: str


@dataclass
class ResultadoEscaneo:
    raiz: str
    archivos: list[ArchivoEscaneado] = field(default_factory=list)
    omitidos: list[Omitido] = field(default_factory=list)
    limite_alcanzado: bool = False

    def resumen(self) -> dict:
        por_tipo: dict[str, int] = {}
        por_ubicacion: dict[str, int] = {}
        for a in self.archivos:
            por_tipo[a.tipo] = por_tipo.get(a.tipo, 0) + 1
            por_ubicacion[a.ubicacion] = por_ubicacion.get(a.ubicacion, 0) + 1
        return {
            "raiz": self.raiz,
            "archivos": len(self.archivos),
            "omitidos": len(self.omitidos),
            "por_tipo": dict(sorted(por_tipo.items())),
            "por_ubicacion": dict(sorted(por_ubicacion.items())),
            "limite_alcanzado": self.limite_alcanzado,
        }

    def a_dict(self) -> dict:
        return {
            "resumen": self.resumen(),
            "archivos": [asdict(a) for a in self.archivos],
            "omitidos": [asdict(o) for o in self.omitidos],
        }


def calcular_sha256(ruta: str | os.PathLike) -> str:
    """Hash SHA-256 del archivo, leído por bloques (no carga todo en memoria)."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while bloque := f.read(_BLOQUE):
            h.update(bloque)
    return h.hexdigest()


def _ubicacion(partes: tuple[str, ...], config: Config) -> tuple[str, str | None, str | None]:
    """Decide si un archivo ya está organizado, en _Por revisar o suelto."""
    if len(partes) >= 2 and partes[0].casefold() == config.carpeta_dudas.casefold():
        return POR_REVISAR, None, None
    if len(partes) >= 3:
        materias = {m.casefold(): m for m in config.nombres_materias}
        tipos = {t.casefold(): t for t in config.tipos}
        materia = materias.get(partes[0].casefold())
        tipo = tipos.get(partes[1].casefold())
        if materia and tipo:
            return ORGANIZADO, materia, tipo
    return SUELTO, None, None


def _megas(nbytes: int) -> str:
    return f"{nbytes / (1024 * 1024):g} MB"


def escanear(guardian: Guardian, config: Config, limite: int = LIMITE_ARCHIVOS) -> ResultadoEscaneo:
    """Recorre la carpeta raíz del guardián y describe cada archivo.

    Nunca lanza excepciones por un archivo problemático: lo agrega a
    `omitidos` con el motivo.
    """
    raiz = guardian.raiz
    resultado = ResultadoEscaneo(raiz=str(raiz))
    pendientes: list[Path] = [raiz]

    while pendientes:
        carpeta = pendientes.pop()
        try:
            with os.scandir(carpeta) as it:
                entradas = sorted(it, key=lambda e: e.name.casefold())
        except OSError as error:
            rel = carpeta.relative_to(raiz).as_posix() if carpeta != raiz else "."
            resultado.omitidos.append(Omitido(rel, f"no se pudo abrir la carpeta: {error.strerror or error}"))
            continue

        subcarpetas: list[Path] = []
        for entrada in entradas:
            ruta = Path(entrada.path)
            rel_partes = ruta.relative_to(raiz).parts
            rel = "/".join(rel_partes)

            decision = guardian.revisar(ruta)
            if not decision.permitido:
                resultado.omitidos.append(Omitido(rel, decision.motivo))
                continue

            try:
                if entrada.is_dir(follow_symlinks=False):
                    subcarpetas.append(ruta)
                    continue
                if not entrada.is_file(follow_symlinks=False):
                    resultado.omitidos.append(Omitido(rel, "no es un archivo normal"))
                    continue
                info = entrada.stat(follow_symlinks=False)
            except OSError as error:
                resultado.omitidos.append(Omitido(rel, f"no se pudo revisar: {error.strerror or error}"))
                continue

            if entrada.name.startswith("~$"):
                resultado.omitidos.append(Omitido(rel, "es un archivo temporal de Office (~$)"))
                continue
            if info.st_size > config.tamano_maximo_bytes:
                resultado.omitidos.append(
                    Omitido(rel, f"pesa más de {_megas(config.tamano_maximo_bytes)}")
                )
                continue
            if len(resultado.archivos) >= limite:
                resultado.limite_alcanzado = True
                return _ordenar(resultado)

            try:
                sha = calcular_sha256(ruta)
            except OSError as error:
                resultado.omitidos.append(
                    Omitido(rel, f"no se pudo leer (¿está abierto o sin permisos?): {error.strerror or error}")
                )
                continue

            extension = ruta.suffix.lower()
            ubicacion, materia, tipo_actual = _ubicacion(rel_partes, config)
            resultado.archivos.append(ArchivoEscaneado(
                ruta=str(ruta),
                ruta_relativa=rel,
                nombre=entrada.name,
                extension=extension,
                tipo=config.tipo_de(extension),
                tamano_bytes=info.st_size,
                modificado=datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds"),
                sha256=sha,
                ubicacion=ubicacion,
                materia_actual=materia,
                tipo_actual=tipo_actual,
            ))

        # Se agregan al revés para recorrer en orden alfabético (pila).
        pendientes.extend(reversed(subcarpetas))

    return _ordenar(resultado)


def _ordenar(resultado: ResultadoEscaneo) -> ResultadoEscaneo:
    resultado.archivos.sort(key=lambda a: a.ruta_relativa.casefold())
    resultado.omitidos.sort(key=lambda o: o.ruta_relativa.casefold())
    return resultado

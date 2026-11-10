"""Guardián de rutas de Archy.

Toda ruta que Archy vaya a leer, mover o crear pasa por aquí. El guardián solo
deja pasar rutas que:

- quedan dentro de la carpeta autorizada (la carpeta raíz, ej. `Trabajos`),
- no contienen `..`,
- no pasan por carpetas o archivos ocultos,
- no son accesos directos de Windows (`.lnk`),
- no pasan por enlaces simbólicos ni *junctions* de Windows,
- no están en la lista negra.

La lista negra base vive en este archivo y no se puede quitar desde la
configuración; `config.yaml` solo puede agregar rutas (`lista_negra_extra`).

Funciona en Linux, en WSL (rutas `/mnt/c/...`) y en Windows nativo.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Iterable

__all__ = [
    "ErrorGuardian",
    "AccesoDenegado",
    "ConfiguracionInvalida",
    "Decision",
    "Guardian",
    "motivo_lista_negra",
]


class ErrorGuardian(Exception):
    """Error base del guardián."""


class AccesoDenegado(ErrorGuardian):
    """La ruta pedida no está permitida."""

    def __init__(self, ruta: object, motivo: str) -> None:
        self.ruta = str(ruta)
        self.motivo = motivo
        super().__init__(f"Acceso denegado a '{self.ruta}': {motivo}")


class ConfiguracionInvalida(ErrorGuardian):
    """La carpeta raíz configurada no es segura o no existe."""


@dataclass(frozen=True)
class Decision:
    """Resultado de `Guardian.revisar`: nunca lanza excepciones."""

    permitido: bool
    ruta: str
    motivo: str


# ---------------------------------------------------------------------------
# Lista negra base
# ---------------------------------------------------------------------------

# Linux: se bloquea la carpeta y todo lo que tiene dentro.
_POSIX_ARBOL = (
    "/etc", "/usr", "/bin", "/sbin", "/boot", "/root", "/var",
    "/proc", "/sys", "/dev", "/lib", "/lib64", "/run",
)
# Linux: se bloquea solo esa carpeta exacta (lo de adentro puede ser válido).
_POSIX_EXACTAS = ("/", "/home", "/mnt")

# Dentro de una unidad de Windows (C:\ o /mnt/c): carpetas del sistema.
_WINDOWS_SISTEMA = ("windows", "program files", "program files (x86)", "programdata")

# Dentro de la carpeta personal: siempre bloqueadas, con todo su contenido.
_HOME_PROHIBIDAS = (".ssh", ".config", ".var", ".gnupg", ".local")

_RUTA_WINDOWS = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


def _motivo_unidad(letra: str, partes: list[str]) -> str | None:
    """Reglas para lo que hay dentro de una unidad de Windows.

    `partes` son los nombres de carpeta después de la unidad, en minúsculas
    (Windows no distingue mayúsculas).
    """
    if not partes:
        return f"es la raíz de la unidad {letra.upper()}:"
    if partes[0] in _WINDOWS_SISTEMA:
        return "es una carpeta del sistema de Windows"
    if partes[0] == "users":
        if len(partes) == 1:
            return "es la carpeta de todos los usuarios de Windows"
        if len(partes) == 2:
            return "es la carpeta personal completa de un usuario"
        if partes[2] == "appdata":
            return "es AppData (configuración de programas de Windows)"
    return None


def _dentro_puro(ruta: PurePath, base: PurePath, sin_mayusculas: bool) -> bool:
    if sin_mayusculas:
        ruta = type(ruta)(str(ruta).lower())
        base = type(base)(str(base).lower())
    return ruta == base or base in ruta.parents


def motivo_lista_negra(ruta: PurePath, home: PurePath | None = None) -> str | None:
    """Devuelve por qué `ruta` está en la lista negra, o `None` si no lo está.

    `ruta` debe ser absoluta y estar normalizada (sin `..`). Acepta rutas de
    Linux/WSL (`PurePosixPath`) y de Windows (`PureWindowsPath`).
    """
    if isinstance(ruta, PureWindowsPath):
        if ruta.drive.startswith("\\\\"):
            return "es una ruta de red"
        partes = [p.lower() for p in ruta.parts[1:]]
        motivo = _motivo_unidad(ruta.drive.rstrip(":"), partes)
        if motivo:
            return motivo
        sin_mayusculas = True
    else:
        texto = str(ruta)
        if texto in _POSIX_EXACTAS:
            return "es una carpeta del sistema"
        for carpeta in _POSIX_ARBOL:
            if _dentro_puro(ruta, PurePosixPath(carpeta), sin_mayusculas=False):
                return f"está dentro de {carpeta} (carpeta del sistema)"
        partes = list(ruta.parts)
        # WSL: /mnt/<letra>/... es una unidad de Windows.
        if len(partes) >= 3 and partes[1] == "mnt" and len(partes[2]) == 1:
            motivo = _motivo_unidad(partes[2], [p.lower() for p in partes[3:]])
            if motivo:
                return motivo
        sin_mayusculas = texto.startswith("/mnt/")

    if home is not None:
        if _dentro_puro(ruta, home, sin_mayusculas) and len(ruta.parts) == len(home.parts):
            return "es la carpeta personal completa"
        for carpeta in _HOME_PROHIBIDAS:
            if _dentro_puro(ruta, home / carpeta, sin_mayusculas):
                return f"está dentro de ~/{carpeta}"
    return None


# ---------------------------------------------------------------------------
# Utilidades de rutas reales
# ---------------------------------------------------------------------------

def _clave(ruta: os.PathLike | str) -> str:
    """Forma comparable de una ruta (en Windows, sin mayúsculas)."""
    return os.path.normcase(os.path.normpath(str(ruta)))


def _dentro(ruta: Path, base: Path) -> bool:
    try:
        return os.path.commonpath([_clave(base), _clave(ruta)]) == _clave(base)
    except ValueError:  # unidades distintas en Windows
        return False


def _es_junction(ruta: Path) -> bool:
    if hasattr(os.path, "isjunction"):  # Python 3.12+
        return os.path.isjunction(ruta)
    if os.name != "nt":
        return False
    try:
        return os.lstat(ruta).st_reparse_tag == 0xA0000003  # IO_REPARSE_TAG_MOUNT_POINT
    except (OSError, AttributeError):
        return False


def _es_enlace(ruta: Path) -> bool:
    return os.path.islink(ruta) or _es_junction(ruta)


def _expandir_home(texto: str, home: Path) -> str:
    if texto == "~":
        return str(home)
    if texto.startswith("~/") or texto.startswith("~\\"):
        return str(home / texto[2:])
    return texto


# ---------------------------------------------------------------------------
# Guardián
# ---------------------------------------------------------------------------

class Guardian:
    """Decide si una ruta es segura para Archy.

    Uso:
        guardian = Guardian("~/Documentos/Trabajos")
        ruta = guardian.validar("tarea1.py")        # lanza AccesoDenegado si no
        decision = guardian.revisar("/etc/passwd")  # nunca lanza
    """

    def __init__(
        self,
        carpeta_raiz: os.PathLike | str,
        lista_negra_extra: Iterable[os.PathLike | str] = (),
        home: os.PathLike | str | None = None,
    ) -> None:
        self.home = Path(home) if home is not None else Path.home()
        self.raiz = self._validar_raiz(carpeta_raiz)
        self._extra = [
            Path(os.path.normpath(_expandir_home(str(r), self.home)))
            for r in lista_negra_extra
        ]

    # -- carpeta raíz -------------------------------------------------------

    def _validar_raiz(self, carpeta_raiz: os.PathLike | str) -> Path:
        texto = _expandir_home(str(carpeta_raiz).strip(), self.home)
        if not texto:
            raise ConfiguracionInvalida("La carpeta raíz está vacía.")
        ruta = Path(texto)
        if not ruta.is_absolute():
            raise ConfiguracionInvalida(f"La carpeta raíz debe ser una ruta completa: '{texto}'.")
        if ".." in ruta.parts:
            raise ConfiguracionInvalida(f"La carpeta raíz no puede contener '..': '{texto}'.")
        ruta = Path(os.path.normpath(ruta))

        motivo = motivo_lista_negra(ruta, self.home)
        if motivo:
            raise ConfiguracionInvalida(f"La carpeta raíz '{ruta}' no es segura: {motivo}.")
        if not ruta.exists():
            raise ConfiguracionInvalida(f"La carpeta raíz no existe: '{ruta}'.")
        if not ruta.is_dir():
            raise ConfiguracionInvalida(f"La carpeta raíz no es una carpeta: '{ruta}'.")
        if _es_enlace(ruta) or _clave(ruta.resolve()) != _clave(ruta):
            raise ConfiguracionInvalida(
                f"La carpeta raíz '{ruta}' es o pasa por un enlace; configura la ruta real."
            )
        return ruta

    # -- validación de rutas ------------------------------------------------

    def validar(self, ruta: os.PathLike | str) -> Path:
        """Devuelve la ruta absoluta si es segura; si no, lanza `AccesoDenegado`.

        La ruta puede ser relativa a la carpeta raíz o absoluta. No necesita
        existir (sirve también para validar destinos de un movimiento).
        """
        texto = str(ruta).strip()
        if not texto:
            raise AccesoDenegado(ruta, "la ruta está vacía")
        if "\x00" in texto:
            raise AccesoDenegado(ruta, "la ruta contiene caracteres no válidos")
        if os.name != "nt" and _RUTA_WINDOWS.match(texto):
            raise AccesoDenegado(ruta, "es una ruta de Windows; en WSL se escribe como /mnt/c/...")

        candidata = Path(_expandir_home(texto, self.home))
        if ".." in candidata.parts:
            raise AccesoDenegado(ruta, "contiene '..' (intento de salir de la carpeta)")
        if not candidata.is_absolute():
            candidata = self.raiz / candidata
        candidata = Path(os.path.normpath(candidata))

        motivo = motivo_lista_negra(candidata, self.home) or self._motivo_extra(candidata)
        if motivo:
            raise AccesoDenegado(ruta, f"está en la lista negra: {motivo}")

        if not _dentro(candidata, self.raiz):
            raise AccesoDenegado(ruta, f"está fuera de la carpeta autorizada ({self.raiz})")

        relativa = candidata.relative_to(self.raiz).parts if candidata != self.raiz else ()
        if any(parte.startswith(".") for parte in relativa):
            raise AccesoDenegado(ruta, "es un archivo o carpeta oculta")
        if candidata.suffix.lower() == ".lnk":
            raise AccesoDenegado(ruta, "es un acceso directo de Windows (.lnk)")

        # Ningún tramo de la ruta (desde la raíz) puede ser un enlace.
        actual = self.raiz
        for parte in relativa:
            actual = actual / parte
            if not os.path.lexists(actual):
                break
            if _es_enlace(actual):
                raise AccesoDenegado(ruta, "pasa por un enlace simbólico o junction")

        # Segunda barrera: la ruta real debe coincidir con la escrita.
        real = candidata.resolve()
        if _clave(real) != _clave(candidata) or not _dentro(real, self.raiz):
            raise AccesoDenegado(ruta, "la ruta real no coincide con la escrita (posible enlace)")

        return candidata

    def revisar(self, ruta: os.PathLike | str) -> Decision:
        """Como `validar`, pero devuelve una `Decision` en lugar de lanzar errores."""
        try:
            permitida = self.validar(ruta)
        except AccesoDenegado as error:
            return Decision(False, str(ruta), error.motivo)
        except (OSError, ValueError) as error:
            return Decision(False, str(ruta), f"no se pudo revisar la ruta: {error}")
        return Decision(True, str(permitida), "permitida")

    def _motivo_extra(self, ruta: Path) -> str | None:
        for prohibida in self._extra:
            if _dentro(ruta, prohibida):
                return f"está en la lista negra configurada ({prohibida})"
        return None

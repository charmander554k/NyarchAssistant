"""Utilidades de texto compartidas por el nombrador y el clasificador."""

from __future__ import annotations

import re
import unicodedata

__all__ = ["sin_acentos", "normalizar", "palabras"]


def sin_acentos(texto: str) -> str:
    """Quita acentos y diéresis; la ñ se vuelve n."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos."""
    return sin_acentos(texto).lower()


def palabras(texto: str) -> list[str]:
    """Palabras normalizadas (letras y números). Separa camelCase y guiones bajos."""
    texto = re.sub(r"([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])", r"\1 \2", texto)  # camelCase -> camel Case
    return re.findall(r"[a-z0-9]+", normalizar(texto))

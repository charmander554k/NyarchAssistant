"""Cliente mínimo de Ollama (solo librería estándar).

Archy usa Ollama local; en desarrollo puede apuntar a otra PC por Tailscale
(ver CLAUDE.md, "Servidor Ollama remoto").
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Sequence

__all__ = ["ErrorOllama", "embebedor", "disponible"]


class ErrorOllama(Exception):
    """Ollama no respondió o respondió algo inesperado."""


def _post(endpoint: str, ruta: str, datos: dict, timeout: float) -> dict:
    peticion = urllib.request.Request(
        endpoint.rstrip("/") + ruta,
        data=json.dumps(datos).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise ErrorOllama(f"Ollama ({endpoint}) no respondió: {error}") from error


def disponible(endpoint: str, modelo: str, timeout: float = 5) -> bool:
    """¿Ollama responde y tiene el modelo descargado?"""
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/api/tags", timeout=timeout) as r:
            modelos = [m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])]
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
        return False
    return any(m == modelo or m.split(":")[0] == modelo for m in modelos)


def embebedor(endpoint: str, modelo: str = "paraphrase-multilingual", timeout: float = 60):
    """Devuelve una función textos -> vectores que usa /api/embed de Ollama."""

    def embeber(textos: Sequence[str]) -> list[list[float]]:
        respuesta = _post(endpoint, "/api/embed", {"model": modelo, "input": list(textos)}, timeout)
        vectores = respuesta.get("embeddings")
        if not isinstance(vectores, list) or len(vectores) != len(textos):
            raise ErrorOllama(f"respuesta inesperada de /api/embed: {str(respuesta)[:200]}")
        return vectores

    return embeber

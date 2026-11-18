"""Cliente mínimo de Ollama (solo librería estándar).

Archy usa Ollama local; en desarrollo puede apuntar a otra PC por Tailscale
(ver CLAUDE.md, "Servidor Ollama remoto").
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Sequence

__all__ = ["ErrorOllama", "embebedor", "disponible", "chat_json"]


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


def embebedor(endpoint: str, modelo: str = "paraphrase-multilingual", timeout: float = 180):
    """Devuelve una función textos -> vectores que usa /api/embed de Ollama."""

    def embeber(textos: Sequence[str]) -> list[list[float]]:
        respuesta = _post(endpoint, "/api/embed", {"model": modelo, "input": list(textos)}, timeout)
        vectores = respuesta.get("embeddings")
        if not isinstance(vectores, list) or len(vectores) != len(textos):
            raise ErrorOllama(f"respuesta inesperada de /api/embed: {str(respuesta)[:200]}")
        return vectores

    return embeber


def chat_json(endpoint: str, modelo: str = "qwen2.5:3b", timeout: float = 120, contexto: int = 4096):
    """Devuelve una función mensajes -> dict que pide a Ollama una respuesta en JSON.

    Usa temperatura 0 (respuestas estables) y un contexto pequeño, porque el
    mensaje que arma el clasificador es corto (no pasa por NyarchAssistant).
    """

    def consultar(mensajes: list[dict]) -> dict:
        datos = {"model": modelo, "messages": mensajes, "format": "json", "stream": False,
                 "options": {"temperature": 0, "num_ctx": contexto}}
        respuesta = _post(endpoint, "/api/chat", datos, timeout)
        contenido = (respuesta.get("message") or {}).get("content", "")
        try:
            resultado = json.loads(contenido)
        except ValueError as error:
            raise ErrorOllama(f"Qwen no devolvió JSON: {contenido[:200]}") from error
        if not isinstance(resultado, dict):
            raise ErrorOllama(f"Qwen devolvió un JSON que no es objeto: {contenido[:200]}")
        return resultado

    return consultar

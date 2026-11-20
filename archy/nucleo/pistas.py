"""Pistas para el modelo: qué herramienta de Archy corresponde a un mensaje.

Qwen 2.5 3B, después de un par de turnos, deja de llamar a las herramientas y
copia el estilo de sus respuestas anteriores (inventa materias y confianzas).
Probado el 20 nov con la conversación real: aun sin el ruido de NyarchAssistant
solo llamó a la herramienta en 3 de 5 casos. Por eso la extensión revisa el
último mensaje del estudiante con reglas simples y, si reconoce la intención
(un nombre de archivo, "organiza", "deshaz"...), le agrega al modelo una pista
explícita. La extensión la pone en un campo interno del mensaje
("RetrievedContext") que la app envía al modelo pero no muestra: el texto del
estudiante no cambia. Con la pista ahí, Qwen acertó en 14 de 15 turnos.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

__all__ = ["pista_para", "ETIQUETA"]

ETIQUETA = "[Pista de Archy]"


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in sin_acentos if not unicodedata.combining(c))


INTENCIONES = (
    ("deshacer", r"\b(deshaz|deshacer|deshagas|revierte|revertir|regresa(r)? (los|mis) archivos)\b"),
    ("historial", r"\b(historial|bitacora|que hiciste|que has hecho|registro de cambios)\b"),
    ("aplicar", r"\b(aplica|aplicar|ejecuta|ejecutar|mueve|mover|realiza) (el |los |mis )?(plan|cambios|archivos)\b"),
    ("proponer_plan", r"\b(organiza|organizar|ordena|ordenar|clasifica|clasificar|escanea|escanear|escaneo|revisa|revisar)\b"
                      r".{0,40}\b(carpeta|trabajos|archivos)\b"),
)


def _archivos_mencionados(mensaje: str, extensiones: Iterable[str]) -> list[str]:
    extensiones = sorted({e.lstrip(".").lower() for e in extensiones if e}, key=len, reverse=True)
    if not extensiones:
        return []
    patron = r"([\w\-. áéíóúñÁÉÍÓÚÑ]*?[\w\-áéíóúñÁÉÍÓÚÑ]\.(?:" + "|".join(map(re.escape, extensiones)) + r"))\b"
    nombres = []
    for crudo in re.findall(patron, mensaje, flags=re.IGNORECASE):
        nombre = crudo.strip(" .")
        # "que contiene escaneo_red.csv" -> "escaneo_red.csv": se quitan palabras sueltas de la pregunta.
        palabras = nombre.split(" ")
        while len(palabras) > 1 and _normalizar(palabras[0]) in {
                "que", "es", "el", "la", "archivo", "contiene", "hay", "en", "de", "por", "porque", "va", "a",
                "y", "dime", "abre", "explica", "ver", "muestra", "sobre", "del", "lee", "este", "ese", "mi",
                "compara", "comparar", "entre", "con", "cual", "dame", "info", "informacion", "analiza", "describe"}:
            palabras.pop(0)
        nombre = " ".join(palabras)
        if nombre and nombre not in nombres:
            nombres.append(nombre)
    return nombres


def pista_para(mensaje: str, extensiones: Iterable[str] = (), herramientas: Iterable[str] = ()) -> str | None:
    """Texto que se agrega al mensaje para el modelo, o None si no hay una intención clara."""
    disponibles = set(herramientas)
    archivos = _archivos_mencionados(mensaje, extensiones)
    if archivos and "ver_archivo" in disponibles:
        llamadas = ", ".join(f"ver_archivo(nombre=\"{a}\")" for a in archivos)
        return (f"{ETIQUETA} Para responder, llama a {llamadas} y contesta solo con su resultado. "
                "No inventes materias ni confianzas.")
    texto = _normalizar(mensaje)
    for intencion, patron in INTENCIONES:
        if not re.search(patron, texto):
            continue
        if intencion == "aplicar":
            return (f"{ETIQUETA} Tú no puedes mover archivos. Dile al estudiante que use el botón «Mover» de la "
                    "tarjeta del plan (y que active «Modo real» en Configuración → Extensiones → Archy para "
                    "mover de verdad). No digas que ya se aplicó.")
        if intencion in disponibles:
            return f"{ETIQUETA} Para responder, llama a {intencion}() y luego resume su resultado en 2 o 3 frases."
    return None

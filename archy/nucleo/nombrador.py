"""Nombrador de Archy: valida nombres y propone nombres PascalCase.

Regla del proyecto: PascalCase, sin acentos ni ñ, sin espacios ni símbolos,
máximo 50 caracteres (incluida la extensión) y extensión en minúsculas, por
ejemplo `AlgoritmoBolsaDePalabras.py`. **Solo se renombra si el nombre actual
no es descriptivo.**

De dónde sale el nombre propuesto, en orden:
1. la sugerencia de Qwen (si la hay y es válida),
2. el título del contenido: primera línea de un Word/PDF/texto, título de la
   primera diapositiva, encabezado de Markdown o notebook, comentario inicial,
   clase o función principal del código, columnas de una tabla,
3. las palabras clave de las materias que aparecen en el texto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Iterable

from .extractor import Extraccion
from .texto import palabras, sin_acentos

__all__ = ["MAXIMO", "Propuesta", "validar_nombre", "es_descriptivo", "a_pascal",
           "titulo_del_contenido", "proponer_nombre"]

MAXIMO = 50
_PASCAL = re.compile(r"^[A-Z][A-Za-z0-9]*$")

# Palabras que no dicen de qué trata un archivo.
GENERICAS = {
    "doc", "docx", "documento", "document", "sin", "titulo", "untitled", "nuevo", "nueva", "new",
    "copia", "copy", "de", "del", "la", "el", "los", "las", "tarea", "tareas", "final", "finales",
    "v", "ver", "version", "libro", "book", "presentacion", "presentation", "img", "image",
    "imagen", "foto", "captura", "screenshot", "archivo", "file", "main", "programa", "practica",
    "practicas", "proyecto", "trabajo", "ejercicio", "notas", "apuntes", "resumen", "reporte",
    "informe", "ensayo", "expo", "exposicion", "equipo", "datos", "data", "resultados", "results",
    "log", "logs", "grafica", "grafico", "prueba", "test", "readme", "codigo", "script", "clase",
    "ok", "ultimo", "definitivo", "entrega", "hoja", "sheet", "pptx", "pdf", "txt", "py",
}
# Siglas cortas que sí dicen algo.
SIGLAS = {"ia", "ai", "rsa", "aes", "des", "nlp", "pln", "knn", "lda", "ids", "sql", "xss", "dns",
          "vpn", "mfa", "dmz", "bfs", "dfs", "xor", "svm", "cnn", "rnn", "tls", "ssl", "ssh", "csv"}
# Palabras que se quitan al armar un nombre (artículos y conectores).
_RELLENO = {"el", "la", "los", "las", "un", "una", "unos", "unas", "y", "e", "o", "u", "en",
            "con", "para", "por", "que", "se", "al", "a"}
_VOCALES = set("aeiou")


@dataclass(frozen=True)
class Propuesta:
    nombre: str        # nombre final (igual al actual si no se renombra)
    renombrar: bool
    motivo: str


def validar_nombre(nombre: str, maximo: int = MAXIMO) -> list[str]:
    """Lista de problemas del nombre según la regla del proyecto (vacía si está bien)."""
    problemas = []
    ruta = PurePath(nombre)
    base, extension = ruta.stem, ruta.suffix
    if not base:
        problemas.append("no tiene nombre")
    elif not _PASCAL.match(base):
        problemas.append("no está en PascalCase (solo letras sin acento y números, empezando con mayúscula)")
    if extension != extension.lower():
        problemas.append("la extensión debe ir en minúsculas")
    if len(nombre) > maximo:
        problemas.append(f"tiene más de {maximo} caracteres")
    return problemas


def _parece_basura(palabra: str) -> bool:
    """vdksahdas, sniff... Pocas vocales o 4+ consonantes seguidas."""
    if len(palabra) < 5 or palabra.isdigit():
        return False
    vocales = sum(c in _VOCALES for c in palabra)
    return vocales / len(palabra) < 0.25 or re.search(r"[^aeiou\d]{4,}", palabra) is not None


def es_descriptivo(nombre: str, vocabulario: Iterable[str] = ()) -> tuple[bool, str]:
    """¿El nombre dice de qué trata el archivo? Devuelve (respuesta, motivo)."""
    vocabulario = set(vocabulario)
    informativas = []
    for p in palabras(PurePath(nombre).stem):
        raiz = re.sub(r"\d+$", "", p)  # Doc1 -> doc, practica3 -> practica
        if p in vocabulario or raiz in vocabulario or raiz in SIGLAS:
            informativas.append(p)
        elif not raiz or len(raiz) < 4 or raiz in GENERICAS:
            continue
        elif _parece_basura(p):
            continue
        else:
            informativas.append(p)
    if informativas:
        return True, "el nombre ya dice de qué trata (" + ", ".join(informativas[:3]) + ")"
    return False, "el nombre no dice de qué trata"


def a_pascal(texto: str, extension: str = "", maximo: int = MAXIMO, max_palabras: int = 5) -> str | None:
    """Convierte un texto en un nombre PascalCase válido, o None si no queda nada útil."""
    texto = re.sub(r"([a-z])([A-Z])", r"\1 \2", sin_acentos(texto))  # AlgoritmoTfidf -> Algoritmo Tfidf
    trozos = re.findall(r"[A-Za-z0-9]+", texto)
    elegidas = []
    for t in trozos:
        if t.lower() in _RELLENO or (t.isdigit() and len(t) > 2):
            continue
        if t.isupper() and len(t) <= 4 and t.isalpha():
            elegidas.append(t)                       # siglas: RSA, AES, XOR
        else:
            elegidas.append(t[0].upper() + t[1:].lower())
        if len(elegidas) == max_palabras:
            break
    if not elegidas:
        return None
    base = "".join(elegidas)
    if base[0].isdigit():
        base = "Archivo" + base
    extension = extension.lower()
    limite = maximo - len(extension)
    while len(base) > limite and len(elegidas) > 1:   # recorta por palabras completas
        elegidas.pop()
        base = "".join(elegidas)
    base = base[:limite]
    nombre = base + extension
    return nombre if not validar_nombre(nombre, maximo) else None


def _primera_linea(texto: str) -> str:
    for linea in texto.splitlines():
        linea = linea.strip().lstrip("#").strip()
        if linea:
            return linea
    return ""


def titulo_del_contenido(extraccion: Extraccion | None) -> tuple[str, str] | None:
    """(título, de dónde salió) a partir del texto extraído, o None."""
    if extraccion is None or extraccion.vacio:
        return None
    texto, metodo = extraccion.texto, extraccion.metodo
    if metodo == "codigo":
        clase = re.search(r"^\s*class\s+([A-Za-z_]\w*)", texto, re.M)
        comentario = re.search(r"^\s*(?:#|//|--)\s*(?!include)(.{12,})$", texto, re.M)
        docstring = re.search(r'"""\s*(.{12,}?)\s*(?:"""|$)', texto, re.M)
        funcion = re.search(r"^\s*(?:async\s+)?(?:def|function)\s+([A-Za-z_]\w*)", texto, re.M)
        for encontrado, origen in ((comentario, "comentario inicial"), (docstring, "docstring"),
                                   (clase, "clase principal"), (funcion, "función principal")):
            if encontrado:
                return encontrado.group(1).replace("_", " "), origen
        return None
    if metodo == "tabla":
        columnas = texto.splitlines()[0].removeprefix("Columnas:").split(",")
        return "Datos " + " ".join(c.strip() for c in columnas[:3]), "nombres de columnas"
    if metodo == "xlsx":
        hojas = re.search(r"^Hojas:\s*(.+)$", texto, re.M)
        textos = re.search(r"^Celdas:\s*(.+)$", texto, re.M)
        hoja = hojas.group(1).split(",")[0].strip() if hojas else ""
        if re.fullmatch(r"(?i)(hoja|sheet)\s*\d*", hoja):
            hoja = ""
        primeros = " ".join(t.strip() for t in textos.group(1).split("|")[:2]) if textos else ""
        titulo = f"{hoja} {primeros}".strip()
        return (titulo, "hoja de cálculo") if titulo else None
    if metodo == "notebook":
        encabezado = re.search(r"^\s*#+\s*(.+)$", texto, re.M)
        return (encabezado.group(1) if encabezado else _primera_linea(texto)), "encabezado del notebook"
    titulo = _primera_linea(texto)
    return (titulo, "primera línea del contenido") if titulo else None


def proponer_nombre(nombre_actual: str, extraccion: Extraccion | None = None,
                    sugerencia: str | None = None, palabras_clave: Iterable[str] = (),
                    maximo: int = MAXIMO) -> Propuesta:
    """Decide si renombrar y propone el nombre nuevo (sin acentos, PascalCase)."""
    extension = PurePath(nombre_actual).suffix.lower()
    vocabulario = set(palabras_clave)
    descriptivo, motivo = es_descriptivo(nombre_actual, vocabulario)
    if descriptivo:
        return Propuesta(nombre_actual, False, motivo)

    candidatos = []
    if sugerencia:
        candidatos.append((PurePath(sugerencia).stem, "sugerencia de Qwen"))
    titulo = titulo_del_contenido(extraccion)
    if titulo:
        candidatos.append(titulo)
    if extraccion is not None and not extraccion.vacio and vocabulario:
        encontradas = []
        for p in palabras(extraccion.texto):
            if p in vocabulario and p not in encontradas:
                encontradas.append(p)
        if encontradas:
            candidatos.append((" ".join(encontradas[:3]), "palabras clave del contenido"))

    for texto, origen in candidatos:
        nombre = a_pascal(texto, extension, maximo)
        if nombre and nombre != nombre_actual:
            return Propuesta(nombre, True, f"{motivo}; nombre tomado de: {origen}")
    return Propuesta(nombre_actual, False, f"{motivo}, pero no hay contenido para proponer otro")

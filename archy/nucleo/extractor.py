"""Extractor de Archy (paso "Percibir", segunda parte).

Saca los primeros caracteres útiles de un archivo (por defecto 2,000, según
`caracteres_a_leer` en config.yaml) para que el clasificador decida a qué
materia pertenece.

Reglas:
- Toda ruta pasa por el guardián.
- Los archivos se abren solo para lectura; nunca se modifican.
- Nunca lanza excepciones: un archivo dañado devuelve texto vacío y un aviso.
- El texto solo vive en memoria; nunca se guarda en la bitácora.
- Sin dependencias extra: .docx, .pptx, .xlsx y OpenDocument se leen como lo
  que son (un ZIP con XML). Para .pdf se usa pypdf, que ya viene en el Flatpak
  de NyarchAssistant.
"""

from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .configuracion import Config
from .guardian import Guardian

__all__ = ["Extraccion", "extraer", "LECTOR_POR_EXTENSION"]

# Límites de seguridad.
MAX_BYTES_TEXTO = 256 * 1024        # de un archivo de texto o código se leen como máximo 256 KB
MAX_BYTES_XML = 4 * 1024 * 1024     # de cada parte de un ZIP (docx, pptx...) como máximo 4 MB
MAX_BYTES_NOTEBOOK = 5 * 1024 * 1024
MAX_PAGINAS_PDF = 5
MAX_FILAS_TABLA = 5
MAX_DIAPOSITIVAS = 30


@dataclass(frozen=True)
class Extraccion:
    ruta_relativa: str
    texto: str
    metodo: str           # texto | codigo | notebook | tabla | docx | pptx | xlsx | opendocument | pdf | no_soportado | error
    truncado: bool        # True si el archivo tenía más texto que el límite
    aviso: str | None = None

    @property
    def vacio(self) -> bool:
        return not self.texto.strip()


class _Aviso(Exception):
    """Problema esperado al leer un archivo (se convierte en aviso, no en error)."""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _leer_bytes(ruta: Path, limite: int) -> tuple[bytes, bool]:
    with open(ruta, "rb") as f:
        datos = f.read(limite + 1)
    return datos[:limite], len(datos) > limite


def _decodificar(datos: bytes) -> str:
    if b"\x00" in datos[:4096]:
        raise _Aviso("parece un archivo binario, no texto")
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return datos.decode("latin-1")  # nunca falla


def _limpiar(texto: str) -> str:
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    lineas = [linea.rstrip() for linea in texto.split("\n")]
    texto = "\n".join(lineas)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


# Líneas que más dicen de un archivo de código: imports, definiciones y comentarios.
_LINEA_CLAVE = re.compile(
    r"""^\s*(
        import\s | from\s+\S+\s+import\s | \#include | using\s | package\s | library\( | require\( |
        def\s | class\s | async\s+def\s | function\s | public\s | private\s | protected\s | static\s |
        \# | // | /\* | \*\s | -- | \"\"\" | '''
    )""",
    re.VERBOSE,
)


def _priorizar_codigo(codigo: str) -> str:
    """Pone primero imports, definiciones y comentarios; luego el resto."""
    claves, resto = [], []
    for linea in codigo.splitlines():
        if not linea.strip():
            continue
        (claves if _LINEA_CLAVE.match(linea) else resto).append(linea.rstrip())
    return "\n".join(claves + resto)


def _texto_de_xml(xml: str, etiquetas_texto: tuple[str, ...], fin_parrafo: str) -> str:
    """Saca el texto de un XML de Office sin parsearlo completo.

    Funciona aunque el XML esté cortado (por el límite de tamaño), porque solo
    busca las etiquetas de texto con una expresión regular.
    """
    xml = re.sub(fin_parrafo, "\n", xml)
    patron = "|".join(re.escape(e) for e in etiquetas_texto)
    trozos = re.findall(rf"<(?:{patron})(?:\s[^>]*)?>([^<]*)</(?:{patron})>|(\n)", xml)
    return html.unescape("".join(t or salto for t, salto in trozos))


def _leer_parte_zip(zf: zipfile.ZipFile, nombre: str) -> tuple[str, bool]:
    """Lee como máximo MAX_BYTES_XML descomprimidos (protege contra bombas ZIP)."""
    with zf.open(nombre) as parte:
        datos = parte.read(MAX_BYTES_XML + 1)
    return datos[:MAX_BYTES_XML].decode("utf-8", errors="replace"), len(datos) > MAX_BYTES_XML


def _abrir_zip(ruta: Path) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(ruta)
    except zipfile.BadZipFile as error:
        raise _Aviso("el archivo está dañado o no es un documento de Office válido") from error


def _numero(nombre: str) -> int:
    encontrado = re.search(r"(\d+)\.xml$", nombre)
    return int(encontrado.group(1)) if encontrado else 0


# ---------------------------------------------------------------------------
# Lectores por formato. Cada uno devuelve (texto, recortado_en_origen).
# ---------------------------------------------------------------------------

def _leer_texto(ruta: Path, limite: int) -> tuple[str, bool]:
    datos, cortado = _leer_bytes(ruta, MAX_BYTES_TEXTO)
    return _decodificar(datos), cortado


def _leer_codigo(ruta: Path, limite: int) -> tuple[str, bool]:
    texto, cortado = _leer_texto(ruta, limite)
    return _priorizar_codigo(texto), cortado


def _leer_notebook(ruta: Path, limite: int) -> tuple[str, bool]:
    datos, cortado = _leer_bytes(ruta, MAX_BYTES_NOTEBOOK)
    if cortado:
        raise _Aviso("el notebook es demasiado grande para leerlo")
    try:
        cuaderno = json.loads(_decodificar(datos))
        celdas = cuaderno.get("cells", [])
    except (ValueError, AttributeError) as error:
        raise _Aviso("el notebook está dañado (no es JSON válido)") from error
    markdown, codigo = [], []
    for celda in celdas:
        fuente = celda.get("source", "")
        fuente = "".join(fuente) if isinstance(fuente, list) else str(fuente)
        (codigo if celda.get("cell_type") == "code" else markdown).append(fuente)
    return "\n".join(markdown) + "\n" + _priorizar_codigo("\n".join(codigo)), False


def _leer_tabla(ruta: Path, limite: int) -> tuple[str, bool]:
    datos, cortado = _leer_bytes(ruta, 64 * 1024)
    texto = _decodificar(datos)
    if ruta.suffix.lower() == ".tsv":
        delimitador = "\t"
    else:
        try:
            delimitador = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t|").delimiter
        except csv.Error:
            delimitador = ","
    filas = list(csv.reader(io.StringIO(texto), delimiter=delimitador))
    filas = [f for f in filas if any(c.strip() for c in f)]
    if not filas:
        return "", False
    lineas = ["Columnas: " + ", ".join(c.strip() for c in filas[0])]
    for fila in filas[1:1 + MAX_FILAS_TABLA]:
        lineas.append(" | ".join(c.strip() for c in fila))
    return "\n".join(lineas), cortado or len(filas) > 1 + MAX_FILAS_TABLA


def _leer_docx(ruta: Path, limite: int) -> tuple[str, bool]:
    with _abrir_zip(ruta) as zf:
        if "word/document.xml" not in zf.namelist():
            raise _Aviso("no se encontró el texto del documento (word/document.xml)")
        xml, cortado = _leer_parte_zip(zf, "word/document.xml")
    return _texto_de_xml(xml, ("w:t",), r"</w:p>"), cortado


def _leer_pptx(ruta: Path, limite: int) -> tuple[str, bool]:
    with _abrir_zip(ruta) as zf:
        diapositivas = sorted(
            (n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=_numero
        )
        if not diapositivas:
            raise _Aviso("la presentación no tiene diapositivas con texto")
        partes, cortado = [], len(diapositivas) > MAX_DIAPOSITIVAS
        for nombre in diapositivas[:MAX_DIAPOSITIVAS]:
            xml, parte_cortada = _leer_parte_zip(zf, nombre)
            cortado = cortado or parte_cortada
            partes.append(_texto_de_xml(xml, ("a:t",), r"</a:p>").strip())
            if sum(len(p) for p in partes) > limite:
                cortado = True
                break
    return "\n".join(partes), cortado


def _leer_xlsx(ruta: Path, limite: int) -> tuple[str, bool]:
    with _abrir_zip(ruta) as zf:
        nombres = zf.namelist()
        hojas = []
        if "xl/workbook.xml" in nombres:
            xml, _ = _leer_parte_zip(zf, "xl/workbook.xml")
            hojas = [html.unescape(h) for h in re.findall(r'<sheet\b[^>]*\bname="([^"]*)"', xml)]
        textos, cortado = [], False
        if "xl/sharedStrings.xml" in nombres:
            xml, cortado = _leer_parte_zip(zf, "xl/sharedStrings.xml")
            textos = [html.unescape(t) for t in re.findall(r"<t(?:\s[^>]*)?>([^<]*)</t>", xml)]
    lineas = []
    if hojas:
        lineas.append("Hojas: " + ", ".join(hojas))
    if textos:
        lineas.append("Textos: " + " | ".join(t for t in textos if t.strip()))
    return "\n".join(lineas), cortado


def _leer_opendocument(ruta: Path, limite: int) -> tuple[str, bool]:
    with _abrir_zip(ruta) as zf:
        if "content.xml" not in zf.namelist():
            raise _Aviso("no se encontró el contenido del documento (content.xml)")
        xml, cortado = _leer_parte_zip(zf, "content.xml")
    xml = re.sub(r"</text:(?:p|h)>", "\n", xml)
    texto = html.unescape(re.sub(r"<[^>]*>", "", xml))
    return texto, cortado


def _leer_pdf(ruta: Path, limite: int) -> tuple[str, bool]:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise _Aviso("falta la librería pypdf para leer PDF") from error
    try:
        lector = PdfReader(str(ruta), strict=False)
        if lector.is_encrypted:
            raise _Aviso("el PDF está protegido con contraseña")
        paginas = lector.pages
        partes, cortado = [], len(paginas) > MAX_PAGINAS_PDF
        for pagina in list(paginas)[:MAX_PAGINAS_PDF]:
            partes.append(pagina.extract_text() or "")
            if sum(len(p) for p in partes) > limite:
                cortado = True
                break
    except _Aviso:
        raise
    except Exception as error:  # pypdf lanza muchos tipos de error con PDFs dañados
        raise _Aviso(f"el PDF está dañado o no se pudo leer ({type(error).__name__})") from error
    texto = "\n".join(partes)
    if not texto.strip():
        raise _Aviso("el PDF no tiene texto (¿es una imagen escaneada?)")
    return texto, cortado


_TEXTO = (".txt", ".md", ".markdown", ".rst", ".tex", ".log", ".json", ".xml", ".yaml", ".yml", ".html", ".htm", ".css")
_CODIGO = (".py", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".js", ".ts", ".sql", ".sh", ".r", ".m", ".go", ".rb", ".php", ".kt")

LECTOR_POR_EXTENSION = {
    **{e: ("texto", _leer_texto) for e in _TEXTO},
    **{e: ("codigo", _leer_codigo) for e in _CODIGO},
    ".ipynb": ("notebook", _leer_notebook),
    ".csv": ("tabla", _leer_tabla),
    ".tsv": ("tabla", _leer_tabla),
    ".docx": ("docx", _leer_docx),
    ".pptx": ("pptx", _leer_pptx),
    ".xlsx": ("xlsx", _leer_xlsx),
    ".odt": ("opendocument", _leer_opendocument),
    ".ods": ("opendocument", _leer_opendocument),
    ".odp": ("opendocument", _leer_opendocument),
    ".pdf": ("pdf", _leer_pdf),
}


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def extraer(guardian: Guardian, config: Config, ruta: str | os.PathLike) -> Extraccion:
    """Devuelve el texto útil de un archivo dentro de la carpeta autorizada."""
    limite = config.caracteres_a_leer
    decision = guardian.revisar(ruta)
    if not decision.permitido:
        return Extraccion(str(ruta), "", "error", False, decision.motivo)

    ruta_segura = Path(decision.ruta)
    rel = ruta_segura.relative_to(guardian.raiz).as_posix() if ruta_segura != guardian.raiz else "."
    try:
        if not ruta_segura.is_file():
            return Extraccion(rel, "", "error", False, "no es un archivo")
        tamano = ruta_segura.stat().st_size
    except OSError as error:
        return Extraccion(rel, "", "error", False, f"no se pudo revisar: {error.strerror or error}")
    if tamano > config.tamano_maximo_bytes:
        return Extraccion(rel, "", "error", False, "pesa más que el máximo permitido")

    extension = ruta_segura.suffix.lower()
    if extension not in LECTOR_POR_EXTENSION:
        return Extraccion(rel, "", "no_soportado", False,
                          f"Archy no lee el contenido de archivos {extension or 'sin extensión'}")

    metodo, lector = LECTOR_POR_EXTENSION[extension]
    try:
        texto, cortado = lector(ruta_segura, limite)
    except _Aviso as aviso:
        return Extraccion(rel, "", "error", False, str(aviso))
    except OSError as error:
        return Extraccion(rel, "", "error", False,
                          f"no se pudo leer (¿está abierto o sin permisos?): {error.strerror or error}")
    except Exception as error:  # nunca dejar caer al agente por un archivo raro
        return Extraccion(rel, "", "error", False, f"error inesperado al leer ({type(error).__name__})")

    texto = _limpiar(texto)
    truncado = cortado or len(texto) > limite
    return Extraccion(rel, texto[:limite], metodo, truncado,
                      None if texto else "el archivo no tiene texto")

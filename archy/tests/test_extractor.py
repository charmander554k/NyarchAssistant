"""Pruebas del extractor. Todos los archivos de prueba se crean aquí mismo,
sin librerías extra (los .docx/.pptx/.xlsx son ZIP con XML y el PDF se arma
a mano)."""

import dataclasses
import json
import time
import zipfile
from pathlib import Path

import pytest

from nucleo.configuracion import cargar_config
from nucleo.extractor import Extraccion, extraer

CONFIG_REAL = Path(__file__).resolve().parent.parent / "config.yaml"


@pytest.fixture
def config():
    return cargar_config(CONFIG_REAL)


# ---------------------------------------------------------------------------
# Fabricantes de archivos de prueba
# ---------------------------------------------------------------------------

def crear_zip(ruta: Path, partes: dict[str, str]) -> Path:
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre, contenido in partes.items():
            zf.writestr(nombre, contenido)
    return ruta


def crear_docx(ruta: Path, parrafos: list[str]) -> Path:
    cuerpo = "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{p}</w:t></w:r></w:p>" for p in parrafos)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document '
           'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{cuerpo}</w:body></w:document>")
    return crear_zip(ruta, {"word/document.xml": xml})


def crear_pptx(ruta: Path, diapositivas: list[str]) -> Path:
    partes = {}
    for i, texto in enumerate(diapositivas, start=1):
        partes[f"ppt/slides/slide{i}.xml"] = (
            '<p:sld xmlns:p="p" xmlns:a="a"><p:txBody><a:p><a:r>'
            f"<a:t>{texto}</a:t></a:r></a:p></p:txBody></p:sld>")
    return crear_zip(ruta, partes)


def crear_xlsx(ruta: Path, hoja: str, textos: list[str]) -> Path:
    compartidos = "".join(f"<si><t>{t}</t></si>" for t in textos)
    return crear_zip(ruta, {
        "xl/workbook.xml": f'<workbook><sheets><sheet name="{hoja}" sheetId="1"/></sheets></workbook>',
        "xl/sharedStrings.xml": f"<sst>{compartidos}</sst>",
    })


def crear_pdf(ruta: Path, texto: str) -> Path:
    """PDF mínimo de una página con texto en Helvetica (offsets calculados)."""
    contenido = f"BT /F1 12 Tf 72 720 Td ({texto}) Tj ET".encode("latin-1")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(contenido) + contenido + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % numero + cuerpo + b"\nendobj\n"
    inicio_xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for posicion in posiciones:
        salida += b"%010d 00000 n \n" % posicion
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, inicio_xref)
    ruta.write_bytes(bytes(salida))
    return ruta


# ---------------------------------------------------------------------------
# Formatos
# ---------------------------------------------------------------------------

def test_texto_plano(entorno, config):
    (entorno.raiz / "notas.txt").write_text("Apuntes de criptografía: RSA y AES", encoding="utf-8")
    r = extraer(entorno.guardian, config, "notas.txt")
    assert r.metodo == "texto"
    assert "criptografía" in r.texto
    assert r.truncado is False and r.aviso is None
    assert r.ruta_relativa == "notas.txt"


def test_texto_con_acentos_de_windows(entorno, config):
    (entorno.raiz / "viejo.txt").write_bytes("Criptografía y contraseñas".encode("cp1252"))
    assert extraer(entorno.guardian, config, "viejo.txt").texto == "Criptografía y contraseñas"


def test_codigo_pone_primero_imports_y_definiciones(entorno, config):
    relleno = "\n".join(f"x{i} = {i} * 2" for i in range(400))  # mucho más de 2,000 caracteres
    codigo = relleno + "\nimport nltk\nfrom sklearn.feature_extraction.text import TfidfVectorizer\n" \
                       "def limpiar_texto(t):\n    # quita stopwords\n    return t\n"
    (entorno.raiz / "vdksahdas.py").write_text(codigo, encoding="utf-8")
    r = extraer(entorno.guardian, config, "vdksahdas.py")
    assert r.metodo == "codigo"
    assert r.texto.startswith("import nltk")
    assert "TfidfVectorizer" in r.texto
    assert "def limpiar_texto" in r.texto
    assert "# quita stopwords" in r.texto
    assert r.truncado is True


def test_notebook(entorno, config):
    cuaderno = {"cells": [
        {"cell_type": "markdown", "source": ["# Práctica: perceptrón\n", "Agente simple"]},
        {"cell_type": "code", "source": "w = [0, 0]\nimport numpy as np\nclass Perceptron:\n    pass"},
    ]}
    (entorno.raiz / "p1.ipynb").write_text(json.dumps(cuaderno), encoding="utf-8")
    r = extraer(entorno.guardian, config, "p1.ipynb")
    assert r.metodo == "notebook"
    assert "Práctica: perceptrón" in r.texto
    assert r.texto.index("import numpy") < r.texto.index("w = [0, 0]")


def test_csv_con_punto_y_coma(entorno, config):
    (entorno.raiz / "datos.csv").write_text("texto;sentimiento\nbueno;1\nmalo;0\n", encoding="utf-8")
    r = extraer(entorno.guardian, config, "datos.csv")
    assert r.metodo == "tabla"
    assert r.texto.splitlines()[0] == "Columnas: texto, sentimiento"
    assert "bueno | 1" in r.texto


def test_docx(entorno, config):
    crear_docx(entorno.raiz / "informe.docx", ["Análisis de puertos con nmap", "Firewall &amp; reglas"])
    r = extraer(entorno.guardian, config, "informe.docx")
    assert r.metodo == "docx"
    assert r.texto == "Análisis de puertos con nmap\nFirewall & reglas"


def test_pptx(entorno, config):
    crear_pptx(entorno.raiz / "expo.pptx", ["Bolsa de palabras", "TF-IDF", "Conclusiones"])
    r = extraer(entorno.guardian, config, "expo.pptx")
    assert r.metodo == "pptx"
    assert r.texto.split("\n") == ["Bolsa de palabras", "TF-IDF", "Conclusiones"]


def test_pptx_respeta_orden_numerico_de_diapositivas(entorno, config):
    crear_pptx(entorno.raiz / "larga.pptx", [f"D{i}" for i in range(1, 12)])
    texto = extraer(entorno.guardian, config, "larga.pptx").texto
    assert texto.index("D2") < texto.index("D10")


def test_xlsx(entorno, config):
    crear_xlsx(entorno.raiz / "notas.xlsx", "Calificaciones", ["alumno", "corpus", "tfidf"])
    r = extraer(entorno.guardian, config, "notas.xlsx")
    assert r.metodo == "xlsx"
    assert "Hojas: Calificaciones" in r.texto
    assert "alumno | corpus | tfidf" in r.texto


def test_opendocument(entorno, config):
    crear_zip(entorno.raiz / "tarea.odt",
              {"content.xml": "<office:text><text:h>Heurísticas</text:h><text:p>Búsqueda A*</text:p></office:text>"})
    r = extraer(entorno.guardian, config, "tarea.odt")
    assert r.metodo == "opendocument"
    assert r.texto == "Heurísticas\nBúsqueda A*"


def test_pdf(entorno, config):
    pytest.importorskip("pypdf")
    crear_pdf(entorno.raiz / "practica.pdf", "Practica de cifrado RSA")
    r = extraer(entorno.guardian, config, "practica.pdf")
    assert r.metodo == "pdf"
    assert "Practica de cifrado RSA" in r.texto


# ---------------------------------------------------------------------------
# Límites y archivos problemáticos
# ---------------------------------------------------------------------------

def test_recorta_al_limite_de_config(entorno, config):
    (entorno.raiz / "largo.txt").write_text("a" * 5000, encoding="utf-8")
    r = extraer(entorno.guardian, config, "largo.txt")
    assert len(r.texto) == config.caracteres_a_leer == 2000
    assert r.truncado is True


def test_limite_configurable(entorno, config):
    corto = dataclasses.replace(config, caracteres_a_leer=10)
    (entorno.raiz / "x.txt").write_text("0123456789ABCDEF", encoding="utf-8")
    assert extraer(entorno.guardian, corto, "x.txt").texto == "0123456789"


def test_docx_danado(entorno, config):
    (entorno.raiz / "roto.docx").write_bytes(b"esto no es un zip")
    r = extraer(entorno.guardian, config, "roto.docx")
    assert r.metodo == "error" and r.texto == ""
    assert "dañado" in r.aviso


def test_pdf_danado(entorno, config):
    pytest.importorskip("pypdf")
    (entorno.raiz / "roto.pdf").write_bytes(b"%PDF-1.4\nbasura sin estructura")
    r = extraer(entorno.guardian, config, "roto.pdf")
    assert r.metodo == "error" and r.texto == ""
    assert r.aviso


def test_bomba_zip_no_se_descomprime_completa(entorno, config):
    # 60 MB de XML que comprimen a muy poco: solo se deben leer los primeros MB.
    enorme = "<w:p><w:r><w:t>a</w:t></w:r></w:p>" * 2_000_000
    crear_zip(entorno.raiz / "bomba.docx", {"word/document.xml": enorme})
    inicio = time.perf_counter()
    r = extraer(entorno.guardian, config, "bomba.docx")
    assert time.perf_counter() - inicio < 10
    assert r.truncado is True
    assert len(r.texto) <= config.caracteres_a_leer


def test_binario_con_extension_de_texto(entorno, config):
    (entorno.raiz / "falso.txt").write_bytes(b"\x00\x01\x02binario")
    r = extraer(entorno.guardian, config, "falso.txt")
    assert r.metodo == "error"
    assert "binario" in r.aviso


def test_extension_no_soportada(entorno, config):
    (entorno.raiz / "foto.png").write_bytes(b"\x89PNG\r\n")
    r = extraer(entorno.guardian, config, "foto.png")
    assert r.metodo == "no_soportado" and r.texto == ""
    assert ".png" in r.aviso


def test_archivo_vacio(entorno, config):
    (entorno.raiz / "vacio.txt").write_text("", encoding="utf-8")
    r = extraer(entorno.guardian, config, "vacio.txt")
    assert r.vacio and r.aviso == "el archivo no tiene texto"


def test_archivo_demasiado_grande(entorno, config):
    pequeno = dataclasses.replace(config, tamano_maximo_bytes=10)
    (entorno.raiz / "grande.txt").write_text("x" * 100, encoding="utf-8")
    r = extraer(entorno.guardian, pequeno, "grande.txt")
    assert r.metodo == "error" and "máximo" in r.aviso


# ---------------------------------------------------------------------------
# Seguridad: todo pasa por el guardián
# ---------------------------------------------------------------------------

def test_ruta_fuera_de_trabajos(entorno, config):
    r = extraer(entorno.guardian, config, entorno.fuera / "secreto.txt")
    assert r.metodo == "error" and r.texto == ""
    assert "fuera de la carpeta" in r.aviso


def test_llaves_ssh(entorno, config):
    r = extraer(entorno.guardian, config, "~/.ssh/id_rsa")
    assert r.texto == "" and "~/.ssh" in r.aviso


def test_carpeta_no_es_archivo(entorno, config):
    r = extraer(entorno.guardian, config, "sub")
    assert r.metodo == "error" and r.aviso == "no es un archivo"


def test_no_modifica_el_archivo(entorno, config):
    ruta = crear_docx(entorno.raiz / "intacto.docx", ["Texto"])
    antes = (ruta.read_bytes(), ruta.stat().st_mtime_ns)
    extraer(entorno.guardian, config, "intacto.docx")
    assert (ruta.read_bytes(), ruta.stat().st_mtime_ns) == antes


def test_siempre_devuelve_extraccion(entorno, config):
    for nombre in ("tarea.py", "no_existe.txt", "../x", ""):
        assert isinstance(extraer(entorno.guardian, config, nombre), Extraccion)

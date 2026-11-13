import pytest

from nucleo.extractor import Extraccion
from nucleo.nombrador import (a_pascal, es_descriptivo, proponer_nombre, titulo_del_contenido,
                              validar_nombre)


def ext(texto, metodo="texto"):
    return Extraccion("x", texto, metodo, False)


# --- validar_nombre -------------------------------------------------------

@pytest.mark.parametrize("nombre", ["AlgoritmoBolsaDePalabras.py", "Practica3CifradoRSA.docx", "Iris.csv"])
def test_nombres_validos(nombre):
    assert validar_nombre(nombre) == []


@pytest.mark.parametrize("nombre, problema", [
    ("algoritmo.py", "PascalCase"),
    ("Práctica.docx", "PascalCase"),
    ("Mi Archivo.txt", "PascalCase"),
    ("Archivo-Final.txt", "PascalCase"),
    ("Informe.PDF", "minúsculas"),
    ("A" * 48 + ".py", "50"),
])
def test_nombres_invalidos(nombre, problema):
    assert any(problema in p for p in validar_nombre(nombre))


# --- es_descriptivo -------------------------------------------------------

@pytest.mark.parametrize("nombre", [
    "vdksahdas.py", "Doc1.docx", "Untitled.ipynb", "tarea final FINAL.pdf", "nuevo 3.txt",
    "Libro1.xlsx", "Presentación1.pptx", "IMG_20261005.png", "a1.py", "x.py", "programa_final(1).py",
    "Documento sin título.docx", "sniff.ipynb", "equipo4_final.pptx",
])
def test_nombres_no_descriptivos(nombre):
    assert es_descriptivo(nombre)[0] is False


@pytest.mark.parametrize("nombre", [
    "perceptron.py", "hashes_contrasenas.py", "captura_wireshark.png", "apuntes ia.txt",
    "knn_practica.ipynb", "PRACTICA_RSA.PDF", "corpus.csv", "AlgoritmoBolsaDePalabras.py",
])
def test_nombres_descriptivos(nombre):
    assert es_descriptivo(nombre)[0] is True


# --- a_pascal ---------------------------------------------------------------

def test_a_pascal_quita_acentos_y_simbolos():
    assert a_pascal("Práctica 3: Cifrado RSA", ".docx") == "Practica3CifradoRSA.docx"


def test_a_pascal_quita_articulos_y_conserva_de():
    assert a_pascal("La ley de Zipf", ".DOCX") == "LeyDeZipf.docx"


def test_a_pascal_enie_y_numeros_largos():
    assert a_pascal("Contraseñas 2026 seguras", ".txt") == "ContrasenasSeguras.txt"


def test_a_pascal_respeta_el_maximo():
    nombre = a_pascal("Análisis comparativo exhaustivo de algoritmos criptográficos modernos", ".docx")
    assert len(nombre) <= 50 and validar_nombre(nombre) == []


def test_a_pascal_sin_contenido_util():
    assert a_pascal("--- ### ---", ".txt") is None


# --- titulo_del_contenido -------------------------------------------------

def test_titulo_docx():
    assert titulo_del_contenido(ext("Informe de vulnerabilidades\nSe revisó...", "docx"))[0] == "Informe de vulnerabilidades"


def test_titulo_markdown():
    assert titulo_del_contenido(ext("# Ingeniería social y phishing\n- algo"))[0] == "Ingeniería social y phishing"


def test_titulo_codigo_prefiere_comentario():
    codigo = "import numpy as np\n# Lee reglas de firewall estilo iptables\ndef evaluar(p):\n    pass"
    assert titulo_del_contenido(ext(codigo, "codigo"))[0] == "Lee reglas de firewall estilo iptables"


def test_titulo_codigo_usa_clase_o_funcion():
    assert titulo_del_contenido(ext("import numpy\nclass Perceptron:\n    pass", "codigo"))[0] == "Perceptron"
    assert titulo_del_contenido(ext("def generar_claves(p, q):\n    pass", "codigo"))[0] == "generar claves"


def test_titulo_tabla():
    assert titulo_del_contenido(ext("Columnas: ip, puerto, servicio, estado\n1 | 2", "tabla"))[0] == "Datos ip puerto servicio"


def test_titulo_xlsx_ignora_hoja_generica():
    assert titulo_del_contenido(ext("Hojas: Hoja1\nCeldas: alumno | corpus | tfidf", "xlsx"))[0] == "alumno corpus"
    assert titulo_del_contenido(ext("Hojas: Riesgos\nCeldas: activo | amenaza", "xlsx"))[0] == "Riesgos activo amenaza"


# --- proponer_nombre ------------------------------------------------------

def test_no_renombra_si_es_descriptivo():
    p = proponer_nombre("perceptron.py", ext("class Perceptron: pass", "codigo"))
    assert p.renombrar is False and p.nombre == "perceptron.py"


def test_renombra_con_titulo_del_documento():
    p = proponer_nombre("practica3 v2.docx", ext("Práctica 3: Cifrado RSA\nObjetivo...", "docx"))
    assert p.renombrar and p.nombre == "Practica3CifradoRSA.docx"
    assert "primera línea" in p.motivo


def test_prefiere_la_sugerencia_de_qwen():
    p = proponer_nombre("vdksahdas.py", ext("import nltk", "codigo"), sugerencia="AlgoritmoTfidf.py")
    assert p.nombre == "AlgoritmoTfidf.py" and "Qwen" in p.motivo


def test_usa_palabras_clave_si_no_hay_titulo():
    p = proponer_nombre("vdksahdas.py", ext("import nltk\nfrom sklearn import TfidfVectorizer", "codigo"),
                        palabras_clave={"nltk", "tfidf"})
    assert p.nombre == "NltkTfidf.py"


def test_sin_contenido_no_renombra():
    p = proponer_nombre("IMG_20261005.png", None)
    assert p.renombrar is False and "no hay contenido" in p.motivo


def test_extension_queda_en_minusculas():
    p = proponer_nombre("Doc1.DOCX", ext("Tipos de agentes inteligentes", "docx"))
    assert p.nombre == "TiposDeAgentesInteligentes.docx"

from pathlib import Path

import pytest

from nucleo.clasificador import ADVERTIR, MOVER, REVISAR, Clasificador
from nucleo.configuracion import cargar_config
from nucleo.extractor import Extraccion

CONFIG = cargar_config(Path(__file__).resolve().parent.parent / "config.yaml")
SEG, MIN, IA = "Seguridad Informática", "Minería de Texto", "Fundamentos de IA"


def ext(texto, metodo="texto"):
    return Extraccion("x", texto, metodo, False)


@pytest.fixture
def clasificador():
    return Clasificador(CONFIG)


def test_codigo_de_mineria(clasificador):
    c = clasificador.clasificar("vdksahdas.py", ext("import nltk\nfrom sklearn import TfidfVectorizer\ncorpus = []", "codigo"))
    assert c.materia == MIN and c.decision == MOVER
    assert c.tipo == "Codigo"
    assert "nltk" in c.motivo


def test_pista_en_el_nombre_pesa_mas(clasificador):
    c = clasificador.clasificar("perceptron.py", ext("w = 0"))
    assert c.materia == IA
    assert "perceptron (nombre)" in c.motivo


def test_palabras_completas_no_pedazos(clasificador):
    # "contexto" y "pretexto" no deben contar como la palabra clave "texto".
    c = clasificador.clasificar("cifrado.py", ext("# Cifrado César\n# contexto y pretexto\nclave = 3"))
    assert c.materia == SEG


def test_palabra_generica_pesa_menos(clasificador):
    # "texto" (genérica) aparece 3 veces; "cifrado" y "rsa" (específicas) una vez.
    c = clasificador.clasificar("a.py", ext("def cifrar(texto): texto = texto  # cifrado rsa"))
    assert c.materia == SEG


def test_sin_pistas_va_a_dudas(clasificador):
    c = clasificador.clasificar("IMG_20261005.png", None)
    assert c.decision == REVISAR and c.materia == CONFIG.carpeta_dudas
    assert c.confianza == 0
    assert "no se encontraron pistas" in c.motivo


def test_empate_entre_materias_no_se_mueve(clasificador):
    texto = "Horario: Seguridad Informática, Minería de Texto, Fundamentos de IA"
    c = clasificador.clasificar("horario_semestre.pdf", ext(texto, "pdf"))
    assert c.decision == REVISAR


def test_poca_evidencia_da_advertencia(clasificador):
    c = clasificador.clasificar("notas.txt", ext("hablamos del hash"))
    assert c.decision in (ADVERTIR, REVISAR)
    assert c.confianza < CONFIG.umbrales.alto


def test_tipo_sale_de_la_extension(clasificador):
    assert clasificador.clasificar("x.PPTX", ext("tfidf")).tipo == "Presentaciones"
    assert clasificador.clasificar("x.zip", None).tipo == "Otros"


def test_puntajes_suman_uno(clasificador):
    c = clasificador.clasificar("x.py", ext("import nltk; nmap; perceptron"))
    assert abs(sum(c.puntajes.values()) - 1) < 0.01


def test_frases_de_varias_palabras(clasificador):
    c = clasificador.clasificar("x.txt", ext("Una red neuronal con lógica difusa y un árbol de decisión"))
    assert c.materia == IA


# --- etapa de embeddings con un "Ollama falso" ------------------------------

def embebedor_falso(textos):
    """Vector según qué materia "se parece" el texto (palabras guía)."""
    vectores = []
    for t in textos:
        t = t.lower()
        vectores.append([
            1.0 if "cripto" in t or "seguridad" in t else 0.1,
            1.0 if "tfidf" in t or "minería" in t or "texto" in t else 0.1,
            1.0 if "perceptr" in t or "fundamentos" in t else 0.1,
        ])
    return vectores


def test_embeddings_ayudan_cuando_no_hay_palabras_clave():
    c = Clasificador(CONFIG, embeber=embebedor_falso)
    r = c.clasificar("Libro1.xlsx", ext("Hojas: Riesgos\nCeldas: activo | amenaza | criptografía", "xlsx"))
    assert r.etapa == "embeddings"
    assert r.materia == SEG


def test_embeddings_sin_texto_no_se_usan():
    c = Clasificador(CONFIG, embeber=embebedor_falso)
    r = c.clasificar("captura.png", None)
    assert r.etapa == "reglas" and r.decision == REVISAR


def test_las_descripciones_se_embeben_una_sola_vez():
    llamadas = []

    def contar(textos):
        llamadas.append(len(textos))
        return embebedor_falso(textos)

    c = Clasificador(CONFIG, embeber=contar)
    c.clasificar("a.txt", ext("tfidf"))
    c.clasificar("b.txt", ext("perceptron"))
    assert llamadas == [3, 1, 1]  # 3 materias una vez, luego 1 texto por archivo

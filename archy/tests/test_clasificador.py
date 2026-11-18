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
            1.0 if "candado" in t or "seguridad" in t else 0.1,
            1.0 if "tfidf" in t or "minería" in t or "texto" in t else 0.1,
            1.0 if "perceptr" in t or "fundamentos" in t else 0.1,
        ])
    return vectores


def test_embeddings_ayudan_cuando_no_hay_palabras_clave():
    # "candado" no es palabra clave: las reglas no saben y deciden los embeddings.
    c = Clasificador(CONFIG, embeber=embebedor_falso)
    r = c.clasificar("Libro1.xlsx", ext("Hojas: Hoja1\nCeldas: candado | llave | puerta", "xlsx"))
    assert r.etapa == "embeddings"
    assert r.materia == SEG


def test_embeddings_no_se_consultan_si_las_reglas_ya_estan_seguras():
    llamadas = []

    def contar(textos):
        llamadas.append(len(textos))
        return embebedor_falso(textos)

    r = Clasificador(CONFIG, embeber=contar).clasificar("vdksahdas.py", ext("import nltk; tfidf corpus", "codigo"))
    assert r.etapa == "reglas" and llamadas == []


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


# --- etapa de Qwen con un "Qwen falso" --------------------------------------

def qwen_falso(respuesta):
    llamadas = []

    def consultar(mensajes):
        llamadas.append(mensajes)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    consultar.llamadas = llamadas
    return consultar


DUDOSO = ext("hablamos del hash y de la busqueda")  # pistas de Seguridad e IA: empate


def test_qwen_no_se_consulta_si_hay_certeza():
    q = qwen_falso({"materia": SEG, "confianza": 0.9})
    c = Clasificador(CONFIG, consultar=q).clasificar("vdksahdas.py", ext("import nltk; tfidf corpus", "codigo"))
    assert q.llamadas == [] and c.etapa == "reglas" and c.consulto_qwen is False


def test_qwen_no_se_consulta_sin_texto():
    q = qwen_falso({"materia": SEG, "confianza": 0.9})
    c = Clasificador(CONFIG, consultar=q).clasificar("captura.png", None)
    assert q.llamadas == [] and c.decision == REVISAR


def test_qwen_se_consulta_en_empate_y_el_prompt_lleva_las_materias():
    q = qwen_falso({"materia": IA, "confianza": 0.8, "nombre_sugerido": "BusquedaHash.txt", "motivo": "habla de búsqueda"})
    c = Clasificador(CONFIG, consultar=q).clasificar("notas.txt", DUDOSO)
    assert len(q.llamadas) == 1
    prompt = q.llamadas[0][1]["content"]
    assert all(m in prompt for m in (SEG, MIN, IA, CONFIG.carpeta_dudas)) and "notas.txt" in prompt
    assert c.etapa == "qwen" and c.consulto_qwen
    assert c.nombre_sugerido == "BusquedaHash.txt"
    assert "habla de búsqueda" in c.motivo


def test_si_qwen_no_coincide_nunca_se_mueve_con_confianza():
    q = qwen_falso({"materia": MIN, "confianza": 1.0})
    c = Clasificador(CONFIG, consultar=q).clasificar("notas.txt", DUDOSO)
    assert c.decision != MOVER
    assert c.confianza < CONFIG.umbrales.alto


def test_si_qwen_coincide_sube_la_confianza():
    previa = Clasificador(CONFIG).clasificar("notas.txt", ext("cifrado con rsa"))
    q = qwen_falso({"materia": SEG, "confianza": 0.95})
    c = Clasificador(CONFIG, consultar=q).clasificar("notas.txt", ext("cifrado con rsa"))
    if previa.decision == ADVERTIR:  # solo se consulta si había duda
        assert c.confianza > previa.confianza and c.materia == SEG


def test_qwen_dice_que_no_es_de_ninguna_materia():
    q = qwen_falso({"materia": "_por revisar", "confianza": 0.9, "motivo": "es un horario"})
    c = Clasificador(CONFIG, consultar=q).clasificar("notas.txt", DUDOSO)
    assert c.decision == REVISAR and c.materia == CONFIG.carpeta_dudas


def test_qwen_acepta_materia_sin_acentos():
    q = qwen_falso({"materia": "fundamentos de ia", "confianza": 0.7})
    c = Clasificador(CONFIG, consultar=q).clasificar("notas.txt", DUDOSO)
    assert c.etapa == "qwen"


@pytest.mark.parametrize("respuesta", [
    {"materia": "Química", "confianza": 0.9},       # materia inventada
    {"materia": SEG, "confianza": "mucha"},          # confianza inválida
    {"materia": SEG, "confianza": 3},                # fuera de rango
    RuntimeError("Ollama apagado"),                  # falla de conexión
])
def test_si_qwen_falla_se_queda_lo_de_las_reglas(respuesta):
    sin_qwen = Clasificador(CONFIG).clasificar("notas.txt", DUDOSO)
    c = Clasificador(CONFIG, consultar=qwen_falso(respuesta)).clasificar("notas.txt", DUDOSO)
    assert (c.materia, c.decision, c.confianza) == (sin_qwen.materia, sin_qwen.decision, sin_qwen.confianza)
    assert "Qwen no dio una respuesta válida" in c.motivo


def test_qwen_nunca_convierte_una_duda_en_certeza():
    q = qwen_falso({"materia": SEG, "confianza": 1.0})
    c = Clasificador(CONFIG, consultar=q).clasificar("notas.txt", DUDOSO)
    if c.consulto_qwen and c.materia == SEG:
        assert c.decision != MOVER and c.confianza < CONFIG.umbrales.alto

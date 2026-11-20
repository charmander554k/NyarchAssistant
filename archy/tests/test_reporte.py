from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from nucleo.clasificador import ADVERTIR, MOVER, REVISAR, Clasificador
from nucleo.configuracion import cargar_config
from nucleo.escaner import escanear
from nucleo.guardian import Guardian
from nucleo.reporte import (AVISO_MODELO, FilaReporte, archivos_del_dataset, buscar_archivo, clasificar_archivos,
                            clasificar_uno, leer_etiquetas, medir, resumen_clasificacion,
                            resumen_medicion)

ARCHY = Path(__file__).resolve().parent.parent
CONFIG = cargar_config(ARCHY / "config.yaml")
SEG, MIN, IA = "Seguridad Informática", "Minería de Texto", "Fundamentos de IA"


@pytest.fixture
def trabajos(entorno):
    raiz = entorno.raiz
    (raiz / "tarea.py").unlink()
    (raiz / "vdksahdas.py").write_text("import nltk\nfrom sklearn import TfidfVectorizer\ncorpus = []\n",
                                       encoding="utf-8")
    (raiz / "Doc1.txt").write_text("Informe de vulnerabilidades\nEscaneo con nmap y cifrado RSA.\n",
                                   encoding="utf-8")
    (raiz / "IMG_2026.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
    config = replace(CONFIG, carpeta_raiz=str(raiz))
    archivos = [a for a in escanear(entorno.guardian, config).archivos if a.ubicacion == "suelto"]
    return SimpleNamespace(guardian=entorno.guardian, config=config, archivos=archivos, raiz=raiz)


def fila(nombre, materia, decision=MOVER, confianza=0.9, renombrar=False, nuevo=None, qwen=False):
    return FilaReporte(nombre, nombre, "Codigo", materia, confianza, decision, "motivo", "reglas",
                       qwen, nuevo or nombre, renombrar, "motivo nombre")


# -- clasificar_archivos -----------------------------------------------------------

def test_clasifica_y_propone_nombres(trabajos):
    avances = []
    filas = clasificar_archivos(trabajos.guardian, trabajos.config, trabajos.archivos,
                                Clasificador(trabajos.config), progreso=lambda i, n: avances.append((i, n)))
    por_nombre = {f.nombre: f for f in filas}
    assert por_nombre["vdksahdas.py"].materia == MIN
    assert por_nombre["vdksahdas.py"].decision == MOVER
    assert por_nombre["vdksahdas.py"].renombrar          # nombre basura
    assert por_nombre["Doc1.txt"].materia == SEG
    assert por_nombre["Doc1.txt"].nombre_propuesto == "InformeDeVulnerabilidades.txt"
    assert por_nombre["IMG_2026.png"].decision == REVISAR
    assert por_nombre["IMG_2026.png"].materia == CONFIG.carpeta_dudas
    assert avances == [(1, 3), (2, 3), (3, 3)]


def test_no_mueve_ni_cambia_archivos(trabajos):
    antes = {p.name: p.read_bytes() for p in trabajos.raiz.iterdir() if p.is_file()}
    clasificar_archivos(trabajos.guardian, trabajos.config, trabajos.archivos, Clasificador(trabajos.config))
    despues = {p.name: p.read_bytes() for p in trabajos.raiz.iterdir() if p.is_file()}
    assert antes == despues


def test_si_el_modelo_falla_usa_solo_reglas_y_no_insiste(trabajos):
    llamadas = []

    def embeber_caido(textos):
        llamadas.append(textos)
        raise ConnectionError("Ollama apagado")

    # Un archivo con poca evidencia obliga a consultar los embeddings.
    (trabajos.raiz / "notas.txt").write_text("apuntes de la clase de cifrado", encoding="utf-8")
    (trabajos.raiz / "otras.txt").write_text("apuntes de la clase de agentes", encoding="utf-8")
    config = trabajos.config
    archivos = [a for a in escanear(trabajos.guardian, config).archivos if a.nombre in ("notas.txt", "otras.txt")]
    filas = clasificar_archivos(trabajos.guardian, config, archivos,
                                Clasificador(config, embeber=embeber_caido), respaldo=Clasificador(config))
    assert len(filas) == 2
    assert AVISO_MODELO in filas[0].aviso
    assert len(llamadas) == 1          # el segundo archivo ya no espera al modelo
    assert filas[0].materia == SEG


def test_sin_respaldo_el_error_se_propaga(trabajos):
    def embeber_caido(textos):
        raise ConnectionError("Ollama apagado")
    (trabajos.raiz / "notas.txt").write_text("apuntes de la clase de cifrado", encoding="utf-8")
    archivo = next(a for a in escanear(trabajos.guardian, trabajos.config).archivos if a.nombre == "notas.txt")
    with pytest.raises(ConnectionError):
        clasificar_uno(trabajos.guardian, trabajos.config, archivo, Clasificador(trabajos.config, embeber=embeber_caido))


def test_lectura_con_problemas_queda_como_aviso(trabajos):
    (trabajos.raiz / "roto.docx").write_bytes(b"esto no es un zip")
    archivo = next(a for a in escanear(trabajos.guardian, trabajos.config).archivos if a.nombre == "roto.docx")
    f, extraccion = clasificar_uno(trabajos.guardian, trabajos.config, archivo, Clasificador(trabajos.config))
    assert extraccion.aviso and f.aviso == extraccion.aviso
    assert f.decision == REVISAR


# -- resumen para el modelo -------------------------------------------------------

def test_resumen_es_corto_y_no_pide_repetir_la_tabla():
    filas = [fila(f"a{i}.py", MIN) for i in range(60)] + [fila("duda.py", IA, ADVERTIR, 0.5, qwen=True),
                                                           fila("x.png", "_Por revisar", REVISAR, 0.0)]
    texto = resumen_clasificacion(filas, CONFIG, otros=4, nota="Etapas usadas: reglas.")
    assert "62 archivos" in texto
    assert "60 se proponen mover, 1 con advertencia, 1 a _Por revisar" in texto
    assert "Consultas a Qwen: 1" in texto
    assert "duda.py" in texto and "a0.py" not in texto     # solo se nombran los dudosos
    assert "4 archivos ya organizados" in texto
    # Solo datos: Qwen 3B copiaba al chat las instrucciones que venían en el resumen.
    assert "repitas" not in texto.lower() and "ver_archivo" not in texto
    assert len(texto) < 1200


def test_resumen_sin_archivos():
    assert "No hay archivos sin organizar" in resumen_clasificacion([], CONFIG)
    assert "1 archivo ya organizado" in resumen_clasificacion([], CONFIG, otros=1)


# -- buscar_archivo ---------------------------------------------------------------

ARCHIVOS = [SimpleNamespace(nombre=n, ruta_relativa=r) for n, r in [
    ("Doc1.docx", "Doc1.docx"),
    ("practica3 v2.docx", "practica3 v2.docx"),
    ("Práctica RSA.py", "Seguridad Informática/Codigo/Práctica RSA.py"),
    ("Doc1.docx", "Minería de Texto/Documentos/Doc1.docx"),
    ("expo.pptx", "expo.pptx"),
    ("tarea3 final FINAL.txt", "tarea3 final FINAL.txt"),
]]


@pytest.mark.parametrize("consulta, esperado", [
    ("expo.pptx", "expo.pptx"),
    ("EXPO.PPTX", "expo.pptx"),
    ("expo", "expo.pptx"),                                               # sin extensión
    ("practica rsa.py", "Seguridad Informática/Codigo/Práctica RSA.py"),  # sin acento
    ("practica3", "practica3 v2.docx"),                                  # parte del nombre
    ("Minería de Texto/Documentos/Doc1.docx", "Minería de Texto/Documentos/Doc1.docx"),
    ("Mineria de Texto\\Documentos\\Doc1.docx", "Minería de Texto/Documentos/Doc1.docx"),
    ("tarea3finalfinal", "tarea3 final FINAL.txt"),                     # sin espacios
    ("tarea3_final_final.txt", "tarea3 final FINAL.txt"),
])
def test_busca_por_nombre_o_ruta(consulta, esperado):
    archivo, candidatos = buscar_archivo(ARCHIVOS, consulta)
    assert archivo is not None and archivo.ruta_relativa == esperado
    assert candidatos == []


def test_nombre_repetido_pide_aclarar():
    archivo, candidatos = buscar_archivo(ARCHIVOS, "doc1.docx")
    assert archivo is None
    assert len(candidatos) == 2


@pytest.mark.parametrize("consulta", ["", "   ", "noexiste.py"])
def test_sin_coincidencias(consulta):
    assert buscar_archivo(ARCHIVOS, consulta) == (None, [])


# -- medición -----------------------------------------------------------------------

def etiqueta(archivo, materia, dificultad="facil"):
    return {"archivo": archivo, "materia": materia, "dificultad": dificultad}


def test_medir_cuenta_aciertos_errores_y_graves():
    filas = [
        fila("a.py", MIN),                                   # acierto
        fila("b.py", SEG),                                   # error grave (se movería)
        fila("c.py", IA, ADVERTIR, 0.5, qwen=True),          # error prudente
        fila("d.py", "_Por revisar", REVISAR, 0.1),          # acierto (debía ir a revisar)
        fila("e.py", MIN, renombrar=True, nuevo="BolsaDePalabras.py"),
        fila("f.py", MIN, renombrar=True, nuevo="nombre malo.py"),
        fila("ajeno.py", MIN),                               # no está etiquetado
    ]
    etiquetas = [etiqueta("a.py", MIN), etiqueta("b.py", IA, "dificil"), etiqueta("c.py", SEG, "dificil"),
                 etiqueta("d.py", "_Por revisar"), etiqueta("e.py", MIN), etiqueta("f.py", MIN),
                 etiqueta("perdido.py", MIN)]
    m = medir(filas, etiquetas)
    assert (m.aciertos, m.total) == (4, 6)
    assert [f.nombre for f in m.graves] == ["b.py"]
    assert [(f.nombre, esperada) for f, esperada in m.errores] == [("b.py", IA), ("c.py", SEG)]
    assert m.por_dificultad == {"facil": [4, 4], "dificil": [0, 2]}
    assert (m.consultas_qwen, m.aciertos_qwen) == (1, 0)
    assert (m.nombres_validos, m.nombres_propuestos) == (1, 2)
    assert m.sin_etiqueta == ["ajeno.py"]
    assert m.faltantes == ["perdido.py"]
    texto = resumen_medicion(m, "reglas")
    assert "4/6 (67%)" in texto and "no cumplida" in texto
    assert "Errores graves (se movería con confianza a la materia equivocada): 1" in texto
    assert "optimistas" in texto


def test_medir_sin_archivos_etiquetados():
    m = medir([fila("ajeno.py", MIN)], [etiqueta("a.py", MIN)])
    assert m.total == 0 and m.exactitud == 0
    assert "--copiar-a" in resumen_medicion(m, "reglas")


def test_medicion_con_el_dataset_real():
    """El mismo resultado que dataset/medir_clasificador.py (solo reglas): >= 85 % y 0 graves."""
    carpeta = ARCHY / "dataset" / "Trabajos_prueba"
    guardian = Guardian(carpeta)
    config = replace(CONFIG, carpeta_raiz=str(carpeta))
    etiquetas = leer_etiquetas(ARCHY / "dataset" / "etiquetas.csv")
    archivos = escanear(guardian, config).archivos
    filas = clasificar_archivos(guardian, config, archivos, Clasificador(config))
    m = medir(filas, etiquetas)
    assert m.total == len(etiquetas) == 75
    assert m.exactitud >= 0.85
    assert m.graves == []
    assert m.nombres_validos == m.nombres_propuestos


def test_medicion_usa_solo_la_carpeta_del_dataset():
    archivos = [SimpleNamespace(nombre=n, ruta_relativa=r) for n, r in [
        ("vdksahdas.py", "vdksahdas.py"),                     # archivo propio del estudiante
        ("vdksahdas.py", "Dataset_prueba/vdksahdas.py"),
        ("Doc1.docx", "Dataset_prueba/Doc1.docx"),
        ("expo.pptx", "Dataset_prueba/expo.pptx"),
        ("tarea.py", "Dataset_prueba/tarea.py"),              # no está etiquetado
    ]]
    elegidos = archivos_del_dataset(archivos, {"vdksahdas.py", "Doc1.docx", "expo.pptx"})
    assert [a.ruta_relativa for a in elegidos] == [
        "Dataset_prueba/vdksahdas.py", "Dataset_prueba/Doc1.docx", "Dataset_prueba/expo.pptx"]
    assert archivos_del_dataset(archivos, {"otro.py"}) == []

import pytest

from nucleo.pistas import ETIQUETA, pista_para

EXT = [".py", ".csv", ".docx", ".pdf", ".txt", ".pptx", ".png"]
TODAS = ["proponer_plan", "ver_archivo", "deshacer", "historial"]


def pista(mensaje):
    return pista_para(mensaje, EXT, TODAS)


@pytest.mark.parametrize("mensaje, archivo", [
    ("que contiene escaneo_red.csv", "escaneo_red.csv"),
    ("escaner.py", "escaner.py"),
    ("que es agente_ids.py", "agente_ids.py"),
    ("¿Qué es Doc1.docx?", "Doc1.docx"),
    ("¿por qué vdksahdas.py va a Minería?", "vdksahdas.py"),
    ("que es tarea3 final FINAL.txt segun lo que estudiaste", "tarea3 final FINAL.txt"),
    ("dime qué hay en practica3 v2.docx", "practica3 v2.docx"),
    ("abre el archivo IMG_20261005.PNG", "IMG_20261005.PNG"),
])
def test_nombre_de_archivo_pide_ver_archivo(mensaje, archivo):
    texto = pista(mensaje)
    assert texto.startswith(ETIQUETA)
    assert f'ver_archivo(nombre="{archivo}")' in texto


def test_varios_archivos():
    texto = pista("compara a1.py y Doc1.docx")
    assert 'ver_archivo(nombre="a1.py")' in texto and 'ver_archivo(nombre="Doc1.docx")' in texto


@pytest.mark.parametrize("mensaje, herramienta", [
    ("organiza mi carpeta Trabajos", "proponer_plan"),
    ("escaneo mis archivos de la carpeta de trabajo", "proponer_plan"),
    ("Clasifica mi carpeta de trabajos dataset_prueba", "proponer_plan"),
    ("deshaz lo que hiciste", "deshacer"),
    ("quiero deshacer los cambios", "deshacer"),
    ("¿qué hiciste?", "historial"),
    ("muéstrame la bitácora", "historial"),
])
def test_intenciones(mensaje, herramienta):
    assert f"llama a {herramienta}()" in pista(mensaje)


def test_aplicar_explica_el_boton():
    texto = pista("aplica el plan que propusiste")
    assert "no puedes mover" in texto and "«Mover»" in texto


@pytest.mark.parametrize("mensaje", ["hola, ¿quién eres?", "gracias", "¿qué materias conoces?", ""])
def test_sin_intencion_clara_no_hay_pista(mensaje):
    assert pista(mensaje) is None


def test_solo_herramientas_disponibles():
    assert pista_para("deshaz", EXT, ["ver_archivo"]) is None
    assert pista_para("que es a.py", EXT, ["proponer_plan"]) is None

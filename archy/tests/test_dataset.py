"""Pruebas de consistencia del dataset de prueba (archy/dataset/)."""

from collections import Counter
from pathlib import Path

import pytest

from dataset import verificar_dataset as v
from nucleo.configuracion import cargar_config

CONFIG = cargar_config(Path(__file__).resolve().parent.parent / "config.yaml")

pytestmark = pytest.mark.skipif(not v.ETIQUETAS.exists(), reason="dataset no generado")


@pytest.fixture(scope="module")
def filas():
    return v.leer_etiquetas()


def test_tamano_entre_60_y_90(filas):
    assert 60 <= len(filas) <= 90


def test_integridad(filas):
    assert v.revisar_integridad(filas, CONFIG, v.CARPETA) == []


def test_cada_materia_tiene_todos_los_tipos(filas):
    conteo = Counter((f["materia"], f["tipo"]) for f in filas)
    for materia in CONFIG.nombres_materias:
        for tipo in CONFIG.tipos:
            assert conteo[(materia, tipo)] >= 1, f"{materia} no tiene archivos de tipo {tipo}"


def test_materias_balanceadas(filas):
    conteo = Counter(f["materia"] for f in filas)
    cantidades = [conteo[m] for m in CONFIG.nombres_materias]
    assert max(cantidades) - min(cantidades) <= 5


def test_incluye_casos_dificiles(filas):
    casos = Counter(f["caso"] for f in filas)
    for caso in ("ambiguo", "ajeno", "sin_informacion", "duplicado", "pista_en_nombre"):
        assert casos[caso] >= 1, f"falta el caso '{caso}'"
    assert sum(1 for f in filas if f["dificultad"] == "dificil") >= len(filas) * 0.1


def test_mayoria_de_nombres_no_descriptivos(filas):
    # El problema real: nombres como vdksahdas.py o Doc1.docx.
    assert sum(1 for f in filas if f["nombre_descriptivo"] == "no") > len(filas) / 2


def test_linea_base_empate_va_a_dudas():
    materia, puntajes = v.linea_base("x.txt", "", CONFIG)
    assert materia == CONFIG.carpeta_dudas and set(puntajes.values()) == {0}


def test_linea_base_ignora_acentos():
    materia, _ = v.linea_base("tarea.txt", "Heurística y búsqueda A*", CONFIG)
    assert materia == "Fundamentos de IA"


def test_verificador_completo_pasa(capsys):
    assert v.main([]) == 0
    salida = capsys.readouterr().out
    assert "✓" in salida and "Línea base" in salida

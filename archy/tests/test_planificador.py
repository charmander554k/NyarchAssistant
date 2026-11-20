from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from nucleo.clasificador import ADVERTIR, MOVER, REVISAR
from nucleo.configuracion import cargar_config
from nucleo.planificador import asignar_destinos, con_sufijo, crear_plan, resumen_plan
from nucleo.reporte import FilaReporte

CONFIG = cargar_config(Path(__file__).resolve().parent.parent / "config.yaml")
SEG, MIN, IA = "Seguridad Informática", "Minería de Texto", "Fundamentos de IA"
DUDAS = CONFIG.carpeta_dudas


def fila(nombre, materia, decision=MOVER, tipo="Codigo", nuevo=None, confianza=0.9):
    return FilaReporte(nombre, nombre, tipo, materia, confianza, decision, "motivo", "reglas", False,
                       nuevo or nombre, nuevo is not None, "motivo nombre")


def archivo(ruta, sha, ubicacion="suelto"):
    return SimpleNamespace(ruta_relativa=ruta, nombre=ruta.rsplit("/", 1)[-1], sha256=sha, ubicacion=ubicacion)


def plan_de(filas, extra=(), config=CONFIG):
    archivos = [archivo(f.ruta_relativa, f"h-{f.nombre}") for f in filas] + list(extra)
    return crear_plan(filas, archivos, config)


def test_destinos_materia_tipo_y_dudas():
    plan = plan_de([fila("a.py", MIN), fila("b.docx", SEG, tipo="Documentos"),
                    fila("c.png", DUDAS, REVISAR, tipo="Otros")])
    assert [a.destino for a in plan.acciones] == [
        f"{MIN}/Codigo/a.py", f"{SEG}/Documentos/b.docx", f"{DUDAS}/c.png"]


def test_aprobados_por_defecto_solo_los_seguros():
    plan = plan_de([fila("a.py", MIN), fila("b.py", IA, ADVERTIR, confianza=0.6),
                    fila("c.png", DUDAS, REVISAR, tipo="Otros")])
    assert [a.aprobada for a in plan.acciones] == [True, False, False]
    assert [a.nombre_original for a in plan.aprobadas] == ["a.py"]


def test_renombrar_segun_config():
    filas = [fila("vdksahdas.py", MIN, nuevo="BolsaDePalabras.py")]
    preguntar = plan_de(filas).acciones[0]
    assert preguntar.renombrar and preguntar.puede_renombrar
    assert preguntar.destino == f"{MIN}/Codigo/BolsaDePalabras.py"

    nunca = plan_de(filas, config=replace(CONFIG, permitir_renombrar="nunca")).acciones[0]
    assert not nunca.renombrar and not nunca.puede_renombrar
    assert nunca.destino == f"{MIN}/Codigo/vdksahdas.py"


def test_en_dudas_no_se_renombra_por_defecto():
    a = plan_de([fila("Doc1.docx", DUDAS, REVISAR, tipo="Documentos", nuevo="Algo.docx")]).acciones[0]
    assert a.puede_renombrar and not a.renombrar
    assert a.destino == f"{DUDAS}/Doc1.docx"


def test_nunca_pisa_un_archivo_existente():
    existente = archivo(f"{MIN}/Codigo/a.py", "otro-hash", "organizado")
    a = plan_de([fila("a.py", MIN)], extra=[existente]).acciones[0]
    assert a.destino == f"{MIN}/Codigo/a_2.py"
    assert "se usa a_2.py" in a.nota


def test_existente_sin_importar_mayusculas():
    existente = archivo(f"{MIN}/Codigo/A.PY", "otro-hash", "organizado")
    assert plan_de([fila("a.py", MIN)], extra=[existente]).acciones[0].destino == f"{MIN}/Codigo/a_2.py"


def test_dos_archivos_al_mismo_destino():
    filas = [fila("x.py", MIN, nuevo="Tarea.py"), fila("y.py", MIN, nuevo="Tarea.py"),
             fila("z.py", MIN, nuevo="Tarea.py")]
    assert [a.destino for a in plan_de(filas).acciones] == [
        f"{MIN}/Codigo/Tarea.py", f"{MIN}/Codigo/Tarea_2.py", f"{MIN}/Codigo/Tarea_3.py"]


def test_las_aprobadas_reservan_primero():
    filas = [fila("x.py", MIN, ADVERTIR, nuevo="Tarea.py"), fila("y.py", MIN, nuevo="Tarea.py")]
    plan = plan_de(filas)
    assert plan.acciones[1].destino == f"{MIN}/Codigo/Tarea.py"       # la aprobada conserva el nombre
    assert plan.acciones[0].destino == f"{MIN}/Codigo/Tarea_2.py"


def test_duplicados_se_marcan_y_no_se_aprueban():
    filas = [fila("tarea.py", MIN), fila("copia de tarea.py", MIN)]
    archivos = [archivo("tarea.py", "mismo"), archivo("copia de tarea.py", "mismo")]
    plan = crear_plan(filas, archivos, CONFIG)
    assert plan.acciones[0].aprobada and plan.acciones[0].duplicado_de is None
    assert not plan.acciones[1].aprobada
    assert plan.acciones[1].duplicado_de == "tarea.py"
    assert "mismo contenido que tarea.py" in plan.acciones[1].nota


def test_duplicado_de_un_archivo_ya_organizado():
    organizado = archivo(f"{MIN}/Codigo/tarea.py", "mismo", "organizado")
    filas = [fila("otra.py", MIN)]
    plan = crear_plan(filas, [archivo("otra.py", "mismo"), organizado], CONFIG)
    assert plan.acciones[0].duplicado_de == f"{MIN}/Codigo/tarea.py"
    assert not plan.acciones[0].aprobada


def test_editar_el_plan_recalcula_destinos():
    plan = plan_de([fila("vdksahdas.py", MIN, nuevo="BolsaDePalabras.py"), fila("b.py", IA)])
    a, b = plan.acciones
    a.materia = SEG                  # el estudiante corrige la materia
    a.renombrar = False              # y prefiere conservar el nombre
    b.materia = DUDAS
    asignar_destinos(plan, CONFIG, [])
    assert a.destino == f"{SEG}/Codigo/vdksahdas.py"
    assert b.destino == f"{DUDAS}/b.py"


@pytest.mark.parametrize("nombre, n, esperado", [
    ("Tarea.py", 1, "Tarea.py"), ("Tarea.py", 2, "Tarea_2.py"), ("README", 3, "README_3"),
    ("datos.tar.gz", 2, "datos.tar_2.gz"),
])
def test_con_sufijo(nombre, n, esperado):
    assert con_sufijo(nombre, n) == esperado


def test_resumen_solo_datos():
    texto = resumen_plan(plan_de([fila("a.py", MIN), fila("b.py", IA, ADVERTIR, confianza=0.5)]), CONFIG)
    assert "2 archivos" in texto and "1 marcados para mover" in texto
    assert "Con advertencia: 1" in texto
    assert resumen_plan(plan_de([]), CONFIG).startswith("No hay archivos")

"""Pruebas del ejecutor y la bitácora: mover, simular, no sobrescribir, deshacer."""
import os
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from nucleo.bitacora import Bitacora
from nucleo.clasificador import Clasificador
from nucleo.configuracion import cargar_config
from nucleo.ejecutor import ERROR, MOVIDO, OMITIDO, SIMULADO, aplicar, deshacer
from nucleo.escaner import calcular_sha256, escanear
from nucleo.planificador import crear_plan
from nucleo.reporte import clasificar_archivos

CONFIG = cargar_config(Path(__file__).resolve().parent.parent / "config.yaml")
MIN, SEG = "Minería de Texto", "Seguridad Informática"
SECRETO = "contenido-secreto-que-no-debe-quedar-en-la-bitacora"


def huellas(raiz: Path) -> dict[str, str]:
    """Nombre relativo -> SHA-256 de todos los archivos (la prueba de deshacer compara esto)."""
    return {p.relative_to(raiz).as_posix(): calcular_sha256(p) for p in raiz.rglob("*") if p.is_file()}


@pytest.fixture
def caso(entorno):
    raiz = entorno.raiz
    (raiz / "tarea.py").unlink()
    (raiz / "vdksahdas.py").write_text(f"import nltk\nfrom sklearn import TfidfVectorizer\n# {SECRETO}\n",
                                       encoding="utf-8")
    (raiz / "Doc1.txt").write_text("Informe de vulnerabilidades\nEscaneo con nmap y cifrado RSA.\n",
                                   encoding="utf-8")
    (raiz / "IMG_2026.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
    config = replace(CONFIG, carpeta_raiz=str(raiz))
    bitacora = Bitacora(entorno.zona / "datos" / "bitacora.sqlite3")   # fuera de Trabajos

    def nuevo_plan():
        escaneo = escanear(entorno.guardian, config)
        sueltos = [a for a in escaneo.archivos if a.ubicacion == "suelto"]
        filas = clasificar_archivos(entorno.guardian, config, sueltos, Clasificador(config))
        return crear_plan(filas, escaneo.archivos, config)

    caso = type("Caso", (), {})()
    caso.raiz, caso.guardian, caso.config, caso.bitacora, caso.plan = raiz, entorno.guardian, config, bitacora, nuevo_plan
    caso.zona = entorno.zona
    return caso


def accion(plan, nombre):
    return next(a for a in plan.acciones if a.nombre_original == nombre)


def test_simular_no_toca_nada(caso):
    antes = huellas(caso.raiz)
    plan = caso.plan()
    op, resultados = aplicar(plan.acciones, caso.guardian, caso.bitacora, simular=True)
    assert huellas(caso.raiz) == antes
    assert {r.estado for r in resultados} == {SIMULADO}
    assert not caso.bitacora.operacion(op).deshacible          # una simulación no se deshace


def test_mueve_solo_lo_aprobado_y_renombra(caso):
    plan = caso.plan()
    imagen = accion(plan, "IMG_2026.png")
    assert not imagen.aprobada
    _, resultados = aplicar(plan.acciones, caso.guardian, caso.bitacora, simular=False)
    assert all(r.estado == MOVIDO for r in resultados)
    assert (caso.raiz / "IMG_2026.png").exists()               # no aprobada: no se movió
    assert (caso.raiz / SEG / "Documentos" / "InformeDeVulnerabilidades.txt").exists()
    assert not (caso.raiz / "Doc1.txt").exists()


def test_nunca_borra_ni_pierde_archivos(caso):
    antes = sorted(huellas(caso.raiz).values())
    plan = caso.plan()
    for a in plan.acciones:
        a.aprobada = True
    aplicar(plan.acciones, caso.guardian, caso.bitacora, simular=False)
    assert sorted(huellas(caso.raiz).values()) == antes       # mismo contenido, solo cambian lugares


def test_no_sobrescribe_si_el_destino_aparece_despues_del_plan(caso):
    plan = caso.plan()
    a = accion(plan, "vdksahdas.py")
    ocupado = caso.raiz / a.destino
    ocupado.parent.mkdir(parents=True)
    ocupado.write_text("otro archivo del estudiante", encoding="utf-8")
    _, resultados = aplicar([a], caso.guardian, caso.bitacora, simular=False)
    assert resultados[0].estado == MOVIDO
    assert resultados[0].destino.endswith("_2.py")
    assert ocupado.read_text(encoding="utf-8") == "otro archivo del estudiante"


def test_archivo_modificado_despues_del_plan_no_se_mueve(caso):
    plan = caso.plan()
    (caso.raiz / "vdksahdas.py").write_text("cambió", encoding="utf-8")
    _, resultados = aplicar([accion(plan, "vdksahdas.py")], caso.guardian, caso.bitacora, simular=False)
    assert resultados[0].estado == OMITIDO and "cambió" in resultados[0].detalle
    assert (caso.raiz / "vdksahdas.py").exists()


def test_archivo_que_ya_no_esta(caso):
    plan = caso.plan()
    os.rename(caso.raiz / "vdksahdas.py", caso.raiz / "otro_nombre.py")
    _, resultados = aplicar([accion(plan, "vdksahdas.py")], caso.guardian, caso.bitacora, simular=False)
    assert resultados[0].estado == OMITIDO


@pytest.mark.parametrize("destino", ["../fuera/robado.py", "/etc/robado.py", ".oculta/x.py", "~/.ssh/x.py"])
def test_guardian_bloquea_destinos_y_queda_en_la_bitacora(caso, destino):
    plan = caso.plan()
    a = accion(plan, "vdksahdas.py")
    a.destino = destino
    _, resultados = aplicar([a], caso.guardian, caso.bitacora, simular=False)
    assert resultados[0].estado == ERROR and "guardián" in resultados[0].detalle
    assert (caso.raiz / "vdksahdas.py").exists()
    assert caso.bitacora.bloqueos(1)[0].ruta == destino


def test_deshacer_deja_las_huellas_identicas(caso):
    """Meta de evaluación: hashes de la carpeta antes y después de deshacer, idénticos."""
    antes = huellas(caso.raiz)
    plan = caso.plan()
    for a in plan.acciones:
        a.aprobada = True
    op, _ = aplicar(plan.acciones, caso.guardian, caso.bitacora, simular=False)
    assert huellas(caso.raiz) != antes
    assert caso.bitacora.ultima_deshacible(str(caso.raiz)).id == op
    _, resultados = deshacer(caso.bitacora, caso.guardian, op)
    assert all(r.estado == MOVIDO for r in resultados)
    assert huellas(caso.raiz) == antes
    assert caso.bitacora.ultima_deshacible(str(caso.raiz)) is None
    _, otra_vez = deshacer(caso.bitacora, caso.guardian, op)       # no se deshace dos veces
    assert otra_vez[0].estado == OMITIDO


def test_deshacer_respeta_cambios_del_estudiante(caso):
    plan = caso.plan()
    op, resultados = aplicar(plan.acciones, caso.guardian, caso.bitacora, simular=False)
    movido = caso.raiz / next(r.destino for r in resultados if r.origen == "vdksahdas.py")
    movido.write_text("el estudiante lo editó", encoding="utf-8")
    (caso.raiz / "Doc1.txt").write_text("nuevo archivo en el lugar original", encoding="utf-8")
    _, deshechos = deshacer(caso.bitacora, caso.guardian, op)
    estados = {r.destino: (r.estado, r.detalle) for r in deshechos}
    assert estados["vdksahdas.py"][0] == ERROR and "cambió" in estados["vdksahdas.py"][1]
    assert estados["Doc1.txt"][0] == ERROR and "ocupado" in estados["Doc1.txt"][1]
    assert movido.read_text(encoding="utf-8") == "el estudiante lo editó"
    assert caso.bitacora.ultima_deshacible(str(caso.raiz)).id == op   # sigue pendiente


def test_deshacer_funciona_como_pila(caso):
    plan = caso.plan()
    primera, _ = aplicar([accion(plan, "vdksahdas.py")], caso.guardian, caso.bitacora, simular=False)
    plan = caso.plan()
    segunda, _ = aplicar([accion(plan, "Doc1.txt")], caso.guardian, caso.bitacora, simular=False)
    assert caso.bitacora.ultima_deshacible(str(caso.raiz)).id == segunda
    deshacer(caso.bitacora, caso.guardian, segunda)
    assert caso.bitacora.ultima_deshacible(str(caso.raiz)).id == primera


def test_la_bitacora_no_guarda_contenido(caso):
    plan = caso.plan()
    aplicar(plan.acciones, caso.guardian, caso.bitacora, simular=False)
    datos = caso.bitacora.ruta.read_bytes()
    assert SECRETO.encode() not in datos
    assert b"vdksahdas.py" in datos                                  # rutas y metadatos sí
    with sqlite3.connect(caso.bitacora.ruta) as c:
        columnas = {r[1] for t in ("operaciones", "movimientos", "bloqueos")
                    for r in c.execute(f"pragma table_info({t})")}
    assert not columnas & {"texto", "contenido"}


def test_historial_de_operaciones(caso):
    plan = caso.plan()
    aplicar(plan.acciones, caso.guardian, caso.bitacora, simular=True)
    op, _ = aplicar(plan.acciones, caso.guardian, caso.bitacora, simular=False)
    ops = caso.bitacora.operaciones()
    assert [o.tipo for o in ops] == ["aplicar", "aplicar"]
    assert ops[0].id == op and not ops[0].simulacion and ops[0].movidos == len(plan.aprobadas)
    assert ops[1].simulacion and ops[1].movidos == 0
    assert [m.estado for m in caso.bitacora.movimientos(op)] == [MOVIDO] * len(plan.aprobadas)


def test_nada_aprobado_no_crea_operacion(caso):
    plan = caso.plan()
    for a in plan.acciones:
        a.aprobada = False
    assert aplicar(plan.acciones, caso.guardian, caso.bitacora, simular=False) == (None, [])
    assert caso.bitacora.operaciones() == []


def test_no_existe_funcion_de_borrar():
    import nucleo.ejecutor as ejecutor
    codigo = Path(ejecutor.__file__).read_text(encoding="utf-8")
    for prohibido in ("os.remove(", "unlink(", "rmtree(", "os.rmdir(", "shutil.move("):
        assert prohibido not in codigo

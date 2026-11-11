import os
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from nucleo.guardian import Guardian


@pytest.fixture
def zona(tmp_path):
    """Carpeta temporal para las pruebas.

    En Windows la carpeta temporal normal está dentro de AppData, que el
    guardián bloquea (a propósito). Por eso ahí se usa una carpeta junto a las
    pruebas, que se borra al terminar.
    """
    if os.name != "nt":
        yield tmp_path
        return
    base = Path(__file__).resolve().parent / "_tmp_pruebas" / uuid.uuid4().hex[:8]
    base.mkdir(parents=True)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def entorno(zona):
    """Un estudiante con su carpeta Trabajos, una carpeta de afuera y ~/.ssh."""
    home = zona / "home" / "estudiante"
    raiz = home / "Documentos" / "Trabajos"
    (raiz / "sub").mkdir(parents=True)
    (raiz / "tarea.py").write_text("print('hola')", encoding="utf-8")

    fuera = zona / "fuera"
    fuera.mkdir()
    (fuera / "secreto.txt").write_text("no deberías leer esto", encoding="utf-8")

    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_rsa").write_text("clave privada", encoding="utf-8")

    return SimpleNamespace(
        guardian=Guardian(raiz, home=home),
        raiz=raiz,
        home=home,
        fuera=fuera,
        zona=zona,
    )

import dataclasses
import hashlib
import os
from pathlib import Path

import pytest

from nucleo import escaner as modulo_escaner
from nucleo.configuracion import cargar_config
from nucleo.escaner import calcular_sha256, escanear

CONFIG_REAL = Path(__file__).resolve().parent.parent / "config.yaml"


def escribir(ruta: Path, contenido: str = "x") -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


@pytest.fixture
def config():
    # Límite de tamaño pequeño para poder probar "archivo demasiado grande".
    return dataclasses.replace(cargar_config(CONFIG_REAL), tamano_maximo_bytes=200)


@pytest.fixture
def carpeta(entorno):
    """La carpeta Trabajos de un estudiante, revuelta y con trampas."""
    r = entorno.raiz
    # entorno ya trae: tarea.py y sub/
    escribir(r / "vdksahdas.py", "import nltk\nprint('tokens')")
    escribir(r / "notas.txt", "apuntes de criptografía")
    escribir(r / "datos.csv", "texto,etiqueta\nhola,1")
    escribir(r / "expo.pptx", "pptx falso")
    escribir(r / "foto.png", "png falso")
    escribir(r / "sub" / "anidado.ipynb", "{}")
    escribir(r / ".oculto.txt", "secreto")
    escribir(r / ".git" / "config", "[core]")
    escribir(r / "~$informe.docx", "temporal de Word")
    escribir(r / "grande.pdf", "x" * 500)
    escribir(r / "Fundamentos de IA" / "Codigo" / "perceptron.py", "class Perceptron: pass")
    escribir(r / "_Por revisar" / "raro.bin", "???")
    escribir(r / "atajo.lnk", "acceso directo")
    return entorno


def por_ruta(resultado):
    return {a.ruta_relativa: a for a in resultado.archivos}


def motivos(resultado):
    return {o.ruta_relativa: o.motivo for o in resultado.omitidos}


def test_lista_los_archivos_permitidos(carpeta, config):
    resultado = escanear(carpeta.guardian, config)
    assert [a.ruta_relativa for a in resultado.archivos] == [
        "_Por revisar/raro.bin",
        "datos.csv",
        "expo.pptx",
        "foto.png",
        "Fundamentos de IA/Codigo/perceptron.py",
        "notas.txt",
        "sub/anidado.ipynb",
        "tarea.py",
        "vdksahdas.py",
    ]


def test_tipos_segun_config(carpeta, config):
    archivos = por_ruta(escanear(carpeta.guardian, config))
    assert archivos["vdksahdas.py"].tipo == "Codigo"
    assert archivos["sub/anidado.ipynb"].tipo == "Codigo"
    assert archivos["notas.txt"].tipo == "Documentos"
    assert archivos["datos.csv"].tipo == "Datos"
    assert archivos["expo.pptx"].tipo == "Presentaciones"
    assert archivos["foto.png"].tipo == "Otros"  # extensión no listada


def test_omite_con_motivo(carpeta, config):
    m = motivos(escanear(carpeta.guardian, config))
    assert "oculta" in m[".oculto.txt"]
    assert "oculta" in m[".git"]  # ni siquiera entra a la carpeta
    assert ".lnk" in m["atajo.lnk"]
    assert "temporal de Office" in m["~$informe.docx"]
    assert "pesa más de" in m["grande.pdf"]


def test_no_entra_a_carpetas_ocultas(carpeta, config):
    resultado = escanear(carpeta.guardian, config)
    assert not any(a.ruta_relativa.startswith(".git") for a in resultado.archivos)
    assert ".git/config" not in motivos(resultado)


def test_detecta_ubicacion(carpeta, config):
    archivos = por_ruta(escanear(carpeta.guardian, config))
    organizado = archivos["Fundamentos de IA/Codigo/perceptron.py"]
    assert organizado.ubicacion == "organizado"
    assert organizado.materia_actual == "Fundamentos de IA"
    assert organizado.tipo_actual == "Codigo"
    assert archivos["_Por revisar/raro.bin"].ubicacion == "por_revisar"
    assert archivos["vdksahdas.py"].ubicacion == "suelto"
    assert archivos["sub/anidado.ipynb"].ubicacion == "suelto"


def test_datos_de_cada_archivo(carpeta, config):
    archivo = por_ruta(escanear(carpeta.guardian, config))["vdksahdas.py"]
    contenido = (carpeta.raiz / "vdksahdas.py").read_bytes()
    assert archivo.sha256 == hashlib.sha256(contenido).hexdigest()
    assert archivo.tamano_bytes == len(contenido)
    assert archivo.extension == ".py"
    assert archivo.nombre == "vdksahdas.py"
    assert Path(archivo.ruta) == carpeta.raiz / "vdksahdas.py"
    assert "T" in archivo.modificado  # formato ISO


def test_extension_en_minusculas(carpeta, config):
    escribir(carpeta.raiz / "INFORME.PDF", "pdf")
    archivo = por_ruta(escanear(carpeta.guardian, config))["INFORME.PDF"]
    assert archivo.extension == ".pdf"
    assert archivo.tipo == "Documentos"


def test_resultado_estable(carpeta, config):
    a = escanear(carpeta.guardian, config).a_dict()
    b = escanear(carpeta.guardian, config).a_dict()
    assert a == b


def test_resumen(carpeta, config):
    resumen = escanear(carpeta.guardian, config).resumen()
    assert resumen["archivos"] == 9
    assert resumen["por_tipo"]["Codigo"] == 4
    assert resumen["por_ubicacion"] == {"organizado": 1, "por_revisar": 1, "suelto": 7}
    assert resumen["limite_alcanzado"] is False


def test_limite_de_archivos(carpeta, config):
    resultado = escanear(carpeta.guardian, config, limite=3)
    assert len(resultado.archivos) == 3
    assert resultado.limite_alcanzado is True


def test_archivo_que_no_se_puede_leer(carpeta, config, monkeypatch):
    original = modulo_escaner.calcular_sha256

    def falla_con_notas(ruta):
        if Path(ruta).name == "notas.txt":
            raise PermissionError(13, "Permission denied")
        return original(ruta)

    monkeypatch.setattr(modulo_escaner, "calcular_sha256", falla_con_notas)
    resultado = escanear(carpeta.guardian, config)
    assert "notas.txt" not in por_ruta(resultado)
    assert "¿está abierto" in motivos(resultado)["notas.txt"]


def test_symlink_no_se_sigue(carpeta, config):
    try:
        os.symlink(carpeta.fuera, carpeta.raiz / "atajo", target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"este sistema no permite crear symlinks: {error}")
    resultado = escanear(carpeta.guardian, config)
    assert "enlace" in motivos(resultado)["atajo"]
    assert not any("secreto" in a.ruta_relativa for a in resultado.archivos)


@pytest.mark.skipif(os.name != "nt", reason="las junctions solo existen en Windows")
def test_junction_no_se_sigue(carpeta, config):
    import _winapi

    enlace = carpeta.raiz / "atajo"
    _winapi.CreateJunction(str(carpeta.fuera), str(enlace))
    try:
        resultado = escanear(carpeta.guardian, config)
        assert "enlace" in motivos(resultado)["atajo"]
        assert not any("secreto" in a.ruta_relativa for a in resultado.archivos)
    finally:
        os.rmdir(enlace)


def test_carpeta_vacia(entorno, config):
    (entorno.raiz / "tarea.py").unlink()
    resultado = escanear(entorno.guardian, config)
    assert resultado.archivos == []
    assert resultado.resumen()["archivos"] == 0


def test_sha256_por_bloques(zona):
    grande = zona / "bloques.bin"
    grande.write_bytes(os.urandom(3 * 1024 * 1024 + 7))
    assert calcular_sha256(grande) == hashlib.sha256(grande.read_bytes()).hexdigest()

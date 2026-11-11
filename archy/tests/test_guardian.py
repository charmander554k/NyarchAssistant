"""Pruebas de seguridad del guardián (metas de evaluación de CLAUDE.md).

Cada intento de escape debe bloquearse con un motivo claro.
"""

import os
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from nucleo.guardian import (
    AccesoDenegado,
    ConfiguracionInvalida,
    Guardian,
    motivo_lista_negra,
)

EN_WINDOWS = os.name == "nt"


def crear_symlink(destino: Path, enlace: Path) -> None:
    try:
        os.symlink(destino, enlace, target_is_directory=destino.is_dir())
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"este sistema no permite crear symlinks: {error}")


def denegada(guardian: Guardian, ruta) -> str:
    """Comprueba que la ruta se bloquea y devuelve el motivo."""
    with pytest.raises(AccesoDenegado) as info:
        guardian.validar(ruta)
    decision = guardian.revisar(ruta)
    assert decision.permitido is False
    assert decision.motivo == info.value.motivo
    return info.value.motivo


# ---------------------------------------------------------------------------
# Lo que SÍ se permite
# ---------------------------------------------------------------------------

def test_permite_archivo_relativo(entorno):
    assert entorno.guardian.validar("tarea.py") == entorno.raiz / "tarea.py"


def test_permite_archivo_absoluto(entorno):
    ruta = entorno.raiz / "tarea.py"
    assert entorno.guardian.validar(str(ruta)) == ruta


def test_permite_la_carpeta_raiz(entorno):
    assert entorno.guardian.validar(entorno.raiz) == entorno.raiz


def test_permite_destino_que_aun_no_existe(entorno):
    destino = entorno.guardian.validar("Fundamentos de IA/Codigo/Perceptron.py")
    assert destino == entorno.raiz / "Fundamentos de IA" / "Codigo" / "Perceptron.py"


def test_revisar_devuelve_decision_permitida(entorno):
    decision = entorno.guardian.revisar("sub")
    assert decision.permitido is True
    assert decision.ruta == str(entorno.raiz / "sub")


# ---------------------------------------------------------------------------
# Fuera de la carpeta y rutas con ..
# ---------------------------------------------------------------------------

def test_bloquea_ruta_fuera_de_la_raiz(entorno):
    motivo = denegada(entorno.guardian, entorno.fuera / "secreto.txt")
    assert "fuera de la carpeta" in motivo


@pytest.mark.parametrize("ruta", [
    "../secreto.txt",
    "../../../fuera/secreto.txt",
    "sub/../../Trabajos/tarea.py",
    "sub/../tarea.py",  # aunque quede dentro, '..' nunca se acepta
])
def test_bloquea_rutas_con_puntos(entorno, ruta):
    assert "'..'" in denegada(entorno.guardian, ruta)


def test_bloquea_puntos_en_ruta_absoluta(entorno):
    ruta = f"{entorno.raiz}{os.sep}..{os.sep}..{os.sep}secreto.txt"
    assert "'..'" in denegada(entorno.guardian, ruta)


# ---------------------------------------------------------------------------
# Ocultos, accesos directos y carpeta personal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ruta", [".git/config", "sub/.oculto.txt", ".env"])
def test_bloquea_ocultos(entorno, ruta):
    assert "oculta" in denegada(entorno.guardian, ruta)


@pytest.mark.parametrize("ruta", ["atajo.lnk", "sub/ATAJO.LNK"])
def test_bloquea_accesos_directos_lnk(entorno, ruta):
    assert ".lnk" in denegada(entorno.guardian, ruta)


def test_bloquea_llaves_ssh(entorno):
    assert "~/.ssh" in denegada(entorno.guardian, "~/.ssh/id_rsa")


def test_bloquea_carpeta_personal_completa(entorno):
    assert "carpeta personal" in denegada(entorno.guardian, "~")


# ---------------------------------------------------------------------------
# Enlaces simbólicos y junctions
# ---------------------------------------------------------------------------

def test_bloquea_symlink_que_apunta_afuera(entorno):
    crear_symlink(entorno.fuera, entorno.raiz / "atajo")
    assert "enlace" in denegada(entorno.guardian, "atajo/secreto.txt")
    assert "enlace" in denegada(entorno.guardian, "atajo")


def test_bloquea_symlink_aunque_apunte_adentro(entorno):
    crear_symlink(entorno.raiz / "tarea.py", entorno.raiz / "sub" / "copia.py")
    assert "enlace" in denegada(entorno.guardian, "sub/copia.py")


@pytest.mark.skipif(not EN_WINDOWS, reason="las junctions solo existen en Windows")
def test_bloquea_junction_de_windows(entorno):
    import _winapi

    enlace = entorno.raiz / "atajo"
    _winapi.CreateJunction(str(entorno.fuera), str(enlace))
    try:
        assert "enlace" in denegada(entorno.guardian, "atajo/secreto.txt")
        assert "enlace" in denegada(entorno.guardian, "atajo")
    finally:
        os.rmdir(enlace)  # quita la junction sin tocar su destino


# ---------------------------------------------------------------------------
# Carpetas del sistema
# ---------------------------------------------------------------------------

@pytest.mark.skipif(EN_WINDOWS, reason="rutas de Linux/WSL")
@pytest.mark.parametrize("ruta", [
    "/etc/passwd",
    "/root/.bashrc",
    "/proc/self/environ",
    "/mnt/c/Windows/System32/config/SAM",
    "/mnt/c/Users/estudiante/AppData/Roaming/x",
])
def test_bloquea_carpetas_del_sistema_linux(entorno, ruta):
    assert "lista negra" in denegada(entorno.guardian, ruta)


@pytest.mark.skipif(EN_WINDOWS, reason="en Linux/WSL una ruta C:\\ no es válida")
def test_bloquea_ruta_de_windows_escrita_en_linux(entorno):
    assert "ruta de Windows" in denegada(entorno.guardian, "C:\\Windows\\System32")


@pytest.mark.skipif(not EN_WINDOWS, reason="rutas de Windows")
@pytest.mark.parametrize("ruta", [
    "C:\\Windows\\System32\\config\\SAM",
    "C:\\Program Files\\App\\app.exe",
    "C:\\ProgramData\\x",
    "\\\\servidor\\compartido\\x",
])
def test_bloquea_carpetas_del_sistema_windows(entorno, ruta):
    assert "lista negra" in denegada(entorno.guardian, ruta)


def test_lista_negra_extra_de_config(entorno):
    privado = entorno.raiz / "privado"
    privado.mkdir()
    guardian = Guardian(entorno.raiz, lista_negra_extra=[privado], home=entorno.home)
    assert "configurada" in denegada(guardian, "privado/diario.txt")
    assert guardian.validar("tarea.py") == entorno.raiz / "tarea.py"


@pytest.mark.parametrize("ruta", ["", "   ", "tarea\x00.py"])
def test_bloquea_rutas_vacias_o_raras(entorno, ruta):
    denegada(entorno.guardian, ruta)


# ---------------------------------------------------------------------------
# Carpeta raíz mal configurada
# ---------------------------------------------------------------------------

def test_raiz_que_no_existe(entorno):
    with pytest.raises(ConfiguracionInvalida, match="no existe"):
        Guardian(entorno.zona / "no_existe", home=entorno.home)


def test_raiz_que_es_archivo(entorno):
    with pytest.raises(ConfiguracionInvalida, match="no es una carpeta"):
        Guardian(entorno.raiz / "tarea.py", home=entorno.home)


def test_raiz_relativa(entorno):
    with pytest.raises(ConfiguracionInvalida, match="ruta completa"):
        Guardian("Trabajos", home=entorno.home)


def test_raiz_con_puntos(entorno):
    with pytest.raises(ConfiguracionInvalida, match=r"\.\."):
        Guardian(f"{entorno.raiz}{os.sep}..{os.sep}Trabajos", home=entorno.home)


def test_raiz_no_puede_ser_la_carpeta_personal(entorno):
    with pytest.raises(ConfiguracionInvalida, match="carpeta personal"):
        Guardian(entorno.home, home=entorno.home)


def test_raiz_no_puede_ser_un_enlace(entorno):
    enlace = entorno.zona / "enlace_raiz"
    crear_symlink(entorno.raiz, enlace)
    with pytest.raises(ConfiguracionInvalida, match="enlace"):
        Guardian(enlace, home=entorno.home)


@pytest.mark.parametrize("raiz", ["C:\\", "C:\\Windows"] if EN_WINDOWS else ["/", "/etc", "/mnt/c"])
def test_raiz_no_puede_ser_del_sistema(entorno, raiz):
    with pytest.raises(ConfiguracionInvalida, match="no es segura"):
        Guardian(raiz, home=entorno.home)


# ---------------------------------------------------------------------------
# Lista negra (sin tocar el disco; corre igual en cualquier sistema)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ruta", [
    "/", "/etc", "/etc/passwd", "/usr/bin/python3", "/bin", "/boot/grub",
    "/root", "/var/log/syslog", "/proc/1/environ", "/sys/kernel", "/home",
    "/mnt", "/mnt/c", "/mnt/d",
    "/mnt/c/Windows/System32", "/mnt/c/WINDOWS/system32",
    "/mnt/c/Program Files/App", "/mnt/c/Program Files (x86)/App",
    "/mnt/c/ProgramData/x", "/mnt/c/Users", "/mnt/c/Users/rober",
    "/mnt/c/Users/rober/AppData/Local/x", "/mnt/c/users/rober/appdata",
])
def test_lista_negra_posix_bloquea(ruta):
    assert motivo_lista_negra(PurePosixPath(ruta)) is not None


@pytest.mark.parametrize("ruta", [
    "/mnt/c/Users/rober/Documents/Trabajos",
    "/mnt/c/Users/rober/Documents/Trabajos/tarea.py",
    "/home/rober/Documentos/Trabajos/tarea.py",
])
def test_lista_negra_posix_permite(ruta):
    assert motivo_lista_negra(PurePosixPath(ruta), PurePosixPath("/home/rober")) is None


@pytest.mark.parametrize("ruta", [
    "/home/rober", "/home/rober/.ssh/id_rsa", "/home/rober/.config/x", "/home/rober/.var/app",
])
def test_lista_negra_home_posix(ruta):
    assert motivo_lista_negra(PurePosixPath(ruta), PurePosixPath("/home/rober")) is not None


@pytest.mark.parametrize("ruta", [
    "C:\\", "D:\\", "C:\\Windows\\System32", "c:\\windows",
    "C:\\Program Files\\x", "C:\\Program Files (x86)\\x", "C:\\ProgramData\\x",
    "C:\\Users", "C:\\Users\\rober", "C:\\Users\\rober\\AppData\\Roaming\\x",
    "\\\\servidor\\compartido\\x",
])
def test_lista_negra_windows_bloquea(ruta):
    assert motivo_lista_negra(PureWindowsPath(ruta)) is not None


@pytest.mark.parametrize("ruta", [
    "C:\\Users\\rober\\Documents\\Trabajos\\tarea.py",
    "D:\\Escuela\\Trabajos",
])
def test_lista_negra_windows_permite(ruta):
    assert motivo_lista_negra(PureWindowsPath(ruta), PureWindowsPath("C:\\Users\\rober")) is None

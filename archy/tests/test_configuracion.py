import copy
from pathlib import Path

import pytest
import yaml

from nucleo.configuracion import ConfigInvalida, cargar_config, config_desde_dict

CONFIG_REAL = Path(__file__).resolve().parent.parent / "config.yaml"


@pytest.fixture
def base():
    return yaml.safe_load(CONFIG_REAL.read_text(encoding="utf-8"))


def errores_de(datos) -> list[str]:
    with pytest.raises(ConfigInvalida) as info:
        config_desde_dict(datos)
    return info.value.errores


def test_el_config_del_repo_es_valido():
    config = cargar_config(CONFIG_REAL)
    assert config.modo == "simulacion"
    assert config.carpeta_dudas == "_Por revisar"
    assert config.tamano_maximo_bytes == 50 * 1024 * 1024
    assert config.umbrales.alto == 0.70 and config.umbrales.bajo == 0.45
    assert config.nombres_materias == ("Seguridad Informática", "Minería de Texto", "Fundamentos de IA")


@pytest.mark.parametrize("extension, tipo", [
    (".py", "Codigo"), (".PY", "Codigo"), (".docx", "Documentos"),
    (".csv", "Datos"), (".pptx", "Presentaciones"), (".zip", "Otros"), ("", "Otros"),
])
def test_tipo_de_extension(extension, tipo):
    assert cargar_config(CONFIG_REAL).tipo_de(extension) == tipo


def test_palabras_clave_en_minusculas(base):
    base["materias"][0]["palabras_clave"] = ["NMAP", " Firewall "]
    config = config_desde_dict(base)
    assert config.materias[0].palabras_clave == ("nmap", "firewall")


def test_clave_desconocida(base):
    base["umbral"] = 0.5
    assert "desconocidas" in errores_de(base)[0]


def test_clave_faltante(base):
    del base["materias"]
    assert "faltan" in errores_de(base)[0]


@pytest.mark.parametrize("cambio, texto", [
    ({"modo": "rapido"}, "modo"),
    ({"permitir_renombrar": "a veces"}, "permitir_renombrar"),
    ({"organizar_por_parcial": True}, "parcial"),
    ({"tamano_maximo_mb": 0}, "tamano_maximo_mb"),
    ({"umbrales": {"alto": 0.4, "bajo": 0.6}}, "umbrales"),
    ({"caracteres_a_leer": -1}, "caracteres_a_leer"),
    ({"carpeta_dudas": "../fuera"}, "carpeta_dudas"),
    ({"lista_negra_extra": "/etc"}, "lista_negra_extra"),
])
def test_valores_invalidos(base, cambio, texto):
    base.update(cambio)
    assert any(texto in e for e in errores_de(base))


def test_extension_en_dos_tipos(base):
    base["tipos"]["Datos"].append(".py")
    assert any("dos tipos" in e for e in errores_de(base))


def test_extension_sin_punto(base):
    base["tipos"]["Codigo"].append("py")
    assert any("debe empezar con punto" in e for e in errores_de(base))


def test_falta_tipo_otros(base):
    del base["tipos"]["Otros"]
    assert any("Otros" in e for e in errores_de(base))


def test_materia_repetida(base):
    base["materias"].append(copy.deepcopy(base["materias"][0]))
    assert any("repetida" in e for e in errores_de(base))


def test_reporta_todos_los_errores_juntos(base):
    base["modo"] = "x"
    base["umbrales"] = {"alto": 2, "bajo": 1}
    base["materias"] = []
    assert len(errores_de(base)) == 3


def test_yaml_invalido(zona):
    archivo = zona / "config.yaml"
    archivo.write_text("modo: [sin cerrar", encoding="utf-8")
    with pytest.raises(ConfigInvalida, match="YAML"):
        cargar_config(archivo)

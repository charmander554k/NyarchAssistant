from pathlib import Path

import demo_extractor

CONFIG_REAL = str(Path(__file__).resolve().parent.parent / "config.yaml")


def test_demo_muestra_las_tres_secciones(entorno, capsys):
    (entorno.raiz / "vdksahdas.py").write_text("x = 1\nimport nltk\n", encoding="utf-8")
    (entorno.raiz / ".oculto.txt").write_text("secreto", encoding="utf-8")
    assert demo_extractor.main([str(entorno.raiz), "--config", CONFIG_REAL]) == 0
    salida = capsys.readouterr().out
    assert "1. Lo que Archy lee de cada archivo" in salida
    assert "import nltk" in salida
    assert "2. Lo que Archy no revisa" in salida and ".oculto.txt" in salida
    assert "3. El guardián bloquea" in salida and "BLOQUEADA" in salida
    assert "permitida" not in salida  # ninguna ruta peligrosa debe pasar


def test_demo_texto_completo(entorno, capsys):
    (entorno.raiz / "notas.txt").write_text("Cifrado RSA y AES", encoding="utf-8")
    assert demo_extractor.main([str(entorno.raiz), "--config", CONFIG_REAL, "--completo", "notas.txt"]) == 0
    salida = capsys.readouterr().out
    assert "Cifrado RSA y AES" in salida and "Formato: texto" in salida


def test_demo_carpeta_invalida(capsys, zona):
    assert demo_extractor.main([str(zona / "no_existe"), "--config", CONFIG_REAL]) == 1
    assert "no existe" in capsys.readouterr().out

"""Demostración del extractor de Archy.

Muestra, para cada archivo de una carpeta, qué entiende Archy de él (lo que
después usará el clasificador), qué archivos no revisa y por qué, y cómo el
guardián bloquea rutas peligrosas. Solo lee: no mueve ni modifica nada.

Uso (desde la carpeta archy/):
    python demo_extractor.py "C:\\Users\\<usuario>\\Documents\\Trabajos"   # Windows
    python demo_extractor.py /mnt/c/Users/<usuario>/Documents/Trabajos      # WSL / Linux
    python demo_extractor.py <carpeta> --completo vdksahdas.py              # texto completo de un archivo

Requiere: pyyaml (y pypdf para leer PDF).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from nucleo.configuracion import ConfigInvalida, cargar_config  # noqa: E402
from nucleo.escaner import escanear  # noqa: E402
from nucleo.extractor import extraer  # noqa: E402
from nucleo.guardian import ErrorGuardian, Guardian  # noqa: E402

NOMBRE_METODO = {
    "texto": "texto", "codigo": "código", "notebook": "notebook", "tabla": "tabla",
    "docx": "Word", "pptx": "PowerPoint", "xlsx": "Excel", "opendocument": "OpenDocument",
    "pdf": "PDF", "no_soportado": "—", "error": "AVISO",
}

# Intentos de salir de la carpeta que el guardián debe bloquear.
RUTAS_PELIGROSAS_COMUNES = ["~/.ssh/id_rsa", "../", "~/.config"]
RUTAS_PELIGROSAS = {
    "nt": ["C:\\Windows\\win.ini", "C:\\Users"],
    "posix": ["/etc/passwd", "/mnt/c/Windows/win.ini"],
}


def recortar(texto: str, ancho: int) -> str:
    texto = " ".join(texto.replace("\n", " / ").split())
    return texto if len(texto) <= ancho else texto[: max(ancho - 1, 0)] + "…"


def carpeta_por_defecto() -> str | None:
    for candidata in (Path.home() / "Documents" / "Trabajos", Path.home() / "Documentos" / "Trabajos"):
        if candidata.is_dir():
            return str(candidata)
    return None


def titulo(texto: str) -> None:
    print(f"\n{texto}\n{'─' * len(texto)}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    analizador = argparse.ArgumentParser(description="Muestra qué lee Archy de cada archivo.")
    analizador.add_argument("carpeta", nargs="?", help="carpeta Trabajos (por defecto ~/Documents/Trabajos)")
    analizador.add_argument("--completo", metavar="ARCHIVO", help="muestra el texto completo extraído de un archivo")
    analizador.add_argument("--config", default=str(AQUI / "config.yaml"), help="ruta de config.yaml")
    args = analizador.parse_args(argv)

    carpeta = args.carpeta or carpeta_por_defecto()
    if not carpeta:
        print("Indica la carpeta Trabajos, ej.: python demo_extractor.py \"C:\\Users\\yo\\Documents\\Trabajos\"")
        return 2
    try:
        config = cargar_config(args.config)
        guardian = Guardian(carpeta, config.lista_negra_extra)
    except (ConfigInvalida, ErrorGuardian) as error:
        print(f"No se puede empezar: {error}")
        return 1

    if args.completo:
        r = extraer(guardian, config, args.completo)
        titulo(f"Texto que Archy extrae de: {r.ruta_relativa}")
        print(f"Formato: {NOMBRE_METODO.get(r.metodo, r.metodo)} · "
              f"{len(r.texto)} caracteres{' (recortado)' if r.truncado else ''}")
        if r.aviso:
            print(f"Aviso: {r.aviso}")
        print()
        print(r.texto)
        return 0

    resultado = escanear(guardian, config)
    ancho_total = max(shutil.get_terminal_size((120, 30)).columns, 90)
    ancho_archivo = min(max((len(a.ruta_relativa) for a in resultado.archivos), default=10), 38)
    ancho_vista = ancho_total - ancho_archivo - 18

    print(f"Archy · demostración del extractor (solo lectura)\nCarpeta: {guardian.raiz}")

    titulo(f"1. Lo que Archy lee de cada archivo ({len(resultado.archivos)} archivos)")
    print(f"{'Archivo':{ancho_archivo}}  {'Formato':12}  Lo que lee (primeros caracteres)")
    for archivo in resultado.archivos:
        r = extraer(guardian, config, archivo.ruta)
        formato = NOMBRE_METODO.get(r.metodo, r.metodo)
        vista = f"[{r.aviso}]" if r.aviso else recortar(r.texto, ancho_vista)
        print(f"{recortar(archivo.ruta_relativa, ancho_archivo):{ancho_archivo}}  {formato:12}  {vista}")

    titulo(f"2. Lo que Archy no revisa ({len(resultado.omitidos)})")
    if not resultado.omitidos:
        print("(nada: todos los archivos se pudieron revisar)")
    for omitido in resultado.omitidos:
        print(f"{recortar(omitido.ruta_relativa, ancho_archivo):{ancho_archivo}}  {omitido.motivo}")

    titulo("3. El guardián bloquea rutas fuera de Trabajos")
    for ruta in RUTAS_PELIGROSAS_COMUNES + RUTAS_PELIGROSAS["nt" if os.name == "nt" else "posix"]:
        decision = guardian.revisar(ruta)
        estado = "permitida" if decision.permitido else "BLOQUEADA"
        print(f"{ruta:28}  {estado:9}  {'' if decision.permitido else decision.motivo}")

    print("\nPara ver el texto completo de un archivo: --completo <nombre>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

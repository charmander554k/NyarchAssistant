"""Verifica el dataset de prueba de Archy y mide una línea base.

1. Integridad: cada fila de etiquetas.csv tiene su archivo y cada archivo su
   fila; materias y tipos válidos según config.yaml; el tipo coincide con la
   extensión.
2. Composición: cuántos archivos hay por materia, tipo, caso y dificultad.
3. Lectura: pasa el escáner y el extractor de Archy por todo el dataset.
4. Duplicados: archivos con el mismo hash SHA-256.
5. Línea base: un clasificador muy simple que solo cuenta palabras clave de
   config.yaml en el nombre y el texto. Es el punto de partida contra el que
   se medirá el clasificador real (meta del proyecto: >= 85 % en materia).

Uso (desde archy/):
    python dataset/verificar_dataset.py               # informe
    python dataset/verificar_dataset.py --detalle     # además, cada error de la línea base
    python dataset/verificar_dataset.py --copiar-a "C:\\Users\\yo\\Documents\\Trabajos"
        # copia el dataset a una carpeta para probarlo en la app (nunca sobrescribe)

Solo lee el dataset; con --copiar-a solo agrega archivos que no existan.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

from nucleo.configuracion import Config, cargar_config  # noqa: E402
from nucleo.escaner import escanear  # noqa: E402
from nucleo.extractor import extraer  # noqa: E402
from nucleo.guardian import Guardian  # noqa: E402

CARPETA = AQUI / "Trabajos_prueba"
ETIQUETAS = AQUI / "etiquetas.csv"
META = 0.85


def leer_etiquetas(ruta: Path = ETIQUETAS) -> list[dict]:
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sin_acentos if not unicodedata.combining(c))


def linea_base(nombre: str, texto: str, config: Config) -> tuple[str, dict[str, int]]:
    """Clasificador de referencia: la materia con más palabras clave gana.

    Si nadie tiene palabras clave o hay empate, va a la carpeta de dudas.
    """
    contenido = normalizar(nombre.replace("_", " ") + " " + texto)
    puntajes = {
        m.nombre: sum(contenido.count(normalizar(p)) for p in m.palabras_clave)
        for m in config.materias
    }
    mejor = max(puntajes.values())
    ganadores = [m for m, p in puntajes.items() if p == mejor]
    if mejor == 0 or len(ganadores) > 1:
        return config.carpeta_dudas, puntajes
    return ganadores[0], puntajes


def revisar_integridad(filas: list[dict], config: Config, carpeta: Path) -> list[str]:
    problemas = []
    validas = set(config.nombres_materias) | {config.carpeta_dudas}
    en_disco = {p.name for p in carpeta.iterdir() if p.is_file()}
    en_etiquetas = [f["archivo"] for f in filas]
    for nombre in sorted(set(en_etiquetas) - en_disco):
        problemas.append(f"Etiquetado pero no existe: {nombre}")
    for nombre in sorted(en_disco - set(en_etiquetas)):
        problemas.append(f"Existe pero no está etiquetado: {nombre}")
    for nombre, veces in Counter(en_etiquetas).items():
        if veces > 1:
            problemas.append(f"Etiquetado {veces} veces: {nombre}")
    for f in filas:
        if f["materia"] not in validas:
            problemas.append(f"{f['archivo']}: materia desconocida '{f['materia']}'")
        esperado = config.tipo_de(Path(f["archivo"]).suffix)
        if f["tipo"] != esperado:
            problemas.append(f"{f['archivo']}: tipo '{f['tipo']}' pero por su extensión es '{esperado}'")
    return problemas


def tabla(titulo: str, filas: list[list], anchos: list[int]) -> None:
    print(f"\n{titulo}\n{'─' * len(titulo)}")
    for fila in filas:
        print("  ".join(f"{str(c):{a}}" if i == 0 else f"{str(c):>{a}}" for i, (c, a) in enumerate(zip(fila, anchos))))


def porcentaje(aciertos: int, total: int) -> str:
    return f"{aciertos}/{total} ({aciertos / total:.0%})" if total else "—"


def copiar(destino: Path) -> int:
    destino.mkdir(parents=True, exist_ok=True)
    copiados = omitidos = 0
    for archivo in sorted(CARPETA.iterdir()):
        objetivo = destino / archivo.name
        if objetivo.exists():
            omitidos += 1
            continue
        shutil.copy2(archivo, objetivo)
        copiados += 1
    print(f"Copiados {copiados} archivos a {destino} ({omitidos} ya existían y no se tocaron).")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    analizador = argparse.ArgumentParser(description="Verifica el dataset de prueba de Archy.")
    analizador.add_argument("--detalle", action="store_true", help="lista cada error de la línea base")
    analizador.add_argument("--copiar-a", type=Path, metavar="CARPETA", help="copia el dataset a otra carpeta")
    args = analizador.parse_args(argv)

    if args.copiar_a:
        return copiar(args.copiar_a)

    config = cargar_config(AQUI.parent / "config.yaml")
    filas = leer_etiquetas()
    print(f"Dataset de prueba de Archy\nCarpeta: {CARPETA}\nEtiquetas: {ETIQUETAS.name} ({len(filas)} archivos)")

    # 1. Integridad
    problemas = revisar_integridad(filas, config, CARPETA)
    print("\n1. Integridad\n─────────────")
    if problemas:
        for p in problemas:
            print(f"  ✗ {p}")
        return 1
    print("  ✓ Cada archivo tiene su etiqueta y cada etiqueta su archivo; materias y tipos válidos.")

    # 2. Composición
    materias = list(config.nombres_materias) + [config.carpeta_dudas]
    tipos = list(config.tipos)
    conteo = Counter((f["materia"], f["tipo"]) for f in filas)
    filas_tabla = [["Materia"] + tipos + ["Total"]]
    for m in materias:
        valores = [conteo[(m, t)] for t in tipos]
        filas_tabla.append([m] + valores + [sum(valores)])
    filas_tabla.append(["Total"] + [sum(conteo[(m, t)] for m in materias) for t in tipos] + [len(filas)])
    tabla("2. Composición (materia × tipo)", filas_tabla, [22] + [max(len(t), 5) for t in tipos] + [5])
    print("  Casos:      " + ", ".join(f"{c} {n}" for c, n in Counter(f["caso"] for f in filas).most_common()))
    print("  Dificultad: " + ", ".join(f"{d} {n}" for d, n in Counter(f["dificultad"] for f in filas).most_common()))
    print("  Nombre descriptivo: " + ", ".join(f"{d} {n}" for d, n in Counter(f["nombre_descriptivo"] for f in filas).most_common()))

    # 3. Lectura con el escáner y el extractor de Archy
    guardian = Guardian(CARPETA)
    resultado = escanear(guardian, config)
    extracciones = {a.nombre: extraer(guardian, config, a.ruta) for a in resultado.archivos}
    por_metodo = Counter(e.metodo for e in extracciones.values())
    con_texto = sum(1 for e in extracciones.values() if not e.vacio)
    print("\n3. Lectura con el escáner y el extractor\n────────────────────────────────────────")
    print(f"  Escaneados: {len(resultado.archivos)} · omitidos: {len(resultado.omitidos)}")
    print(f"  Con texto legible: {con_texto} de {len(extracciones)}")
    print("  Por formato: " + ", ".join(f"{m} {n}" for m, n in sorted(por_metodo.items())))
    sin_texto = sorted(n for n, e in extracciones.items() if e.vacio)
    print(f"  Sin texto (esperado: imágenes y el archivo vacío): {', '.join(sin_texto)}")

    # 4. Duplicados
    por_hash = defaultdict(list)
    for a in resultado.archivos:
        por_hash[a.sha256].append(a.nombre)
    grupos = [sorted(n) for n in por_hash.values() if len(n) > 1]
    print("\n4. Duplicados (mismo SHA-256)\n─────────────────────────────")
    print("  " + ("; ".join(" = ".join(g) for g in grupos) if grupos else "ninguno"))

    # 5. Línea base
    aciertos_por = defaultdict(lambda: [0, 0])
    errores = []
    for f in filas:
        e = extracciones.get(f["archivo"])
        obtenido, puntajes = linea_base(f["archivo"], e.texto if e else "", config)
        bien = obtenido == f["materia"]
        for clave in ("total", f"dificultad: {f['dificultad']}", f"materia: {f['materia']}"):
            aciertos_por[clave][0] += bien
            aciertos_por[clave][1] += 1
        if not bien:
            errores.append((f["archivo"], f["materia"], obtenido, puntajes, f["caso"]))
    total_bien, total = aciertos_por["total"]
    print("\n5. Línea base: solo palabras clave de config.yaml\n─────────────────────────────────────────────────")
    print(f"  Exactitud en materia: {porcentaje(total_bien, total)}   (meta del clasificador real: {META:.0%})")
    for clave in sorted(k for k in aciertos_por if k != "total"):
        print(f"    {clave:32} {porcentaje(*aciertos_por[clave])}")
    if args.detalle:
        print("\n  Errores de la línea base:")
        for archivo, esperado, obtenido, puntajes, caso in errores:
            resumen = ", ".join(f"{m.split()[0]} {p}" for m, p in puntajes.items())
            print(f"    {archivo:30} esperado: {esperado:22} obtuvo: {obtenido:22} [{resumen}] ({caso})")
    else:
        print(f"  ({len(errores)} errores; usa --detalle para verlos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

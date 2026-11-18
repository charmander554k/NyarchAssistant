"""Mide el clasificador y el nombrador de Archy contra el dataset etiquetado.

Uso (desde archy/):
    python dataset/medir_clasificador.py                          # reglas + contenido
    python dataset/medir_clasificador.py --ollama http://localhost:11434   # + embeddings
    python dataset/medir_clasificador.py --detalle                # lista cada error

Métricas:
- Exactitud en materia (meta >= 85 %), por dificultad y por materia, contra
  la línea base de solo palabras clave (79 %).
- Errores graves: archivos que se moverían con confianza a una materia equivocada.
- Cuántos irían a Qwen (confianza media) y cuántos a _Por revisar.
- Nombres: % de nombres propuestos válidos en PascalCase (meta 100 %) y
  acuerdo con la etiqueta "nombre_descriptivo".
Solo lee el dataset.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

from dataset.verificar_dataset import CARPETA, linea_base, leer_etiquetas  # noqa: E402
from nucleo.clasificador import MOVER, REVISAR, Clasificador  # noqa: E402
from nucleo.configuracion import cargar_config  # noqa: E402
from nucleo.escaner import escanear  # noqa: E402
from nucleo.extractor import extraer  # noqa: E402
from nucleo.guardian import Guardian  # noqa: E402
from nucleo.nombrador import proponer_nombre, validar_nombre  # noqa: E402

META = 0.85


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else "—"


def medir(config, embeber=None, consultar=None) -> dict:
    """Clasifica todo el dataset y devuelve los resultados por archivo."""
    guardian = Guardian(CARPETA)
    clasificador = Clasificador(config, embeber=embeber, consultar=consultar)
    vocabulario = {p for m in config.materias for p in m.palabras_clave}
    extracciones = {a.nombre: extraer(guardian, config, a.ruta) for a in escanear(guardian, config).archivos}
    resultados = []
    for fila in leer_etiquetas():
        e = extracciones.get(fila["archivo"])
        c = clasificador.clasificar(fila["archivo"], e)
        base, _ = linea_base(fila["archivo"], e.texto if e else "", config)
        propuesta = proponer_nombre(fila["archivo"], e, sugerencia=c.nombre_sugerido, palabras_clave=vocabulario)
        resultados.append({"fila": fila, "c": c, "base": base, "nombre": propuesta})
    return {"resultados": resultados}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    analizador = argparse.ArgumentParser(description="Mide el clasificador de Archy con el dataset.")
    analizador.add_argument("--ollama", metavar="URL", help="Ollama a usar (ej. http://localhost:11434); activa los embeddings")
    analizador.add_argument("--modelo-embeddings", default="paraphrase-multilingual")
    analizador.add_argument("--sin-embeddings", action="store_true", help="con --ollama, no usar embeddings")
    analizador.add_argument("--qwen", action="store_true", help="con --ollama, consultar a Qwen en los dudosos")
    analizador.add_argument("--modelo-qwen", default="qwen2.5:3b")
    analizador.add_argument("--detalle", action="store_true", help="listar cada error")
    args = analizador.parse_args(argv)

    config = cargar_config(AQUI.parent / "config.yaml")
    embeber = consultar = None
    if (args.qwen or args.sin_embeddings) and not args.ollama:
        print("--qwen y --sin-embeddings necesitan --ollama URL")
        return 2
    if args.ollama:
        from nucleo.ollama import chat_json, disponible, embebedor
        necesarios = ([] if args.sin_embeddings else [args.modelo_embeddings]) + ([args.modelo_qwen] if args.qwen else [])
        for modelo in necesarios:
            if not disponible(args.ollama, modelo):
                print(f"Ollama en {args.ollama} no responde o no tiene '{modelo}'.")
                print(f"Descárgalo en esa PC con: ollama pull {modelo}")
                return 1
        if not args.sin_embeddings:
            embeber = embebedor(args.ollama, args.modelo_embeddings)
        if args.qwen:
            consultar = chat_json(args.ollama, args.modelo_qwen)

    inicio = time.perf_counter()
    resultados = medir(config, embeber, consultar)["resultados"]
    segundos = time.perf_counter() - inicio
    etapa = " + ".join(["reglas + contenido"] + (["embeddings"] if embeber else []) + (["Qwen"] if consultar else []))

    total = len(resultados)
    bien = sum(r["c"].materia == r["fila"]["materia"] for r in resultados)
    bien_base = sum(r["base"] == r["fila"]["materia"] for r in resultados)
    print(f"Medición del clasificador de Archy ({etapa})\nDataset: {total} archivos · {segundos:.1f} s\n")

    print("1. Exactitud en materia\n───────────────────────")
    print(f"  Clasificador: {pct(bien, total)}   ·   línea base (solo palabras clave): {pct(bien_base, total)}"
          f"   ·   meta: {META:.0%}  {'✓' if bien / total >= META else '✗'}")
    grupos = defaultdict(lambda: [0, 0, 0])
    for r in resultados:
        for clave in (f"dificultad {r['fila']['dificultad']}", f"materia: {r['fila']['materia']}"):
            grupos[clave][0] += r["c"].materia == r["fila"]["materia"]
            grupos[clave][1] += r["base"] == r["fila"]["materia"]
            grupos[clave][2] += 1
    print(f"  {'':34} {'clasificador':>14} {'línea base':>14}")
    for clave in sorted(grupos):
        a, b, n = grupos[clave]
        print(f"  {clave:34} {pct(a, n):>14} {pct(b, n):>14}")

    print("\n2. Decisiones\n─────────────")
    decisiones = Counter(r["c"].decision for r in resultados)
    graves = [r for r in resultados if r["c"].decision == MOVER and r["c"].materia != r["fila"]["materia"]]
    print(f"  Mover con confianza (>= {config.umbrales.alto}): {decisiones['mover']}"
          f" · con advertencia: {decisiones['advertir']}"
          f" · a {config.carpeta_dudas}: {decisiones['revisar']}")
    if consultar:
        consultados = [r for r in resultados if r["c"].consulto_qwen]
        acertados = sum(r["c"].materia == r["fila"]["materia"] for r in consultados)
        print(f"  Consultas a Qwen: {len(consultados)} (acertó después de consultar: {pct(acertados, len(consultados))})")
    print(f"  Errores graves (se movería con confianza a la materia equivocada): {len(graves)}")
    for r in graves:
        print(f"    ✗ {r['fila']['archivo']}: esperado {r['fila']['materia']}, propuso {r['c'].materia}")

    materias = list(config.nombres_materias) + [config.carpeta_dudas]
    cortas = {m: m.split()[0][:9] for m in materias}
    matriz = Counter((r["fila"]["materia"], r["c"].materia) for r in resultados)
    print("\n3. Matriz de confusión (filas: correcto · columnas: propuesto)\n──────────────────────────────────────────────────────────────")
    print("  " + " " * 12 + "".join(f"{cortas[m]:>11}" for m in materias))
    for real in materias:
        print(f"  {cortas[real]:12}" + "".join(f"{matriz[(real, p)]:>11}" for p in materias))

    print("\n4. Nombres\n──────────")
    renombrados = [r for r in resultados if r["nombre"].renombrar]
    validos = [r for r in renombrados if not validar_nombre(r["nombre"].nombre)]
    acuerdo = sum((not r["nombre"].renombrar and "ya dice" in r["nombre"].motivo) == (r["fila"]["nombre_descriptivo"] == "si")
                  for r in resultados)
    no_descriptivos = [r for r in resultados if r["fila"]["nombre_descriptivo"] == "no"]
    print(f"  Nombres propuestos: {len(renombrados)} · válidos en PascalCase: {pct(len(validos), len(renombrados))} (meta 100 %)")
    print(f"  De los {len(no_descriptivos)} con nombre no descriptivo, se propone nombre a "
          f"{sum(r['nombre'].renombrar for r in no_descriptivos)} (los demás no tienen texto, ej. imágenes)")
    print(f"  Acuerdo con la etiqueta 'nombre_descriptivo': {pct(acuerdo, total)}")
    ejemplos = [r for r in renombrados][:8]
    for r in ejemplos:
        print(f"    {r['fila']['archivo']:28} → {r['nombre'].nombre}")

    errores = [r for r in resultados if r["c"].materia != r["fila"]["materia"]]
    if args.detalle:
        print("\n5. Errores de materia\n─────────────────────")
        for r in errores:
            print(f"  {r['fila']['archivo']:28} esperado: {r['fila']['materia']:22} "
                  f"propuso: {r['c'].materia:22} ({r['fila']['caso']})\n      {r['c'].motivo}")
    else:
        print(f"\n({len(errores)} errores de materia; usa --detalle para verlos con su motivo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

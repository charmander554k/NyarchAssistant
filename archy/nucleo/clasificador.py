"""Clasificador de Archy (paso "Razonar").

Decide a qué materia pertenece cada archivo, con una confianza de 0 a 1 y un
motivo legible. Es un clasificador híbrido en cascada:

1. Reglas: palabras clave de config.yaml en el NOMBRE del archivo (peso alto).
2. Contenido: las mismas palabras en el texto extraído (peso normal).
   Se comparan palabras completas, no pedazos ("texto" no cuenta dentro de
   "contexto"), y las palabras genéricas que forman parte del nombre de una
   materia ("seguridad", "texto"...) pesan menos.
3. Embeddings (opcional): similitud semántica entre el texto y la descripción
   de cada materia. Se pasa como una función `embeber(textos) -> vectores`,
   así las pruebas no necesitan Ollama.
4. Qwen (opcional, solo si hay duda): se pasa como una función.

Decisión con los umbrales de config.yaml:
    confianza >= alto  -> "mover"
    bajo <= ... < alto -> "advertir" (se propone, pero con advertencia)
    confianza <  bajo  -> "revisar"  (va a la carpeta de dudas)

El tipo (Codigo, Documentos...) sale siempre de la extensión.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Callable, Sequence

from .configuracion import Config
from .extractor import Extraccion
from .texto import palabras

__all__ = ["Clasificacion", "Clasificador", "MOVER", "ADVERTIR", "REVISAR"]

MOVER, ADVERTIR, REVISAR = "mover", "advertir", "revisar"

PESO_NOMBRE = 2.0
PESO_CONTENIDO = 1.0
FACTOR_GENERICA = 0.4      # palabras que forman parte del nombre de una materia
ESCALA_EVIDENCIA = 1.5     # cuánta evidencia hace falta para confiar
GENERICAS_EXTRA = {"inteligencia artificial"}

Embeber = Callable[[Sequence[str]], Sequence[Sequence[float]]]


@dataclass(frozen=True)
class Clasificacion:
    archivo: str
    materia: str              # materia propuesta, o la carpeta de dudas
    tipo: str
    confianza: float          # 0 a 1
    decision: str             # mover | advertir | revisar
    motivo: str
    puntajes: dict[str, float] = field(default_factory=dict)   # probabilidad por materia
    etapa: str = "reglas"     # reglas | embeddings | qwen

    @property
    def necesita_qwen(self) -> bool:
        return self.decision == ADVERTIR


class Clasificador:
    def __init__(self, config: Config, embeber: Embeber | None = None,
                 peso_embeddings: float = 0.5) -> None:
        self.config = config
        self.embeber = embeber
        self.peso_embeddings = peso_embeddings
        self._vectores_materias: list[Sequence[float]] | None = None

        nombres_materia = set()
        for m in config.materias:
            nombres_materia.update(p for p in palabras(m.nombre) if len(p) > 2)
        self._claves: dict[str, list[tuple[str, float]]] = {}
        for m in config.materias:
            lista = []
            for clave in m.palabras_clave:
                clave_n = " ".join(_singular(w) for w in palabras(clave))
                if not clave_n:
                    continue
                generica = clave_n in GENERICAS_EXTRA or clave_n in nombres_materia
                lista.append((clave_n, FACTOR_GENERICA if generica else 1.0))
            self._claves[m.nombre] = lista

    # -- etapas 1 y 2: reglas y contenido ------------------------------------

    def _pistas(self, nombre: str, texto: str) -> tuple[dict[str, float], dict[str, list[str]]]:
        nombre_palabras = [_singular(p) for p in palabras(PurePath(nombre).stem)]
        texto_palabras = [_singular(p) for p in palabras(texto)]
        nombre_frase = f" {' '.join(nombre_palabras)} "
        texto_frase = f" {' '.join(texto_palabras)} "
        conteo = Counter(texto_palabras)

        puntajes, evidencias = {}, {}
        for materia, claves in self._claves.items():
            puntaje, vistas = 0.0, []
            for clave, factor in claves:
                if " " in clave:
                    en_nombre = f" {clave} " in nombre_frase
                    veces = texto_frase.count(f" {clave} ")
                else:
                    en_nombre = clave in nombre_palabras
                    veces = conteo[clave]
                if en_nombre:
                    puntaje += PESO_NOMBRE * factor
                    vistas.append(f"{clave} (nombre)")
                if veces:
                    puntaje += PESO_CONTENIDO * factor * (1 + 0.5 * (min(veces, 3) - 1))
                    if not en_nombre:
                        vistas.append(clave)
            puntajes[materia] = puntaje
            evidencias[materia] = vistas
        return puntajes, evidencias

    # -- etapa 3: embeddings --------------------------------------------------

    def _similitudes(self, texto: str) -> dict[str, float] | None:
        if self.embeber is None or not texto.strip():
            return None
        if self._vectores_materias is None:
            descripciones = [f"{m.nombre}. {m.descripcion} {' '.join(m.palabras_clave)}"
                             for m in self.config.materias]
            self._vectores_materias = list(self.embeber(descripciones))
        vector = self.embeber([texto[: self.config.caracteres_a_leer]])[0]
        return {m.nombre: _coseno(vector, v) for m, v in zip(self.config.materias, self._vectores_materias)}

    # -- decisión --------------------------------------------------------------

    def clasificar(self, nombre: str, extraccion: Extraccion | None = None) -> Clasificacion:
        texto = extraccion.texto if extraccion is not None else ""
        tipo = self.config.tipo_de(PurePath(nombre).suffix)
        puntajes, evidencias = self._pistas(nombre, texto)
        total = sum(puntajes.values())

        if total > 0:
            reglas = {m: p / total for m, p in puntajes.items()}
            evidencia = 1 - math.exp(-total / ESCALA_EVIDENCIA)
        else:
            reglas = {m.nombre: 1 / len(self.config.materias) for m in self.config.materias}
            evidencia = 0.0

        probabilidades, etapa = reglas, "reglas"
        similitudes = self._similitudes(texto)
        if similitudes:
            semantica = _softmax(similitudes, temperatura=0.05)
            peso = self.peso_embeddings if total > 0 else 1.0
            probabilidades = {m: (1 - peso) * reglas[m] + peso * semantica[m] for m in reglas}
            # La similitud también es evidencia: con un texto parecido a una materia se confía más.
            evidencia = max(evidencia, _a_evidencia(max(similitudes.values())))
            etapa = "embeddings"

        mejor = max(probabilidades, key=probabilidades.get)
        confianza = round(probabilidades[mejor] * evidencia, 2)
        umbrales = self.config.umbrales
        if confianza >= umbrales.alto:
            decision = MOVER
        elif confianza >= umbrales.bajo:
            decision = ADVERTIR
        else:
            decision = REVISAR

        motivo = _motivo(mejor, evidencias, similitudes, confianza, decision)
        materia = mejor if decision != REVISAR else self.config.carpeta_dudas
        return Clasificacion(nombre, materia, tipo, confianza, decision, motivo,
                             {m: round(p, 3) for m, p in probabilidades.items()}, etapa)


def _singular(palabra: str) -> str:
    """Plural simple a singular (paquetes -> paquete, resenas -> resena).

    No es perfecto, pero se aplica igual a las palabras clave y al texto, así
    que basta con que sea consistente.
    """
    if len(palabra) > 5 and palabra.endswith("es") and palabra[-3] not in "aeiou":
        return palabra[:-2]
    if len(palabra) > 4 and palabra.endswith("s") and not palabra.endswith("ss"):
        return palabra[:-1]
    return palabra


def _coseno(a: Sequence[float], b: Sequence[float]) -> float:
    producto = sum(x * y for x, y in zip(a, b))
    norma = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return producto / norma if norma else 0.0


def _softmax(valores: dict[str, float], temperatura: float) -> dict[str, float]:
    maximo = max(valores.values())
    exps = {k: math.exp((v - maximo) / temperatura) for k, v in valores.items()}
    suma = sum(exps.values())
    return {k: e / suma for k, e in exps.items()}


def _a_evidencia(similitud: float) -> float:
    """Convierte la similitud coseno (≈0.2 nada que ver, ≈0.6 muy parecido) en evidencia 0–1."""
    return min(max((similitud - 0.2) / 0.4, 0.0), 1.0)


def _motivo(mejor: str, evidencias: dict[str, list[str]], similitudes: dict[str, float] | None,
            confianza: float, decision: str) -> str:
    partes = []
    pistas = evidencias.get(mejor, [])
    if pistas:
        partes.append("pistas: " + ", ".join(pistas[:5]))
    otras = [f"{m.split()[0]}: {', '.join(v[:2])}" for m, v in evidencias.items() if m != mejor and v]
    if otras:
        partes.append("también hay pistas de " + "; ".join(otras))
    if similitudes:
        partes.append(f"parecido semántico {similitudes[mejor]:.2f}")
    if not partes:
        partes.append("no se encontraron pistas en el nombre ni en el contenido")
    accion = {MOVER: "se propone", ADVERTIR: "se propone con advertencia", REVISAR: "no hay suficiente certeza"}[decision]
    return f"{mejor} ({confianza:.2f}, {accion}): " + "; ".join(partes)

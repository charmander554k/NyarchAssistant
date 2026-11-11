"""Carga y valida `config.yaml`.

Si algo está mal, `ConfigInvalida` explica en español TODOS los problemas
encontrados, para que el estudiante pueda corregirlos de una vez.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["ConfigInvalida", "Materia", "Umbrales", "Config", "cargar_config", "config_desde_dict"]

_MODOS = ("simulacion", "real")
_RENOMBRAR = ("siempre", "preguntar", "nunca")
_FORMATOS = ("PascalCase",)
_TIPO_POR_DEFECTO = "Otros"
_CLAVES = {
    "carpeta_raiz", "modo", "permitir_renombrar", "formato_nombres",
    "organizar_por_parcial", "carpeta_dudas", "tamano_maximo_mb", "tipos",
    "modelo", "embeddings", "umbrales", "caracteres_a_leer", "materias",
    "lista_negra_extra",
}


class ConfigInvalida(Exception):
    """`config.yaml` tiene uno o más errores."""

    def __init__(self, errores: list[str]) -> None:
        self.errores = errores
        super().__init__("config.yaml tiene errores:\n- " + "\n- ".join(errores))


@dataclass(frozen=True)
class Materia:
    nombre: str
    descripcion: str
    palabras_clave: tuple[str, ...]


@dataclass(frozen=True)
class Umbrales:
    alto: float
    bajo: float


@dataclass(frozen=True)
class Config:
    carpeta_raiz: str
    modo: str
    permitir_renombrar: str
    formato_nombres: str
    organizar_por_parcial: bool
    carpeta_dudas: str
    tamano_maximo_bytes: int
    tipos: dict[str, tuple[str, ...]]
    modelo: str
    contexto_minimo: int
    modelo_embeddings: str
    umbrales: Umbrales
    caracteres_a_leer: int
    materias: tuple[Materia, ...]
    lista_negra_extra: tuple[str, ...]

    def tipo_de(self, extension: str) -> str:
        """Tipo (subcarpeta) que corresponde a una extensión, ej. '.py' -> 'Codigo'."""
        extension = extension.lower()
        for tipo, extensiones in self.tipos.items():
            if extension in extensiones:
                return tipo
        return _TIPO_POR_DEFECTO

    @property
    def nombres_materias(self) -> tuple[str, ...]:
        return tuple(m.nombre for m in self.materias)


def cargar_config(ruta: str | Path) -> Config:
    """Lee un `config.yaml` y lo devuelve validado."""
    import yaml  # PyYAML ya viene en el Flatpak de NyarchAssistant

    ruta = Path(ruta)
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigInvalida([f"no se pudo leer {ruta}: {error}"]) from error
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError as error:
        raise ConfigInvalida([f"el archivo no es YAML válido: {error}"]) from error
    return config_desde_dict(datos)


def _nombre_de_carpeta_valido(nombre: Any) -> bool:
    return (
        isinstance(nombre, str)
        and nombre.strip() == nombre
        and bool(nombre)
        and not nombre.startswith(".")
        and not any(c in nombre for c in '/\\:*?"<>|')
    )


def _lista_de_textos(valor: Any) -> bool:
    return isinstance(valor, list) and all(isinstance(v, str) and v.strip() for v in valor)


def config_desde_dict(datos: Any) -> Config:
    """Valida un diccionario (ya leído del YAML) y construye `Config`."""
    if not isinstance(datos, dict):
        raise ConfigInvalida(["el archivo debe contener pares clave: valor"])

    errores: list[str] = []
    desconocidas = sorted(set(datos) - _CLAVES)
    if desconocidas:
        errores.append(f"claves desconocidas (¿error de escritura?): {', '.join(desconocidas)}")
    faltantes = sorted(_CLAVES - set(datos))
    if faltantes:
        errores.append(f"faltan claves: {', '.join(faltantes)}")
    if errores:
        raise ConfigInvalida(errores)

    carpeta_raiz = datos["carpeta_raiz"]
    if not isinstance(carpeta_raiz, str) or not carpeta_raiz.strip():
        errores.append("carpeta_raiz debe ser una ruta")

    if datos["modo"] not in _MODOS:
        errores.append(f"modo debe ser uno de: {', '.join(_MODOS)}")
    if datos["permitir_renombrar"] not in _RENOMBRAR:
        errores.append(f"permitir_renombrar debe ser uno de: {', '.join(_RENOMBRAR)}")
    if datos["formato_nombres"] not in _FORMATOS:
        errores.append(f"formato_nombres debe ser uno de: {', '.join(_FORMATOS)}")
    if datos["organizar_por_parcial"] is not False:
        errores.append("organizar_por_parcial debe ser false (el equipo decidió no organizar por parcial)")

    carpeta_dudas = datos["carpeta_dudas"]
    if not _nombre_de_carpeta_valido(carpeta_dudas):
        errores.append("carpeta_dudas debe ser un nombre de carpeta válido (sin / \\ : * ? \" < > |)")

    tamano = datos["tamano_maximo_mb"]
    if isinstance(tamano, bool) or not isinstance(tamano, (int, float)) or tamano <= 0:
        errores.append("tamano_maximo_mb debe ser un número mayor que 0")
        tamano = 1

    # Tipos y extensiones
    tipos: dict[str, tuple[str, ...]] = {}
    tipos_crudos = datos["tipos"]
    if not isinstance(tipos_crudos, dict) or not tipos_crudos:
        errores.append("tipos debe tener al menos un tipo con su lista de extensiones")
    else:
        vistas: dict[str, str] = {}
        for tipo, extensiones in tipos_crudos.items():
            if not _nombre_de_carpeta_valido(tipo):
                errores.append(f"el tipo '{tipo}' no es un nombre de carpeta válido")
                continue
            if extensiones is None:
                extensiones = []
            if not isinstance(extensiones, list):
                errores.append(f"las extensiones del tipo '{tipo}' deben ser una lista")
                continue
            normalizadas = []
            for ext in extensiones:
                if not isinstance(ext, str) or not ext.startswith(".") or len(ext) < 2:
                    errores.append(f"extensión inválida en '{tipo}': {ext!r} (debe empezar con punto, ej. '.py')")
                    continue
                ext = ext.lower()
                if ext in vistas:
                    errores.append(f"la extensión {ext} está en dos tipos: '{vistas[ext]}' y '{tipo}'")
                    continue
                vistas[ext] = tipo
                normalizadas.append(ext)
            tipos[tipo] = tuple(normalizadas)
        if _TIPO_POR_DEFECTO not in tipos:
            errores.append(f"tipos debe incluir '{_TIPO_POR_DEFECTO}' (para extensiones no listadas)")

    # Modelo y embeddings
    modelo = datos["modelo"]
    if not isinstance(modelo, dict) or not isinstance(modelo.get("nombre"), str):
        errores.append("modelo debe tener 'nombre' (ej. qwen2.5:3b)")
        modelo = {"nombre": "", "contexto_minimo": 0}
    contexto = modelo.get("contexto_minimo", 16384)
    if not isinstance(contexto, int) or isinstance(contexto, bool) or contexto < 4096:
        errores.append("modelo.contexto_minimo debe ser un entero >= 4096")
        contexto = 16384
    embeddings = datos["embeddings"]
    if not isinstance(embeddings, dict) or not isinstance(embeddings.get("modelo"), str):
        errores.append("embeddings debe tener 'modelo'")
        embeddings = {"modelo": ""}

    # Umbrales
    umbrales = datos["umbrales"]
    alto = bajo = None
    if isinstance(umbrales, dict):
        alto, bajo = umbrales.get("alto"), umbrales.get("bajo")
    numeros = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (alto, bajo))
    if not numeros or not (0 < bajo < alto <= 1):
        errores.append("umbrales debe cumplir 0 < bajo < alto <= 1 (ej. bajo: 0.45, alto: 0.70)")
        alto, bajo = 0.70, 0.45

    caracteres = datos["caracteres_a_leer"]
    if not isinstance(caracteres, int) or isinstance(caracteres, bool) or caracteres <= 0:
        errores.append("caracteres_a_leer debe ser un entero mayor que 0")
        caracteres = 2000

    # Materias
    materias: list[Materia] = []
    crudas = datos["materias"]
    if not isinstance(crudas, list) or not crudas:
        errores.append("materias debe tener al menos una materia")
        crudas = []
    nombres_vistos: set[str] = set()
    for i, m in enumerate(crudas, start=1):
        if not isinstance(m, dict):
            errores.append(f"la materia #{i} debe tener nombre, descripcion y palabras_clave")
            continue
        nombre = m.get("nombre")
        if not _nombre_de_carpeta_valido(nombre):
            errores.append(f"la materia #{i} necesita un nombre válido de carpeta")
            continue
        if nombre.casefold() in nombres_vistos:
            errores.append(f"la materia '{nombre}' está repetida")
            continue
        if nombre == carpeta_dudas:
            errores.append(f"la materia '{nombre}' tiene el mismo nombre que carpeta_dudas")
            continue
        nombres_vistos.add(nombre.casefold())
        descripcion = m.get("descripcion")
        if not isinstance(descripcion, str) or not descripcion.strip():
            errores.append(f"la materia '{nombre}' necesita una descripcion")
            descripcion = ""
        palabras = m.get("palabras_clave")
        if not _lista_de_textos(palabras):
            errores.append(f"las palabras_clave de '{nombre}' deben ser una lista de textos")
            palabras = []
        materias.append(Materia(nombre, " ".join(descripcion.split()),
                                tuple(p.strip().lower() for p in palabras)))

    extra = datos["lista_negra_extra"]
    if extra is None:
        extra = []
    if not isinstance(extra, list) or not all(isinstance(r, str) and r.strip() for r in extra):
        errores.append("lista_negra_extra debe ser una lista de rutas (o [])")
        extra = []

    if errores:
        raise ConfigInvalida(errores)

    return Config(
        carpeta_raiz=carpeta_raiz.strip(),
        modo=datos["modo"],
        permitir_renombrar=datos["permitir_renombrar"],
        formato_nombres=datos["formato_nombres"],
        organizar_por_parcial=False,
        carpeta_dudas=carpeta_dudas,
        tamano_maximo_bytes=int(tamano * 1024 * 1024),
        tipos=tipos,
        modelo=modelo["nombre"],
        contexto_minimo=contexto,
        modelo_embeddings=embeddings["modelo"],
        umbrales=Umbrales(alto=float(alto), bajo=float(bajo)),
        caracteres_a_leer=caracteres,
        materias=tuple(materias),
        lista_negra_extra=tuple(r.strip() for r in extra),
    )

"""Bitácora de Archy (paso "Registrar").

SQLite fuera de la carpeta Trabajos (en la carpeta de datos de la app). Guarda
solo rutas y metadatos: qué se movió, de dónde a dónde, su huella SHA-256,
materia, confianza y motivo, y los intentos que bloqueó el guardián.
**Nunca guarda el contenido de los archivos.**

Las rutas se guardan relativas a la carpeta Trabajos, junto con la carpeta
raíz de cada operación, para que deshacer solo actúe sobre la misma carpeta.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

__all__ = ["Bitacora", "Operacion", "Movimiento", "Bloqueo"]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS operaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    tipo TEXT NOT NULL,              -- aplicar | deshacer
    simulacion INTEGER NOT NULL,     -- 1 = no se movió nada
    raiz TEXT NOT NULL,
    deshace INTEGER,                 -- id de la operación que deshace (si tipo = deshacer)
    deshecha_por INTEGER             -- id de la operación que la deshizo
);
CREATE TABLE IF NOT EXISTS movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operacion INTEGER NOT NULL REFERENCES operaciones(id),
    orden INTEGER NOT NULL,
    origen TEXT NOT NULL,
    destino TEXT,
    sha256 TEXT,
    materia TEXT,
    tipo TEXT,
    confianza REAL,
    motivo TEXT,
    estado TEXT NOT NULL,            -- movido | simulado | omitido | error
    detalle TEXT
);
CREATE TABLE IF NOT EXISTS bloqueos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    ruta TEXT NOT NULL,
    motivo TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Movimiento:
    orden: int
    origen: str
    destino: str | None
    sha256: str | None
    materia: str | None
    tipo: str | None
    confianza: float | None
    motivo: str | None
    estado: str
    detalle: str | None


@dataclass(frozen=True)
class Operacion:
    id: int
    fecha: str
    tipo: str
    simulacion: bool
    raiz: str
    deshace: int | None
    deshecha_por: int | None
    movidos: int
    total: int

    @property
    def deshacible(self) -> bool:
        return self.tipo == "aplicar" and not self.simulacion and self.deshecha_por is None and self.movidos > 0


@dataclass(frozen=True)
class Bloqueo:
    fecha: str
    ruta: str
    motivo: str


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Bitacora:
    def __init__(self, ruta: str | Path) -> None:
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._conectar() as c:
            c.executescript(ESQUEMA)

    def _conectar(self) -> sqlite3.Connection:
        conexion = sqlite3.connect(self.ruta, timeout=10)
        conexion.execute("PRAGMA foreign_keys = ON")
        return conexion

    # -- escribir ------------------------------------------------------------------

    def iniciar_operacion(self, tipo: str, simulacion: bool, raiz: str, deshace: int | None = None) -> int:
        with self._conectar() as c:
            cursor = c.execute(
                "INSERT INTO operaciones (fecha, tipo, simulacion, raiz, deshace) VALUES (?, ?, ?, ?, ?)",
                (_ahora(), tipo, int(simulacion), str(raiz), deshace))
            return int(cursor.lastrowid)

    def registrar_movimiento(self, operacion: int, orden: int, origen: str, destino: str | None,
                             estado: str, detalle: str | None = None, sha256: str | None = None,
                             materia: str | None = None, tipo: str | None = None,
                             confianza: float | None = None, motivo: str | None = None) -> None:
        with self._conectar() as c:
            c.execute(
                "INSERT INTO movimientos (operacion, orden, origen, destino, sha256, materia, tipo, confianza,"
                " motivo, estado, detalle) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (operacion, orden, origen, destino, sha256, materia, tipo, confianza, motivo, estado, detalle))

    def registrar_bloqueo(self, ruta: str, motivo: str) -> None:
        with self._conectar() as c:
            c.execute("INSERT INTO bloqueos (fecha, ruta, motivo) VALUES (?, ?, ?)", (_ahora(), str(ruta), motivo))

    def marcar_deshecha(self, operacion: int, por: int) -> None:
        with self._conectar() as c:
            c.execute("UPDATE operaciones SET deshecha_por = ? WHERE id = ?", (por, operacion))

    # -- leer ----------------------------------------------------------------------

    def operaciones(self, limite: int = 10) -> list[Operacion]:
        with self._conectar() as c:
            filas = c.execute(
                "SELECT o.id, o.fecha, o.tipo, o.simulacion, o.raiz, o.deshace, o.deshecha_por,"
                " SUM(m.estado = 'movido'), COUNT(m.id)"
                " FROM operaciones o LEFT JOIN movimientos m ON m.operacion = o.id"
                " GROUP BY o.id ORDER BY o.id DESC LIMIT ?", (limite,)).fetchall()
        return [Operacion(i, f, t, bool(s), r, d, dp, int(mv or 0), int(n or 0))
                for i, f, t, s, r, d, dp, mv, n in filas]

    def operacion(self, id_operacion: int) -> Operacion | None:
        return next((o for o in self.operaciones(limite=10_000) if o.id == id_operacion), None)

    def ultima_deshacible(self, raiz: str | None = None) -> Operacion | None:
        """La operación real más reciente que sigue sin deshacer (deshacer funciona como una pila)."""
        for o in self.operaciones(limite=200):
            if o.deshacible and (raiz is None or o.raiz == str(raiz)):
                return o
        return None

    def movimientos(self, id_operacion: int) -> list[Movimiento]:
        with self._conectar() as c:
            filas = c.execute(
                "SELECT orden, origen, destino, sha256, materia, tipo, confianza, motivo, estado, detalle"
                " FROM movimientos WHERE operacion = ? ORDER BY orden", (id_operacion,)).fetchall()
        return [Movimiento(*f) for f in filas]

    def bloqueos(self, limite: int = 10) -> list[Bloqueo]:
        with self._conectar() as c:
            filas = c.execute("SELECT fecha, ruta, motivo FROM bloqueos ORDER BY id DESC LIMIT ?",
                              (limite,)).fetchall()
        return [Bloqueo(*f) for f in filas]

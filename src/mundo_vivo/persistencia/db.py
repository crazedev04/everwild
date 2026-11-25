"""
Apertura de la base de datos con migraciones versionadas y backups.

Reglas (del plan maestro):
  - Nunca se borra ni se recrea una base automáticamente.
  - Antes de aplicar migraciones a una base con datos se hace un backup.
  - Si la base es de una versión MÁS NUEVA que el código, se aborta sin tocarla.
"""
from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

DIR_MIGRACIONES = Path(__file__).parent / "migraciones"
BACKUPS_A_CONSERVAR = 10


class ErrorVersionFutura(Exception):
    """La base fue creada por una versión más nueva del programa."""


def listar_migraciones(directorio: Path = DIR_MIGRACIONES) -> List[Tuple[int, str, Path]]:
    out = []
    for f in sorted(directorio.glob("*.sql")):
        m = re.match(r"^(\d{4})_(.+)\.sql$", f.name)
        if m:
            out.append((int(m.group(1)), m.group(2), f))
    return out


def version_actual(con: sqlite3.Connection) -> int:
    existe = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migraciones'").fetchone()
    if not existe:
        return 0
    fila = con.execute("SELECT MAX(version) FROM schema_migraciones").fetchone()
    return fila[0] or 0


def hacer_backup(con: sqlite3.Connection, destino: Path) -> Path:
    """Copia consistente de la base (funciona aunque esté en uso)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    dst = sqlite3.connect(destino)
    try:
        con.backup(dst)
    finally:
        dst.close()
    return destino


def _rotar_backups(directorio: Path, prefijo: str, conservar: int) -> None:
    archivos = sorted(directorio.glob(prefijo + "*.db"), key=lambda p: p.stat().st_mtime)
    for viejo in archivos[:-conservar]:
        viejo.unlink()


def abrir(ruta: Path, dir_backups: Optional[Path] = None,
          directorio_migraciones: Path = DIR_MIGRACIONES) -> sqlite3.Connection:
    """Abre (o crea) la base y la deja migrada a la última versión."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")

    migraciones = listar_migraciones(directorio_migraciones)
    ultima = migraciones[-1][0] if migraciones else 0
    actual = version_actual(con)
    if actual > ultima:
        con.close()
        raise ErrorVersionFutura(
            "La base %s es de la versión de esquema %d, pero este programa solo conoce hasta la %d. "
            "No se tocó nada. Actualizá el programa." % (ruta.name, actual, ultima))

    pendientes = [m for m in migraciones if m[0] > actual]
    if pendientes:
        if actual > 0:  # la base ya tenía datos: backup antes de migrar
            carpeta = Path(dir_backups) if dir_backups else ruta.parent / "backups"
            sello = datetime.now().strftime("%Y%m%d_%H%M%S")
            prefijo = "%s_antes_de_migrar_" % ruta.stem
            hacer_backup(con, carpeta / ("%sv%04d_%s.db" % (prefijo, actual, sello)))
            _rotar_backups(carpeta, prefijo, BACKUPS_A_CONSERVAR)
        con.execute("""CREATE TABLE IF NOT EXISTS schema_migraciones (
                          version INTEGER PRIMARY KEY, nombre TEXT NOT NULL, aplicada_en TEXT NOT NULL)""")
        con.commit()
        for version, nombre, archivo in pendientes:
            sql = archivo.read_text(encoding="utf-8")
            script = ("BEGIN;\n" + sql + "\nINSERT INTO schema_migraciones (version, nombre, aplicada_en) "
                      "VALUES (%d, '%s', '%s');\nCOMMIT;" % (version, nombre.replace("'", ""),
                                                           datetime.now().isoformat(timespec="seconds")))
            try:
                con.executescript(script)
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                con.close()
                raise
    return con

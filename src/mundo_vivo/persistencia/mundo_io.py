"""Guardar y cargar mundos, eventos, y paquetes de exportación."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
import time
import zipfile
import zlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from ..generador.pipeline import DTYPES, VERSION_GENERADOR, generar_mundo
from . import db

TAM_CHUNK = 64
VERSION_PAQUETE = 1


# Celdas de 5 m: a 50 m las distancias sociales no cerraban (hablarse a 300 m) y la gente quedaba
# amontonada en la misma celda. 2048×2048 a 5 m = 10,2 km de lado.
TAM_CELDA_POR_DEFECTO = 5
ANCHO_POR_DEFECTO = 2048


class MundoYaExiste(Exception):
    pass


def _le(arr: np.ndarray, dtype) -> np.ndarray:
    """Array contiguo en little-endian (formato fijo en disco)."""
    return np.ascontiguousarray(arr.astype(np.dtype(dtype).newbyteorder("<")))


def hash_capas(capas: Dict[str, np.ndarray]) -> str:
    h = hashlib.sha256()
    for nombre in sorted(capas):
        h.update(nombre.encode())
        h.update(_le(capas[nombre], DTYPES[nombre]).tobytes())
    return h.hexdigest()


# --------------------------------------------------------------------- meta

def guardar_meta(con: sqlite3.Connection, **valores) -> None:
    with con:
        for k, v in valores.items():
            con.execute("INSERT OR REPLACE INTO meta (clave, valor) VALUES (?, ?)", (k, json.dumps(v)))


def cargar_meta(con: sqlite3.Connection) -> dict:
    return {r["clave"]: json.loads(r["valor"]) for r in con.execute("SELECT clave, valor FROM meta")}


# -------------------------------------------------------------------- mundo

def guardar_mundo(con: sqlite3.Connection, mundo: dict, nombre: str = "") -> None:
    """Guarda un mundo generado en una base VACÍA. Nunca sobrescribe un mundo existente."""
    if con.execute("SELECT 1 FROM meta WHERE clave='semilla'").fetchone():
        raise MundoYaExiste("Esta base ya contiene un mundo; no se sobrescribe.")
    meta, capas = mundo["meta"], mundo["capas"]
    guardar_capas(con, capas, dimension=0)
    guardar_meta(con, **meta, tam_chunk=TAM_CHUNK, hash_capas=hash_capas(capas),
                 esquema_capas={k: np.dtype(v).name for k, v in DTYPES.items()},
                 nombre=nombre, creado_en=datetime.now().isoformat(timespec="seconds"))


def guardar_capas(con: sqlite3.Connection, capas: Dict[str, np.ndarray], dimension: int = 0) -> None:
    """Escribe un mapa entero por bloques comprimidos. La dimensión 0 es el mundo de siempre."""
    h, w = next(iter(capas.values())).shape
    with con:
        for nombre_capa, arr in capas.items():
            dt = DTYPES[nombre_capa]
            for cy in range(0, h, TAM_CHUNK):
                for cx in range(0, w, TAM_CHUNK):
                    sub = arr[cy:cy + TAM_CHUNK, cx:cx + TAM_CHUNK]
                    datos = zlib.compress(_le(sub, dt).tobytes(), 6)
                    con.execute("INSERT OR REPLACE INTO capas (dimension, capa, cx, cy, datos) VALUES (?,?,?,?,?)",
                                (int(dimension), nombre_capa, cx // TAM_CHUNK, cy // TAM_CHUNK, datos))


def cargar_capas(con: sqlite3.Connection, verificar: bool = False, dimension: int = 0) -> Dict[str, np.ndarray]:
    meta = cargar_meta(con)
    tam = meta.get("tam_chunk", TAM_CHUNK)
    esquema = meta.get("esquema_capas") or {k: np.dtype(v).name for k, v in DTYPES.items()}
    if dimension:
        d = dimension_por_id(con, dimension)
        if d is None:
            raise ValueError("No existe la dimensión %s en este mundo." % dimension)
        w, h, huella = d["ancho"], d["alto"], d["hash_capas"]
    else:
        w, h, huella = meta.get("ancho", 2048), meta.get("alto", 2048), meta.get("hash_capas")
    capas = {n: np.zeros((h, w), dtype=np.dtype(dt)) for n, dt in esquema.items()}
    for fila in con.execute("SELECT capa, cx, cy, datos FROM capas WHERE dimension = ?", (int(dimension),)):
        n = fila["capa"]
        if n not in esquema:
            continue
        x0, y0 = fila["cx"] * tam, fila["cy"] * tam
        sh = (min(tam, h - y0), min(tam, w - x0))
        dt = np.dtype(esquema[n]).newbyteorder("<")
        sub = np.frombuffer(zlib.decompress(fila["datos"]), dtype=dt).reshape(sh)
        capas[n][y0:y0 + sh[0], x0:x0 + sh[1]] = sub
    if verificar and huella and hash_capas(capas) != huella:
        raise ValueError("El mapa guardado no coincide con su huella (posible corrupción).")
    return capas


# --------------------------------------------------------------- dimensiones

def listar_dimensiones(con: sqlite3.Connection) -> List[dict]:
    """La 0 siempre existe aunque la tabla esté vacía: es el mundo de siempre, el de la tabla `meta`."""
    filas = [dict(r) for r in con.execute("SELECT * FROM dimensiones ORDER BY id")]
    if not any(d["id"] == 0 for d in filas):
        m = cargar_meta(con)
        filas.insert(0, {"id": 0, "ident": "mundo", "nombre": m.get("nombre") or "Mundo",
                         "semilla": m.get("semilla", 0), "ancho": m["ancho"], "alto": m["alto"],
                         "tam_celda_m": m["tam_celda_m"], "hash_capas": m.get("hash_capas"), "meta": "{}",
                         "creado_en": m.get("creado_en")})
    return filas


def dimension_por_id(con: sqlite3.Connection, dimension: int) -> Optional[dict]:
    for d in listar_dimensiones(con):
        if d["id"] == int(dimension):
            return d
    return None


def dimension_por_ident(con: sqlite3.Connection, ident: str) -> Optional[dict]:
    for d in listar_dimensiones(con):
        if d["ident"] == ident:
            return d
    return None


def crear_dimension(con: sqlite3.Connection, ident: str, semilla: Optional[int] = None,
                    ancho: Optional[int] = None, alto: Optional[int] = None,
                    tam_celda_m: Optional[float] = None, progreso=None) -> dict:
    """Genera y guarda el mapa de una dimensión nueva (cavernas, por ejemplo) dentro de este mundo.

    Es idempotente: si ya existe esa dimensión se devuelve la que hay. El mapa se genera con el MISMO
    algoritmo pedido por los datos de la dimensión y sus umbrales (`preset`), así que una dimensión nueva
    no pide código: es un JSON en `datos_base/dimensiones/`."""
    ya = dimension_por_ident(con, ident)
    if ya is not None:
        return ya
    m = cargar_meta(con)
    from ..registro import Registro
    d = Registro.cargar().uno("dimension", ident) or {}
    tamano = d.get("tamano") or {}
    ancho = int(ancho or tamano.get("ancho") or m["ancho"])
    alto = int(alto or tamano.get("alto") or m["alto"])
    tam_celda_m = float(tam_celda_m or tamano.get("tam_celda_m") or m["tam_celda_m"])
    semilla = int(m["semilla"] if semilla is None else semilla)
    # Semilla propia derivada de la del mundo: dos dimensiones del mismo mundo no pueden salir iguales,
    # y el mundo sigue siendo reproducible desde su semilla.
    semilla_dim = (semilla * 2654435761 + sum(ident.encode())) & 0x7FFFFFFF
    mundo = generar_mundo(semilla_dim, ancho, alto, tam_celda_m, progreso=progreso, dimension=ident)
    siguiente = (con.execute("SELECT COALESCE(MAX(id), 0) FROM dimensiones").fetchone()[0] or 0) + 1
    with con:
        con.execute("INSERT INTO dimensiones (id, ident, nombre, semilla, ancho, alto, tam_celda_m, hash_capas, meta, creado_en) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (siguiente, ident, d.get("nombre") or ident, semilla_dim, ancho, alto, tam_celda_m,
                     hash_capas(mundo["capas"]), json.dumps(mundo["meta"]),
                     datetime.now().isoformat(timespec="seconds")))
    guardar_capas(con, mundo["capas"], dimension=siguiente)
    return dimension_por_id(con, siguiente)


def crear_mundo(dir_mundos: Path, semilla: int, ancho: int = ANCHO_POR_DEFECTO, alto: int = ANCHO_POR_DEFECTO,
                tam_celda_m: int = TAM_CELDA_POR_DEFECTO, nombre: Optional[str] = None, progreso=None) -> Path:
    """Genera un mundo nuevo en un archivo NUEVO dentro de dir_mundos.
    `progreso(fraccion, texto)` sirve para la pantalla de carga: generar 2048×2048 lleva más de un minuto."""
    dir_mundos = Path(dir_mundos)
    dir_mundos.mkdir(parents=True, exist_ok=True)
    base = nombre or "mundo_%d" % semilla
    base = re.sub(r"[^A-Za-z0-9_\-]", "_", base)
    ruta, i = dir_mundos / (base + ".db"), 2
    while ruta.exists():  # nunca pisar un mundo existente
        ruta = dir_mundos / ("%s_%d.db" % (base, i))
        i += 1
    mundo = generar_mundo(semilla, ancho, alto, tam_celda_m, progreso=progreso)
    if progreso:
        progreso(0.88, "Guardando el mundo")
    con = db.abrir(ruta, dir_backups=dir_mundos / "backups")
    try:
        guardar_mundo(con, mundo, nombre=ruta.stem)
        from ..agentes import ajustes as _aj
        _aj.guardar(con, {"modulos": {"hambre": True}})     # los mundos nuevos nacen con hambre
        registrar_evento(con, 480, "mundo_creado", origen="sistema", importancia=5,
                         texto="Se creó el mundo con semilla %d (generador %s)." % (semilla, VERSION_GENERADOR),
                         datos={"semilla": semilla, "ancho": ancho, "alto": alto})
    finally:
        con.close()
    return ruta


# ------------------------------------------------------------------ eventos

def registrar_evento(con: sqlite3.Connection, t_min: int, tipo: str, texto: str = "",
                     actor_id: Optional[int] = None, objetivo_id: Optional[int] = None,
                     x=None, y=None, z=None, causa: Optional[str] = None,
                     resultado: Optional[str] = None, importancia: int = 1,
                     origen: str = "autonomo", datos: Optional[dict] = None, dimension: int = 0) -> int:
    with con:
        cur = con.execute(
            """INSERT INTO eventos (t_min, tipo, actor_id, objetivo_id, x, y, z, causa, resultado,
                                    importancia, origen, datos, texto, dimension)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (t_min, tipo, actor_id, objetivo_id, x, y, z, causa, resultado, importancia, origen,
             json.dumps(datos or {}), texto, int(dimension)))
    return cur.lastrowid


def listar_eventos(con: sqlite3.Connection, tipo: Optional[str] = None, actor_id: Optional[int] = None,
                   antes_id: Optional[int] = None, limite: int = 100) -> List[dict]:
    sql, args = "SELECT * FROM eventos WHERE 1=1", []
    if tipo:
        sql += " AND tipo = ?"; args.append(tipo)
    if actor_id is not None:
        sql += " AND actor_id = ?"; args.append(actor_id)
    if antes_id is not None:
        sql += " AND id < ?"; args.append(antes_id)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(int(limite), 1000)))
    return [dict(r) for r in con.execute(sql, args)]


def tipos_de_evento(con: sqlite3.Connection) -> List[str]:
    return [r[0] for r in con.execute("SELECT DISTINCT tipo FROM eventos ORDER BY tipo")]


# --------------------------------------------------- exportar / importar

def exportar_paquete(ruta_db: Path, destino_zip: Path) -> Path:
    """Paquete portable: copia consistente de la base + metadatos legibles."""
    ruta_db, destino_zip = Path(ruta_db), Path(destino_zip)
    destino_zip.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "mundo.db"
        origen = db.abrir(ruta_db)  # abrir NO destruye nada; migra con backup si hace falta
        try:
            db.hacer_backup(origen, copia)
            meta = cargar_meta(origen)
            n_hab = origen.execute("SELECT COUNT(*) FROM habitantes").fetchone()[0]
            n_ev = origen.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
            version_esquema = db.version_actual(origen)
        finally:
            origen.close()
        info = {"formato_paquete": VERSION_PAQUETE, "version_esquema": version_esquema,
                "exportado_en": datetime.now().isoformat(timespec="seconds"),
                "habitantes": n_hab, "eventos": n_ev, "meta": meta}
        with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copia, "mundo.db")
            z.writestr("meta.json", json.dumps(info, ensure_ascii=False, indent=2))
            z.writestr("LEEME.txt", "Paquete de Mundo Vivo. Contiene mundo.db (SQLite) y meta.json.\n"
                                    "Se restaura con: python -m mundo_vivo importar <este.zip>\n")
    return destino_zip


def importar_paquete(zip_path: Path, dir_mundos: Path, nombre: Optional[str] = None) -> Path:
    """Restaura un paquete como un mundo NUEVO (no pisa nada) y verifica su integridad."""
    dir_mundos = Path(dir_mundos)
    dir_mundos.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        info = json.loads(z.read("meta.json"))
        base = re.sub(r"[^A-Za-z0-9_\-]", "_", nombre or info["meta"].get("nombre") or "importado")
        ruta, i = dir_mundos / (base + ".db"), 2
        while ruta.exists():
            ruta = dir_mundos / ("%s_%d.db" % (base, i))
            i += 1
        ruta.write_bytes(z.read("mundo.db"))
    con = db.abrir(ruta, dir_backups=dir_mundos / "backups")
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("La base importada no pasó la verificación de integridad.")
        cargar_capas(con, verificar=True)
    finally:
        con.close()
    return ruta

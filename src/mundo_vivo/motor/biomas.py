"""Definición de biomas: sale de `datos_base/biomas/biomas.json` (tipo `bioma`), no del código.

Los ids numéricos se guardan en la base de datos de cada mundo: NO cambiar ni reordenar los existentes.
Cada entrada del JSON trae su `id_numerico`, el nombre y color que ve la gente, y las propiedades que usa
el motor:
  - `velocidad`: multiplicador de costo al caminar (más alto = más lento). `null` = intransitable.
  - `combustible`: cuán fácil arde el bioma (0..1).

El módulo sigue exponiendo lo mismo de siempre (`B.PRADERA`, `B.BIOMAS`, ...) para no romper los usos
que hay desparramados por todo el proyecto.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from ..registro import Registro

# id numérico -> (clave, nombre, color)
BIOMAS: Dict[int, Tuple[str, str, str]] = {}
# id numérico -> multiplicador de costo al caminar (None = intransitable)
VELOCIDAD: Dict[int, Optional[float]] = {}
# id numérico -> combustible base 0..1
COMBUSTIBLE: Dict[int, float] = {}


def _cargar() -> None:
    entradas = Registro.cargar().de_tipo("bioma")
    if not entradas:
        raise RuntimeError("No hay biomas en el registro: falta datos_base/biomas/biomas.json")
    porid: Dict[int, dict] = {}
    for d in entradas.values():
        if "id_numerico" not in d:
            raise ValueError("El bioma «%s» no tiene «id_numerico»." % d.get("id"))
        n = int(d["id_numerico"])
        if n in porid:
            raise ValueError("Dos biomas comparten el id numérico %d: «%s» y «%s»."
                             % (n, porid[n]["id"], d["id"]))
        porid[n] = d
    for n in sorted(porid):                       # orden estable por id (lo que ve la UI)
        d = porid[n]
        BIOMAS[n] = (str(d["id"]), str(d.get("nombre") or d["id"]), str(d.get("color") or "#888888"))
        v = d.get("velocidad")
        VELOCIDAD[n] = None if v is None else float(v)
        COMBUSTIBLE[n] = float(d.get("combustible") or 0.0)
        # constante con el nombre en mayúsculas: B.PRADERA, B.BOSQUE_FRIO, ...
        globals()[str(d["id"]).upper()] = n


_cargar()

# Constantes declaradas acá sólo para que se vean de un vistazo y las encuentren los editores;
# el valor real lo pone `_cargar()` desde el JSON (si faltara una, el import explota al toque).
OCEANO_PROFUNDO: int = globals()["OCEANO_PROFUNDO"]
OCEANO: int = globals()["OCEANO"]
PLAYA: int = globals()["PLAYA"]
DESIERTO: int = globals()["DESIERTO"]
SABANA: int = globals()["SABANA"]
PRADERA: int = globals()["PRADERA"]
BOSQUE_TEMPLADO: int = globals()["BOSQUE_TEMPLADO"]
SELVA: int = globals()["SELVA"]
PANTANO: int = globals()["PANTANO"]
BOSQUE_FRIO: int = globals()["BOSQUE_FRIO"]
TUNDRA: int = globals()["TUNDRA"]
NIEVE: int = globals()["NIEVE"]
MONTANA: int = globals()["MONTANA"]
VOLCAN: int = globals()["VOLCAN"]
LAGO: int = globals()["LAGO"]


def tabla(fuente: Dict[int, Optional[float]], ausente: float) -> list:
    """Tabla de 256 posiciones (id numérico -> valor) para traducir la capa «bioma» de un saque.

    Se arma UNA vez al construir el terreno o el fuego, nunca por celda ni por tick.
    """
    t = [float(ausente)] * 256
    for n, v in fuente.items():
        t[n] = float(ausente) if v is None else float(v)
    return t


# códigos de la capa "agua"
AGUA_NINGUNA = 0
AGUA_OCEANO = 1
AGUA_LAGO = 2
AGUA_RIO = 3

# bits de la capa "rasgos"
RASGO_CASCADA = 1
RASGO_LAVA = 2

"""Derivación determinista de semillas para generadores por subsistema.

La utilidad es pura: recibe una semilla raíz del mundo y un nombre estable de
subsistema, y devuelve un entero de semilla reproducible. No toca estado global,
no crea generadores globales y no modifica generadores existentes.

La misma combinación raíz+nombre siempre devuelve la misma semilla, independientemente
del orden en que se soliciten otros streams. Agregar un nombre nuevo no altera los
resultados de los existentes.

La entrada se codifica de forma canónica: `raiz` como entero de 64 bits en orden
big-endian, seguido de un separador y de los bytes UTF-8 de `nombre`. Se aplica
SHA-256 y se convierte el digest completo a entero (256 bits), apto tanto para
`random.Random` como para `numpy.random.default_rng`.
"""

from __future__ import annotations

import hashlib

_SEPARADOR = b"\x00"           # separador de longitud fija entre raíz y nombre
_DIGEST_BYTES = 8              # bytes del digest SHA-256 usados para la semilla


def derivar_semilla(raiz: int, nombre: str) -> int:
    """Devuelve una semilla determinista para el subsistema `nombre`.

    Argumentos:
        raiz: semilla raíz del mundo, entero en [0, 2^64 - 1].
        nombre: identificador estable del subsistema, cadena no vacía.

    Retorna:
        Entero de 256 bits derivado de raíz+nombre.

    Lanza:
        TypeError: si `raiz` no es entero.
        ValueError: si `raiz` está fuera de rango o `nombre` no es una cadena no vacía.
    """
    if isinstance(raiz, bool) or not isinstance(raiz, int):
        raise TypeError("raiz debe ser un entero")
    if raiz < 0 or raiz > 2 ** 64 - 1:
        raise ValueError("raiz debe estar en el rango [0, 2^64 - 1]")
    if not isinstance(nombre, str) or not nombre:
        raise ValueError("nombre debe ser una cadena no vacía")

    h = hashlib.sha256()
    h.update(raiz.to_bytes(8, "big"))
    h.update(_SEPARADOR)
    h.update(nombre.encode("utf-8"))
    return int.from_bytes(h.digest(), "big")

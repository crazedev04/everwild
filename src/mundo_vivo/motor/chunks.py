"""Chunks espaciales de 64×64 celdas y LOD espacial (Etapa 6).

El mapa se divide en chunks; un chunk está "activo" si tiene habitantes, animales o fuego. Solo los
chunks activos se actualizan cada tick; el resto se actualiza cada N ticks (LOD). La grilla espacial
de fauna y el LOD cognitivo ya existen en `motor/fauna.py` y `motor/atencion.py`; esto es el índice
común que los junta y que el visor puede dibujar.
"""
from __future__ import annotations

CHUNK = 64


def chunks_de(ancho: int, alto: int) -> tuple:
    """Cantidad de chunks en X e Y."""
    return ((ancho + CHUNK - 1) // CHUNK, (alto + CHUNK - 1) // CHUNK)


def chunk_de(x: int, y: int) -> tuple:
    return (int(x) // CHUNK, int(y) // CHUNK)


def chunks_activos(sim) -> list:
    """Lista de [cx, cy] de los chunks que tienen algo que simular este tick."""
    ancho, alto = sim.terreno.ancho, sim.terreno.alto
    cxn, cyn = chunks_de(ancho, alto)
    activos = set()
    for h in getattr(sim, "habitantes", {}).values():
        if getattr(h, "vivo", True):
            activos.add(chunk_de(int(h.x), int(h.y)))
    fauna = getattr(sim, "fauna", None)
    if fauna is not None:
        for a in getattr(fauna, "animales", {}).values():
            if getattr(a, "vivo", True):
                activos.add(chunk_de(int(a.x), int(a.y)))
    fuego = getattr(sim, "fuego", None)
    if fuego is not None and getattr(fuego, "_hubo_fuego", False):
        try:
            ys, xs = __import__("numpy").nonzero(fuego.fuego)
            for x, y in zip(xs.tolist()[::64], ys.tolist()[::64]):
                activos.add(chunk_de(int(x), int(y)))
        except Exception:
            pass
    out = []
    for cx, cy in activos:
        if 0 <= cx < cxn and 0 <= cy < cyn:
            out.append([int(cx), int(cy)])
    return sorted(out)

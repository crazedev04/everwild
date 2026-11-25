"""Terreno transitable y búsqueda de caminos (A*).

Las coordenadas son celdas (x, y) enteras; una posición continua (1.5, 2.5) está en el centro de la celda (1, 2).
Costo de moverse = bioma x pendiente x río. Agua profunda, lava, cascadas y paredes son intransitables.
"""
from __future__ import annotations

import heapq
import math
from collections import deque
from typing import List, Optional, Tuple

import numpy as np

from . import biomas as B

VEL_BASE = 1.6  # celdas por minuto en terreno fácil (~4,8 km/h con celdas de 50 m)
PENDIENTE_MAX = 3.0  # más que eso es un acantilado; entre 0.6 y 3.0 se trepa muy despacio y se puede caer
_OFFS = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
         (1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)), (-1, -1, math.sqrt(2))]
INF = float("inf")
# Caché de viajes imposibles (ver `buscar_camino`). El bloque es en CELDAS a propósito: no es una
# distancia del mundo, es «me moví tan poco que el viaje sigue siendo el mismo».
BLOQUE_FRACASO = 4
TOPE_FRACASOS = 4096


def mult_bioma(bioma: np.ndarray) -> np.ndarray:
    """Multiplicador de costo al caminar por celda, sacado del registro de biomas.

    La tabla se arma una sola vez y se traduce el mapa entero de un saque (nunca celda por celda).
    Un bioma sin «velocidad» en el JSON es intransitable (inf).
    """
    tabla = np.array(B.tabla(B.VELOCIDAD, INF), dtype=np.float64)
    return tabla[np.asarray(bioma).astype(np.uint8)]


def _listas_compartiendo_floats(costo: np.ndarray) -> List[List[float]]:
    """`costo.tolist()`, pero con un solo objeto float por valor distinto.

    Por qué: `Terreno._c` es la copia en listas que usa el A* (indexar una lista de Python es mucho
    más rápido que indexar un array de numpy, que además fabrica un escalar en cada lectura). El
    problema es el tamaño. En un mapa de 2048² son 4,2 millones de celdas, y `tolist()` crea un
    objeto float por celda: 33,6 MB de punteros más 100 MB de floats, o sea 134 MB para una copia de
    un array de 33,6 MB.

    Lo que hace esto posible es un dato medido: en un mundo real de 2048² hay **3.809** valores
    distintos de costo en esos 4,2 millones de celdas (el costo sale de una tabla de biomas por un
    factor de pendiente que viene de una elevación entera, así que se repite muchísimo; además dos
    tercios del mapa son `inf`). Compartiendo un float por valor quedan los 33,6 MB de punteros y
    nada más: ~100 MB menos, con los mismos valores bit a bit y el A* igual de rápido.
    """
    unicos: dict = {}
    out = []
    for fila in costo.tolist():
        out.append([unicos.setdefault(v, v) for v in fila])
    return out


class Terreno:
    def __init__(self, capas: dict, tam_celda_m: float):
        elev = capas["elevacion"].astype(np.float64)
        gy, gx = np.gradient(elev)
        self.pendiente = np.hypot(gx, gy) / float(tam_celda_m)
        # `gx` y `gy` no se guardan: no se usaban en ninguna parte y en un mapa de 2048² eran 67 MB
        # de float64 vivos para siempre. Se calculan, dan la pendiente y se sueltan.
        self.elev = elev
        self.alto, self.ancho = elev.shape
        self.agua = capas["agua"]
        self.bioma = capas["bioma"]
        self.humedad = capas["humedad"]
        self.temperatura = capas["temperatura"]
        mult = mult_bioma(self.bioma)   # una vez al construir el terreno, no por tick
        costo = mult * (1.0 + 8.0 * np.minimum(self.pendiente, PENDIENTE_MAX) ** 2)
        rio = self.agua == B.AGUA_RIO
        costo[rio] = costo[rio] * np.where(capas["caudal"][rio] > 200, 8.0, 3.0)  # los ríos se vadean (o se nadan)
        bloqueado = ((self.agua == B.AGUA_OCEANO) | (self.agua == B.AGUA_LAGO) |
                     ((capas["rasgos"] & B.RASGO_LAVA) > 0) | ((capas["rasgos"] & B.RASGO_CASCADA) > 0) |
                     (self.pendiente > PENDIENTE_MAX))
        costo[bloqueado] = np.inf
        self.costo = costo
        self._c = _listas_compartiendo_floats(costo)
        self._mult_bioma = np.array(B.tabla(B.VELOCIDAD, INF), dtype=np.float64)
        # lo que el costo le debe al terreno y NO al bioma (pendiente, río): así cambiar el bioma de una
        # celda es una multiplicación y no hay que recalcular nada más
        ok = np.isfinite(costo) & np.isfinite(mult)
        self._factor_terreno = np.full(costo.shape, np.inf)
        np.divide(costo, np.maximum(1e-9, mult), out=self._factor_terreno, where=ok)
        self._fracasos: set = set()   # viajes que ya se comprobó que no se pueden hacer

    def cambiar_bioma(self, x: int, y: int, bioma: int) -> None:
        """Cambia el bioma de UNA celda y recalcula su costo.

        Existe por un detalle que no se ve: `self.costo` es el array y `self._c` es una COPIA en listas
        de Python, que es la que usa el A*. Escribir sólo una de las dos deja al A* caminando el mapa
        viejo para siempre. Lo usa el desgaste del suelo (ver motor/senderos.py).

        Y hay una tercera cosa que invalidar: la caché de viajes imposibles. Si el mapa cambió, lo
        que no se podía puede pasar a poderse (y al revés), así que los fracasos se olvidan.
        """
        if not self.dentro(x, y):
            return
        if self.bioma[y, x] == bioma:
            return                      # nada cambió: no hay por qué olvidar nada
        self.bioma[y, x] = bioma
        f = self._factor_terreno[y, x]
        c = INF if not np.isfinite(f) else float(self._mult_bioma[int(bioma)] * f)
        self.costo[y, x] = c
        self._c[y][x] = c
        self.olvidar_fracasos()

    def dentro(self, x: int, y: int) -> bool:
        return 0 <= x < self.ancho and 0 <= y < self.alto

    def caminable(self, x: int, y: int) -> bool:
        return self.dentro(x, y) and self._c[y][x] != INF

    def velocidad_en(self, x: float, y: float) -> float:
        c = self._c[min(self.alto - 1, max(0, int(y)))][min(self.ancho - 1, max(0, int(x)))]
        return VEL_BASE / (min(c, 4.0) if c != INF else 10.0)  # trepar cuesta cansa pero no es una tortuga: piso de ~0,4 celdas/min

    def humedad_aprox(self, x: int, y: int) -> float:
        """Humedad 0..1 de la celda (para decidir dónde se forman tormentas)."""
        if not self.dentro(x, y):
            return 0.5
        return float(self.humedad[y, x]) / 255.0

    def caminable_cerca(self, x: int, y: int, radio: int = 6) -> Optional[Tuple[int, int]]:
        for r in range(radio + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) == r and self.caminable(x + dx, y + dy):
                        return (x + dx, y + dy)
        return None

    def agua_adyacente(self, x: int, y: int) -> bool:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if self.dentro(x + dx, y + dy) and self.agua[y + dy, x + dx] > 0:
                    return True
        return False

    def componente(self, x: int, y: int) -> int:
        """Cantidad de celdas transitables conectadas a (x, y)."""
        if not self.caminable(x, y):
            return 0
        visto = {(x, y)}
        cola = deque([(x, y)])
        c = self._c
        while cola:
            cx, cy = cola.popleft()
            for ax, ay, _ in _OFFS:
                nx, ny = cx + ax, cy + ay
                if 0 <= nx < self.ancho and 0 <= ny < self.alto and (nx, ny) not in visto and c[ny][nx] != INF:
                    visto.add((nx, ny))
                    cola.append((nx, ny))
        return len(visto)

    def zona_conectada(self, x: int, y: int, tope: int = 400000) -> List[Tuple[int, int]]:
        """Celdas transitables alcanzables desde (x, y), hasta `tope`. Sirve para repartir gente por el mundo
        con la garantía de que puedan llegar unos a otros: en islas distintas no se encontrarían nunca."""
        if not self.caminable(x, y):
            return []
        visto = {(x, y)}
        cola = deque([(x, y)])
        c = self._c
        while cola and len(visto) < tope:
            cx, cy = cola.popleft()
            for ax, ay, _ in _OFFS:
                nx, ny = cx + ax, cy + ay
                if 0 <= nx < self.ancho and 0 <= ny < self.alto and (nx, ny) not in visto and c[ny][nx] != INF:
                    visto.add((nx, ny))
                    cola.append((nx, ny))
        return list(visto)

    def _clave_fracaso(self, origen: Tuple[int, int], destino: Tuple[int, int]) -> Tuple[int, int, int, int]:
        """Clave de la caché de fracasos: el destino exacto y el origen redondeado a un bloque.

        El origen va redondeado porque entre un intento y el siguiente la persona se movió unas
        pocas celdas, y para un viaje que no se puede hacer eso no cambia nada. El destino va exacto
        porque es el que decide si hay camino o no.
        """
        return (int(origen[0]) // BLOQUE_FRACASO, int(origen[1]) // BLOQUE_FRACASO,
                int(destino[0]), int(destino[1]))

    def olvidar_fracasos(self) -> None:
        """Se llama cuando el mapa cambia (ver `cambiar_bioma`): lo imposible puede volverse posible."""
        self._fracasos.clear()

    def buscar_camino(self, origen: Tuple[int, int], destino: Tuple[int, int],
                      max_exp: int = 40000) -> Optional[List[Tuple[int, int]]]:
        """Camino de menor costo (sin incluir el origen), o None si no hay.

        Una búsqueda que falla es lo más caro que hace el motor: agota el presupuesto de nodos antes
        de rendirse. Medido en un mundo de 2048² con celdas de 5 m: de 36 búsquedas en 3 días
        simulados, 24 fallaron y se llevaron 16,7 de los 19,1 segundos que pasó el motor dentro del
        A*. Y lo peor es que eran la MISMA búsqueda: el mismo destino imposible reintentado 12
        veces, a 0,7 s cada vez, porque nadie se acordaba de que no se podía.

        Así que los fracasos se recuerdan. Es una caché negativa acotada, y sólo se guarda el
        fracaso: si hay camino se devuelve y no se guarda nada, porque un camino caduca en cuanto
        alguien construye algo. Se vacía entera cuando el mapa cambia (`cambiar_bioma`).
        """
        ox, oy = origen
        dx, dy = destino
        c = self._c
        if not self.caminable(dx, dy):
            return None
        if (ox, oy) == (dx, dy):
            return []
        clave = self._clave_fracaso(origen, destino)
        if clave in self._fracasos:
            return None
        w, h = self.ancho, self.alto

        def costo_en(x, y):
            v = c[y][x]
            return 1.0 if v == INF else v

        def heur(x, y):
            a, b = abs(x - dx), abs(y - dy)
            return max(a, b) + (math.sqrt(2) - 1.0) * min(a, b)

        abiertos = [(heur(ox, oy), 0.0, ox, oy)]
        g = {(ox, oy): 0.0}
        previo = {}
        expandidos = 0
        while abiertos:
            _, gc, x, y = heapq.heappop(abiertos)
            if (x, y) == (dx, dy):
                camino = [(x, y)]
                while camino[-1] != (ox, oy):
                    camino.append(previo[camino[-1]])
                camino.reverse()
                return camino[1:]
            if gc > g.get((x, y), INF) + 1e-9:
                continue
            expandidos += 1
            if expandidos > max_exp:
                return self._anotar_fracaso(clave)
            cx = costo_en(x, y)
            for ax, ay, d in _OFFS:
                nx, ny = x + ax, y + ay
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                cn = c[ny][nx]
                if cn == INF:
                    continue
                if ax and ay and (c[y][nx] == INF or c[ny][x] == INF):
                    continue  # no cortar esquinas
                ng = gc + d * 0.5 * (cx + cn)
                if ng < g.get((nx, ny), INF):
                    g[(nx, ny)] = ng
                    previo[(nx, ny)] = (x, y)
                    heapq.heappush(abiertos, (ng + heur(nx, ny), ng, nx, ny))
        return self._anotar_fracaso(clave)

    def _anotar_fracaso(self, clave: Tuple[int, int, int, int]) -> None:
        """Se acuerda de un viaje que no se pudo hacer. Devuelve None, para usarla en el `return`."""
        if len(self._fracasos) >= TOPE_FRACASOS:
            self._fracasos.clear()   # acotada a lo bruto: lo que importa es no reintentar en ráfaga
        self._fracasos.add(clave)
        return None

"""
Fenómenos naturales (primera tanda): tormentas con lluvia y rayos, y derrumbes por gravedad.

Son reglas generales, no guiones: una tormenta aparece según la estación, se desplaza con el viento,
llueve (apaga fuegos), lanza rayos (pueden prender fuego o herir a alguien) y, si hay pendientes
empinadas debajo, puede soltar rocas que ruedan cuesta abajo siguiendo la gravedad.
El resto de los fenómenos está en docs/CATALOGO_FENOMENOS.md.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from . import biomas as B
from . import reloj

MAX_TORMENTAS = 3
PEND_DERRUMBE = 0.55   # pendiente mínima donde pueden soltarse rocas


@dataclass
class Tormenta:
    x: float
    y: float
    r: float
    vx: float
    vy: float
    intensidad: float
    restante: float  # minutos de vida

    def a_lista(self) -> list:
        return [round(self.x, 2), round(self.y, 2), round(self.r, 2), round(self.intensidad, 2)]


class Clima:
    def __init__(self, ancho: int, alto: int, semilla: int, viento: Tuple[float, float]):
        self.ancho, self.alto = ancho, alto
        self.rng = random.Random(int(semilla) * 7919 + 13)
        self.viento = viento
        self.tormentas: List[Tormenta] = []

    # ----------------------------------------------------------------- consulta
    def lluvia_en(self, x: float, y: float) -> float:
        """Intensidad de lluvia 0..1 en un punto (cuando hay varias tormentas, gana la más fuerte)."""
        mejor = 0.0
        for t in self.tormentas:
            d2 = ((x - t.x) ** 2 + (y - t.y) ** 2) / (t.r ** 2)
            if d2 < 1.0:
                mejor = max(mejor, t.intensidad * (1.0 - d2))
        return mejor

    def mascara_lluvia(self, forma: Tuple[int, int]) -> Optional[np.ndarray]:
        if not self.tormentas:
            return None
        h, w = forma
        m = np.zeros(forma, dtype=np.float32)
        yy, xx = np.ogrid[:h, :w]
        for t in self.tormentas:
            x0, x1 = max(0, int(t.x - t.r) - 1), min(w, int(t.x + t.r) + 2)
            y0, y1 = max(0, int(t.y - t.r) - 1), min(h, int(t.y + t.r) + 2)
            if x0 >= x1 or y0 >= y1:
                continue
            d2 = ((xx[:, x0:x1] + 0.5 - t.x) ** 2 + (yy[y0:y1, :] + 0.5 - t.y) ** 2) / (t.r ** 2)
            v = np.clip(1.0 - d2, 0.0, 1.0) * t.intensidad
            m[y0:y1, x0:x1] = np.maximum(m[y0:y1, x0:x1], v.astype(np.float32))
        return m

    def a_publico(self) -> list:
        return [t.a_lista() for t in self.tormentas]

    # -------------------------------------------------------------- persistencia
    def exportar(self) -> list:
        return [[t.x, t.y, t.r, t.vx, t.vy, t.intensidad, t.restante] for t in self.tormentas]

    def importar(self, datos: list) -> None:
        self.tormentas = [Tormenta(*[float(v) for v in d]) for d in datos][:MAX_TORMENTAS]

    # --------------------------------------------------------------------- paso
    def paso(self, sim, dt: float) -> None:
        t_min = sim.t
        # nacimiento de tormentas (más probables en verano y primavera)
        if len(self.tormentas) < MAX_TORMENTAS and self.rng.random() < dt * reloj.probabilidad_tormenta(t_min) / reloj.MIN_DIA:
            self._nueva(sim)
        for t in list(self.tormentas):
            t.x += t.vx * dt
            t.y += t.vy * dt
            t.restante -= dt
            if t.restante <= 0 or not (-t.r < t.x < self.ancho + t.r and -t.r < t.y < self.alto + t.r):
                self.tormentas.remove(t)
                continue
            # rayos: más tormenta, más rayos
            if self.rng.random() < dt * 0.04 * t.intensidad ** 2:
                ang, rad = self.rng.random() * 2 * math.pi, t.r * math.sqrt(self.rng.random()) * 0.9
                sim.rayo(int(t.x + math.cos(ang) * rad), int(t.y + math.sin(ang) * rad))
            # derrumbes por gravedad bajo la lluvia
            if self.rng.random() < dt * 0.006 * t.intensidad:
                self._intentar_derrumbe(sim, t)

    def _nueva(self, sim) -> None:
        vx, vy = self.viento
        for _ in range(30):  # aparecen más fácil sobre zonas húmedas
            x, y = self.rng.random() * self.ancho, self.rng.random() * self.alto
            hum = sim.terreno.humedad_aprox(int(x), int(y))
            if self.rng.random() < 0.25 + hum:
                break
        vel = 0.10 + 0.12 * self.rng.random()
        self.tormentas.append(Tormenta(x, y, 10 + 18 * self.rng.random(), vx * vel, vy * vel,
                                       0.4 + 0.6 * self.rng.random(), 180 + 360 * self.rng.random()))

    def _intentar_derrumbe(self, sim, t: Tormenta) -> None:
        for _ in range(25):
            ang, rad = self.rng.random() * 2 * math.pi, t.r * math.sqrt(self.rng.random())
            x, y = int(t.x + math.cos(ang) * rad), int(t.y + math.sin(ang) * rad)
            if sim.terreno.dentro(x, y) and sim.terreno.pendiente[y, x] >= PEND_DERRUMBE and sim.terreno.elev[y, x] > 100:
                sim.derrumbe(x, y)
                return


def camino_de_caida(terreno, x: int, y: int, largo: int = 14) -> List[Tuple[int, int]]:
    """Camino que sigue una roca cuesta abajo (gravedad): siempre hacia el vecino más bajo."""
    camino = [(x, y)]
    for _ in range(largo):
        cx, cy = camino[-1]
        mejor, mejor_e = None, terreno.elev[cy, cx]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nx, ny = cx + dx, cy + dy
                if (dx or dy) and terreno.dentro(nx, ny) and terreno.elev[ny, nx] < mejor_e:
                    mejor, mejor_e = (nx, ny), terreno.elev[ny, nx]
        if mejor is None:
            break
        camino.append(mejor)
        if terreno.agua[mejor[1], mejor[0]] > 0 or (len(camino) > 4 and terreno.pendiente[mejor[1], mejor[0]] < 0.15):
            break
    return camino

"""
Hábito: una red chica y PROPIA de cada persona que aprende de lo que le sale bien o mal.

Qué es
  - Entradas: cómo está (sed, cansancio, dolor, noche, compañía, soledad, aburrimiento, peligro, presas) y su carácter vivo (7 rasgos).
  - Salidas: cuánto «vale» para esta persona, ahora, cada tipo de actividad (explorar, buscar compañía, cazar, probar ideas, ir al agua...).
  - Aprende sola por experiencia (regresión online sobre la recompensa que vivió): lo que le trae cosas buenas gana valor, lo que la
    lastima lo pierde. Dos personas con la misma situación terminan inclinándose a cosas distintas.
  - Arranca distinta en cada una (pesos iniciales derivados de su genoma) y lo aprendido NO se hereda, como los recuerdos.
Qué NO es
  - No reemplaza al modelo de lenguaje: lo sesga (una línea en lo que siente) y manda cuando el modelo no responde.
Solo biblioteca estándar; unos 250 números por persona.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional

ACTIVIDADES = ("explorar", "acercarse", "conversar", "cazar", "inventar", "agua", "esperar", "dormir")
FRASE = {"explorar": "explorar", "acercarse": "buscar compañía", "conversar": "conversar", "cazar": "cazar",
         "inventar": "probar ideas nuevas", "agua": "ir al agua", "esperar": "quedarte quieto", "dormir": "dormir"}
SENALES = ("sed", "cansancio", "dolor", "noche", "hay_otros", "soledad", "aburrimiento", "peligro", "presas")
RASGOS = ("audacia", "sociabilidad", "curiosidad", "agresividad", "cautela", "empatia", "resiliencia")
N_IN, N_OC, N_OUT = len(SENALES) + len(RASGOS), 8, len(ACTIVIDADES)
N_PESOS = N_IN * N_OC + N_OC + N_OC * N_OUT + N_OUT
TASA = 0.12


def _inicial(semilla_pesos: List[float]) -> List[float]:
    """Pesos de arranque: pequeños y propios, tomados del genoma (cada persona parte con inclinaciones distintas)."""
    if not semilla_pesos:
        rng = random.Random(1)
        return [rng.uniform(-0.2, 0.2) for _ in range(N_PESOS)]
    return [0.25 * math.tanh(semilla_pesos[i % len(semilla_pesos)] * (1.0 + (i // len(semilla_pesos)) * 0.37)) for i in range(N_PESOS)]


class Habito:
    def __init__(self, pesos: Optional[List[float]] = None, n: int = 0, genoma_pesos: Optional[List[float]] = None):
        self.w = list(pesos) if pesos and len(pesos) == N_PESOS else _inicial(genoma_pesos or [])
        self.n = int(n)                      # cuántas experiencias aprendió

    # ----------------------------------------------------------------- red
    def _adelante(self, x: List[float]):
        w = self.w
        i = 0
        oc = []
        for _ in range(N_OC):
            oc.append(sum(x[j] * w[i + j] for j in range(N_IN)))
            i += N_IN
        for k in range(N_OC):
            oc[k] = math.tanh(oc[k] + w[i + k])
        i += N_OC
        sal = []
        for _ in range(N_OUT):
            sal.append(sum(oc[k] * w[i + k] for k in range(N_OC)))
            i += N_OC
        sal = [math.tanh(sal[a] + w[i + a]) for a in range(N_OUT)]
        return oc, sal

    def valores(self, x: List[float]) -> Dict[str, float]:
        return dict(zip(ACTIVIDADES, self._adelante(x)[1]))

    def aprender(self, x: List[float], actividad: str, recompensa: float) -> float:
        """Un paso de descenso por gradiente hacia la recompensa vivida. Devuelve el error previo."""
        a = ACTIVIDADES.index(actividad)
        oc, sal = self._adelante(x)
        meta = max(-1.0, min(1.0, recompensa))
        err = meta - sal[a]
        d_out = err * (1.0 - sal[a] ** 2)                    # derivada de tanh
        w = self.w
        base_out = N_IN * N_OC + N_OC
        d_oc = [d_out * w[base_out + a * N_OC + k] * (1.0 - oc[k] ** 2) for k in range(N_OC)]
        for k in range(N_OC):
            w[base_out + a * N_OC + k] += TASA * d_out * oc[k]
        w[base_out + N_OC * N_OUT + a] += TASA * d_out
        for k in range(N_OC):
            for j in range(N_IN):
                w[k * N_IN + j] += TASA * d_oc[k] * x[j]
            w[N_IN * N_OC + k] += TASA * d_oc[k]
        self.n += 1
        return abs(err)

    # ---------------------------------------------------------------- estado
    def a_dict(self) -> dict:
        return {"w": [round(v, 4) for v in self.w], "n": self.n}

    @staticmethod
    def de_dict(d: Optional[dict], genoma_pesos: Optional[List[float]] = None) -> "Habito":
        if not d:
            return Habito(genoma_pesos=genoma_pesos)
        return Habito(d.get("w"), d.get("n", 0), genoma_pesos)


def senales(h, sim, hay_otros: bool, soledad_dias: float, aburrimiento_dias: float, peligro: bool, presas: int) -> List[float]:
    """Vector de entrada: cuerpo, entorno y carácter vivo, todo en 0..1."""
    from ..motor import reloj
    c = lambda v: max(0.0, min(1.0, v))
    x = [c(h.sed / 100.0), c((100.0 - h.energia) / 100.0), c((100.0 - h.salud) / 100.0),
         1.0 if reloj.es_noche(sim.t) else 0.0, 1.0 if hay_otros else 0.0, c(soledad_dias / 4.0), c(aburrimiento_dias / 6.0),
         1.0 if peligro else 0.0, c(presas / 4.0)]
    x += [h.rasgo(r) for r in RASGOS]
    return x


def actividad_de(accion: dict) -> Optional[str]:
    """Qué tipo de actividad es la acción que se eligió (None = no se aprende de ella)."""
    t = accion.get("tipo")
    if t == "ir":
        m = accion.get("motivo", "")
        return "explorar" if m in ("explora", "vuelve con los suyos") else "agua" if accion.get("luego") == "beber" or "agua" in m or "sed" in m else None
    return {"esperar": "esperar", "dormir": "dormir", "beber": "agua", "hablar": "conversar", "ir_hacia": "acercarse", "buscar": "acercarse",
            "cazar": "cazar", "inventar": "inventar", "juntar": "inventar", "fabricar": "inventar", "encender": "inventar",
            "tomar_fuego": "inventar"}.get(t)


def recompensa(h, sim, snap: dict) -> float:
    """Qué tan bien le fue desde que eligió (snap) hasta ahora. -1 (muy mal) .. +1 (muy bien)."""
    r = 0.0
    d_salud = h.salud - snap["salud"]
    r += max(-0.8, min(0.3, d_salud / 40.0))
    if h.ataque_t > snap["t"]:
        r -= 0.5
    if snap["act"] == "agua" and snap["sed"] - h.sed > 15:
        r += 0.5
    if h.novedad_t > snap["novedad"]:
        r += 0.3
    if sim.t - 1e-9 > snap["t"] and max([v for v in h.ultima_charla.values()] + [0]) > snap["t"]:
        r += 0.35
    if len(h.conoce) > snap["conoce"]:
        r += 0.8
    if snap["act"] == "inventar" and sum(h.inventario.values()) > snap["inv"]:
        r += 0.3
    if snap["act"] == "cazar" and sum(h.inventario.values()) > snap["inv"]:
        r += 0.6
    if snap["act"] == "esperar":
        r -= 0.05                       # quedarse quieto no da nada
    if not snap.get("ok", True):
        r -= 0.2
    return max(-1.0, min(1.0, r))

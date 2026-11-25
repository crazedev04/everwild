"""
Un mundo con más de un mapa: el de siempre y las dimensiones que se le agreguen (cavernas, por ejemplo).

Por qué una `Simulacion` por dimensión y no una sola Simulación con todo adentro: un mapa distinto es
*otro* terreno, otro fuego, otro clima, otra fauna y otra nieve. Meter la dimensión como un parámetro más
habría obligado a tocar ~190 lugares que hoy dicen `self.terreno` y cada uno de ellos sería una chance de
que alguien camine por el mapa equivocado. Así, en cambio, cada simulación sigue siendo exactamente lo que
era, y lo que es del MUNDO (ajustes, conocimientos, relaciones, el cerebro) se comparte por referencia
(`Simulacion.compartir_con`).

Lo que sí es nuevo de verdad: una persona puede estar en un mapa o en el otro, y pasar de uno al otro por
una estructura que lo lleve (`provee.lleva_a` en los datos). El motor no sabe qué es una caverna ni qué es
un portal: sabe que una estructura puede llevar a una dimensión, igual que sabe que puede dar calor.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np

from .simulacion import HabitanteSim, Simulacion


class Mundo:
    def __init__(self, principal: Simulacion):
        self.sims: Dict[int, Simulacion] = {principal.dimension: principal}
        self.principal = principal
        principal.mundo = self
        self.al_crear_dimension = None   # callback(ident) -> Simulacion (lo pone sim_io; genera y guarda el mapa)

    # ------------------------------------------------------------------ acceso
    def agregar(self, sim: Simulacion) -> Simulacion:
        sim.compartir_con(self.principal)
        sim.t = self.principal.t
        sim.mundo = self
        self.sims[sim.dimension] = sim
        return sim

    def de_ident(self, ident: str) -> Optional[Simulacion]:
        for s in self.sims.values():
            if s.ident == ident:
                return s
        return None

    def dimensiones(self) -> List[dict]:
        return [{"id": s.dimension, "ident": s.ident, "nombre": (s.registro.uno("dimension", s.ident) or {}).get("nombre", s.ident),
                 "ancho": s.terreno.ancho, "alto": s.terreno.alto, "tam_celda_m": s.tam_celda_m,
                 "habitantes": sum(1 for h in s.habitantes.values() if h.vivo)}
                for s in sorted(self.sims.values(), key=lambda s: s.dimension)]

    def donde_esta(self, habitante_id: int) -> Optional[Simulacion]:
        for s in self.sims.values():
            if habitante_id in s.habitantes:
                return s
        return None

    # ------------------------------------------------------------------ avance
    def avanzar(self, dt_min: float) -> None:
        """Todas las dimensiones corren con el MISMO reloj. Si no, quien baja a la caverna y vuelve se
        encontraría con que arriba pasaron otras horas."""
        for s in sorted(self.sims.values(), key=lambda s: s.dimension):
            s.avanzar(dt_min)

    def vaciar_eventos(self) -> List[dict]:
        out = []
        for s in sorted(self.sims.values(), key=lambda s: s.dimension):
            for e in s.vaciar_eventos():
                e.setdefault("dimension", s.dimension)
                out.append(e)
        return out

    def vaciar_efectos(self) -> List[dict]:
        out = []
        for s in self.sims.values():
            for e in s.vaciar_efectos():
                e.setdefault("dimension", s.dimension)
                out.append(e)
        return out

    # ----------------------------------------------------------------- pasajes
    def pasaje_cerca(self, sim: Simulacion, h: HabitanteSim) -> Optional[dict]:
        """El paso a otra dimensión más cercano que tenga al alcance de la mano, si hay alguno.
        Mismo molde que `calor_disponible`: el dato manda, el motor sólo lee `provee.lleva_a`."""
        mejor = None
        for r in sim.refugios:
            e = sim.estructuras.get(r.get("tipo")) or {}
            destino = (e.get("provee") or {}).get("lleva_a")
            if not destino:
                continue
            d = math.hypot(r["x"] - h.x, r["y"] - h.y)
            if d <= sim.celdas(float(e.get("radio_m", 6.0)), minimo=1.5) and (mejor is None or d < mejor[0]):
                mejor = (d, {"a": destino, "x": r["x"], "y": r["y"], "tipo": r["tipo"], "rid": r.get("rid"), "r": r})
        return mejor[1] if mejor else None

    def otra_punta(self, origen: Simulacion, r: dict, destino: Simulacion) -> Optional[tuple]:
        """Dónde sale este paso del otro lado. La primera vez se elige (y queda del lado de allá una salida
        de vuelta); después siempre da al MISMO lugar, así bajar y volver te deja donde estabas."""
        d = r.get("destino")
        if d and len(d) == 2:
            return float(d[0]), float(d[1])
        import random as _random
        rng = _random.Random(destino.semilla * 7919 + int(r.get("rid") or 0) * 31 + origen.dimension)
        libres = np.argwhere(np.isfinite(destino.terreno.costo))
        if not len(libres):
            return None
        y, x = libres[rng.randrange(len(libres))]
        pos = (float(x) + 0.5, float(y) + 0.5)
        r["destino"] = [round(pos[0], 2), round(pos[1], 2)]
        vuelta = self._tipo_que_lleva_a(destino, origen.ident)
        if vuelta:      # una salida de vuelta, en el mismo lugar donde uno aparece
            destino.refugios.append({"rid": destino._nuevo_refugio(), "x": pos[0], "y": pos[1], "dueno": None,
                                     "tipo": vuelta, "nombre": destino.estructuras[vuelta].get("nombre", vuelta),
                                     "abrigo": 0.0, "t": int(destino.t), "natural": True,
                                     "destino": [round(r["x"], 2), round(r["y"], 2)]})
        return pos

    @staticmethod
    def _tipo_que_lleva_a(sim: Simulacion, ident: str) -> Optional[str]:
        for eid, e in sim.estructuras.items():
            if (e.get("provee") or {}).get("lleva_a") == ident:
                return eid
        return None

    def dimension_para(self, ident: str) -> Optional[Simulacion]:
        """La simulación de esa dimensión, creándola si todavía no existe en este mundo."""
        s = self.de_ident(ident)
        if s is not None:
            return s
        if self.al_crear_dimension is None:
            return None
        return self.al_crear_dimension(ident)

    def mover(self, h: HabitanteSim, destino: Simulacion, x: Optional[float] = None,
              y: Optional[float] = None) -> bool:
        """Pasa a alguien de un mapa al otro. Deja de existir en el de origen y aparece en el de destino,
        en una celda transitable: nadie puede quedar dentro de la roca."""
        origen = self.donde_esta(h.id)
        if origen is None or origen is destino:
            return False
        if x is None or y is None:
            x, y = destino.terreno.ancho / 2.0, destino.terreno.alto / 2.0
        c = destino.terreno.caminable_cerca(int(x), int(y), 40)
        if c is None:
            return False
        origen.habitantes.pop(h.id, None)
        if h.montura is not None:          # el animal se queda de este lado
            a = origen.fauna.animales.get(h.montura)
            if a is not None:
                a.jinete = None
            h.montura = None
        h.x, h.y = c[0] + 0.5, c[1] + 0.5
        h.camino, h.al_llegar, h.accion, h.hasta = [], None, "libre", 0.0
        h.mensajes, h.propuesta = [], None
        destino.habitantes[h.id] = h
        return True

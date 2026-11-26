"""
Fauna del mundo: animales terrestres, acuáticos y voladores definidos en JSON (`datos_base/fauna/especies.json`).

Diseño (lecciones de RimWorld / Dwarf Fortress / ecología simple):
- Pocas poblaciones, acotadas por especie y en total, para no cargar la computadora.
- Cada especie vive en sus biomas; los herbívoros comen del suelo (no si se quemó), los carnívoros cazan presas.
- Equilibrio: nacen más si hay espacio y comida; mueren de vejez, hambre, fuego o cazados. Si una especie casi se extingue
  llega algún ejemplar nuevo (como el "narrador" de RimWorld, que evita colapsos bruscos).
- Los animales reaccionan al fuego (huyen, mueren si están en una celda ardiendo): un incendio también es un hecho de fauna.
- El motor solo mueve y valida; la interacción con las personas (caza, ataques, monta) está en `ecologia.py`.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import biomas as B
from .semilla import derivar_semilla

TICK_MIN = 5.0            # cada cuántos minutos del mundo se piensa la fauna
TICK_MAX = 30.0           # a velocidades altas se agrupan ticks (no se pierde precisión importante)
MAX_TOTAL = 450
MAX_POR_ESPECIE = 40
CELDA_GRID = 8
ESCALA_VEL = 0.6          # celdas por minuto al perseguir/huir = velocidad * ESCALA_VEL
FRACCION_PASEO = 0.12     # caminando tranquilo se mueve esa fracción
RADIO_CAZA = 8.0
RADIO_HUIDA = 6.0
CLAVES_HABITAT = {v[0] for v in B.BIOMAS.values()} | {"rio"}
_DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


class Animal:
    __slots__ = ("id", "sp", "x", "y", "hx", "hy", "hambre", "edad", "jinete", "huye_hasta", "provocado_hasta", "ataque_hasta")

    def __init__(self, id: int, sp: str, x: float, y: float, hambre: float = 0.0, edad: float = 0.0):
        self.id, self.sp, self.x, self.y = id, sp, float(x), float(y)
        self.hx, self.hy = float(x), float(y)       # "hogar" (los voladores no se alejan mucho)
        self.hambre, self.edad = hambre, edad
        self.jinete: Optional[int] = None
        self.huye_hasta = 0.0
        self.provocado_hasta = 0.0
        self.ataque_hasta = 0.0

    def a_dict(self) -> dict:
        return {"id": self.id, "sp": self.sp, "x": round(self.x, 2), "y": round(self.y, 2), "h": round(self.hambre, 3),
                "e": round(self.edad, 1), "j": self.jinete}


class Fauna:
    def __init__(self, terreno, fuego, semilla: int, especies: Dict[str, dict]):
        self.mutaciones: list = []       # variantes que aparecieron (las avisa el motor)
        self.terreno, self.fuego, self.esp = terreno, fuego, especies
        self.temp_fn = None                      # función (x, y) -> °C; la pone la simulación
        self.rng = random.Random(derivar_semilla(semilla, "fauna"))
        self.animales: Dict[int, Animal] = {}
        self._sig_id = 1
        self._acum = 0.0
        self._acum_dia = 0.0
        self.t = 0.0
        self.centro_seguro = None
        self.cuentas: Dict[str, int] = {}
        self.muertes: Dict[str, int] = {}        # causa -> cantidad (estadística para el observador)
        self.depredadores_de: Dict[str, set] = {k: set() for k in especies}
        for k, d in especies.items():
            for p in d.get("presas", []):
                self.depredadores_de[p].add(k)
        self.mascara: Dict[str, np.ndarray] = {}
        self.objetivo: Dict[str, int] = {}
        self._grid: Dict[Tuple[int, int], List[Animal]] = {}
        self._preparar()

    # ------------------------------------------------------------- preparación
    def _preparar(self) -> None:
        t = self.terreno
        tierra = np.isfinite(t.costo) & (t.agua == 0)
        claves = {v[0]: k for k, v in B.BIOMAS.items()}
        for sid, d in self.esp.items():
            m = np.zeros(t.bioma.shape, dtype=bool)
            for b in d["biomas"]:
                m |= (t.agua == B.AGUA_RIO) if b == "rio" else (t.bioma == claves[b])
            if d["medio"] == "tierra":
                m &= tierra
            elif d["medio"] == "agua":
                m &= (t.agua > 0)
            self.mascara[sid] = m
            n = int(m.sum())
            mult = 2.0 if d["peso_kg"] < 5 and d["dieta"] != "carnivoro" else 1.0     # las presas chicas son más numerosas
            self.objetivo[sid] = 0 if n < 40 else int(min(MAX_POR_ESPECIE, max(2, round(mult * d["densidad"] * n / 10000.0))))
        # el total no pasa del tope: se recorta proporcionalmente
        total = sum(self.objetivo.values())
        if total > MAX_TOTAL:
            f = MAX_TOTAL / total
            self.objetivo = {k: (max(1, int(v * f)) if v else 0) for k, v in self.objetivo.items()}

    def poblar_inicial(self, centro: Optional[Tuple[float, float]] = None) -> None:
        """Puebla el mundo. Cerca del punto de inicio de las personas no hay grandes depredadores (arranque amable)."""
        self.centro_seguro = centro
        for sid, n in self.objetivo.items():
            peligroso = self.esp[sid]["peligro"] >= 5 and self.esp[sid]["agresivo"] != "no"
            for _ in range(n):
                for _intento in range(12):
                    a = self._nacer(sid, edad_aleatoria=True, _quieto=True)
                    if a is None:
                        break
                    if peligroso and centro is not None and math.hypot(a.x - centro[0], a.y - centro[1]) < 45:
                        self.animales.pop(a.id, None)
                        self.cuentas[sid] -= 1
                        continue
                    break

    def _celda_al_azar(self, sid: str) -> Optional[Tuple[int, int]]:
        m = self.mascara[sid]
        idx = np.flatnonzero(m)
        if len(idx) == 0:
            return None
        k = int(idx[self.rng.randrange(len(idx))])
        return k % m.shape[1], k // m.shape[1]

    def _mutar(self, sid: str, x: int, y: int) -> str:
        """Al nacer, una especie puede derivar en una variante. Las variantes y sus condiciones son DATOS
        (`mutacion` en datos_base/fauna/): el motor no conoce ninguna por su nombre.

        Esto es lo que hace que un mundo largo no tenga siempre la misma fauna: un lobo que nace donde hace
        mucho frío puede salir lobo blanco, y esa variante se reproduce sola a partir de ahí.
        """
        mut = (self.esp.get(sid) or {}).get("mutacion")
        if not mut or self.rng.random() >= float(mut.get("prob_por_nacimiento", 0)):
            return sid
        temp = self.temp_fn(x + 0.5, y + 0.5) if self.temp_fn else 15.0
        for v in mut.get("variantes") or []:
            destino = v.get("a")
            if destino not in self.esp:
                continue
            rango = v.get("temperatura_C")
            if rango and not (float(rango[0]) <= temp < float(rango[1])):
                continue
            self.mutaciones.append({"de": sid, "a": destino, "x": x, "y": y, "t": self.t})
            return destino
        return sid

    def _nacer(self, sid: str, cerca: Optional[Tuple[float, float]] = None, edad_aleatoria: bool = False,
               _quieto: bool = False) -> Optional[Animal]:
        if len(self.animales) >= MAX_TOTAL:
            return None
        d = self.esp[sid]
        if cerca is not None:
            x, y = int(cerca[0]) + self.rng.randint(-1, 1), int(cerca[1]) + self.rng.randint(-1, 1)
            if not self._valida(sid, x, y):
                x, y = int(cerca[0]), int(cerca[1])
        else:
            c = self._celda_al_azar(sid)
            if c is None:
                return None
            x, y = c
            e_ = d
            if (not _quieto and self.centro_seguro is not None and e_["peligro"] >= 5 and e_["agresivo"] != "no"
                    and math.hypot(x - self.centro_seguro[0], y - self.centro_seguro[1]) < 45):
                return None
        sid = self._mutar(sid, x, y)          # a veces nace una variante (ver `mutacion` en los datos)
        d = self.esp[sid]
        a = Animal(self._sig_id, sid, x + 0.5, y + 0.5, hambre=self.rng.random() * 0.4,
                   edad=(self.rng.random() * 0.8 * d["vida_dias"] * 1440.0) if edad_aleatoria else 0.0)
        self._sig_id += 1
        self.animales[a.id] = a
        self.cuentas[sid] = self.cuentas.get(sid, 0) + 1
        return a

    # -------------------------------------------------------------- consultas
    def _valida(self, sid: str, x: int, y: int) -> bool:
        t = self.terreno
        if not t.dentro(x, y):
            return False
        if self.esp[sid]["medio"] == "aire":
            return True
        return bool(self.mascara[sid][y, x])

    def cerca(self, x: float, y: float, radio: float, sp: Optional[str] = None) -> List[Tuple[float, Animal]]:
        out = []
        r2 = radio * radio
        for a in self.animales.values():
            if sp is not None and a.sp != sp:
                continue
            dx, dy = a.x - x, a.y - y
            if dx * dx + dy * dy <= r2:
                out.append((math.hypot(dx, dy), a))
        out.sort(key=lambda p: p[0])
        return out

    def matar(self, a: Animal, causa: str) -> None:
        if self.animales.pop(a.id, None) is not None:
            self.cuentas[a.sp] = max(0, self.cuentas.get(a.sp, 1) - 1)
            self.muertes[causa] = self.muertes.get(causa, 0) + 1

    def resumen(self) -> List[dict]:
        out = []
        for sid, d in self.esp.items():
            n = self.cuentas.get(sid, 0)
            if n or self.objetivo.get(sid):
                out.append({"id": sid, "nombre": d["nombre"], "emoji": d["emoji"], "medio": d["medio"],
                            "n": n, "objetivo": self.objetivo.get(sid, 0), "peligro": d["peligro"]})
        return out

    def publico(self) -> List[list]:
        idx = self._idx
        return [[idx[a.sp], round(a.x, 1), round(a.y, 1)] for a in self.animales.values()]

    @property
    def _idx(self) -> Dict[str, int]:
        if not hasattr(self, "_idx_cache"):
            self._idx_cache = {k: i for i, k in enumerate(self.esp)}
        return self._idx_cache

    def catalogo_publico(self) -> List[dict]:
        # clase, peso y peligro van al visor para dibujar cada bicho con su forma y su tamaño real
        return [{"id": k, "nombre": d["nombre"], "emoji": d["emoji"], "medio": d["medio"], "clase": d["clase"],
                 "peso_kg": d["peso_kg"], "peligro": d.get("peligro", 0), "montable": bool(d.get("montable"))}
                for k, d in self.esp.items()]

    # ------------------------------------------------------------------ avance
    def paso(self, dt: float, t: float, humanos: Optional[list] = None) -> bool:
        """Avanza la fauna. Devuelve True si hubo un tick de cálculo (para chequear ataques solo entonces)."""
        self.t = t
        hubo = False
        self._acum += dt
        self._acum_dia += dt
        while self._acum >= TICK_MIN:
            tick = min(self._acum, TICK_MAX)
            self._acum -= tick
            self._tick(tick, humanos or [])
            hubo = True
        if self._acum_dia >= 1440.0:
            self._acum_dia = 0.0
            self._llegadas()
        return hubo

    def _llegadas(self) -> None:
        """Si una especie casi desaparece, llega algún ejemplar de afuera (evita extinciones por mala suerte)."""
        for sid, obj in self.objetivo.items():
            if obj and self.cuentas.get(sid, 0) < max(1, int(obj * 0.5)):
                self._nacer(sid)

    def _armar_grid(self) -> None:
        g: Dict[Tuple[int, int], List[Animal]] = {}
        for a in self.animales.values():
            g.setdefault((int(a.x) // CELDA_GRID, int(a.y) // CELDA_GRID), []).append(a)
        self._grid = g

    def _vecinos(self, x: float, y: float, radio: float):
        gx0, gx1 = int(x - radio) // CELDA_GRID, int(x + radio) // CELDA_GRID
        gy0, gy1 = int(y - radio) // CELDA_GRID, int(y + radio) // CELDA_GRID
        for gy in range(gy0, gy1 + 1):
            for gx in range(gx0, gx1 + 1):
                for a in self._grid.get((gx, gy), ()):
                    yield a

    def _paso_hacia(self, a: Animal, tx: float, ty: float, pasos: float, alejarse: bool = False) -> None:
        sid = a.sp
        n = int(pasos + self.rng.random())
        for _ in range(max(0, n)):
            dx, dy = tx - a.x, ty - a.y
            d = math.hypot(dx, dy)
            if d < 1e-6:
                break
            sx, sy = (dx / d, dy / d)
            if alejarse:
                sx, sy = -sx, -sy
            nx, ny = a.x + sx, a.y + sy
            if self._valida(sid, int(nx), int(ny)):
                a.x, a.y = nx, ny
            else:   # prueba un costado
                for ax, ay in ((sy, -sx), (-sy, sx)):
                    nx, ny = a.x + ax, a.y + ay
                    if self._valida(sid, int(nx), int(ny)):
                        a.x, a.y = nx, ny
                        break

    def _pasear(self, a: Animal, pasos: float) -> None:
        n = int(pasos + self.rng.random())
        d = self.esp[a.sp]
        for _ in range(max(0, n)):
            dx, dy = self.rng.choice(_DIRS)
            nx, ny = a.x + dx, a.y + dy
            if d["medio"] == "aire" and math.hypot(nx - a.hx, ny - a.hy) > 25:
                dx, dy = (a.hx - a.x), (a.hy - a.y)
                m = math.hypot(dx, dy) or 1.0
                nx, ny = a.x + dx / m, a.y + dy / m
            if self._valida(a.sp, int(nx), int(ny)):
                a.x, a.y = nx, ny

    def _tick(self, dt: float, humanos: list) -> None:
        self._armar_grid()
        rng = self.rng
        fuego = self.fuego
        hay_fuego = fuego._hubo_fuego
        h_obj = self.terreno
        muertos: List[Tuple[Animal, str]] = []
        nacer: List[Animal] = []
        for a in list(self.animales.values()):
            if a.id not in self.animales:
                continue                         # lo cazaron en este mismo tick
            d = self.esp[a.sp]
            a.edad += dt
            a.hambre += dt / (d["ayuno_dias"] * 1440.0)
            if a.edad > d["vida_dias"] * 1440.0:
                muertos.append((a, "vejez"))
                continue
            if a.hambre >= 2.0:
                muertos.append((a, "hambre"))
                continue
            ix, iy = int(a.x), int(a.y)
            if a.jinete is not None:
                continue                         # lo lleva una persona
            vel = d["velocidad"] * ESCALA_VEL
            # --- frío: lo que no aguanta la temperatura de su zona se debilita y muere de a poco (el mundo repone con inmigración)
            if self.temp_fn is not None and d["medio"] != "agua":
                T = self.temp_fn(a.x, a.y)
                if T < d["frio_min"] and rng.random() < dt / 1440.0 * 0.45 * min(3.0, (d["frio_min"] - T) / 6.0):
                    muertos.append((a, "frío"))
                    continue
            # --- fuego
            if hay_fuego and d["medio"] != "agua":
                if fuego.fuego[iy, ix] > 0:
                    if rng.random() < 0.7:
                        muertos.append((a, "fuego"))
                        continue
                x0, x1, y0, y1 = max(0, ix - 4), min(fuego.fuego.shape[1], ix + 5), max(0, iy - 4), min(fuego.fuego.shape[0], iy + 5)
                sub = fuego.fuego[y0:y1, x0:x1]
                if sub.any():
                    ys, xs = np.nonzero(sub)
                    k = int(np.argmin((xs + x0 - ix) ** 2 + (ys + y0 - iy) ** 2))
                    self._paso_hacia(a, float(xs[k] + x0), float(ys[k] + y0), vel * dt, alejarse=True)
                    continue
            # --- presas huyen de los depredadores y de las personas
            amenaza = None
            if d["peligro"] < 8 or d["dieta"] == "herbivoro":
                mejor = RADIO_HUIDA * RADIO_HUIDA
                for o in self._vecinos(a.x, a.y, RADIO_HUIDA):
                    if o.sp in self.depredadores_de[a.sp]:
                        dd = (o.x - a.x) ** 2 + (o.y - a.y) ** 2
                        if dd < mejor:
                            mejor, amenaza = dd, (o.x, o.y)
                if amenaza is None and d["agresivo"] == "no" and d["velocidad"] > 0:
                    for h in humanos:
                        dd = (h.x - a.x) ** 2 + (h.y - a.y) ** 2
                        if dd < 16.0 and dd < mejor:
                            mejor, amenaza = dd, (h.x, h.y)
            if amenaza is not None and d["velocidad"] > 0:
                self._paso_hacia(a, amenaza[0], amenaza[1], vel * dt, alejarse=True)
                continue
            if a.huye_hasta > self.t and humanos:
                h = min(humanos, key=lambda p: (p.x - a.x) ** 2 + (p.y - a.y) ** 2)
                self._paso_hacia(a, h.x, h.y, vel * dt, alejarse=True)
                continue
            # --- comer
            dieta = d["dieta"]
            if dieta == "filtrador":
                a.hambre = 0.0
            elif dieta in ("herbivoro", "omnivoro", "insectivoro") and self.mascara[a.sp][iy, ix] or (d["medio"] == "aire" and dieta in ("herbivoro", "omnivoro")):
                if fuego.quemado[iy, ix] < 0.3:
                    a.hambre = max(0.0, a.hambre - 0.6 * min(1.0, dt / 30.0 + 0.2))
            # --- cazar
            if d["presas"] and a.hambre > 0.35 and d["velocidad"] > 0:
                blanco = None
                mejor = RADIO_CAZA * RADIO_CAZA
                for o in self._vecinos(a.x, a.y, RADIO_CAZA):
                    if o.sp in d["presas"] and o.jinete is None:
                        dd = (o.x - a.x) ** 2 + (o.y - a.y) ** 2
                        if dd < mejor:
                            mejor, blanco = dd, o
                if blanco is None and d["agresivo"] == "siempre" and d["peligro"] >= 5 and a.hambre > 0.6:
                    for h in humanos:           # los grandes depredadores hambrientos también van por las personas
                        dd = (h.x - a.x) ** 2 + (h.y - a.y) ** 2
                        if dd < 49.0 and dd < mejor:
                            mejor, blanco = dd, h
                if blanco is not None:
                    self._paso_hacia(a, blanco.x, blanco.y, vel * dt)
                    if isinstance(blanco, Animal) and (blanco.x - a.x) ** 2 + (blanco.y - a.y) ** 2 <= 2.25 and rng.random() < 0.35:
                        muertos.append((blanco, "cazado"))
                        saciedad = max(0.25, min(1.5, self.esp[blanco.sp]["peso_kg"] / (0.08 * d["peso_kg"])))
                        a.hambre = max(0.0, a.hambre - saciedad)
                    continue
            # --- pasear
            if d["velocidad"] > 0:
                self._pasear(a, vel * dt * FRACCION_PASEO)
            # --- criar
            obj = self.objetivo.get(a.sp, 0)
            n = self.cuentas.get(a.sp, 0)
            if obj and n < obj * 1.4 and a.hambre < 0.5 and a.edad > 0.15 * d["vida_dias"] * 1440.0:
                p = dt / (1440.0 * min(120.0, max(8.0, d["vida_dias"] / 14.0))) * max(0.0, 1.0 - n / (obj * 1.3)) * 2.0
                if rng.random() < p:
                    nacer.append(a)
        for a, causa in muertos:
            self.matar(a, causa)
        for a in nacer:
            self._nacer(a.sp, cerca=(a.x, a.y))

    # --------------------------------------------------------------- guardado
    def exportar(self) -> dict:
        return {"sig_id": self._sig_id, "t": self.t, "acum": self._acum, "animales": [a.a_dict() for a in self.animales.values()],
                "muertes": self.muertes}

    def importar(self, d: dict) -> None:
        self.animales.clear()
        self.cuentas = {}
        for r in d.get("animales", []):
            if r["sp"] not in self.esp:
                continue          # una especie que ya no está en el catálogo
            a = Animal(int(r["id"]), r["sp"], r["x"], r["y"], hambre=r.get("h", 0.0), edad=r.get("e", 0.0))
            a.jinete = r.get("j")
            self.animales[a.id] = a
            self.cuentas[a.sp] = self.cuentas.get(a.sp, 0) + 1
        self._sig_id = max(int(d.get("sig_id", 1)), max(self.animales, default=0) + 1)
        self.muertes = dict(d.get("muertes", {}))

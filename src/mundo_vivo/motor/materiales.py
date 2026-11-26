"""Materiales del mundo: qué se puede juntar, dónde, con qué herramienta y cuánto queda en cada zona.

El motor no conoce ningún material por su nombre: todo sale del registro y se compila a tablas
planas una vez al crear el mundo. El bucle de 20 Hz nunca toca el registro ni el evaluador.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from . import biomas as B

TIEMPO_JUNTAR_MIN = 20.0
# En metros: los recursos se agotan por zona y vuelven a crecer. A 50 m/celda son zonas de 16x16 celdas.
METROS_ZONA = 800.0
DIAS_REGENERAR = 8.0
MIN_DIA = 1440.0

# Grupos de biomas que el motor usa para reglas propias (no son contenido: son atajos de lectura).
_BOSQUES = (B.BOSQUE_TEMPLADO, B.SELVA, B.BOSQUE_FRIO)
_PASTOS = (B.PRADERA, B.SABANA)


class MaterialesMixin:
    # ------------------------------------------------------- datos de materiales
    def _compilar_materiales(self) -> None:
        """Del registro a tablas planas. Se hace UNA vez al crear el mundo."""
        por_clave = {v[0]: k for k, v in B.BIOMAS.items()}
        self.recoleccion: Dict[str, tuple] = {}     # material -> (biomas,)
        self.prob_rec: Dict[str, float] = {}
        self.cant_rec: Dict[str, tuple] = {}
        self.capacidad: Dict[str, int] = {}
        self.herramienta_rec: Dict[str, str] = {}   # material -> propiedad que hace falta llevar
        self.lena: tuple = ()
        lena = []
        for mid, d in self.registro.de_tipo("material").items():
            r = d.get("recoleccion") or {}
            prop = (r.get("requiere") or {}).get("propiedad")
            if prop:
                self.herramienta_rec[mid] = str(prop)
            if r.get("biomas"):
                self.recoleccion[mid] = tuple(por_clave[b] if isinstance(b, str) else b for b in r["biomas"])
            if r.get("prob") is not None:
                self.prob_rec[mid] = float(r["prob"])
            if r.get("cantidad"):
                self.cant_rec[mid] = tuple(r["cantidad"])
            if r.get("capacidad_zona") is not None:
                self.capacidad[mid] = int(r["capacidad_zona"])
            if d.get("lena"):
                lena.append(mid)
        self.lena = tuple(sorted(lena))
        # Armas, antorchas y objetivos: también datos. El alcance va en METROS en el JSON y se pasa a celdas
        # aca, una sola vez: en celdas, a 5 m por celda las armas tenian 10 veces menos alcance.
        self.armas: Dict[str, tuple] = {}
        antorchas = []
        for iid, d in self.registro.de_tipo("item").items():
            arma = d.get("arma")
            if arma:
                self.armas[iid] = (float(arma["bono_caza"]), self.celdas(float(arma["alcance_m"]), minimo=0.0))
            if d.get("antorcha"):
                antorchas.append(iid)
        # el palo pelado va ultimo: es el ultimo recurso para llevarse una llama
        # se respeta el ORDEN del archivo de datos: se prueba la primera que uno tenga encima
        self.antorchas = tuple(a for a in antorchas if a != "palo") + ("palo",)
        # Estado de agotamiento de zonas y depositos de fenomenos: se comparten con estructuras y fenomenos.
        self.agotamiento: dict = {}
        self.depositos: Dict[str, float] = {}

    # ------------------------------------------------------------ consultas
    def tiene(self, h, item: str) -> bool:
        return h.inventario.get(item, 0) > 0

    def lena_que_lleva(self, h) -> int:
        return sum(h.inventario.get(m, 0) for m in self.lena)

    def restante(self, x: float, y: float, mat: str) -> float:
        cap = self.capacidad.get(mat)
        if cap is None:
            return 99.0
        usado, t0 = self.agotamiento.get("%d,%d,%s" % (int(x) // self.zona, int(y) // self.zona, mat), (0.0, self.t))
        usado = max(0.0, usado - cap / DIAS_REGENERAR * (self.t - t0) / 1440.0)
        extra = self.depositos.get("%d,%d,%s" % (int(x) // self.zona, int(y) // self.zona, mat), 0.0)
        return cap + extra - usado

    def _gastar_recurso(self, x: float, y: float, mat: str, n: int) -> None:
        if mat not in self.capacidad:
            return
        k = "%d,%d,%s" % (int(x) // self.zona, int(y) // self.zona, mat)
        usado, t0 = self.agotamiento.get(k, (0.0, self.t))
        usado = max(0.0, usado - self.capacidad[mat] / DIAS_REGENERAR * (self.t - t0) / 1440.0) + n
        self.agotamiento[k] = (usado, self.t)
        if len(self.agotamiento) > 600:                          # poda las zonas ya regeneradas
            for kk in [kk for kk, (u, tt) in self.agotamiento.items() if u - self.capacidad.get(kk.split(",", 2)[2], 10) / DIAS_REGENERAR * (self.t - tt) / 1440.0 <= 0]:
                self.agotamiento.pop(kk, None)

    def agotados(self, h) -> List[str]:
        """Materiales que el bioma da pero que aca ya se juntaron todos (vuelven a crecer con los dias)."""
        return sorted(m for m in self.disponibles(h, con_agotados=True) if self.restante(h.x, h.y, m) < 1.0)

    def disponibles(self, h, con_agotados: bool = False) -> Dict[str, float]:
        """Que se puede juntar aca, con su probabilidad."""
        t = self.terreno
        x, y = int(h.x), int(h.y)
        if not t.dentro(x, y):
            return {}
        b = int(t.bioma[y, x])
        out: Dict[str, float] = {}
        for m, v in self.recoleccion.items():
            if b in v:
                out[m] = self.prob_rec.get(m, 0.5)
        zx, zy = int(x) // self.zona, int(y) // self.zona
        for k, n in self.depositos.items():          # lo que dejo caer un fenomeno
            if n > 0 and k.startswith("%d,%d," % (zx, zy)):
                out[k.split(",", 2)[2]] = 0.6
        cerca_agua = t.agua_adyacente(x, y)
        if cerca_agua or b == B.PANTANO:
            out["arcilla"] = self.prob_rec.get("arcilla", 0.5)
        if cerca_agua:
            out["pescado"] = 0.6 if any(self.tiene(h, i) for i in ("red_de_pesca", "arpon", "red_de_fibra")) else self.prob_rec.get("pescado", 0.5)
        if b in _BOSQUES and any(self.tiene(h, i) for i in self.recetas_con_propiedad("corta")):
            out["madera"] = self.prob_rec.get("madera", 0.5)
        if self.fogata_cerca(h, self.r_mano):
            out["ceniza"] = self.prob_rec.get("ceniza", 0.5); out["carbon"] = self.prob_rec.get("carbon", 0.5)
        # La roca dura no se junta con la mano: pide algo que golpee.
        if self.herramienta_rec:
            for m in [m for m in out if m in self.herramienta_rec]:
                if not any(self.tiene(h, i) for i in self.recetas_con_propiedad(self.herramienta_rec[m])):
                    out.pop(m)
        if not con_agotados:
            out = {m: p for m, p in out.items() if self.restante(x, y, m) >= 1.0}
        return out

    # -------------------------------------------------------------- juntar
    def _accion_juntar(self, h, it: dict) -> Tuple[bool, str]:
        mat = str(it.get("material", "")).strip().lower()
        col = self.cosechar_colonia(h) if self.modulo("colonias") else None
        if col and (not mat or mat == col[0]):          # esta parado sobre una colonia que da algo
            self._ganar_item(h, col[0], col[1])
            h.accion, h.detalle, h.hasta = "juntando", col[0], self.t + TIEMPO_JUNTAR_MIN
            h.camino = []
            return True, "Juntaste %d de %s de lo que crece aca." % (col[1], col[0])
        disp = self.disponibles(h)
        if mat not in disp:
            prop = self.herramienta_rec.get(mat)
            if prop and int(self.terreno.bioma[int(h.y), int(h.x)]) in self.recoleccion.get(mat, ()):
                return False, "Hay %s aca, pero esta metido en la roca: con las manos no sale." % mat
            if mat in self.agotados(h):
                return False, "Aca ya juntaste todo el %s; vuelve a crecer con los dias. Habria que buscar en otro lado." % mat
            return False, "Aca no encontrás eso. Lo que hay: %s." % (", ".join(sorted(disp)) or "nada util")
        h.accion, h.detalle, h.hasta = "juntando", mat, self.t + TIEMPO_JUNTAR_MIN
        h.camino = []
        if self.rng_materiales.random() > disp[mat]:
            return True, "Buscaste %s un rato pero no encontraste." % mat
        lo, hi = self.cant_rec.get(mat, (1, 2))
        n = self.rng_materiales.randint(lo, hi)
        if self.modulo("atributos") and self.atributo(h, "fuerza") > 0.5:   # brazos fuertes rinden mas
            n += int(self.rng_materiales.random() < (self.atributo(h, "fuerza") - 0.5) * 1.2)
        n = min(n, max(1, int(self.restante(h.x, h.y, mat))))
        self._gastar_recurso(h.x, h.y, mat, n)
        self._ganar_item(h, mat, n)
        primera = mat not in h.recursos
        if primera:
            h.recursos.add(mat)
            self._recuerdo(h, "En este lugar se consigue %s (cerca de (%d, %d))." % (mat, int(h.x), int(h.y)), 0.5, "semantica")
        return True, "Juntaste %d de %s." % (n, mat)

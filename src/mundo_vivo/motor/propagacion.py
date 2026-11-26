"""
Colonias: lo que se propaga por el mapa sin caminar. Hongos, musgos, plagas, microbios.

No son fauna y forzar `Fauna` para esto sería un error: un hongo no se mueve, no caza, no tiene hambre.
Crece en las celdas que le gustan, se expande a las vecinas y muere donde no aguanta. Es un autómata
celular, igual molde que `motor/fuego.py`, pero con los umbrales en los datos:

    {"type":"colonia","id":"moho_de_pantano","nombre":"moho",
     "biomas":["pantano","selva"], "color":"#7a8f4a",
     "crece":{"por_dia":0.08,"humedad_min":0.6,"temperatura_C":[4,40]},
     "muere":{"temperatura_C":[-99,0]},
     "cosecha":{"material":"hongo_visionario","cantidad":[1,3]},
     "al_pisar":{"riesgo_enfermar":0.04}}

Lo que se cosecha de una colonia entra como depósito, igual que lo que siembra un meteorito: así un hongo
puede llevar un material a un lugar donde ese material no existía.

RENDIMIENTO: se avanza por MUESTREO, no barriendo el mapa. En 2048×2048 barrer cada tick es inviable; se
tocan unas pocas celdas por día del mundo y la mancha crece igual, de a poco, sin que nadie note el salto.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

MUESTRAS_POR_DIA = 220          # celdas candidatas que se miran por día del mundo y por colonia
MAX_CELDAS = 4000               # tope por colonia, para que no se coma el mapa ni la memoria


class PropagacionMixin:
    # ------------------------------------------------------------- datos
    def _compilar_colonias(self) -> None:
        self.colonias_def: Dict[str, dict] = dict(self.registro.de_tipo("colonia"))
        self.colonias: Dict[str, set] = getattr(self, "colonias", {})     # id -> {(x, y)}
        self._acum_col = 0.0

    def colonia_en(self, x: float, y: float) -> Optional[str]:
        c = (int(x), int(y))
        for cid, celdas in self.colonias.items():
            if c in celdas:
                return cid
        return None

    # -------------------------------------------------------------- paso
    def _paso_colonias(self, paso: float) -> None:
        if not self.colonias_def or not self.modulo("colonias"):
            return
        self._acum_col += paso
        if self._acum_col < 1440.0:            # una vez por día del mundo
            return
        dias, self._acum_col = self._acum_col / 1440.0, 0.0
        for cid, d in self.colonias_def.items():
            self._paso_colonia(cid, d, dias)

    def _paso_colonia(self, cid: str, d: dict, dias: float) -> None:
        celdas = self.colonias.setdefault(cid, set())
        if not celdas:
            self._sembrar_colonia(cid, d)
            return
        crece = d.get("crece") or {}
        muere = d.get("muere") or {}
        por_dia = float(crece.get("por_dia", 0.05)) * dias
        # morir donde ya no aguanta
        for c in list(celdas):
            if not self._colonia_aguanta(c, muere, invertir=True):
                celdas.discard(c)
        # crecer hacia las vecinas, por muestreo
        if len(celdas) >= MAX_CELDAS:
            return
        base = list(celdas)
        n = min(int(MUESTRAS_POR_DIA * dias), max(8, len(base) * 2))
        for _ in range(n):
            if self.rng_propagacion.random() >= por_dia:
                continue
            cx, cy = base[self.rng_propagacion.randrange(len(base))]
            nx, ny = cx + self.rng_propagacion.randint(-1, 1), cy + self.rng_propagacion.randint(-1, 1)
            if (nx, ny) in celdas or not self.terreno.dentro(nx, ny):
                continue
            if self._colonia_puede(cid, d, nx, ny):
                celdas.add((nx, ny))
                if len(celdas) >= MAX_CELDAS:
                    return

    def _sembrar_colonia(self, cid: str, d: dict) -> None:
        """La primera manchita, en un lugar que le guste."""
        for _ in range(40):
            x = self.rng_propagacion.randrange(self.terreno.ancho)
            y = self.rng_propagacion.randrange(self.terreno.alto)
            if self._colonia_puede(cid, d, x, y):
                self.colonias.setdefault(cid, set()).add((x, y))
                self._evento("colonia", "Apareció %s en la zona." % d.get("nombre", cid),
                             x=x + 0.5, y=y + 0.5, importancia=2, origen="sistema", datos={"colonia": cid})
                return

    def _colonia_puede(self, cid: str, d: dict, x: int, y: int) -> bool:
        from . import biomas as B
        t = self.terreno
        if not t.dentro(x, y) or t.agua[y, x]:
            return False
        claves = {v[0]: k for k, v in B.BIOMAS.items()}
        permitidos = {claves[b] for b in (d.get("biomas") or []) if b in claves}
        if permitidos and int(t.bioma[y, x]) not in permitidos:
            return False
        return self._colonia_aguanta((x, y), d.get("crece") or {})

    def _colonia_aguanta(self, c, cond: dict, invertir: bool = False) -> bool:
        """¿Las condiciones de esa celda le sirven? Con `invertir`, se comprueba la condición de MUERTE."""
        x, y = c
        if not self.terreno.dentro(x, y):
            return False
        temp = self.temp_en(x + 0.5, y + 0.5)
        hum = float(self.terreno.humedad[y, x]) / 255.0
        rango = cond.get("temperatura_C")
        if rango is not None:
            dentro = float(rango[0]) <= temp < float(rango[1])
            if invertir and dentro:
                return False            # está en el rango que la mata
            if not invertir and not dentro:
                return False
        if not invertir and cond.get("humedad_min") is not None and hum < float(cond["humedad_min"]):
            return False
        return True

    # ----------------------------------------------------------- cosecha
    def cosechar_colonia(self, h) -> Optional[tuple]:
        """Si está parado sobre una colonia que da algo, devuelve (material, cantidad)."""
        cid = self.colonia_en(h.x, h.y)
        if cid is None:
            return None
        cos = (self.colonias_def.get(cid) or {}).get("cosecha")
        if not cos:
            return None
        lo, hi = (cos.get("cantidad") or [1, 1])[:2]
        return cos["material"], self.rng_propagacion.randint(int(lo), int(hi))

    # --------------------------------------------------------- publicar
    def publico_colonias(self) -> list:
        """Para el visor: [[id, [x, y], ...]]. Se manda recortado, que puede ser grande."""
        return [[cid, sorted(c)[:MAX_CELDAS]] for cid, c in self.colonias.items() if c]

    def exportar_colonias(self) -> dict:
        return {cid: sorted(list(c)) for cid, c in self.colonias.items()}

    def importar_colonias(self, d: dict) -> None:
        self.colonias = {cid: {(int(x), int(y)) for x, y in celdas} for cid, celdas in (d or {}).items()}

"""Minerales que el mundo inventa: materiales que no están en ningún JSON de contenido.

Es la regla 6 de `CLAUDE.md` llevada hasta el final. En el resto del motor el contenido no está en el
código pero sí lo escribió alguien; acá ni el motor ni el autor saben qué hay abajo: cada mundo sortea
unos pocos minerales con su propia semilla, y de las propiedades que les tocaron salen invenciones que
nadie anticipó. Si a uno le sale denso y duro, cumple `golpea` y entra en las recetas de pico; si
conduce, sirve para el cable; si no sirve para nada, es una piedra rara y también está bien.

Tres decisiones que lo hacen barato:

1. **Las recetas NO se generan.** El catálogo sigue siendo fijo. Lo que lo hace funcionar es que la
   receta de fundición mira una ETIQUETA (`#mena_desconocida`) y no un id, pide el calor del mineral que
   se esté usando (`requiere: {calor_C: "@mena"}`) y devuelve el metal que ese mineral declara
   (`resultado: {desde_mena: true}`). Tres campos de datos, ningún `if` de contenido.
2. **El espacio de lo posible es dato** (`datos_base/generacion/minerales_desconocidos.json`): rangos de
   densidad y dureza, probabilidades de conducir o de ser magnético, sílabas para el nombre. Cambiar lo
   que puede existir es editar un JSON.
3. **Determinismo.** El generador aleatorio del mundo es sagrado y no se gasta acá: RNG propio sembrado
   con la semilla y la dimensión, igual que `sembrar_estructuras_naturales`. El mismo mundo tiene siempre
   los mismos minerales. Y la lista se guarda con el mundo, así que cambiar el JSON del espacio no le
   cambia la geología a una partida que ya empezó.

El nombre nunca delata una propiedad (regla 8): «piedra cerúlea», «veta lechosa». Que sea mejor que el
acero no se tiene que poder leer en el nombre, igual que `piedra_rojiza` no dice «hierro».
"""
from __future__ import annotations

import random
from typing import Dict, List

ETIQUETA_MENA = "mena_desconocida"
PRIMO = 1181783497276652981        # para que la semilla de los minerales no choque con las otras


class MineralesMixin:
    # ------------------------------------------------------------------ generación
    def _espacio_minerales(self) -> dict:
        return self.registro.uno("generacion_minerales", "minerales_desconocidos") or {}

    def generar_minerales_desconocidos(self) -> List[dict]:
        """Los minerales de ESTE mundo, sorteados de la semilla. Función pura: el mismo mundo da siempre
        la misma lista, y llamarla dos veces no cambia nada ni gasta el RNG del mundo."""
        esp = self._espacio_minerales()
        if not esp:
            return []
        rng = random.Random(self.semilla * PRIMO + self.dimension * 7919 + 101)
        lo, hi = esp.get("cantidad", [2, 6])
        cuantos = rng.randint(int(lo), int(hi))
        rangos, probs = esp.get("rangos", {}), esp.get("probabilidades", {})
        mrangos = esp.get("metal_rangos", {})
        usados: set = set()
        out: List[dict] = []
        for n in range(cuantos):
            nombre_mena = self._nombre_sorteado(rng, esp.get("nombres", {}), usados)
            nombre_metal = self._nombre_sorteado(rng, esp.get("metal", {}), usados)
            mid = "mineral_%d_%d" % (self.semilla % 100000, n)
            metal_id = "metal_%d_%d" % (self.semilla % 100000, n)
            metal = {
                "type": "material", "id": metal_id, "nombre": nombre_metal,
                "densidad_kg_m3": self._num(rng, mrangos.get("densidad_kg_m3", [2000, 12000]), 0),
                "dureza_mohs": self._num(rng, mrangos.get("dureza_mohs", [1.5, 8.0]), 1),
                "conductividad_W_mK": self._num(rng, mrangos.get("conductividad_W_mK", [0.5, 400.0]), 1),
                "punto_fusion_C": self._num(rng, mrangos.get("punto_fusion_C", [400, 1600]), 0),
                "inflamable": False, "_desconocido": True,
            }
            for campo, p in sorted(probs.items()):
                metal[campo] = rng.random() < float(p)
            mena = {
                "type": "material", "id": mid, "nombre": nombre_mena, "mena": metal_id,
                "densidad_kg_m3": self._num(rng, rangos.get("densidad_kg_m3", [1500, 9000]), 0),
                "dureza_mohs": self._num(rng, rangos.get("dureza_mohs", [1.0, 9.0]), 1),
                "conductividad_W_mK": self._num(rng, rangos.get("conductividad_W_mK", [0.2, 120.0]), 1),
                "punto_fusion_C": self._num(rng, rangos.get("punto_fusion_C", [300, 1500]), 0),
                "inflamable": False, "conduce_electricidad": False, "_desconocido": True,
                "recoleccion": {
                    "biomas": list(esp.get("biomas") or ["caverna"]),
                    "prob": self._num(rng, rangos.get("prob", [0.05, 0.3]), 2),
                    "cantidad": [1, 1],
                    "capacidad_zona": int(self._num(rng, rangos.get("capacidad_zona", [1, 5]), 0)),
                    "requiere": {"propiedad": esp.get("requiere_propiedad", "golpea")},
                },
            }
            for campo, p in sorted(probs.items()):
                if campo in ("magnetico", "aglomerante"):      # lo que se puede ver en la piedra misma
                    mena[campo] = rng.random() < float(p)
            out.append({"mena": mena, "metal": metal})
        return out

    @staticmethod
    def _num(rng, rango, decimales: int):
        lo, hi = float(rango[0]), float(rango[1])
        v = rng.uniform(lo, hi)
        return round(v, decimales) if decimales else int(round(v))

    @staticmethod
    def _nombre_sorteado(rng, cfg: dict, usados: set) -> str:
        """Un nombre que no se repite y que no cuenta nada de lo que el mineral hace."""
        inicio = cfg.get("silabas_inicio") or ["ca", "ve", "ri"]
        fin = cfg.get("silabas_fin") or ["lita", "rina"]
        adjetivos = cfg.get("adjetivos") or ["rara"]
        formas = cfg.get("formas") or ["piedra %(adj)s"]
        for _ in range(40):
            inventado = rng.choice(inicio) + rng.choice(fin)
            nombre = rng.choice(formas) % {"adj": rng.choice(adjetivos), "inventado": inventado}
            if nombre not in usados:
                usados.add(nombre)
                return nombre
        return inventado

    # ------------------------------------------------------------------ inyección
    def inyectar_minerales(self, pares: List[dict]) -> None:
        """Mete los minerales sorteados en el registro de ESTE mundo y en las tablas planas del bucle.

        Se hace una vez, al armar la `Simulacion` (o al cargarla de la base): el bucle de 20 Hz no toca
        el registro. Es el mismo contrato que `_compilar_materiales`, sólo que una parte del contenido no
        viene de un archivo.
        """
        # Reemplaza, no suma: al cargar un mundo se inyecta lo GUARDADO encima de lo que ya se había
        # sorteado al armar la `Simulacion`. Sin esta purga quedaban menas fantasma en la etiqueta y en
        # las tablas de recolección (minerales de otra geología, juntables y sin dueño).
        for par in getattr(self, "minerales_mundo", []):
            for d in (par["mena"], par["metal"]):
                self.recoleccion.pop(d["id"], None)
                self.prob_rec.pop(d["id"], None)
                self.cant_rec.pop(d["id"], None)
                self.capacidad.pop(d["id"], None)
                self.herramienta_rec.pop(d["id"], None)
                self.reglas.materiales.pop(d["id"], None)
        self.etiquetas[ETIQUETA_MENA] = set()
        self.minerales_mundo = list(pares or [])
        if not self.minerales_mundo:
            return
        mats: Dict[str, dict] = {}
        for par in self.minerales_mundo:
            for d in (par["mena"], par["metal"]):
                mats[d["id"]] = dict(d, _archivo="generado")
        self.registro.agregar("material", mats)
        self.reglas.materiales.update(mats)
        for mid, d in sorted(mats.items()):
            r = d.get("recoleccion") or {}
            if not r:
                continue
            from . import biomas as _B
            por_clave = {v[0]: k for k, v in _B.BIOMAS.items()}
            self.recoleccion[mid] = tuple(por_clave[b] if isinstance(b, str) else b for b in r["biomas"])
            self.prob_rec[mid] = float(r.get("prob", 0.1))
            self.cant_rec[mid] = tuple(r.get("cantidad", (1, 1)))
            self.capacidad[mid] = int(r.get("capacidad_zona", 2))
            prop = (r.get("requiere") or {}).get("propiedad")
            if prop:
                self.herramienta_rec[mid] = str(prop)
        # la etiqueta que usan las recetas de fundición: es de este mundo, no del catálogo
        self.etiquetas.setdefault(ETIQUETA_MENA, set()).update(p["mena"]["id"] for p in self.minerales_mundo)

    def metal_de(self, material: str) -> str:
        """El metal que da una mena, o la mena misma si no da nada. Lo lee `resultado: {desde_mena: true}`."""
        d = self.reglas.materiales.get(material) or {}
        return str(d.get("mena") or material)

    def minerales_desconocidos(self) -> List[str]:
        return sorted(p["mena"]["id"] for p in getattr(self, "minerales_mundo", []))

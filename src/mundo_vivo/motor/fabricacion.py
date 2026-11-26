"""Fabricación y recetas: transformar materiales del mundo en objetos usando recetas conocidas.

Nada de esto es automático: hay que saber la receta (`sabe(h, receta_id)`), tener los materiales y
dedicarle el tiempo que dice la receta (`tiempo_min`). Los datos están en datos_base/recetas.

También concentra el modelo de calor/energía: `calor_disponible`, `energía_disponible`, `_provisto_en`
y las curvas de caída. `requisitos_ok` es el único lugar donde se valida si una receta se puede hacer
acá y ahora (materiales, herramientas, calor).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .estructuras import MAX_REFUGIOS_POR_PERSONA, MIN_LENA

PROVISIONES = {
    "calor_C": ("hace falta fuego al lado.", "hace falta más calor del que da esto."),
    "energia_W": ("hace falta corriente al lado.", "hace falta más corriente de la que da esto."),
}


class FabricacionMixin:
    # ------------------------------------------------------- datos de recetas
    def _compilar_objetives(self) -> None:
        """Objetivos de respaldo: ids de recetas que el motor propone cuando nadie decide."""
        obj = self.registro.uno("objetivos", "respaldo") or {}
        self.objetivos: tuple = tuple(obj.get("recetas") or ())

    # ------------------------------------------------------------ consultas
    def _receta_de(self, texto: str) -> Optional[dict]:
        t = str(texto or "").strip().lower()
        if not t:
            return None
        if t in self.recetas:
            return self.recetas[t]
        for r in self.recetas.values():
            if r["nombre"].lower() == t:
                return r
        for r in self.recetas.values():
            if t in r["nombre"].lower():
                return r
        return None

    def receta_de_invento(self, nombre: str, materiales: List[str], propiedad: str, descripcion: str = "") -> str:
        """Un invento que no está en el catálogo igual tiene que PODERSE hacer: se le arma una receta
        de verdad y se suma al catálogo de este mundo."""
        from ..catalogos import TIEMPO_CATEGORIA
        base = "".join(ch if ch.isalnum() else "_" for ch in nombre.lower().strip())[:40].strip("_") or "invento"
        rid = base
        n = 2
        while rid in self.recetas:
            rid = "%s_%d" % (base, n)
            n += 1
        cat = {"corta": "herramienta", "perfora": "herramienta", "golpea": "herramienta", "ata": "herramienta",
               "abriga": "ropa", "protege": "ropa", "arde": "fuego", "enciende": "fuego", "cura": "salud",
               "contiene": "recipiente", "flota": "transporte"}.get(propiedad, "otros")
        self.recetas[rid] = {
            "type": "receta", "id": rid, "nombre": nombre, "ingredientes": list(materiales), "propiedad": propiedad,
            "categoria": cat, "descripcion": descripcion, "tiempo_min": TIEMPO_CATEGORIA.get(cat, 20),
            "resultado": {"item": rid, "cantidad": 1}, "herramienta": [], "requiere_fuego": False,
            "_archivo": "inventado", "_inventada": True}
        return rid

    def rearmar_recetas_inventadas(self) -> None:
        """Al cargar el mundo, el catálogo vuelve del JSON: devolverle las recetas que inventaron acá."""
        for c in self.conocimientos.values():
            rid = c.get("receta_id")
            if c.get("origen") == "inventada" and rid and rid not in self.recetas:
                self.recetas[rid] = {
                    "type": "receta", "id": rid, "nombre": c["nombre"], "ingredientes": list(c["materiales"]),
                    "propiedad": c["propiedad"], "categoria": "otros", "descripcion": c.get("descripcion", ""),
                    "tiempo_min": 20, "resultado": {"item": rid, "cantidad": 1}, "herramienta": [],
                    "requiere_fuego": False, "_archivo": "inventado", "_inventada": True}

    def recetas_con_propiedad(self, *props) -> List[str]:
        """Ids de receta por propiedad. Cacheado por propiedad: `disponibles()` lo consulta varias
        veces por llamada. El índice se rehace solo cuando aparece una receta inventada."""
        cache = getattr(self, "_idx_prop", None)
        if cache is None or self._idx_prop_n != len(self.recetas):
            cache = {}
            for i, r in self.recetas.items():
                cache.setdefault(r["propiedad"], []).append(i)
            self._idx_prop, self._idx_prop_n = cache, len(self.recetas)
        if len(props) == 1:
            return cache.get(props[0], [])
        return [i for p in props for i in cache.get(p, [])]

    def fuente_de_chispa(self, h) -> Optional[str]:
        for i in self.recetas_con_propiedad("enciende"):
            if self.tiene(h, i):
                return i
        return "antorcha_encendida" if self.tiene(h, "antorcha_encendida") else None

    # ------------------------------------------------------ requisitos y calor
    @staticmethod
    def _caida(d: float, nucleo: float, radio: float, curva: str) -> float:
        """Factor 0..1 del calor a distancia `d`. Pleno en el núcleo, nada pasado el radio."""
        if d <= nucleo:
            return 1.0
        if d >= radio or curva == "escalon":
            return 0.0
        f = (radio - d) / max(1e-9, radio - nucleo)
        return f * f if curva == "cuadratica" else f

    def _alcance(self, e: dict) -> Tuple[float, float, str]:
        """(núcleo, radio, curva) de una estructura, en CELDAS."""
        p = e.get("provee") or {}
        radio = self.celdas(float(e.get("radio_m", 6.0)), minimo=1.5)
        nucleo = self.celdas(float(p.get("nucleo_m", e.get("radio_m", 6.0))), minimo=1.0)
        return min(nucleo, radio), radio, str(p.get("caida", "escalon"))

    def _provisto_en(self, x: float, y: float, campo: str, trabajo: bool = True) -> float:
        """Cuánto de `campo` (grados, vatios) hay en un punto. Es el MÁXIMO, no la suma."""
        mejor = 0.0
        for key in ("fogata", "incendio"):
            est = self.estructuras.get(key) or {}
            provee = float((est.get("provee") or {}).get(campo, 0))
            if not provee:
                continue
            nuc, rad, curva = self._alcance(est)
            if key == "fogata":
                for f in self.fogatas:
                    d = math.hypot(f["x"] - x, f["y"] - y)
                    k = 1.0 if d <= nuc else (0.0 if trabajo else self._caida(d, nuc, rad, curva))
                    if k:
                        mejor = max(mejor, provee * k)
            else:
                if self.fuego_cerca_de(x, y, rad):
                    mejor = max(mejor, provee)
        for r in self.refugios:
            e = self.estructuras.get(r.get("tipo")) or {}
            provee = float((e.get("provee") or {}).get(campo, 0))
            if not provee:
                continue
            nuc, rad, curva = self._alcance(e)
            d = math.hypot(r["x"] - x, r["y"] - y)
            k = 1.0 if d <= nuc else (0.0 if trabajo else self._caida(d, nuc, rad, curva))
            if k:
                mejor = max(mejor, provee * k)
        return mejor

    def _grados_en(self, x: float, y: float, trabajo: bool = True) -> float:
        return self._provisto_en(x, y, "calor_C", trabajo)

    def calor_disponible(self, h) -> float:
        """Los grados que tiene al alcance de la MANO: con esto se decide si una receta se puede hacer."""
        return self._provisto_en(h.x, h.y, "calor_C", trabajo=True)

    def energia_disponible(self, h) -> float:
        """Los vatios que tiene al alcance de la mano. Calcado del calor, con otra magnitud."""
        return self._provisto_en(h.x, h.y, "energia_W", trabajo=True)

    def atractor_fogata(self, h) -> float:
        """0..1: cuánto tira la fogata de la aldea a quedarse. Solo en horas de poca luz."""
        from . import reloj
        if not self.fogatas or not reloj.es_noche(self.t):
            return 0.0
        tope = float(self.estructuras.get("fogata", {}).get("provee", {}).get("calor_C", 600)) or 600.0
        return min(1.0, self._grados_en(h.x, h.y, trabajo=False) / tope)

    def requisitos_ok(self, h, r: dict, usar: Optional[List[str]] = None) -> Tuple[bool, str]:
        """¿Puede hacer esta receta acá y ahora? Un solo lugar para todos los requisitos."""
        req = r.get("requiere") or ({"calor_C": 400} if r.get("requiere_fuego") else {})
        for campo, (falta, poco) in PROVISIONES.items():
            pedido = req.get(campo, 0)
            if isinstance(pedido, str) and pedido.startswith("@"):
                if usar is None:
                    usar, _ = self._ingredientes_ok(h, r)
                pide = max([0.0] + [float((self.reglas.materiales.get(m) or {}).get("punto_fusion_C", 0) or 0)
                                    for m in (usar or [])])
            else:
                pide = float(pedido)
            if not pide:
                continue
            hay = self._provisto_en(h.x, h.y, campo, trabajo=True)
            if hay < pide:
                return False, ("Para hacer %s " % r["nombre"]) + (falta if hay <= 0 else poco)
        return True, ""

    # ------------------------------------------------------------ fabricar
    def puede_fabricar(self, h, r: dict) -> bool:
        if not self.sabe(h, r["id"]):
            return False
        usar, _ = self._ingredientes_ok(h, r)
        return usar is not None and self.requisitos_ok(h, r)[0]

    def _ingredientes_ok(self, h, r: dict) -> Tuple[Optional[List[str]], str]:
        """(lista de ítems concretos a consumir, motivo si falta algo)."""
        usar, pedido = [], dict()
        for ing in r["ingredientes"]:
            if ing.startswith("#"):
                opts = sorted(self.etiquetas.get(ing[1:], ()), key=lambda m: -h.inventario.get(m, 0))
                elegido = next((m for m in opts if h.inventario.get(m, 0) - pedido.get(m, 0) > 0), None)
                if elegido is None:
                    return None, "te falta algo de «%s»" % ing[1:]
            else:
                elegido = ing
                if h.inventario.get(ing, 0) - pedido.get(ing, 0) <= 0:
                    return None, "te falta %s" % ing
            pedido[elegido] = pedido.get(elegido, 0) + 1
            usar.append(elegido)
        for herr in r.get("herramienta", []):
            if not self.tiene(h, herr):
                return None, "te falta la herramienta %s" % herr
        return usar, ""

    def _accion_fabricar(self, h, it: dict) -> Tuple[bool, str]:
        r = self._receta_de(it.get("objeto") or it.get("receta"))
        if r is None:
            return False, "No sabés qué es eso."
        if not self.sabe(h, r["id"]):
            return False, "Todavía no descubriste cómo hacer eso."
        usar, falta = self._ingredientes_ok(h, r)
        if usar is None:
            return False, "No podés hacer %s: %s." % (r["nombre"], falta)
        ok_req, por_que = self.requisitos_ok(h, r, usar)
        if not ok_req:
            return False, por_que
        est = r.get("estructura")
        if est and float(est.get("abrigo", 0.0)) > 0 and \
                sum(1 for x in self.refugios if x["dueno"] == h.id and float(x.get("abrigo", 0.0)) > 0) >= MAX_REFUGIOS_POR_PERSONA:
            return False, "Ya tenés suficientes refugios."
        if est and not self.terreno.caminable(int(h.x), int(h.y)):
            return False, "Acá no se puede construir."
        for m in usar:
            h.inventario[m] -= 1
            if h.inventario[m] <= 0:
                h.inventario.pop(m, None); h.inv_t.pop(m, None)
        h.camino = []
        h.accion, h.detalle, h.hasta = ("construyendo" if est else "fabricando"), r["nombre"], self.t + self.tiempo_de_receta(h, r)
        self.practicar(h, r["id"])
        if est:
            nuevo = {"rid": self._nuevo_refugio(), "x": round(h.x, 2), "y": round(h.y, 2), "dueno": h.id,
                     "tipo": r["id"], "nombre": r["nombre"], "abrigo": float(est.get("abrigo", 0.0)),
                     "abrigo0": float(est.get("abrigo", 0.0)),
                     "visto": int(self.t), "t": int(self.t + r["tiempo_min"])}
            self.refugios.append(nuevo)
            techo = float(est.get("abrigo", 0.0)) > 0
            if techo:
                h.hogar = (round(h.x, 1), round(h.y, 1))
                h.hogar_rid = nuevo["rid"]
            h.marcar_lugar("refugio", h.x, h.y, r["nombre"], self.t, radio=self.celdas(300.0))
            self._evento("construccion", "%s construyó %s." % (h.nombre, r["nombre"]), h, importancia=4, datos={"receta": r["id"]})
            self._recuerdo(h, ("Construiste %s. Es tu refugio: cerca de (%d, %d)." if techo else
                               "Construiste %s: quedó cerca de (%d, %d).") % (r["nombre"], int(h.x), int(h.y)), 0.85)
            self.sentir(h, "alegria", 0.3)
            if techo:
                self._hito("vivienda", h, "primera vivienda. %s construyó %s." % (h.nombre, r["nombre"]))
                if any(o["dueno"] != h.id and float(o.get("abrigo", 0.0)) > 0
                       and math.hypot(o["x"] - h.x, o["y"] - h.y) <= self.r_aldea for o in self.refugios):
                    self._hito("aldea", h, "primera aldea: varias viviendas de familias distintas, una junto a la otra.")
            provee = self.estructuras.get(r["id"], {}).get("provee") or {}
            grados = float(provee.get("calor_C", 0))
            if grados > 0:
                self._hito("calor_%d" % int(grados), h,
                           "el calor de %d grados: %s levantó %s." % (int(grados), h.nombre, r["nombre"]))
            if float(provee.get("energia_W", 0)) > 0:
                self._hito("luz", h, "la corriente eléctrica. %s levantó %s." % (h.nombre, r["nombre"]))
            return True, "Construiste %s (te llevó un buen rato)." % r["nombre"]
        res = r["resultado"]
        n = int(res.get("cantidad", 1))
        if res.get("desde_mena"):
            res = dict(res, item=next((self.metal_de(m) for m in usar if self.metal_de(m) != m), usar[0]))
        self._ganar_item(h, res["item"], n)
        h.inv_t[res["item"]] = 0.0
        primera = res["item"] not in h.fabricados
        h.fabricados.add(res["item"])
        self._evento("fabricacion", "%s hizo %s." % (h.nombre, r["nombre"]), h, importancia=3 if primera else 1,
                     datos={"receta": r["id"], "item": res["item"], "n": n})
        self._recuerdo(h, "Hiciste %s con tus manos." % r["nombre"], 0.6 if primera else 0.3)
        if primera:
            self.experiencia(h, "fabricar")
        item = res["item"]
        if item in self.armas:
            self._hito("armas", h, "herramientas y armas. %s hizo %s." % (h.nombre, r["nombre"]))
        if r["propiedad"] == "funde":
            self._hito("metalurgia", h, "el primer metal. %s fundió %s." % (h.nombre, r["nombre"]))
        if r["propiedad"] == "abriga":
            self._hito("ropa", h, "primera ropa. %s hizo %s." % (h.nombre, r["nombre"]))
        if item == "tela":
            self._hito("telar", h, "el tejido: %s hizo la primera tela." % h.nombre)
        if item == "ceramica":
            self._hito("ceramica", h, "la cerámica: %s coció arcilla." % h.nombre)
        if r["propiedad"] == "contiene":
            self._hito("recipientes", h, "recipientes para guardar y cargar. %s hizo %s." % (h.nombre, r["nombre"]))
        return True, "Hiciste %s." % r["nombre"]

    # ------------------------------------------------------------- plan
    def plan_tecnologico(self, h):
        """Una acción concreta para avanzar en la tecnología (o None). Es el 'sentido común' del respaldo."""
        frio = self.modulo("frio") and self.severidad_frio(h) > 0.2
        if h.salud < 50 and self.curativo(h):
            return {"tipo": "usar", "objeto": self.curativo(h)}
        if (frio or self.t % 1440 > 1080 or self.t % 1440 < 300) and not self.fogata_cerca(h, self.r_fogata):
            if self.fuente_de_chispa(h) and self.lena_que_lleva(h) >= MIN_LENA:
                return {"tipo": "encender"}
            if self.fuente_de_chispa(h) and "palo" in self.disponibles(h):
                return {"tipo": "juntar", "material": "palo"}
            if not self.fuente_de_chispa(h) and (self.fogata_cerca(h, self.r_mano) or self.fuego_cerca(h, self.r_mano)) and (self.tiene(h, "palo") or any(self.tiene(h, a) for a in self.antorchas)):
                return {"tipo": "tomar_fuego"}
        for rid in self.objetivos:
            r = self.recetas.get(rid)
            if r is None:
                continue
            res = r["resultado"]["item"]
            if r.get("estructura"):
                if any(x["dueno"] == h.id for x in self.refugios):
                    continue
            elif self.tiene(h, res):
                continue
            if not self.sabe(h, rid):
                if self.t - h.ultima_idea_t > 300 and self.modulo("conocimientos"):
                    ing = []
                    for m in r["ingredientes"]:
                        if m.startswith("#"):
                            m = sorted(self.etiquetas.get(m[1:], ("palo",)))[0]
                        ing.append(m)
                    return {"tipo": "inventar", "receta": {"nombre": r["nombre"], "materiales": ing, "propiedad": r["propiedad"],
                                                            "descripcion": r.get("descripcion", "")}}
                return None
            usar, falta = self._ingredientes_ok(h, r)
            if usar is not None:
                if not self.requisitos_ok(h, r)[0]:
                    continue
                return {"tipo": "fabricar", "objeto": rid}
            disp = self.disponibles(h)
            for ing in r["ingredientes"]:
                if not ing.startswith("#") and h.inventario.get(ing, 0) <= 0:
                    if ing in disp:
                        return {"tipo": "juntar", "material": ing}
                    break
        return None

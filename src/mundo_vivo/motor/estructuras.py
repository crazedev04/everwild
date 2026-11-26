"""Estructuras del mundo: refugios, fogatas, aldeas, calor que proveen y su deterioro.

Una estructura es algo construido: una choza, un horno, una fragua, una dinamica, una boca de caverna natural.
Las fogatas y los refugios viven en listas propias; las aldeas se derivan de la proximidad entre refugios.
El calor cae con la distancia segun el dato de cada estructura: `provee.nucleo_m`, `provee.radio_m` y `provee.caida`.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import biomas as B
from .materiales import MIN_DIA

DURA_ANTORCHA_MIN = 0.2 * 1440.0
MIN_LENA = 2
FOGATA_MIN_POR_LENA = 150.0
# En metros: lo que abriga una fogata alrededor, y adentro de la choza y su alero.
METROS_CALOR_FOGATA = 20.0
METROS_CALOR_REFUGIO = 12.0
MAX_REFUGIOS_POR_PERSONA = 3
METROS_ALDEA = 150.0
# Deterioro: una casa por la que no pasa nadie se cae sola. 20 dias de gracia y luego medio ano hasta ruinas.
DIAS_SIN_USO = 20.0
DESGASTE_POR_DIA = 0.004
MIN_ABRIGO = 0.05


class EstructurasMixin:
    # ------------------------------------------------------- datos de estructuras
    def _compilar_estructures(self) -> None:
        """Estructuras que proveen calor/energia: de aqui sale la progresion (fogata 600 C, horno 1000, fragua 1500)."""
        self.estructuras: Dict[str, dict] = dict(self.registro.de_tipo("estructura"))

    # ------------------------------------------------------------ consultas
    def fogata_cerca(self, h, radio: float) -> Optional[dict]:
        for f in self.fogatas:
            if math.hypot(f["x"] - h.x, f["y"] - h.y) <= radio:
                return f
        return None

    def refugio_cerca(self, h, radio: Optional[float] = None) -> Optional[dict]:
        """El mejor techo al alcance. «Mejor» es por abrigo EFECTIVO (choza mas fogata de al lado), y a igual
        abrigo gana el propio: la cama de uno antes que la del vecino."""
        radio = self.r_refugio if radio is None else radio
        mejor, mejor_a = None, 0.0
        for r in self.refugios:
            # un pozo o una boca de caverna estan en la misma lista pero NO son un techo: no abrigan a nadie
            if float(r.get("abrigo", 0.0)) <= 0:
                continue
            if math.hypot(r["x"] - h.x, r["y"] - h.y) > radio:
                continue
            a = self.abrigo_efectivo(r)
            propio = r.get("dueno") == h.id
            if mejor is None or a > mejor_a or (a == mejor_a and propio and mejor.get("dueno") != h.id):
                mejor, mejor_a = r, a
        return mejor

    def abrigo_efectivo(self, r: dict) -> float:
        """El abrigo de una casa contando el fuego que tiene alrededor."""
        a = float(r.get("abrigo", 0.0))
        if a <= 0:
            return 0.0
        tope = float(self.estructuras.get("fogata", {}).get("provee", {}).get("calor_C", 600)) or 600.0
        k = min(1.0, self._grados_en(r["x"], r["y"], trabajo=False) / tope)
        return min(0.95, a + (1.0 - a) * 0.5 * k)

    def calor_de_estructuras(self, h) -> float:
        """Factor (0..1] que multiplica la severidad del frio: junto a una fogata o dentro de un refugio se pasa menos frio."""
        k = 1.0
        tope = float(self.estructuras.get("fogata", {}).get("provee", {}).get("calor_C", 600)) or 600.0
        f = min(1.0, self._grados_en(h.x, h.y, trabajo=False) / tope)
        if f > 0:
            k *= 1.0 - 0.75 * f
        r = self.refugio_cerca(h)
        if r:
            k *= 1.0 - self.abrigo_efectivo(r)
        return k

    def sembrar_estructuras_naturales(self) -> int:
        """Lo que no construyo nadie y esta desde siempre: bocas de caverna de la montaña."""
        hechas = set(getattr(self, "naturales_sembradas", []))
        ids_bioma = {d["id"]: int(d["id_numerico"]) for d in self.registro.de_tipo("bioma").values()}
        puestas = 0
        for eid, e in self.estructuras.items():
            nat = e.get("natural")
            if not nat or eid in hechas:
                continue
            hechas.add(eid)
            quiere = [ids_bioma[b] for b in (nat.get("biomas") or []) if b in ids_bioma]
            if not quiere:
                continue
            ok = np.isin(self.terreno.bioma, quiere) & np.isfinite(self.terreno.costo)
            ys, xs = np.nonzero(ok)
            if not len(xs):
                continue
            km2 = len(xs) * (self.tam_celda_m ** 2) / 1e6
            cuantas = int(round(km2 * float(nat.get("cada_km2", 0.5))))
            cuantas = max(int(nat.get("minimo", 1)), min(int(nat.get("maximo", 40)), cuantas))
            rng = random.Random(self.semilla * 2246822519 + self.dimension * 97 + sum(eid.encode()))
            orden = list(range(len(xs)))
            rng.shuffle(orden)
            sep = self.celdas(float(nat.get("separacion_m", 1500.0)))
            elegidas: List[tuple] = []
            for i in orden:
                if len(elegidas) >= cuantas:
                    break
                px, py = float(xs[i]) + 0.5, float(ys[i]) + 0.5
                if all(math.hypot(px - ax, py - ay) >= sep for ax, ay in elegidas):
                    elegidas.append((px, py))
            for px, py in elegidas:
                self.refugios.append({"rid": self._nuevo_refugio(), "x": round(px, 2), "y": round(py, 2),
                                      "dueno": None, "tipo": eid, "nombre": e.get("nombre", eid),
                                      "abrigo": float((e.get("estructura") or {}).get("abrigo", 0.0)),
                                      "t": int(self.t), "natural": True})
            puestas += len(elegidas)
        self.naturales_sembradas = sorted(hechas)
        return puestas

    def _accion_atravesar(self, h, it: dict) -> Tuple[bool, str]:
        """Cruzar a otra dimension por una estructura que lleve alli (`provee.lleva_a` en los datos)."""
        if self.mundo is None:
            return False, "Acá no hay a donde cruzar."
        p = self.mundo.pasaje_cerca(self, h)
        if p is None:
            return False, "No tenés nada al lado que lleve a ninguna parte."
        destino = self.mundo.dimension_para(p["a"])
        if destino is None:
            return False, "Mirás el paso y no se ve nada del otro lado todavía."
        nombre = self.estructuras.get(p["tipo"], {}).get("nombre", p["tipo"])
        r = p["r"]
        llegada = self.mundo.otra_punta(self, r, destino)
        if llegada is None or not self.mundo.mover(h, destino, llegada[0], llegada[1]):
            return False, "No se puede pasar."
        self._evento("paso_dimension", "%s cruzo por %s." % (h.nombre, nombre), h, importancia=4,
                     datos={"a": destino.ident, "desde": self.ident})
        destino._recuerdo(h, "Cruzaste por %s y apareciste del otro lado, en (%d, %d)."
                          % (nombre, int(h.x), int(h.y)), 0.9)
        h.marcar_lugar("refugio", h.x, h.y, "la salida por donde viniste", destino.t,
                       radio=destino.celdas(300.0))
        return True, "Cruzaste por %s." % nombre

    def curativo(self, h) -> Optional[str]:
        for i in self.recetas_con_propiedad("cura"):
            if self.tiene(h, i):
                return i
        return None

    def _accion_usar(self, h, it: dict) -> Tuple[bool, str]:
        item = str(it.get("objeto") or it.get("item") or "").strip().lower()
        r = self._receta_de(item)
        i = r["id"] if r else item
        if r is None or r["propiedad"] != "cura" or not self.tiene(h, r["resultado"]["item"]):
            return False, "No tenés nada asi para curarte."
        it_id = r["resultado"]["item"]
        h.inventario[it_id] -= 1
        if h.inventario[it_id] <= 0:
            h.inventario.pop(it_id, None); h.inv_t.pop(it_id, None)
        h.salud = min(100.0, h.salud + 25.0)
        h.accion, h.detalle, h.hasta = "esperando", "se cura", self.t + 15.0
        self._recuerdo(h, "Te curaste con %s." % r["nombre"], 0.6)
        return True, "Usaste %s y te sentis mejor." % r["nombre"]

    def bono_arma(self, h) -> Tuple[float, float]:
        bono, alcance = 0.0, 0.0
        for item, (b, al) in self.armas.items():
            if self.tiene(h, item) and b > bono:
                bono, alcance = b, al
        if self.modulo("atributos"):
            bono += 0.25 * (self.atributo(h, "fuerza") - 0.3)
        return max(0.0, bono), alcance

    def proteccion_de(self, h) -> float:
        """0..0.5 menos dano por ataques si lleva algo que proteja."""
        n = sum(1 for i in self.recetas_con_propiedad("protege") if self.tiene(h, i))
        return min(0.5, 0.25 * n)

    def abrigo_objetos(self, h) -> float:
        n = sum(1 for i in self.recetas_con_propiedad("abriga") if self.tiene(h, i))
        return min(0.6, 0.22 * n)

    # -------------------------------------------------------------- aldeas
    def aldeas(self) -> List[dict]:
        """Grupos de refugios pegados (<= METROS_ALDEA entre vecinos). Una aldea necesita CASAS."""
        sin_ver = [r for r in self.refugios if r.get("rid") is not None and float(r.get("abrigo", 0.0)) > 0]
        out = []
        while sin_ver:
            grupo = [sin_ver.pop()]
            i = 0
            while i < len(grupo):
                a = grupo[i]
                i += 1
                for r in list(sin_ver):
                    if math.hypot(r["x"] - a["x"], r["y"] - a["y"]) <= self.r_aldea:
                        sin_ver.remove(r)
                        grupo.append(r)
            if len(grupo) < 2:
                continue
            cx = sum(r["x"] for r in grupo) / len(grupo)
            cy = sum(r["y"] for r in grupo) / len(grupo)
            radio = max(6.0, max(math.hypot(r["x"] - cx, r["y"] - cy) for r in grupo) + 4.0)
            viejos = sorted(n for n in (self.aldea_num.get(r["rid"]) for r in grupo) if n is not None)
            num = viejos[0] if viejos else self._nuevo_numero_aldea()
            for r in grupo:
                self.aldea_num[r["rid"]] = num
            duenos = [d for d in dict.fromkeys(r["dueno"] for r in grupo)]
            vecinos = [h for h in self.habitantes.values()
                       if h.vivo and (h.id in duenos or math.hypot(h.x - cx, h.y - cy) <= radio)]
            out.append({"num": num, "nombre": "Aldea %d" % num, "x": round(cx, 1), "y": round(cy, 1),
                        "r": round(radio, 1), "casas": len(grupo), "familias": len(duenos),
                        "gente": [{"id": h.id, "nombre": h.nombre} for h in sorted(vecinos, key=lambda h: h.id)]})
        out.sort(key=lambda a: a["num"])
        return out

    def _nuevo_refugio(self) -> int:
        self.prox_refugio = max(1, int(getattr(self, "prox_refugio", 1)))
        n, self.prox_refugio = self.prox_refugio, self.prox_refugio + 1
        return n

    def _nuevo_numero_aldea(self) -> int:
        self.prox_aldea = max(1, int(getattr(self, "prox_aldea", 1)))
        n, self.prox_aldea = self.prox_aldea, self.prox_aldea + 1
        return n

    # ------------------------------------------------------------ fuego y tick
    def _accion_tomar_fuego(self, h, it: dict) -> Tuple[bool, str]:
        if not (self.fogata_cerca(h, self.r_mano) or self.fuego_cerca(h, self.r_mano)):
            return False, "No hay fuego al alcance para prender una rama."
        base = next((a for a in self.antorchas if self.tiene(h, a)), None) or ("palo" if self.tiene(h, "palo") else None)
        if base is None:
            return False, "Necesitás un palo o una antorcha para llevarte el fuego."
        h.inventario[base] -= 1
        if h.inventario[base] <= 0:
            h.inventario.pop(base, None); h.inv_t.pop(base, None)
        self._ganar_item(h, "antorcha_encendida", 1)
        h.inv_t["antorcha_encendida"] = 0.0 if base != "palo" else 0.5 * DURA_ANTORCHA_MIN
        h.accion, h.detalle, h.hasta = "esperando", "prende una rama", self.t + 3.0
        self._evento("fuego_llevado", "%s prendio una rama en el fuego y se la llevo." % h.nombre, h, importancia=3)
        self._recuerdo(h, "Prendiste una rama en el fuego: se puede llevar la llama a otro lado.", 0.8, "semantica")
        return True, "Prendiste una antorcha."

    def _accion_encender(self, h, it: dict) -> Tuple[bool, str]:
        f0 = self.fogata_cerca(h, self.r_mano)
        fuente = self.fuente_de_chispa(h)
        if fuente is None:
            return False, "No tenés con que sacar fuego (chispa, frotar palos o una antorcha prendida)."
        if self.lena_que_lleva(h) < MIN_LENA:
            return False, "Te falta leña: juntá palos, paja o carbon."
        if self.nieve_en(h.x, h.y) > 0.6 and fuente != "antorcha_encendida":
            return False, "Con tanta nieve no prende."
        gastar = MIN_LENA
        for m in self.lena:
            while gastar > 0 and h.inventario.get(m, 0) > 0:
                h.inventario[m] -= 1
                gastar -= 1
            if h.inventario.get(m, 0) <= 0:
                h.inventario.pop(m, None); h.inv_t.pop(m, None)
            if gastar == 0:
                break
        mas = MIN_LENA * FOGATA_MIN_POR_LENA
        h.accion, h.detalle, h.hasta = "esperando", "prende el fuego", self.t + 10.0
        h.camino = []
        if f0:
            f0["hasta"] = max(f0["hasta"], self.t) + mas
            return True, "Le agregaste leña a la fogata."
        self.fogatas.append({"x": round(h.x, 2), "y": round(h.y, 2), "hasta": self.t + mas, "dueno": h.id})
        self._evento("fogata", "%s encendio una fogata." % h.nombre, h, importancia=3, datos={"con": fuente})
        self._hito("fuego", h, "dominio del fuego. %s encendio la primera fogata." % h.nombre)
        self._recuerdo(h, "Encendiste una fogata (con %s). Da calor, luz y sirve para cocinar." % fuente.replace("_", " "), 0.8, "semantica")
        h.marcar_lugar("refugio", h.x, h.y, "fogata", self.t, radio=self.celdas(300.0))
        self.sentir(h, "alegria", 0.3)
        self.experiencia(h, "hacer_fuego")
        return True, "Encendiste una fogata."

    def _paso_tecnologia(self, paso: float) -> None:
        self._acum_tec = getattr(self, "_acum_tec", 0.0) + paso
        if self._acum_tec < 10.0:
            return
        dt, self._acum_tec = self._acum_tec, 0.0
        if self.fogatas:
            vivas = []
            for f in self.fogatas:
                if self.nieve_en(f["x"], f["y"]) > 0.7:
                    f["hasta"] -= dt * 2.0
                if f["hasta"] > self.t:
                    vivas.append(f)
            self.fogatas = vivas
        self._paso_ruinas()

    def _paso_ruinas(self) -> None:
        """Lo que nadie usa se cae. Una vez por dia simulado, no por tick."""
        ultimo = getattr(self, "_ruinas_t", None)
        if ultimo is not None and self.t - ultimo < MIN_DIA:
            return
        dias = 1.0 if ultimo is None else (self.t - ultimo) / MIN_DIA
        self._ruinas_t = self.t
        if ultimo is None:
            return
        vivos = [h for h in self.habitantes.values() if h.vivo]
        for r in self.refugios:
            if r.get("natural") or float(r.get("abrigo", 0.0)) <= 0:
                continue
            if any(math.hypot(h.x - r["x"], h.y - r["y"]) <= self.r_refugio for h in vivos):
                r["visto"] = int(self.t)
                continue
            if self.t - float(r.get("visto", self.t)) < DIAS_SIN_USO * MIN_DIA:
                continue
            r["abrigo"] = round(max(0.0, float(r["abrigo"]) - DESGASTE_POR_DIA * dias), 3)
            if r["abrigo"] <= MIN_ABRIGO:
                r["abrigo"], r["ruina"] = 0.0, True
                for h in self.habitantes.values():
                    if h.hogar_rid == r.get("rid"):
                        h.hogar, h.hogar_rid = None, None
                self._evento("ruina", "%s quedo en ruinas: no paso nadie en mucho tiempo." % r.get("nombre", "Un refugio"),
                             x=r["x"], y=r["y"], importancia=2, origen="sistema", datos={"rid": r.get("rid")})

    def publico_estructuras(self) -> dict:
        return {"fogatas": [[f["x"], f["y"], round(max(0.0, min(1.0, (f["hasta"] - self.t) / (MIN_LENA * FOGATA_MIN_POR_LENA))), 2)]
                            for f in self.fogatas],
                "refugios": [[r["x"], r["y"], r["tipo"]] for r in self.refugios],
                "ruinas": [[r["x"], r["y"], r["tipo"]] for r in self.refugios if r.get("ruina")],
                "senderos": self.publico_senderos(),
                "aldeas": self.aldeas()}

    # ----------------------------------------------------------- hitos
    def _hito(self, clave: str, h, texto: str) -> None:
        """Un avance de la sociedad (primera vez en este mundo). Sale como alerta en el visor."""
        if clave in self.hitos:
            return
        self.hitos.add(clave)
        self._evento("hito", "🌅 Nueva etapa: %s" % texto, h, importancia=5, datos={"hito": clave})

    # --------------------------------------------------------- persistencia
    def exportar_estructuras(self) -> dict:
        return {"fogatas": self.fogatas, "refugios": self.refugios, "hitos": sorted(self.hitos),
                "minerales": getattr(self, "minerales_mundo", []),
                "naturales_sembradas": sorted(getattr(self, "naturales_sembradas", [])),
                "prox_refugio": self.prox_refugio, "prox_aldea": self.prox_aldea,
                "aldea_num": {str(k): v for k, v in self.aldea_num.items()},
                "agotamiento": {k: [round(u, 2), round(tt, 1)] for k, (u, tt) in self.agotamiento.items()}}

    def importar_estructuras(self, d: dict) -> None:
        if d.get("minerales"):
            self.inyectar_minerales(d["minerales"])
        self.fogatas = [f for f in d.get("fogatas", []) if f.get("hasta", 0) > self.t]
        self.refugios = list(d.get("refugios", []))[-400:]
        self.hitos = set(d.get("hitos", []))
        self.naturales_sembradas = list(d.get("naturales_sembradas", []))
        self.prox_refugio = int(d.get("prox_refugio", 1))
        self.prox_aldea = int(d.get("prox_aldea", 1))
        self.aldea_num = {int(k): int(v) for k, v in (d.get("aldea_num") or {}).items()}
        for r in self.refugios:
            if r.get("rid") is None:
                r["rid"] = self.prox_refugio
                self.prox_refugio += 1
            r.setdefault("abrigo0", float(r.get("abrigo", 0.0)))
            r.setdefault("visto", int(r.get("t", self.t)))
        self.agotamiento = {k: (float(v[0]), float(v[1])) for k, v in (d.get("agotamiento") or {}).items()}

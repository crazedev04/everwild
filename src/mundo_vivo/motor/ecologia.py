"""
Ecología desde el punto de vista de las personas: ver animales, cazar, ser atacado, montar, y las emociones.

Igual que el resto del motor: el cerebro PROPONE ("cazar ciervo") y acá se VALIDA (distancia, herramientas conocidas,
tirada de suerte) y se cuentan las consecuencias reales. Las emociones son un estado interno simple (4 canales, 0..1) que
sube con lo que le pasa a cada uno, baja solo con el tiempo (vida media de 2 horas del mundo) y se ve en el prompt como una
palabra; el temperamento heredado modula cuánto le afecta cada cosa.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

CANALES = ("miedo", "tristeza", "alegria", "enojo")
VIDA_MEDIA_EMOCION_MIN = 120.0
ALCANCE_CUERPO = 1.6
ALCANCE_LANZA = 2.6
ALCANCE_ARCO = 6.0
METROS_VISTA_FAUNA = 1000.0        # en metros: a 50 m/celda da las 20 celdas de siempre
RADIO_PELIGRO = 12.0
# La tabla de armas era un duplicado parcial de la de tecnologia.py: ahora hay una sola, `self.armas`.


def _genero(h, masc: str, fem: str) -> str:
    return fem if h.sexo == "F" else masc


class EcologiaMixin:
    # ------------------------------------------------------------------ personalidad plástica
    def _tabla_experiencias(self) -> dict:
        """Qué experiencia mueve qué rasgo, y cuánto. Ahora es un dato (datos_base/cultura/experiencias.json):
        es la perilla para ajustar que no se vuelvan cautelosos demasiado rápido, sin tocar cuatro archivos."""
        if not hasattr(self, "_exp"):
            self._exp = dict(self.registro.de_tipo("experiencia"))
        return self._exp

    def experiencia(self, h, id_: str) -> None:
        """Aplica una experiencia con nombre. Reemplaza a los ~15 `moldear(...)` con deltas literales."""
        d = self._tabla_experiencias().get(id_)
        if d is None:
            return
        motivo = d.get("motivo", id_)
        for rasgo, delta in (d.get("mueve") or {}).items():
            self.moldear(h, rasgo, float(delta), motivo)

    def moldear(self, h, rasgo: str, delta: float, motivo: str = "") -> None:
        """La experiencia corre un poco el carácter de la persona (nunca más de ±0.25 de lo heredado). Cuando un rasgo cruza un
        umbral (0.3 / 0.7) que cambia cómo se la describe, queda anotado como suceso."""
        g = h.genoma
        if g is None or rasgo not in g.rasgos or not h.vivo or not self.modulo("personalidad"):
            return
        base = g.rasgos[rasgo]
        antes = h.rasgo(rasgo)
        nuevo = max(0.0, min(1.0, max(base - 0.25, min(base + 0.25, antes + delta))))
        if nuevo == antes:
            return
        if not h.rasgos_vivos:
            h.rasgos_vivos = dict(g.rasgos)
        h.rasgos_vivos[rasgo] = nuevo
        banda = lambda v: 2 if v >= 0.7 else 0 if v <= 0.3 else 1
        if banda(nuevo) != banda(antes):
            txt = {"audacia": ("más temeroso", "más audaz"), "cautela": ("más impulsivo", "más cauteloso"), "sociabilidad": ("más solitario", "más sociable"),
                   "curiosidad": ("más conformista", "más curioso"), "agresividad": ("más pacífico", "más combativo"),
                   "empatia": ("menos empático", "más empático"), "resiliencia": ("más frágil", "más resistente")}[rasgo][1 if nuevo > antes else 0]
            self._evento("personalidad", "%s se volvió %s%s." % (h.nombre, txt, (" (" + motivo + ")") if motivo else ""), h, importancia=3,
                         causa=motivo or "experiencia")
            self._recuerdo(h, "Sentís que cambiaste: ahora sos %s." % txt, 0.8, "semantica")

    # ------------------------------------------------------------------ emociones
    def sentir(self, h, canal: str, cantidad: float) -> None:
        if canal not in h.emo or not self.modulo("emociones"):
            return
        k = 1.0
        g = h.genoma
        if g is not None:
            r = {k: h.rasgo(k) for k in g.rasgos}
            if canal in ("miedo", "tristeza"):
                k = 1.4 - 0.8 * r.get("resiliencia", 0.5)
                if canal == "miedo":
                    k *= 1.2 - 0.5 * r.get("audacia", 0.5)
                else:
                    k *= 0.7 + 0.6 * r.get("empatia", 0.5)
            elif canal == "enojo":
                k = 0.6 + 0.8 * r.get("agresividad", 0.5)
            elif canal == "alegria":
                k = 0.7 + 0.6 * r.get("sociabilidad", 0.5)
        h.emo[canal] = min(1.0, h.emo[canal] + cantidad * k)

    def _decaer_emociones(self, h, paso: float) -> None:
        f = 0.5 ** (paso / VIDA_MEDIA_EMOCION_MIN)
        for c in CANALES:
            h.emo[c] *= f
            if h.emo[c] < 0.01:
                h.emo[c] = 0.0

    def etiqueta_emocion(self, h) -> str:
        c = max(CANALES, key=lambda k: h.emo[k])
        v = h.emo[c]
        if v < 0.25:
            return "tranquilo" if h.sexo == "M" else "tranquila"
        palabra = {"miedo": _genero(h, "asustado", "asustada"), "tristeza": "triste",
                   "alegria": _genero(h, "contento", "contenta"), "enojo": _genero(h, "enojado", "enojada")}[c]
        return ("muy " if v >= 0.6 else "") + palabra

    # ------------------------------------------------------------------ percepción
    def modulo_fauna(self) -> bool:
        return self.modulo("fauna") and self.fauna is not None

    def ver_animales(self, h) -> List[dict]:
        if not self.modulo_fauna():
            return []
        grupos: Dict[str, dict] = {}
        for d, a in self.fauna.cerca(h.x, h.y, self.celdas(METROS_VISTA_FAUNA)):
            if a.jinete is not None:
                continue
            g = grupos.setdefault(a.sp, {"sp": a.sp, "n": 0, "dist": d})
            g["n"] += 1
        out = []
        for sid, g in grupos.items():
            e = self.fauna.esp[sid]
            g.update(nombre=e["nombre"], peligro=e["peligro"], agresivo=e["agresivo"], montable=e["montable"],
                     comestible=bool(e["drops"].get("carne")), medio=e["medio"], veneno=e["veneno"])
            out.append(g)
        out.sort(key=lambda g: g["dist"])
        return out

    def peligro_cercano(self, h):
        """El animal peligroso más cercano que de verdad puede atacar (para el reflejo de huida)."""
        if not self.modulo_fauna():
            return None
        for d, a in self.fauna.cerca(h.x, h.y, RADIO_PELIGRO):
            e = self.fauna.esp[a.sp]
            if a.jinete is not None or e["peligro"] < 4 or e["medio"] == "agua" and not self.terreno.agua_adyacente(int(h.x), int(h.y)):
                continue
            if (e["agresivo"] == "siempre" and a.hambre > 0.4) or a.provocado_hasta > self.t:
                return a
        return None

    def sabe(self, h, receta_id: str) -> bool:
        """¿Esta persona sabe hacer esta receta?

        Se pregunta muchísimo (medido: 455.924 veces en 50 días simulados de un mundo de 2048²), así
        que la vuelta al revés —de receta a conocimientos que la enseñan— está indexada en lugar de
        recorrer todo lo que la persona conoce. El índice se rearma solo cuando aparece un
        conocimiento nuevo, que es lo único que lo invalida (`vida.py` los agrega al inventar).
        """
        if getattr(self, "_idx_recetas_n", -1) != len(self.conocimientos):
            idx: dict = {}
            for cid, c in self.conocimientos.items():
                rid = (c or {}).get("receta_id")
                if rid:
                    idx.setdefault(rid, set()).add(cid)
            self._idx_recetas = idx
            self._idx_recetas_n = len(self.conocimientos)
        cids = self._idx_recetas.get(receta_id)
        return bool(cids) and not cids.isdisjoint(h.conoce)

    # --------------------------------------------------------------------- ataques
    def _avisar_mutaciones(self) -> None:
        """Una variante nueva es un hecho del mundo: queda como suceso y lo ve quien esté cerca."""
        for m in self.fauna.mutaciones:
            de = self.fauna.esp.get(m["de"], {}).get("nombre", m["de"])
            a = self.fauna.esp.get(m["a"], {}).get("nombre", m["a"])
            self._evento("mutacion", "Nació un %s distinto de los demás: un %s." % (de, a),
                         x=m["x"] + 0.5, y=m["y"] + 0.5, importancia=4, origen="sistema",
                         datos={"de": m["de"], "a": m["a"]})
            for h in self.habitantes.values():
                if h.vivo and math.hypot(h.x - m["x"], h.y - m["y"]) <= self.r_vista:
                    self._recuerdo(h, "Viste un %s que no era como los otros." % a, 0.7, "semantica")
        self.fauna.mutaciones.clear()

    def _ataques_animales(self) -> None:
        f = self.fauna
        for h in self.habitantes.values():
            if not h.vivo:
                continue
            for a in list(f._vecinos(h.x, h.y, 2.5)):
                if a.id not in f.animales or a.jinete is not None or a.ataque_hasta > self.t:
                    continue
                dd = math.hypot(a.x - h.x, a.y - h.y)
                e = f.esp[a.sp]
                if dd > 1.8 or e["peligro"] <= 0:
                    continue
                if e["medio"] == "agua" and not self.terreno.agua_adyacente(int(h.x), int(h.y)):
                    continue
                ataca = False
                if e["agresivo"] == "siempre" and a.hambre > 0.5:
                    ataca = self.rng.random() < 0.6
                elif a.provocado_hasta > self.t:
                    ataca = self.rng.random() < 0.6
                elif e["veneno"] and dd < 1.0:
                    ataca = self.rng.random() < 0.08          # lo pisó sin querer
                if not ataca:
                    continue
                a.ataque_hasta = self.t + 60.0
                dmg = e["peligro"] * self.rng.uniform(1.0, 2.5) * (1.3 if e["veneno"] else 1.0) * (1.0 - self.proteccion_de(h))
                self._dano(h, dmg, "ataque de %s" % e["nombre"], "ataque_animal",
                           "%s fue atacad%s por un animal: %s." % (h.nombre, "a" if h.sexo == "F" else "o", e["nombre"]),
                           mio="Te atacó un animal (%s) cerca de (%d, %d). Mejor evitar ese lugar." % (e["nombre"], int(h.x), int(h.y)))
                h.ataque_t = self.t
                h.marcar_lugar("peligro", h.x, h.y, e["nombre"], self.t, radio=self.celdas(400.0))
                self.experiencia(h, "ataque_de_animal")
                self.sentir(h, "miedo", 0.7)
                self.sentir(h, "enojo", 0.3)
                if not h.vivo:
                    break

    # ----------------------------------------------------------------- acciones
    def _acercarse_a(self, h, a, motivo: str) -> Tuple[bool, str]:
        c = self.terreno.caminable_cerca(int(a.x), int(a.y), 2)
        camino = self.terreno.buscar_camino((int(h.x), int(h.y)), c) if c else None
        e = self.fauna.esp[a.sp]
        if not camino:
            h.accion, h.detalle, h.hasta = "esperando", "no puede llegar", self.t + 5
            return False, "No hay manera de llegar hasta %s." % e["nombre"]
        h.camino, h.accion, h.detalle, h.al_llegar = camino, "caminando", motivo, None
        return True, "Te acercaste a %s." % e["nombre"]

    def _elegir_animal(self, h, nombre: str):
        nombre = str(nombre or "").strip().lower()
        sid = next((k for k, v in self.fauna.esp.items() if k == nombre or v["nombre"].lower() == nombre), None)
        if sid is None:
            sid = next((k for k, v in self.fauna.esp.items() if nombre and nombre in v["nombre"].lower()), None)
        if sid is None:
            return None, "No conocés ningún animal llamado «%s»." % nombre
        cand = self.fauna.cerca(h.x, h.y, self.celdas(METROS_VISTA_FAUNA), sid)
        cand = [(d, a) for d, a in cand if a.jinete is None]
        if not cand:
            return None, "No ves ningún animal de esa clase cerca."
        return cand[0], ""

    def _accion_cazar(self, h, it: dict) -> Tuple[bool, str]:
        if not self.modulo_fauna():
            return False, "No hay animales para cazar."
        par, err = self._elegir_animal(h, it.get("animal"))
        if par is None:
            return False, err
        dist, a = par
        e = self.fauna.esp[a.sp]
        if e["medio"] == "agua" and not self.terreno.agua_adyacente(int(h.x), int(h.y)):
            return False, "%s está en el agua y vos no tenés cómo alcanzarlo." % e["nombre"].capitalize()
        bono, alcance = 0.0, ALCANCE_CUERPO
        b_arma, al_arma = self.bono_arma(h)               # solo cuenta lo que lleva encima, no lo que sabe hacer
        if b_arma > 0:
            bono, alcance = b_arma, max(alcance, al_arma)
        if e["medio"] == "aire":
            alcance = max(alcance, 3.0) if alcance >= 5.0 else 0.0
            if alcance == 0.0:
                return False, "%s vuela: sin un arco no lo alcanzás." % e["nombre"].capitalize()
        if dist > alcance:
            return self._acercarse_a(h, a, "persigue un%s %s" % ("a" if e["nombre"][-1] == "a" else "", e["nombre"]))
        # a tiro: se intenta
        a.provocado_hasta = self.t + 120.0
        h.camino, h.accion, h.detalle, h.hasta = [], "cazando", e["nombre"], self.t + 10.0
        chance = 0.25 + bono - 0.05 * min(6.0, e["velocidad"]) - 0.015 * min(10.0, e["peligro"]) + 0.1
        chance = max(0.05, min(0.9, chance))
        if self.rng.random() < chance:
            self.fauna.matar(a, "cazado por personas")
            botin = {}
            drops = dict(e["drops"])
            if drops.get("carne"):                       # lo que además se aprovecha de un animal grande
                pesado = e["peso_kg"] >= 40
                for extra, p in (("grasa", 0.6 if pesado else 0.2), ("tendon", 0.4 if pesado else 0.1), ("piel", 0.5 if pesado else 0.15)):
                    if self.rng.random() < p:
                        drops[extra] = 1
                if a.sp in ("ciervo", "cabra", "vaca") and self.rng.random() < 0.5:
                    drops["cuerno"] = 1
                if a.sp in ("elefante", "jabali") and self.rng.random() < 0.6:
                    drops["colmillo"] = 1
            for item, n in drops.items():
                cant = max(1, int(round(n * self.rng.uniform(0.7, 1.3))))
                self._ganar_item(h, item, cant)
                botin[item] = cant
            txt = ", ".join("%d de %s" % (v, k) for k, v in botin.items()) or "nada que aprovechar"
            self._evento("caza", "%s cazó %s (%s)." % (h.nombre, e["nombre"], txt), h, importancia=3,
                         datos={"animal": a.sp, "botin": botin})
            self._recuerdo(h, "Cazaste %s y conseguiste %s." % (e["nombre"], txt), 0.7)
            h.marcar_lugar("comida", h.x, h.y, e["nombre"], self.t, radio=self.celdas(500.0))
            self.experiencia(h, "cazar_con_exito")
            self.sentir(h, "alegria", 0.35)
            h.novedad_t = self.t
            return True, "Cazaste %s: conseguiste %s." % (e["nombre"], txt)
        a.huye_hasta = self.t + 40.0
        texto = "Se te escapó %s." % e["nombre"]
        if (e["agresivo"] != "no" or e["peligro"] >= 4) and self.rng.random() < 0.5:
            dmg = e["peligro"] * self.rng.uniform(1.2, 3.0)
            self._dano(h, dmg, "ataque de %s" % e["nombre"], "ataque_animal",
                       "%s fue herid%s por %s al intentar cazarlo." % (h.nombre, "a" if h.sexo == "F" else "o", e["nombre"]),
                       mio="Intentaste cazar (%s) y te lastimó." % e["nombre"])
            h.ataque_t = self.t
            h.marcar_lugar("peligro", h.x, h.y, e["nombre"], self.t, radio=self.celdas(400.0))
            self.experiencia(h, "cazar_y_salir_herido")
            self.sentir(h, "miedo", 0.6)
            texto += " Te hirió."
        return False, texto

    def _accion_montar(self, h, it: dict) -> Tuple[bool, str]:
        if not self.modulo_fauna():
            return False, "No hay animales."
        if h.montura is not None:
            return False, "Ya estás montando."
        if not self.sabe(h, "rienda"):
            return False, "No sabés cómo guiar a un animal: te falta inventar algo para controlarlo (una rienda de cuero)."
        par, err = self._elegir_animal(h, it.get("animal"))
        if par is None:
            return False, err
        dist, a = par
        e = self.fauna.esp[a.sp]
        if not e["montable"]:
            return False, "%s no se deja montar." % e["nombre"].capitalize()
        if dist > 1.8:
            return self._acercarse_a(h, a, "se acerca a un %s" % e["nombre"])
        h.camino, h.hasta, h.accion, h.detalle = [], self.t + 5.0, "esperando", "intenta montar"
        if self.rng.random() < 0.6:
            h.montura, a.jinete = a.id, h.id
            self._evento("monta", "%s montó un %s." % (h.nombre, e["nombre"]), h, importancia=3, datos={"animal": a.sp})
            self._recuerdo(h, "Montaste un %s: ahora vas mucho más rápido." % e["nombre"], 0.8)
            self.sentir(h, "alegria", 0.3)
            h.novedad_t = self.t
            return True, "Montaste un %s." % e["nombre"]
        a.huye_hasta = self.t + 30.0
        return False, "El %s se asustó y se alejó." % e["nombre"]

    def _accion_desmontar(self, h, it: dict) -> Tuple[bool, str]:
        if h.montura is None:
            return False, "No estás montando nada."
        a = self.fauna.animales.get(h.montura)
        if a is not None:
            a.jinete = None
        h.montura = None
        return True, "Te bajaste del animal."

    def _sincronizar_montura(self, h) -> None:
        if h.montura is None:
            return
        a = self.fauna.animales.get(h.montura) if self.fauna else None
        if a is None or not h.vivo:
            if a is not None:
                a.jinete = None
            h.montura = None
            return
        a.x, a.y = h.x, h.y

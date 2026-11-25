"""
Cerebro híbrido de los habitantes.

Capas (de más barata a más cara):
  1. Reflejos: huir del fuego, tomar agua, dormir. Los umbrales salen de la red heredada (genoma), no de un número fijo.
  2. Modelo de lenguaje (Ollama): decide intenciones cuando el cuerpo no apremia (hablar, acercarse a alguien, proponer
     una familia, enseñar, inventar...). Corre en un hilo aparte; mientras piensa, el habitante espera un momento.
  3. Si el modelo no está disponible o falla, el habitante sigue con reglas simples y el mundo no se detiene.
El cerebro solo PROPONE; el motor valida (distancias, edades, consentimiento, materiales reales).
"""
from __future__ import annotations

import json
import math
import time
from typing import Dict, Optional, Tuple

import numpy as np

from ..motor import biomas as B
from ..motor import reloj
from ..motor.alimentacion import HAMBRE_DESPIERTA
from ..motor.simulacion import SED_DESPIERTA, Cerebro, CerebroDemo, HabitanteSim, Simulacion
from ..persistencia import social
from ..persistencia.memoria import MemoriaPrivada, tokens
from . import conocimiento
from .genoma import describir_temperamento, impulsos
from .habito import FRASE, Habito, actividad_de, recompensa, senales
from .ollama import ClienteOllama, extraer_json

ACCIONES = ["explorar", "ir_al_agua", "beber", "dormir", "esperar", "ir_hacia", "hablar",
            "proponer_hijo", "responder_propuesta", "ensenar", "inventar", "cazar", "montar", "desmontar", "atravesar", "buscar", "cocinar", "curar", "juntar", "fabricar", "encender", "tomar_fuego", "usar", "comer"]
ESQUEMA = {
    "type": "object",
    "properties": {
        "pensamiento": {"type": "string"},
        "accion": {"type": "string", "enum": ACCIONES},
        "a": {"type": "string"},
        "mensaje": {"type": "string"},
        "intencion": {"type": "string", "enum": ["contar", "advertir", "preguntar", "mentir"]},
        "impresion": {"type": "number"},
        "acepta": {"type": "boolean"},
        "animal": {"type": "string"},
        "conocimiento": {"type": "string"}, "material": {"type": "string"}, "objeto": {"type": "string"},
        "receta": {"type": "object", "properties": {
            "nombre": {"type": "string"}, "materiales": {"type": "array", "items": {"type": "string"}},
            "propiedad": {"type": "string"}, "descripcion": {"type": "string"}}},
    },
    "required": ["pensamiento", "accion"],

}
SISTEMA = (
    "Sos {nombre}, una persona que vive en un mundo natural junto a muy pocas personas más. No hay nadie fuera de "
    "las que ves. Decidís vos qué hacer, según tu forma de ser, tu cuerpo, tus recuerdos y tus vínculos. "
    "Hablás en español, natural y breve. Respondé SIEMPRE con un único objeto JSON válido y nada más. "
    "Este mundo es naturaleza salvaje: no existen casas, ciudades, comercios, café, dinero, relojes ni aparatos; no tenés "
    "ningún recuerdo de otro lugar. Solo existen lo que ves (terreno, agua, fuego, plantas) y las personas que conocés. "
    "Lo primero es sobrevivir: agua, descanso, no quemarte y no pasar frío. Hablá con otra persona solo si tenés algo concreto que decirle "
    "(dónde viste agua, un peligro, algo que te pasó, algo que aprendiste) y no repitas lo que ya dijiste; si no hay "
    "nada que decir, explorá o descansá. Nunca menciones cosas que no existen acá."
)


def _rumbo(dx: float, dy: float) -> str:
    if abs(dy) > 2 * abs(dx):
        return "norte" if dy < 0 else "sur"
    if abs(dx) > 2 * abs(dy):
        return "oeste" if dx < 0 else "este"
    return ("noroeste" if dx < 0 else "noreste") if dy < 0 else ("suroeste" if dx < 0 else "sureste")


def _procedencia(m: dict) -> str:
    """Cómo se le presenta un recuerdo a la persona según de dónde salió. Un rumor no es un hecho: si se le
    muestran iguales, el modelo los trata iguales y empieza a dar por cierto lo que le contaron."""
    origen = (m.get("origen") or "vivido")
    certeza = float(m.get("certeza", 1.0) or 1.0)
    if origen == "oido":
        if certeza >= 0.8:
            return " (te lo contaron y le creés)"
        if certeza >= 0.5:
            return " (te lo contaron)"
        return " (te lo contaron, pero no sabés si es cierto)"
    if origen == "inferido":
        return " (lo pensaste vos, no lo viste)"
    return ""


DIAS_REFLEXION = 3            # cada cuántos días del mundo se reflexiona (antes: 1; se comía la mitad de las consultas)
MIN_MEMORIAS_REFLEXION = 3    # y solo si pasó algo nuevo desde la última reflexión
ESQUEMA_REFLEXION = {
    "type": "object",
    "properties": {"aprendizajes": {"type": "array", "items": {"type": "string"}},
                   "intenciones": {"type": "array", "items": {"type": "string"}}},
    "required": ["aprendizajes", "intenciones"],
}


class CerebroHibrido(Cerebro):
    nombre = "híbrido (reflejos con genoma + modelo de lenguaje)"

    def __init__(self, con, cliente: Optional[ClienteOllama] = None):
        self.con = con
        self.cliente = cliente or ClienteOllama()
        self._demo = CerebroDemo()
        self.pend: Dict[int, tuple] = {}      # habitante_id -> (futuro, firma, prompt_usuario)
        self.pend_ref: Dict[int, tuple] = {}  # reflexiones en curso: habitante_id -> (futuro, prompt)
        self.reflexiones = 0
        self.decisiones_llm = 0
        self.rechazos_llm = 0
        self.ultimo_pensamiento: Dict[int, str] = {}
        self.ancla: Dict[int, list] = {}              # id -> [x, y, t] desde cuándo está en la misma zona

    # ----------------------------------------------------------------- estado
    def pendientes(self) -> int:
        """Consultas al modelo en vuelo. Las reflexiones también cuentan: si no, mientras alguien reflexiona el
        mundo corre a velocidad plena y se le pasan días encima."""
        return (sum(1 for f, _, _ in self.pend.values() if not f.done())
                + sum(1 for f, _ in self.pend_ref.values() if not f.done()))

    def estado(self, sim: Simulacion) -> dict:
        on = sim.ajustes["modulos"].get("cerebro_llm", False)
        e = self.cliente.estado()
        return {"llm_activo": on, "llm_disponible": e["disponible"], "modelo": sim.ajustes["modelo"],
                "pensando": self.pendientes(), "latencia_s": e["latencia_s"], "ultimo_error": e["ultimo_error"],
                "decisiones_llm": self.decisiones_llm, "rechazos_llm": self.rechazos_llm,
                "semantica": sim.semantica.estado()}

    # ------------------------------------------------------------------ decidir
    def decidir(self, sim: Simulacion, h: HabitanteSim) -> dict:
        if h.snap is not None and sim.es_adulto(h):
            self._aprender(sim, h)
        acc = self._decidir(sim, h)
        if not (acc.get("tipo") == "esperar" and acc.get("motivo") == "pensando") and sim.es_adulto(h):
            self._foto(sim, h, acc)
        return acc

    # ------------------------------------------------------- hábito (red que aprende)
    def _hb(self, h: HabitanteSim) -> Habito:
        if h.habito is None:
            h.habito = Habito(genoma_pesos=h.genoma.pesos if h.genoma else None)
        return h.habito

    def _features(self, sim: Simulacion, h: HabitanteSim) -> list:
        cercanos = sim.percibir(h)["cercanos"]
        sol = 0.0
        if not cercanos and h.visto:
            sol = (sim.t - max(v[2] for v in h.visto.values())) / 1440.0
        presas = len([g for g in sim.ver_animales(h) if g["comestible"]]) if sim.modulo_fauna() else 0
        return senales(h, sim, bool(cercanos), sol, (sim.t - h.novedad_t) / 1440.0, sim.peligro_cercano(h) is not None, presas)

    def _foto(self, sim: Simulacion, h: HabitanteSim, acc: dict) -> None:
        act = actividad_de(acc)
        if act is None or not sim.modulo("habitos"):
            h.snap = None
            return
        h.snap = {"act": act, "x": self._features(sim, h), "t": sim.t, "salud": h.salud, "sed": h.sed, "novedad": h.novedad_t,
                  "conoce": len(h.conoce), "inv": sum(h.inventario.values()), "ok": True}

    def _aprender(self, sim: Simulacion, h: HabitanteSim) -> None:
        snap, h.snap = h.snap, None
        if snap is None or sim.t - snap["t"] < 5:
            return
        snap["ok"] = not (h.ultimo_resultado.startswith(("No ", "Esa persona", "Ya ", "Estás repitiendo")) if h.ultimo_resultado else False)
        self._hb(h).aprender(snap["x"], snap["act"], recompensa(h, sim, snap))

    # ------------------------------------------------------------ familia
    def ganas_de_familia(self, sim: Simulacion, h: HabitanteSim) -> float:
        """0..2: cuánto desea formar una familia. Crece con los días de adulto sin hijo ni embarazo (≈1 a los 20 días) y con la sociabilidad."""
        if not sim.es_adulto(h) or h.embarazo:
            return 0.0
        adulta_desde = h.nacimiento_min + 12 * 120 * 1440.0           # ADULTO_MIN: 12 años del mundo
        dias = (sim.t - max(adulta_desde, h.sin_concebir_hasta)) / 1440.0
        return max(0.0, min(2.0, dias / 20.0 * (0.6 + 0.8 * h.rasgo("sociabilidad"))))

    def _pareja_posible(self, sim: Simulacion, h: HabitanteSim):
        """Adultos del otro sexo, vivos, que no son familia directa y entre los que puede haber un embarazo."""
        out = []
        for o in sim.habitantes.values():
            if o.id == h.id or not o.vivo or o.sexo == h.sexo or not sim.es_adulto(o):
                continue
            if o.id in (h.madre_id, h.padre_id) or h.id in (o.madre_id, o.padre_id):
                continue                                          # padres e hijos
            if (h.madre_id and h.madre_id == o.madre_id) or (h.padre_id and h.padre_id == o.padre_id):
                continue                                          # hermanos y medio hermanos (por madre o por padre)
            mujer = h if h.sexo == "F" else o
            if mujer.embarazo or sim.t < mujer.sin_concebir_hasta:
                continue
            out.append(o)
        return out

    def _familia(self, sim: Simulacion, h: HabitanteSim, solo_urgente: bool = False) -> Optional[dict]:
        """Responder o hacer una propuesta cuando el deseo manda. Sin esto, nadie formaría una familia nunca."""
        if not sim.modulo("reproduccion") or not sim.es_adulto(h):
            return None
        p = h.propuesta
        if p and sim.t - p["t"] <= 360:
            o = sim.habitantes.get(p["de"])
            if o is not None and o.vivo and (not solo_urgente or sim.t - p["t"] > 90):
                return {"tipo": "responder_propuesta", "acepta": sim.rng.random() < 0.85}
        ganas = self.ganas_de_familia(sim, h)
        if ganas < (1.6 if solo_urgente else 1.0) or sim.t - getattr(h, "ultima_prop_t", -1e9) < 2 * 1440:
            return None
        cand = [o for o in self._pareja_posible(sim, h) if o.id in h.visto]      # hace falta haberse visto antes
        if not cand:
            return None
        cand.sort(key=lambda o: math.hypot(o.x - h.x, o.y - h.y))
        o = cand[0]
        d = math.hypot(o.x - h.x, o.y - h.y)
        if d <= 3.0:
            h.ultima_prop_t = sim.t
            return {"tipo": "proponer_hijo", "a": o.id}
        if d <= 28.0:
            return {"tipo": "ir_hacia", "a": o.id}
        if o.id in h.visto:
            return {"tipo": "buscar", "a": o.id}
        return None

    def _respaldo(self, sim: Simulacion, h: HabitanteSim) -> dict:
        """Cuando el modelo no responde: reglas simples, pero si ya aprendió algo de la experiencia, su hábito manda un poco."""
        base = self._demo.decidir(sim, h)
        if base.get("motivo") == "explora" and h.sed < 45:        # con sed no se hace otra cosa que buscar agua
            f = self._familia(sim, h)
            if f:
                return f
        if base.get("motivo") == "explora" and h.sed < 45:
            # Primero lo que la persona se propuso: Utility AI elige el objetivo y el encadenado arma el paso.
            o = sim.plan_de_objetivo(h)
            if o:
                return o
        if base.get("motivo") == "explora" and h.sed < 45 and sim.modulo("conocimientos"):
            t = sim.plan_tecnologico(h)
            if t:
                return t
        hb = h.habito
        if hb is None or hb.n < 30 or not sim.modulo("habitos") or base.get("motivo") != "explora":
            return base
        v = hb.valores(self._features(sim, h))
        mejor = max(v, key=v.get)
        if v[mejor] < 0.2:
            return base
        if mejor == "acercarse":
            aus = sim.ausentes(h)
            if aus:
                return {"tipo": "buscar", "a": aus[0][0].id}
        if mejor == "cazar" and sim.modulo_fauna():
            presas = [g for g in sim.ver_animales(h) if g["comestible"]]
            if presas:
                return {"tipo": "cazar", "animal": presas[0]["nombre"]}
        return base

    def _decidir(self, sim: Simulacion, h: HabitanteSim) -> dict:
        if not sim.es_adulto(h):
            return self._nino(sim, h)
        r = self._reflejos(sim, h)
        if r:
            return r
        aj = sim.ajustes
        if not aj["modulos"].get("cerebro_llm") or not self.cliente.disponible():
            self.pend.pop(h.id, None)
            return self._respaldo(sim, h)
        # LOD cognitivo: sólo los que están EN FOCO consultan al modelo. Los demás deciden igual, con
        # reflejos, hábitos y objetivos. Sin esto, con 25 personas el modelo no da abasto y el mundo se frena.
        nivel = sim.nivel_cognitivo(h)
        if nivel > 1:
            self.pend.pop(h.id, None)
            if nivel >= 3:
                return {"tipo": "esperar", "min": 60, "motivo": "lejos de todo"}
            return self._respaldo(sim, h)
        if aj["modulos"].get("memoria"):
            r = self._reflexion(sim, h)
            if r:
                return r
        firma = (len(h.mensajes), bool(h.propuesta), len(h.conoce))
        p = self.pend.get(h.id)
        if p is not None:
            fut, firma_ant, _ = p
            if time.time() - fut.t0 > aj["timeout_s"] + 10:       # se colgó: se descarta
                self.pend.pop(h.id, None)
                return self._respaldo(sim, h)
            if not fut.done():
                return {"tipo": "esperar", "min": 1, "motivo": "pensando"}
            if firma_ant != firma:                                  # cambió algo importante mientras pensaba
                self.pend.pop(h.id, None)
                p = None
        if p is None:
            self._lanzar(sim, h, firma)
            return {"tipo": "esperar", "min": 1, "motivo": "pensando"}
        fut, _, prompt = self.pend.pop(h.id)
        try:
            r = fut.result()
        except Exception:
            return self._respaldo(sim, h)
        return self._interpretar(sim, h, r, prompt)

    # ----------------------------------------------------------------- reflejos
    def _reflejos(self, sim: Simulacion, h: HabitanteSim) -> Optional[dict]:
        # Huir solo si el fuego lo puede alcanzar, y nunca por encima de la sed mortal: con el radio de "ver humo"
        # (1,1 km) huían en círculos durante días y se morían de sed sin llegar al agua (pasó de verdad).
        if h.sed < SED_DESPIERTA and sim.fuego_cerca(h, sim.r_huir_fuego):
            sim.sentir(h, "miedo", 0.1)
            return self._demo.decidir(sim, h)        # la huida ya está resuelta ahí
        f = self._familia(sim, h, solo_urgente=True) if h.sed < 70 else None      # responder tarde o un deseo muy fuerte
        if f:
            return f
        if h.salud < 45 and sim.curativo(h):
            return {"tipo": "usar", "objeto": sim.curativo(h)}
        if sim.modulo("frio") and h.sed < 70 and sim.severidad_frio(h) > 0.45 and not sim.fogata_cerca(h, sim.r_fogata) and sim.nieve_en(h.x, h.y) <= 0.6:
            if sim.fuente_de_chispa(h) and sim.lena_que_lleva(h) >= 2:
                return {"tipo": "encender"}
        if h.rotos:                                   # ya aprendió que lo fresco se pudre: lo conserva a tiempo
            from ..motor.conservacion import vida_min
            for c in sim.crudos:
                if h.inventario.get(c, 0) > 0 and h.inv_t.get(c, 0.0) > 0.35 * vida_min(c):
                    return {"tipo": "cocinar"} if sim.fuego_cerca(h, sim.r_mano) else {"tipo": "curar"}
        peli = sim.peligro_cercano(h)
        if peli is not None:
            sim.sentir(h, "miedo", 0.15)
            e = sim.fauna.esp[peli.sp]
            dx, dy = h.x - peli.x, h.y - peli.y
            m = math.hypot(dx, dy) or 1.0
            for dist, giro in ((14, 0.0), (10, 0.7), (10, -0.7), (6, 1.5), (6, -1.5)):     # huye por donde SE PUEDE ir
                ca, sa = math.cos(giro), math.sin(giro)
                vx, vy = (dx * ca - dy * sa) / m, (dx * sa + dy * ca) / m
                c = sim.terreno.caminable_cerca(int(h.x + vx * dist), int(h.y + vy * dist), 3)
                if c and c != (int(h.x), int(h.y)) and sim.terreno.buscar_camino((int(h.x), int(h.y)), c, sim.nodos_camino):
                    return {"tipo": "ir", "destino": c, "motivo": "huye de %s" % e["nombre"]}
        # El hambre va antes que el frío: morirse de hambre es peor que pasar frío, y si el frío manda
        # primero nunca se llega a la línea de buscar comida (pasó: 1426 «dormir» y 0 «juntar»).
        # Buscar comida cansa. Con la energía en rojo primero se duerme: el agotamiento también mata, y si
        # el hambre manda siempre salen a cazar sin descansar nunca (pasó: muertes por agotamiento al día 42).
        if (sim.modulo("hambre") and h.hambre >= HAMBRE_DESPIERTA and h.sed < SED_DESPIERTA
                and h.energia > 20.0):
            if sim.comestibles(h):
                return {"tipo": "comer"}
            # Sin nada encima hay que SALIR A BUSCAR. Si no, se mueren de hambre parados: arrancan con el
            # inventario vacío y nadie sabe cazar todavía (pasó: los tres muertos el día 3).
            aqui = [m for m in sim.disponibles(h) if m in sim.alimentos]
            if aqui:
                return {"tipo": "juntar", "material": aqui[0]}
            if sim.modulo_fauna():
                presas = [g for g in sim.ver_animales(h) if g["comestible"] and g["peligro"] < 4]
                if presas:
                    return {"tipo": "cazar", "animal": presas[0]["nombre"]}
        if sim.modulo("frio") and sim.severidad_frio(h) > 0.55 and sim.t - getattr(h, "calor_t", -1e9) > 180:
            c = sim.buscar_calor(h)
            # tiene que haber camino: devolver un destino inalcanzable deja a la persona clavada probando
            # una y otra vez (pasó: 312 «No encontraste camino» de 357 intentos)
            if c and sim.terreno.buscar_camino((int(h.x), int(h.y)), c, sim.nodos_camino):
                h.calor_t = sim.t
                return {"tipo": "ir", "destino": c, "motivo": "busca abrigo del frío"}
        umbral_sed, umbral_sueno, noche_sueno = 70.0, 22.0, 60.0
        if sim.modulo("reflejos_genoma") and h.genoma is not None:
            cerca = sim.percibir(h)["cercanos"]
            imp = impulsos(h.genoma, {
                "sed": h.sed / 100.0, "cansancio": (100.0 - h.energia) / 100.0, "dolor": (100.0 - h.salud) / 100.0,
                "amenaza_cercana": 0.0, "hay_otros": 1.0 if cerca else 0.0,
                "noche": 1.0 if reloj.es_noche(sim.t) else 0.0, "familiaridad_lugar": 0.5})
            umbral_sed = 82.0 - 30.0 * imp["buscar_recursos"]      # 52..82: quién se ocupa antes de la sed
            umbral_sueno = 12.0 + 25.0 * imp["descansar"]           # 12..37
            noche_sueno = 45.0 + 30.0 * imp["descansar"]
        # Orden por lo que mata más rápido. La sed saca 0,3 de salud por minuto desde 90; el cansancio 0,1 desde 5.
        # Si el cansancio fuera primero sin este corte, pasa esto: se duerme, la sed lo despierta a los pocos
        # minutos (ver _actualizar), sigue cansado, se vuelve a dormir... y se muere de sed al lado del agua.
        sed_mortal = h.sed >= SED_DESPIERTA      # el mismo umbral con el que el motor lo despierta
        # El hambre va DESPUÉS de la sed (que mata en horas) y ANTES del cansancio. Y usa el mismo umbral con
        # el que el motor lo despierta, para no caer en el bucle de despertarse y volver a dormirse.
        if h.energia <= 12 and not sed_mortal:
            return {"tipo": "dormir", "min": sim.rng.randint(300, 480)}
        if h.sed >= umbral_sed or sed_mortal:
            if sim.terreno.agua_adyacente(int(h.x), int(h.y)):
                return {"tipo": "beber"}
            c = sim.agua_cercana(h, sim.r_agua_cerca) or sim.agua_cercana(h, sim.r_agua_lejos)
            if c:
                return {"tipo": "ir", "destino": c, "luego": "beber", "motivo": "tiene sed"}
            b = sim.buscar_agua_lejos(h)
            if b:
                return b
        if (h.energia <= umbral_sueno or (reloj.es_noche(sim.t) and h.energia < noche_sueno)) and not sed_mortal:
            return {"tipo": "dormir", "min": sim.rng.randint(240, 420)}
        return None

    def _nino(self, sim: Simulacion, h: HabitanteSim) -> dict:
        f = self._reflejos(sim, h)
        if f:
            return f
        m = sim.habitantes.get(h.madre_id) if h.madre_id else None
        if m is not None and m.vivo and math.hypot(m.x - h.x, m.y - h.y) > 5:
            return {"tipo": "ir_hacia", "a": m.id}
        return {"tipo": "esperar", "min": 20, "motivo": "juega cerca"}

    # ------------------------------------------------------------------- prompt
    def _agua_a(self, sim: Simulacion, h: HabitanteSim) -> Optional[float]:
        r = 40
        x0, y0 = int(h.x), int(h.y)
        ys0, ys1 = max(0, y0 - r), min(sim.terreno.alto, y0 + r + 1)
        xs0, xs1 = max(0, x0 - r), min(sim.terreno.ancho, x0 + r + 1)
        ys, xs = np.nonzero(sim.terreno.agua[ys0:ys1, xs0:xs1] > 0)
        if len(xs) == 0:
            return None
        return float(np.min(np.hypot(xs + xs0 - h.x, ys + ys0 - h.y)))

    def _prompt(self, sim: Simulacion, h: HabitanteSim) -> Tuple[str, str, dict]:
        t = sim.terreno
        cx, cy = min(t.ancho - 1, max(0, int(h.x))), min(t.alto - 1, max(0, int(h.y)))
        bioma = B.BIOMAS[int(t.bioma[cy, cx])][1]
        percep = sim.percibir(h)
        cercanos = percep["cercanos"]
        L = []
        sexo = "mujer" if h.sexo == "F" else "hombre"
        L.append("Sos %s, %s de %.0f años. %s." % (h.nombre, sexo, sim.edad_anios(h),
                 describir_temperamento(h.genoma, h.rasgos_vivos or None).capitalize() if h.genoma else "De carácter equilibrado"))
        L.append("Ahora: %s. Estás en %s%s." % (reloj.texto(sim.t), bioma, ", de noche" if reloj.es_noche(sim.t) else ""))
        L.append("Tu cuerpo: sed %d/100 (100 = muriendo de sed), cansancio %d/100, salud %d/100." % (
            h.sed, 100 - h.energia, h.salud))
        if sim.modulo("frio"):
            T = sim.temp_en(h.x, h.y)
            if T <= 0:
                L.append("Hiela (%d °C)%s." % (round(T), " y el suelo está cubierto de nieve" if sim.nieve_en(h.x, h.y) > 0.3 else ""))
            elif T < 8:
                L.append("Hace frío (%d °C)." % round(T))
            if h.frio > 0.3:
                L.append("Estás a la intemperie y el frío te está debilitando.%s" % (" Lo que llevás puesto te abriga algo." if sim.abrigo_de(h) > 0 else ""))
        if sim.modulo("psique"):
            viaje = sim.describir_viaje(h)
            if viaje:
                L.append("Algo que comiste te está haciendo efecto: %s. No estás seguro de lo que ves." % viaje)
        if sim.modulo("atributos"):
            cuerpo = sim.describir_atributos(h)
            if cuerpo:
                L.append("De tanto vivir, %s." % cuerpo)
        if sim.modulo("emociones"):
            L.append("Te sentís %s." % sim.etiqueta_emocion(h))
        if h.embarazo:
            L.append("Estás esperando un hijo.")
        da = self._agua_a(sim, h)
        L.append("Agua: %s." % ("estás junto al agua" if sim.terreno.agua_adyacente(cx, cy) else
                                "la más cercana está a unas %d celdas" % da if da is not None else "no ves agua cerca"))
        ll = sim.clima.lluvia_en(h.x, h.y)
        if ll > 0.1:
            L.append("Está lloviendo%s." % (" fuerte" if ll > 0.5 else ""))
        animales = sim.ver_animales(h)
        if animales:
            L.append("Animales que ves:")
            for g in animales[:7]:
                notas = []
                if g["agresivo"] == "siempre" and g["peligro"] >= 4:
                    notas.append("PELIGROSO")
                elif g["peligro"] >= 4:
                    notas.append("peligroso si lo molestás")
                if g["veneno"]:
                    notas.append("venenoso")
                if g["comestible"]:
                    notas.append("sirve de comida y cuero")
                if g["montable"]:
                    notas.append("se podría montar")
                L.append("- %s (%d), a %d celdas%s" % (g["nombre"], g["n"], g["dist"], (" — " + ", ".join(notas)) if notas else ""))
        ganas = self.ganas_de_familia(sim, h) if sim.modulo("reproduccion") else 0.0
        if ganas >= 0.6:
            pos = self._pareja_posible(sim, h)
            if pos:
                L.append("Hace tiempo que sentís ganas de formar una familia y tener un hijo; %s podría ser tu pareja." % ", ".join(o.nombre for o in pos[:2]))
            elif ganas >= 1.0:
                L.append("Sentís ganas de formar una familia, pero ahora no hay con quién.")
        if sim.fogata_cerca(h, sim.r_fogata):
            L.append("Hay una fogata encendida cerca: da calor y luz, y se puede cocinar en ella.")
        if h.hogar:
            L.append("Tenés un refugio cerca de (%d, %d)." % (int(h.hogar[0]), int(h.hogar[1])))
        if h.inventario:
            L.append("Llevás: " + ", ".join("%d de %s%s" % (v, k, (" (%s)" % sim.estado_item(h, k)) if sim.estado_item(h, k) else "")
                                            for k, v in h.inventario.items() if v > 0) + ".")
            if any(h.inventario.get(c, 0) > 0 for c in ("carne", "pescado")):
                L.append("La carne cruda se pudre en un par de días: se puede cocinar (cerca de un fuego) o curar (secarla, dura semanas).")
        if h.montura is not None:
            L.append("Estás montando un animal (vas más rápido).")
        nombres = {}
        if cercanos:
            L.append("Personas que ves:")
            for c in cercanos[:6]:
                nombres[c["nombre"].lower()] = c["id"]
                est = {"durmiendo": "duerme", "caminando": "camina", "hablando": "está hablando"}.get(c["accion"], "")
                dorm = c["accion"] == "durmiendo"
                L.append("- %s (%s%s), a %d celdas%s%s" % (
                    c["nombre"], "mujer" if c["sexo"] == "F" else "hombre", "" if c["adulto"] else ", niño",
                    c["dist"], ", " + est if est else "",
                    " — está durmiendo: no te va a oír" if dorm else (" — está al alcance de tu voz" if c["al_alcance"] else "")))
        else:
            L.append("No ves a nadie cerca.")
        if sim.modulo("memoria"):
            rels = social.relaciones_de(self.con, h.id)
            if rels:
                L.append("Lo que sentís por quienes conocés: " + "; ".join(
                    "%s (%s)" % (r["otro_nombre"], social.describir_relacion(r["afecto"], r["confianza"])) for r in rels[:5]) + ".")
            # recuerdos: no «los últimos 5», sino los que más sirven para esta situación (recientes + importantes + relacionados)
            ctx = [bioma] + [c["nombre"] for c in cercanos] + [g["nombre"] for g in (animales or [])] + [m for _, _, m in h.mensajes]
            if reloj.es_noche(sim.t):
                ctx.append("noche dormir")
            if h.sed >= 60:
                ctx.append("sed agua")
            if sim.fuego_cerca(h, sim.r_ver_fuego):
                ctx.append("fuego incendio")
            if h.ultimo_resultado:
                ctx.append(h.ultimo_resultado)
            ctx_txt = " ".join(ctx)
            mem = MemoriaPrivada(self.con, h.id, sim.semantica)
            cre = mem.creencias(3, ctx_txt, sim.t)
            if cre:
                L.append("Lo que fuiste aprendiendo:")
                for m in cre:
                    L.append("- " + m["contenido"])
            rec = mem.recordar(sim.t, ctx_txt, h.x, h.y, n=6, tipos=("episodica", "semantica"))
            if rec:
                L.append("Recordás:")
                for m in sorted(rec, key=lambda m: m["t_min"]):
                    L.append("- " + m["contenido"] + _procedencia(m)
                             + (" (ya pasó %d veces)" % m["veces"] if m.get("veces", 1) > 1 else ""))
            if sim.modulo("habitos"):
                hb = self._hb(h)
                v = hb.valores(self._features(sim, h))
                h.habito_v = v
                if hb.n >= 10:
                    mejor, peor = max(v, key=v.get), min(v, key=v.get)
                    if v[mejor] >= 0.15:
                        L.append("Por lo que fuiste viviendo, últimamente te tira %s." % FRASE[mejor])
                    if v[peor] <= -0.15 and peor != mejor:
                        L.append("Y te fue mal con %s, así que te da desconfianza." % FRASE[peor])
            if sim.modulo("objetivos") and h.objetivo:
                L.append("Te propusiste %s (%s)." % (sim._texto_objetivo(h.objetivo),
                                                     h.objetivo.get("porque", "")))
            if h.plan:
                L.append("Tus intenciones: " + "; ".join(h.plan) + ".")
            lug = []
            for tipo, nombre in (("agua", "agua"), ("peligro", "peligro"), ("comida", "buena caza"), ("refugio", "refugio")):
                cand = sorted(h.lugares.get(tipo, []), key=lambda p: math.hypot(p[0] - h.x, p[1] - h.y))[:2]
                for p in cand:
                    d = math.hypot(p[0] - h.x, p[1] - h.y)
                    lug.append("%s hacia el %s, a %d celdas%s" % (nombre, _rumbo(p[0] - h.x, p[1] - h.y), int(d),
                               " (%s%s)" % (p[3], ", %d veces" % p[4] if p[4] > 1 else "") if p[3] and tipo != "agua" else ""))
            if lug:
                L.append("Lugares que recordás: " + "; ".join(lug) + ".")
        # Lo que se ve a lo lejos y lleva a alguna parte (una boca de caverna en la ladera, un pozo abierto).
        # Nunca se nombra como «otro mapa»: es un agujero en la piedra, y entrar es meterse a ver qué hay.
        pasos = []
        for r in sim.refugios:
            e = sim.estructuras.get(r.get("tipo")) or {}
            if not (e.get("provee") or {}).get("lleva_a"):
                continue
            d = math.hypot(r["x"] - h.x, r["y"] - h.y)
            if d <= sim.r_vista:
                pasos.append((d, "%s hacia el %s, a %d celdas" % (e.get("nombre", "un paso"),
                                                                 _rumbo(r["x"] - h.x, r["y"] - h.y), int(d))))
        if pasos:
            pasos.sort()
            L.append("Ves " + "; ".join(t for _, t in pasos[:2]) + ". Si te parás al lado, podés meterte a ver qué hay.")
        if h.conoce:
            L.append("Sabés hacer o saber: " + ", ".join(sim.conocimientos[c]["nombre"] for c in h.conoce if c in sim.conocimientos) + ".")
        recibido = list(h.mensajes)
        h.mensajes = []
        for _, quien, msg in recibido:
            L.append("%s te dijo: «%s»" % (quien, msg))
        dias = (sim.t - h.novedad_t) / 1440.0
        if dias >= 4:
            L.append("Hace %d días que hacés siempre lo mismo en los mismos lugares. Te aburre; tenés ganas de explorar lejos, "
                     "de probar algo nuevo o de ver qué hay más allá." % dias)
        elif dias >= 1.5:
            L.append("Hace un par de días que no descubrís nada nuevo; te pica la curiosidad por ver qué hay más lejos.")
        ausentes = sim.ausentes(h) if sim.modulo("percepcion_social") else []
        if ausentes and not cercanos:
            sin = min(a[1] for a in ausentes)
            if sin >= 1.0:
                L.append("Hace %d días que no ves a nadie y extrañás compañía." % sin)
        for o, d_sin, dx, dy, dist in ausentes[:3]:
            rumbo = _rumbo(dx, dy)
            L.append("No ves a %s; la última vez estaba hacia el %s, a unas %d celdas%s." % (
                o.nombre, rumbo, int(dist), (" (hace %d días)" % d_sin) if d_sin >= 1 else ""))
        ideas = self._ideas(sim, h, animales)
        if ideas:
            L.extend(ideas)
        paso = self._siguiente_paso(sim, h)
        if paso:
            L.append(paso)
        if h.ultimo_resultado:
            L.append("Lo último que intentaste: " + h.ultimo_resultado)
        propuesta = None
        if h.propuesta and sim.t - h.propuesta["t"] <= 360:
            o = sim.habitantes.get(h.propuesta["de"])
            if o is not None and o.vivo:
                propuesta = o
                L.append("%s te propuso formar una familia, y te está esperando una respuesta." % o.nombre)
        # acciones disponibles
        A = ["ir_al_agua: ir hasta el agua más cercana", "beber: tomar agua (si estás junto al agua)",
             "dormir", "esperar: quedarte un rato", "explorar: caminar a conocer los alrededores (lejos de tus compañeros te quedás solo)"]
        if any(h.inventario.get(c, 0) > 0 for c in ("carne", "pescado")):
            A.append("curar: secar la carne para que dure semanas")
            if sim.fogata_cerca(h, sim.r_mano) or sim.fuego_cerca(h, sim.r_mano):
                A.append("cocinar: cocinar la carne en el fuego")
        if sim.modulo("hambre"):
            com = sim.comestibles(h)
            if com:
                A.append('comer: comer algo de lo que llevás (%s) -> {"accion":"comer","objeto":"nombre"}' % ", ".join(com[:5]))
        if sim.modulo("conocimientos"):
            disp = sim.disponibles(h)
            if disp:
                A.append('juntar: recoger materiales de lo que hay acá (%s) -> {"accion":"juntar","material":"palo"}' % ", ".join(sorted(disp)))
            hacer, faltan = [], []
            for c in h.conoce:
                rid = sim.conocimientos.get(c, {}).get("receta_id")
                r = sim.recetas.get(rid) if rid else None
                if not r:
                    continue
                usar, falta = sim._ingredientes_ok(h, r)
                if usar is None:
                    aca = sim.disponibles(h, con_agotados=True)
                    miss = [i for i in r["ingredientes"] if not i.startswith("#") and h.inventario.get(i, 0) <= 0]
                    donde = ", ".join("%s%s" % (i, "" if i in aca else " (no se consigue acá: hay que ir a otro lugar)") for i in miss)
                    faltan.append("%s (te falta %s)" % (r["nombre"], donde or falta))
                elif not sim.requisitos_ok(h, r)[0]:
                    faltan.append("%s (%s)" % (r["nombre"], sim.requisitos_ok(h, r)[1].rstrip(".").lower()))
                else:
                    hacer.append(r["nombre"] + (" — lleva un rato" if r["tiempo_min"] >= 240 else ""))
            ago = sim.agotados(h)
            if ago:
                L.append("Acá ya juntaste todo el material de: %s (vuelve a crecer con los días); para conseguir más hay que ir a otro lado." % ", ".join(ago))
            an = self.ancla.get(h.id)
            if an is None or math.hypot(an[0] - h.x, an[1] - h.y) > 18:
                self.ancla[h.id] = [h.x, h.y, sim.t]
            elif (sim.t - an[2]) / 1440.0 >= 3:
                L.append("Hace %d días que no te alejás de este lugar; más allá hay sitios que no conocés, con otros materiales y animales." % int((sim.t - an[2]) / 1440.0))
            if hacer:
                A.append('fabricar: hacer algo que ya sabés y para lo que tenés todo (%s) -> {"accion":"fabricar","objeto":"nombre"}' % ", ".join(hacer[:8]))
            if faltan:
                L.append("Sabés hacer pero hoy no podés: " + "; ".join(faltan[:5]) + ".")
            if sim.fuente_de_chispa(h) and sim.lena_que_lleva(h) >= 2:
                A.append("encender: prender una fogata (da calor y luz, sirve para cocinar)")
            elif sim.lena_que_lleva(h) >= 1 and (sim.fogata_cerca(h, sim.r_mano) or sim.fuego_cerca(h, sim.r_mano)):
                A.append("tomar_fuego: prender una rama en ese fuego y llevarte la llama (sirve para encender otra fogata)")
            if sim.curativo(h) and h.salud < 85:
                A.append('usar: curarte con lo que fabricaste -> {"accion":"usar","objeto":"nombre"}')
        if ausentes:
            A.append('buscar: ir adonde viste por última vez a alguien que ahora no ves -> {"accion":"buscar","a":"Nombre"}')
        if cercanos:
            A.append('ir_hacia: acercarte a alguien -> {"accion":"ir_hacia","a":"Nombre"}')
        if any(c["al_alcance"] and c["accion"] != "durmiendo" for c in cercanos) and sim.modulo("conversacion"):
            A.append('hablar -> {"accion":"hablar","a":"Nombre","mensaje":"lo que le decís",'
                     '"intencion":"contar|advertir|preguntar|mentir","impresion":-2..2 (qué impresión te da)}. '
                     'Lo que decís le queda al otro: si le advertís de un peligro o le contás dónde hay agua, '
                     'se lo lleva anotado.')
        if propuesta is not None:
            A.insert(0, 'responder_propuesta -> {"accion":"responder_propuesta","acepta":true/false}  (la persona espera tu respuesta)')
        elif sim.modulo("reproduccion") and sim.es_adulto(h) and any(c["al_alcance"] and c["adulto"] and c["sexo"] != h.sexo for c in cercanos):
            A.append('proponer_hijo: proponerle formar una familia a alguien que te importe -> {"accion":"proponer_hijo","a":"Nombre"}')
        if animales and sim.modulo_fauna():
            A.append('cazar: ir tras un animal y atraparlo para conseguir carne, cuero y huesos (con una lanza o un arco tenés más suerte; '
                     'los grandes depredadores te pueden herir) -> {"accion":"cazar","animal":"ciervo"}')
            if sim.sabe(h, "rienda") and h.montura is None and any(g["montable"] for g in animales):
                A.append('montar -> {"accion":"montar","animal":"caballo"}')
        if h.montura is not None:
            A.append("desmontar: bajarte del animal")
        paso = sim.mundo.pasaje_cerca(sim, h) if sim.mundo is not None else None
        if paso:
            # Nunca se nombra «dimensión» ni nada que suene a que esto es un sistema: ve un paso y ve que baja.
            A.append('atravesar: meterte por %s, que sigue para el otro lado -> {"accion":"atravesar"}'
                     % sim.estructuras.get(paso["tipo"], {}).get("nombre", "ese paso"))
        if sim.modulo("conocimientos"):
            if h.conoce and any(c["al_alcance"] for c in cercanos):
                A.append('ensenar -> {"accion":"ensenar","a":"Nombre","conocimiento":"nombre de lo que sabés"}')
            mats = ", ".join(sorted(sim.reglas.materiales))
            props = ", ".join(conocimiento.PROPIEDADES)
            A.append('inventar: probar una idea nueva con materiales reales (%s). Propiedades que se pueden comprobar: %s '
                     '-> {"accion":"inventar","receta":{"nombre":"nombre que le pongas","materiales":["material1","material2"],"propiedad":"una de las propiedades","descripcion":"para qué sirve"}}' % (mats, props))
        if ideas and any(a.startswith("inventar") for a in A):     # si se les ocurrió algo, la opción de probarlo va primera
            i = next(k for k, a in enumerate(A) if a.startswith("inventar"))
            A.insert(0, A.pop(i))
        L.append("Qué hacés ahora? Acciones posibles:\n" + "\n".join("* " + a for a in A))
        L.append('Respondé un JSON empezando por "pensamiento" (analizá tu estado, tus recuerdos, qué materiales tenés o ves y qué te conviene hacer) y luego "accion" con los campos que pida.')
        return SISTEMA.format(nombre=h.nombre), "\n".join(L), nombres

    # -------------------------------------------------------------- reflexión
    def _reflexion(self, sim: Simulacion, h: HabitanteSim) -> Optional[dict]:
        """Una vez por día del mundo, mientras está despierto y libre, repasa lo vivido y saca aprendizajes e intenciones
        (la «reflexión» de Generative Agents: lo vivido se condensa en algo que dura más y orienta lo que viene)."""
        p = self.pend_ref.get(h.id)
        if p is not None:
            fut, prompt = p
            if time.time() - fut.t0 > sim.ajustes["timeout_s"] + 10:
                self.pend_ref.pop(h.id, None)
                return None
            if not fut.done():
                return {"tipo": "esperar", "min": 1, "motivo": "pensando"}
            self.pend_ref.pop(h.id, None)
            try:
                self._guardar_reflexion(sim, h, fut.result(), prompt)
            except Exception:
                pass
            return None
        if sim.t < 1440 or sim.t - h.ultima_reflexion_t < DIAS_REFLEXION * 1440:
            return None
        mem = MemoriaPrivada(self.con, h.id, sim.semantica)
        if mem.contar() < 6:
            return None
        # reflexionar cuesta una consulta entera al modelo: solo vale la pena si pasó algo nuevo desde la última vez
        nuevas = self.con.execute("SELECT COUNT(*) FROM memorias WHERE habitante_id = ? AND t_min > ? AND tipo IN ('episodica','semantica')",
                                  (h.id, int(h.ultima_reflexion_t))).fetchone()[0]
        if nuevas < MIN_MEMORIAS_REFLEXION:
            h.ultima_reflexion_t = sim.t - (DIAS_REFLEXION - 1) * 1440     # reintenta mañana, no en 3 días
            return None
        h.ultima_reflexion_t = sim.t
        rec = mem.recordar(sim.t, "", h.x, h.y, n=10, tipos=("episodica", "semantica"), tocar=False)
        for m in mem.recientes(6):
            if m["id"] not in {x["id"] for x in rec} and m["tipo"] in ("episodica", "semantica"):
                rec.append(m)
        previas = mem.creencias(3, "", sim.t)
        L = ["Es el final de un día. Repasás lo que te pasó:"]
        for m in sorted(rec, key=lambda m: m["t_min"]):
            L.append("- " + m["contenido"] + _procedencia(m)
                     + (" (%d veces)" % m["veces"] if m.get("veces", 1) > 1 else ""))
        if previas:
            L.append("Lo que ya habías aprendido:")
            L.extend("- " + m["contenido"] for m in previas)
        if h.plan:
            L.append("Tus intenciones de ayer: " + "; ".join(h.plan) + ".")
        L.append("Pensá con calma. ¿Qué aprendiste de esto que te sirva para vivir mejor (algo nuevo, no lo que ya sabías)? ¿Qué te proponés hacer mañana?")
        L.append('Respondé un JSON: {"aprendizajes":["1 a 3 frases cortas"],"intenciones":["1 a 3 cosas concretas que puedas hacer acá"]}')
        prompt = "\n".join(L)
        fut = self.cliente.pedir(sim.ajustes, SISTEMA.format(nombre=h.nombre), prompt, ESQUEMA_REFLEXION,
                                 semilla=(sim.semilla * 17 + h.id * 11 + int(sim.t)) & 0x7FFFFFFF)
        self.pend_ref[h.id] = (fut, prompt)
        return {"tipo": "esperar", "min": 1, "motivo": "pensando"}

    def _guardar_reflexion(self, sim: Simulacion, h: HabitanteSim, r: dict, prompt: str) -> None:
        d = extraer_json(r.get("texto", "")) or {}
        lat = int(1000 * r.get("latencia_s", 0))
        mem = MemoriaPrivada(self.con, h.id, sim.semantica)
        viejas = [tokens(m["contenido"]) for m in mem.creencias(8, "", sim.t)]
        nuevas = []
        for a in (d.get("aprendizajes") or [])[:3]:
            a = " ".join(str(a).split())[:160]
            tk = tokens(a)
            if len(a) < 12 or not tk or any(len(tk & v) / max(1, len(tk | v)) > 0.6 for v in viejas):
                continue       # vacío o repetido: no se guarda
            nuevas.append(a)
            self._recuerdo_ref(sim, h, a)
        plan = [" ".join(str(i).split())[:110] for i in (d.get("intenciones") or [])[:3] if len(str(i).strip()) >= 6]
        if plan:
            h.plan = plan
        self.reflexiones += 1
        self._registrar(sim, h, prompt, json.dumps(d, ensure_ascii=False), "reflexionar",
                        "Aprendió: %s | Se propone: %s" % ("; ".join(nuevas) or "nada nuevo", "; ".join(h.plan) or "nada"), 1 if d else 0, lat)

    def _recuerdo_ref(self, sim: Simulacion, h: HabitanteSim, texto: str) -> None:
        sim._recuerdo(h, texto, 0.85, "creencia", "reflexion")

    # ------------------------------------------------------- siguiente paso útil
    def _siguiente_paso(self, sim: Simulacion, h: HabitanteSim) -> Optional[str]:
        """El sentido común del motor, dicho como una corazonada. Sin esto nunca encienden un fuego ni construyen:
        `plan_tecnologico` solo se usaba cuando el modelo estaba caído, o sea nunca."""
        if not sim.modulo("conocimientos"):
            return None
        try:
            p = sim.plan_tecnologico(h)
        except Exception:
            return None
        if not p:
            return None
        t = p.get("tipo")
        if t == "encender":
            return "Tenés con qué prender fuego y leña encima: se te viene a la cabeza armar una fogata acá."
        if t == "tomar_fuego":
            return "Hay fuego al alcance: podrías prender un palo y llevarte la llama."
        if t == "juntar":
            return "Te falta juntar %s para lo que querés hacer, y acá hay." % p.get("material")
        if t == "fabricar":
            r = sim.recetas.get(p.get("objeto"), {})
            return "Tenés todo para hacer %s y te vendría bien." % (r.get("nombre") or p.get("objeto"))
        if t == "inventar":
            r = p.get("receta") or {}
            return ("Se te cruza una idea: probar %s con %s, para que %s."
                    % (r.get("nombre"), " y ".join(r.get("materiales") or []), r.get("propiedad")))
        if t == "usar":
            return "Estás lastimado y llevás algo con qué curarte."
        return None

    # ------------------------------------------------------------------ ideas
    def _ideas(self, sim: Simulacion, h: HabitanteSim, animales: list) -> list:
        """Pistas para que se les ocurra inventar algo que les resuelva un problema real que están viviendo.
        No dicen QUÉ inventar (el nombre y la receta los pone la persona); solo señalan la necesidad y qué propiedad la resolvería."""
        if not sim.modulo("conocimientos"):
            return []
        dias = (sim.t - h.ultima_idea_t) / 1440.0
        if dias < 0.75:
            return []
        sabe = {sim.conocimientos[c]["propiedad"] for c in h.conoce if c in sim.conocimientos}
        # (urgencia, propiedad, frase). Lo que mata va primero: sin esto, «ata» (lo más inofensivo) tapaba al resto.
        motivos = []
        frio = sim.modulo("frio") and sim.temp_en(h.x, h.y) < 8
        if "enciende" not in sabe:
            motivos.append((9 if frio else 7, "enciende",
                            "Cuando cae la noche no tenés con qué hacer fuego, y el fuego es calor, luz y comida caliente."))
        if "arde" not in sabe and (reloj.es_noche(sim.t) or frio):
            motivos.append((8, "arde", "De noche se ve poco y hace frío; algo que arda cambiaría eso."))
        if "abriga" not in sabe and frio:
            motivos.append((8, "abriga", "El frío de las noches te debilita y dormís a la intemperie; algo que te abrigue ayudaría."))
        if "construye" not in sabe:
            motivos.append((7 if frio else 5, "construye",
                            "Dormís donde te agarra la noche, sin nada encima; un techo propio te cambiaría la vida."))
        if sim.t - h.ataque_t < 3 * 1440 and "corta" not in sabe:
            motivos.append((7, "corta", "Un animal te lastimó hace poco; algo con filo, o con qué defenderte, te vendría bien."))
        if animales and "corta" not in sabe:
            motivos.append((6, "corta", "Ves animales de los que sacarías comida y cuero, pero con las manos vacías es difícil."))
        if "cura" not in sabe and h.salud < 70:
            motivos.append((6, "cura", "Estás golpeado y no tenés con qué curarte."))
        if "perfora" not in sabe and h.inventario.get("cuero", 0) + h.inventario.get("piel", 0) > 0:
            motivos.append((4, "perfora", "Llevás cuero que no podés coser ni agujerear."))
        if "flota" not in sabe and sim.terreno.agua_adyacente(int(h.x), int(h.y)):
            motivos.append((3, "flota", "Estás junto al agua; del otro lado se ven cosas que no alcanzás."))
        if "contiene" not in sabe:
            motivos.append((3, "contiene", "No tenés dónde guardar ni llevar nada: todo lo cargás en las manos."))
        if "ata" not in sabe:
            motivos.append((2, "ata", "Muchas cosas se te caen o se te sueltan; algo que las una ayudaría."))
        if not motivos:
            return []
        sim.rng.shuffle(motivos)                       # desempata al azar...
        motivos.sort(key=lambda m: -m[0])              # ...pero la necesidad manda
        motivos = [(p, f) for _, p, f in motivos]
        L = ["Hace %d días que no probás una idea nueva; tus manos quieren hacer algo útil." % max(1, int(dias))]
        vistos = set()
        for prop, frase in motivos:
            if prop in vistos:
                continue
            vistos.add(prop)
            L.append(frase + " Pensá qué materiales reales conocés o tenés a mano cuya naturaleza sirva para que %s." % prop)
            if len(vistos) >= 2:
                break
        L.append("Podés usar «inventar» para probarlo: el mundo comprueba si de verdad funciona con esos materiales.")
        return L


    def _lanzar(self, sim: Simulacion, h: HabitanteSim, firma: tuple) -> None:
        sistema, usuario, nombres = self._prompt(sim, h)
        fut = self.cliente.pedir(sim.ajustes, sistema, usuario, ESQUEMA, semilla=(sim.semilla * 13 + h.id * 7 + int(sim.t)) & 0x7FFFFFFF)
        fut.nombres = nombres  # type: ignore[attr-defined]
        # la firma se calcula DESPUÉS de armar el prompt (que consume los mensajes) para detectar novedades
        self.pend[h.id] = (fut, (len(h.mensajes), bool(h.propuesta), len(h.conoce)), usuario)

    # ------------------------------------------------------------- interpretar
    def _interpretar(self, sim: Simulacion, h: HabitanteSim, r: dict, prompt: str) -> dict:
        d = extraer_json(r.get("texto", ""))
        lat = int(1000 * r.get("latencia_s", 0))
        if d is None or d.get("accion") not in ACCIONES:
            self.rechazos_llm += 1
            self._registrar(sim, h, prompt, r.get("texto", ""), "", "Respuesta inválida.", 0, lat)
            return self._respaldo(sim, h)
        self.decisiones_llm += 1
        pens = str(d.get("pensamiento", ""))[:200]
        if pens:
            self.ultimo_pensamiento[h.id] = pens
        ac = d["accion"]
        nombres = {o.nombre.lower(): o.id for o in sim.habitantes.values() if o.vivo and o.id != h.id}
        a_id = nombres.get(str(d.get("a", "")).strip().lower())
        accion: Optional[dict] = None
        if ac == "explorar":
            accion = self._demo_explorar(sim, h)
        elif ac == "ir_al_agua":
            c = sim.agua_cercana(h, sim.r_agua_cerca) or sim.agua_cercana(h, sim.r_agua_lejos)
            accion = {"tipo": "ir", "destino": c, "luego": "beber", "motivo": "va al agua"} if c else None
        elif ac == "beber":
            accion = {"tipo": "beber"}
        elif ac == "dormir":
            accion = {"tipo": "dormir", "min": sim.rng.randint(240, 420)}
        elif ac == "esperar":
            accion = {"tipo": "esperar", "min": 10, "motivo": pens[:40]}
        elif ac in ("ir_hacia", "hablar", "proponer_hijo", "ensenar") and a_id is not None:
            accion = {"tipo": ac, "a": a_id}
            if ac == "hablar":
                accion.update(mensaje=d.get("mensaje", ""), impresion=d.get("impresion", 0),
                              intencion=d.get("intencion", "contar"))
            if ac == "ensenar":
                accion["conocimiento"] = d.get("conocimiento")
        elif ac in ("cocinar", "curar", "encender", "tomar_fuego"):
            accion = {"tipo": ac}
        elif ac == "comer":
            accion = {"tipo": "comer", "objeto": str(d.get("objeto", "")).strip().lower()}
        elif ac == "juntar":
            accion = {"tipo": "juntar", "material": str(d.get("material", "")).strip().lower()}
        elif ac in ("fabricar", "usar"):
            accion = {"tipo": ac, "objeto": str(d.get("objeto", "")).strip()}
        elif ac == "buscar" and a_id is not None:
            accion = {"tipo": "buscar", "a": a_id}
        elif ac in ("cazar", "montar"):
            accion = {"tipo": ac, "animal": d.get("animal", "")}
        elif ac == "desmontar":
            accion = {"tipo": "desmontar"}
        elif ac == "atravesar":
            accion = {"tipo": "atravesar"}
        elif ac == "responder_propuesta":
            accion = {"tipo": "responder_propuesta", "acepta": bool(d.get("acepta"))}
        elif ac == "inventar" and isinstance(d.get("receta"), dict):
            accion = {"tipo": "inventar", "receta": d["receta"]}
        if accion is None:
            self.rechazos_llm += 1
            self._registrar(sim, h, prompt, json.dumps(d, ensure_ascii=False), ac, "Acción incompleta o persona desconocida.", 0, lat)
            return self._respaldo(sim, h)
        # se registra el resultado real cuando el motor la ejecute (ver registrar_resultado)
        h._decision_pendiente = (prompt, json.dumps(d, ensure_ascii=False), ac, lat)  # type: ignore[attr-defined]
        return accion

    def _demo_explorar(self, sim: Simulacion, h: HabitanteSim) -> dict:
        # si hace mucho que está solo y sabe dónde vio a alguien, va a buscarlo antes que seguir alejándose
        aus = sim.ausentes(h) if sim.modulo("percepcion_social") else []
        if aus and min(a[1] for a in aus) >= 2.0 and sim.rng.random() < 0.6:
            return {"tipo": "buscar", "a": aus[0][0].id}
        # Todo EN METROS, no en celdas. Con celdas fijas, en un mundo de 5 m por celda se podían alejar 150 m como
        # mucho, y la zona de recursos mide 800: quedaban encerrados en una zona ya vaciada, sin poder salir nunca.
        acompanado = bool(sim.percibir(h)["cercanos"])
        aburrido = max(0.0, (sim.t - h.novedad_t) / 1440.0)
        # Solo se anima menos; de a dos se van bastante más lejos (y vuelven).
        tope_m = (4500.0 if acompanado else 1800.0) * (1.0 + 0.25 * min(4.0, aburrido))
        cerca = sim.celdas(250.0)
        lejos = max(cerca + 1, sim.celdas(tope_m))
        # El grupo no se disuelve, pero el radio TIENE que superar a la zona de recursos: si no, el grupo entero
        # queda atrapado dentro de una sola zona y cuando la vacían no pueden juntar nada más (bug real visto).
        radio_grupo = max(sim.celdas(6000.0 if acompanado else 3500.0), sim.zona * 3.0)
        ref = [(v[0], v[1]) for k, v in h.visto.items() if (o := sim.habitantes.get(k)) is not None and o.vivo]
        cx = sum(p[0] for p in ref) / len(ref) if ref else None
        cy = sum(p[1] for p in ref) / len(ref) if ref else None
        paso_z = max(1, int(sim.celdas(600.0)))        # el mismo cuadriculado con el que se marcan los lugares vistos
        mejor, mejor_p, primero = None, -1e9, None
        for _ in range(16):
            dd = sim.rng.uniform(cerca, lejos)
            a = sim.rng.random() * 2 * math.pi
            c = sim.terreno.caminable_cerca(int(h.x + math.cos(a) * dd), int(h.y + math.sin(a) * dd), 3)
            if not c:
                continue
            primero = primero or c
            if cx is not None and math.hypot(c[0] - cx, c[1] - cy) > radio_grupo:
                continue
            # Preferir lo que NO conoce: sin esto el paseo es al azar y vuelven siempre al mismo lado.
            nuevo = (c[0] // paso_z, c[1] // paso_z) not in h.zonas
            p = (10.0 if nuevo else 0.0) + math.hypot(c[0] - h.x, c[1] - h.y) / max(1.0, lejos)
            if p > mejor_p:
                mejor, mejor_p = c, p
        if mejor is not None:
            return {"tipo": "ir", "destino": mejor, "motivo": "explora"}
        if cx is not None and primero is not None:      # todo quedaba lejos del grupo: vuelve hacia él
            c = sim.terreno.caminable_cerca(int(cx), int(cy), 8)
            if c:
                return {"tipo": "ir", "destino": c, "motivo": "vuelve con los suyos"}
        return {"tipo": "ir", "destino": primero, "motivo": "explora"} if primero else {"tipo": "esperar", "min": 10}

    # --------------------------------------------------------------- registro
    def registrar_resultado(self, sim: Simulacion, h: HabitanteSim, ok: bool, texto: str) -> None:
        dp = getattr(h, "_decision_pendiente", None)
        if dp:
            h._decision_pendiente = None  # type: ignore[attr-defined]
            self._registrar(sim, h, dp[0], dp[1], dp[2], texto, 1 if ok else 0, dp[3])

    def _registrar(self, sim, h, prompt, respuesta, accion, resultado, ok, lat_ms) -> None:
        with self.con:
            self.con.execute(
                "INSERT INTO decisiones (habitante_id, t_min, percepcion, recuerdos, respuesta_modelo, accion, resultado, ok, modelo, latencia_ms) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (h.id, int(sim.t), prompt[:1800], None, respuesta[:600], accion, resultado[:300], ok, sim.ajustes["modelo"], lat_ms))

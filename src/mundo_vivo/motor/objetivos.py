"""
Objetivos y planificación.

Hasta ahora `h.plan` eran tres frases de texto que salían de la reflexión y que nadie ejecutaba: lindas de leer,
sin ningún efecto. Acá vive lo que falta para que una intención se convierta en pasos reales.

Dos piezas, en el orden de Kahneman que pide docs/arquitectura/:

  **Utility AI** — qué querer. Cada objetivo candidato se puntúa con el estado del cuerpo, el carácter heredado
  y lo que la red de hábitos aprendió de cómo le fue antes. Gana el más urgente, con un poco de histéresis para
  que no cambie de idea cada minuto.

  **Encadenado de precondiciones (GOAP corto)** — cómo conseguirlo. «Quiero una lanza» se desarma en: ¿la sé
  hacer? ¿tengo los materiales? ¿hay suficiente calor? Cada respuesta que falta genera el paso anterior.
  Esto sólo es posible porque el registro de la fase A sabe qué pide cada receta: sin él habría que
  hardcodear la tabla de dependencias, que es justo lo que sacamos del motor.

El objetivo se guarda con la persona, así que sobrevive al reinicio y se puede mirar desde el visor.
El motor sigue validando todo: acá sólo se PROPONE.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

MIN_DIA = 1440.0
VENCE_MIN = 3 * MIN_DIA           # un objetivo que no se logró en 3 días se abandona
HISTERESIS = 1.25                 # el nuevo tiene que ganarle por este margen al que ya tenía


class ObjetivosMixin:
    # ------------------------------------------------------- qué querer
    def _candidatos(self, h) -> List[Tuple[float, dict]]:
        """(puntaje, objetivo). El puntaje sale de la necesidad real, no de una lista de prioridades fija."""
        out: List[Tuple[float, dict]] = []
        hambre = h.hambre if self.modulo("hambre") else 0.0

        # --- cuerpo: lo que aprieta ahora
        if h.sed >= 45:
            out.append((h.sed / 100.0 * 3.0, {"que": "beber", "porque": "tengo sed"}))
        if hambre >= 45:
            out.append((hambre / 100.0 * 2.6, {"que": "comer", "porque": "tengo hambre"}))
        if h.energia <= 45:
            out.append(((100.0 - h.energia) / 100.0 * 2.2, {"que": "dormir", "porque": "estoy agotado"}))
        if self.modulo("frio") and self.severidad_frio(h) > 0.3:
            out.append((self.severidad_frio(h) * 2.4, {"que": "calentarse", "porque": "me estoy helando"}))

        # --- oficio: hacer algo que sirva. Lo que ya sabe y le falta tener.
        if self.modulo("conocimientos"):
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
                # más ganas cuanto más arriba esté en la lista de objetivos y más curioso sea
                orden = 1.0 - self.objetivos.index(rid) / max(1, len(self.objetivos))
                out.append((0.9 + 0.7 * orden * (0.5 + h.rasgo("curiosidad")),
                            {"que": "conseguir", "receta": rid, "porque": "me vendría bien %s" % r["nombre"]}))
                break                        # uno por vez: el primero que le falta

        # --- compañía: el que está solo hace días va a buscar
        aus = self.ausentes(h) if self.modulo("percepcion_social") else []
        if aus and not self.percibir(h)["cercanos"]:
            dias = min(a[1] for a in aus)
            if dias >= 1.0:
                out.append((min(2.0, 0.5 * dias) * (0.4 + h.rasgo("sociabilidad")) * (1.0 + self.atractor_fogata(h)),
                            {"que": "buscar", "a": aus[0][0].id, "porque": "hace %d días que no veo a nadie" % dias}))

        # --- curiosidad: conocer lo que hay más allá. Con el fuego encendido y de noche, la fogata TIRA:
        # irse lejos vale menos de lo que vale quedarse donde hay luz y gente (ver `atractor_fogata`).
        dias_quieto = (self.t - h.novedad_t) / MIN_DIA
        out.append((min(1.6, 0.25 * dias_quieto) * (0.4 + h.rasgo("curiosidad")) / (1.0 + self.atractor_fogata(h)),
                    {"que": "explorar", "porque": "quiero ver qué hay más allá"}))

        # --- lo que la experiencia le enseñó (la red de hábitos ya aprendida)
        if self.modulo("habitos") and h.habito_v:
            for act, v in h.habito_v.items():
                if v > 0.2 and act in ("juntar", "fabricar", "cazar", "acercarse"):
                    out.append((0.6 + v, {"que": {"acercarse": "buscar_companiero"}.get(act, act),
                                          "porque": "me viene saliendo bien"}))
        return out

    def elegir_objetivo(self, h) -> Optional[dict]:
        """Decide qué quiere ahora. Mantiene el objetivo anterior salvo que otro le gane por buen margen."""
        if not self.modulo("objetivos"):
            return None
        cands = self._candidatos(h)
        if not cands:
            return None
        cands.sort(key=lambda c: -c[0])
        mejor_p, mejor = cands[0]
        actual = h.objetivo
        if actual and self.t - actual.get("desde", 0) < VENCE_MIN:
            # ¿sigue teniendo sentido el que tenía? Si sí, cuesta cambiarlo.
            igual = next((p for p, c in cands if c.get("que") == actual.get("que")
                          and c.get("receta") == actual.get("receta")), None)
            if igual is not None and mejor_p < igual * HISTERESIS:
                return actual
        if actual and actual.get("que") == mejor.get("que") and actual.get("receta") == mejor.get("receta"):
            return actual                       # el mismo: se conserva la fecha de inicio
        mejor = dict(mejor, desde=self.t)
        h.objetivo = mejor
        self._recuerdo(h, "Te propusiste %s: %s." % (self._texto_objetivo(mejor), mejor.get("porque", "")), 0.4)
        return mejor

    def _texto_objetivo(self, o: dict) -> str:
        que = o.get("que")
        if que == "conseguir":
            r = self.recetas.get(o.get("receta")) or {}
            return "conseguir %s" % r.get("nombre", o.get("receta"))
        return {"beber": "tomar agua", "comer": "comer algo", "dormir": "descansar",
                "calentarse": "entrar en calor", "explorar": "explorar",
                "buscar": "encontrar a alguien", "buscar_companiero": "buscar compañía"}.get(que, str(que))

    # --------------------------------------- cómo conseguirlo (GOAP corto)
    def pasos_para(self, h, objetivo: dict) -> Optional[dict]:
        """La acción concreta de HOY para ese objetivo, o None si no hay forma.

        Para «conseguir X» se desarma la cadena hacia atrás usando el registro: saber -> materiales -> calor.
        """
        que = objetivo.get("que")
        if que == "beber":
            if self.terreno.agua_adyacente(int(h.x), int(h.y)):
                return {"tipo": "beber"}
            c = self.agua_cercana(h, self.r_agua_cerca) or self.agua_cercana(h, self.r_agua_lejos)
            return {"tipo": "ir", "destino": c, "luego": "beber", "motivo": "tiene sed"} if c else None
        if que == "comer":
            if self.comestibles(h):
                return {"tipo": "comer"}
            aqui = [m for m in self.disponibles(h) if m in self.alimentos]
            if aqui:
                return {"tipo": "juntar", "material": aqui[0]}
            if self.modulo_fauna():
                presas = [g for g in self.ver_animales(h) if g["comestible"] and g["peligro"] < 4]
                if presas:
                    return {"tipo": "cazar", "animal": presas[0]["nombre"]}
            return None
        if que == "dormir":
            return {"tipo": "dormir", "min": self.rng_objetivos.randint(300, 480)}
        if que == "calentarse":
            if self.fuente_de_chispa(h) and self.lena_que_lleva(h) >= 2:
                return {"tipo": "encender"}
            c = self.buscar_calor(h)
            if c and self.terreno.buscar_camino((int(h.x), int(h.y)), c, self.nodos_camino):
                return {"tipo": "ir", "destino": c, "motivo": "busca abrigo del frío"}
            return None
        if que == "buscar":
            return {"tipo": "buscar", "a": objetivo.get("a")}
        if que == "conseguir":
            return self._cadena_receta(h, objetivo.get("receta"))
        if que in ("juntar", "fabricar", "cazar", "explorar", "buscar_companiero"):
            return None            # los resuelve el respaldo de siempre
        return None

    def _cadena_receta(self, h, rid: Optional[str]) -> Optional[dict]:
        """El paso que falta para poder hacer `rid`. Acá es donde el registro gana: nadie hardcodeó qué
        necesita cada cosa, sale de los datos."""
        r = self.recetas.get(rid or "")
        if r is None:
            return None
        # 1. ¿lo sabe hacer?
        if not self.sabe(h, r["id"]):
            if self.modulo("conocimientos") and self.t - h.ultima_idea_t > 300:
                ing = []
                for m in r["ingredientes"]:
                    if m.startswith("#"):
                        m = sorted(self.etiquetas.get(m[1:], ("palo",)))[0]
                    ing.append(m)
                return {"tipo": "inventar", "receta": {"nombre": r["nombre"], "materiales": ing,
                                                       "propiedad": r["propiedad"],
                                                       "descripcion": r.get("descripcion", "")}}
            return None
        # 2. ¿tiene los materiales?
        usar, _ = self._ingredientes_ok(h, r)
        if usar is None:
            disp = self.disponibles(h)
            for ing in r["ingredientes"]:
                if ing.startswith("#") or h.inventario.get(ing, 0) > 0:
                    continue
                if ing in disp:
                    return {"tipo": "juntar", "material": ing}
                return None            # no se consigue acá: que el objetivo venza y se replanifique
            return None
        # 3. ¿hay bastante calor? (la progresión horno/fragua de la fase D)
        ok, _ = self.requisitos_ok(h, r)
        if not ok:
            if self.fuente_de_chispa(h) and self.lena_que_lleva(h) >= 2:
                return {"tipo": "encender"}
            if "palo" in self.disponibles(h):
                return {"tipo": "juntar", "material": "palo"}
            return None
        return {"tipo": "fabricar", "objeto": r["id"]}

    # ------------------------------------------------------------- juntas
    def plan_de_objetivo(self, h) -> Optional[dict]:
        """Elige qué quiere y devuelve el paso de hoy. Si el plan no es viable, lo abandona y replanifica."""
        if not self.modulo("objetivos"):
            return None
        o = self.elegir_objetivo(h)
        if not o:
            return None
        paso = self.pasos_para(h, o)
        if paso is None:
            # el plan dejó de ser posible: se descarta y se prueba con el siguiente candidato
            h.objetivo = None
            o2 = self.elegir_objetivo(h)
            if o2 and (o2.get("que") != o.get("que") or o2.get("receta") != o.get("receta")):
                paso = self.pasos_para(h, o2)
        return paso

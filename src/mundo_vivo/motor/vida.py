"""
Vida social del motor: percepción mutua, conversación, familia, enseñanza e invención.

El motor NO decide qué hace cada uno (eso es del cerebro): solo da la POSIBILIDAD y valida que se cumplan las reglas
(distancia, edad, consentimiento, materiales reales). Cada acción devuelve (ok, texto). Los efectos sobre la base de datos
(diálogos, recuerdos, relaciones) salen como eventos internos que empiezan con "_" y los procesa `persistencia/sim_io.py`.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from .. import catalogos
from ..agentes import conocimiento
from ..agentes.genoma import Genoma, heredar

DIAS_ANIO = 120
MIN_DIA = 1440
ANIO_MIN = DIAS_ANIO * MIN_DIA
ADULTO_MIN = 12 * ANIO_MIN          # a los 12 años del mundo ya es adulto
VEJEZ_MIN = 60 * ANIO_MIN           # desde los 60 empieza a morir de vejez
GESTACION_MIN = 60 * MIN_DIA
DESCANSO_PARTO_MIN = 120 * MIN_DIA
# Las distancias van en METROS, no en celdas: así el mismo comportamiento social vale para un mundo de celdas de 50 m
# y para uno de 5 m. `Simulacion.celdas()` las convierte una vez al crear el mundo (ver r_habla, r_vista, r_encuentro).
METROS_HABLA = 300.0                # se oyen gritando
METROS_VISTA = 1500.0               # hasta dónde se reconoce a alguien a campo abierto
METROS_ENCUENTRO = 400.0            # lo bastante cerca como para conocerse
VALIDEZ_PROPUESTA_MIN = 360


def _nombres() -> tuple:
    """Los nombres son contenido: viven en datos_base/cultura/nombres.json y se pueden ampliar sin tocar código."""
    from ..registro import Registro
    d = Registro.cargar().uno("nombres", "fundadores") or {}
    return tuple(d.get("F") or []), tuple(d.get("M") or [])


NOMBRES_F, NOMBRES_M = _nombres()


def _dist(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


class VidaMixin:
    # ------------------------------------------------------------ utilidades
    def modulo(self, nombre: str) -> bool:
        return bool(self.ajustes.get("modulos", {}).get(nombre, False))

    def edad_anios(self, h) -> float:
        return (self.t - h.nacimiento_min) / ANIO_MIN

    def es_adulto(self, h) -> bool:
        return (self.t - h.nacimiento_min) >= ADULTO_MIN

    def _recuerdo(self, h, texto: str, importancia: float = 0.5, tipo: str = "episodica", origen: str = "vivido",
                  de_quien=None, certeza: float = 1.0) -> None:
        """`origen`: vivido (me pasó), oido (me lo contaron), inferido (lo deduje). Con `de_quien` y `certeza`
        un rumor deja de valer lo mismo que algo visto."""
        if self.modulo("memoria"):
            self._evento("_memoria", texto, h, datos={"importancia": importancia, "tipo": tipo, "origen": origen,
                                                      "de_quien": de_quien, "certeza": certeza})

    def percibir(self, h) -> dict:
        """Lo que el habitante ve a su alrededor (solo personas vivas a la vista)."""
        cerca = []
        for o in self.habitantes.values():
            if o.id == h.id or not o.vivo:
                continue
            d = _dist(h, o)
            if d <= self.r_vista:
                cerca.append({"id": o.id, "nombre": o.nombre, "dist": round(d, 1), "accion": o.accion,
                              "adulto": self.es_adulto(o), "sexo": o.sexo, "al_alcance": d <= self.r_habla})
        cerca.sort(key=lambda c: c["dist"])
        return {"cercanos": cerca}

    def certeza_de(self, quien, le_dijo) -> float:
        """Cuánto le cree a lo que le contó esa persona.

        El afecto y la confianza viven en la base y el motor no la toca a propósito, así que la certeza se
        arma con lo que el motor SÍ sabe: si se conocen, si son familia y cuánto hace que se tratan. Un
        desconocido arranca en la mitad; la familia casi se cree del todo.
        """
        c = 0.5
        par = (min(quien.id, le_dijo.id), max(quien.id, le_dijo.id))
        if par in self.conocidos:
            c += 0.15
        if self.parentesco_cercano(quien, le_dijo) is not None:
            c += 0.25
        charlas = len([1 for t in (quien.oido_de.get(le_dijo.id),) if t is not None])
        if charlas and self.t - quien.oido_de[le_dijo.id] < 30 * MIN_DIA:
            c += 0.05           # con trato reciente se le presta más oído
        return max(0.25, min(0.95, c))

    def _interrumpir(self, o) -> None:
        """Alguien le habla o le propone algo: deja lo que hacía (menos dormir) para atender."""
        if o.accion in ("caminando", "esperando", "libre", "bebiendo", "hablando"):
            o.camino, o.hasta, o.accion, o.detalle = [], 0.0, "libre", ""

    # --------------------------------------------------------- paso de vida
    def _vida(self, h, paso: float) -> None:
        # vejez
        if self.t - h.nacimiento_min > VEJEZ_MIN and self.rng_vida.random() < paso / (3 * ANIO_MIN):
            self._morir(h, "vejez")
            return
        # parto
        if h.embarazo and self.t >= h.embarazo["parto_t"]:
            self._nacer(h)
        # encuentros (cada ~5 min simulados)
        if self.modulo("percepcion_social") and self.t >= h.prox_vista:
            h.prox_vista = self.t + 5.0
            if h.vivo and (not h.visto or self.t - max(v[2] for v in h.visto.values()) > 2 * MIN_DIA):
                self.experiencia(h, "soledad")       # extrañar compañía va corriendo el carácter, muy de a poco
            for o in self.habitantes.values():
                if o.id != h.id and o.vivo and _dist(h, o) <= self.r_vista:
                    h.visto[o.id] = [round(o.x, 1), round(o.y, 1), self.t]       # recuerda dónde la vio por última vez
                if o.id != h.id and o.vivo and _dist(h, o) <= self.r_encuentro:
                    par = (min(h.id, o.id), max(h.id, o.id))
                    if par not in self.conocidos:
                        self.conocidos.add(par)
                        self._evento("_encuentro", "%s y %s se conocieron." % (h.nombre, o.nombre), h,
                                     importancia=2, datos={"a": h.id, "b": o.id})

    def _prob_hija(self) -> float:
        """Normalmente mitad y mitad. Pero si de un sexo no queda nadie vivo, el próximo nacimiento se inclina para ese
        lado: si no, un par de muertes mal timeadas dejan al mundo sin futuro y nadie se reproduce más nunca."""
        f = sum(1 for h in self.habitantes.values() if h.vivo and h.sexo == "F")
        m = sum(1 for h in self.habitantes.values() if h.vivo and h.sexo == "M")
        if f == 0 or m == 0:
            return 0.9 if f == 0 else 0.1
        if min(f, m) == 1 and max(f, m) >= 3:        # casi sin futuro de ese lado: una ayudita, no una regla de hierro
            return 0.75 if f < m else 0.25
        return 0.5

    def _nacer(self, madre) -> None:
        padre = self.habitantes.get(madre.embarazo["padre_id"])
        madre.embarazo = None
        madre.sin_concebir_hasta = self.t + DESCANSO_PARTO_MIN
        gm = madre.genoma
        gp = padre.genoma if padre is not None else None
        if gm is None or gp is None:
            gm = gp = gm or gp
        if gm is None:
            return
        g = heredar(gm, gp, self.semilla * 7919 + int(self.t))
        sexo = "F" if self.rng_vida.random() < self._prob_hija() else "M"
        usados = {x.nombre for x in self.habitantes.values()}
        pool = [n for n in (NOMBRES_F if sexo == "F" else NOMBRES_M) if n not in usados] or ["Nuevo%d" % (len(self.habitantes) + 1)]
        nombre = self.rng_vida.choice(pool)
        if self.al_nacer is not None:
            nuevo = self.al_nacer(self, madre, padre, g, sexo, nombre)
        else:
            from .simulacion import HabitanteSim
            nuevo = HabitanteSim(max(self.habitantes) + 1, nombre, madre.x, madre.y, color=len(self.habitantes))
            nuevo.sexo, nuevo.genoma, nuevo.madre_id = sexo, g, madre.id
            nuevo.padre_id = padre.id if padre else None
            nuevo.nacimiento_min = int(self.t)
            self.habitantes[nuevo.id] = nuevo
        # Fase 8: penalización por endogamia si los padres son medio hermanos (colapso genético).
        endogamia = False
        if padre is not None:
            endogamia = ((madre.madre_id and madre.madre_id == padre.madre_id) or
                         (madre.padre_id and madre.padre_id == padre.padre_id)) and not (
                madre.madre_id == padre.madre_id and madre.padre_id == padre.padre_id)
        if endogamia:
            nuevo.salud = 70.0
            self._recuerdo(nuevo, "Naciste de una unión cercana; tu salud es frágil.", 0.6)
        self._evento("nacimiento", "Nació %s, hij%s de %s%s." % (nuevo.nombre, "a" if sexo == "F" else "o",
                     madre.nombre, (" y " + padre.nombre) if padre else ""), nuevo, importancia=4,
                     datos={"madre": madre.id, "padre": padre.id if padre else None})
        self._hito("primer_hijo", nuevo, "el primer hijo nacido en este mundo: %s." % nuevo.nombre)
        if madre.madre_id is not None or madre.padre_id is not None or (padre is not None and (padre.madre_id is not None or padre.padre_id is not None)):
            self._hito("nietos", nuevo, "tres generaciones: nació %s, nieto de los fundadores." % nuevo.nombre)
        vivos = sum(1 for x in self.habitantes.values() if x.vivo)
        for n, clave, txt in ((10, "pob10", "diez personas viven en este mundo."), (25, "pob25", "veinticinco personas: ya es un pueblo."),
                              (60, "pob60", "sesenta personas: una pequeña ciudad.")):
            if vivos >= n:
                self._hito(clave, nuevo, txt)
        for p in (madre, padre):
            if p is not None and p.vivo:
                self.sentir(p, "alegria", 0.8)
                self._recuerdo(p, "Nació tu hij%s %s." % ("a" if sexo == "F" else "o", nuevo.nombre), 0.95)

    # ------------------------------------------------------------- acciones
    def _accion_hablar(self, h, it: dict) -> Tuple[bool, str]:
        if not self.modulo("conversacion"):
            return False, "Hablar no está habilitado."
        o = self.habitantes.get(int(it.get("a", -1)))
        msg = " ".join(str(it.get("mensaje", "")).split())[:280]
        if o is None or not o.vivo or o.id == h.id:
            return False, "Esa persona no está."
        if not msg:
            return False, "No dijiste nada."
        if _dist(h, o) > self.r_habla:
            return False, "%s está demasiado lejos para oírte; tenés que acercarte." % o.nombre
        if o.accion == "durmiendo" and self.t < o.hasta:
            return False, "%s está durmiendo y no te oye; esperá a que despierte." % o.nombre
        if h.ultimo_dicho.get(o.id) == msg:
            return False, "Ya le dijiste exactamente eso."
        respondiendo = self.t - h.oido_de.get(o.id, -1e9) <= 90.0
        if not respondiendo and self.t - h.ultima_charla.get(o.id, -1e9) < 120.0:
            return False, "Hablaste con %s hace muy poco; dejá pasar un rato antes de volver a hablarle." % o.nombre
        palabras = {w for w in msg.lower().replace(",", " ").replace(".", " ").split() if len(w) > 3}
        for previo in h.historial_dicho[-3:]:
            pp = {w for w in previo.lower().replace(",", " ").replace(".", " ").split() if len(w) > 3}
            if palabras and pp and len(palabras & pp) / max(1, len(palabras | pp)) > 0.55:
                return False, "Estás repitiendo casi lo mismo que ya dijiste; si no hay nada nuevo que decir, no hables."
        h.historial_dicho = (h.historial_dicho + [msg])[-5:]
        h.ultima_charla[o.id] = self.t
        h.ultimo_dicho[o.id] = msg
        imp = max(-2.0, min(2.0, float(it.get("impresion", 0) or 0)))
        if imp > 0.5:
            self.sentir(h, "alegria", 0.08 * imp)
            self.experiencia(h, "buena_charla")
        elif imp < -0.5:
            self.sentir(h, "enojo", 0.08 * -imp)
            self.experiencia(h, "mala_charla")
        # La certeza viaja con el diálogo: `registrar_dialogo` guarda el recuerdo del que escucha como OÍDO.
        self._evento("_dialogo", msg, h, datos={"emisor": h.id, "receptores": [o.id], "mensaje": msg,
                                                "impresion": imp, "certeza": self.certeza_de(o, h)})
        self._efectos.append({"tipo": "habla", "id": h.id, "texto": msg[:160]})
        o.oido_de[h.id] = self.t
        o.mensajes.append((int(self.t), h.nombre, msg))
        o.mensajes = o.mensajes[-5:]
        self._interrumpir(o)
        if self.modulo("conversacion"):
            self._consecuencia_de_hablar(h, o, it)
        h.accion, h.detalle, h.hasta = "hablando", "habla con %s" % o.nombre, self.t + 2.0
        return True, "Le dijiste a %s: «%s»" % (o.nombre, msg)

    # ------------------------------------------------ consecuencias de hablar
    INTENCIONES = ("contar", "advertir", "preguntar", "mentir")

    def _consecuencia_de_hablar(self, h, o, it: dict) -> None:
        """Hablar no es sólo texto: lo que se dice cambia lo que el otro SABE.

        Hasta ahora una conversación dejaba un recuerdo y nada más. Acá se transfiere conocimiento de verdad:
        avisar de un peligro pone ese lugar en el mapa mental del otro, contar dónde hay agua le sirve para ir.
        Y se puede **mentir**: el que escucha recibe un lugar que no existe, con la misma certeza que si fuera
        cierto. No hay forma de que lo sepa hasta que vaya y no encuentre nada, igual que en la vida.
        """
        intencion = str(it.get("intencion", "contar")).strip().lower()
        if intencion not in self.INTENCIONES:
            intencion = "contar"
        if intencion == "preguntar":
            return
        certeza = self.certeza_de(o, h)
        if intencion == "mentir":
            if not self.modulo("memoria"):
                return
            # Un lugar inventado, en un rumbo cualquiera. El que escucha se lo cree igual que a lo verdadero.
            ang = self.rng_vida.random() * 6.2832
            d = self.celdas(self.rng_vida.uniform(400.0, 2000.0))
            fx, fy = h.x + math.cos(ang) * d, h.y + math.sin(ang) * d
            o.marcar_lugar("agua", fx, fy, "se lo contaron", self.t, radio=self.celdas(300.0))
            self._recuerdo(o, "%s te contó que hay agua hacia allá." % h.nombre, 0.5,
                           origen="oido", de_quien=h.id, certeza=certeza)
            self.experiencia(h, "mentir")
            self._evento("mentira", "%s le contó algo que no era cierto a %s." % (h.nombre, o.nombre), h,
                         importancia=2, datos={"a": o.id})
            return
        # contar / advertir: se pasa un lugar que el que habla SÍ conoce
        tipo = "peligro" if intencion == "advertir" else self.rng_vida.choice(("agua", "comida", "refugio"))
        propios = h.lugares.get(tipo) or []
        if not propios:
            return
        p = min(propios, key=lambda q: math.hypot(q[0] - h.x, q[1] - h.y))
        o.marcar_lugar(tipo, p[0], p[1], "te lo contó %s" % h.nombre, self.t, radio=self.celdas(300.0))
        comos = {"peligro": "un peligro", "agua": "dónde hay agua",
                 "comida": "dónde cazar", "refugio": "dónde guarecerse"}
        self._recuerdo(o, "%s te contó %s por acá cerca." % (h.nombre, comos[tipo]), 0.55,
                       origen="oido", de_quien=h.id, certeza=certeza)
        if intencion == "advertir":
            self.sentir(o, "miedo", 0.1)

    def _accion_ir_hacia(self, h, it: dict) -> Tuple[bool, str]:
        o = self.habitantes.get(int(it.get("a", -1)))
        if o is None or not o.vivo or o.id == h.id:
            return False, "Esa persona no está."
        d = _dist(h, o)
        if d > self.r_vista:
            return False, "No ves a %s; está lejos." % o.nombre
        if d <= self.r_habla * 0.6:
            h.accion, h.detalle, h.hasta = "esperando", "junto a %s" % o.nombre, self.t + 3.0
            return True, "Ya estás junto a %s." % o.nombre
        dest = self.terreno.caminable_cerca(int(o.x), int(o.y), 3)
        cam = self.terreno.buscar_camino((int(h.x), int(h.y)), dest, self.nodos_camino) if dest else None
        if not cam:
            return False, "No hay camino hasta %s." % o.nombre
        h.camino, h.accion, h.detalle, h.al_llegar = cam, "caminando", "se acerca a %s" % o.nombre, None
        return True, "Vas hacia %s." % o.nombre

    def ausentes(self, h) -> list:
        """Personas vivas que h conoce pero no ve ahora: [(otro, dias_sin_verla, dx, dy, dist)] de la más reciente a la más vieja."""
        out = []
        for oid, (x, y, t) in h.visto.items():
            o = self.habitantes.get(oid)
            if o is None or not o.vivo or _dist(h, o) <= self.r_vista:
                continue
            out.append((o, (self.t - t) / 1440.0, x - h.x, y - h.y, math.hypot(x - h.x, y - h.y)))
        out.sort(key=lambda a: a[1])
        return out

    def _accion_buscar(self, h, it: dict) -> Tuple[bool, str]:
        o = self.habitantes.get(int(it.get("a", -1)))
        if o is None or not o.vivo or o.id == h.id:
            return False, "Esa persona no está."
        v = h.visto.get(o.id)
        if not v:
            return False, "No sabés por dónde buscar a %s." % o.nombre
        if _dist(h, o) <= self.r_vista:
            return False, "Ya ves a %s; acercate." % o.nombre
        dest = self.terreno.caminable_cerca(int(v[0]), int(v[1]), 5)
        cam = self.terreno.buscar_camino((int(h.x), int(h.y)), dest, self.nodos_camino) if dest else None
        if not cam:
            return False, "No hay camino hasta donde viste a %s." % o.nombre
        h.camino, h.accion, h.detalle, h.al_llegar = cam, "caminando", "busca a %s" % o.nombre, None
        return True, "Vas a buscar a %s, adonde la viste por última vez." % o.nombre if o.sexo == "F" else "Vas a buscar a %s, adonde lo viste por última vez." % o.nombre

    def parentesco_cercano(self, a, b, sim=None) -> Optional[str]:
        """Padres, hijos, hermanos y medio hermanos. El motor lo valida: el cerebro solo propone, y podría proponer
        cualquier cosa. Devuelve el vínculo si son familia directa, o None.

        Fase 8: ante cuello de botella genético (población baja y sin parejas fértiles no emparentadas), se
        relaja la prohibición para medio hermanos (distinta madre) aplicando penalización genética en el
        recién nacido en vez de extinguir la colonia."""
        if b.id in (a.madre_id, a.padre_id):
            return "madre" if b.id == a.madre_id else "padre"
        if a.id in (b.madre_id, b.padre_id):
            return "hijo"
        # hermanos completos: siempre prohibido
        if a.madre_id and a.madre_id == b.madre_id and a.padre_id and a.padre_id == b.padre_id:
            return "hermano"
        # medio hermanos: prohibido salvo colapso poblacional
        medio = ((a.madre_id and a.madre_id == b.madre_id) or (a.padre_id and a.padre_id == b.padre_id))
        if medio:
            if sim is not None and self._colapso_genetico(sim):
                return None   # se permite, con penalización al nacer
            return "hermano"
        return None

    def _colapso_genetico(self, sim) -> bool:
        """True si no hay ninguna pareja fértil no emparentada (o población < 10)."""
        vivos = [h for h in sim.habitantes.values() if h.vivo and self.es_adulto(h)]
        if len(vivos) < 10:
            return True
        for a in vivos:
            for b in vivos:
                if a.id >= b.id or a.sexo == b.sexo:
                    continue
                if self.parentesco_cercano(a, b) is None:
                    mujer = a if a.sexo == "F" else b
                    if not (mujer.embarazo or sim.t < mujer.sin_concebir_hasta):
                        return False
        return True

    def _accion_proponer_hijo(self, h, it: dict) -> Tuple[bool, str]:
        if not self.modulo("reproduccion"):
            return False, "Formar familia no está habilitado."
        o = self.habitantes.get(int(it.get("a", -1)))
        if o is None or not o.vivo or o.id == h.id:
            return False, "Esa persona no está."
        if not (self.es_adulto(h) and self.es_adulto(o)):
            return False, "Los dos tienen que ser adultos."
        if h.sexo == o.sexo:
            return False, "Para tener un hijo hacen falta una mujer y un hombre."
        par = self.parentesco_cercano(h, o, sim=self)
        if par is not None:
            return False, ("%s es de tu propia sangre: no se tienen hijos con la familia." % o.nombre)
        # Fase 8: infidelidad — si alguno ya tiene pareja formal y no es el otro, la pareja engañada lo sabe.
        for proponente, otro in ((h, o), (o, h)):
            pareja_id = getattr(proponente, "pareja_id", None)
            if pareja_id is not None and pareja_id != otro.id:
                pareja = self.habitantes.get(pareja_id)
                if pareja is not None and pareja.vivo:
                    self._evento("_relacion", "", pareja, datos={"hab": pareja.id, "otro": proponente.id,
                                                                  "d_afecto": -0.6, "d_confianza": -0.9,
                                                                  "motivo": "traición: propuso familia a otro"})
                    self._recuerdo(pareja, "%s te fue infiel: le propuso familia a %s." % (proponente.nombre, otro.nombre), 0.95)
                    self.sentir(pareja, "tristeza", 0.8)
                    self.sentir(pareja, "enojo", 0.7)
                    self.experiencia(pareja, "traicion")
        mujer = h if h.sexo == "F" else o
        if mujer.embarazo or self.t < mujer.sin_concebir_hasta:
            return False, "%s no puede tener un hijo ahora." % mujer.nombre
        if _dist(h, o) > self.r_habla:
            return False, "%s está demasiado lejos." % o.nombre
        o.propuesta = {"de": h.id, "t": self.t}
        self._interrumpir(o)
        self._recuerdo(o, "%s te propuso formar una familia." % h.nombre, 0.8)
        self._recuerdo(h, "Le propusiste a %s formar una familia." % o.nombre, 0.7)
        h.accion, h.detalle, h.hasta = "hablando", "habla con %s" % o.nombre, self.t + 2.0
        return True, "Le propusiste a %s formar una familia; ahora tiene que decidir." % o.nombre

    def _accion_responder(self, h, it: dict) -> Tuple[bool, str]:
        p = h.propuesta
        h.propuesta = None
        if not p or self.t - p["t"] > VALIDEZ_PROPUESTA_MIN:
            return False, "No hay ninguna propuesta pendiente."
        o = self.habitantes.get(p["de"])
        if o is None or not o.vivo or _dist(h, o) > self.r_habla * 2:
            return False, "Quien te lo propuso ya no está cerca."
        acepta = bool(it.get("acepta"))
        if not acepta:
            self._recuerdo(h, "Le dijiste que no a %s." % o.nombre, 0.5)
            self._recuerdo(o, "%s no quiso formar una familia con vos." % h.nombre, 0.7)
            self._evento("_relacion", "", o, datos={"hab": o.id, "otro": h.id, "d_afecto": -0.05, "d_confianza": 0.0,
                                                    "motivo": "rechazó formar una familia"})
            h.accion, h.detalle, h.hasta = "hablando", "responde a %s" % o.nombre, self.t + 1.0
            return True, "Le dijiste que no a %s." % o.nombre
        mujer = h if h.sexo == "F" else o
        if mujer.embarazo or self.t < mujer.sin_concebir_hasta:
            return False, "%s no puede tener un hijo ahora." % mujer.nombre
        padre = o if mujer is h else h
        mujer.embarazo = {"padre_id": padre.id, "parto_t": self.t + GESTACION_MIN}
        # Fase 8: compromiso formal
        h.pareja_id = o.id
        o.pareja_id = h.id
        self._evento("familia", "%s y %s decidieron formar una familia." % (h.nombre, o.nombre), h, importancia=4,
                     datos={"a": h.id, "b": o.id})
        for a, b in ((h, o), (o, h)):
            self._recuerdo(a, "Vos y %s decidieron formar una familia." % b.nombre, 0.95)
            self._evento("_relacion", "", a, datos={"hab": a.id, "otro": b.id, "d_afecto": 0.2, "d_confianza": 0.2,
                                                    "motivo": "decidieron formar una familia"})
        h.accion, h.detalle, h.hasta = "hablando", "con %s" % o.nombre, self.t + 5.0
        o.accion, o.detalle, o.hasta = "hablando", "con %s" % h.nombre, self.t + 5.0
        return True, "Aceptaste: vos y %s van a formar una familia." % o.nombre

    def _accion_ensenar(self, h, it: dict) -> Tuple[bool, str]:
        if not self.modulo("conocimientos"):
            return False, "Enseñar no está habilitado."
        o = self.habitantes.get(int(it.get("a", -1)))
        cid = it.get("conocimiento")
        if o is None or not o.vivo:
            return False, "Esa persona no está."
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            cid = next((k for k, v in self.conocimientos.items() if v["nombre"].lower() == str(cid).lower()), None)
        if cid not in h.conoce:
            return False, "No sabés eso, no lo podés enseñar."
        if _dist(h, o) > self.r_habla:
            return False, "%s está demasiado lejos." % o.nombre
        if cid in o.conoce:
            return False, "%s ya lo sabe." % o.nombre
        o.conoce.add(cid)
        o.novedad_t = self.t
        nombre = self.conocimientos[cid]["nombre"]
        self._evento("_aprende", "", o, datos={"hab": o.id, "conocimiento": cid, "de": h.id})
        self._evento("ensenanza", "%s le enseñó a %s: «%s»." % (h.nombre, o.nombre, nombre), h, importancia=3,
                     datos={"maestro": h.id, "alumno": o.id, "conocimiento": cid})
        self._recuerdo(h, "Le enseñaste «%s» a %s." % (nombre, o.nombre), 0.6)
        self.experiencia(h, "ensenar")
        self._recuerdo(o, "%s te enseñó «%s»." % (h.nombre, nombre), 0.8, "semantica")
        self._evento("_relacion", "", o, datos={"hab": o.id, "otro": h.id, "d_afecto": 0.05, "d_confianza": 0.1,
                                                "motivo": "le enseñó algo"})
        o.camino, o.hasta, o.accion, o.detalle = [], self.t + 5.0, "hablando", "aprende de %s" % h.nombre
        h.accion, h.detalle, h.hasta = "hablando", "enseña a %s" % o.nombre, self.t + 5.0
        return True, "Le enseñaste «%s» a %s." % (nombre, o.nombre)

    def _accion_inventar(self, h, it: dict) -> Tuple[bool, str]:
        if not self.modulo("conocimientos"):
            return False, "Inventar no está habilitado."
        h.ultima_idea_t = self.t
        r = it.get("receta") or {}
        nombre = str(r.get("nombre", "")).strip()
        mats = [str(m).strip().lower() for m in (r.get("materiales") or [])]
        prop = str(r.get("propiedad", "")).strip().lower()
        existente = next((k for k, v in self.conocimientos.items() if v["nombre"].lower() == nombre.lower()), None)
        if existente is not None:
            if existente in h.conoce:
                return False, "Eso ya lo sabés."
            h.conoce.add(existente)
            self._evento("_aprende", "", h, datos={"hab": h.id, "conocimiento": existente, "de": None})
            self._recuerdo(h, "Descubriste por tu cuenta «%s»." % nombre, 0.8, "semantica")
            return True, "Descubriste por tu cuenta «%s»." % nombre
        ok, motivo = conocimiento.validar(self.reglas, nombre, mats, prop)
        if not ok:
            self._recuerdo(h, "Probaste «%s» y no funcionó: %s" % (nombre, motivo), 0.4)
            h.accion, h.detalle, h.hasta = "esperando", "prueba una idea", self.t + 10.0
            return False, motivo
        desc = str(r.get("descripcion", ""))[:200]
        rec = catalogos.buscar_receta(self.recetas, mats, prop)
        origen, rid = "inventada", None
        if rec is not None:
            origen, rid, nombre = "catalogo", rec["id"], rec["nombre"]
            desc = desc or rec.get("descripcion", "")
            ya = next((k for k, v in self.conocimientos.items() if v.get("receta_id") == rid), None)
            if ya is not None:                       # ya existía en el mundo: lo redescubre
                if ya in h.conoce:
                    return False, "Eso ya lo sabés."
                h.conoce.add(ya)
                self._evento("_aprende", "", h, datos={"hab": h.id, "conocimiento": ya, "de": None})
                self._recuerdo(h, "Descubriste por tu cuenta «%s»." % nombre, 0.8, "semantica")
                return True, "Descubriste por tu cuenta «%s»." % nombre
        if rid is None:
            rid = self.receta_de_invento(nombre, mats, prop, desc)    # que se pueda fabricar, no solo "saber"
        if self.al_inventar is not None:
            cid = self.al_inventar(self, h, nombre, mats, prop, desc, origen, rid)
        else:
            cid = max(self.conocimientos, default=0) + 1
        self.conocimientos[cid] = {"nombre": nombre, "materiales": mats, "propiedad": prop, "descripcion": desc,
                                   "creador_id": h.id, "origen": origen, "receta_id": rid, "t_min": int(self.t)}
        h.conoce.add(cid)
        verbo = "descubrió cómo hacer" if origen == "catalogo" else "inventó"
        self._evento("descubrimiento", "%s %s «%s» (%s). %s" % (h.nombre, verbo, nombre, ", ".join(mats), motivo),
                     h, importancia=4, causa="idea comprobada con las reglas de materiales",
                     datos={"conocimiento": cid, "materiales": mats, "propiedad": prop, "origen": origen, "receta": rid})
        self._recuerdo(h, "Descubriste «%s»: %s" % (nombre, motivo), 0.95, "semantica")
        self.sentir(h, "alegria", 0.4)
        self.experiencia(h, "inventar")
        h.novedad_t = self.t
        h.accion, h.detalle, h.hasta = "esperando", "prueba su idea", self.t + 15.0
        return True, "Descubriste «%s»." % nombre

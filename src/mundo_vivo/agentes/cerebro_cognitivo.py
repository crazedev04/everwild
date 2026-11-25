"""Puente entre Mundo Vivo y Cognitive Engine.

El motor cognitivo vive en otro proyecto (`/home/cracken/Mimundo/Cognitive Engine`) y no puede
importar nada de acá: esa es su regla fundacional, y es lo que le permite manejar los NPC de
cualquier proyecto. **El NPC se amolda al cerebro**, así que toda la traducción vive en este archivo.

Cómo está armado:

- **Un cerebro por habitante**, con personalidad derivada del genoma.
- **Necesidades**: las cuatro del cuerpo (sed, hambre, energía, salud) más tres que empujan la vida
  social y técnica (compañía, calor, herramientas). Las del cuerpo usan curva cuadrática —no
  molestan hasta que aprietan, y entonces explotan—; las otras usan curva lineal, que tira parejo.
- **Creencias de dominio**: en vez de un «hay un recurso visible» genérico, el puente le pasa al
  planificador el estado real del mundo (hay agua al lado, llevo algo crudo, hay fuego al alcance,
  tengo con qué sacar chispa, hay una presa cerca, alguien a quien hablarle...).
- **Capacidades**: las 20 acciones que el motor sabe ejecutar, cada una con precondiciones y
  efectos. El planificador GOAP encadena lo que haga falta. **Ninguna secuencia está escrita acá**:
  cazar → cocinar → comer sale de que cazar deja carne cruda, cocinar pide carne cruda y fuego, y
  comer pide comida en mano.

Lo que NO hace: el cerebro nunca toca el mundo. Propone; `Simulacion._aplicar` valida y ejecuta.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

from mundo_vivo.motor.simulacion import (
    SED_DESPIERTA,
    Cerebro,
    CerebroDemo,
    HabitanteSim,
    Simulacion,
)

# --------------------------------------------------------------------- necesidades
SED = "sed"
HAMBRE = "hambre"
ENERGIA = "energia"
SALUD = "salud"
CALOR = "calor"
COMPANIA = "compania"
HERRAMIENTAS = "herramientas"
FAMILIA = "familia"
CURIOSIDAD = "curiosidad"

CUERPO = (SED, HAMBRE, ENERGIA, SALUD, CALOR)

# Desde dónde cada necesidad del cuerpo empieza a reclamar atención (en la escala de Mundo Vivo).
UMBRAL_SED = 55.0
UMBRAL_HAMBRE = 60.0
UMBRAL_ENERGIA = 30.0
UMBRAL_SALUD = 45.0
UMBRAL_FRIO = 0.65

# Cuánto aguanta sin hablar con nadie antes de que la compañía pese del todo. Medio día del mundo
# para alguien de sociabilidad media; el rasgo lo acorta o lo alarga.
MINUTOS_SIN_CHARLA = 720.0
# Cuánto aguanta sin novedades o descubrimientos antes de que la curiosidad / aburrimiento empuje.
MINUTOS_SIN_NOVEDAD = 1440.0

# Las necesidades que no son del cuerpo nunca son "críticas": empujan de a poco y pierden siempre
# contra la sed. Un umbral negativo es la forma de decir eso sin tocar el motor.
NUNCA_CRITICA = -1.0

# --------------------------------------------------------------------- creencias
AGUA_AL_LADO = "agua_al_lado"
AGUA_CONOCIDA = "agua_conocida"
COMIDA_EN_MANO = "comida_en_mano"
COMIDA_JUNTABLE = "comida_juntable"
CRUDO_EN_MANO = "crudo_en_mano"
PRESA_CERCA = "presa_cerca"
FUEGO_AL_ALCANCE = "fuego_al_alcance"
FUEGO_CONOCIDO = "fuego_conocido"
CHISPA_Y_LENA = "chispa_y_lena"
PALO_EN_MANO = "palo_en_mano"
ANTORCHA_EN_MANO = "antorcha_en_mano"
PERSONA_CERCA = "persona_cerca"
PERSONA_LEJOS = "persona_lejos"
PROPUESTA_PENDIENTE = "propuesta_pendiente"
PAREJA_POSIBLE = "pareja_posible"
PAREJA_LEJOS = "pareja_lejos"
PUEDE_DORMIR = "puede_dormir"
ALGO_PARA_ENSENAR = "algo_para_ensenar"
RECETA_LISTA = "receta_lista"
MATERIAL_AQUI = "material_aqui"
PUEDE_INVENTAR = "puede_inventar"
OBJETO_USABLE = "objeto_usable"
ANIMAL_MONTABLE = "animal_montable"
MONTADO = "montado"
PASAJE_CERCA = "pasaje_cerca"
ABRIGO_PUESTO = "abrigo_puesto"

METROS_VISTA_SOCIAL = 60.0


def _ruta_motor_cognitivo() -> Optional[Path]:
    """Busca el código de Cognitive Engine sin asumir que está instalado.

    Orden: la variable `COGNITIVE_ENGINE_SRC`, y si no está, una carpeta hermana del repo.
    """
    desde_entorno = os.environ.get("COGNITIVE_ENGINE_SRC")
    if desde_entorno:
        p = Path(desde_entorno)
        return p if p.is_dir() else None

    raiz = Path(__file__).resolve().parents[3]          # .../mundo-vivo
    for nombre in ("Cognitive Engine", "cognitive-engine", "cognitive_engine"):
        candidato = raiz.parent / nombre / "src"
        if candidato.is_dir():
            return candidato
    return None


def motor_cognitivo_disponible() -> bool:
    """Indica si se puede importar el motor cognitivo en este entorno."""
    try:
        import cognitive_engine  # noqa: F401

        return True
    except ImportError:
        ruta = _ruta_motor_cognitivo()
        if ruta is None:
            return False
        if str(ruta) not in sys.path:
            sys.path.insert(0, str(ruta))
        try:
            import cognitive_engine  # noqa: F401

            return True
        except ImportError:
            return False


ATRIBUTO_RECETAS_INVENTAR = "_cog_recetas_inventar"


def _recetas_para_inventar(sim: Simulacion) -> tuple:
    """Recetas ordenadas, con nombre, propiedad e ingredientes ya en lista y en conjunto.

    El catálogo no cambia mientras el mundo corre, así que esto se arma una sola vez y queda
    colgado de la propia simulación. Es la misma idea que el resto del motor
    (`_compilar_materiales`, `_compilar_conservacion`): lo que se puede compilar una vez no se
    recalcula en el bucle. Antes `_idea_para_probar` re-ordenaba las ~190 recetas y volvía a
    convertir sus ingredientes en cada decisión de cada habitante.

    Va colgado de `sim` y no en un diccionario del módulo a propósito: una tabla indexada por
    `id(sim)` sobrevive a la simulación que la pidió, y Python recicla los ids, así que un mundo
    nuevo podría recibir el catálogo de uno viejo.
    """
    guardado = getattr(sim, ATRIBUTO_RECETAS_INVENTAR, None)
    if guardado is not None and guardado[0] == len(sim.recetas):
        return guardado[1]
    tabla = []
    for rid, receta in sorted(sim.recetas.items()):
        lista = tuple(str(m).lower() for m in receta.get("ingredientes", ()))
        if not lista:
            continue
        tabla.append((rid, receta.get("nombre", rid), receta.get("propiedad", ""),
                      lista, frozenset(lista)))
    congelada = tuple(tabla)
    setattr(sim, ATRIBUTO_RECETAS_INVENTAR, (len(sim.recetas), congelada))
    return congelada


class CerebroCognitivo(Cerebro):
    """Cerebro de los habitantes delegado a Cognitive Engine (sin LLM, determinista).

    Cumple la misma interfaz que `CerebroHibrido`: `decidir`, `registrar_resultado`, `estado` y
    `pendientes`, así que el motor no distingue uno de otro.
    """

    nombre = "cognitive engine (GOAP + utility AI, sin modelo)"

    def __init__(self, con=None) -> None:
        """`con` es la base del mundo. Si viene, cada decisión queda registrada en `decisiones`,
        que es de donde el visor saca «Lo que pensó». Sin base, el cerebro funciona igual pero el
        panel queda vacío."""
        if not motor_cognitivo_disponible():
            raise RuntimeError(
                "No se encontró Cognitive Engine. Poné su carpeta `src` en la variable de entorno "
                "COGNITIVE_ENGINE_SRC o dejá el proyecto como carpeta hermana de mundo-vivo."
            )
        from cognitive_engine import SQLiteBrainRepository
        from cognitive_engine.scheduler.scheduler import MultiBrainScheduler

        self.cliente = None                 # no hay modelo de lenguaje en este cerebro
        self.con = con
        self._demo = CerebroDemo()          # sólo para el reflejo de huir del fuego
        self._repo = SQLiteBrainRepository(":memory:")
        self._scheduler = MultiBrainScheduler()
        self._cerebros: dict[int, Any] = {}
        self._ultima_propuesta: dict[int, Any] = {}
        self._decisiones = 0
        self._sin_traducir: dict[str, int] = {}
        self._anotaciones_fallidas = 0
        self._ultimo_error_anotando = ""
        self._ultima_charla: dict[int, float] = {}
        self._charlas = 0
        # Las creencias de la decisión que se está resolviendo, por habitante: {id: (t, creencias)}.
        # `_anotar_decision` las necesita para el registro de entrenamiento y antes las volvía a
        # calcular, o sea el doble de la consulta más cara del puente por cada decisión de cada
        # habitante. Ver `_creencias_de_la_decision`.
        self._creencias_vigentes: dict[int, tuple[float, dict[str, Any]]] = {}

    # ------------------------------------------------------------------ catálogo

    @staticmethod
    def _catalogo() -> Any:
        """Las 20 acciones del motor como capacidades GOAP, con precondiciones y efectos.

        `needs` dice para qué objetivo sirve cada una: así `dormir` no compite por saciar el hambre
        y no hace falta ningún `if` de contenido en el motor cognitivo. Las que no declaran `needs`
        sirven para cualquier objetivo, y el planificador las usa sólo si su efecto hace falta.
        """
        from cognitive_engine.decision.capabilities import (
            IDLE,
            NEED_SATISFIED,
            NOVELTY,
            SOCIAL_CONTACT,
            ActionCatalog,
            Capability,
        )

        c = ActionCatalog()

        def reg(nombre, pre, efec, costo, necesidades=frozenset()):
            c.register(
                Capability(
                    name=nombre,
                    preconditions=pre,
                    effects=efec,
                    cost=costo,
                    needs=necesidades,
                )
            )

        # --- sed
        reg("beber", {AGUA_AL_LADO: True}, {NEED_SATISFIED: True}, 1.0, frozenset({SED}))
        reg("ir_al_agua", {AGUA_CONOCIDA: True}, {AGUA_AL_LADO: True}, 2.0, frozenset({SED}))

        # --- hambre: comer, y las tres formas de conseguir algo que comer
        reg("comer", {COMIDA_EN_MANO: True}, {NEED_SATISFIED: True}, 1.0, frozenset({HAMBRE}))
        reg("juntar_comida", {COMIDA_JUNTABLE: True}, {COMIDA_EN_MANO: True}, 2.0, frozenset({HAMBRE}))
        reg("cazar", {PRESA_CERCA: True}, {CRUDO_EN_MANO: True}, 4.0, frozenset({HAMBRE}))
        reg(
            "cocinar",
            {CRUDO_EN_MANO: True, FUEGO_AL_ALCANCE: True},
            {COMIDA_EN_MANO: True},
            2.0,
            frozenset({HAMBRE}),
        )
        reg("curar_carne", {CRUDO_EN_MANO: True}, {COMIDA_EN_MANO: True}, 3.0, frozenset({HAMBRE}))

        # --- energía y salud (siempre que la sed no esté a nivel de inanición)
        reg("dormir", {PUEDE_DORMIR: True}, {NEED_SATISFIED: True}, 1.0, frozenset({ENERGIA, SALUD}))

        # --- calor: hacer fuego, llevárselo, o acercarse al que ya hay.
        # Conseguir fuego NO satisface ninguna necesidad por sí mismo: es un medio. Lo que calienta
        # es quedarse al lado (`calentarse`). Si `encender` declarara `need_satisfied`, el
        # planificador habría «comido» prendiendo una fogata.
        reg("encender", {CHISPA_Y_LENA: True}, {FUEGO_AL_ALCANCE: True}, 3.0,
            frozenset({CALOR, HAMBRE}))
        reg("ir_al_fuego", {FUEGO_CONOCIDO: True}, {FUEGO_AL_ALCANCE: True}, 2.0,
            frozenset({CALOR, HAMBRE}))
        reg("calentarse", {FUEGO_AL_ALCANCE: True}, {NEED_SATISFIED: True}, 0.5,
            frozenset({CALOR}))
        reg(
            "tomar_fuego",
            {FUEGO_AL_ALCANCE: True, PALO_EN_MANO: True},
            {ANTORCHA_EN_MANO: True},
            1.5,
            frozenset({CALOR}),
        )

        # --- compañía: hablar, buscar, enseñar
        reg("hablar", {PERSONA_CERCA: True}, {NEED_SATISFIED: True, SOCIAL_CONTACT: True}, 1.0,
            frozenset({COMPANIA}))
        reg("ir_hacia", {PERSONA_LEJOS: True}, {PERSONA_CERCA: True}, 2.0, frozenset({COMPANIA}))
        reg("buscar", {PERSONA_LEJOS: True}, {PERSONA_CERCA: True}, 3.0, frozenset({COMPANIA}))
        reg(
            "ensenar",
            {PERSONA_CERCA: True, ALGO_PARA_ENSENAR: True},
            {NEED_SATISFIED: True, SOCIAL_CONTACT: True},
            0.8,
            frozenset({COMPANIA, CURIOSIDAD}),
        )

        # --- familia y reproducción: desear descendencia impulsa buscar pareja y proponer
        reg(
            "proponer_hijo",
            {PERSONA_CERCA: True, PAREJA_POSIBLE: True},
            {NEED_SATISFIED: True, SOCIAL_CONTACT: True},
            1.2,
            frozenset({FAMILIA, COMPANIA}),
        )
        reg(
            "ir_hacia_pareja",
            {PAREJA_LEJOS: True},
            {PERSONA_CERCA: True, PAREJA_POSIBLE: True},
            2.0,
            frozenset({FAMILIA}),
        )
        reg(
            "buscar_pareja",
            {PAREJA_LEJOS: True},
            {PERSONA_CERCA: True, PAREJA_POSIBLE: True},
            3.0,
            frozenset({FAMILIA}),
        )
        # Contestar lo que alguien preguntó/propuso es casi un reflejo: el costo más bajo del catálogo.
        reg("responder_propuesta", {PROPUESTA_PENDIENTE: True}, {NEED_SATISFIED: True}, 0.2,
            frozenset({COMPANIA, FAMILIA}))

        # --- herramientas, técnica y curiosidad
        reg("fabricar", {RECETA_LISTA: True}, {NEED_SATISFIED: True}, 1.5, frozenset({HERRAMIENTAS}))
        reg("juntar_material", {MATERIAL_AQUI: True}, {RECETA_LISTA: True}, 2.0,
            frozenset({HERRAMIENTAS}))
        reg("juntar_para_inventar", {MATERIAL_AQUI: True}, {PUEDE_INVENTAR: True}, 2.2,
            frozenset({CURIOSIDAD, HERRAMIENTAS}))
        reg("inventar", {PUEDE_INVENTAR: True}, {NEED_SATISFIED: True, RECETA_LISTA: True, NOVELTY: True}, 1.5,
            frozenset({HERRAMIENTAS, CURIOSIDAD}))
        # `usar` en este motor es sólo curarse, así que cuelga de la salud y de nada más.
        reg("usar", {OBJETO_USABLE: True}, {NEED_SATISFIED: True}, 1.0, frozenset({SALUD}))

        # --- moverse por el mundo (sirven para cualquier objetivo que necesite su efecto)
        reg("montar", {ANIMAL_MONTABLE: True}, {MONTADO: True}, 2.0)
        reg("desmontar", {MONTADO: True}, {MONTADO: False}, 0.5)
        reg("atravesar", {PASAJE_CERCA: True}, {NOVELTY: True}, 3.0)

        # Explorar vuelve alcanzable lo que todavía no se conoce. Es optimista a propósito: si no
        # aparece nada, el plan se cae, se replanifica y la pericia aprendida lo encarece.
        reg(
            "explorar",
            {},
            {
                NOVELTY: True,
                AGUA_CONOCIDA: True,
                COMIDA_JUNTABLE: True,
                PRESA_CERCA: True,
                MATERIAL_AQUI: True,
                PERSONA_LEJOS: True,
                FUEGO_CONOCIDO: True,
            },
            5.0,
        )
        reg("esperar", {}, {IDLE: True}, 0.5)
        return c

    # ------------------------------------------------------------------ cerebros

    def _personalidad(self, h: HabitanteSim) -> Any:
        """Deriva los rasgos del motor cognitivo desde el genoma del habitante."""
        from cognitive_engine import PersonalityTraits

        # Los rasgos del genoma son los de `agentes/genoma.py`: la persistencia sale de la
        # resiliencia, que es lo más cerca que hay de "no abandonar lo que empezó".
        curiosidad = float(h.rasgo("curiosidad"))
        cautela = float(h.rasgo("cautela"))
        sociabilidad = float(h.rasgo("sociabilidad"))
        persistencia = float(h.rasgo("resiliencia"))

        # Si está bajo efecto de una planta psicoactiva / hongo alucinógeno, modula rasgos temporalmente
        viaje = getattr(h, "viaje", None)
        if viaje and "rasgos" in viaje:
            v_rasgos = viaje["rasgos"]
            curiosidad = max(0.05, min(0.95, curiosidad + float(v_rasgos.get("curiosidad", 0.0))))
            cautela = max(0.05, min(0.95, cautela + float(v_rasgos.get("cautela", 0.0))))
            sociabilidad = max(0.05, min(0.95, sociabilidad + float(v_rasgos.get("sociabilidad", 0.0))))

        return PersonalityTraits(
            curiosity=curiosidad,
            cautiousness=cautela,
            sociability=sociabilidad,
            persistence=persistencia,
        )

    def _necesidades(self, sim: Simulacion, h: HabitanteSim) -> Any:
        """Traduce el cuerpo y la situación a necesidades 0 (crítica) .. 100 (saciada)."""
        from cognitive_engine import Need, NeedsSystem

        frio = float(getattr(h, "frio", 0.0)) if sim.modulo("frio") else 0.0
        tiene_herramienta = any(sim.tiene(h, a) for a in sorted(sim.armas)) if sim.armas else False
        ganas_familia = self._ganas_de_familia(sim, h)
        # La salud no se atiende sola: se arregla arreglando lo que la está bajando. Sus únicas dos
        # capacidades son `dormir`, que el motor PROHÍBE con sed alta (`PUEDE_DORMIR`, para que nadie
        # se duerma y se muera de sed), y `usar`, que pide llevar un remedio encima. Si la sed ya pasó
        # el umbral de despertarse y no hay remedio, declarar la salud como crítica le gana la puja a
        # `satisfy_sed` y deja al planificador sin ningún plan posible: devuelve `wait`, el motor
        # espera, la sed sigue subiendo y la persona se muere al lado del agua.
        #
        # Medido en el mundo `gaia` antes de este arreglo: de 484 decisiones con sed ≥ 80, el 57,6%
        # fueron `wait` y el 73% no tenían plan; el objetivo elegido fue `satisfy_salud` el 48% de
        # las veces contra `satisfy_sed` el 41%. 23 de las 27 muertes del mundo fueron de sed, y 13
        # de los muertos tenían el agua pegada al cuerpo. Ver `docs/MUERTE_POR_SED.md`.
        salud_atendible = h.sed < SED_DESPIERTA or self._objeto_usable(sim, h) is not None
        # La sed pasada del umbral manda sobre todo lo que mata más despacio.
        #
        # El árbitro del motor cognitivo ordena los objetivos por `urgency`, que es cuán VACÍA está
        # la necesidad (`(max - valor) / max`), y no tiene —ni tiene por qué tener— idea de cuán
        # rápido mata cada una: eso es conocimiento del mundo y vive acá. El resultado era que con
        # sed 85 y hambre 90 ganaba el hambre, por 5 puntos de «vacío».
        #
        # Lo que dice el motor, medido: la sed a 100 saca 0,3 de salud por minuto, o sea mata en
        # **5,5 horas**; el hambre a 100 saca 0,035, o sea **2 días**; el frío extremo saca 0,02, o
        # sea 3,5 días; y la energía no mata sola. La sed mata 8,6 veces más rápido que el hambre.
        # Así que mientras la sed sea mortal, las otras no pueden declararse críticas y disputarle
        # la puja. Es la regla de «lo que mata más rápido va primero» de CLAUDE.md, puesta donde el
        # árbitro la puede ver.
        #
        # Medido en un mundo nuevo antes de este arreglo: de 68 decisiones con sed ≥ 80, el 72%
        # eligió `cazar` para `satisfy_hambre` y sólo el 12% `beber`.
        sed_manda = h.sed >= SED_DESPIERTA
        def umbral_lento(umbral: float) -> float:
            return NUNCA_CRITICA if sed_manda else umbral

        def need(nombre, valor, umbral):
            return Need(
                name=nombre,
                value=max(0.0, min(100.0, valor)),
                decay_rate=0.0,            # el cuerpo lo lleva Mundo Vivo, no el cerebro
                critical_threshold=umbral,
            )

        return NeedsSystem(
            needs={
                SED: need(SED, 100.0 - float(h.sed), 100.0 - UMBRAL_SED),
                HAMBRE: need(HAMBRE, 100.0 - float(h.hambre), umbral_lento(100.0 - UMBRAL_HAMBRE)),
                ENERGIA: need(ENERGIA, float(h.energia), umbral_lento(UMBRAL_ENERGIA)),
                SALUD: need(SALUD, max(0.0, float(h.salud)),
                            UMBRAL_SALUD if salud_atendible else NUNCA_CRITICA),
                CALOR: need(CALOR, 100.0 - 100.0 * frio,
                            umbral_lento(100.0 - 100.0 * UMBRAL_FRIO)),
                COMPANIA: need(COMPANIA, self._compania_de(sim, h), NUNCA_CRITICA),
                HERRAMIENTAS: need(
                    HERRAMIENTAS, 100.0 if tiene_herramienta else 35.0, NUNCA_CRITICA
                ),
                FAMILIA: need(
                    FAMILIA, max(0.0, 100.0 - 50.0 * ganas_familia), NUNCA_CRITICA
                ),
                CURIOSIDAD: need(
                    CURIOSIDAD, self._curiosidad_de(sim, h), NUNCA_CRITICA
                ),
            }
        )

    @staticmethod
    def _ganas_de_familia(sim: Simulacion, h: HabitanteSim) -> float:
        """0..2: cuánto desea formar una familia. Crece con los días de adulto sin hijo."""
        if not sim.modulo("reproduccion") or not sim.es_adulto(h) or h.embarazo:
            return 0.0
        adulta_desde = h.nacimiento_min + 12 * 120 * 1440.0
        dias = (sim.t - max(adulta_desde, getattr(h, "sin_concebir_hasta", 0.0))) / 1440.0
        return max(0.0, min(2.0, (dias / 20.0) * (0.6 + 0.8 * float(h.rasgo("sociabilidad")))))

    @classmethod
    def _curiosidad_de(cls, sim: Simulacion, h: HabitanteSim) -> float:
        """Cuánta curiosidad/aburrimiento técnico siente.

        Baja cuando pasa tiempo sin descubrir ni inventar nada nuevo.
        El rasgo 'curiosidad' del genoma modula la velocidad de decaimiento.
        """
        ultima = getattr(h, "novedad_t", None)
        if ultima is None or ultima <= 0:
            ultima = getattr(h, "ultima_idea_t", None)
        if ultima is None or ultima <= 0:
            ultima = float(h.nacimiento_min)

        rasgo = max(0.2, float(h.rasgo("curiosidad")))
        aguante = MINUTOS_SIN_NOVEDAD / rasgo
        pasado = max(0.0, float(sim.t) - ultima)
        return max(0.0, 100.0 - 100.0 * min(1.0, pasado / aguante))

    def _compania_de(self, sim: Simulacion, h: HabitanteSim) -> float:
        """Cuánta compañía le falta, según hace cuánto que no habla con nadie.

        El error que esto arregla: antes alcanzaba con tener a alguien al lado para que la necesidad
        estuviera llena, así que dos personas podían pasar meses juntas **sin hablarse nunca**. La
        compañía no se satisface por cercanía; se satisface interactuando.
        """
        ultima = self._ultima_charla.get(h.id)
        if ultima is None:
            ultima = float(h.nacimiento_min)
        aguante = MINUTOS_SIN_CHARLA / max(0.25, 0.5 + float(h.rasgo("sociabilidad")))
        pasado = max(0.0, float(sim.t) - ultima)
        return max(0.0, 100.0 - 100.0 * min(1.0, pasado / aguante))

    def _cerebro_de(self, sim: Simulacion, h: HabitanteSim) -> Any:
        """Devuelve el cerebro del habitante, creándolo la primera vez."""
        existente = self._cerebros.get(h.id)
        if existente is not None:
            return existente

        from cognitive_engine import AffordanceIndex, AutonomousBrain, BrainIdentity
        from cognitive_engine.core.ids import DeterministicIdFactory
        from cognitive_engine.decision.engine import GOAPDecisionEngine
        from cognitive_engine.decision.goal_selection import GoalArbiter
        from cognitive_engine.decision.utility import CurveType, UtilityCurve

        # El piso del reposo baja de 0,5 (el default del motor) a 0,3: con 0,5, los impulsos que no
        # son del cuerpo nunca ganaban y los habitantes se quedaban sentados con el agua ya bebida,
        # sin fabricar ni buscar a nadie. Este número es del anfitrión, no del motor: define cuánto
        # tolera el quedarse quieto una persona de ESTE mundo.
        arbitro = GoalArbiter(idle_utility=0.3)
        # Las necesidades que no son del cuerpo tiran parejo en vez de explotar al final: la
        # compañía, las herramientas, la curiosidad y la familia se atienden cuando sobra lugar.
        for secundaria in (COMPANIA, HERRAMIENTAS, FAMILIA, CURIOSIDAD):
            arbitro.set_curve(secundaria, UtilityCurve(curve_type=CurveType.LINEAR, slope=0.7))

        identidad = BrainIdentity(
            brain_id=f"{sim.ident}:d{sim.dimension}:h{h.id}",
            name=h.nombre,
            created_tick=int(h.nacimiento_min),
        )
        cerebro = AutonomousBrain(
            identity=identidad,
            personality=self._personalidad(h),
            needs=self._necesidades(sim, h),
            decision_engine=GOAPDecisionEngine(
                arbiter=arbitro,
                catalog=self._catalogo(),
                # Mundo Vivo resuelve las affordances con su propio mapa y sus datos, así que el
                # índice por palabras va vacío a propósito.
                affordances=AffordanceIndex(),
            ),
            id_factory=DeterministicIdFactory(namespace=identidad.brain_id),
        )
        self._cerebros[h.id] = cerebro
        self._scheduler.register_brain(cerebro)
        return cerebro

    def olvidar(self, h_id: int) -> None:
        """Archiva el cerebro de alguien que murió."""
        cerebro = self._cerebros.pop(h_id, None)
        self._ultima_propuesta.pop(h_id, None)
        self._creencias_vigentes.pop(h_id, None)
        self._ultima_charla.pop(h_id, None)   # si no, queda una entrada por cada muerto, para siempre
        if cerebro is not None:
            self._scheduler.unregister_brain(cerebro.identity.brain_id)

    # ------------------------------------------------------------------ percepción

    def _observacion(self, sim: Simulacion, h: HabitanteSim, cerebro: Any) -> Any:
        """Arma la observación: posición propia, agua a la vista y gente cerca, en metros reales."""
        from cognitive_engine import Observation, PerceivedFact

        hechos: list[Any] = [
            PerceivedFact(
                subject=cerebro.identity.brain_id,
                predicate="position",
                value=(float(h.x), float(h.y)),
                confidence=1.0,
            )
        ]

        agua = self._agua_alcanzable(sim, h)
        if agua is not None:
            hechos.append(
                PerceivedFact(
                    subject="agua",
                    predicate="fuente",
                    value="agua",
                    confidence=1.0,
                    metadata={"satisfies": [SED], "position": (float(agua[0]), float(agua[1]))},
                )
            )

        fogata = sim.fogata_cerca(h, sim.celdas(400.0))
        if fogata is not None:
            hechos.append(
                PerceivedFact(
                    subject="fuego",
                    predicate="fuente",
                    value="fuego",
                    confidence=1.0,
                    metadata={
                        "satisfies": [CALOR],
                        "position": (float(fogata["x"]), float(fogata["y"])),
                    },
                )
            )

        for otro in sim.habitantes.values():
            if otro.id == h.id or not otro.vivo:
                continue
            if math.hypot(otro.x - h.x, otro.y - h.y) <= sim.celdas(METROS_VISTA_SOCIAL):
                hechos.append(
                    PerceivedFact(
                        subject=f"persona_{otro.id}",
                        predicate="presencia",
                        value=otro.nombre,
                        confidence=1.0,
                        metadata={
                            "satisfies": [COMPANIA],
                            "position": (float(otro.x), float(otro.y)),
                        },
                    )
                )

        return Observation(
            brain_id=cerebro.identity.brain_id, tick=int(sim.t), facts=tuple(hechos)
        )

    # ------------------------------------------------------------------ creencias

    def _creencias(self, sim: Simulacion, h: HabitanteSim) -> dict[str, Any]:
        """El estado del mundo que el planificador necesita, en claves booleanas.

        Se calcula entero en cada decisión. Es el costo del puente: `disponibles()`, `ausentes()` y
        `ver_animales()` son las tres consultas caras, las mismas que ya hace el respaldo del cerebro
        híbrido. Anotado en `docs/OPTIMIZACION.md`.
        """
        crudo = self._crudo_en_mano(sim, h)
        receta = self._receta_lista(sim, h)
        fuego_mano = sim.fogata_cerca(h, sim.r_mano) or sim.fuego_cerca(h, sim.r_mano)

        return {
            AGUA_AL_LADO: sim.terreno.agua_adyacente(int(h.x), int(h.y)),
            AGUA_CONOCIDA: self._agua_alcanzable(sim, h) is not None,
            COMIDA_EN_MANO: self._comida_en_mano(sim, h) is not None,
            COMIDA_JUNTABLE: self._comida_juntable(sim, h) is not None,
            CRUDO_EN_MANO: crudo is not None,
            PRESA_CERCA: self._presa_cerca(sim, h) is not None,
            FUEGO_AL_ALCANCE: fuego_mano is not None,
            FUEGO_CONOCIDO: sim.fogata_cerca(h, sim.celdas(400.0)) is not None,
            CHISPA_Y_LENA: (
                sim.fuente_de_chispa(h) is not None and sim.lena_que_lleva(h) >= 2
            ),
            PALO_EN_MANO: sim.tiene(h, "palo") or sim.tiene(h, "antorcha"),
            ANTORCHA_EN_MANO: sim.tiene(h, "antorcha_encendida"),
            # «Cerca» para el planificador significa **se le puede hablar ahora**, no sólo estar al
            # lado: el motor exige distancia de habla, que el otro esté despierto y 120 minutos de
            # espera entre charlas.
            PERSONA_CERCA: (
                sim.modulo("conversacion") and self._alguien_para_hablar(sim, h) is not None
            ),
            PERSONA_LEJOS: bool(self._alguien_lejos(sim, h)),
            PROPUESTA_PENDIENTE: bool(h.propuesta),
            PAREJA_POSIBLE: self._pareja_posible(sim, h) is not None,
            PAREJA_LEJOS: bool(self._pareja_lejos(sim, h)),
            ALGO_PARA_ENSENAR: self._algo_para_ensenar(sim, h) is not None,
            RECETA_LISTA: receta is not None,
            MATERIAL_AQUI: bool(sim.disponibles(h)),
            PUEDE_INVENTAR: (
                sim.modulo("conocimientos") and self._idea_para_probar(sim, h) is not None
            ),
            OBJETO_USABLE: self._objeto_usable(sim, h) is not None,
            ANIMAL_MONTABLE: self._animal_montable(sim, h) is not None,
            MONTADO: h.montura is not None,
            PASAJE_CERCA: self._pasaje_cerca(sim, h) is not None,
            ABRIGO_PUESTO: bool(sim.fogata_cerca(h, sim.r_mano)),
            PUEDE_DORMIR: h.sed < SED_DESPIERTA,
        }

    def _creencias_de_la_decision(self, sim: Simulacion, h: HabitanteSim) -> dict[str, Any]:
        """Las creencias con las que se tomó la decisión que se está anotando.

        Son las que ya calculó `decidir` en este mismo minuto; acá sólo se recuperan. Antes esto
        llamaba de nuevo a `_creencias()`, que es la consulta más cara del puente (`disponibles()`,
        `ausentes()`, `ver_animales()`), así que cada decisión de cada habitante la pagaba dos veces.

        Hay además un detalle que no es de rendimiento: `registrar_resultado` corre DESPUÉS de que el
        motor aplicó la acción, así que recalcularlas devolvía el mundo de después y no el de antes.
        Para entrenar un cerebro con pares (estado, acción) el estado que sirve es el de antes.
        """
        guardadas = self._creencias_vigentes.get(h.id)
        if guardadas is not None and abs(guardadas[0] - float(sim.t)) < 1e-9:
            return guardadas[1]
        return self._creencias(sim, h)

    # ------------------------------------------------------------- consultas al mundo

    @staticmethod
    def _agua_alcanzable(sim: Simulacion, h: HabitanteSim) -> Optional[tuple[int, int]]:
        """Agua al alcance, con la misma búsqueda que usa el resto del motor."""
        if sim.terreno.agua_adyacente(int(h.x), int(h.y)):
            return (int(h.x), int(h.y))
        return sim.agua_cercana(h, sim.r_agua_cerca) or sim.agua_cercana(h, sim.r_agua_lejos)

    @staticmethod
    def _comida_en_mano(sim: Simulacion, h: HabitanteSim) -> Optional[str]:
        """Algo comestible en el inventario. `sim.alimentos` es dato, no una lista del motor."""
        for objeto, cantidad in sorted(h.inventario.items()):
            if cantidad > 0 and objeto in sim.alimentos:
                return objeto
        return None

    @staticmethod
    def _comida_juntable(sim: Simulacion, h: HabitanteSim) -> Optional[str]:
        """Algo comestible que se pueda juntar acá mismo (mismo criterio que `objetivos.py`)."""
        for material in sorted(sim.disponibles(h)):
            if material in sim.alimentos:
                return material
        return None

    @staticmethod
    def _crudo_en_mano(sim: Simulacion, h: HabitanteSim) -> Optional[str]:
        """Algo crudo encima, que se puede cocinar o curar."""
        for crudo in sorted(sim.crudos):
            if h.inventario.get(crudo, 0) > 0:
                return crudo
        return None

    @staticmethod
    def _presa_cerca(sim: Simulacion, h: HabitanteSim) -> Optional[str]:
        """Un animal comestible a la vista."""
        if not sim.modulo_fauna():
            return None
        presas = [g for g in sim.ver_animales(h) if g.get("comestible")]
        if not presas:
            return None
        return str(sorted(presas, key=lambda g: g["nombre"])[0]["nombre"])

    @staticmethod
    def _animal_montable(sim: Simulacion, h: HabitanteSim) -> Optional[str]:
        """Un animal que se pueda montar, si el módulo está prendido."""
        if not sim.modulo_fauna() or h.montura is not None:
            return None
        montables = [g for g in sim.ver_animales(h) if g.get("montable")]
        if not montables:
            return None
        return str(sorted(montables, key=lambda g: g["nombre"])[0]["nombre"])

    @staticmethod
    def _alguien_cerca(sim: Simulacion, h: HabitanteSim) -> Optional[HabitanteSim]:
        """La persona viva más cercana dentro del campo social, en metros."""
        radio = sim.celdas(METROS_VISTA_SOCIAL)
        cerca = [
            o
            for o in sim.habitantes.values()
            if o.id != h.id and o.vivo and math.hypot(o.x - h.x, o.y - h.y) <= radio
        ]
        if not cerca:
            return None
        return min(cerca, key=lambda o: (math.hypot(o.x - h.x, o.y - h.y), o.id))

    @staticmethod
    def _alguien_para_hablar(sim: Simulacion, h: HabitanteSim) -> Optional[HabitanteSim]:
        """Alguien a quien de verdad se le puede hablar AHORA, con las reglas del motor.

        `_accion_hablar` pide estar dentro de `r_habla`, que el otro no esté durmiendo y que hayan
        pasado 120 minutos desde la última charla con esa persona (salvo que esté contestando). Si
        el puente no mira esto, el cerebro propone hablar contra una pared: el motor lo rechaza, la
        pericia de «hablar» se desploma y el planificador deja de intentarlo.
        """
        candidatos = []
        for o in sim.habitantes.values():
            if o.id == h.id or not o.vivo:
                continue
            if math.hypot(o.x - h.x, o.y - h.y) > sim.r_habla:
                continue
            if o.accion == "durmiendo" and sim.t < o.hasta:
                continue
            respondiendo = sim.t - h.oido_de.get(o.id, -1e9) <= 90.0
            if not respondiendo and sim.t - h.ultima_charla.get(o.id, -1e9) < 120.0:
                continue
            candidatos.append(o)
        if not candidatos:
            return None
        return min(candidatos, key=lambda o: (math.hypot(o.x - h.x, o.y - h.y), o.id))

    @staticmethod
    def _mensaje_para(sim: Simulacion, h: HabitanteSim, otro: HabitanteSim) -> Optional[dict]:
        """Algo concreto que decir, sacado de lo que esta persona sabe y vivió.

        El motor rechaza repetir casi lo mismo que ya se dijo (compara palabras contra las últimas
        tres frases), así que acá se arma una lista de cosas que de verdad tiene para contar y se
        descarta lo que se parece a lo último. Si no tiene nada nuevo que decir, **no habla**: eso
        es lo que el motor quiere, y es lo que haría cualquiera.
        """
        candidatos: list[tuple[str, str, float]] = []      # (mensaje, intención, impresión)

        for lugar in h.lugares.get("agua", [])[:2]:
            candidatos.append(
                (f"Hay agua en ({int(lugar[0])}, {int(lugar[1])}).", "contar", 0.3)
            )
        peligro = sim.fuego_cerca(h, sim.celdas(400.0))
        if peligro:
            candidatos.append(("Cuidado, hay fuego cerca de acá.", "advertir", -0.2))
        if h.frio > 0.5:
            candidatos.append(("Hace frío, conviene buscar reparo.", "advertir", -0.1))
        comida = CerebroCognitivo._comida_en_mano(sim, h)
        if comida:
            candidatos.append((f"Conseguí {comida} para comer.", "contar", 0.4))
        for cid in sorted(h.conoce)[:2]:
            nombre = sim.conocimientos.get(cid, {}).get("nombre")
            if nombre:
                candidatos.append((f"Aprendí a hacer {nombre}.", "contar", 0.5))
        if not h.lugares.get("agua"):
            candidatos.append(("¿Viste agua por acá?", "preguntar", 0.1))
        if h.hambre > 50:
            candidatos.append(("Tengo hambre, ¿sabés dónde conseguir comida?", "preguntar", 0.0))
        candidatos.append((f"Te vi por acá, {otro.nombre}.", "contar", 0.2))

        def palabras(texto: str) -> set:
            limpio = texto.lower().replace(",", " ").replace(".", " ").replace("¿", " ")
            return {w for w in limpio.split() if len(w) > 3}

        previos = [palabras(p) for p in h.historial_dicho[-3:]]
        ultimo = h.ultimo_dicho.get(otro.id)

        for mensaje, intencion, impresion in candidatos:
            if mensaje == ultimo:
                continue
            p = palabras(mensaje)
            if any(
                p and pp and len(p & pp) / max(1, len(p | pp)) > 0.55 for pp in previos
            ):
                continue
            return {
                "tipo": "hablar",
                "a": otro.id,
                "mensaje": mensaje,
                "intencion": intencion,
                "impresion": impresion,
            }
        return None

    @staticmethod
    def _alguien_lejos(sim: Simulacion, h: HabitanteSim) -> list:
        """Gente conocida que no está a la vista (lo que el motor llama `ausentes`)."""
        return sim.ausentes(h)

    @staticmethod
    def _candidatos_pareja(sim: Simulacion, h: HabitanteSim) -> list[HabitanteSim]:
        """Adultos vivos del otro sexo que no sean parientes cercanos y puedan tener un hijo."""
        if not sim.modulo("reproduccion") or not sim.es_adulto(h) or h.embarazo:
            return []
        candidatos = []
        for o in sim.habitantes.values():
            if o.id == h.id or not o.vivo or o.sexo == h.sexo or not sim.es_adulto(o):
                continue
            if sim.parentesco_cercano(h, o) is not None:
                continue
            mujer = h if h.sexo == "F" else o
            if mujer.embarazo or sim.t < getattr(mujer, "sin_concebir_hasta", 0.0):
                continue
            candidatos.append(o)
        return candidatos

    @classmethod
    def _pareja_posible(cls, sim: Simulacion, h: HabitanteSim) -> Optional[HabitanteSim]:
        """Alguien cerca con quien el motor permitiría tener un hijo."""
        radio = sim.celdas(METROS_VISTA_SOCIAL)
        candidatos = [o for o in cls._candidatos_pareja(sim, h) if math.hypot(o.x - h.x, o.y - h.y) <= radio]
        if not candidatos:
            return None
        return min(candidatos, key=lambda o: (math.hypot(o.x - h.x, o.y - h.y), o.id))

    @classmethod
    def _pareja_lejos(cls, sim: Simulacion, h: HabitanteSim) -> Optional[HabitanteSim]:
        """Alguien conocido o existente pero lejos con quien formar familia."""
        radio = sim.celdas(METROS_VISTA_SOCIAL)
        candidatos = [o for o in cls._candidatos_pareja(sim, h) if math.hypot(o.x - h.x, o.y - h.y) > radio]
        if not candidatos:
            return None
        return min(candidatos, key=lambda o: (math.hypot(o.x - h.x, o.y - h.y), o.id))

    @staticmethod
    def _algo_para_ensenar(sim: Simulacion, h: HabitanteSim) -> Optional[tuple[int, str]]:
        """Algo que esta persona sabe y la que tiene al lado (dentro de r_habla) no."""
        for o in sim.habitantes.values():
            if o.id == h.id or not o.vivo:
                continue
            if math.hypot(o.x - h.x, o.y - h.y) > sim.r_habla:
                continue
            if o.accion == "durmiendo" and sim.t < o.hasta:
                continue
            for conocimiento in sorted(h.conoce):
                if conocimiento not in o.conoce:
                    return (o.id, conocimiento)
        return None

    @staticmethod
    def _receta_lista(sim: Simulacion, h: HabitanteSim) -> Optional[str]:
        """Una receta que esta persona sabe y para la que ya tiene todo."""
        for rid, receta in sorted(sim.recetas.items()):
            if sim.puede_fabricar(h, receta):
                return rid
        return None

    @staticmethod
    def _material_para_recetas(sim: Simulacion, h: HabitanteSim) -> Optional[str]:
        """Un material juntable acá que aparezca en alguna receta que la persona sabe."""
        disponibles = sim.disponibles(h)
        if not disponibles:
            return None
        quiere: set[str] = set()
        for rid, receta in sim.recetas.items():
            if sim.sabe(h, rid):
                quiere.update(receta.get("ingredientes", ()))
        for material in sorted(disponibles):
            if material in quiere:
                return material
        # Si no sabe ninguna receta todavía, juntar lo que haya igual sirve para inventar.
        return sorted(disponibles)[0] if not quiere else None

    @staticmethod
    def _material_para_inventar(sim: Simulacion, h: HabitanteSim) -> Optional[str]:
        """Un material juntable acá para experimentar e inventar algo nuevo."""
        disponibles = sim.disponibles(h)
        if not disponibles:
            return None
        encima = {m for m, n in h.inventario.items() if n > 0}
        novedosos = [m for m in sorted(disponibles) if m not in encima]
        return novedosos[0] if novedosos else sorted(disponibles)[0]

    @staticmethod
    def _objeto_usable(sim: Simulacion, h: HabitanteSim) -> Optional[str]:
        """Un remedio en el inventario. `usar` en este motor es sólo curarse (`_accion_usar`)."""
        for rid, receta in sorted(sim.recetas.items()):
            if receta.get("propiedad") != "cura":
                continue
            resultado = (receta.get("resultado") or {}).get("item")
            if resultado and sim.tiene(h, resultado):
                return rid
        return None

    @staticmethod
    def _idea_para_probar(sim: Simulacion, h: HabitanteSim) -> Optional[dict]:
        """Una combinación para probar: materiales que la persona lleva encima.

        El cerebro propone juntar lo que tiene y el motor valida contra el catálogo
        (`_accion_inventar`). Si coincide con una receta, la descubre; si no,
        aprendió que eso no funciona.
        """
        encima = {m for m, n in h.inventario.items() if n > 0}
        if not encima:
            return None
        candidatas = []
        # El catálogo ordenado y con los ingredientes ya en conjunto se arma una sola vez
        # (`_recetas_para_inventar`). Antes se re-ordenaban las ~190 recetas y se recalculaban sus
        # ingredientes en cada decisión de cada habitante.
        for rid, nombre, propiedad, lista, conjunto in _recetas_para_inventar(sim):
            # Primero la prueba barata: casi ninguna receta se puede armar con lo que uno lleva
            # encima. `sabe()` recorre todo lo que la persona conoce, así que preguntarlo antes
            # costaba ~190 recorridos por decisión para descartar casi todo igual después.
            if not conjunto <= encima:
                continue
            if sim.sabe(h, rid):
                continue
            candidatas.append({
                "nombre": nombre,
                "materiales": list(lista),
                "propiedad": propiedad,
                "descripcion": "",
                "cant": len(lista),
            })
        if not candidatas:
            return None
        # Priorizar recetas que combinen más materiales (más complejas/avanzadas)
        candidatas.sort(key=lambda c: c["cant"], reverse=True)
        elegida = candidatas[0]
        return {
            "nombre": elegida["nombre"],
            "materiales": elegida["materiales"],
            "propiedad": elegida["propiedad"],
            "descripcion": elegida["descripcion"],
        }

    @staticmethod
    def _pasaje_cerca(sim: Simulacion, h: HabitanteSim) -> Optional[dict]:
        """Un paso a otra dimensión al lado (`provee.lleva_a` en los datos)."""
        if sim.mundo is None:
            return None
        return sim.mundo.pasaje_cerca(sim, h)

    # ------------------------------------------------------------------ decisión

    def decidir(self, sim: Simulacion, h: HabitanteSim) -> dict:
        """Interfaz que llama el motor: devuelve la acción propuesta para este habitante."""
        # Reflejo que no se delega: el fuego encima no admite deliberación.
        if h.sed < SED_DESPIERTA and sim.fuego_cerca(h, sim.r_huir_fuego):
            return self._demo.decidir(sim, h)

        # Responder propuesta de familia pendiente es una reacción social inmediata
        if h.propuesta and sim.t - h.propuesta.get("t", 0.0) <= 360:
            return {"tipo": "responder_propuesta", "acepta": sim.rng.random() < 0.85, "motivo": "responder familia"}

        cerebro = self._cerebro_de(sim, h)
        cerebro.needs = self._necesidades(sim, h)
        cerebro.personality = self._personalidad(h)

        creencias = self._creencias(sim, h)
        self._creencias_vigentes[h.id] = (float(sim.t), creencias)
        propuesta = cerebro.tick(
            self._observacion(sim, h, cerebro),
            extra_state=creencias,
        )
        self._ultima_propuesta[h.id] = propuesta
        self._decisiones += 1
        return self._traducir(sim, h, propuesta)

    def _traducir(self, sim: Simulacion, h: HabitanteSim, propuesta: Any) -> dict:
        """Convierte la propuesta del cerebro en la acción que el motor sabe validar."""
        tipo = propuesta.action_type
        motivo = (propuesta.goal_id or "reposo")[:40]
        resolver = self._TRADUCTORES.get(tipo)
        if resolver is None:
            self._sin_traducir[tipo] = self._sin_traducir.get(tipo, 0) + 1
            return {"tipo": "esperar", "min": 15, "motivo": motivo}
        accion = resolver(self, sim, h, motivo)
        if accion is None:
            # El plan se armó con una creencia que ya no se cumple: esperar poco y replanificar.
            return {"tipo": "esperar", "min": 10, "motivo": motivo}
        accion.setdefault("motivo", motivo)
        return accion

    # Un traductor por capacidad. Devuelve None si el dato concreto ya no está.
    def _t_beber(self, sim, h, motivo):
        return {"tipo": "beber"}

    def _t_ir_al_agua(self, sim, h, motivo):
        destino = self._agua_alcanzable(sim, h)
        return None if destino is None else {"tipo": "ir", "destino": destino, "luego": "beber"}

    def _t_comer(self, sim, h, motivo):
        objeto = self._comida_en_mano(sim, h)
        return None if objeto is None else {"tipo": "comer", "objeto": objeto}

    def _t_juntar_comida(self, sim, h, motivo):
        material = self._comida_juntable(sim, h)
        return None if material is None else {"tipo": "juntar", "material": material}

    def _t_juntar_material(self, sim, h, motivo):
        material = self._material_para_recetas(sim, h)
        return None if material is None else {"tipo": "juntar", "material": material}

    def _t_juntar_para_inventar(self, sim, h, motivo):
        material = self._material_para_inventar(sim, h)
        return None if material is None else {"tipo": "juntar", "material": material}

    def _t_cazar(self, sim, h, motivo):
        animal = self._presa_cerca(sim, h)
        return None if animal is None else {"tipo": "cazar", "animal": animal}

    def _t_cocinar(self, sim, h, motivo):
        return {"tipo": "cocinar"}

    def _t_curar_carne(self, sim, h, motivo):
        return {"tipo": "curar"}

    def _t_dormir(self, sim, h, motivo):
        cerebro = self._cerebros.get(h.id)
        if cerebro is not None and hasattr(cerebro, "consolidate_sleep"):
            try:
                cerebro.consolidate_sleep(int(sim.t))
            except Exception:
                pass
        return {"tipo": "dormir", "min": sim.rng.randint(240, 420)}

    def _t_encender(self, sim, h, motivo):
        return {"tipo": "encender"}

    def _t_tomar_fuego(self, sim, h, motivo):
        return {"tipo": "tomar_fuego"}

    def _t_calentarse(self, sim, h, motivo):
        # Quedarse quieto al lado del fuego: el motor ya calienta a quien esté en el radio.
        return {"tipo": "esperar", "min": 30}

    def _t_ir_al_fuego(self, sim, h, motivo):
        fogata = sim.fogata_cerca(h, sim.celdas(400.0))
        if fogata is None:
            return None
        return {"tipo": "ir", "destino": (int(fogata["x"]), int(fogata["y"]))}

    def _t_hablar(self, sim, h, motivo):
        otro = self._alguien_para_hablar(sim, h)
        if otro is None:
            return None
        return self._mensaje_para(sim, h, otro)

    def _t_ir_hacia(self, sim, h, motivo):
        ausentes = self._alguien_lejos(sim, h)
        return None if not ausentes else {"tipo": "ir_hacia", "a": ausentes[0][0].id}

    def _t_buscar(self, sim, h, motivo):
        ausentes = self._alguien_lejos(sim, h)
        return None if not ausentes else {"tipo": "buscar", "a": ausentes[0][0].id}

    def _t_ensenar(self, sim, h, motivo):
        par = self._algo_para_ensenar(sim, h)
        if par is None:
            return None
        return {"tipo": "ensenar", "a": par[0], "conocimiento": par[1]}

    def _t_proponer_hijo(self, sim, h, motivo):
        otro = self._pareja_posible(sim, h)
        return None if otro is None else {"tipo": "proponer_hijo", "a": otro.id}

    def _t_ir_hacia_pareja(self, sim, h, motivo):
        otro = self._pareja_lejos(sim, h)
        return None if otro is None else {"tipo": "ir_hacia", "a": otro.id}

    def _t_buscar_pareja(self, sim, h, motivo):
        otro = self._pareja_lejos(sim, h)
        return None if otro is None else {"tipo": "buscar", "a": otro.id}

    def _t_responder_propuesta(self, sim, h, motivo):
        if not h.propuesta:
            return None
        # El mismo 0,85 que usa el cerebro híbrido, y del mismo generador sembrado: si fueran dos
        # números distintos, dos mundos con la misma semilla no darían la misma familia.
        return {"tipo": "responder_propuesta", "acepta": sim.rng.random() < 0.85}

    def _t_fabricar(self, sim, h, motivo):
        receta = self._receta_lista(sim, h)
        return None if receta is None else {"tipo": "fabricar", "objeto": receta}

    def _t_inventar(self, sim, h, motivo):
        idea = self._idea_para_probar(sim, h)
        return None if idea is None else {"tipo": "inventar", "receta": idea}

    def _t_usar(self, sim, h, motivo):
        objeto = self._objeto_usable(sim, h)
        return None if objeto is None else {"tipo": "usar", "objeto": objeto}

    def _t_montar(self, sim, h, motivo):
        animal = self._animal_montable(sim, h)
        return None if animal is None else {"tipo": "montar", "animal": animal}

    def _t_desmontar(self, sim, h, motivo):
        return {"tipo": "desmontar"}

    def _t_atravesar(self, sim, h, motivo):
        return {"tipo": "atravesar"}

    def _t_explorar(self, sim, h, motivo):
        destino = self._destino_de_exploracion(sim, h)
        return None if destino is None else {"tipo": "ir", "destino": destino}

    def _t_esperar(self, sim, h, motivo):
        return {"tipo": "esperar", "min": 15}

    _TRADUCTORES = {
        "beber": _t_beber,
        "ir_al_agua": _t_ir_al_agua,
        "comer": _t_comer,
        "juntar_comida": _t_juntar_comida,
        "juntar_material": _t_juntar_material,
        "juntar_para_inventar": _t_juntar_para_inventar,
        "cazar": _t_cazar,
        "cocinar": _t_cocinar,
        "curar_carne": _t_curar_carne,
        "dormir": _t_dormir,
        "encender": _t_encender,
        "tomar_fuego": _t_tomar_fuego,
        "ir_al_fuego": _t_ir_al_fuego,
        "calentarse": _t_calentarse,
        "hablar": _t_hablar,
        "ir_hacia": _t_ir_hacia,
        "buscar": _t_buscar,
        "ensenar": _t_ensenar,
        "proponer_hijo": _t_proponer_hijo,
        "ir_hacia_pareja": _t_ir_hacia_pareja,
        "buscar_pareja": _t_buscar_pareja,
        "responder_propuesta": _t_responder_propuesta,
        "fabricar": _t_fabricar,
        "inventar": _t_inventar,
        "usar": _t_usar,
        "montar": _t_montar,
        "desmontar": _t_desmontar,
        "atravesar": _t_atravesar,
        "explorar": _t_explorar,
        "esperar": _t_esperar,
        # `wait` es el respaldo propio de Cognitive Engine (`WAIT_ACTION` en su `decision/engine.py`):
        # lo devuelve cuando eligió un objetivo y NO pudo armar ningún plan para él. No sale de
        # nuestro catálogo, así que no estaba traducido y caía en el camino de «capacidad
        # desconocida»: 15 minutos de espera y una marca en `_sin_traducir`. Medido en el mundo
        # `gaia`: 790 decisiones así, 279 de ellas con sed por encima de 80, o sea gente esperando
        # mientras se moría de sed. Es lo mismo que `esperar`, pero conviene que quede dicho.
        "wait": _t_esperar,
    }

    @staticmethod
    def _destino_de_exploracion(sim: Simulacion, h: HabitanteSim) -> Optional[tuple[int, int]]:
        """Un punto caminable a una distancia en METROS, no en celdas (ver CLAUDE.md).

        El tiro al azar se recorta contra los bordes del mapa antes de buscar: sin eso, alguien
        parado cerca de un borde mandaba casi todos los intentos afuera y se quedaba esperando para
        siempre, que es exactamente el bug de «quedarse clavado sin poder explorar».
        """
        ancho, alto = sim.terreno.ancho, sim.terreno.alto
        for intento in range(16):
            lejos = sim.celdas(900.0) if intento < 8 else sim.celdas(300.0)
            d = sim.rng.uniform(sim.celdas(100.0), max(sim.celdas(100.0) + 1.0, lejos))
            a = sim.rng.random() * 2 * math.pi
            x = min(ancho - 2, max(1, int(h.x + math.cos(a) * d)))
            y = min(alto - 2, max(1, int(h.y + math.sin(a) * d)))
            if (x, y) == (int(h.x), int(h.y)):
                continue
            c = sim.terreno.caminable_cerca(x, y, 4)
            if c:
                return c
        return None

    # ------------------------------------------------------------------ resultados

    def registrar_resultado(
        self, sim: Simulacion, h: HabitanteSim, ok: bool, texto: str
    ) -> None:
        """Devuelve al cerebro lo que pasó: de ahí sale el aprendizaje y la replanificación."""
        from cognitive_engine import ActionResult, ActionStatus

        propuesta = self._ultima_propuesta.get(h.id)
        cerebro = self._cerebros.get(h.id)
        if propuesta is None or cerebro is None:
            return

        cerebro.receive_result(
            ActionResult(
                proposal_id=propuesta.proposal_id,
                brain_id=cerebro.identity.brain_id,
                tick=int(sim.t),
                status=ActionStatus.ACCEPTED if ok else ActionStatus.REJECTED,
                rejection_reason=None if ok else (texto or "El entorno no lo permitió."),
            )
        )
        # Lo que llena la compañía es haber interactuado, no estar cerca.
        if ok and propuesta.action_type in (
            "hablar",
            "ensenar",
            "proponer_hijo",
            "responder_propuesta",
        ):
            self._ultima_charla[h.id] = float(sim.t)
            self._charlas += 1

        self._anotar_decision(sim, h, propuesta, ok, texto)

    def _anotar_decision(
        self, sim: Simulacion, h: HabitanteSim, propuesta: Any, ok: bool, texto: str
    ) -> None:
        """Deja la decisión en la tabla `decisiones`, que es lo que el visor muestra como pensamiento.
        Registra también la trayectoria estructurada en `entrenamiento_cerebro` para entrenar futuros cerebros.
        """
        if self.con is None:
            return
        pensamiento = self._pensamiento_de(propuesta)
        cerebro = self._cerebros.get(h.id)
        plan_str = None
        if cerebro and hasattr(cerebro, "decision_engine") and hasattr(cerebro.decision_engine, "state"):
            plan = cerebro.decision_engine.state.plan
            if plan:
                plan_str = json.dumps([p.action_type for p in plan.steps])

        try:
            with self.con:
                self.con.execute(
                    "INSERT INTO decisiones (habitante_id, t_min, percepcion, recuerdos, "
                    "respuesta_modelo, accion, resultado, ok, modelo, latencia_ms) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        h.id,
                        int(sim.t),
                        pensamiento[:1800],
                        None,
                        json.dumps(
                            {
                                "pensamiento": pensamiento,
                                "accion": propuesta.action_type,
                                "objetivo": propuesta.goal_id,
                                "plan": plan_str,
                                "confianza": propuesta.confidence,
                            },
                            ensure_ascii=False,
                        )[:600],
                        propuesta.action_type,
                        (texto or "")[:300],
                        1 if ok else 0,
                        "cognitive-engine",
                        0,
                    ),
                )
                if not getattr(self, "_tabla_entrenamiento_ok", False):
                    self.con.execute(
                        "CREATE TABLE IF NOT EXISTS entrenamiento_cerebro ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "brain_id TEXT NOT NULL, "
                        "habitante_id INTEGER NOT NULL, "
                        "t_min INTEGER NOT NULL, "
                        "necesidades TEXT NOT NULL, "
                        "rasgos TEXT NOT NULL, "
                        "creencias TEXT NOT NULL, "
                        "objetivo TEXT NOT NULL, "
                        "plan TEXT, "
                        "accion TEXT NOT NULL, "
                        "parametros TEXT, "
                        "resultado TEXT, "
                        "ok INTEGER NOT NULL)"
                    )
                    # Sin este índice la poda diaria (`sim_io._podar_por_habitante`) tiene que
                    # recorrer la tabla entera por cada habitante.
                    self.con.execute(
                        "CREATE INDEX IF NOT EXISTS idx_entrenamiento_hab "
                        "ON entrenamiento_cerebro (habitante_id, id)"
                    )
                    self._tabla_entrenamiento_ok = True

                necesidades_dict = {
                    "sed": round(float(h.sed), 1),
                    "hambre": round(float(h.hambre), 1),
                    "energia": round(float(h.energia), 1),
                    "salud": round(float(h.salud), 1),
                    "frio": round(float(getattr(h, "frio", 0.0)), 2),
                }
                rasgos_dict = {
                    "curiosidad": round(float(h.rasgo("curiosidad")), 3),
                    "cautela": round(float(h.rasgo("cautela")), 3),
                    "sociabilidad": round(float(h.rasgo("sociabilidad")), 3),
                    "resiliencia": round(float(h.rasgo("resiliencia")), 3),
                }
                self.con.execute(
                    "INSERT INTO entrenamiento_cerebro ("
                    "brain_id, habitante_id, t_min, necesidades, rasgos, creencias, "
                    "objetivo, plan, accion, parametros, resultado, ok) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        f"{sim.ident}:h{h.id}",
                        h.id,
                        int(sim.t),
                        json.dumps(necesidades_dict),
                        json.dumps(rasgos_dict),
                        json.dumps(self._creencias_de_la_decision(sim, h)),
                        propuesta.goal_id or "idle",
                        plan_str,
                        propuesta.action_type,
                        json.dumps(propuesta.parameters or {}),
                        (texto or "")[:300],
                        1 if ok else 0,
                    ),
                )
        except sqlite3.Error as e:
            # Anotar lo que pensó no puede tumbar el mundo, pero tampoco se tapa: el contador sale
            # en el panel. El caso típico es un habitante que todavía no está guardado en la base
            # (la tabla `decisiones` tiene clave foránea contra `habitantes`).
            self._anotaciones_fallidas += 1
            self._ultimo_error_anotando = str(e)[:120]

    @staticmethod
    def _pensamiento_de(propuesta: Any) -> str:
        """El razonamiento en una frase, contado como lo contaría la persona.

        Nunca puede delatar que esto es una simulación (regla 8 de CLAUDE.md), así que no se nombran
        ni «GOAP», ni «utilidad», ni «plan del motor»: sale la justificación traducida a intención.
        """
        objetivo = (propuesta.goal_id or "").replace("satisfy_", "")
        destino = propuesta.parameters.get("target")
        por_necesidad = {
            "sed": "Tengo sed",
            "hambre": "Tengo hambre",
            "energia": "Estoy cansado",
            "salud": "No me siento bien",
            "calor": "Tengo frío",
            "compania": "Tengo ganas de ver a alguien",
            "familia": "Tengo ganas de formar una familia",
            "herramientas": "Me vendría bien tener algo mejor",
            "explore_environment": "Tengo ganas de ver qué hay por ahí",
            "idle": "Por ahora no me falta nada",
        }
        arranque = por_necesidad.get(objetivo, "Me puse a pensar")
        cola = f" (voy por {destino})" if destino else ""
        return f"{arranque}: {propuesta.action_type}{cola}."

    # ------------------------------------------------------------------ panel

    def pendientes(self) -> int:
        """Siempre 0: este cerebro es sincrónico y no espera a ningún modelo."""
        return 0

    def estado(self, sim: Simulacion) -> dict:
        """Lo que muestra el panel de la UI."""
        objetivos: dict[str, int] = {}
        replanificaciones = 0
        pericia: dict[str, float] = {}
        for cerebro in self._cerebros.values():
            objetivo = cerebro.decision_engine.state.goal_id or "sin objetivo"
            objetivos[objetivo] = objetivos.get(objetivo, 0) + 1
            replanificaciones += cerebro.decision_engine.state.replans
            for nombre, habilidad in cerebro.learner.skills.items():
                pericia[nombre] = round(
                    (pericia.get(nombre, habilidad.proficiency) + habilidad.proficiency) / 2, 3
                )
        return {
            "motor": self.nombre,
            "disponible": True,
            "llm": False,
            "cerebros": len(self._cerebros),
            "decisiones": self._decisiones,
            "replanificaciones": replanificaciones,
            "objetivos": objetivos,
            "pericia": pericia,
            "sin_traducir": dict(self._sin_traducir),
            "charlas": self._charlas,
            "anotaciones_fallidas": self._anotaciones_fallidas,
            "ultimo_error_anotando": self._ultimo_error_anotando,
            "latencia_s": 0.0,
            "rechazos_llm": 0,
        }

"""El cerebro de los habitantes delegado a Cognitive Engine (proyecto aparte, sin LLM).

Lo que se mide acá es el puente, no el motor cognitivo: que la traducción de ida (cuerpo y mundo a
observación) y la de vuelta (propuesta a acción válida) no pierdan nada, que la cadena de acciones
la arme el planificador y que el mundo siga siendo determinista.

Si Cognitive Engine no está en el entorno, las pruebas se saltean: Mundo Vivo no depende de él.
"""
from __future__ import annotations

import unittest

from mundo_vivo.agentes.cerebro_cognitivo import (
    CerebroCognitivo,
    motor_cognitivo_disponible,
)
from mundo_vivo.motor.generador import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion

# Tipos internos que `Simulacion._aplicar` sabe ejecutar y que este puente puede emitir.
# No es la lista `ACCIONES` de `mente.py`: esa es el vocabulario que ve el modelo de lenguaje.
TIPOS_DEL_MOTOR = {"ir", "beber", "comer", "juntar", "dormir", "esperar"}

_HAY_MOTOR = motor_cognitivo_disponible()


def _tierra_firme(s: Simulacion) -> tuple[int, int]:
    """Primera celda caminable barriendo desde el centro: determinista y nunca dentro del agua.

    No se puede plantar a nadie en una coordenada fija: en este mapa (10, 10) es agua, y ahí no hay
    a dónde explorar, así que una prueba de movimiento ahí mide otra cosa.
    """
    cx, cy = s.terreno.ancho // 2, s.terreno.alto // 2
    for radio in range(0, max(s.terreno.ancho, s.terreno.alto)):
        for dy in range(-radio, radio + 1):
            for dx in range(-radio, radio + 1):
                x, y = cx + dx, cy + dy
                if s.terreno.dentro(x, y) and s.terreno.caminable(x, y):
                    return x, y
    raise AssertionError("El mundo de prueba no tiene ni una celda caminable.")


def _mundo(semilla: int = 7):
    """Mundo chico con celdas de 50 m, como el resto de los tests (ver CLAUDE.md)."""
    m = generar_mundo(semilla, 128, 128, 50)
    s = Simulacion(m["capas"], m["meta"])
    s.ajustes["modulos"]["hambre"] = True
    x, y = _tierra_firme(s)
    h = HabitanteSim(1, "Prueba", x + 0.5, y + 0.5)
    s.habitantes[1] = h
    return s, h


@unittest.skipUnless(_HAY_MOTOR, "Cognitive Engine no está disponible en este entorno")
class TestPuente(unittest.TestCase):
    def test_la_accion_propuesta_siempre_es_una_que_el_motor_conoce(self):
        s, h = _mundo()
        cerebro = CerebroCognitivo()
        for sed, hambre, energia in ((10, 10, 100), (80, 20, 90), (20, 80, 90), (10, 10, 15)):
            h.sed, h.hambre, h.energia = float(sed), float(hambre), float(energia)
            accion = cerebro.decidir(s, h)
            self.assertIn(accion["tipo"], TIPOS_DEL_MOTOR, f"acción inventada: {accion}")

    def test_con_sed_arma_la_cadena_ir_y_beber_sin_que_nadie_la_guione(self):
        s, h = _mundo()
        cerebro = CerebroCognitivo()
        h.sed = 85.0

        accion = cerebro.decidir(s, h)

        if accion["tipo"] == "beber":
            self.assertTrue(s.terreno.agua_adyacente(int(h.x), int(h.y)))
        else:
            self.assertEqual(accion["tipo"], "ir")
            self.assertEqual(accion.get("luego"), "beber", "ir al agua sin beber no sirve de nada")

        # La cadena completa está en el plan del cerebro, no sólo el paso que se ejecuta.
        interno = cerebro._cerebros[h.id]
        plan = interno.decision_engine.state.plan
        self.assertIsNotNone(plan)
        self.assertIn("beber", [p.action_type for p in plan.steps])

    def test_sin_nada_urgente_hace_algo_igual(self):
        """Con el cuerpo cubierto tiene que seguir habiendo vida: juntar, fabricar, buscar, explorar."""
        s, h = _mundo()
        cerebro = CerebroCognitivo()
        h.sed, h.hambre, h.energia, h.salud = 5.0, 5.0, 100.0, 100.0

        tipos = {cerebro.decidir(s, h)["tipo"] for _ in range(5)}
        self.assertTrue(tipos, "no propuso nada")
        self.assertNotEqual(tipos, {"esperar"}, "con todo cubierto se quedó sentado sin hacer nada")

    def test_el_objetivo_sale_de_la_necesidad_que_mas_aprieta(self):
        s, h = _mundo()
        cerebro = CerebroCognitivo()

        h.sed, h.hambre = 90.0, 50.0
        cerebro.decidir(s, h)
        self.assertEqual(cerebro._cerebros[h.id].decision_engine.state.goal_id, "satisfy_sed")

        h.sed, h.hambre = 5.0, 90.0
        cerebro.decidir(s, h)
        self.assertEqual(cerebro._cerebros[h.id].decision_engine.state.goal_id, "satisfy_hambre")

    def test_un_rechazo_del_motor_tira_el_plan_y_hace_replanificar(self):
        s, h = _mundo()
        cerebro = CerebroCognitivo()
        h.sed = 85.0

        cerebro.decidir(s, h)
        interno = cerebro._cerebros[h.id]
        self.assertIsNotNone(interno.decision_engine.state.plan)

        cerebro.registrar_resultado(s, h, False, "No hay agua acá.")
        self.assertIsNone(interno.decision_engine.state.plan, "un rechazo tiene que invalidar el plan")

        replanes = interno.decision_engine.state.replans
        cerebro.decidir(s, h)
        self.assertGreater(interno.decision_engine.state.replans, replanes)

    def test_aprende_del_resultado(self):
        s, h = _mundo()
        cerebro = CerebroCognitivo()
        h.sed = 85.0

        cerebro.decidir(s, h)
        cerebro.registrar_resultado(s, h, True, "Bebiste.")
        habilidades = cerebro._cerebros[h.id].learner.skills
        self.assertTrue(habilidades, "tendría que haber quedado una habilidad registrada")
        self.assertTrue(all(sk.success_count >= 1 for sk in habilidades.values()))

    def test_dos_mundos_iguales_deciden_igual(self):
        def correr() -> list[str]:
            s, h = _mundo()
            cerebro = CerebroCognitivo()
            salida = []
            for sed in (20.0, 50.0, 80.0, 90.0, 20.0):
                h.sed = sed
                accion = cerebro.decidir(s, h)
                salida.append(f"{accion['tipo']}:{accion.get('luego', '')}")
            return salida

        self.assertEqual(correr(), correr())

    def test_el_panel_no_miente_sobre_el_modelo(self):
        s, h = _mundo()
        cerebro = CerebroCognitivo()
        cerebro.decidir(s, h)
        est = cerebro.estado(s)
        self.assertFalse(est["llm"], "este cerebro no usa modelo de lenguaje")
        self.assertEqual(cerebro.pendientes(), 0)
        self.assertEqual(est["cerebros"], 1)
        self.assertEqual(est["decisiones"], 1)

    def test_personalidades_distintas_deciden_distinto(self):
        s, base = _mundo()
        cerebro = CerebroCognitivo()

        curioso = HabitanteSim(2, "Curioso", base.x, base.y)
        prudente = HabitanteSim(3, "Prudente", base.x, base.y)
        for h in (curioso, prudente):
            h.sed, h.hambre, h.energia, h.salud = 5.0, 5.0, 100.0, 100.0
            s.habitantes[h.id] = h
        curioso.rasgos_vivos = {"curiosidad": 0.95, "cautela": 0.1, "sociabilidad": 0.5, "resiliencia": 0.5}
        prudente.rasgos_vivos = {"curiosidad": 0.05, "cautela": 0.95, "sociabilidad": 0.5, "resiliencia": 0.5}

        accion_curioso = cerebro.decidir(s, curioso)
        accion_prudente = cerebro.decidir(s, prudente)

        # El curioso sale a explorar; el prudente se queda haciendo algo útil donde está.
        self.assertEqual(accion_curioso["tipo"], "ir")
        self.assertNotEqual(accion_prudente["tipo"], "ir")
        self.assertNotEqual(
            cerebro._cerebros[curioso.id].decision_engine.state.goal_id,
            cerebro._cerebros[prudente.id].decision_engine.state.goal_id,
            "mismo escenario, misma decisión: la personalidad no cambió nada",
        )


@unittest.skipUnless(_HAY_MOTOR, "Cognitive Engine no está disponible en este entorno")
class TestCatalogoCompleto(unittest.TestCase):
    """El grafo de capacidades: lo que se declara tiene que poder encadenarse y traducirse."""

    def _planificar(self, creencias: dict, necesidad: str, meta: dict):
        from cognitive_engine.decision.goap import GOAPPlanner

        catalogo = CerebroCognitivo._catalogo()
        acciones = [cap.to_action() for cap in catalogo.for_need(necesidad)]
        return GOAPPlanner.plan(current_state=creencias, goal_state=meta, available_actions=acciones)

    def _base(self) -> dict:
        from cognitive_engine.decision.capabilities import IDLE, NEED_SATISFIED, NOVELTY

        from mundo_vivo.agentes import cerebro_cognitivo as cc

        claves = [
            cc.AGUA_AL_LADO, cc.AGUA_CONOCIDA, cc.COMIDA_EN_MANO, cc.COMIDA_JUNTABLE,
            cc.CRUDO_EN_MANO, cc.PRESA_CERCA, cc.FUEGO_AL_ALCANCE, cc.FUEGO_CONOCIDO,
            cc.CHISPA_Y_LENA, cc.PALO_EN_MANO, cc.ANTORCHA_EN_MANO, cc.PERSONA_CERCA,
            cc.PERSONA_LEJOS, cc.PROPUESTA_PENDIENTE, cc.PAREJA_POSIBLE, cc.PAREJA_LEJOS,
            cc.PUEDE_DORMIR, cc.ALGO_PARA_ENSENAR,
            cc.RECETA_LISTA, cc.MATERIAL_AQUI, cc.PUEDE_INVENTAR, cc.OBJETO_USABLE,
            cc.ANIMAL_MONTABLE, cc.MONTADO, cc.PASAJE_CERCA, cc.ABRIGO_PUESTO,
        ]
        estado = dict.fromkeys(claves, False)
        estado.update({NEED_SATISFIED: False, IDLE: False, NOVELTY: False})
        return estado

    def test_cazar_cocinar_comer_sale_del_planificador(self):
        from cognitive_engine.decision.capabilities import NEED_SATISFIED

        from mundo_vivo.agentes import cerebro_cognitivo as cc

        estado = self._base()
        estado[cc.PRESA_CERCA] = True
        estado[cc.FUEGO_AL_ALCANCE] = True

        plan = self._planificar(estado, cc.HAMBRE, {NEED_SATISFIED: True})

        self.assertIsNotNone(plan)
        self.assertEqual(
            [p.action_type for p in plan.steps],
            ["cazar", "cocinar", "comer"],
            "nadie escribió esta secuencia: sale de las precondiciones",
        )

    def test_sin_fuego_la_carne_se_cura_en_vez_de_cocinarse(self):
        from cognitive_engine.decision.capabilities import NEED_SATISFIED

        from mundo_vivo.agentes import cerebro_cognitivo as cc

        estado = self._base()
        estado[cc.CRUDO_EN_MANO] = True

        plan = self._planificar(estado, cc.HAMBRE, {NEED_SATISFIED: True})

        self.assertIsNotNone(plan)
        self.assertEqual([p.action_type for p in plan.steps], ["curar_carne", "comer"])

    def test_el_fuego_se_enciende_antes_de_calentarse(self):
        from cognitive_engine.decision.capabilities import NEED_SATISFIED

        from mundo_vivo.agentes import cerebro_cognitivo as cc

        estado = self._base()
        estado[cc.CHISPA_Y_LENA] = True

        plan = self._planificar(estado, cc.CALOR, {NEED_SATISFIED: True})

        self.assertIsNotNone(plan)
        self.assertEqual([p.action_type for p in plan.steps], ["encender", "calentarse"])

    def test_conseguir_fuego_no_sacia_el_hambre(self):
        """Prender una fogata es un medio, no una comida. Si fuera un fin, nadie cazaría."""
        from cognitive_engine.decision.capabilities import NEED_SATISFIED

        from mundo_vivo.agentes import cerebro_cognitivo as cc

        estado = self._base()
        estado[cc.CHISPA_Y_LENA] = True
        estado[cc.FUEGO_CONOCIDO] = True

        plan = self._planificar(estado, cc.HAMBRE, {NEED_SATISFIED: True})

        self.assertIsNotNone(plan)
        tipos = [p.action_type for p in plan.steps]
        self.assertEqual(tipos[-1], "comer", f"el plan del hambre termina comiendo, no en {tipos}")

    def test_con_carne_cruda_elige_el_camino_mas_barato(self):
        """Curar (secar al aire) sale más barato que prender fuego para cocinar: eso es correcto."""
        from cognitive_engine.decision.capabilities import NEED_SATISFIED

        from mundo_vivo.agentes import cerebro_cognitivo as cc

        estado = self._base()
        estado[cc.CRUDO_EN_MANO] = True
        estado[cc.CHISPA_Y_LENA] = True

        plan = self._planificar(estado, cc.HAMBRE, {NEED_SATISFIED: True})

        self.assertIsNotNone(plan)
        self.assertEqual([p.action_type for p in plan.steps], ["curar_carne", "comer"])

        # Con el fuego ya hecho, cocinar pasa a ser más barato que curar.
        estado[cc.FUEGO_AL_ALCANCE] = True
        plan2 = self._planificar(estado, cc.HAMBRE, {NEED_SATISFIED: True})
        self.assertEqual([p.action_type for p in plan2.steps], ["cocinar", "comer"])

    def test_juntar_antes_de_fabricar(self):
        from cognitive_engine.decision.capabilities import NEED_SATISFIED

        from mundo_vivo.agentes import cerebro_cognitivo as cc

        estado = self._base()
        estado[cc.MATERIAL_AQUI] = True

        plan = self._planificar(estado, cc.HERRAMIENTAS, {NEED_SATISFIED: True})

        self.assertIsNotNone(plan)
        self.assertEqual([p.action_type for p in plan.steps], ["juntar_material", "fabricar"])

    def test_buscar_a_alguien_antes_de_hablarle(self):
        from cognitive_engine.decision.capabilities import NEED_SATISFIED

        from mundo_vivo.agentes import cerebro_cognitivo as cc

        estado = self._base()
        estado[cc.PERSONA_LEJOS] = True

        plan = self._planificar(estado, cc.COMPANIA, {NEED_SATISFIED: True})

        self.assertIsNotNone(plan)
        tipos = [p.action_type for p in plan.steps]
        self.assertIn(tipos[0], ("ir_hacia", "buscar"))
        self.assertEqual(tipos[-1], "hablar")

    def test_con_sed_mortal_la_salud_no_le_gana_la_puja_a_la_sed(self):
        """Regresión del mundo `gaia`: 23 de 27 muertes fueron de sed, 13 con el agua pegada.

        La cadena era ésta. La sed baja la salud; las dos necesidades llegan a crítica; el árbitro
        elige `satisfy_salud`; las únicas capacidades que satisfacen la salud son `dormir`, que el
        motor prohíbe con sed alta (`PUEDE_DORMIR`), y `usar`, que pide llevar un remedio encima; sin
        ninguna de las dos, el planificador no arma plan y devuelve `wait`; el motor espera 15
        minutos; la sed sigue subiendo. Medido: 57,6% de las decisiones con sed ≥ 80 fueron `wait` y
        el 73% no tenían plan.

        Así que con la sed pasada del umbral y sin remedio, la salud NO puede declararse crítica: lo
        único que se puede atender es la sed. Con un remedio encima sí, porque ahí hay algo que hacer.
        """
        from mundo_vivo.agentes import cerebro_cognitivo as cc
        from mundo_vivo.motor.simulacion import SED_DESPIERTA

        s, h = _mundo()
        cerebro = CerebroCognitivo()
        h.salud, h.energia = 20.0, 90.0

        h.sed = SED_DESPIERTA + 5.0
        salud = cerebro._necesidades(s, h).needs[cc.SALUD]
        self.assertEqual(salud.critical_threshold, cc.NUNCA_CRITICA,
                         "con sed mortal y sin remedio, la salud no puede ganarle la puja a la sed")

        h.sed = SED_DESPIERTA - 5.0
        salud = cerebro._necesidades(s, h).needs[cc.SALUD]
        self.assertEqual(salud.critical_threshold, cc.UMBRAL_SALUD,
                         "sin sed mortal, la salud vuelve a ser una necesidad como cualquier otra")

    def test_con_sed_mortal_nada_que_mate_mas_despacio_le_disputa_la_puja(self):
        """La regla de «lo que mata más rápido va primero», puesta donde el árbitro la pueda ver.

        El árbitro del motor cognitivo ordena por cuán VACÍA está la necesidad, no por cuán rápido
        mata: con sed 85 y hambre 90 ganaba el hambre, por 5 puntos. Pero el motor dice otra cosa: la
        sed a 100 saca 0,3 de salud por minuto (mata en 5,5 horas), el hambre 0,035 (2 días) y el
        frío extremo 0,02 (3,5 días). Medido antes del arreglo en un mundo nuevo: de 68 decisiones
        con sed ≥ 80, el 72% eligió `cazar` y sólo el 12% `beber`.
        """
        from mundo_vivo.agentes import cerebro_cognitivo as cc
        from mundo_vivo.motor.simulacion import SED_DESPIERTA

        s, h = _mundo()
        cerebro = CerebroCognitivo()
        h.hambre, h.energia, h.frio = 95.0, 5.0, 0.9

        h.sed = SED_DESPIERTA + 5.0
        n = cerebro._necesidades(s, h).needs
        for nombre in (cc.HAMBRE, cc.ENERGIA, cc.CALOR):
            self.assertEqual(n[nombre].critical_threshold, cc.NUNCA_CRITICA,
                             "con sed mortal, %s no puede disputarle la puja a la sed" % nombre)
        self.assertGreater(n[cc.SED].critical_threshold, 0.0,
                           "la sed sí tiene que seguir siendo crítica")

        h.sed = SED_DESPIERTA - 5.0
        n = cerebro._necesidades(s, h).needs
        self.assertGreater(n[cc.HAMBRE].critical_threshold, 0.0,
                           "sin sed mortal, el hambre vuelve a ser crítica")

    def test_toda_capacidad_declarada_se_puede_traducir(self):
        catalogo = CerebroCognitivo._catalogo()
        declaradas = set(catalogo.capabilities)
        traducibles = set(CerebroCognitivo._TRADUCTORES)
        self.assertEqual(
            declaradas - traducibles,
            set(),
            "hay capacidades que el cerebro puede proponer y el puente no sabe traducir",
        )
        # El motor cognitivo puede devolver acciones que NO salen de nuestro catálogo: `WAIT_ACTION`
        # es su propio respaldo para cuando eligió un objetivo y no pudo armar ningún plan. Ésas
        # también tienen que estar traducidas, así que se admiten de este lado sin estar declaradas.
        # Sin traducir caían en el camino de «capacidad desconocida» y el motor esperaba 15 minutos
        # a ciegas: en el mundo `gaia` pasó 790 veces, 279 de ellas con sed por encima de 80.
        from cognitive_engine.decision.engine import WAIT_ACTION

        self.assertIn(WAIT_ACTION, traducibles,
                      "el respaldo propio del motor cognitivo tiene que estar traducido")
        self.assertEqual(
            traducibles - declaradas - {WAIT_ACTION},
            set(),
            "hay traductores de capacidades que ya no existen",
        )


@unittest.skipUnless(_HAY_MOTOR, "Cognitive Engine no está disponible en este entorno")
class TestLoQuePenso(unittest.TestCase):
    """El visor muestra «Lo que pensó» leyendo la tabla `decisiones`. Este cerebro tiene que llenarla."""

    def test_cada_decision_queda_anotada_y_se_entiende(self):
        import json
        import tempfile
        from pathlib import Path

        from mundo_vivo.persistencia import db

        s, h = _mundo()
        with tempfile.TemporaryDirectory() as tmp:
            con = db.abrir(Path(tmp) / "m.db")
            try:
                # `decisiones` tiene clave foránea contra `habitantes`: el de prueba tiene que estar
                # en la base, como lo está cualquiera en un mundo de verdad.
                with con:
                    con.execute(
                        "INSERT INTO habitantes (id, uuid, nombre, nacimiento_min, x, y, estado) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (h.id, f"u{h.id}", h.nombre, 0, h.x, h.y, "{}"),
                    )
                cerebro = CerebroCognitivo(con)
                h.sed = 85.0
                cerebro.decidir(s, h)
                cerebro.registrar_resultado(s, h, True, "Bebiste agua.")

                filas = con.execute(
                    "SELECT respuesta_modelo, accion, modelo FROM decisiones WHERE habitante_id = ?",
                    (h.id,),
                ).fetchall()
                self.assertEqual(len(filas), 1, "la decisión no quedó anotada")

                datos = json.loads(filas[0][0])
                self.assertTrue(datos["pensamiento"], "el pensamiento quedó vacío")
                self.assertEqual(filas[0][2], "cognitive-engine")
                self.assertEqual(
                    cerebro.estado(s)["anotaciones_fallidas"], 0, "anotar falló en silencio"
                )

                # Regla 8: nadie puede sospechar que vive en una simulación.
                texto = datos["pensamiento"].lower()
                for palabra in ("goap", "utilidad", "plan goap", "simulación", "motor", "tick"):
                    self.assertNotIn(palabra, texto, f"el pensamiento delata la máquina: {texto}")

                # Comprobar registro para entrenamiento de futuros cerebros
                entren = con.execute(
                    "SELECT brain_id, habitante_id, necesidades, rasgos, creencias, accion, ok "
                    "FROM entrenamiento_cerebro WHERE habitante_id = ?",
                    (h.id,),
                ).fetchall()
                self.assertEqual(len(entren), 1, "no se guardó la trayectoria de entrenamiento")
                nec = json.loads(entren[0][2])
                self.assertIn("sed", nec)
                cre = json.loads(entren[0][4])
                self.assertIn("agua_al_lado", cre)
            finally:
                con.close()

    def test_deseo_de_familia_procura_reproduccion(self):
        s, h = _mundo()
        s.ajustes["modulos"]["reproduccion"] = True
        s.ajustes["modulos"]["conversacion"] = True
        h.sexo = "M"
        h.sed, h.hambre, h.energia, h.salud = 5.0, 5.0, 100.0, 100.0
        h.nacimiento_min = -30 * 120 * 1440.0
        h.sin_concebir_hasta = 0.0

        mujer = HabitanteSim(2, "Mujer", h.x + 1.0, h.y)
        mujer.sexo = "F"
        mujer.sed, mujer.hambre, mujer.energia, mujer.salud = 5.0, 5.0, 100.0, 100.0
        mujer.nacimiento_min = -30 * 120 * 1440.0
        s.habitantes[mujer.id] = mujer

        cerebro = CerebroCognitivo()
        accion = cerebro.decidir(s, h)
        self.assertIn(accion["tipo"], ("proponer_hijo", "ir_hacia", "hablar"))

    def test_curiosidad_inventa_y_descubre_receta(self):
        s, h = _mundo()
        s.ajustes["modulos"]["conocimientos"] = True
        h.sed, h.hambre, h.energia, h.salud = 5.0, 5.0, 100.0, 100.0
        h.inventario = {"arcilla": 5}
        cerebro = CerebroCognitivo()
        cerebro._ultima_charla[h.id] = s.t
        accion = cerebro.decidir(s, h)
        self.assertEqual(accion["tipo"], "inventar")
        self.assertIn("receta", accion)

    def test_transmision_cultural_ensenar(self):
        s, h = _mundo()
        s.ajustes["modulos"]["conocimientos"] = True
        s.ajustes["modulos"]["conversacion"] = True
        h.sed, h.hambre, h.energia, h.salud = 5.0, 5.0, 100.0, 100.0
        h.conoce.add(1)
        s.conocimientos[1] = {"nombre": "vasija de barro", "materiales": ["arcilla"], "propiedad": "contiene"}

        alumno = HabitanteSim(2, "Alumno", h.x + 1.0, h.y)
        alumno.sed, alumno.hambre, alumno.energia, alumno.salud = 5.0, 5.0, 100.0, 100.0
        s.habitantes[alumno.id] = alumno

        cerebro = CerebroCognitivo()
        accion = cerebro.decidir(s, h)
        self.assertEqual(accion["tipo"], "ensenar")
        self.assertEqual(accion["a"], alumno.id)
        self.assertEqual(accion["conocimiento"], 1)

    def test_sin_base_no_se_rompe(self):
        s, h = _mundo()
        cerebro = CerebroCognitivo()          # sin base: el panel queda vacío, pero vive igual
        cerebro.decidir(s, h)
        cerebro.registrar_resultado(s, h, True, "Listo.")


@unittest.skipUnless(_HAY_MOTOR, "Cognitive Engine no está disponible en este entorno")
class TestMundoCorriendo(unittest.TestCase):
    def test_un_mundo_chico_corre_con_este_cerebro_sin_romperse(self):
        """Lo mínimo que hay que probar antes de mirarlo horas: que avance y que nadie se clave."""
        m = generar_mundo(11, 128, 128, 50)
        s = Simulacion(m["capas"], m["meta"], cerebro=CerebroCognitivo())
        for k in ("hambre", "objetivos", "atributos", "conocimientos"):
            s.ajustes["modulos"][k] = True

        x, y = _tierra_firme(s)
        for i in range(1, 5):
            s.habitantes[i] = HabitanteSim(i, f"P{i}", x + 0.5 + i * 0.3, y + 0.5)

        acciones_vistas = set()
        for _ in range(600):                      # 600 minutos simulados
            s.avanzar(1.0)
            acciones_vistas.update(h.accion for h in s.habitantes.values() if h.vivo)

        vivos = [h for h in s.habitantes.values() if h.vivo]
        self.assertTrue(vivos, "se murieron todos en 10 horas")
        self.assertTrue(acciones_vistas - {"esperando"}, f"nadie hizo nada en 10 horas: {acciones_vistas}")

        est = s.cerebro.estado(s)
        self.assertEqual(
            est["sin_traducir"], {}, "el cerebro propuso algo que el puente no supo traducir"
        )
        self.assertGreater(est["decisiones"], 0)

    def test_con_sed_mortal_y_agua_al_lado_la_decision_es_ir_a_beber(self):
        """La red que de verdad caza el bug de la muerte por sed, de punta a punta.

        No alcanza con mirar los umbrales de las necesidades por separado: lo que importa es qué
        decide la persona. Con la sed pasada del umbral de despertarse y agua al alcance, lo único
        aceptable es beber o ir al agua. En el mundo `gaia`, de 484 decisiones así, el 57,6% fueron
        esperar y NINGUNA fue beber; en un mundo nuevo, el 72% fue cazar.

        Se le pone encima todo lo que antes le ganaba la puja: hambre casi máxima, energía por el
        piso, frío fuerte y salud baja.
        """
        m = generar_mundo(11, 128, 128, 50)
        s = Simulacion(m["capas"], m["meta"], cerebro=CerebroCognitivo())
        for k in ("hambre", "objetivos", "atributos", "conocimientos"):
            s.ajustes["modulos"][k] = True

        # una celda caminable con agua al lado: es la situación en la que se morían
        destino = None
        for y in range(s.terreno.alto):
            for x in range(s.terreno.ancho):
                if s.terreno.caminable(x, y) and s.terreno.agua_adyacente(x, y):
                    destino = (x, y)
                    break
            if destino:
                break
        self.assertIsNotNone(destino, "el mapa de prueba no tiene orilla caminable")

        h = HabitanteSim(1, "Sediento", destino[0] + 0.5, destino[1] + 0.5)
        h.sed, h.hambre, h.energia, h.salud, h.frio = 95.0, 95.0, 5.0, 20.0, 0.9
        s.habitantes[1] = h

        decision = s.cerebro.decidir(s, h)
        self.assertIn(decision.get("tipo"), ("beber", "ir"),
                      "con sed mortal y agua al lado decidió %r" % (decision,))
        propuesta = s.cerebro._ultima_propuesta[1]
        self.assertEqual(propuesta.goal_id, "satisfy_sed",
                         "persiguió %s en lugar de la sed" % propuesta.goal_id)

    def test_nadie_se_muere_de_sed_ni_de_hambre_en_veinte_dias(self):
        """La prueba que faltaba: nada fallaba si el mundo mataba a todos.

        Las diez horas del test de arriba no alcanzan ni de lejos. La sed tarda días en matar, así
        que todos los colapsos de población que se encontraron mirando mundos a mano —23 de 27
        muertes de sed en `gaia`, 13 de ellas con el agua pegada al cuerpo— pasaban con los tests en
        verde. Veinte días simulados sí los ve.

        Se mira la CAUSA, no la cantidad de vivos: morir de viejo, de un ataque o comiendo algo malo
        es parte del mundo. Morirse de sed o de hambre teniendo agua y comida al alcance es un bug
        del puente (ver `docs/MUERTE_POR_SED.md`).

        Arrancan con sed y hambre ya altas a propósito. Con el cuerpo lleno nadie llega en 20 días a
        la zona donde las necesidades se disputan la puja, que es justamente donde vivía el bug: el
        test pasaba igual con el bug puesto. Empezar incómodos es lo que lo convierte en una red.
        """
        m = generar_mundo(11, 128, 128, 50)
        s = Simulacion(m["capas"], m["meta"], cerebro=CerebroCognitivo())
        for k in ("hambre", "objetivos", "atributos", "conocimientos"):
            s.ajustes["modulos"][k] = True

        x, y = _tierra_firme(s)
        for i in range(1, 5):
            h = HabitanteSim(i, f"P{i}", x + 0.5 + i * 0.3, y + 0.5)
            h.sed, h.hambre = 70.0, 85.0
            s.habitantes[i] = h

        for _ in range(20 * 48):              # 20 días simulados, en tandas de media hora
            s.avanzar(30.0)

        por_hambre_o_sed = [h.causa_muerte for h in s.habitantes.values()
                            if not h.vivo and h.causa_muerte in ("sed", "hambre", "inanición")]
        self.assertEqual(por_hambre_o_sed, [],
                         "se murieron de sed o de hambre en 20 días: %s" % por_hambre_o_sed)
        self.assertTrue([h for h in s.habitantes.values() if h.vivo],
                        "no quedó nadie vivo a los 20 días")
        self.assertEqual(s.cerebro.estado(s)["sin_traducir"], {})


if __name__ == "__main__":
    unittest.main()

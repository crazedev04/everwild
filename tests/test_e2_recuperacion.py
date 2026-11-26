"""E2 — Regresión Leo/Paula/Bruno buscando a Elena: fallo repetido, cooldown,
alternativa y reconsideración, sin tocar la necesidad de compañía.

Usa el puente real (`CerebroCognitivo`) y su `decision_engine`; no simula el motor.
"""
from __future__ import annotations

import unittest

from mundo_vivo.agentes.cerebro_cognitivo import (
    CerebroCognitivo,
    motor_cognitivo_disponible,
)
from mundo_vivo.generador.pipeline import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion

_HAY_MOTOR = motor_cognitivo_disponible()

# Motivo real que devuelve el motor cuando el destino no está a la vista.
RECHAZO = "No ves a Elena; está lejos."


def _tierra_firme(s: Simulacion) -> tuple[int, int]:
    cx, cy = s.terreno.ancho // 2, s.terreno.alto // 2
    for radio in range(max(s.terreno.ancho, s.terreno.alto)):
        for dy in range(-radio, radio + 1):
            for dx in range(-radio, radio + 1):
                x, y = cx + dx, cy + dy
                if s.terreno.dentro(x, y) and s.terreno.caminable(x, y):
                    return x, y
    raise AssertionError("sin celda caminable")


def _mundo(semilla: int = 11):
    m = generar_mundo(semilla, 128, 128, 50)
    s = Simulacion(m["capas"], m["meta"])
    _tierra_firme(s)  # asegura que el mundo tiene celda caminable
    return s


@unittest.skipUnless(_HAY_MOTOR, "Cognitive Engine no está disponible")
class TestE2RegresionCompania(unittest.TestCase):
    def _cerebro(self, c: CerebroCognitivo, s: Simulacion, hid: int, nombre: str):
        h = HabitanteSim(hid, nombre, s.terreno.ancho / 2 + 0.5, s.terreno.alto / 2 + 0.5)
        s.habitantes[hid] = h
        cerebro = c._cerebro_de(s, h)
        cerebro.needs = c._necesidades(s, h)
        return h, cerebro

    def test_bloqueo_compania_genera_cooldown_y_alternativa(self):
        s = _mundo()
        c = CerebroCognitivo()
        _, cerebro = self._cerebro(c, s, 1, "Leo")
        eng = cerebro.decision_engine
        eng.state.goal_id = "satisfy_compania"
        val_compania_antes = cerebro.needs.needs["compania"].value

        for t in range(3):
            eng.register_result_for_plan(False, RECHAZO, tick=t, target="elena")

        # El objetivo entra en cooldown (no reintenta infinito).
        self.assertTrue(eng.state.failures.en_cooldown("satisfy_compania", tick=3))
        # La necesidad de compañía NO se tocó: no se simula éxito artificial.
        self.assertEqual(cerebro.needs.needs["compania"].value, val_compania_antes)
        # Con el objetivo penalizado, el árbitro elige otra cosa (no satisfy_compania).
        from cognitive_engine.decision.goal_failures import FACTOR_COOLDOWN
        g = eng.arbiter.choose(
            cerebro.needs, cerebro.personality, current_goal_id="satisfy_compania",
            social_available=eng.catalog.produces("social_contact"),
            goal_penalties={"satisfy_compania": FACTOR_COOLDOWN},
        )
        self.assertNotEqual(g.goal_id, "satisfy_compania")

    def test_reconsidera_tras_cooldown(self):
        s = _mundo()
        c = CerebroCognitivo()
        _, cerebro = self._cerebro(c, s, 2, "Paula")
        eng = cerebro.decision_engine
        eng.state.goal_id = "satisfy_compania"
        for t in range(3):
            eng.register_result_for_plan(False, RECHAZO, tick=t, target="elena")
        from cognitive_engine.decision.goal_failures import COOLDOWN_TICKS
        self.assertTrue(eng.state.failures.en_cooldown("satisfy_compania", tick=2 + COOLDOWN_TICKS - 1))
        # Expirado el cooldown, el objetivo vuelve a ser elegible.
        self.assertFalse(eng.state.failures.en_cooldown("satisfy_compania", tick=3 + COOLDOWN_TICKS))

    def test_historiales_independientes_por_habitante(self):
        s = _mundo()
        c = CerebroCognitivo()
        _, c1 = self._cerebro(c, s, 1, "Leo")
        _, c2 = self._cerebro(c, s, 2, "Paula")
        c1.decision_engine.state.goal_id = "satisfy_compania"
        for t in range(3):
            c1.decision_engine.register_result_for_plan(False, RECHAZO, tick=t, target="elena")
        self.assertTrue(c1.decision_engine.state.failures.en_cooldown("satisfy_compania", tick=3))
        self.assertFalse(c2.decision_engine.state.failures.en_cooldown("satisfy_compania", tick=3))

    def test_un_exito_limpia_el_bloqueo(self):
        s = _mundo()
        c = CerebroCognitivo()
        _, cerebro = self._cerebro(c, s, 3, "Bruno")
        eng = cerebro.decision_engine
        eng.state.goal_id = "satisfy_compania"
        for t in range(3):
            eng.register_result_for_plan(False, RECHAZO, tick=t, target="elena")
        self.assertTrue(eng.state.failures.en_cooldown("satisfy_compania", tick=3))
        eng.register_result_for_plan(True, None, tick=4, target="elena")
        self.assertFalse(eng.state.failures.en_cooldown("satisfy_compania", tick=5))


if __name__ == "__main__":
    unittest.main()
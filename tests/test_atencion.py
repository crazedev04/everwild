"""Fase L: LOD cognitivo. No todos piensan con el modelo a la vez."""
from __future__ import annotations

import unittest

from mundo_vivo.agentes.genoma import genoma_fundador
from mundo_vivo.motor.atencion import CUPO_BASE
from mundo_vivo.generador.pipeline import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion


def _mundo(n=20):
    m = generar_mundo(7, 128, 128, 50)
    s = Simulacion(m["capas"], m["meta"])
    for i in range(1, n + 1):
        h = HabitanteSim(i, "P%d" % i, 10.5 + i * 0.3, 10.5)
        h.genoma = genoma_fundador(i)
        s.habitantes[i] = h
    return s


class TestFoco(unittest.TestCase):
    def test_el_cupo_se_respeta(self):
        s = _mundo(20)
        s.repartir_atencion()
        self.assertLessEqual(len(s._foco), CUPO_BASE, "no pueden pensar todos a la vez: el modelo no da")
        self.assertGreater(len(s._foco), 0)

    def test_la_urgencia_manda(self):
        s = _mundo(20)
        sediento = s.habitantes[13]
        sediento.sed = 98.0
        s.repartir_atencion()
        self.assertIn(13, s._foco, "el que se muere de sed tiene que poder pensar")

    def test_quien_tiene_una_propuesta_pendiente_entra(self):
        s = _mundo(20)
        s.habitantes[9].propuesta = {"de": 1, "t": 0}
        s.repartir_atencion()
        self.assertIn(9, s._foco)

    def test_hay_rotacion_y_nadie_queda_afuera_para_siempre(self):
        s = _mundo(12)
        vistos = set()
        for _ in range(30):
            s.repartir_atencion()
            vistos |= s._foco
            s.t += 200.0
            s._foco_hasta = 0.0
        self.assertGreater(len(vistos), CUPO_BASE, "siempre piensan los mismos")

    def test_los_niveles_son_coherentes(self):
        s = _mundo(20)
        s.repartir_atencion()
        for h in s.habitantes.values():
            n = s.nivel_cognitivo(h)
            self.assertIn(n, (1, 2, 3))
            if h.id in s._foco:
                self.assertEqual(n, 1)
        r = s.resumen_atencion()
        self.assertEqual(r["foco"] + r["fondo"] + r["lejos"], 20)

    def test_el_que_esta_perdido_hace_una_semana_baja_a_nivel_3(self):
        s = _mundo(20)
        solo = s.habitantes[20]
        solo.x, solo.y = 100.5, 100.5          # bien lejos de todos
        s.t = 20000.0
        s.ultimo_pensado[solo.id] = 0.0
        s.repartir_atencion()
        if solo.id in s._foco:
            s._foco.discard(solo.id)
        self.assertEqual(s.nivel_cognitivo(solo), 3)

    def test_con_el_modulo_apagado_todos_piensan(self):
        s = _mundo(20)
        s.ajustes["modulos"]["atencion"] = False
        for h in s.habitantes.values():
            self.assertEqual(s.nivel_cognitivo(h), 1)


if __name__ == "__main__":
    unittest.main()

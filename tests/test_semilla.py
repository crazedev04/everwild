"""L.3 — Streams RNG independientes por subsistema.

Verifica que `derivar_semilla` produce semillas deterministas e independientes,
y que `Simulacion` expone 14 streams separados que no se interfieren entre sí.
"""
from __future__ import annotations

import random
import unittest

from mundo_vivo.motor.semilla import derivar_semilla
from mundo_vivo.motor.simulacion import Simulacion
from mundo_vivo.generador.pipeline import generar_mundo


class TestDerivarSemilla(unittest.TestCase):
    """La utilidad es pura: misma raíz+nombre → misma semilla, siempre."""

    def test_es_determinista(self):
        s1 = derivar_semilla(11, "cerebro")
        s2 = derivar_semilla(11, "cerebro")
        self.assertEqual(s1, s2)
        self.assertIsInstance(s1, int)
        self.assertGreaterEqual(s1, 0)

    def test_diferente_nombre_diferente_semilla(self):
        s_a = derivar_semilla(11, "agua")
        s_b = derivar_semilla(11, "cerebro")
        self.assertNotEqual(s_a, s_b)

    def test_diferente_raiz_diferente_semilla(self):
        s_a = derivar_semilla(11, "cerebro")
        s_b = derivar_semilla(12, "cerebro")
        self.assertNotEqual(s_a, s_b)

    def test_nombres_distintos_no_colisionan(self):
        nombres = ["cerebro", "agua", "rayos", "derrumbes", "caídas", "calor",
                   "materiales", "psique", "fauna", "objetivos", "propagacion",
                   "alimentacion", "vida", "fenomenos"]
        semillas = [derivar_semilla(11, n) for n in nombres]
        self.assertEqual(len(set(semillas)), len(nombres))


class TestSimulacionStreamsIndependientes(unittest.TestCase):
    """Simulacion expone 14 streams RNG, uno por subsistema."""

    def _sim(self, semilla=11):
        m = generar_mundo(semilla, 128, 128, 50)
        return Simulacion(m["capas"], m["meta"], cerebro=None)

    def test_existen_los_14_streams(self):
        s = self._sim()
        esperados = [
            "rng_cerebro", "rng_agua", "rng_rayos", "rng_derrumbes",
            "rng_caidas", "rng_calor", "rng_materiales", "rng_psique",
            "rng_fauna", "rng_objetivos", "rng_propagacion",
            "rng_alimentacion", "rng_vida", "rng_fenomenos",
        ]
        for nombre in esperados:
            self.assertTrue(hasattr(s, nombre), f"falta stream {nombre}")
            self.assertIsInstance(getattr(s, nombre), random.Random)

    def test_streams_no_comparten_estado(self):
        """Dos streams con distinta secuencia no producen iguales."""
        s = self._sim()
        vals_cerebro = [s.rng_cerebro.random() for _ in range(5)]
        vals_agua = [s.rng_agua.random() for _ in range(5)]
        self.assertNotEqual(vals_cerebro, vals_agua)

    def test_mismo_mundo_misma_secuencia(self):
        """Reproducibilidad: mismo mundo, misma secuencia de RNG."""
        m1 = generar_mundo(11, 64, 64, 50)
        s1 = Simulacion(m1["capas"], m1["meta"], cerebro=None)
        seq1 = [s1.rng_cerebro.random() for _ in range(10)]

        m2 = generar_mundo(11, 64, 64, 50)
        s2 = Simulacion(m2["capas"], m2["meta"], cerebro=None)
        seq2 = [s2.rng_cerebro.random() for _ in range(10)]

        self.assertEqual(seq1, seq2)

    def test_distinto_mundo_distinta_secuencia(self):
        """Diferente semilla → diferente secuencia."""
        m1 = generar_mundo(11, 64, 64, 50)
        s1 = Simulacion(m1["capas"], m1["meta"], cerebro=None)
        seq1 = [s1.rng_cerebro.random() for _ in range(10)]

        m2 = generar_mundo(42, 64, 64, 50)
        s2 = Simulacion(m2["capas"], m2["meta"], cerebro=None)
        seq2 = [s2.rng_cerebro.random() for _ in range(10)]

        self.assertNotEqual(seq1, seq2)


if __name__ == "__main__":
    unittest.main()

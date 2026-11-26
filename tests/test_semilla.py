"""Utilidad pura de derivación determinista de semillas (etapa L.2).

Valida que `motor.semilla.derivar_semilla` es determinista, reproducible,
independiente del orden de solicitud y compatible con `random.Random` y
`numpy.random.default_rng`.
"""
from __future__ import annotations

import subprocess
import sys
import unittest

import numpy as np

from mundo_vivo.motor.semilla import derivar_semilla


class TestDerivarSemilla(unittest.TestCase):
    RAIZ = 123456789

    def test_misma_raiz_mismo_nombre_misma_semilla(self):
        self.assertEqual(derivar_semilla(self.RAIZ, "fuego"), derivar_semilla(self.RAIZ, "fuego"))

    def test_raices_diferentes_producen_semillas_diferentes(self):
        self.assertNotEqual(derivar_semilla(1, "fuego"), derivar_semilla(2, "fuego"))
        self.assertNotEqual(derivar_semilla(0, "fuego"), derivar_semilla(2 ** 64 - 1, "fuego"))

    def test_nombres_diferentes_producen_semillas_diferentes(self):
        nombres = ["fuego", "fauna", "sim", "vida", "materiales", "psique"]
        semillas = [derivar_semilla(self.RAIZ, n) for n in nombres]
        self.assertEqual(len(set(semillas)), len(nombres), "cada nombre debe dar semilla distinta")

    def test_resultado_independiente_del_orden_de_solicitud(self):
        nombres = ["fuego", "fauna", "vida"]
        primero = {n: derivar_semilla(self.RAIZ, n) for n in nombres}
        for n in reversed(nombres):
            derivar_semilla(self.RAIZ, n)
        segundo = {n: derivar_semilla(self.RAIZ, n) for n in nombres}
        self.assertEqual(primero, segundo)

    def test_agregar_nombre_no_altera_resultados_previos(self):
        base = derivar_semilla(self.RAIZ, "fuego")
        for extra in ["fauna", "vida", "materiales", "psique", "nuevo_subsistema"]:
            derivar_semilla(self.RAIZ, extra)
        self.assertEqual(derivar_semilla(self.RAIZ, "fuego"), base)

    def test_reproducible_entre_procesos(self):
        codigo = (
            "from mundo_vivo.motor.semilla import derivar_semilla; "
            "print(derivar_semilla(123456789, 'fuego'))"
        )
        out = subprocess.run(
            [sys.executable, "-c", codigo],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(out.stdout.strip(), str(derivar_semilla(123456789, "fuego")))

    def test_compatible_con_random_random(self):
        semilla = derivar_semilla(self.RAIZ, "fuego")
        rng = __import__("random").Random(semilla)
        self.assertIsInstance(rng.random(), float)

    def test_compatible_con_numpy_default_rng(self):
        semilla = derivar_semilla(self.RAIZ, "fuego")
        rng = np.random.default_rng(semilla)
        self.assertIsInstance(rng.random(), float)

    def test_semilla_utiliza_al_menos_128_bits(self):
        """El resultado usa el digest SHA-256 completo (256 bits)."""
        for _ in range(20):
            semilla = derivar_semilla(self.RAIZ, f"n_{_}")
            self.assertGreaterEqual(semilla, 0)
            self.assertLessEqual(semilla, 2 ** 256 - 1)
        # al menos uno de los resultados debe superar 2^128 para confirmar que no se trunca a 128 bits
        supera_128 = any(
            derivar_semilla(self.RAIZ, f"n_{_}") > 2 ** 128 for _ in range(20)
        )
        self.assertTrue(supera_128, "se esperaba al menos una semilla superior a 2^128")

    def test_raiz_no_entero_lanza_type_error(self):
        with self.assertRaises(TypeError):
            derivar_semilla("no_entero", "fuego")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            derivar_semilla(True, "fuego")  # type: ignore[arg-type]

    def test_raiz_fuera_de_rango_lanza_value_error(self):
        with self.assertRaises(ValueError):
            derivar_semilla(-1, "fuego")
        with self.assertRaises(ValueError):
            derivar_semilla(2 ** 64, "fuego")

    def test_nombre_invalido_lanza_value_error(self):
        with self.assertRaises(ValueError):
            derivar_semilla(self.RAIZ, "")
        with self.assertRaises(ValueError):
            derivar_semilla(self.RAIZ, 123)  # type: ignore[arg-type]


class TestAislamientoDeStreamsRNG(unittest.TestCase):
    """Cada subsistema de Simulacion debe tener su propio stream de RNG aislado:
    consumir de uno no afecta a los demás, y el mismo mundo da los mismos streams."""

    RAIZ = 123456789
    NOMBRES_STREAMS = [
        "cerebro", "agua", "rayo", "derrumbe", "caida",
        "calor", "materiales", "psique", "fauna", "objetivos",
        "propagacion", "alimentacion", "vida", "fenomenos",
    ]

    def _mundo(self, semilla):
        from mundo_vivo.generador.pipeline import generar_mundo
        return generar_mundo(semilla, 64, 64, 50)

    def test_todos_los_streams_existen_y_son_instancias_de_random(self):
        import random
        from mundo_vivo.motor.simulacion import Simulacion
        m = self._mundo(self.RAIZ)
        s = Simulacion(m["capas"], m["meta"])
        for nombre in self.NOMBRES_STREAMS:
            stream = getattr(s, "rng_" + nombre, None)
            self.assertIsNotNone(stream, "falta el stream rng_%s" % nombre)
            self.assertIsInstance(stream, random.Random)

    def test_streams_son_independientes_consumir_de_uno_no_afecta_a_otro(self):
        import random
        from mundo_vivo.motor.simulacion import Simulacion
        m = self._mundo(self.RAIZ)
        s = Simulacion(m["capas"], m["meta"])
        # consumir mucho del stream de psique
        for _ in range(1000):
            s.rng_psique.random()
        # agua y materiales no deben haberse movido
        ref_agua = random.Random(derivar_semilla(self.RAIZ, "agua"))
        ref_mat = random.Random(derivar_semilla(self.RAIZ, "materiales"))
        self.assertEqual(s.rng_agua.random(), ref_agua.random())
        self.assertEqual(s.rng_materiales.random(), ref_mat.random())

    def test_mismo_mundo_mismas_secuencias(self):
        from mundo_vivo.motor.simulacion import Simulacion
        m = self._mundo(self.RAIZ)
        s1 = Simulacion(m["capas"], m["meta"])
        s2 = Simulacion(m["capas"], m["meta"])
        for nombre in self.NOMBRES_STREAMS:
            v1 = getattr(s1, "rng_" + nombre).random()
            v2 = getattr(s2, "rng_" + nombre).random()
            self.assertEqual(v1, v2, "rng_%s no es determinista por mundo" % nombre)

    def test_mundos_distintos_streams_distintos(self):
        from mundo_vivo.motor.simulacion import Simulacion
        m1 = self._mundo(1)
        m2 = self._mundo(2)
        s1 = Simulacion(m1["capas"], m1["meta"])
        s2 = Simulacion(m2["capas"], m2["meta"])
        for nombre in self.NOMBRES_STREAMS:
            v1 = getattr(s1, "rng_" + nombre).random()
            v2 = getattr(s2, "rng_" + nombre).random()
            self.assertNotEqual(v1, v2, "rng_%s debería diferir entre mundos" % nombre)


if __name__ == "__main__":
    unittest.main()

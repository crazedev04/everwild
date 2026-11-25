"""Fase 7 del plan del motor: la luz, con el mismo molde que el calor.

Lo importante de esta fase no es la lámpara: es que agregar una magnitud física nueva no haya pedido un
sistema nuevo. `_provisto_en` toma el campo por parámetro, así que `calor_disponible` y
`energia_disponible` son la misma función, y la validación de catálogo de la fase 0 vale igual acá (una
estructura que provee corriente sin receta que la construya es el mismo agujero que tuvo el horno).
"""
from __future__ import annotations

import unittest

from mundo_vivo import catalogos
from tests.test_calor import _construir, _mundo
from tests.test_metalurgia import _hacer


class TestEnergia(unittest.TestCase):
    def test_sin_nada_no_hay_corriente(self):
        s, h = _mundo()
        self.assertEqual(s.energia_disponible(h), 0.0)

    def test_la_fogata_da_calor_pero_no_corriente(self):
        s, h = _mundo()
        s.fogatas.append({"x": h.x, "y": h.y, "hasta": 1e9, "dueno": 1})
        self.assertEqual(s.calor_disponible(h), 600.0)
        self.assertEqual(s.energia_disponible(h), 0.0, "una fogata no es una dinamo")

    def test_la_pila_da_poco_y_la_dinamo_mucho(self):
        s, h = _mundo()
        self.assertTrue(_hacer(s, h, "pila")[0])
        self.assertEqual(s.energia_disponible(h), 6.0)
        self.assertTrue(any(r["tipo"] == "pila" for r in s.refugios), "la pila es una estructura")
        s.refugios.append({"rid": 50, "x": h.x, "y": h.y, "dueno": 1, "tipo": "dinamo",
                           "nombre": "dinamo", "abrigo": 0.0, "t": 0})
        self.assertEqual(s.energia_disponible(h), 80.0, "es el máximo, no la suma")

    def test_la_lampara_pide_corriente_y_la_pila_no_alcanza(self):
        s, h = _mundo()
        self.assertFalse(_hacer(s, h, "lampara")[0], "sin corriente no hay luz")
        self.assertTrue(_hacer(s, h, "pila")[0])
        ok, texto = _hacer(s, h, "lampara")
        self.assertFalse(ok, "6 W no encienden nada: la lámpara pide 50")
        self.assertIn("corriente", texto)
        s.refugios.append({"rid": 50, "x": h.x, "y": h.y, "dueno": 1, "tipo": "dinamo",
                           "nombre": "dinamo", "abrigo": 0.0, "t": 0})
        ok, texto = _hacer(s, h, "lampara")
        self.assertTrue(ok, texto)

    def test_la_corriente_tambien_cae_con_la_distancia(self):
        s, h = _mundo()
        s.refugios.append({"rid": 50, "x": h.x, "y": h.y, "dueno": 1, "tipo": "dinamo",
                           "nombre": "dinamo", "abrigo": 0.0, "t": 0})
        self.assertEqual(s.energia_disponible(h), 80.0)
        # el mundo de prueba tiene celdas de 50 m, así que el radio de 6 m queda en el mínimo de 1,5 celdas
        h.x += s.celdas(6.0, minimo=1.5) + 1.0
        self.assertEqual(s.energia_disponible(h), 0.0, "la corriente no llega sola hasta la otra cuadra")

    def test_la_validacion_de_catalogo_vale_igual_para_la_corriente(self):
        """El agujero del horno no se puede repetir con la energía."""
        est = {"turbina": {"id": "turbina", "provee": {"energia_W": 500}, "_archivo": "prueba.json"}}
        with self.assertRaises(catalogos.ErrorDeCatalogo) as e:
            catalogos._validar_estructuras({}, est)
        self.assertIn("no hay forma de tenerla", str(e.exception))

    def test_la_cadena_entera_existe(self):
        s, _ = _mundo()
        for rid in ("fundir_cobre", "cable", "pila", "dinamo", "lampara"):
            self.assertIn(rid, s.recetas, "falta el escalón %s" % rid)
        self.assertIn("energia_W", s.recetas["lampara"]["requiere"])
        self.assertEqual(s.recetas["dinamo"]["requiere"]["calor_C"], 1200,
                         "una dinamo pide una fragua: no se hace en la edad de piedra")


class TestHitos(unittest.TestCase):
    def test_la_primera_corriente_es_un_hito(self):
        s, h = _mundo()
        self.assertTrue(_hacer(s, h, "pila")[0])
        self.assertIn("luz", s.hitos)

    def test_el_primer_metal_es_un_hito(self):
        s, h = _mundo()
        self.assertTrue(_construir(s, h, "horno_de_barro")[0])
        self.assertNotIn("metalurgia", s.hitos)
        self.assertTrue(_hacer(s, h, "fundir_cobre")[0])
        self.assertIn("metalurgia", s.hitos)


if __name__ == "__main__":
    unittest.main()

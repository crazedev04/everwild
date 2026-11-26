"""Fase F: especies que mutan y colonias que se propagan sin caminar."""
from __future__ import annotations

import random
import unittest

from mundo_vivo.generador.pipeline import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion
from mundo_vivo.registro import Registro


def _mundo(n=192):
    m = generar_mundo(7, n, n, 50)
    return Simulacion(m["capas"], m["meta"])


class TestMutaciones(unittest.TestCase):
    def test_las_variantes_heredan_todo_de_su_base(self):
        """Agregar una variante tiene que costar 4 líneas de JSON, no copiar una especie entera."""
        s = _mundo(128)
        base, var = s.especies["lobo"], s.especies["lobo_blanco"]
        self.assertEqual(var["medio"], base["medio"])
        self.assertEqual(var["dieta"], base["dieta"])
        self.assertEqual(var["peligro"], base["peligro"])
        self.assertNotEqual(var["frio_min"], base["frio_min"], "la variante tiene que diferenciarse en algo")

    def test_muta_donde_se_dan_las_condiciones(self):
        s = _mundo(128)
        f = s.fauna
        f.temp_fn = lambda x, y: -10.0            # bien frío: es donde sale el lobo blanco
        f.rng = random.Random(5)
        salidas = {f._mutar("lobo", 10, 10) for _ in range(2000)}
        self.assertIn("lobo_blanco", salidas)

    def test_no_muta_donde_no_corresponde(self):
        s = _mundo(128)
        f = s.fauna
        f.temp_fn = lambda x, y: 25.0             # calor: el lobo blanco no tiene sentido
        f.rng = random.Random(5)
        salidas = {f._mutar("lobo", 10, 10) for _ in range(2000)}
        self.assertEqual(salidas, {"lobo"})

    def test_una_especie_sin_mutacion_nunca_cambia(self):
        s = _mundo(128)
        f = s.fauna
        f.rng = random.Random(5)
        self.assertEqual({f._mutar("conejo", 10, 10) for _ in range(500)}, {"conejo"})

    def test_queda_anotado_como_suceso(self):
        s = _mundo(128)
        s.fauna.mutaciones.append({"de": "lobo", "a": "lobo_blanco", "x": 10, "y": 10, "t": 0})
        s._avisar_mutaciones()
        self.assertTrue(any(e["tipo"] == "mutacion" for e in s._eventos))
        self.assertFalse(s.fauna.mutaciones, "la lista se vacía después de avisar")


class TestColonias(unittest.TestCase):
    def test_las_colonias_salen_de_los_datos(self):
        reg = Registro.cargar()
        self.assertIn("moho_de_pantano", reg.de_tipo("colonia"))
        for cid, d in reg.de_tipo("colonia").items():
            self.assertTrue(d.get("biomas"), "%s no dice dónde crece" % cid)
            self.assertTrue(d.get("crece"), "%s no dice cómo crece" % cid)

    def test_aparecen_y_se_expanden(self):
        s = _mundo()
        for _ in range(60):
            s.avanzar(1440.0)
        total = sum(len(c) for c in s.colonias.values())
        self.assertGreater(total, 1, "en dos meses tendrían que haberse expandido")

    def test_se_pueden_cosechar(self):
        s = _mundo(128)
        h = HabitanteSim(1, "Prueba", 10.5, 10.5)
        s.habitantes[1] = h
        s.colonias["moho_de_pantano"] = {(10, 10)}
        cos = s.cosechar_colonia(h)
        self.assertIsNotNone(cos)
        self.assertEqual(cos[0], "hongo_visionario")
        ok, txt = s._accion_juntar(h, {"material": ""})
        self.assertTrue(ok)
        self.assertGreater(h.inventario.get("hongo_visionario", 0), 0,
                           "una colonia puede traer un material a donde no existía")

    def test_sin_el_modulo_no_crecen(self):
        s = _mundo(128)
        s.ajustes["modulos"]["colonias"] = False
        for _ in range(30):
            s.avanzar(1440.0)
        self.assertFalse(any(s.colonias.values()))

    def test_sobreviven_al_guardado(self):
        s = _mundo(128)
        s.colonias["moho_de_pantano"] = {(5, 6), (5, 7)}
        d = s.exportar_colonias()
        s2 = _mundo(128)
        s2.importar_colonias(d)
        self.assertEqual(s2.colonias["moho_de_pantano"], {(5, 6), (5, 7)})


if __name__ == "__main__":
    unittest.main()

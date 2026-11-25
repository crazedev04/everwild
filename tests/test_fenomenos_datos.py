"""Fase E: los fenómenos son datos. Las primitivas de efecto son código; las combinaciones, JSON."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mundo_vivo.motor.generador import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion
from mundo_vivo.persistencia import db, mundo_io, sim_io


def _mundo():
    m = generar_mundo(7, 128, 128, 50)
    s = Simulacion(m["capas"], m["meta"])
    s.ajustes["modulos"]["fenomenos"] = True
    h = HabitanteSim(1, "Prueba", 10.5, 10.5)
    s.habitantes[1] = h
    return s, h


class TestMeteorito(unittest.TestCase):
    def test_el_meteorito_sale_de_los_datos(self):
        s, _ = _mundo()
        self.assertIn("meteorito", s.fenomenos)
        efectos = {e["tipo"] for e in s.fenomenos["meteorito"]["efectos"]}
        self.assertEqual(efectos, {"marca", "sembrar", "encender_fuego", "dano_area", "evento", "recuerdo"})

    def test_deja_crater_siembra_material_y_avisa(self):
        s, _ = _mundo()
        s.rng.seed(3)
        s._disparar_fenomeno(s.fenomenos["meteorito"])
        self.assertTrue(s.marcas, "tiene que dejar el cráter")
        self.assertEqual(s.marcas[0]["clave"], "crater")
        self.assertTrue(any("hierro_del_cielo" in k for k in s.depositos), "tiene que sembrar el material")
        self.assertTrue(any(e["tipo"] == "meteorito" for e in s._eventos), "tiene que quedar como suceso")

    def test_el_material_sembrado_se_puede_juntar(self):
        """La prueba de que sirve de verdad: trae un material que antes no existía en ese bioma."""
        s, h = _mundo()
        antes = "hierro_del_cielo" in s.disponibles(h)
        k = "%d,%d,hierro_del_cielo" % (int(h.x) // s.zona, int(h.y) // s.zona)
        s.depositos[k] = 6.0
        self.assertFalse(antes)
        self.assertIn("hierro_del_cielo", s.disponibles(h), "lo que cayó del cielo tiene que poder juntarse")
        self.assertGreater(s.restante(h.x, h.y, "hierro_del_cielo"), 0)

    def test_lastima_a_quien_este_cerca(self):
        s, h = _mundo()
        h.x, h.y = 20.5, 20.5
        antes = h.salud
        s._efecto_fenomeno(s.fenomenos["meteorito"],
                           {"tipo": "dano_area", "radio_m": 500, "dano": 30, "causa": "prueba"}, 20, 20)
        self.assertLess(h.salud, antes)

    def test_un_fenomeno_apagado_no_pasa(self):
        s, _ = _mundo()
        s.ajustes["modulos"]["fenomenos"] = False
        for _ in range(100):
            s._paso_fenomenos(120.0)
        self.assertFalse(s.marcas)

    def test_sobrevive_al_guardado(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = mundo_io.crear_mundo(Path(d), 777, 128, 128, tam_celda_m=50)
            con = db.abrir(ruta)
            try:
                sim_io.crear_habitantes_iniciales(con, 4)
                sim = sim_io.cargar_simulacion(con)
                sim.marcas.append({"clave": "crater", "x": 5.0, "y": 6.0, "r": 2.4, "t": 100})
                sim.depositos["1,1,hierro_del_cielo"] = 4.0
                sim_io.guardar_simulacion(con, sim)
                s2 = sim_io.cargar_simulacion(con)
                self.assertEqual(len(s2.marcas), 1)
                self.assertEqual(s2.marcas[0]["clave"], "crater")
                self.assertAlmostEqual(s2.depositos["1,1,hierro_del_cielo"], 4.0)
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()

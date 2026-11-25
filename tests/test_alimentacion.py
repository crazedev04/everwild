"""Fase C: hambre y alimentos. Las cuatro barras son independientes."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mundo_vivo.agentes import ajustes as aj
from mundo_vivo.agentes.mente import CerebroHibrido
from mundo_vivo.motor.alimentacion import HAMBRE_DESPIERTA
from mundo_vivo.persistencia import db, mundo_io, sim_io


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ruta = mundo_io.crear_mundo(Path(self.tmp.name), 777, 128, 128, tam_celda_m=50)
        self.con = db.abrir(ruta)
        sim_io.crear_habitantes_iniciales(self.con, 4)
        aj.guardar(self.con, {"modulos": {"cerebro_llm": False, "hambre": True}})
        self.cerebro = CerebroHibrido(self.con)
        self.sim = sim_io.cargar_simulacion(self.con, cerebro=self.cerebro)
        self.h = self.sim.habitantes[1]

    def tearDown(self):
        self.cerebro.cliente._pool.shutdown(wait=False, cancel_futures=True)
        self.con.close()
        self.tmp.cleanup()


class TestAlimentos(_Base):
    def test_lo_cocinado_alimenta_mas_que_lo_crudo(self):
        """Y sale del JSON, no de un número escrito en el motor."""
        crudo = self.sim.alimentos["carne"]["crudo"]["hambre"]
        cocido = self.sim.alimentos["carne_cocida"]["cocinado"]["hambre"]
        self.assertGreater(cocido, crudo)

    def test_comer_baja_el_hambre_y_lo_podrido_saca_salud(self):
        self.h.hambre, self.h.inventario = 70.0, {"carne_cocida": 1}
        ok, _ = self.sim._accion_comer(self.h, {})
        self.assertTrue(ok)
        self.assertLess(self.h.hambre, 70.0)
        self.h.inventario, antes = {"podrido": 1}, self.h.salud
        self.sim.rng.seed(1)
        self.sim._accion_comer(self.h, {})
        self.assertLess(self.h.salud, antes, "lo podrido tiene que hacer mal")

    def test_sin_comer_se_muere(self):
        self.h.inventario = {}
        for _ in range(20000):
            self.sim._paso_hambre(self.h, 1.0, False)
            if self.h.salud <= 0:
                break
        self.assertLessEqual(self.h.salud, 0.0, "el ayuno tiene que matar, aunque lento")

    def test_las_barras_son_independientes(self):
        """Bien comido pero sin energía, o lleno pero herido: tiene que poder pasar."""
        self.h.hambre, self.h.energia, self.h.salud, self.h.sed = 0.0, 10.0, 30.0, 5.0
        self.sim._paso_hambre(self.h, 10.0, False)
        self.assertLess(self.h.hambre, 5.0, "comer no debería subir la energía por arte de magia")
        self.assertLess(self.h.energia, 20.0)
        self.assertLess(self.h.salud, 40.0)


class TestNoSeDuermeConHambre(_Base):
    def test_el_hambre_lo_despierta_y_come_antes_de_volver_a_dormir(self):
        """Durmiendo con hambre: se despierta, come y recién ahí sigue. Si no tuviera comida volvería a
        dormirse, que también está bien; lo que no puede pasar es morirse con comida encima."""
        self.h.hambre, self.h.energia, self.h.sed = HAMBRE_DESPIERTA + 5, 50.0, 10.0
        self.h.inventario = {"carne_cocida": 2}
        self.h.accion, self.h.hasta = "durmiendo", self.sim.t + 400
        for _ in range(30):
            self.sim._actualizar(self.h, 1.0)
            if self.h.hambre < HAMBRE_DESPIERTA - 5:
                break
        self.assertLess(self.h.hambre, HAMBRE_DESPIERTA, "se tiene que haber despertado a comer")

    def test_con_hambre_alta_come_en_vez_de_dormir(self):
        # con energía suficiente para levantarse: con la energía en rojo primero se duerme, a propósito
        self.h.hambre, self.h.energia, self.h.sed = HAMBRE_DESPIERTA + 5, 60.0, 10.0
        self.h.inventario = {"carne_cocida": 1}
        acc = self.cerebro._reflejos(self.sim, self.h)
        self.assertEqual(acc["tipo"], "comer", "si no, se duerme, se despierta de hambre y entra en bucle")

    def test_la_sed_le_gana_al_hambre(self):
        self.h.hambre, self.h.sed = 95.0, 95.0
        self.h.inventario = {"carne_cocida": 1}
        acc = self.cerebro._reflejos(self.sim, self.h)
        self.assertNotEqual(acc["tipo"], "comer", "la sed mata en horas; el hambre en días")


class TestMundosViejos(_Base):
    def test_el_modulo_viene_apagado_y_no_pasa_nada(self):
        self.sim.ajustes["modulos"]["hambre"] = False
        self.h.hambre = 0.0
        self.sim._paso_hambre(self.h, 1000.0, False)
        self.assertEqual(self.h.hambre, 0.0, "con el módulo apagado el hambre no corre")

    def test_el_hambre_sobrevive_al_guardado(self):
        self.h.hambre = 42.5
        sim_io.guardar_simulacion(self.con, self.sim)
        s2 = sim_io.cargar_simulacion(self.con, self.cerebro)
        self.assertAlmostEqual(s2.habitantes[1].hambre, 42.5, places=1)


if __name__ == "__main__":
    unittest.main()

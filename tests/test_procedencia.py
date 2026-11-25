"""Fase I: de dónde salió cada cosa que uno cree.

Antes un rumor valía lo mismo que algo visto con los propios ojos. El documento de arquitectura lo pide
explícitamente en su sección 3.1: «escuchar algo no significa que sea verdadero».
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mundo_vivo.agentes import ajustes as aj
from mundo_vivo.agentes.mente import CerebroHibrido, _procedencia
from mundo_vivo.persistencia import db, mundo_io, sim_io
from mundo_vivo.persistencia.memoria import MemoriaPrivada


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ruta = mundo_io.crear_mundo(Path(self.tmp.name), 777, 128, 128, tam_celda_m=50)
        self.con = db.abrir(ruta)
        sim_io.crear_habitantes_iniciales(self.con, 4)
        aj.guardar(self.con, {"modulos": {"cerebro_llm": False, "hambre": False}})
        self.cerebro = CerebroHibrido(self.con)
        self.sim = sim_io.cargar_simulacion(self.con, cerebro=self.cerebro)

    def tearDown(self):
        self.cerebro.cliente._pool.shutdown(wait=False, cancel_futures=True)
        self.con.close()
        self.tmp.cleanup()


class TestProcedencia(_Base):
    def test_se_guarda_de_quien_vino_y_cuanto_se_le_cree(self):
        mem = MemoriaPrivada(self.con, 1)
        mem.agregar(100, "episodica", "Hay agua al norte", 0.5, origen="oido", de_quien=2, certeza=0.4)
        m = mem.recientes(1)[0]
        self.assertEqual(m["origen"], "oido")
        self.assertEqual(m["de_quien"], 2)
        self.assertAlmostEqual(m["certeza"], 0.4, places=3)

    def test_lo_vivido_tiene_certeza_plena_por_defecto(self):
        mem = MemoriaPrivada(self.con, 1)
        mem.agregar(100, "episodica", "Te quemaste con un incendio", 0.8)
        m = mem.recientes(1)[0]
        self.assertEqual(m["origen"], "vivido")
        self.assertAlmostEqual(m["certeza"], 1.0)
        self.assertIsNone(m["de_quien"])

    def test_hablar_deja_un_recuerdo_OIDO_en_quien_escucha(self):
        a, b = self.sim.habitantes[1], self.sim.habitantes[2]
        b.x, b.y = a.x, a.y
        ok, _ = self.sim._accion_hablar(a, {"a": b.id, "mensaje": "Vi agua hacia el norte, cerca de las piedras"})
        self.assertTrue(ok)
        sim_io.volcar_eventos(self.con, self.sim)
        oidos = [m for m in MemoriaPrivada(self.con, b.id).recientes(10) if m["origen"] == "oido"]
        self.assertTrue(oidos, "lo que le dijeron tiene que quedarle como recuerdo oído")
        self.assertEqual(oidos[0]["de_quien"], a.id)
        self.assertLess(oidos[0]["certeza"], 1.0, "un rumor no puede valer como algo visto")

    def test_a_la_familia_se_le_cree_mas_que_a_un_desconocido(self):
        a, b = self.sim.habitantes[1], self.sim.habitantes[2]
        desconocido = self.sim.certeza_de(a, b)
        b.madre_id = a.id                      # ahora es su hijo
        self.assertGreater(self.sim.certeza_de(a, b), desconocido)

    def test_la_certeza_siempre_queda_en_un_rango_razonable(self):
        a, b = self.sim.habitantes[1], self.sim.habitantes[2]
        c = self.sim.certeza_de(a, b)
        self.assertGreaterEqual(c, 0.25)
        self.assertLessEqual(c, 0.95)


class TestComoSeLePresenta(unittest.TestCase):
    """El modelo tiene que VER la diferencia, si no trata un rumor como un hecho."""

    def test_un_rumor_se_marca_como_tal(self):
        self.assertIn("contaron", _procedencia({"origen": "oido", "certeza": 0.6}))
        self.assertIn("no sabés si es cierto", _procedencia({"origen": "oido", "certeza": 0.3}))
        self.assertIn("creés", _procedencia({"origen": "oido", "certeza": 0.9}))

    def test_lo_vivido_no_lleva_aclaracion(self):
        self.assertEqual(_procedencia({"origen": "vivido", "certeza": 1.0}), "")
        self.assertEqual(_procedencia({}), "")

    def test_lo_inferido_se_distingue(self):
        self.assertIn("lo pensaste vos", _procedencia({"origen": "inferido"}))


class TestMundoViejo(_Base):
    def test_los_recuerdos_de_antes_siguen_valiendo(self):
        """La migración 0008 pone certeza 1.0 y origen vivido: que es lo que eran."""
        mem = MemoriaPrivada(self.con, 1)
        mem.agregar(100, "episodica", "Algo que pasó antes de la migración", 0.5)
        m = mem.recientes(1)[0]
        self.assertAlmostEqual(m["certeza"], 1.0)


if __name__ == "__main__":
    unittest.main()

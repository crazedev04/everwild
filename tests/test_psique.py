"""Plantas que mueven la cabeza: psicoactivos, visiones y rasgos que se corren un rato.

Lo importante del diseño: **una alucinación es un recuerdo con procedencia `inferido` y certeza baja**
(fase I). La persona la recuerda, pero el sistema sabe que no la vivió, y si la cuenta el que escucha la
recibe como rumor. Así una visión puede volverse leyenda sin que nadie mienta.
"""
from __future__ import annotations

import unittest

from mundo_vivo.agentes.genoma import genoma_fundador
from mundo_vivo.motor.generador import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion
from mundo_vivo.registro import Registro


def _mundo():
    m = generar_mundo(7, 128, 128, 50)
    s = Simulacion(m["capas"], m["meta"])
    s.ajustes["modulos"]["hambre"] = True
    h = HabitanteSim(1, "Prueba", 10.5, 10.5)
    h.genoma = genoma_fundador(7)
    s.habitantes[1] = h
    return s, h


class TestPlantasEnDatos(unittest.TestCase):
    def test_las_plantas_declaran_su_efecto(self):
        reg = Registro.cargar()
        for pid in ("hongo_visionario", "cactus_amargo", "baya_del_sueno"):
            d = reg.uno("material", pid)
            self.assertIsNotNone(d, "falta la planta %s" % pid)
            ps = d.get("psicoactivo")
            self.assertIsNotNone(ps, "%s no declara qué hace" % pid)
            self.assertGreater(ps.get("dura_min", 0), 0)
            self.assertTrue(ps.get("nombre_efecto"), "%s no dice qué se siente" % pid)

    def test_se_pueden_juntar_del_mundo(self):
        reg = Registro.cargar()
        for pid in ("hongo_visionario", "cactus_amargo", "baya_del_sueno"):
            self.assertTrue((reg.uno("material", pid) or {}).get("recoleccion", {}).get("biomas"),
                            "%s no crece en ningún lado" % pid)

    def test_el_motor_las_compila_sin_conocerlas_por_nombre(self):
        s, _ = _mundo()
        self.assertGreaterEqual(len(s.psicoactivos), 3)


class TestEfecto(unittest.TestCase):
    def test_comerla_corre_los_rasgos_y_se_siente(self):
        s, h = _mundo()
        antes = h.rasgo("curiosidad")
        h.inventario = {"hongo_visionario": 1}
        ok, texto = s._accion_comer(h, {})
        self.assertTrue(ok)
        self.assertIn("colores", texto)
        self.assertGreater(h.rasgo("curiosidad"), antes, "el hongo tiene que abrir la cabeza")
        self.assertGreater(s.bono_inventiva(h), 0.0)
        self.assertTrue(s.describir_viaje(h))

    def test_al_pasarse_el_efecto_los_rasgos_vuelven(self):
        """Un viaje no te cambia el carácter para siempre; lo que recordás de él, sí."""
        s, h = _mundo()
        antes = h.rasgo("curiosidad")
        h.inventario = {"hongo_visionario": 1}
        s._accion_comer(h, {})
        s.t = h.viaje["hasta"] + 1
        s._paso_psique(h, 1.0)
        self.assertIsNone(s.bajo_efecto(h))
        self.assertAlmostEqual(h.rasgo("curiosidad"), antes, places=5)

    def test_una_vision_queda_como_recuerdo_INFERIDO_y_poco_confiable(self):
        s, h = _mundo()
        h.inventario = {"hongo_visionario": 1}
        s._accion_comer(h, {})
        s._eventos.clear()
        s.rng.seed(3)
        for _ in range(400):
            s.t += 10.0
            s._paso_psique(h, 10.0)
            if any((e.get("datos") or {}).get("origen") == "inferido" for e in s._eventos):
                break
        visiones = [e for e in s._eventos if (e.get("datos") or {}).get("origen") == "inferido"]
        self.assertTrue(visiones, "con 0,45 de probabilidad tendría que haber visto algo")
        d = visiones[0]["datos"]
        self.assertEqual(d["origen"], "inferido", "no lo vivió: lo imaginó")
        self.assertLess(d["certeza"], 0.5, "una visión no puede valer como algo visto de verdad")

    def test_sin_el_modulo_no_pasa_nada(self):
        s, h = _mundo()
        s.ajustes["modulos"]["psique"] = False
        h.inventario = {"hongo_visionario": 1}
        antes = h.rasgo("curiosidad")
        s._accion_comer(h, {})
        self.assertIsNone(s.bajo_efecto(h))
        self.assertAlmostEqual(h.rasgo("curiosidad"), antes)

    def test_el_viaje_sobrevive_al_guardado(self):
        import tempfile
        from pathlib import Path
        from mundo_vivo.persistencia import db, mundo_io, sim_io
        with tempfile.TemporaryDirectory() as d:
            ruta = mundo_io.crear_mundo(Path(d), 777, 128, 128, tam_celda_m=50)
            con = db.abrir(ruta)
            try:
                sim_io.crear_habitantes_iniciales(con, 4)
                sim = sim_io.cargar_simulacion(con)
                h = sim.habitantes[1]
                h.inventario = {"hongo_visionario": 1}
                sim._accion_comer(h, {})
                sim_io.guardar_simulacion(con, sim)
                s2 = sim_io.cargar_simulacion(con)
                self.assertEqual(s2.habitantes[1].viaje["item"], "hongo_visionario")
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()

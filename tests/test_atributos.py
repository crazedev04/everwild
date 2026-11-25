"""Fase K: fuerza, resistencia y pulso mejoran con el uso y se oxidan sin él.

Pedido del usuario: «que no solamente suba el hambre, suba la vida, la fuerza, que mejore; con más fuerza
pueden hacer tal cosa, lo mismo las habilidades».
"""
from __future__ import annotations

import unittest

from mundo_vivo.motor.atributos import ATRIBUTOS, BASE
from mundo_vivo.motor.generador import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion


def _mundo():
    m = generar_mundo(7, 128, 128, 50)
    s = Simulacion(m["capas"], m["meta"])
    s.ajustes["modulos"]["atributos"] = True
    h = HabitanteSim(1, "Prueba", 10.5, 10.5)
    s.habitantes[1] = h
    return s, h


class TestAtributos(unittest.TestCase):
    def test_arrancan_en_la_base(self):
        s, h = _mundo()
        for n in ATRIBUTOS:
            self.assertAlmostEqual(s.atributo(h, n), BASE)

    def test_suben_con_el_uso_y_con_rendimientos_decrecientes(self):
        s, h = _mundo()
        s.entrenar(h, "fuerza")
        primero = s.atributo(h, "fuerza") - BASE
        for _ in range(300):
            s.entrenar(h, "fuerza")
        alto = s.atributo(h, "fuerza")
        s.entrenar(h, "fuerza")
        ultimo = s.atributo(h, "fuerza") - alto
        self.assertGreater(alto, BASE)
        self.assertLess(ultimo, primero, "subir de alto tiene que costar más que subir de bajo")

    def test_no_se_progresa_con_hambre_ni_herido(self):
        """Para mejorar hay que estar comido y entero."""
        s, h = _mundo()
        s.ajustes["modulos"]["hambre"] = True
        h.hambre = 90.0
        s.entrenar(h, "fuerza")
        self.assertAlmostEqual(s.atributo(h, "fuerza"), BASE, msg="con hambre no se progresa")
        h.hambre, h.salud = 10.0, 20.0
        s.entrenar(h, "fuerza")
        self.assertAlmostEqual(s.atributo(h, "fuerza"), BASE, msg="herido tampoco")
        h.salud = 100.0
        s.entrenar(h, "fuerza")
        self.assertGreater(s.atributo(h, "fuerza"), BASE, msg="comido y sano sí")

    def test_lo_que_no_se_usa_se_oxida(self):
        s, h = _mundo()
        for _ in range(300):
            s.entrenar(h, "fuerza")
        antes = s.atributo(h, "fuerza")
        h.accion = "esperando"
        for _ in range(60):
            s._paso_atributos(h, 1440.0)
        self.assertLess(s.atributo(h, "fuerza"), antes, "sin usarla la fuerza baja")
        self.assertGreater(s.atributo(h, "fuerza"), 0.0, "pero no se pierde del todo")

    def test_cada_actividad_entrena_lo_suyo(self):
        s, h = _mundo()
        h.accion = "fabricando"
        for _ in range(200):
            s._paso_atributos(h, 20.0)
        self.assertGreater(s.atributo(h, "pulso"), BASE, "fabricar entrena el pulso")
        self.assertLess(s.atributo(h, "fuerza"), BASE + 1e-9, "y no la fuerza")

    def test_la_fuerza_deja_cargar_mas(self):
        s, h = _mundo()
        poco = s.carga_maxima(h)
        for _ in range(600):
            s.entrenar(h, "fuerza")
        self.assertGreater(s.carga_maxima(h), poco)

    def test_la_fuerza_ayuda_a_cazar_aunque_no_tenga_arma(self):
        s, h = _mundo()
        flojo = s.bono_arma(h)[0]
        for _ in range(600):
            s.entrenar(h, "fuerza")
        self.assertGreater(s.bono_arma(h)[0], flojo)


class TestDestreza(unittest.TestCase):
    def test_practicar_baja_el_tiempo_de_esa_receta(self):
        s, h = _mundo()
        r = s.recetas["cuerda"]
        antes = s.tiempo_de_receta(h, r)
        for _ in range(30):
            s.practicar(h, "cuerda")
        self.assertLess(s.tiempo_de_receta(h, r), antes)
        self.assertGreater(s.destreza(h, "cuerda"), 0.5)

    def test_la_destreza_es_por_receta_y_no_se_contagia(self):
        s, h = _mundo()
        for _ in range(20):
            s.practicar(h, "cuerda")
        self.assertGreater(s.destreza(h, "cuerda"), 0.0)
        self.assertEqual(s.destreza(h, "lanza"), 0.0, "practicar cuerdas no enseña a hacer lanzas")

    def test_nunca_baja_de_la_mitad_del_tiempo(self):
        s, h = _mundo()
        r = s.recetas["cuerda"]
        for _ in range(500):
            s.practicar(h, "cuerda")
            s.entrenar(h, "pulso")
        self.assertGreaterEqual(s.tiempo_de_receta(h, r), r["tiempo_min"] * 0.5)


class TestConModuloApagado(unittest.TestCase):
    def test_apagado_no_hace_nada(self):
        s, h = _mundo()
        s.ajustes["modulos"]["atributos"] = False
        s.entrenar(h, "fuerza")
        s.practicar(h, "cuerda")
        self.assertAlmostEqual(s.atributo(h, "fuerza"), BASE)
        self.assertEqual(s.destreza(h, "cuerda"), 0.0)


if __name__ == "__main__":
    unittest.main()

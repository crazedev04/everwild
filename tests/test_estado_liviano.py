"""Etapa 3: el estado que viaja 10 veces por segundo no lleva lo que nadie dibuja.

El mapa se dibuja con la posición y la acción; los atributos, las barras finas y la
estructura del mundo cambian mucho más lento que un cuadro. Esto separa el estado
liviano (cada 100 ms) del bloque pesado (una vez por segundo).
"""
from __future__ import annotations

import unittest

from mundo_vivo.agentes.genoma import genoma_fundador
from mundo_vivo.generador.pipeline import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion


def _mundo():
    m = generar_mundo(7, 96, 96, 50)
    s = Simulacion(m["capas"], m["meta"])
    h = HabitanteSim(1, "Prueba", 10.5, 10.5)
    h.genoma = genoma_fundador(1)
    s.habitantes[1] = h
    return s, h


class TestEstadoLiviano(unittest.TestCase):
    def test_mapa_no_lleva_lo_que_solo_ve_la_ficha(self):
        _, h = _mundo()
        d = h.a_publico_mapa()
        for campo in ("id", "nombre", "x", "y", "vivo", "accion", "sexo", "nac", "en_fuego", "antorcha"):
            self.assertIn(campo, d)
        for campo in ("atributos", "salud", "sed", "energia", "hambre", "objetivo", "embarazada", "montado"):
            self.assertNotIn(campo, d, "%s va por la ficha, no en cada cuadro" % campo)

    def test_liviano_sin_bloques_no_manda_fuego_ni_estructuras(self):
        s, _ = _mundo()
        from mundo_vivo.api.presentador import estado_liviano
        d = estado_liviano(s)
        self.assertIn("habitantes", d)
        for campo in ("fuego", "fogatas", "refugios", "ruinas", "senderos", "aldeas", "colonias"):
            self.assertNotIn(campo, d)

    def test_liviano_con_bloques_manda_lo_pesado(self):
        s, _ = _mundo()
        from mundo_vivo.api.presentador import estado_liviano
        d = estado_liviano(s, bloques=True)
        for campo in ("fuego", "fogatas", "refugios", "senderos", "aldeas", "colonias"):
            self.assertIn(campo, d)

    def test_estado_completo_sigue_igual(self):
        s, _ = _mundo()
        from mundo_vivo.api.presentador import estado_completo
        d = estado_completo(s)
        hb = d["habitantes"][0]
        self.assertIn("atributos", hb)
        self.assertIn("salud", hb)
        self.assertIn("fuego", d)


class TestMotorNoConoceVisor(unittest.TestCase):
    def test_simulacion_no_expone_estado_publico(self):
        from mundo_vivo.motor.simulacion import Simulacion
        for nombre in ("estado_publico", "estado_publico_liviano", "_estado_base"):
            self.assertFalse(hasattr(Simulacion, nombre),
                             "el motor no debe conocer al visor: %s" % nombre)

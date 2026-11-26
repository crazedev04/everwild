"""Fase H: las frases de temperamento y los disparadores de personalidad salen de los DATOS.

Era la perilla que hacía falta para ajustar que no se vuelvan cautelosos demasiado rápido sin tocar
cuatro archivos de Python con deltas literales desparramados.
"""
from __future__ import annotations

import unittest

from mundo_vivo.agentes.genoma import RASGOS, describir_temperamento, genoma_fundador
from mundo_vivo.generador.pipeline import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion
from mundo_vivo.registro import Registro

# copia congelada de los deltas que estaban en el código
EXPERIENCIAS_ORIG = {
    "ataque_de_animal": {"cautela": 0.03, "audacia": -0.02},
    "cazar_con_exito": {"audacia": 0.02, "resiliencia": 0.01},
    "cazar_y_salir_herido": {"audacia": -0.015, "cautela": 0.015},
    "quemarse": {"cautela": 0.03},
    "inventar": {"curiosidad": 0.03},
    "mala_charla": {"agresividad": 0.005, "sociabilidad": -0.005},
}


def _mundo():
    m = generar_mundo(7, 128, 128, 50)
    s = Simulacion(m["capas"], m["meta"])
    h = HabitanteSim(1, "Prueba", 10.5, 10.5)
    h.genoma = genoma_fundador(7)
    s.habitantes[1] = h
    return s, h


class TestExperienciasEnDatos(unittest.TestCase):
    def test_los_deltas_son_los_mismos_que_en_el_codigo(self):
        reg = Registro.cargar()
        for eid, mueve in EXPERIENCIAS_ORIG.items():
            d = reg.uno("experiencia", eid)
            self.assertIsNotNone(d, "falta la experiencia %s" % eid)
            self.assertEqual({k: float(v) for k, v in d["mueve"].items()}, mueve,
                             "cambió cuánto mueve el carácter «%s»" % eid)

    def test_todas_mueven_rasgos_que_existen(self):
        reg = Registro.cargar()
        for eid, d in reg.de_tipo("experiencia").items():
            for rasgo in d.get("mueve", {}):
                self.assertIn(rasgo, RASGOS, "%s mueve un rasgo inexistente: %s" % (eid, rasgo))
            self.assertTrue(d.get("motivo"), "%s no dice por qué (se muestra en el suceso)" % eid)

    def test_aplicar_una_experiencia_mueve_el_caracter(self):
        s, h = _mundo()
        antes = h.rasgo("cautela")
        s.experiencia(h, "ataque_de_animal")
        self.assertGreater(h.rasgo("cautela"), antes)

    def test_una_experiencia_que_no_existe_no_rompe(self):
        s, h = _mundo()
        antes = dict(h.rasgos_vivos)
        s.experiencia(h, "no_existe_esto")
        self.assertEqual(h.rasgos_vivos, antes)


class TestFrasesEnDatos(unittest.TestCase):
    def test_hay_una_frase_por_rasgo(self):
        reg = Registro.cargar()
        self.assertEqual(set(reg.de_tipo("temperamento")), set(RASGOS))
        for rid, d in reg.de_tipo("temperamento").items():
            self.assertTrue(d.get("bajo") and d.get("alto"), "%s necesita frase alta y baja" % rid)

    def test_la_descripcion_usa_los_datos(self):
        g = genoma_fundador(7)
        texto = describir_temperamento(g)
        self.assertTrue(texto)
        reg = Registro.cargar()
        for rasgo, v in g.rasgos.items():
            d = reg.uno("temperamento", rasgo)
            if v >= 0.7:
                self.assertIn(d["alto"], texto)
            elif v <= 0.3:
                self.assertIn(d["bajo"], texto)

    def test_un_caracter_del_medio_no_dice_nada_raro(self):
        g = genoma_fundador(7)
        g.rasgos = {k: 0.5 for k in RASGOS}
        self.assertEqual(describir_temperamento(g), "de caracter equilibrado")


class TestUnaSolaListaDeModulos(unittest.TestCase):
    """Había dos listas de módulos y la del motor no incluía los nuevos: quedaban sin efecto en silencio."""

    def test_el_motor_conoce_todos_los_modulos(self):
        from mundo_vivo.agentes.ajustes import MODULOS
        s, _ = _mundo()
        faltan = set(MODULOS) - set(s.ajustes["modulos"])
        self.assertFalse(faltan, "el motor no conoce estos módulos: %s" % sorted(faltan))


if __name__ == "__main__":
    unittest.main()

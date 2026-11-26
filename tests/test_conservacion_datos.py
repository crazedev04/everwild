"""Fase B: cuánto dura cada cosa, qué se cocina y qué abriga salen de los DATOS.

Copia CONGELADA de las constantes originales. Si alguien cambia el balanceo en el JSON, esto tiene que
fallar y obligar a decidirlo a conciencia, no a que se descubra en un mundo de 400 días.
"""
from __future__ import annotations

import unittest

from mundo_vivo.registro import Registro

# ---- copia congelada de motor/conservacion.py ----
VIDA_DIAS_ORIG = {
    "antorcha_encendida": 0.2, "hierba_medicinal": 8.0, "frutos": 6.0, "raiz": 25.0, "piel": 20.0,
    "pescado_asado": 4.0, "huevos_cocidos": 3.0, "raices_asadas": 6.0, "guiso": 2.0,
    "caldo_de_huesos": 2.0, "grasa": 40.0, "carne": 1.5, "pescado": 1.0, "huevo": 6.0,
    "carne_cocida": 5.0, "carne_curada": 40.0, "cuero": 90.0, "hueso": None, "pluma": None,
    "lana": None, "fibra": 120.0, "podrido": None}
CRUDOS_ORIG = {"carne": "carne_cocida", "pescado": "carne_cocida"}
# ---- copia congelada de motor/frio.py ----
MATERIALES_ABRIGO_ORIG = ("cuero", "lana", "pluma", "fibra")


def _todo(reg: Registro) -> dict:
    """Materiales e ítems juntos: una cosa que se pudre puede ser cualquiera de los dos."""
    d = dict(reg.de_tipo("material"))
    d.update(reg.de_tipo("item"))
    return d


class TestConservacionEnDatos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = Registro.cargar()
        cls.todo = _todo(cls.reg)

    def test_cada_cosa_dura_lo_mismo_que_antes(self):
        for item, dias in VIDA_DIAS_ORIG.items():
            d = self.todo.get(item)
            self.assertIsNotNone(d, "falta la entrada de %s" % item)
            c = d.get("conservacion") or {}
            self.assertEqual(c.get("vida_dias"), dias, "cambió cuánto dura %s" % item)

    def test_lo_que_no_se_pudre_lo_dice_explicitamente(self):
        """`vida_dias: null` es distinto de «no declara nada»: hay que poder verlo en el dato."""
        for item in ("hueso", "pluma", "lana", "podrido"):
            c = (self.todo.get(item) or {}).get("conservacion")
            self.assertIsNotNone(c, "%s no declara «conservacion»" % item)
            self.assertIn("vida_dias", c)
            self.assertIsNone(c["vida_dias"])

    def test_lo_crudo_se_cocina_en_lo_mismo_que_antes(self):
        for crudo, cocido in CRUDOS_ORIG.items():
            d = self.todo.get(crudo)
            self.assertIsNotNone(d, "falta %s" % crudo)
            self.assertEqual((d.get("cocina") or {}).get("resultado"), cocido,
                             "cambió en qué se convierte %s al cocinarlo" % crudo)

    def test_no_hay_mas_crudos_que_antes(self):
        crudos = {i for i, d in self.todo.items() if d.get("cocina")}
        self.assertEqual(crudos, set(CRUDOS_ORIG))

    def test_abriga_lo_mismo_que_antes(self):
        abrigan = {i for i, d in self.todo.items() if d.get("abrigo")}
        self.assertEqual(abrigan, set(MATERIALES_ABRIGO_ORIG), "cambió qué materiales abrigan")


class TestElMotorLoCompila(unittest.TestCase):
    def _sim(self):
        from mundo_vivo.generador.pipeline import generar_mundo
        from mundo_vivo.motor.simulacion import Simulacion
        m = generar_mundo(7, 128, 128, 50)
        return Simulacion(m["capas"], m["meta"])

    def test_las_tablas_compiladas_coinciden(self):
        from mundo_vivo.motor.conservacion import vida_min
        sim = self._sim()
        for item, dias in VIDA_DIAS_ORIG.items():
            esperado = None if dias is None else dias * 1440.0
            self.assertEqual(vida_min(item), esperado, "cambió la vida útil de %s" % item)
        self.assertEqual(dict(sim.crudos), CRUDOS_ORIG)
        self.assertEqual(set(sim.materiales_abrigo), set(MATERIALES_ABRIGO_ORIG))


if __name__ == "__main__":
    unittest.main()

"""Red de seguridad de la fase B.

Antes de sacar una tabla del código, este archivo afirma que lo que devuelve el registro es EXACTAMENTE lo
mismo que decía la constante de Python. Sin esto, mover 300 ids mete deriva de balanceo silenciosa y nadie
se entera hasta mirar un mundo de 400 días.

Los valores esperados están escritos a mano a propósito: son una copia congelada de las constantes originales.
Si alguien cambia el balanceo en los datos, este archivo tiene que fallar y obligar a decidirlo a conciencia.
"""
from __future__ import annotations

import unittest

from mundo_vivo.motor import biomas as B
from mundo_vivo.registro import Registro

# ---- copia congelada de motor/tecnologia.py (antes de la migración) ----
RECOLECCION_ORIG = {
    "palo": (B.BOSQUE_TEMPLADO, B.SELVA, B.BOSQUE_FRIO, B.SABANA, B.PRADERA, B.PANTANO, B.TUNDRA),
    "fibra": (B.PRADERA, B.SABANA, B.BOSQUE_TEMPLADO, B.SELVA, B.PANTANO),
    "paja": (B.PRADERA, B.SABANA, B.DESIERTO),
    "hoja_grande": (B.SELVA, B.BOSQUE_TEMPLADO, B.PANTANO),
    "resina": (B.BOSQUE_TEMPLADO, B.SELVA, B.BOSQUE_FRIO),
    "piedra": (B.MONTANA, B.TUNDRA, B.VOLCAN, B.DESIERTO, B.PLAYA, B.NIEVE),
    "pedernal": (B.MONTANA, B.TUNDRA, B.PLAYA),
    "pirita": (B.MONTANA, B.VOLCAN),
    "sal": (B.PLAYA, B.DESIERTO),
    "hierba_medicinal": (B.PRADERA, B.BOSQUE_TEMPLADO, B.SELVA, B.PANTANO),
    "frutos": (B.BOSQUE_TEMPLADO, B.SELVA, B.PRADERA),
    "raiz": (B.PRADERA, B.SABANA, B.BOSQUE_TEMPLADO, B.TUNDRA),
    "huevo": (B.PLAYA, B.PRADERA, B.PANTANO),
}
PROB_ORIG = {"palo": 0.9, "fibra": 0.8, "paja": 0.85, "hoja_grande": 0.8, "resina": 0.4, "piedra": 0.8,
             "pedernal": 0.35, "pirita": 0.2, "sal": 0.6, "hierba_medicinal": 0.45, "frutos": 0.5,
             "raiz": 0.5, "huevo": 0.25, "madera": 0.7, "arcilla": 0.7, "pescado": 0.15,
             "ceniza": 0.9, "carbon": 0.3}
CANT_ORIG = {"palo": (2, 5), "fibra": (2, 4), "paja": (2, 5), "hoja_grande": (2, 4), "piedra": (1, 3),
             "madera": (1, 2), "arcilla": (2, 4), "ceniza": (1, 3), "carbon": (1, 2)}
CAPACIDAD_ORIG = {"palo": 14, "fibra": 12, "paja": 14, "hoja_grande": 10, "resina": 3, "piedra": 12,
                  "pedernal": 4, "pirita": 3, "sal": 10, "hierba_medicinal": 6, "frutos": 24, "raiz": 24,
                  "huevo": 10, "madera": 8, "arcilla": 12, "pescado": 20}
# raiz, frutos, huevo y pescado se subieron a propósito al agregar el hambre (fase C): una zona que daba
# 8 unidades no alimentaba a tres personas. El resto sigue congelado en los valores originales.
LENA_ORIG = ("palo", "paja", "madera", "carbon")
# La fase 2 (minerales) agrega UNA leña nueva y es a conciencia: la piedra negra (carbón mineral) arde
# más y mucho más tiempo que la vegetal (420 min por unidad contra 150), y es lo que hace que valga la
# pena bajar a la caverna. Cualquier otra adición a esta lista tiene que fallar este test.
LENA_FASE_2 = LENA_ORIG + ("piedra_negra",)


class TestRecoleccionEnDatos(unittest.TestCase):
    """Cada material dice dónde se junta, con qué suerte, cuánto rinde y cuánto aguanta la zona."""

    @classmethod
    def setUpClass(cls):
        cls.reg = Registro.cargar()
        cls.mats = cls.reg.de_tipo("material")

    def _rec(self, mat: str) -> dict:
        d = self.mats.get(mat)
        self.assertIsNotNone(d, "falta el material %s" % mat)
        r = d.get("recoleccion")
        self.assertIsNotNone(r, "el material %s no declara «recoleccion»" % mat)
        return r

    def test_los_biomas_son_los_mismos_que_en_el_codigo(self):
        claves = {v[0]: k for k, v in B.BIOMAS.items()}     # "pradera" -> 5
        for mat, biomas in RECOLECCION_ORIG.items():
            datos = self._rec(mat).get("biomas")
            self.assertIsNotNone(datos, "%s no dice en qué biomas sale" % mat)
            ids = set()
            for b in self.reg.ids(datos) if any(str(x).startswith("#") for x in datos) else datos:
                ids.add(claves[b] if isinstance(b, str) else b)
            self.assertEqual(ids, set(biomas), "cambió dónde se junta %s" % mat)

    def test_las_probabilidades_son_las_mismas(self):
        for mat, p in PROB_ORIG.items():
            self.assertAlmostEqual(self._rec(mat).get("prob"), p, places=6,
                                   msg="cambió la probabilidad de encontrar %s" % mat)

    def test_las_cantidades_son_las_mismas(self):
        for mat, (lo, hi) in CANT_ORIG.items():
            self.assertEqual(tuple(self._rec(mat).get("cantidad")), (lo, hi),
                             "cambió cuánto rinde juntar %s" % mat)

    def test_las_capacidades_de_zona_son_las_mismas(self):
        for mat, cap in CAPACIDAD_ORIG.items():
            self.assertEqual(self._rec(mat).get("capacidad_zona"), cap,
                             "cambió cuánto aguanta una zona de %s" % mat)

    def test_la_lena_es_la_misma(self):
        enl = {i for i, d in self.mats.items() if d.get("lena")}
        self.assertEqual(enl, set(LENA_FASE_2), "cambió qué se puede quemar")
        self.assertEqual(self.mats["piedra_negra"]["lena"]["minutos_por_unidad"], 420.0,
                         "la piedra negra tiene que durar más que la leña vegetal (150)")


if __name__ == "__main__":
    unittest.main()

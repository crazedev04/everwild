"""Fase B: armas, antorchas y objetivos del respaldo salen de los DATOS, no del código.

Como en `test_datos_motor.py`, los valores esperados están escritos a mano a propósito: son una copia
CONGELADA de las constantes que vivían en `motor/tecnologia.py` y `motor/ecologia.py`. Si alguien cambia
el balanceo en los JSON, este archivo falla y obliga a decidirlo a conciencia.

Unidades: las constantes viejas guardaban el alcance en CELDAS. En los datos va en METROS, con la escala
histórica de 50 m por celda (arco: 7 celdas -> 350 m). Por eso cada alcance se compara dividido por 50.
"""
from __future__ import annotations

import unittest

from mundo_vivo.generador.pipeline import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion
from mundo_vivo.registro import Registro

_MUNDO = None


def sim_mini():
    """Un mundo chico (celdas de 50 m, las de siempre) para mirar las tablas ya compiladas."""
    global _MUNDO
    if _MUNDO is None:
        _MUNDO = generar_mundo(42, 64, 64)
    sim = Simulacion(_MUNDO["capas"], _MUNDO["meta"])
    sim.habitantes[1] = HabitanteSim(1, "Test", 1.5, 1.5)
    return sim


ESCALA_HISTORICA_M = 50.0      # metros por celda de los mundos de siempre

# ---- copia congelada de motor/tecnologia.py (antes de la migración) ----
ARMAS_ORIG = {   # item fabricado -> (bono de caza, alcance en celdas)
    "lanza": (0.30, 2.2), "lanza_de_pedernal": (0.35, 2.2), "lanza_de_hueso": (0.28, 2.2), "arpon": (0.30, 2.2),
    "arco": (0.40, 7.0), "arco_de_tendon": (0.45, 8.0), "arco_compuesto": (0.50, 9.0),
    "cuchillo_de_piedra": (0.10, 1.4), "cuchillo_de_pedernal": (0.14, 1.4), "cuchillo_de_cuerno": (0.12, 1.4),
    "cuchillo_de_acero": (0.18, 1.4),
    "hacha_de_piedra": (0.14, 1.4), "hacha_de_pedernal": (0.16, 1.4), "hacha_de_acero": (0.20, 1.4),
    "honda": (0.20, 5.0), "boleadoras": (0.22, 4.0), "lazo": (0.15, 1.4), "red_de_pesca": (0.10, 1.4)}

ANTORCHAS_ORIG = ("antorcha", "antorcha_de_resina", "antorcha_de_grasa")
DURA_ANTORCHA_MIN_ORIG = 0.2 * 1440.0        # lo que aguanta una antorcha prendida (= VIDA_DIAS de conservacion)

OBJETIVOS_ORIG = ["taladro_de_fuego", "cuchillo_de_pedernal", "cuerda", "refugio_de_paja", "hacha_de_piedra",
                  "cesta_de_fibra", "lanza_de_pedernal", "cataplasma", "choza_de_barro"]


class TestArmasEnDatos(unittest.TestCase):
    """Cada arma dice cuánto ayuda a cazar y desde qué distancia se puede tirar."""

    @classmethod
    def setUpClass(cls):
        cls.reg = Registro.cargar()
        cls.items = cls.reg.de_tipo("item")

    def _arma(self, item: str) -> dict:
        d = self.items.get(item)
        self.assertIsNotNone(d, "falta el item %s" % item)
        a = d.get("arma")
        self.assertIsNotNone(a, "el item %s no declara «arma»" % item)
        return a

    def test_estan_todas_las_armas_de_antes_y_ninguna_mas(self):
        con_arma = {i for i, d in self.items.items() if d.get("arma")}
        self.assertEqual(con_arma, set(ARMAS_ORIG))

    def test_el_bono_de_caza_es_el_mismo(self):
        for item, (bono, _) in ARMAS_ORIG.items():
            self.assertAlmostEqual(float(self._arma(item)["bono_caza"]), bono, places=6, msg=item)

    def test_el_alcance_en_metros_da_las_celdas_de_siempre(self):
        for item, (_, celdas) in ARMAS_ORIG.items():
            m = float(self._arma(item)["alcance_m"])
            self.assertAlmostEqual(m / ESCALA_HISTORICA_M, celdas, places=6, msg=item)

    def test_el_motor_compila_las_mismas_armas(self):
        sim = sim_mini()
        self.assertEqual(set(sim.armas), set(ARMAS_ORIG))
        for item, (bono, celdas) in ARMAS_ORIG.items():
            b, m = sim.armas[item]
            self.assertAlmostEqual(b, bono, places=6, msg=item)
            # `sim.armas` ya viene en celdas de ESTE mundo (se convierte al compilar, no acá)
            self.assertAlmostEqual(m, celdas, places=6, msg=item)

    def test_bono_arma_devuelve_celdas_de_este_mundo(self):
        sim = sim_mini()
        h = next(iter(sim.habitantes.values()))
        h.inventario = {"arco": 1}
        bono, alcance = sim.bono_arma(h)
        self.assertAlmostEqual(bono, 0.40, places=6)
        self.assertAlmostEqual(alcance, 7.0 * ESCALA_HISTORICA_M / sim.tam_celda_m, places=6)


class TestAntorchasEnDatos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = Registro.cargar()
        cls.items = cls.reg.de_tipo("item")

    def test_las_antorchas_de_antes_siguen_siendo_antorchas(self):
        for item in ANTORCHAS_ORIG:
            d = self.items.get(item)
            self.assertIsNotNone(d, "falta el item %s" % item)
            self.assertIsNotNone(d.get("antorcha"), "%s no declara «antorcha»" % item)
            self.assertAlmostEqual(float(d["antorcha"]["dura_min"]), DURA_ANTORCHA_MIN_ORIG, places=6, msg=item)

    def test_el_palo_pelado_arde_la_mitad_y_va_ultimo(self):
        """Antes era un `if base != "palo"` en el código: ahora es un dato (dura la mitad que una antorcha)."""
        palo = self.items.get("palo")
        self.assertIsNotNone(palo, "falta el item palo")
        self.assertAlmostEqual(float(palo["antorcha"]["dura_min"]), 0.5 * DURA_ANTORCHA_MIN_ORIG, places=6)
        sim = sim_mini()
        self.assertEqual(set(sim.antorchas), set(ANTORCHAS_ORIG) | {"palo"})
        self.assertEqual(list(sim.antorchas)[-1], "palo")        # el último recurso se prueba al final
        self.assertEqual(list(sim.antorchas)[:len(ANTORCHAS_ORIG)], list(ANTORCHAS_ORIG))


class TestObjetivosEnDatos(unittest.TestCase):
    def test_el_respaldo_intenta_lo_mismo_y_en_el_mismo_orden(self):
        reg = Registro.cargar()
        d = reg.uno("objetivos", "respaldo")
        self.assertIsNotNone(d, "falta la lista de objetivos «respaldo»")
        self.assertEqual([str(r) for r in d["recetas"]], OBJETIVOS_ORIG)

    def test_el_motor_los_lee_en_orden(self):
        sim = sim_mini()
        self.assertEqual(list(sim.objetivos), OBJETIVOS_ORIG)


if __name__ == "__main__":
    unittest.main()

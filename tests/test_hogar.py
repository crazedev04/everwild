"""Fase 4 del plan del motor: el calor cae con la distancia, la casa es de alguien, y lo que nadie usa se cae.

La idea que atraviesa todo el archivo: el motor no sabe qué es una aldea. Lo que hace que un montón de
chozas se vuelva una aldea es físico — una choza dentro del alcance de una fogata abriga más que la misma
choza sola —, y de ahí sale solo el incentivo de construir alrededor del fuego.
"""
from __future__ import annotations

import unittest

from mundo_vivo.motor import tecnologia as T
from tests.test_calor import _construir, _mundo


def _fogata(s, x, y):
    s.fogatas.append({"x": x, "y": y, "hasta": 1e9, "dueno": 1})
    return s.fogatas[-1]


class TestCalorConCaida(unittest.TestCase):
    def test_el_nucleo_abriga_pleno_y_mas_lejos_abriga_menos(self):
        s, h = _mundo()
        _fogata(s, h.x, h.y)
        encima = s.calor_de_estructuras(h)
        self.assertAlmostEqual(encima, 0.25, places=3, msg="encima de las brasas, el 0,25 de siempre")
        nuc = s.celdas(6.0, minimo=1.0)
        rad = s.celdas(20.0, minimo=1.5)
        h.x += nuc + (rad - nuc) * 0.5
        medio = s.calor_de_estructuras(h)
        self.assertGreater(medio, encima, "a mitad de camino abriga menos que encima")
        self.assertLess(medio, 1.0, "pero algo abriga: ya no es todo o nada")
        h.x += rad
        self.assertEqual(s.calor_de_estructuras(h), 1.0, "pasado el radio no abriga nada")

    def test_para_trabajar_hace_falta_estar_en_el_nucleo(self):
        """Dos curvas distintas: no se cocina «casi al lado» del fuego."""
        s, h = _mundo()
        _fogata(s, h.x, h.y)
        self.assertEqual(s.calor_disponible(h), 600.0)
        h.x += s.celdas(6.0, minimo=1.0) + s.celdas(20.0) * 0.4
        self.assertEqual(s.calor_disponible(h), 0.0, "para fabricar la caída es escalonada y corta")
        self.assertLess(s.calor_de_estructuras(h), 1.0, "pero para abrigarse todavía sirve")

    def test_la_caida_es_un_dato_de_la_estructura(self):
        s, _ = _mundo()
        self.assertEqual((s.estructuras["fogata"]["provee"]["nucleo_m"],
                          s.estructuras["fogata"]["provee"]["caida"]), (6.0, "cuadratica"))
        self.assertEqual(s.estructuras["fragua"]["provee"]["caida"], "escalon",
                         "en la fragua se trabaja encima o nada")

    def test_la_curva_se_calcula_sin_barrer_celdas(self):
        """Tres números, no un barrido: esto se consulta seguido (ver docs/OPTIMIZACION.md)."""
        self.assertEqual(T.TecnologiaMixin._caida(0.0, 3.0, 9.0, "lineal"), 1.0)
        self.assertEqual(T.TecnologiaMixin._caida(3.0, 3.0, 9.0, "lineal"), 1.0)
        self.assertAlmostEqual(T.TecnologiaMixin._caida(6.0, 3.0, 9.0, "lineal"), 0.5)
        self.assertAlmostEqual(T.TecnologiaMixin._caida(6.0, 3.0, 9.0, "cuadratica"), 0.25)
        self.assertEqual(T.TecnologiaMixin._caida(6.0, 3.0, 9.0, "escalon"), 0.0)
        self.assertEqual(T.TecnologiaMixin._caida(9.0, 3.0, 9.0, "lineal"), 0.0)


class TestLaFogataAbrigaLasChozas(unittest.TestCase):
    def test_la_misma_choza_abriga_mas_al_lado_del_fuego(self):
        s, h = _mundo()
        self.assertTrue(_construir(s, h, "choza_de_barro")[0])
        casa = next(r for r in s.refugios if r["tipo"] == "choza_de_barro")
        sola = s.abrigo_efectivo(casa)
        self.assertEqual(sola, 0.6, "sola abriga lo que dice su receta")
        _fogata(s, casa["x"], casa["y"])
        self.assertGreater(s.abrigo_efectivo(casa), sola,
                           "con la fogata al lado abriga más: ése es el incentivo para hacer aldea")
        self.assertLessEqual(s.abrigo_efectivo(casa), 0.95)

    def test_el_pozo_no_abriga_aunque_este_al_lado_del_fuego(self):
        s, h = _mundo()
        self.assertTrue(_construir(s, h, "horno_de_barro")[0])
        horno = next(r for r in s.refugios if r["tipo"] == "horno_de_barro")
        _fogata(s, horno["x"], horno["y"])
        self.assertEqual(s.abrigo_efectivo(horno), 0.0, "un horno no es un techo")


class TestCamaPropia(unittest.TestCase):
    def test_construir_deja_el_refugio_a_nombre_de_quien_lo_hizo(self):
        s, h = _mundo()
        self.assertTrue(_construir(s, h, "refugio_de_paja")[0])
        casa = next(r for r in s.refugios if r["tipo"] == "refugio_de_paja")
        self.assertEqual(h.hogar_rid, casa["rid"], "el hogar es un refugio concreto, no una coordenada suelta")
        self.assertEqual(casa["dueno"], h.id)

    def test_a_igual_abrigo_gana_el_refugio_propio(self):
        s, h = _mundo()
        self.assertTrue(_construir(s, h, "refugio_de_paja")[0])
        ajeno = dict(next(r for r in s.refugios if r["dueno"] == h.id))
        ajeno.update(rid=99, dueno=h.id + 1, x=h.x + 0.3)
        s.refugios.append(ajeno)
        self.assertEqual(s.refugio_cerca(h)["dueno"], h.id)

    def test_dormir_bajo_techo_descansa_mas_que_a_la_intemperie(self):
        s, h = _mundo()
        h.energia = 20.0
        ok, texto = s._aplicar(h, {"tipo": "dormir", "min": 300})
        self.assertTrue(ok)
        self.assertIn("intemperie", texto)
        self.assertEqual(h.cama, 0.0)
        afuera = h.energia
        s._actualizar(h, 60.0)
        gano_afuera = h.energia - afuera

        s2, h2 = _mundo()
        h2.energia = 20.0
        self.assertTrue(_construir(s2, h2, "choza_de_barro")[0])
        h2.accion, h2.hasta = "", 0.0
        ok, texto = s2._aplicar(h2, {"tipo": "dormir", "min": 300})
        self.assertTrue(ok)
        self.assertIn("choza", texto)
        self.assertGreater(h2.cama, 0.0)
        adentro = h2.energia
        s2._actualizar(h2, 60.0)
        self.assertGreater(h2.energia - adentro, gano_afuera, "en la choza se descansa mejor que en el barro")


class TestRuinas(unittest.TestCase):
    def _sin_nadie(self, s, h):
        h.x, h.y = h.x + s.celdas(400.0), h.y          # se va lejos: nadie pasa por la casa
        return next(r for r in s.refugios if r["dueno"] == h.id)

    def test_lo_que_nadie_usa_se_cae_y_queda_como_ruina(self):
        s, h = _mundo()
        self.assertTrue(_construir(s, h, "choza_de_barro")[0])
        casa = self._sin_nadie(s, h)
        s._paso_ruinas()                                  # primera pasada: sólo marca el reloj
        for _ in range(500):                              # 500 días sin que pase nadie
            s.t += T.MIN_DIA
            s._paso_ruinas()
        self.assertTrue(casa.get("ruina"), "después de años sin tránsito tiene que quedar en ruinas")
        self.assertEqual(casa["abrigo"], 0.0)
        self.assertIsNone(h.hogar_rid, "y deja de ser el hogar de nadie")
        self.assertEqual(casa["abrigo0"], 0.6, "pero se sabe lo que abrigaba cuando era nueva")

    def test_la_casa_por_la_que_pasa_alguien_no_se_cae(self):
        s, h = _mundo()
        self.assertTrue(_construir(s, h, "choza_de_barro")[0])
        casa = next(r for r in s.refugios if r["dueno"] == h.id)
        s._paso_ruinas()
        for _ in range(500):
            s.t += T.MIN_DIA
            s._paso_ruinas()
        self.assertFalse(casa.get("ruina"))
        self.assertEqual(casa["abrigo"], 0.6)

    def test_una_boca_de_caverna_no_se_arruina(self):
        s, h = _mundo()
        s.refugios.append({"rid": 1, "x": h.x, "y": h.y, "dueno": None, "tipo": "boca_de_caverna",
                           "nombre": "boca de caverna", "abrigo": 0.0, "t": 0, "natural": True})
        s._paso_ruinas()
        for _ in range(900):
            s.t += T.MIN_DIA
            s._paso_ruinas()
        self.assertFalse(s.refugios[-1].get("ruina"))

    def test_la_ruina_sale_aparte_en_lo_que_publica_el_motor(self):
        """Lista nueva y no un campo más en `refugios`: la UI que ya existe no tiene que cambiar nada."""
        s, h = _mundo()
        self.assertTrue(_construir(s, h, "choza_de_barro")[0])
        pub = s.publico_estructuras()
        self.assertEqual(pub["ruinas"], [])
        casa = self._sin_nadie(s, h)
        s._paso_ruinas()
        for _ in range(500):
            s.t += T.MIN_DIA
            s._paso_ruinas()
        self.assertEqual(len(s.publico_estructuras()["ruinas"]), 1)
        self.assertEqual(s.aldeas(), [], "una ruina no cuenta como casa de una aldea")


class TestAtractorDeLaFogata(unittest.TestCase):
    def test_de_noche_y_con_fuego_al_lado_tira_a_quedarse(self):
        s, h = _mundo()
        s.t = 1440.0 * 3 + 60.0                           # de madrugada
        from mundo_vivo.motor import reloj
        if not reloj.es_noche(s.t):
            self.skipTest("ese minuto no es de noche en este mundo")
        self.assertEqual(s.atractor_fogata(h), 0.0, "sin fuego no hay atractor")
        _fogata(s, h.x, h.y)
        self.assertGreater(s.atractor_fogata(h), 0.0)

    def test_de_dia_la_fogata_no_tira(self):
        s, h = _mundo()
        from mundo_vivo.motor import reloj
        s.t = 1440.0 * 3 + 720.0                          # mediodía
        if reloj.es_noche(s.t):
            self.skipTest("ese minuto no es de día en este mundo")
        _fogata(s, h.x, h.y)
        self.assertEqual(s.atractor_fogata(h), 0.0)


if __name__ == "__main__":
    unittest.main()

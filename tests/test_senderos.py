"""Fase 5 del plan del motor: el paso repetido deja huella y el A* usa el camino ya hecho.

Los tres detalles que hacen a esta fase invasiva tienen un test cada uno: que el cambio de costo llegue
a LAS DOS representaciones del terreno (el array y la copia en listas que usa el A*), que a quien venía
caminando se le invalide la ruta vieja, y que nada de esto toque el costo celda por celda por tick.
"""
from __future__ import annotations

import unittest

import numpy as np

from mundo_vivo.motor import biomas as B
from mundo_vivo.motor import senderos as S
from tests.test_calor import _mundo


class TestDesgaste(unittest.TestCase):
    def test_pisar_no_toca_el_mapa_hasta_que_se_vuelca(self):
        """Lo que corre en el bucle es un diccionario disperso, no el mapa (ver docs/OPTIMIZACION.md)."""
        s, h = _mundo()
        x, y = int(h.x), int(h.y)
        bioma = int(s.terreno.bioma[y, x])
        for _ in range(S.PISADAS_SENDERO + 20):
            s.pisar(x, y)
        self.assertEqual(int(s.terreno.bioma[y, x]), bioma, "todavía no se volcó nada")
        self.assertEqual(int(s.desgaste[y, x]), 0)
        s._volcar_pisadas()
        self.assertEqual(int(s.terreno.bioma[y, x]), s.bioma_sendero)

    def test_pocas_pisadas_no_abren_nada(self):
        s, h = _mundo()
        x, y = int(h.x), int(h.y)
        bioma = int(s.terreno.bioma[y, x])
        for _ in range(S.PISADAS_SENDERO - 1):
            s.pisar(x, y)
        s._volcar_pisadas()
        self.assertEqual(int(s.terreno.bioma[y, x]), bioma)
        self.assertEqual(int(s.desgaste[y, x]), S.PISADAS_SENDERO - 1)

    def test_el_sendero_se_camina_mas_rapido(self):
        s, h = _mundo()
        x, y = int(h.x), int(h.y)
        antes = s.terreno.velocidad_en(x + 0.5, y + 0.5)
        for _ in range(S.PISADAS_SENDERO):
            s.pisar(x, y)
        s._volcar_pisadas()
        self.assertGreater(s.terreno.velocidad_en(x + 0.5, y + 0.5), antes)
        self.assertEqual(B.VELOCIDAD[s.bioma_sendero], 0.75, "la velocidad del sendero es un dato del JSON")

    def test_el_costo_cambia_en_LAS_DOS_representaciones(self):
        """`Terreno.costo` es el array y `Terreno._c` es la copia en listas que usa el A*. Escribir sólo
        una deja al A* caminando el mapa viejo para siempre."""
        s, h = _mundo()
        x, y = int(h.x), int(h.y)
        for _ in range(S.PISADAS_SENDERO):
            s.pisar(x, y)
        s._volcar_pisadas()
        self.assertEqual(float(s.terreno.costo[y, x]), s.terreno._c[y][x])
        self.assertLess(s.terreno._c[y][x], s.terreno.tam_celda_m / 1.33)

    def test_no_se_abre_sendero_en_agua_ni_en_pared(self):
        s, h = _mundo()
        ys, xs = np.nonzero(~np.isfinite(s.terreno.costo))
        if not len(xs):
            self.skipTest("el mundo de prueba no tiene celdas intransitables")
        x, y = int(xs[0]), int(ys[0])
        bioma = int(s.terreno.bioma[y, x])
        for _ in range(S.PISADAS_SENDERO * 3):
            s.pisar(x, y)
        s._volcar_pisadas()
        self.assertEqual(int(s.terreno.bioma[y, x]), bioma)

    def test_al_abrirse_se_invalida_el_camino_de_quien_venia_por_ahi(self):
        s, h = _mundo()
        x, y = int(h.x), int(h.y)
        h.camino = [(x + 1, y), (x + 2, y)]
        lejano = type(h)(2, "Lejano", h.x + s.celdas(5000.0), h.y)
        lejano.camino = [(1, 1)]
        s.habitantes[2] = lejano
        for _ in range(S.PISADAS_SENDERO):
            s.pisar(x, y)
        s._volcar_pisadas()
        self.assertEqual(h.camino, [], "su ruta se calculó contra el mapa viejo")
        self.assertEqual(lejano.camino, [(1, 1)], "al que anda lejos no se le toca nada")

    def test_sin_transito_el_sendero_se_cierra(self):
        s, h = _mundo()
        x, y = int(h.x), int(h.y)
        bioma = int(s.terreno.bioma[y, x])
        for _ in range(S.PISADAS_SENDERO):
            s.pisar(x, y)
        s._volcar_pisadas()
        self.assertEqual(int(s.terreno.bioma[y, x]), s.bioma_sendero)
        s._desvanecer()                                   # primera pasada: marca el reloj
        for _ in range(400):
            s.t += S.MIN_DIA
            s._desvanecer()
        self.assertEqual(int(s.desgaste[y, x]), 0)
        self.assertEqual(int(s.terreno.bioma[y, x]), bioma, "vuelve a ser lo que era")
        self.assertEqual(float(s.terreno.costo[y, x]), s.terreno._c[y][x])

    def test_el_transito_lo_mantiene_abierto(self):
        s, h = _mundo()
        x, y = int(h.x), int(h.y)
        for _ in range(S.PISADAS_SENDERO):
            s.pisar(x, y)
        s._volcar_pisadas()
        s._desvanecer()
        for _ in range(400):
            s.t += S.MIN_DIA
            for _ in range(10):                            # alguien sigue pasando todos los días
                s.pisar(x, y)
            s._volcar_pisadas()
            s._desvanecer()
        self.assertEqual(int(s.terreno.bioma[y, x]), s.bioma_sendero)

    def test_el_primer_sendero_es_un_hito(self):
        s, h = _mundo()
        for _ in range(S.PISADAS_SENDERO):
            s.pisar(int(h.x), int(h.y))
        s._volcar_pisadas()
        self.assertIn("senderos", s.hitos)

    def test_caminar_de_verdad_deja_huella(self):
        """No alcanza con que exista `pisar`: el bucle de movimiento tiene que llamarlo."""
        s, h = _mundo()
        destino = None
        for d in range(3, 12):
            c = s.terreno.caminable_cerca(int(h.x) + d, int(h.y), 3)
            if c and s.terreno.buscar_camino((int(h.x), int(h.y)), c, s.nodos_camino):
                destino = c
                break
        if destino is None:
            self.skipTest("no hay a dónde caminar en el mundo de prueba")
        ok, texto = s._aplicar(h, {"tipo": "ir", "destino": destino})
        self.assertTrue(ok, texto)
        for _ in range(200):
            s._mover(h, 1.0)
        self.assertTrue(s._pisadas or s.desgaste.any(), "caminar tiene que haber dejado pisadas")


class TestPersistencia(unittest.TestCase):
    def test_se_guarda_y_se_lee(self):
        s, h = _mundo()
        x, y = int(h.x), int(h.y)
        for _ in range(S.PISADAS_SENDERO):
            s.pisar(x, y)
        s._volcar_pisadas()
        datos = s.desgaste_bytes()
        otro, _ = _mundo()
        otro.importar_desgaste(datos)
        self.assertEqual(int(otro.desgaste[y, x]), int(s.desgaste[y, x]))

    def test_comprime_a_casi_nada(self):
        """Un uint8 de 2048×2048 casi todo en cero: por eso va comprimido y no pesa."""
        s, h = _mundo()
        self.assertLess(len(s.desgaste_bytes()), 2000)

    def test_datos_de_otro_tamano_no_rompen_nada(self):
        s, _ = _mundo()
        s.importar_desgaste(b"basura")
        self.assertEqual(int(s.desgaste.sum()), 0)


if __name__ == "__main__":
    unittest.main()

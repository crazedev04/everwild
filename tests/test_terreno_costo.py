"""Integridad de Terreno.costo / Terreno._c (etapa K).

Verifica que las dos representaciones del costo del terreno se mantienen
sincronizadas tras cada cambio, y que las escrituras directas a costo/_c
están confinadas a navegacion.py.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from mundo_vivo.motor import biomas as B
from mundo_vivo.motor import senderos as S
from tests.test_calor import _mundo


class TestCostoSincronizado(unittest.TestCase):
    def setUp(self):
        self.s, self.h = _mundo()
        self.t = self.s.terreno

    def test_costo_y_c_iguales_al_crear_el_mundo(self):
        """__init__ escribe ambas representaciones desde el mismo array."""
        import numpy as np

        self.assertTrue(np.array_equal(self.t.costo, np.array(self.t._c)))

    def test_establecer_costo_celda_escribe_ambas_representaciones(self):
        x, y = int(self.h.x), int(self.h.y)
        self.t._establecer_costo_celda(x, y, 5.0)
        self.assertEqual(float(self.t.costo[y, x]), 5.0)
        self.assertEqual(self.t._c[y][x], 5.0)

    def test_cambiar_bioma_usa_metodo_centralizado_y_mantiene_sincronia(self):
        x, y = int(self.h.x), int(self.h.y)
        actual = int(self.t.bioma[y, x])
        otro = B.PRADERA if actual != B.PRADERA else B.BOSQUE_TEMPLADO
        self.t.cambiar_bioma(x, y, otro)
        self.assertEqual(float(self.t.costo[y, x]), self.t._c[y][x])
        self.t.cambiar_bioma(x, y, actual)

    def test_abrir_cerrar_sendero_mantiene_sincronizacion(self):
        x, y = int(self.h.x), int(self.h.y)
        for _ in range(S.PISADAS_SENDERO):
            self.s.pisar(x, y)
        self.s._volcar_pisadas()
        self.assertEqual(float(self.t.costo[y, x]), self.t._c[y][x])
        self.s._desvanecer()
        for _ in range(400):
            self.s.t += S.MIN_DIA
            self.s._desvanecer()
        self.assertEqual(float(self.t.costo[y, x]), self.t._c[y][x])

    def test_cambiar_bioma_invalida_rutas_cacheadas(self):
        x0, y0 = int(self.h.x), int(self.h.y)
        x1, y1 = x0 + 5, y0 + 5
        if not self.t.dentro(x1, y1):
            self.skipTest("destino fuera del mundo de prueba")
        self.t.buscar_camino((x0, y0), (x1, y1))
        self.assertGreater(len(self.t._rutas), 0)
        actual = int(self.t.bioma[y0, x0])
        otro = B.PRADERA if actual != B.PRADERA else B.BOSQUE_TEMPLADO
        self.t.cambiar_bioma(x0, y0, otro)
        self.assertEqual(len(self.t._rutas), 0, "rutas deben invalidarse al cambiar bioma")
        self.t.cambiar_bioma(x0, y0, actual)

    def test_cambiar_bioma_invalida_fracasos_cacheados(self):
        clave = (0, 0, 10, 10)
        self.t._fracasos.add(clave)
        x, y = int(self.h.x), int(self.h.y)
        actual = int(self.t.bioma[y, x])
        otro = B.PRADERA if actual != B.PRADERA else B.BOSQUE_TEMPLADO
        self.t.cambiar_bioma(x, y, otro)
        self.assertNotIn(clave, self.t._fracasos, "fracasos deben invalidarse al cambiar bioma")
        self.t.cambiar_bioma(x, y, actual)

    def test_importar_desgaste_reconstruye_sin_desincronizacion(self):
        x, y = int(self.h.x), int(self.h.y)
        for _ in range(S.PISADAS_SENDERO):
            self.s.pisar(x, y)
        self.s._volcar_pisadas()
        datos = self.s.desgaste_bytes()
        self.s.importar_desgaste(datos)
        self.assertEqual(float(self.t.costo[y, x]), self.t._c[y][x])

    def test_no_escritura_directa_costo_fuera_de_navegacion(self):
        """Ninguna asignación indexada a `costo` o `_c` fuera de navegacion.py."""
        patron = re.compile(r"self\.(costo|_c)(\s*\[[^\]]*\])+\s*=")
        src = Path(__file__).resolve().parents[1] / "src"
        for p in src.rglob("*.py"):
            texto = p.read_text()
            for linea in texto.splitlines():
                if patron.search(linea):
                    self.assertEqual(
                        p.name, "navegacion.py",
                        f"escritura directa a costo/_c en {p}: {linea.strip()}",
                    )


if __name__ == "__main__":
    unittest.main()

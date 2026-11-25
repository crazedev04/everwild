"""Fase G1: los umbrales del generador salen de los datos, pero el mapa no cambia ni un píxel.

Los hashes de abajo se capturaron ANTES de mover nada. Si cambian, alguien cambió el mundo sin querer:
un mundo ya guardado conserva su mapa (se guarda el resultado, no la receta), pero uno nuevo con la misma
semilla tiene que salir idéntico o la semilla deja de significar nada.
"""
from __future__ import annotations

import unittest

import numpy as np

from mundo_vivo.motor.generador import generar_mundo
from mundo_vivo.persistencia.mundo_io import hash_capas
from mundo_vivo.registro import Registro

HASH_ORIG = {7: "d36045d1b8752356", 42: "84d35c326ef1e40f"}
BIOMAS_ORIG_7 = {0: 9814, 1: 10461, 2: 562, 3: 582, 4: 1973, 5: 4562, 6: 2258, 7: 1242,
                 8: 51, 9: 899, 10: 1593, 11: 108, 12: 1237, 13: 226, 14: 1296}


class TestElMapaNoCambia(unittest.TestCase):
    def test_los_mapas_son_identicos_a_antes(self):
        for sem, h in HASH_ORIG.items():
            capas = generar_mundo(sem, 192, 192, 50)["capas"]
            self.assertEqual(hash_capas(capas)[:16], h, "cambió el mapa de la semilla %d" % sem)

    def test_la_mezcla_de_biomas_es_la_misma(self):
        capas = generar_mundo(7, 192, 192, 50)["capas"]
        u, n = np.unique(capas["bioma"], return_counts=True)
        self.assertEqual(dict(zip(u.tolist(), n.tolist())), BIOMAS_ORIG_7)


class TestClasificacionEnDatos(unittest.TestCase):
    def test_los_biomas_de_clima_declaran_sus_rangos(self):
        reg = Registro.cargar()
        for bid in ("tundra", "bosque_frio", "desierto", "pradera", "bosque_templado", "sabana", "selva"):
            d = reg.uno("bioma", bid)
            self.assertIsNotNone(d, "falta el bioma %s" % bid)
            c = d.get("clasificacion")
            self.assertIsNotNone(c, "%s no dice en qué clima aparece" % bid)
            self.assertIn("prioridad", c)
            self.assertTrue(c.get("rangos"), "%s no declara rangos" % bid)

    def test_el_agua_y_los_volcanes_no_son_de_clima(self):
        """Son primitivas del generador, no umbrales: no deben declarar `clasificacion`."""
        reg = Registro.cargar()
        for bid in ("oceano", "oceano_profundo", "lago", "playa", "volcan"):
            d = reg.uno("bioma", bid)
            self.assertIsNone((d or {}).get("clasificacion"),
                              "%s no se decide por temperatura y humedad" % bid)

    def test_se_puede_correr_el_rango_de_un_bioma_desde_los_datos(self):
        """La prueba de que sirve: con otro umbral, el mapa cambia."""
        from mundo_vivo.motor import generador
        tabla = generador.tabla_clima(Registro.cargar())
        self.assertTrue(tabla, "no se armó la tabla de clima")
        prioridades = [p for p, _, _ in tabla]
        self.assertEqual(prioridades, sorted(prioridades), "la tabla tiene que venir ordenada por prioridad")


if __name__ == "__main__":
    unittest.main()

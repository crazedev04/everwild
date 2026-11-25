"""Fase 3 del plan del motor: minerales que el mundo inventa y que no están en ningún catálogo.

Lo que hay que cuidar, y es lo que prueba este archivo: que sean los MISMOS siempre en el mismo mundo,
que el nombre no delate lo que hacen, que se puedan fundir con la receta genérica sin generar ninguna
receta nueva, y que cambiar el espacio de lo posible no le cambie la geología a una partida empezada.
"""
from __future__ import annotations

import unittest

from mundo_vivo.motor.generador import generar_mundo
from mundo_vivo.motor.minerales import ETIQUETA_MENA
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion
from tests.test_calor import _ensenar


def _mundo(semilla=7, dimension=0):
    m = generar_mundo(semilla, 128, 128, 50)
    s = Simulacion(m["capas"], m["meta"], dimension=dimension)
    x, y = s.terreno.caminable_cerca(64, 64, 40) or (10, 10)
    h = HabitanteSim(1, "Prueba", x + 0.5, y + 0.5)
    s.habitantes[1] = h
    return s, h


class TestGeneracion(unittest.TestCase):
    def test_el_mismo_mundo_tiene_siempre_los_mismos_minerales(self):
        a, _ = _mundo(7)
        b, _ = _mundo(7)
        self.assertEqual(a.minerales_mundo, b.minerales_mundo, "la semilla manda: nada de azar sin sembrar")
        self.assertTrue(a.minerales_mundo, "un mundo tiene que sortear al menos uno")

    def test_dos_mundos_distintos_tienen_minerales_distintos(self):
        a, _ = _mundo(7)
        b, _ = _mundo(1234)
        self.assertNotEqual(a.minerales_desconocidos(), b.minerales_desconocidos())

    def test_cada_dimension_sortea_lo_suyo(self):
        a, _ = _mundo(7, dimension=0)
        b, _ = _mundo(7, dimension=1)
        self.assertNotEqual([p["mena"]["nombre"] for p in a.minerales_mundo],
                            [p["mena"]["nombre"] for p in b.minerales_mundo])

    def test_no_se_gasta_el_generador_del_mundo(self):
        """El RNG del mundo es sagrado: sortear minerales no puede moverlo."""
        s, _ = _mundo(7)
        antes = s.rng.random()
        s.generar_minerales_desconocidos()
        s.generar_minerales_desconocidos()
        t, _ = _mundo(7)
        t.rng.random()
        self.assertEqual(s.rng.random(), t.rng.random())
        self.assertIsInstance(antes, float)

    def test_la_cantidad_y_los_rangos_salen_del_json(self):
        s, _ = _mundo(7)
        esp = s.registro.uno("generacion_minerales", "minerales_desconocidos")
        self.assertIsNotNone(esp, "el espacio de lo posible tiene que ser un dato, no código")
        lo, hi = esp["cantidad"]
        self.assertTrue(lo <= len(s.minerales_mundo) <= hi)
        rd = esp["rangos"]["densidad_kg_m3"]
        for par in s.minerales_mundo:
            self.assertTrue(rd[0] <= par["mena"]["densidad_kg_m3"] <= rd[1])
            self.assertTrue(esp["rangos"]["punto_fusion_C"][0] <= par["mena"]["punto_fusion_C"]
                            <= esp["rangos"]["punto_fusion_C"][1])

    def test_el_nombre_no_delata_ninguna_propiedad(self):
        """Regla 8: la lista de materiales se le muestra a la persona."""
        prohibidas = ("magnet", "conduc", "duro", "blando", "pesado", "funde", "aglomer", "metal_",
                      "mineral_", "inflamab", "desconocid")
        for semilla in (7, 99, 1234, 55555):
            s, _ = _mundo(semilla)
            for par in s.minerales_mundo:
                for d in (par["mena"], par["metal"]):
                    for mala in prohibidas:
                        self.assertNotIn(mala, d["nombre"].lower(),
                                         "el nombre «%s» delata algo" % d["nombre"])

    def test_los_nombres_no_se_repiten_entre_si(self):
        s, _ = _mundo(7)
        nombres = [p["mena"]["nombre"] for p in s.minerales_mundo] + \
                  [p["metal"]["nombre"] for p in s.minerales_mundo]
        self.assertEqual(len(nombres), len(set(nombres)))


class TestEntranEnElMundo(unittest.TestCase):
    def test_estan_en_el_registro_y_en_las_reglas(self):
        s, _ = _mundo(7)
        for mid in s.minerales_desconocidos():
            self.assertIn(mid, s.reglas.materiales, "el evaluador de propiedades tiene que verlos")
            self.assertIsNotNone(s.registro.uno("material", mid))

    def test_se_pueden_juntar_pero_hacen_falta_herramientas(self):
        s, h = _mundo(7)
        mid = s.minerales_desconocidos()[0]
        self.assertIn(mid, s.recoleccion, "tienen que decir en qué biomas salen")
        self.assertEqual(s.herramienta_rec.get(mid), "golpea", "están metidos en la roca")

    def test_el_metal_no_se_junta_del_suelo(self):
        s, _ = _mundo(7)
        for par in s.minerales_mundo:
            self.assertNotIn(par["metal"]["id"], s.recoleccion)

    def test_entran_en_la_etiqueta_de_este_mundo_y_no_en_el_archivo(self):
        from mundo_vivo import catalogos
        s, _ = _mundo(7)
        self.assertEqual(s.etiquetas[ETIQUETA_MENA], set(s.minerales_desconocidos()))
        self.assertEqual(catalogos.cargar_etiquetas()[ETIQUETA_MENA], set(),
                         "en el catálogo la etiqueta queda vacía: los minerales son de cada mundo")


class TestFundirSinGenerarRecetas(unittest.TestCase):
    """El punto de toda la fase: UNA receta fija funde cualquier piedra, incluida una inventada hoy."""

    def _con_fragua(self, s, h):
        s.refugios.append({"rid": 99, "x": h.x, "y": h.y, "dueno": 1, "tipo": "fragua",
                           "nombre": "fragua", "abrigo": 0.0, "t": 0})

    def test_fundir_una_piedra_rara_da_el_metal_que_ella_declara(self):
        s, h = _mundo(7)
        mid = s.minerales_desconocidos()[0]
        metal = s.metal_de(mid)
        self.assertNotEqual(metal, mid)
        _ensenar(s, h, "fundir_piedra_rara")
        s._ganar_item(h, mid, 3)
        s._ganar_item(h, "carbon", 3)
        self._con_fragua(s, h)
        ok, texto = s._aplicar(h, {"tipo": "fabricar", "objeto": "fundir_piedra_rara"})
        self.assertTrue(ok, texto)
        self.assertEqual(h.inventario.get(metal, 0), 1)

    def test_el_calor_que_pide_es_el_del_mineral_que_se_usa(self):
        """`requiere: {calor_C: "@mena"}`: cada piedra cuesta lo que dice su punto de fusión."""
        s, h = _mundo(7)
        mid = s.minerales_desconocidos()[0]
        _ensenar(s, h, "fundir_piedra_rara")
        s._ganar_item(h, mid, 3)
        s._ganar_item(h, "carbon", 3)
        self.assertFalse(s.requisitos_ok(h, s.recetas["fundir_piedra_rara"])[0], "sin fuego no se funde nada")
        self._con_fragua(s, h)
        self.assertTrue(s.requisitos_ok(h, s.recetas["fundir_piedra_rara"])[0],
                        "la fragua da 1500 °C y ningún mineral sorteado pide más")

    def test_ninguna_receta_se_genero(self):
        s, _ = _mundo(7)
        inventadas = [r for r in s.recetas.values() if r.get("_archivo") == "generado"]
        self.assertEqual(inventadas, [], "el catálogo de recetas sigue siendo fijo")

    def test_las_propiedades_del_metal_nuevo_valen_como_cualquier_otra(self):
        """De acá sale solo lo demás: si al metal le tocó duro y denso, cumple `golpea` y entra en el pico."""
        from mundo_vivo.agentes import conocimiento as C
        s, _ = _mundo(7)
        alguna = False
        for par in s.minerales_mundo:
            for prop in ("funde", "golpea", "conduce", "clava", "imanta", "afila"):
                if C.validar(s.reglas, "prueba", [par["metal"]["id"]], prop)[0]:
                    alguna = True
        self.assertTrue(alguna, "con 2 a 6 metales sorteados, alguno tiene que servir para algo")


class TestPersistencia(unittest.TestCase):
    def test_lo_guardado_manda_sobre_lo_sorteado(self):
        """Si mañana se edita el espacio de lo posible, una partida empezada conserva su geología."""
        s, _ = _mundo(7)
        d = s.exportar_estructuras()
        self.assertTrue(d["minerales"])
        otro, _ = _mundo(1234)
        self.assertNotEqual(otro.minerales_desconocidos(), s.minerales_desconocidos())
        otro.importar_estructuras(d)
        self.assertEqual(otro.minerales_desconocidos(), s.minerales_desconocidos())
        self.assertEqual(otro.etiquetas[ETIQUETA_MENA], set(s.minerales_desconocidos()))
        mid = s.minerales_desconocidos()[0]
        self.assertIn(mid, otro.reglas.materiales)

    def test_un_mundo_viejo_sin_minerales_guardados_abre_igual(self):
        s, _ = _mundo(7)
        propios = s.minerales_desconocidos()
        s.importar_estructuras({"fogatas": [], "refugios": []})
        self.assertEqual(s.minerales_desconocidos(), propios, "los vuelve a sortear de su semilla")


if __name__ == "__main__":
    unittest.main()

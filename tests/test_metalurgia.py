"""Fase 2 del plan del motor: minerales, menas y metalurgia.

Lo que se prueba acá es la CADENA, no una pieza: que exista un camino real desde una persona con las manos
vacías hasta el acero, y que cada escalón esté cerrado por donde tiene que estarlo (el pico para la roca,
el horno para el cobre, la fragua para el hierro). Todo lo que se mide se fabrica de verdad con `_aplicar`:
la trampa del `refugios.append` a mano ya se pagó una vez.
"""
from __future__ import annotations

import unittest

from mundo_vivo import catalogos
from mundo_vivo.agentes import conocimiento as C
from mundo_vivo.generador.pipeline import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion
from mundo_vivo.reglas import Reglas

MENAS = ("piedra_rojiza", "piedra_parda", "piedra_pesada_oscura", "piedra_verdosa", "piedra_azulada",
         "piedra_gris_pesada", "piedra_gris_blanda", "piedra_resinosa", "piedra_plateada",
         "pepita_amarilla", "piedra_opaca_rosada", "piedra_negra", "piedra_grasa",
         "piedra_blanca_blanda", "barro_blanco", "piedra_cristalina", "piedra_amarilla_quebradiza",
         "costra_blanca", "arena")


def _mundo():
    m = generar_mundo(7, 128, 128, 50)
    s = Simulacion(m["capas"], m["meta"])
    x, y = s.terreno.caminable_cerca(64, 64, 40) or (10, 10)
    h = HabitanteSim(1, "Prueba", x + 0.5, y + 0.5)
    s.habitantes[1] = h
    return s, h


def _ensenar(s, h, rid):
    r = s.recetas[rid]
    cid = max(s.conocimientos, default=0) + 1
    s.conocimientos[cid] = {"nombre": r["nombre"], "materiales": r["ingredientes"], "propiedad": r["propiedad"],
                            "descripcion": "", "creador_id": h.id, "origen": "catalogo", "receta_id": rid, "t_min": 0}
    h.conoce.add(cid)
    return r


def _hacer(s, h, rid, et=None):
    """Enseña la receta, le da los ingredientes y la fabrica. Devuelve (ok, texto)."""
    r = _ensenar(s, h, rid)
    et = et or catalogos.cargar_etiquetas()
    for m in r["ingredientes"]:
        s._ganar_item(h, sorted(et[m[1:]])[0] if m.startswith("#") else m, 4)
    ok, texto = s._aplicar(h, {"tipo": "fabricar", "objeto": rid})
    h.accion, h.hasta = "", 0.0
    return ok, texto


class TestMenas(unittest.TestCase):
    def test_estan_las_19_piedras_y_todas_se_pueden_juntar(self):
        reglas = Reglas.cargar()
        for m in MENAS:
            self.assertIn(m, reglas.materiales, "falta la piedra %s" % m)
            r = reglas.materiales[m].get("recoleccion") or {}
            self.assertTrue(r.get("biomas"), "%s no dice en qué biomas sale" % m)

    def test_ningun_id_delata_lo_que_tiene_adentro(self):
        """Regla 8 de CLAUDE.md: la lista de materiales se le muestra a la persona. Nadie nace sabiendo
        que la piedra rojiza tiene hierro adentro."""
        reglas = Reglas.cargar()
        secretos = ("hierro", "cobre", "estano", "plomo", "zinc", "plata", "oro", "aluminio",
                    "mena", "carbon", "cal")
        for m in MENAS:
            texto = m + " " + str(reglas.materiales[m].get("nombre", ""))
            for s in secretos:
                self.assertNotIn(s, texto, "el id/nombre de %s delata que da %s" % (m, s))

    def test_el_metal_no_se_junta_del_suelo(self):
        """Al metal se llega fundiendo: ninguno tiene `recoleccion` (salvo el que cae del cielo)."""
        reglas = Reglas.cargar()
        for metal in ("hierro", "cobre", "bronce", "acero", "estano", "plomo", "zinc", "plata", "oro",
                      "laton", "aluminio", "cal", "cemento", "vidrio"):
            r = reglas.materiales[metal].get("recoleccion") or {}
            self.assertFalse(r.get("biomas"), "%s se junta del suelo y no debería" % metal)

    def test_cada_mena_declara_que_metal_da_y_a_que_temperatura(self):
        reglas = Reglas.cargar()
        for m in MENAS:
            d = reglas.materiales[m]
            if not d.get("mena"):
                continue
            self.assertIn(d["mena"], reglas.materiales, "%s dice dar un metal que no existe" % m)
            self.assertIsNotNone(d.get("punto_fusion_C"), "%s no dice a qué temperatura se derrite" % m)


class TestHerramientaParaJuntar(unittest.TestCase):
    def _en_bioma(self, s, h, mat):
        """Para a la persona en una celda donde ese material salga."""
        import numpy as np
        quiere = s.recoleccion[mat]
        ys, xs = np.nonzero(np.isin(s.terreno.bioma, list(quiere)))
        for x, y in zip(xs, ys):
            if s.terreno.caminable(int(x), int(y)):
                h.x, h.y = int(x) + 0.5, int(y) + 0.5
                return True
        return False

    def test_la_roca_dura_pide_un_pico(self):
        s, h = _mundo()
        if not self._en_bioma(s, h, "piedra_rojiza"):
            self.skipTest("el mundo de prueba no tiene montaña ni caverna")
        self.assertNotIn("piedra_rojiza", s.disponibles(h), "sin pico no se saca la roca de la veta")
        ok, texto = s._aplicar(h, {"tipo": "juntar", "material": "piedra_rojiza"})
        self.assertFalse(ok)
        self.assertIn("roca", texto, texto)
        self.assertTrue(_hacer(s, h, "pico_de_piedra")[0])
        self.assertIn("piedra_rojiza", s.disponibles(h), "con el pico encima sí")

    def test_la_piedra_blanda_se_junta_con_la_mano(self):
        s, h = _mundo()
        if not self._en_bioma(s, h, "piedra_blanca_blanda"):
            self.skipTest("el mundo de prueba no tiene esos biomas")
        self.assertIn("piedra_blanca_blanda", s.disponibles(h))


class TestCadenaDeMetalurgia(unittest.TestCase):
    def _horno(self, s, h):
        from tests.test_calor import _construir
        self.assertTrue(_construir(s, h, "horno_de_barro")[0])

    def _fragua(self, s, h):
        self._horno(s, h)
        self.assertTrue(_hacer(s, h, "fragua")[0])

    def test_el_cobre_sale_con_horno_y_no_con_fogata(self):
        s, h = _mundo()
        s.fogatas.append({"x": h.x, "y": h.y, "hasta": 1e9, "dueno": 1})
        ok, texto = _hacer(s, h, "fundir_cobre")
        self.assertFalse(ok, "una fogata de 600 °C no funde cobre")
        self._horno(s, h)
        ok, texto = _hacer(s, h, "fundir_cobre")
        self.assertTrue(ok, texto)
        self.assertGreater(h.inventario.get("cobre", 0), 0)

    def test_el_plomo_sale_con_una_fogata(self):
        """El escalón de abajo tiene que ser alcanzable el primer día: 330 °C los da cualquier fuego."""
        s, h = _mundo()
        s.fogatas.append({"x": h.x, "y": h.y, "hasta": 1e9, "dueno": 1})
        ok, texto = _hacer(s, h, "fundir_plomo")
        self.assertTrue(ok, texto)

    def test_el_bronce_es_el_primer_metal_de_verdad(self):
        s, h = _mundo()
        self._horno(s, h)
        self.assertTrue(_hacer(s, h, "fundir_cobre")[0])
        self.assertTrue(_hacer(s, h, "fundir_estano")[0])
        ok, texto = _hacer(s, h, "bronce_fundido")
        self.assertTrue(ok, texto)
        self.assertGreaterEqual(h.inventario.get("bronce", 0), 2)

    def test_el_hierro_y_el_acero_piden_la_fragua(self):
        s, h = _mundo()
        self._horno(s, h)
        self.assertFalse(_hacer(s, h, "fundir_hierro")[0], "el horno no alcanza para hierro")
        self.assertTrue(_hacer(s, h, "fragua")[0])
        self.assertEqual(s.calor_disponible(h), 1500.0)
        self.assertTrue(_hacer(s, h, "fundir_hierro")[0])
        ok, texto = _hacer(s, h, "acero_forjado")
        self.assertTrue(ok, texto)
        self.assertGreater(h.inventario.get("acero", 0), 0)

    def test_de_la_caliza_sale_el_cemento_y_de_ahi_la_calle(self):
        """Lo que CLAUDE.md daba por hecho y no existía: la cal, el cemento y las calles."""
        s, h = _mundo()
        self._fragua(s, h)
        self.assertTrue(_hacer(s, h, "cal_viva")[0])
        self.assertTrue(_hacer(s, h, "cemento_cocido")[0])
        ok, texto = _hacer(s, h, "calle_empedrada")
        self.assertTrue(ok, texto)
        self.assertTrue(any(r["tipo"] == "calle_empedrada" for r in s.refugios))

    def test_la_casa_de_piedra_es_el_techo_de_la_cadena_constructiva(self):
        s, h = _mundo()
        self._fragua(s, h)
        self.assertTrue(_hacer(s, h, "cal_viva")[0])
        self.assertTrue(_hacer(s, h, "mortero")[0])
        ok, texto = _hacer(s, h, "casa_de_piedra")
        self.assertTrue(ok, texto)
        casa = next(r for r in s.refugios if r["tipo"] == "casa_de_piedra")
        self.assertEqual(casa["abrigo"], 0.8)
        self.assertGreater(casa["abrigo"], s.recetas["cabana_de_troncos"]["estructura"]["abrigo"])

    def test_la_fragua_pide_arcilla_refractaria_y_esa_viene_del_barro_blanco(self):
        s, h = _mundo()
        self.assertIn("arcilla_refractaria", s.recetas["fragua"]["ingredientes"])
        self.assertEqual(s.recetas["barro_refractario"]["resultado"]["item"], "arcilla_refractaria")

    def test_el_aluminio_queda_fuera_de_alcance_a_proposito(self):
        """2050 °C: la piedra opaca y rosada se puede juntar, pero no hay con qué fundirla todavía."""
        s, _ = _mundo()
        self.assertIn("piedra_opaca_rosada", s.recoleccion)
        funde_aluminio = [r for r in s.recetas.values()
                          if (r.get("resultado") or {}).get("item") == "aluminio"]
        self.assertEqual(funde_aluminio, [], "si alguien le escribe la receta, la validación del catálogo "
                                            "tiene que exigir una estructura de 2050 °C")


class TestVocabularioUsado(unittest.TestCase):
    def test_las_8_propiedades_nuevas_tienen_al_menos_una_receta(self):
        """Una propiedad sin receta es decoración: nadie puede inventar nada con ella."""
        reglas = Reglas.cargar()
        recetas = catalogos.cargar_recetas(reglas.materiales, C.PROPIEDADES)
        usadas = {r["propiedad"] for r in recetas.values()}
        for prop in ("funde", "golpea", "clava", "mezcla", "muele", "afila", "imanta", "aisla"):
            self.assertIn(prop, usadas, "la propiedad '%s' no la usa ninguna receta" % prop)

    def test_cada_propiedad_la_cumple_algun_material_del_mundo(self):
        """Y un `path` que ningún material tiene deja la propiedad inalcanzable."""
        reglas = Reglas.cargar()
        for prop in ("funde", "golpea", "clava", "mezcla", "muele", "afila", "imanta", "aisla"):
            alguno = any(C.validar(reglas, "prueba", [m], prop)[0] for m in reglas.materiales)
            self.assertTrue(alguno, "ningún material del mundo cumple '%s'" % prop)


if __name__ == "__main__":
    unittest.main()

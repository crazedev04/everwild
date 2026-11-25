"""Fase D: la progresión tecnológica sale de la temperatura, no de un `if` en el motor.

Fase 0 del plan del motor: y además la estructura que da esa temperatura tiene que poder CONSTRUIRSE.
La versión vieja de este archivo inyectaba los refugios a mano (`s.refugios.append({... "tipo": "horno"})`),
así que verificaba el lector (`calor_disponible`) y nunca el escritor: el horno y la fragua vivieron meses
declarados en los datos sin ninguna receta que los levantara, y el techo real de calor del mundo era 600 °C.
Lo que sigue **fabrica de verdad** con `_aplicar` y recién después mide.
"""
from __future__ import annotations

import unittest

from mundo_vivo import catalogos
from mundo_vivo.motor.generador import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion


def _mundo():
    m = generar_mundo(7, 128, 128, 50)
    s = Simulacion(m["capas"], m["meta"])
    x, y = s.terreno.caminable_cerca(64, 64, 40) or (10, 10)   # construir pide suelo caminable
    h = HabitanteSim(1, "Prueba", x + 0.5, y + 0.5)
    s.habitantes[1] = h
    return s, h


def _ensenar(s, h, rid):
    """Le da la receta del catálogo sin pasar por el descubrimiento."""
    r = s.recetas[rid]
    cid = max(s.conocimientos, default=0) + 1
    s.conocimientos[cid] = {"nombre": r["nombre"], "materiales": r["ingredientes"], "propiedad": r["propiedad"],
                            "descripcion": "", "creador_id": h.id, "origen": "catalogo", "receta_id": rid, "t_min": 0}
    h.conoce.add(cid)
    return r


def _construir(s, h, rid):
    """Fabrica de verdad: mismo camino que usa el cerebro. Devuelve (ok, texto)."""
    r = _ensenar(s, h, rid)
    et = catalogos.cargar_etiquetas()
    for m in r["ingredientes"]:
        s._ganar_item(h, sorted(et[m[1:]])[0] if m.startswith("#") else m, 3)
    ok, texto = s._aplicar(h, {"tipo": "fabricar", "objeto": rid})
    h.accion, h.hasta = "", 0.0            # el tiempo de obra no interesa para medir el calor
    return ok, texto


class TestCalor(unittest.TestCase):
    def test_las_estructuras_declaran_sus_grados(self):
        s, _ = _mundo()
        self.assertEqual(s.estructuras["fogata"]["provee"]["calor_C"], 600)
        self.assertEqual(s.estructuras["horno_de_barro"]["provee"]["calor_C"], 1000)
        self.assertEqual(s.estructuras["fragua"]["provee"]["calor_C"], 1500)

    def test_sin_nada_no_hay_calor(self):
        s, h = _mundo()
        self.assertEqual(s.calor_disponible(h), 0.0)

    def test_es_el_maximo_y_no_la_suma(self):
        """Dos fogatas no son un horno."""
        s, h = _mundo()
        s.fogatas.append({"x": h.x, "y": h.y, "hasta": 1e9, "dueno": 1})
        s.fogatas.append({"x": h.x + 0.2, "y": h.y, "hasta": 1e9, "dueno": 1})
        self.assertEqual(s.calor_disponible(h), 600.0)

    def test_las_recetas_viejas_siguen_funcionando(self):
        """`requiere_fuego: true` se entiende como 400 °C: lo que da una fogata, igual que siempre."""
        s, h = _mundo()
        vieja = {"id": "x", "nombre": "prueba", "requiere_fuego": True}
        self.assertFalse(s.requisitos_ok(h, vieja)[0])
        s.fogatas.append({"x": h.x, "y": h.y, "hasta": 1e9, "dueno": 1})
        self.assertTrue(s.requisitos_ok(h, vieja)[0])

    def test_una_receta_sin_requisitos_se_hace_en_cualquier_lado(self):
        s, h = _mundo()
        self.assertTrue(s.requisitos_ok(h, {"id": "x", "nombre": "prueba"})[0])

    # ------------------------------------------------- fase 0: se construye de verdad
    def test_el_horno_se_construye_y_sube_el_techo_de_calor(self):
        s, h = _mundo()
        ok, texto = _construir(s, h, "horno_de_barro")
        self.assertTrue(ok, texto)
        self.assertTrue(any(r["tipo"] == "horno_de_barro" for r in s.refugios),
                        "fabricar el horno tiene que dejar una ESTRUCTURA, no un ítem de inventario")
        self.assertEqual(h.inventario.get("horno_de_barro", 0), 0, "el horno no se guarda en el bolsillo")
        self.assertEqual(s.calor_disponible(h), 1000.0)
        self.assertTrue(s.requisitos_ok(h, s.recetas["ceramica_cocida"])[0], "con horno se cuece cerámica")

    def test_sin_horno_la_ceramica_no_sale(self):
        s, h = _mundo()
        s.fogatas.append({"x": h.x, "y": h.y, "hasta": 1e9, "dueno": 1})
        self.assertFalse(s.requisitos_ok(h, s.recetas["ceramica_cocida"])[0],
                         "con una fogata (600 °C) no se cuece cerámica (900 °C)")

    def test_la_fragua_pide_un_horno_antes(self):
        """Nadie hace una fragua al aire libre: pide 1000 °C, o sea un horno ya construido."""
        s, h = _mundo()
        _ensenar(s, h, "fragua")
        et = catalogos.cargar_etiquetas()
        for m in s.recetas["fragua"]["ingredientes"]:
            s._ganar_item(h, sorted(et[m[1:]])[0] if m.startswith("#") else m, 3)
        ok, texto = s._aplicar(h, {"tipo": "fabricar", "objeto": "fragua"})
        self.assertFalse(ok, "sin horno no hay fragua")
        self.assertIn("fuego", texto.lower())
        self.assertTrue(_construir(s, h, "horno_de_barro")[0])
        ok, texto = s._aplicar(h, {"tipo": "fabricar", "objeto": "fragua"})
        self.assertTrue(ok, texto)
        h.accion, h.hasta = "", 0.0
        self.assertEqual(s.calor_disponible(h), 1500.0, "la fragua es el escalón de arriba")

    def test_el_horno_no_gasta_el_cupo_de_casas(self):
        """El tope de refugios es de CASAS: con un horno encima todavía se tiene que poder construir."""
        s, h = _mundo()
        self.assertTrue(_construir(s, h, "horno_de_barro")[0])
        self.assertTrue(_construir(s, h, "fragua")[0])
        ok, texto = _construir(s, h, "choza_de_barro")
        self.assertTrue(ok, texto)
        self.assertIsNotNone(h.hogar, "la casa sí es hogar")

    def test_la_fragua_no_es_la_casa_de_nadie(self):
        s, h = _mundo()
        self.assertTrue(_construir(s, h, "horno_de_barro")[0])
        self.assertIsNone(h.hogar, "un horno no es un hogar")

    def test_un_escalon_de_calor_nuevo_es_un_hito(self):
        s, h = _mundo()
        _construir(s, h, "horno_de_barro")
        self.assertIn("calor_1000", s.hitos)
        self.assertNotIn("vivienda", s.hitos, "un horno no es la primera vivienda")

    # ------------------------------------------------- fase 0: el catálogo se valida
    def test_una_estructura_que_no_se_puede_construir_es_error_de_catalogo(self):
        """La trampa que cerró la fase 0: declarar grados que nadie puede alcanzar."""
        rec = dict(catalogos.cargar("recetas", "receta"))
        est = {"volcan_de_bolsillo": {"id": "volcan_de_bolsillo", "provee": {"calor_C": 2000},
                                      "_archivo": "prueba.json"}}
        with self.assertRaises(catalogos.ErrorDeCatalogo) as e:
            catalogos._validar_estructuras(rec, est)
        self.assertIn("no hay forma de tenerla", str(e.exception))

    def test_una_receta_de_estructura_sin_el_campo_estructura_es_error(self):
        """El bug exacto del horno: receta con el id correcto pero sin `estructura`, así que daba un ítem."""
        rec = {"horno_de_barro": {"id": "horno_de_barro", "ingredientes": ["arcilla"], "_archivo": "prueba.json"}}
        est = {"horno_de_barro": {"id": "horno_de_barro", "provee": {"calor_C": 1000}, "_archivo": "prueba.json"}}
        with self.assertRaises(catalogos.ErrorDeCatalogo) as e:
            catalogos._validar_estructuras(rec, est)
        self.assertIn("estructura", str(e.exception))

    def test_una_receta_que_pide_mas_calor_del_que_existe_es_error(self):
        rec = {"imposible": {"id": "imposible", "requiere": {"calor_C": 3000}, "_archivo": "prueba.json"}}
        est = {"fogata": {"id": "fogata", "provee": {"calor_C": 600}, "provisto_por": "motor",
                          "_archivo": "prueba.json"}}
        with self.assertRaises(catalogos.ErrorDeCatalogo) as e:
            catalogos._validar_estructuras(rec, est)
        self.assertIn("nadie la podría hacer nunca", str(e.exception))

    def test_el_catalogo_de_verdad_pasa_la_validacion(self):
        s, _ = _mundo()
        catalogos._validar_estructuras(s.recetas, s.estructuras)       # no tira

    def test_toda_estructura_con_grados_tiene_receta_o_es_del_motor(self):
        """El techo de calor del mundo tiene que ser alcanzable, no declarado."""
        s, h = _mundo()
        alcanzable = max(float((e.get("provee") or {}).get("calor_C", 0))
                         for eid, e in s.estructuras.items()
                         if e.get("provisto_por") == "motor" or e.get("natural") or eid in s.recetas)
        self.assertEqual(alcanzable, 1500.0, "la metalurgia necesita 1500 °C al alcance")


if __name__ == "__main__":
    unittest.main()

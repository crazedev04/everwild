"""Fase M: hablar tiene consecuencias. Y se puede mentir.

Hasta ahora una conversación dejaba un recuerdo y nada más. Lo pide la sección 3.11 del documento de
arquitectura: «la comunicación debe generar consecuencias cognitivas».
"""
from __future__ import annotations

import unittest

from mundo_vivo.agentes.genoma import genoma_fundador
from mundo_vivo.generador.pipeline import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion


def _dos():
    m = generar_mundo(7, 128, 128, 50)
    s = Simulacion(m["capas"], m["meta"])
    a = HabitanteSim(1, "Ana", 10.5, 10.5)
    b = HabitanteSim(2, "Beto", 10.8, 10.5)
    for h in (a, b):
        h.genoma = genoma_fundador(h.id)
        s.habitantes[h.id] = h
    return s, a, b


def _limpiar(a, b):
    """Las charlas tienen veda entre sí; para probar varias seguidas hay que levantarla."""
    for h in (a, b):
        h.ultima_charla, h.ultimo_dicho, h.historial_dicho = {}, {}, []


class TestConsecuencias(unittest.TestCase):
    def test_advertir_le_pasa_el_peligro_al_otro(self):
        s, a, b = _dos()
        a.marcar_lugar("peligro", 30, 30, "un oso", 0.0)
        self.assertIsNone(b.lugares.get("peligro"))
        ok, _ = s._accion_hablar(a, {"a": 2, "mensaje": "Cuidado, hay un oso por allá", "intencion": "advertir"})
        self.assertTrue(ok)
        self.assertTrue(b.lugares.get("peligro"), "la advertencia tiene que quedarle anotada")
        self.assertGreater(b.emo["miedo"], 0.0, "y tiene que asustarlo un poco")

    def test_contar_pasa_un_lugar_que_el_que_habla_conoce(self):
        s, a, b = _dos()
        a.marcar_lugar("agua", 40, 40, "un arroyo", 0.0)
        s._accion_hablar(a, {"a": 2, "mensaje": "Vi un arroyo grande por el norte", "intencion": "contar"})
        total = sum(len(v) for v in b.lugares.values())
        self.assertGreater(total, 0, "contar algo útil tiene que servirle al otro")

    def test_no_se_puede_contar_lo_que_no_se_sabe(self):
        s, a, b = _dos()
        s._accion_hablar(a, {"a": 2, "mensaje": "Hay cosas interesantes por ahí", "intencion": "contar"})
        self.assertFalse(any(b.lugares.values()), "no sabe nada: no puede pasar nada")

    def test_preguntar_no_transfiere_nada(self):
        s, a, b = _dos()
        a.marcar_lugar("agua", 40, 40, "un arroyo", 0.0)
        s._accion_hablar(a, {"a": 2, "mensaje": "¿Vos sabés dónde hay agua por acá?", "intencion": "preguntar"})
        self.assertFalse(any(b.lugares.values()))


class TestMentir(unittest.TestCase):
    def test_el_que_escucha_se_lo_cree(self):
        """Un lugar que no existe, con la misma certeza que uno verdadero. No hay forma de saberlo hasta ir."""
        s, a, b = _dos()
        ok, _ = s._accion_hablar(a, {"a": 2, "mensaje": "Hay un río enorme hacia el este, te juro",
                                     "intencion": "mentir"})
        self.assertTrue(ok)
        self.assertTrue(b.lugares.get("agua"), "la mentira tiene que entrar como si fuera cierta")

    def test_mentir_cuesta(self):
        s, a, b = _dos()
        antes = a.rasgo("empatia")
        s._accion_hablar(a, {"a": 2, "mensaje": "Hay un río enorme hacia el este, te juro",
                             "intencion": "mentir"})
        self.assertLess(a.rasgo("empatia"), antes, "mentir va corriendo el carácter")

    def test_queda_registrado_para_el_observador(self):
        """El mundo sabe que fue mentira aunque los habitantes no."""
        s, a, b = _dos()
        s._accion_hablar(a, {"a": 2, "mensaje": "Hay un río enorme hacia el este", "intencion": "mentir"})
        self.assertTrue(any(e["tipo"] == "mentira" for e in s._eventos))

    def test_lo_que_le_contaron_queda_como_OIDO(self):
        s, a, b = _dos()
        s._accion_hablar(a, {"a": 2, "mensaje": "Hay un río enorme hacia el este", "intencion": "mentir"})
        oidos = [e for e in s._eventos
                 if e["tipo"] == "_memoria" and (e.get("datos") or {}).get("origen") == "oido"]
        self.assertTrue(oidos, "aunque sea mentira, el que escucha sabe que se lo contaron")
        self.assertEqual(oidos[0]["datos"]["de_quien"], a.id)


class TestIntencionInvalida(unittest.TestCase):
    def test_una_intencion_rara_se_trata_como_contar(self):
        s, a, b = _dos()
        a.marcar_lugar("agua", 40, 40, "un arroyo", 0.0)
        ok, _ = s._accion_hablar(a, {"a": 2, "mensaje": "Algo te quiero decir", "intencion": "hipnotizar"})
        self.assertTrue(ok, "no puede romper por una intención que no existe")


if __name__ == "__main__":
    unittest.main()

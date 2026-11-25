"""Fase J: objetivos propios (Utility AI) y encadenado de precondiciones (GOAP corto).

Antes `h.plan` eran tres frases de texto que nadie ejecutaba. Acá una intención se convierte en pasos reales.
"""
from __future__ import annotations

import unittest

from mundo_vivo.motor.generador import generar_mundo
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion


def _mundo(frio=False):
    """Por defecto sin frío: el punto de prueba del mapa es helado (severidad 0,75) y «calentarse» le ganaría
    a todo lo demás, que es lo correcto pero tapa lo que se quiere medir acá."""
    m = generar_mundo(7, 128, 128, 50)
    s = Simulacion(m["capas"], m["meta"])
    for k in ("objetivos", "atributos", "hambre", "conocimientos"):
        s.ajustes["modulos"][k] = True
    s.ajustes["modulos"]["frio"] = frio
    h = HabitanteSim(1, "Prueba", 10.5, 10.5)
    s.habitantes[1] = h
    return s, h


class TestElegirObjetivo(unittest.TestCase):
    def test_gana_lo_que_mas_aprieta(self):
        s, h = _mundo()
        h.sed, h.hambre = 85.0, 50.0
        self.assertEqual(s.elegir_objetivo(h)["que"], "beber", "la sed mata antes que el hambre")
        h.objetivo, h.sed, h.hambre = None, 10.0, 85.0
        self.assertEqual(s.elegir_objetivo(h)["que"], "comer")

    def test_sin_nada_urgente_se_propone_un_oficio(self):
        s, h = _mundo()
        o = s.elegir_objetivo(h)
        self.assertEqual(o["que"], "conseguir")
        self.assertIn(o["receta"], s.objetivos, "tiene que salir de la lista de objetivos (que es un dato)")
        self.assertTrue(o["porque"], "un objetivo sin motivo no se puede contar")

    def test_no_cambia_de_idea_a_cada_rato(self):
        """Histéresis: el objetivo que ya tenía gana salvo que otro le saque buena ventaja."""
        s, h = _mundo()
        primero = s.elegir_objetivo(h)
        for _ in range(20):
            igual = s.elegir_objetivo(h)
        self.assertEqual(igual["que"], primero["que"])
        self.assertEqual(igual.get("receta"), primero.get("receta"))
        self.assertEqual(igual["desde"], primero["desde"], "no se reinicia el reloj del objetivo")

    def test_el_frio_tambien_es_una_urgencia(self):
        """Si se está helando, entrar en calor le gana a hacer una herramienta."""
        s, h = _mundo(frio=True)
        if s.severidad_frio(h) < 0.3:
            self.skipTest("este punto del mapa no es frío")
        self.assertEqual(s.elegir_objetivo(h)["que"], "calentarse")

    def test_una_urgencia_sí_lo_hace_cambiar(self):
        s, h = _mundo()
        s.elegir_objetivo(h)
        h.sed = 95.0
        self.assertEqual(s.elegir_objetivo(h)["que"], "beber")

    def test_el_objetivo_sobrevive_al_guardado(self):
        import tempfile
        from pathlib import Path
        from mundo_vivo.persistencia import db, mundo_io, sim_io
        with tempfile.TemporaryDirectory() as d:
            ruta = mundo_io.crear_mundo(Path(d), 777, 128, 128, tam_celda_m=50)
            con = db.abrir(ruta)
            try:
                sim_io.crear_habitantes_iniciales(con, 4)
                sim = sim_io.cargar_simulacion(con)
                sim.ajustes["modulos"]["objetivos"] = True
                h = sim.habitantes[1]
                o = sim.elegir_objetivo(h)
                sim_io.guardar_simulacion(con, sim)
                s2 = sim_io.cargar_simulacion(con)
                self.assertEqual(s2.habitantes[1].objetivo["que"], o["que"])
            finally:
                con.close()


class TestCadenaDePrecondiciones(unittest.TestCase):
    """El GOAP: «quiero X» se desarma en saber -> materiales -> calor. Sale del registro, no de código."""

    def test_si_no_sabe_la_receta_el_paso_es_inventarla(self):
        s, h = _mundo()
        paso = s._cadena_receta(h, "taladro_de_fuego")
        self.assertEqual(paso["tipo"], "inventar")
        self.assertEqual(paso["receta"]["propiedad"], "enciende")

    def test_si_la_sabe_pero_le_faltan_materiales_el_paso_es_juntarlos(self):
        s, h = _mundo()
        r = s.recetas["taladro_de_fuego"]
        h.conoce.add(1)
        s.conocimientos[1] = {"nombre": r["nombre"], "materiales": r["ingredientes"],
                              "propiedad": r["propiedad"], "receta_id": "taladro_de_fuego",
                              "creador_id": 1, "origen": "catalogo", "t_min": 0}
        import numpy as np
        from mundo_vivo.motor import biomas as B
        ys, xs = np.nonzero(s.terreno.bioma == B.PRADERA)
        if not len(xs):
            self.skipTest("este mundo no tiene pradera")
        h.x, h.y = float(xs[0]) + 0.5, float(ys[0]) + 0.5
        paso = s._cadena_receta(h, "taladro_de_fuego")
        self.assertEqual(paso["tipo"], "juntar")
        self.assertIn(paso["material"], r["ingredientes"])

    def test_con_todo_listo_el_paso_es_fabricar(self):
        s, h = _mundo()
        r = s.recetas["taladro_de_fuego"]
        h.conoce.add(1)
        s.conocimientos[1] = {"nombre": r["nombre"], "materiales": r["ingredientes"],
                              "propiedad": r["propiedad"], "receta_id": "taladro_de_fuego",
                              "creador_id": 1, "origen": "catalogo", "t_min": 0}
        for ing in r["ingredientes"]:
            h.inventario[ing] = 5
        paso = s._cadena_receta(h, "taladro_de_fuego")
        self.assertEqual(paso["tipo"], "fabricar")
        self.assertEqual(paso["objeto"], "taladro_de_fuego")

    def test_un_plan_que_no_se_puede_se_abandona_y_replanifica(self):
        s, h = _mundo()
        h.objetivo = {"que": "conseguir", "receta": "no_existe_esta_receta", "desde": s.t, "porque": "x"}
        paso = s.plan_de_objetivo(h)
        self.assertIsNotNone(paso, "tiene que proponer otra cosa en vez de quedarse trabado")

    def test_con_el_modulo_apagado_no_se_mete(self):
        s, h = _mundo()
        s.ajustes["modulos"]["objetivos"] = False
        self.assertIsNone(s.elegir_objetivo(h))
        self.assertIsNone(s.plan_de_objetivo(h))


if __name__ == "__main__":
    unittest.main()

"""Fase G2: dimensiones y portales.

Es la única fase que NO es aditiva, así que la mitad de estos tests son de compatibilidad: un mundo que
nunca vio un portal tiene que comportarse exactamente igual que antes.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from mundo_vivo.agentes import ajustes as aj
from mundo_vivo.motor import biomas as B
from mundo_vivo.generador.pipeline import generar_mundo
from mundo_vivo.motor.navegacion import Terreno
from mundo_vivo.persistencia import db, mundo_io, sim_io


class TestGeneradorCavernas(unittest.TestCase):
    def test_hay_roca_hueco_agua_y_todo_conectado(self):
        m = generar_mundo(4242, 192, 192, 5, dimension="cavernas")
        b = m["capas"]["bioma"]
        roca = int((b == B.ROCA_VIVA).sum())
        hueco = int((b == B.CAVERNA).sum() + (b == B.HONGAL).sum())
        self.assertGreater(roca, 0.15 * b.size, "una caverna sin roca es una pradera")
        self.assertGreater(hueco, 0.2 * b.size, "una caverna sin huecos no se puede caminar")
        self.assertTrue((m["capas"]["agua"] == B.AGUA_LAGO).any(), "falta el agua del fondo")
        # lo caminable es UNA sola cueva: un portal no puede dejar a nadie encerrado en una burbuja
        t = Terreno(m["capas"], 5)
        ys, xs = np.nonzero(b == B.CAVERNA)
        self.assertGreaterEqual(t.componente(int(xs[0]), int(ys[0])), 0.9 * hueco)

    def test_la_misma_semilla_da_la_misma_caverna(self):
        a = generar_mundo(7, 96, 96, 5, dimension="cavernas")["capas"]["bioma"]
        b = generar_mundo(7, 96, 96, 5, dimension="cavernas")["capas"]["bioma"]
        self.assertTrue((a == b).all())
        c = generar_mundo(8, 96, 96, 5, dimension="cavernas")["capas"]["bioma"]
        self.assertFalse((a == c).all())

    def test_el_mundo_de_siempre_no_cambia(self):
        """El generador continental no se tocó: una dimensión nueva no puede mover el mapa de nadie."""
        a = generar_mundo(123, 96, 96, 50)
        b = generar_mundo(123, 96, 96, 50, dimension="mundo")
        for k in a["capas"]:
            self.assertTrue((a["capas"][k] == b["capas"][k]).all(), k)


class _Mundo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = mundo_io.crear_mundo(Path(self.tmp.name), 11, 128, 128, tam_celda_m=50)
        self.con = db.abrir(self.ruta)
        sim_io.crear_habitantes_iniciales(self.con, 2)
        aj.guardar(self.con, {"modulos": {"cerebro_llm": False, "fauna": False}})

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def _portal(self, sim, h, tipo="pozo_a_las_cavernas"):
        sim.refugios.append({"rid": 1, "x": h.x, "y": h.y, "dueno": h.id, "tipo": tipo,
                             "nombre": tipo, "abrigo": 0.0, "t": int(sim.t)})


class TestMundoViejo(_Mundo):
    def test_un_mundo_sin_portales_tiene_una_sola_dimension(self):
        mundo = sim_io.cargar_mundo(self.con)
        self.assertEqual([d["id"] for d in mundo.dimensiones()], [0])
        self.assertIs(mundo.principal, mundo.sims[0])
        mundo.avanzar(60)
        sim_io.guardar_mundo_vivo(self.con, mundo)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM habitantes WHERE dimension != 0").fetchone()[0], 0)

    def test_el_estado_dinamico_viejo_se_sigue_leyendo(self):
        """La dimensión 0 guarda con las claves de siempre: sin esto, un mundo que venía andando pierde
        el fuego, la nieve y las estructuras al abrirlo con la versión nueva."""
        mundo = sim_io.cargar_mundo(self.con)
        mundo.principal.fogatas.append({"x": 10.0, "y": 10.0, "hasta": mundo.principal.t + 9999})
        sim_io.guardar_mundo_vivo(self.con, mundo)
        claves = [r[0] for r in self.con.execute("SELECT clave FROM estado_dinamico")]
        self.assertIn("estructuras", claves)
        self.assertFalse(any(c.startswith("d") and ":" in c for c in claves))
        otra = sim_io.cargar_mundo(self.con)
        self.assertEqual(len(otra.principal.fogatas), 1)


class TestPasaje(_Mundo):
    def test_cruzar_crea_la_dimension_y_mueve_a_la_persona(self):
        mundo = sim_io.cargar_mundo(self.con)
        sim = mundo.principal
        h = next(iter(sim.habitantes.values()))
        self._portal(sim, h)
        ok, texto = sim._accion_atravesar(h, {})
        self.assertTrue(ok, texto)
        cav = mundo.de_ident("cavernas")
        self.assertIsNotNone(cav)
        self.assertIn(h.id, cav.habitantes)
        self.assertNotIn(h.id, sim.habitantes)
        self.assertTrue(cav.terreno.caminable(int(h.x), int(h.y)), "no se puede aparecer dentro de la roca")

    def test_sin_portal_al_lado_no_se_cruza(self):
        mundo = sim_io.cargar_mundo(self.con)
        sim = mundo.principal
        h = next(iter(sim.habitantes.values()))
        ok, _ = sim._accion_atravesar(h, {})
        self.assertFalse(ok)
        self.assertEqual([d["id"] for d in mundo.dimensiones()], [0])

    def test_bajo_tierra_no_hay_estaciones_ni_tormentas(self):
        mundo = sim_io.cargar_mundo(self.con)
        sim = mundo.principal
        h = next(iter(sim.habitantes.values()))
        self._portal(sim, h)
        sim._accion_atravesar(h, {})
        cav = mundo.de_ident("cavernas")
        self.assertFalse(cav.cielo.get("dia_noche", True))
        antes = cav.temp_en(h.x, h.y)
        mundo.avanzar(1440)                      # un día entero del mundo
        self.assertAlmostEqual(cav.temp_en(h.x, h.y), antes, places=6)
        self.assertEqual(len(cav.clima.a_publico()), 0)
        self.assertEqual(float(cav.nieve.sum()), 0.0)

    def test_sobrevive_a_guardar_y_recargar(self):
        mundo = sim_io.cargar_mundo(self.con)
        sim = mundo.principal
        h = next(iter(sim.habitantes.values()))
        self._portal(sim, h)
        sim._accion_atravesar(h, {})
        mundo.avanzar(30)
        sim_io.volcar_eventos_mundo(self.con, mundo)
        sim_io.guardar_mundo_vivo(self.con, mundo)
        otra = sim_io.cargar_mundo(self.con)
        self.assertEqual([d["id"] for d in otra.dimensiones()], [0, 1])
        self.assertIn(h.id, otra.de_ident("cavernas").habitantes)
        self.assertNotIn(h.id, otra.principal.habitantes)
        # el suceso quedó anotado en la dimensión donde pasó
        fila = self.con.execute("SELECT dimension FROM eventos WHERE tipo = 'paso_dimension'").fetchone()
        self.assertEqual(fila[0], 0)

    def test_lo_que_es_del_mundo_se_comparte_entre_dimensiones(self):
        """Inventar algo abajo lo sabe el de arriba; apagar un módulo lo apaga en todas partes."""
        mundo = sim_io.cargar_mundo(self.con)
        sim = mundo.principal
        h = next(iter(sim.habitantes.values()))
        self._portal(sim, h)
        sim._accion_atravesar(h, {})
        cav = mundo.de_ident("cavernas")
        self.assertIs(cav.ajustes, sim.ajustes)
        self.assertIs(cav.conocimientos, sim.conocimientos)
        self.assertIs(cav.cerebro, sim.cerebro)
        self.assertIsNot(cav.terreno, sim.terreno)      # el mapa NO se comparte
        self.assertIsNot(cav.fuego, sim.fuego)
        self.assertIsNot(cav.fauna, sim.fauna)

    def test_el_reloj_es_del_mundo_y_no_del_mapa(self):
        mundo = sim_io.cargar_mundo(self.con)
        h = next(iter(mundo.principal.habitantes.values()))
        self._portal(mundo.principal, h)
        mundo.principal._accion_atravesar(h, {})
        mundo.avanzar(120)
        self.assertAlmostEqual(mundo.principal.t, mundo.de_ident("cavernas").t, places=6)


class TestCapasPorDimension(_Mundo):
    def test_cada_dimension_guarda_su_mapa(self):
        d = mundo_io.crear_dimension(self.con, "cavernas")
        self.assertEqual(d["id"], 1)
        arriba = mundo_io.cargar_capas(self.con, dimension=0)
        abajo = mundo_io.cargar_capas(self.con, dimension=1)
        self.assertEqual(arriba["bioma"].shape, (128, 128))
        self.assertEqual(abajo["bioma"].shape, (d["alto"], d["ancho"]))
        self.assertTrue((abajo["bioma"] == B.ROCA_VIVA).any())
        self.assertFalse((arriba["bioma"] == B.ROCA_VIVA).any())
        # y la huella de integridad del mapa nuevo cierra
        mundo_io.cargar_capas(self.con, verificar=True, dimension=1)

    def test_crear_dos_veces_la_misma_dimension_no_la_duplica(self):
        a = mundo_io.crear_dimension(self.con, "cavernas")
        b = mundo_io.crear_dimension(self.con, "cavernas")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM dimensiones").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()


class TestBocasNaturales(_Mundo):
    """Las bocas de caverna de la montaña: están desde siempre, no las construyó nadie."""

    def test_se_siembran_en_la_montana_y_siempre_en_el_mismo_lugar(self):
        a = sim_io.cargar_mundo(self.con).principal
        bocas = [r for r in a.refugios if r["tipo"] == "boca_de_caverna"]
        self.assertTrue(bocas, "un mundo con montañas tiene que tener bocas")
        for b in bocas:
            self.assertIn(int(a.terreno.bioma[int(b["y"]), int(b["x"])]), (B.MONTANA, B.NIEVE))
            self.assertTrue(a.terreno.caminable(int(b["x"]), int(b["y"])))
            self.assertIsNone(b["dueno"], "no la construyó nadie")
        sim_io.guardar_mundo_vivo(self.con, a.mundo)
        b2 = [r for r in sim_io.cargar_mundo(self.con).principal.refugios if r["tipo"] == "boca_de_caverna"]
        self.assertEqual(len(bocas), len(b2), "recargar el mundo no puede duplicar las bocas")
        self.assertEqual(sorted((r["x"], r["y"]) for r in bocas), sorted((r["x"], r["y"]) for r in b2))

    def test_bajar_y_volver_te_deja_donde_estabas(self):
        mundo = sim_io.cargar_mundo(self.con)
        sim = mundo.principal
        h = next(iter(sim.habitantes.values()))
        boca = [r for r in sim.refugios if r["tipo"] == "boca_de_caverna"][0]
        h.x, h.y = boca["x"], boca["y"]
        self.assertTrue(sim._accion_atravesar(h, {})[0])
        cav = mundo.de_ident("cavernas")
        abajo = (h.x, h.y)
        self.assertTrue(any(r["tipo"] == "boca_a_la_superficie" for r in cav.refugios),
                        "tiene que quedar una salida donde uno aparece")
        ok, _ = cav._accion_atravesar(h, {})
        self.assertTrue(ok)
        self.assertAlmostEqual(h.x, boca["x"], places=6)
        self.assertAlmostEqual(h.y, boca["y"], places=6)
        # y volver a bajar lleva al MISMO lugar de antes
        sim._accion_atravesar(h, {})
        self.assertEqual((h.x, h.y), abajo)

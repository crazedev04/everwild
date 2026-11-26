import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from mundo_vivo.motor import biomas as B
from mundo_vivo.persistencia import db, mundo_io, sim_io


class TestSimIO(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _mundo(self, semilla=42):
        ruta = mundo_io.crear_mundo(self.dir, semilla, 128, 128, tam_celda_m=50)
        return ruta, db.abrir(ruta)

    def test_fundadores_junto_al_agua_y_no_se_duplican(self):
        _, con = self._mundo()
        ids = sim_io.crear_habitantes_iniciales(con, 4)
        self.assertEqual(len(ids), 4)
        self.assertEqual(sim_io.crear_habitantes_iniciales(con, 4), ids)  # idempotente
        sim = sim_io.cargar_simulacion(con)
        for h in sim.habitantes.values():
            self.assertTrue(sim.agua_cercana(h, 30) is not None)
        self.assertEqual(len(mundo_io.listar_eventos(con, tipo="llegada")), 4)
        con.close()

    def test_guardar_y_cargar_conserva_todo(self):
        ruta, con = self._mundo()
        sim_io.crear_habitantes_iniciales(con, 4)
        sim = sim_io.cargar_simulacion(con)
        import numpy as np
        ys, xs = np.nonzero(sim.fuego.comb > 0.5)
        i = int(np.argmax(np.hypot(xs - sim.habitantes[1].x, ys - sim.habitantes[1].y) > 25))
        self.assertTrue(sim.encender(int(xs[i]), int(ys[i]), origen="usuario"))
        sim.avanzar(60 * 30)
        sim_io.volcar_eventos(con, sim)
        sim_io.guardar_simulacion(con, sim)
        pos = {i: (h.x, h.y, h.salud) for i, h in sim.habitantes.items()}
        t = int(sim.t)
        con.close()
        con = db.abrir(ruta)
        s2 = sim_io.cargar_simulacion(con)
        self.assertEqual(int(s2.t), t)
        for i, h in s2.habitantes.items():
            for a, b in zip((h.x, h.y, h.salud), pos[i]):
                self.assertAlmostEqual(a, b, delta=0.02)
        self.assertEqual(int(s2.fuego.fuego.sum()), int(sim.fuego.fuego.sum()))
        self.assertGreaterEqual(len(mundo_io.listar_eventos(con, tipo="incendio")), 1)
        con.close()

    def test_muerte_queda_registrada_en_la_base(self):
        ruta, con = self._mundo()
        sim_io.crear_habitantes_iniciales(con, 1)
        sim = sim_io.cargar_simulacion(con)
        sim.habitantes[1].salud = -1.0
        sim.avanzar(2)
        sim_io.guardar_simulacion(con, sim)
        r = con.execute("SELECT muerte_min, causa_muerte FROM habitantes WHERE id=1").fetchone()
        self.assertIsNotNone(r["muerte_min"])
        self.assertIsNotNone(r["causa_muerte"])
        con.close()


class TestHabitabilidadInicio(unittest.TestCase):
    """P2: el inicio sólo se acepta con una orilla de agua alcanzable por la navegación real (A*),
    no por cercanía geométrica. Mapas chicos y controlados (no mundos aleatorios)."""

    def _capas(self, agua, rasgos=None, bioma=None):
        h, w = agua.shape
        return {
            "elevacion": np.zeros((h, w), np.int16),       # plano: pendiente 0, todo caminable
            "temperatura": np.full((h, w), 15, np.int8),
            "humedad": np.full((h, w), 128, np.uint8),
            "bioma": (np.full((h, w), B.PRADERA, np.uint8) if bioma is None else bioma.astype(np.uint8)),
            "agua": agua.astype(np.uint8),
            "caudal": np.zeros((h, w), np.uint8),
            "rasgos": (np.zeros((h, w), np.uint8) if rasgos is None else rasgos.astype(np.uint8)),
        }

    def _terreno(self, capas, tam=50.0):
        from mundo_vivo.motor.navegacion import Terreno
        return Terreno(capas, tam)

    def test_1_orilla_alcanzable_se_acepta(self):
        agua = np.zeros((20, 20), np.uint8)
        agua[:, 0] = B.AGUA_RIO                       # río en la columna izquierda
        capas = self._capas(agua)
        t = self._terreno(capas)
        presupuesto = sim_io._presupuesto_camino(50.0)
        orilla = sim_io._orilla_alcanzable(t, 5, 5, presupuesto)
        self.assertIsNotNone(orilla)
        self.assertTrue(t.agua_adyacente(*orilla))
        self.assertTrue(t.caminable(*orilla))

    def test_1b_inicio_ya_en_orilla_es_habitable(self):
        agua = np.zeros((20, 20), np.uint8)
        agua[:, 0] = B.AGUA_RIO
        t = self._terreno(self._capas(agua))
        self.assertEqual(sim_io._orilla_alcanzable(t, 1, 5, 12000), (1, 5))

    def test_2_agua_infranqueable_se_rechaza(self):
        agua = np.zeros((20, 20), np.uint8)
        agua[:, 0] = B.AGUA_RIO                        # agua a la izquierda
        rasgos = np.zeros((20, 20), np.uint8)
        rasgos[:, 10] = B.RASGO_LAVA                   # muro de lava infranqueable en x=10
        t = self._terreno(self._capas(agua, rasgos))
        presupuesto = sim_io._presupuesto_camino(50.0)
        self.assertIsNone(sim_io._orilla_alcanzable(t, 15, 15, presupuesto))  # lado aislado
        self.assertIsNotNone(sim_io._orilla_alcanzable(t, 5, 15, presupuesto))  # lado con agua

    def test_3_entre_varios_candidatos_elige_habitable(self):
        agua = np.zeros((40, 40), np.uint8)
        agua[:, 0] = B.AGUA_RIO                        # río izq, campo abierto: habitable
        agua[18:22, 28:32] = B.AGUA_LAGO             # lago der, rodeado de lava: orilla inalcanzable
        rasgos = np.zeros((40, 40), np.uint8)
        rasgos[:, 19] = B.RASGO_LAVA                   # separa izquierda de derecha
        rasgos[17, 27:33] = B.RASGO_LAVA               # anillo de lava alrededor del lago
        rasgos[22, 27:33] = B.RASGO_LAVA
        rasgos[18:22, 27] = B.RASGO_LAVA
        rasgos[18:22, 32] = B.RASGO_LAVA
        capas = self._capas(agua, rasgos)
        with mock.patch.object(sim_io, "MIN_ZONA_CONECTADA", 10), \
                mock.patch.object(sim_io, "MAX_CANDIDATOS_INICIO", 10_000):
            x, y = sim_io.elegir_inicio(capas, 50.0)
        self.assertLess(x, 19)                         # eligió el lado con orilla alcanzable
        t = self._terreno(capas)
        self.assertIsNotNone(sim_io._orilla_alcanzable(t, x, y, sim_io._presupuesto_camino(50.0)))

    def test_4_sin_candidato_habitable_comportamiento_explicito(self):
        agua = np.zeros((30, 30), np.uint8)
        agua[13:17, 13:17] = B.AGUA_LAGO             # lago central (dulce, intransitable)
        rasgos = np.zeros((30, 30), np.uint8)
        rasgos[12:18, 12] = B.RASGO_LAVA             # anillo de lava alrededor del lago
        rasgos[12:18, 17] = B.RASGO_LAVA
        rasgos[12, 12:18] = B.RASGO_LAVA
        rasgos[17, 12:18] = B.RASGO_LAVA
        capas = self._capas(agua, rasgos)             # tierra caminable, pero sin orilla alcanzable
        with mock.patch.object(sim_io, "MIN_ZONA_CONECTADA", 10):
            with self.assertRaises(ValueError):
                sim_io.elegir_inicio(capas, 50.0)

    def test_5_determinismo_misma_entrada_mismo_resultado(self):
        agua = np.zeros((25, 25), np.uint8)
        agua[:, 0] = B.AGUA_RIO
        agua[10, 20] = B.AGUA_LAGO
        capas = self._capas(agua)
        with mock.patch.object(sim_io, "MIN_ZONA_CONECTADA", 10):
            a = sim_io.elegir_inicio(capas, 50.0)
            b = sim_io.elegir_inicio(capas, 50.0)
        self.assertEqual(a, b)

    def test_6_no_crea_en_ubicacion_rechazada(self):
        # Invariante: todo inicio devuelto pasa la validación de orilla alcanzable, así que no se
        # crea un habitante en una ubicación que falló la validación.
        agua = np.zeros((20, 20), np.uint8)
        agua[:, 0] = B.AGUA_RIO
        capas = self._capas(agua)
        t = self._terreno(capas)
        with mock.patch.object(sim_io, "MIN_ZONA_CONECTADA", 10):
            x, y = sim_io.elegir_inicio(capas, 50.0)
        self.assertIsNotNone(sim_io._orilla_alcanzable(t, x, y, sim_io._presupuesto_camino(50.0)))


if __name__ == "__main__":
    unittest.main()

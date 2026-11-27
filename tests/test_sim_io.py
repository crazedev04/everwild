import tempfile
import unittest
from pathlib import Path

from mundo_vivo.persistencia import db, mundo_io, sim_io
from mundo_vivo.motor.navegacion import Terreno
from mundo_vivo.motor import biomas as B


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

    def test_elegir_inicio_tiene_agua_alcanzable_por_astar(self):
        """P2 habitabilidad: el punto de inicio devuelto por elegir_inicio tiene agua dulce
        realmente alcanzable por A* (navegación real), no solo cerca geométricamente."""
        ruta, con = self._mundo()
        capas = mundo_io.cargar_capas(con, dimension=0)
        t = Terreno(capas, 50.0)
        x, y = sim_io.elegir_inicio(capas, tam_celda_m=50.0)
        presupuesto = sim_io._presupuesto_camino(50.0)
        orilla = sim_io._orilla_alcanzable(t, x, y, presupuesto)
        self.assertIsNotNone(orilla, "el inicio debe tener agua dulce alcanzable por A*")
        ox, oy = orilla
        # la orilla es tierra con agua dulce adyacente
        self.assertTrue(t.agua_adyacente(ox, oy), "la orilla debe tener agua dulce adyacente")
        con.close()

    def test_elegir_inicio_devuelve_punto_con_agua_dulce_adyacente(self):
        """El punto FINALMENTE devuelto (no sólo una orilla alcanzable) tiene agua dulce
        adyacente: los fundadores deben poder beber sin caminar. Regresión del spawn que
        dejaba a los habitantes a 2-3 celdas del agua, sin acceso, muriendo de sed."""
        import numpy as np
        for semilla in (42, 777, 4242, 1, 2, 3):
            ruta, con = self._mundo(semilla)
            capas = mundo_io.cargar_capas(con, dimension=0)
            t = Terreno(capas, 50.0)
            x, y = sim_io.elegir_inicio(capas, tam_celda_m=50.0)
            self.assertTrue(
                sim_io._agua_adyacente_dulce(t, x, y),
                f"semilla {semilla}: inicio ({x},{y}) sin agua dulce adyacente",
            )
            self.assertTrue(t.caminable(x, y), f"semilla {semilla}: inicio no caminable")
            con.close()

    def test_elegir_inicio_sin_agua_dulce_lanza_error(self):
        """Un mundo sin agua dulce no tiene dónde empezar: elegir_inicio lo dice explícito."""
        import numpy as np
        capas = self._capas_sinteticas(32, 32, agua=None)
        with self.assertRaises(ValueError):
            sim_io.elegir_inicio(capas, tam_celda_m=50.0)

    def test_elegir_inicio_sin_orilla_habitable_lanza_error(self):
        """Agua rodeada de pendiente extrema (nada caminable adyacente): no hay orilla
        habitable, así que elegir_inicio falla explícito en vez de devolver un punto seco."""
        import numpy as np
        # Un lago en el centro, pero todo el terreno con pendiente extrema (nada caminable
        # adyacente al agua): no hay orilla habitable. Rampa monótona y brusca en ambas
        # direcciones para que CADA celda de tierra supere PENDIENTE_MAX.
        capas = self._capas_sinteticas(32, 32, agua="lago")
        ys, xs = np.indices((32, 32))
        capas["elevacion"][:] = (ys + xs) * 1000.0
        with self.assertRaises(ValueError):
            sim_io.elegir_inicio(capas, tam_celda_m=50.0)

    def test_elegir_inicio_busca_orilla_lejos_del_centro(self):
        """La búsqueda no se limita al centro: si el agua dulce está en un extremo, el
        inicio sale allá (con agua adyacente), no se rinde devolviendo tierra seca central."""
        capas = self._capas_sinteticas(48, 48, agua="esquina")
        t = Terreno(capas, 50.0)
        x, y = sim_io.elegir_inicio(capas, tam_celda_m=50.0)
        self.assertTrue(sim_io._agua_adyacente_dulce(t, x, y))

    @staticmethod
    def _capas_sinteticas(ancho, alto, agua="rio"):
        """Capas planas mínimas para probar elegir_inicio sin generar un mundo real.

        `agua`: "rio" (un río vertical), "lago" (lago central), "esquina" (agua en una
        esquina), o None (mundo seco, sin agua dulce).
        """
        import numpy as np
        elev = np.zeros((alto, ancho), dtype=np.float64)
        ag = np.zeros((alto, ancho), dtype=np.uint8)
        if agua == "rio":
            ag[:, ancho // 2] = B.AGUA_RIO
        elif agua == "lago":
            ag[alto // 2 - 2 : alto // 2 + 2, ancho // 2 - 2 : ancho // 2 + 2] = B.AGUA_LAGO
        elif agua == "esquina":
            ag[2:6, 2:6] = B.AGUA_LAGO
        bioma = np.full((alto, ancho), B.PRADERA, dtype=np.uint8)
        return {
            "elevacion": elev,
            "agua": ag,
            "bioma": bioma,
            "humedad": np.zeros((alto, ancho), dtype=np.float64),
            "temperatura": np.full((alto, ancho), 15.0, dtype=np.float64),
            "caudal": np.zeros((alto, ancho), dtype=np.float64),
            "rasgos": np.zeros((alto, ancho), dtype=np.uint8),
        }

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


if __name__ == "__main__":
    unittest.main()

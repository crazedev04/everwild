import unittest

import numpy as np

from mundo_vivo.motor import biomas as B
from mundo_vivo.motor import reloj
from mundo_vivo.motor.fenomenos import camino_de_caida
from mundo_vivo.motor.fuego import Fuego
from mundo_vivo.generador.pipeline import generar_mundo
from mundo_vivo.motor.navegacion import Terreno
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion

_M = generar_mundo(42, 128, 128)


def _terreno(agua, bioma=None, tam=50.0):
    """Terreno chico y determinista para pruebas de navegación (todo pradera y llano por defecto)."""
    h, w = agua.shape
    if bioma is None:
        bioma = np.full((h, w), B.PRADERA, dtype=np.uint8)
    capas = {
        "elevacion": np.zeros((h, w), dtype=np.int16),
        "agua": np.asarray(agua, dtype=np.uint8),
        "bioma": np.asarray(bioma, dtype=np.uint8),
        "humedad": np.full((h, w), 128, dtype=np.uint8),
        "temperatura": np.full((h, w), 15, dtype=np.int8),
        "caudal": np.zeros((h, w), dtype=np.uint8),
        "rasgos": np.zeros((h, w), dtype=np.uint8),
    }
    return Terreno(capas, tam)


class TestReloj(unittest.TestCase):
    def test_fecha_y_estaciones(self):
        f = reloj.fecha(480)
        self.assertEqual((f["dia"], f["hora"], f["estacion"], f["anio"]), (1, 8, "primavera", 1))
        self.assertEqual(reloj.fecha(31 * 1440)["estacion"], "verano")
        self.assertEqual(reloj.fecha(121 * 1440)["anio"], 2)

    def test_luz_dia_y_noche(self):
        self.assertGreater(reloj.luz(13 * 60), 0.9)
        self.assertLess(reloj.luz(2 * 60), 0.15)
        self.assertTrue(reloj.es_noche(23 * 60))
        self.assertFalse(reloj.es_noche(12 * 60))


class TestNavegacion(unittest.TestCase):
    def setUp(self):
        self.t = Terreno(_M["capas"], 50)

    def test_agua_profunda_no_se_camina_y_camino_valido(self):
        oc = np.argwhere(self.t.agua == B.AGUA_OCEANO)
        self.assertFalse(self.t.caminable(int(oc[0][1]), int(oc[0][0])))
        ys, xs = np.nonzero(np.isfinite(self.t.costo))
        a = (int(xs[0]), int(ys[0]))
        for i in range(0, len(xs), max(1, len(xs) // 30)):
            b = (int(xs[i]), int(ys[i]))
            cam = self.t.buscar_camino(a, b)
            if cam:
                self.assertEqual(cam[-1], b)
                for (x1, y1), (x2, y2) in zip([a] + cam, cam):
                    self.assertLessEqual(max(abs(x1 - x2), abs(y1 - y2)), 1)
                    self.assertTrue(self.t.caminable(x2, y2))
                return
        self.fail("no se encontró ningún camino de prueba")

    def test_destino_inalcanzable_se_cachea_como_definitivo(self):
        """Si se agota la lista de abiertos sin llegar, se exploró toda la componente del origen:
        el destino es GENUINAMENTE inalcanzable y SÍ se cachea como definitivo (P0.2)."""
        agua = np.zeros((5, 5), dtype=np.uint8)
        agua[:, 2] = B.AGUA_OCEANO                       # muro intransitable en x=2
        t = _terreno(agua)
        origen, destino = (0, 0), (4, 0)                 # pradera a cada lado del muro
        self.assertTrue(t.caminable(*origen) and t.caminable(*destino))
        clave = t._clave_fracaso(origen, destino)
        self.assertIsNone(t.buscar_camino(origen, destino))
        self.assertIn(clave, t._fracasos, "inalcanzable real: va a la caché de fracasos")
        self.assertNotIn(clave, t._incompletos)
        # con presupuesto de sobra NO se rebusca: se devuelve el fracaso recordado (evita trabajo redundante)
        self.assertIsNone(t.buscar_camino(origen, destino, 10_000_000))
        # cambiar el mapa olvida los fracasos
        t.cambiar_bioma(destino[0], destino[1], B.BOSQUE_TEMPLADO)
        self.assertEqual(t._fracasos, set(), "cambiar el mapa tiene que olvidar los fracasos")

    def test_busqueda_incompleta_no_se_marca_como_imposible(self):
        """Agotar el presupuesto de nodos dejó la búsqueda INCOMPLETA, no probó imposibilidad:
        NO va a `_fracasos`, va a `_incompletos`, y puede reconsiderarse (P0.2)."""
        t = _terreno(np.zeros((2, 20), dtype=np.uint8))  # pasillo recto, todo transitable
        origen, destino = (0, 0), (19, 0)
        clave = t._clave_fracaso(origen, destino)
        self.assertIsNone(t.buscar_camino(origen, destino, 1))
        self.assertNotIn(clave, t._fracasos, "incompleta NO es inaccesibilidad definitiva")
        self.assertIn(clave, t._incompletos)
        # el descarte expira (olvidar_fracasos simula cambio de condiciones): se reconsidera y llega
        t.olvidar_fracasos()
        self.assertIsNotNone(t.buscar_camino(origen, destino))
        self.assertEqual(t._fracasos, set())

    def test_un_exito_nunca_se_guarda_como_fracaso(self):
        """Un camino que SÍ existe no se cachea como fracaso ni como incompleto."""
        t = _terreno(np.zeros((2, 20), dtype=np.uint8))
        origen, destino = (0, 0), (19, 0)
        self.assertTrue(t.buscar_camino(origen, destino))
        self.assertEqual(t._fracasos, set())
        self.assertEqual(t._incompletos, set())

    def test_cambiar_el_mapa_olvida_las_incompletas(self):
        """`cambiar_bioma` debe vaciar también la caché de incompletas, no sólo la de fracasos."""
        t = _terreno(np.zeros((2, 20), dtype=np.uint8))
        t.buscar_camino((0, 0), (19, 0), 1)
        self.assertTrue(t._incompletos)
        t.cambiar_bioma(5, 0, B.BOSQUE_TEMPLADO)
        self.assertEqual(t._incompletos, set())
        self.assertEqual(t._fracasos, set())


class TestFuego(unittest.TestCase):
    def _campo(self, bioma=B.PRADERA, n=60):
        return Fuego(np.full((n, n), bioma, dtype=np.uint8), np.zeros((n, n), dtype=np.uint8), 5)

    def test_se_propaga_y_deja_ceniza(self):
        f = self._campo()
        self.assertTrue(f.encender(30, 30))
        for _ in range(200):
            f.paso(1.0, 1.0, None)
        self.assertGreater(f.quemado.sum() + f.activas, 20)

    def test_lluvia_lo_apaga_mas_rapido(self):
        a, b = self._campo(), self._campo()
        a.encender(30, 30); b.encender(30, 30)
        lluvia = np.ones((60, 60), dtype=np.float32)
        for _ in range(120):
            a.paso(1.0, 1.0, None); b.paso(1.0, 1.0, lluvia)
        self.assertLess(b.quemado.sum() + b.activas, a.quemado.sum() + a.activas)

    def test_el_agua_frena_el_fuego(self):
        bio = np.full((40, 40), B.PRADERA, dtype=np.uint8)
        agua = np.zeros((40, 40), dtype=np.uint8)
        agua[:, 20:23] = B.AGUA_RIO
        f = Fuego(bio, agua, 3)
        f.encender(10, 20)
        for _ in range(600):
            f.paso(1.0, 1.0, None)
        self.assertEqual(int(f.quemado[:, 24:].sum() + f.fuego[:, 24:].sum()), 0)

    def test_no_se_enciende_sin_combustible(self):
        f = self._campo(B.PLAYA)
        self.assertFalse(f.encender(10, 10))

    def test_exportar_importar(self):
        f = self._campo(); f.encender(30, 30)
        for _ in range(20):
            f.paso(1.0, 1.0, None)
        g = self._campo()
        g.importar(**{"fuego": f.exportar()["fuego"], "quemado": f.exportar()["quemado"], "combustible": f.exportar()["combustible"]})
        self.assertEqual(int(g.fuego.sum()), int(f.fuego.sum()))


class TestIncendioAcotado(unittest.TestCase):
    def test_un_incendio_termina_solo_y_no_arrasa_el_mapa(self):
        """Regresión: un rayo llegó a quemar 15 días y un tercio del mundo."""
        for k in range(3):
            sim = Simulacion(_M["capas"], _M["meta"], t_min=480 + k * 20 * 1440)
            ys, xs = np.nonzero(sim.fuego.comb > 0.3)
            i = (k * 7919) % len(xs)
            if not sim.encender(int(xs[i]), int(ys[i])):
                continue
            t0 = sim.t
            while sim.fuego._hubo_fuego and sim.t - t0 < 6 * 1440:
                sim.avanzar(30)
            self.assertFalse(sim.fuego._hubo_fuego, "el incendio siguió más de 6 días")
            self.assertLess((sim.fuego.quemado > 0.05).mean(), 0.2)


class TestSimulacion(unittest.TestCase):
    def _sim(self):
        sim = Simulacion(_M["capas"], _M["meta"])
        t = sim.terreno
        ys, xs = np.nonzero(np.isfinite(t.costo) & (t.pendiente < 0.1))
        i = len(xs) // 2
        sim.habitantes[1] = HabitanteSim(1, "Test", xs[i] + 0.5, ys[i] + 0.5)
        return sim

    def test_necesidades_y_muerte_por_sed(self):
        sim = self._sim(); h = sim.habitantes[1]
        sim.cerebro.decidir = lambda s, hh: {"tipo": "esperar", "min": 600}
        h.sed = 95.0
        sim.avanzar(60 * 12)
        self.assertFalse(h.vivo)
        self.assertEqual(h.causa_muerte, "sed")

    def test_gravedad_la_roca_baja(self):
        t = Terreno(_M["capas"], 50)
        ys, xs = np.nonzero((t.pendiente >= 0.55) & (t.elev > 100))
        if len(xs) == 0:
            self.skipTest("sin pendientes")
        cam = camino_de_caida(t, int(xs[0]), int(ys[0]))
        elevs = [t.elev[y, x] for x, y in cam]
        self.assertTrue(all(b <= a for a, b in zip(elevs, elevs[1:])))

    def test_determinismo(self):
        def correr():
            s = self._sim(); s.avanzar(60 * 24 * 3)
            h = s.habitantes[1]
            return round(h.x, 3), round(h.y, 3), round(h.salud, 2), int(s.t)
        self.assertEqual(correr(), correr())


if __name__ == "__main__":
    unittest.main()

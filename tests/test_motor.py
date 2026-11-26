import unittest

import numpy as np

from mundo_vivo.motor import biomas as B
from mundo_vivo.motor import reloj
from mundo_vivo.motor.fenomenos import camino_de_caida
from mundo_vivo.motor.fuego import Fuego
from mundo_vivo.motor.generador import generar_mundo
from mundo_vivo.motor.navegacion import Terreno
from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion

_M = generar_mundo(42, 128, 128)


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

    def test_un_viaje_imposible_no_se_reintenta_y_se_olvida_si_cambia_el_mapa(self):
        """Una búsqueda fallida agota el presupuesto de nodos: es lo más caro que hace el motor.

        Medido en un mundo de 2048² con celdas de 5 m: de 36 búsquedas en 3 días simulados, 24
        fallaron y se llevaron 16,7 de los 19,1 segundos pasados dentro del A*, y eran el MISMO
        destino reintentado 12 veces. Así que el fracaso se recuerda, con dos condiciones: que no se
        recuerde un ÉXITO (un camino caduca en cuanto alguien construye algo) y que se olvide todo
        si el mapa cambia, porque ahí lo imposible puede volverse posible.
        """
        ys, xs = np.nonzero(np.isfinite(self.t.costo))
        origen = (int(xs[0]), int(ys[0]))
        # un destino caminable al que no se llega: se lo encierra bajando el presupuesto a 1 nodo
        destino = (int(xs[len(xs) // 2]), int(ys[len(xs) // 2]))
        self.assertIsNone(self.t.buscar_camino(origen, destino, 1))
        # Presupuesto agotado: búsqueda incompleta, no fracaso definitivo. Va a _incompletos.
        self.assertEqual(len(self.t._incompletos), 1, "agotar presupuesto anota incompleto")

        # ahora con presupuesto de sobra: SÍ se busca de nuevo, porque el presupuesto creció
        resultado = self.t.buscar_camino(origen, destino, 10_000_000)
        self.assertIsNotNone(resultado, "presupuesto mayor debe permitir nueva búsqueda")

        # si el mapa cambia, se olvida y se vuelve a buscar de verdad
        self.t.cambiar_bioma(destino[0], destino[1], int(self.t.bioma[destino[1], destino[0]]) ^ 1)
        self.assertEqual(self.t._fracasos, set(), "cambiar el mapa tiene que olvidar los fracasos")
        self.assertEqual(self.t._incompletos, {}, "cambiar el mapa tiene que olvidar los incompletos")

        # un camino que SÍ existe nunca se guarda: no hay nada que caduque
        alcanzable = next(((int(x), int(y)) for x, y in zip(xs, ys)
                           if self.t.buscar_camino(origen, (int(x), int(y)))), None)
        self.assertIsNotNone(alcanzable, "el mapa de prueba no tiene ningún destino alcanzable")
        self.t.olvidar_fracasos()
        self.assertTrue(self.t.buscar_camino(origen, alcanzable))
        self.assertEqual(self.t._fracasos, set(), "un éxito no se guarda en la caché")

    def test_destino_inalcanzable_se_anota_como_fracaso_definitivo(self):
        """Destino caminable pero en componente aislada: el A* agota la lista de abiertos
        sin llegar, así que se anota como fracaso definitivo en _fracasos."""
        ys, xs = np.nonzero(np.isfinite(self.t.costo))
        origen = (int(xs[0]), int(ys[0]))

        # aísla una celda caminable rodeándola de océano (INF): queda en su propio componente
        dx, dy = int(xs[len(xs) // 2]), int(ys[len(ys) // 2])
        assert self.t.caminable(dx, dy), "celda de destino debe ser caminable al inicio"
        for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = dx + ax, dy + ay
            if self.t.dentro(nx, ny):
                self.t._establecer_costo_celda(nx, ny, float("inf"))

        self.assertIsNone(self.t.buscar_camino(origen, (dx, dy), 10_000_000))
        self.assertEqual(len(self.t._fracasos), 1, "destino inalcanzable es fracaso definitivo")

    def test_incompleto_bajo_presupuesto_permite_reintento_con_presupuesto_mayor(self):
        """Una búsqueda que agota presupuesto pequeño no bloquea una posterior con presupuesto mayor."""
        ys, xs = np.nonzero(np.isfinite(self.t.costo))
        origen = (int(xs[0]), int(ys[0]))
        destino = (int(xs[len(xs) // 2]), int(ys[len(xs) // 2]))

        self.assertIsNone(self.t.buscar_camino(origen, destino, 1))
        self.assertEqual(len(self.t._incompletos), 1)

        resultado = self.t.buscar_camino(origen, destino, 10_000_000)
        self.assertIsNotNone(resultado)

    def test_incompleto_bloquea_presupuesto_igual_o_menor(self):
        """Una búsqueda incompleta bloquea otro intento con presupuesto igual o menor."""
        ys, xs = np.nonzero(np.isfinite(self.t.costo))
        origen = (int(xs[0]), int(ys[0]))
        destino = (int(xs[len(xs) // 2]), int(ys[len(xs) // 2]))

        self.t._incompletos[(int(origen[0]) // 4, int(origen[1]) // 4, destino[0], destino[1])] = 100

        self.assertIsNone(self.t.buscar_camino(origen, destino, 100))
        self.assertIsNone(self.t.buscar_camino(origen, destino, 50))

    def test_fracaso_definitivo_bloquea_independientemente_de_presupuesto(self):
        """Un fracaso en _fracasos bloquea cualquier búsqueda posterior, sin importar max_exp."""
        ys, xs = np.nonzero(np.isfinite(self.t.costo))
        origen = (int(xs[0]), int(ys[0]))
        destino = (int(xs[len(xs) // 2]), int(ys[len(xs) // 2]))

        dx, dy = destino
        assert self.t.caminable(dx, dy), "celda de destino debe ser caminable al inicio"
        for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = dx + ax, dy + ay
            if self.t.dentro(nx, ny):
                self.t._establecer_costo_celda(nx, ny, float("inf"))

        self.assertIsNone(self.t.buscar_camino(origen, destino, 10_000_000))
        self.assertEqual(len(self.t._fracasos), 1)
        self.assertIsNone(self.t.buscar_camino(origen, destino, 10_000_000))

    def test_cambiar_bioma_invalida_fracasos_e_incompletos(self):
        """Cambiar el terreno vacía tanto _fracasos como _incompletos."""
        ys, xs = np.nonzero(np.isfinite(self.t.costo))
        origen = (int(xs[0]), int(ys[0]))
        destino = (int(xs[len(xs) // 2]), int(ys[len(xs) // 2]))

        self.assertIsNone(self.t.buscar_camino(origen, destino, 1))
        self.assertEqual(len(self.t._incompletos), 1)

        self.t.cambiar_bioma(destino[0], destino[1], int(self.t.bioma[destino[1], destino[0]]) ^ 1)
        self.assertEqual(self.t._fracasos, set())
        self.assertEqual(self.t._incompletos, {})

    def test_fracaso_elimina_entrada_de_incompletos(self):
        """Un fracaso definitivo elimina la entrada previa de _incompletos para esa clave."""
        ys, xs = np.nonzero(np.isfinite(self.t.costo))
        origen = (int(xs[0]), int(ys[0]))
        destino = (int(xs[len(xs) // 2]), int(ys[len(xs) // 2]))

        dx, dy = destino
        assert self.t.caminable(dx, dy), "celda de destino debe ser caminable al inicio"
        for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = dx + ax, dy + ay
            if self.t.dentro(nx, ny):
                self.t._establecer_costo_celda(nx, ny, float("inf"))

        clave = (int(origen[0]) // 4, int(origen[1]) // 4, dx, dy)

        # presupuesto pequeño: queda incompleto
        self.assertIsNone(self.t.buscar_camino(origen, destino, 1))
        self.assertIn(clave, self.t._incompletos)

        # presupuesto mayor: demuestra que no hay camino, se promueve a fracaso
        self.assertIsNone(self.t.buscar_camino(origen, destino, 10_000_000))
        self.assertIn(clave, self.t._fracasos)
        self.assertNotIn(clave, self.t._incompletos)


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

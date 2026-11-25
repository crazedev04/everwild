import json
import math
import unittest

from mundo_vivo.agentes import genoma as G


class TestGenoma(unittest.TestCase):
    def test_fundador_determinista_y_valido(self):
        a, b = G.genoma_fundador(1), G.genoma_fundador(1)
        self.assertEqual(a.a_dict(), b.a_dict())
        self.assertNotEqual(a.a_dict(), G.genoma_fundador(2).a_dict())
        self.assertEqual(len(a.pesos), G.N_PESOS)
        self.assertTrue(all(0 <= v <= 1 for v in a.rasgos.values()))
        self.assertEqual(a.generacion, 0)

    def test_serializacion_ida_y_vuelta(self):
        g = G.genoma_fundador(7)
        g2 = G.Genoma.de_dict(json.loads(json.dumps(g.a_dict())))
        self.assertEqual(g.a_dict(), g2.a_dict())

    def test_rechaza_genomas_corruptos(self):
        d = G.genoma_fundador(3).a_dict()
        malo = dict(d, pesos=d["pesos"][:-1])
        with self.assertRaises(ValueError):
            G.Genoma.de_dict(malo)
        malo = dict(d, rasgos=dict(d["rasgos"], audacia=1.5))
        with self.assertRaises(ValueError):
            G.Genoma.de_dict(malo)
        malo = dict(d, pesos=[float("nan")] + d["pesos"][1:])
        with self.assertRaises(ValueError):
            G.Genoma.de_dict(malo)

    def test_herencia_sin_mutacion_toma_de_los_padres(self):
        a, b = G.genoma_fundador(10), G.genoma_fundador(11)
        h = G.heredar(a, b, semilla=5, tasa_mutacion=0.0)
        for k in G.RASGOS:
            lo, hi = sorted((a.rasgos[k], b.rasgos[k]))
            self.assertTrue(lo - 1e-6 <= h.rasgos[k] <= hi + 1e-6, k)
        for pa, pb, ph in zip(a.pesos, b.pesos, h.pesos):
            self.assertIn(round(ph, 6), (round(pa, 6), round(pb, 6)))
        self.assertEqual(h.generacion, 1)

    def test_herencia_determinista_y_distinta_por_semilla(self):
        a, b = G.genoma_fundador(10), G.genoma_fundador(11)
        self.assertEqual(G.heredar(a, b, 1).a_dict(), G.heredar(a, b, 1).a_dict())
        self.assertNotEqual(G.heredar(a, b, 1).a_dict(), G.heredar(a, b, 2).a_dict())

    def test_mutacion_cambia_algo_y_respeta_limites(self):
        a, b = G.genoma_fundador(20), G.genoma_fundador(21)
        h = G.heredar(a, b, semilla=9, tasa_mutacion=1.0, magnitud_rasgos=5.0)  # mutación enorme
        self.assertTrue(all(0.0 <= v <= 1.0 for v in h.rasgos.values()))
        self.assertTrue(all(math.isfinite(p) for p in h.pesos))
        sin = G.heredar(a, b, semilla=9, tasa_mutacion=0.0)
        self.assertNotEqual(h.pesos, sin.pesos)

    def test_generaciones_suben_y_el_hijo_se_parece_a_los_padres(self):
        a, b = G.genoma_fundador(30), G.genoma_fundador(31)
        hijo = G.heredar(a, b, 1)
        nieto = G.heredar(hijo, G.genoma_fundador(32), 2)
        self.assertEqual((hijo.generacion, nieto.generacion), (1, 2))
        extrano = G.genoma_fundador(99)
        self.assertLess(G.distancia(hijo, a), G.distancia(extrano, a) + 0.25)
        self.assertEqual(G.distancia(a, a), 0.0)

    def test_impulsos_en_rango_y_deterministas(self):
        g = G.genoma_fundador(40)
        e = {"hambre": 0.9, "sed": 0.2, "dolor": 0.5, "amenaza_cercana": 1.0}
        r1, r2 = G.impulsos(g, e), G.impulsos(g, e)
        self.assertEqual(r1, r2)
        self.assertEqual(set(r1), set(G.SALIDAS))
        self.assertTrue(all(0.0 < v < 1.0 for v in r1.values()))
        self.assertTrue(all(0.0 < v < 1.0 for v in G.impulsos(g, {}).values()))

    def test_genomas_distintos_reaccionan_distinto(self):
        e = {"amenaza_cercana": 1.0, "hambre": 0.5}
        resultados = {tuple(round(v, 3) for v in G.impulsos(G.genoma_fundador(s), e).values()) for s in range(10)}
        self.assertGreater(len(resultados), 5)  # hay variedad entre individuos

    def test_describir_temperamento(self):
        g = G.genoma_fundador(50)
        g.rasgos.update({k: 0.5 for k in G.RASGOS})
        self.assertEqual(G.describir_temperamento(g), "de caracter equilibrado")
        g.rasgos["audacia"] = 0.95
        self.assertIn("audaz", G.describir_temperamento(g))


if __name__ == "__main__":
    unittest.main()

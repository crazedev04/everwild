import hashlib
import unittest

import numpy as np

from mundo_vivo.motor import biomas as B
from mundo_vivo.motor.generador import generar_mundo
from mundo_vivo.persistencia.mundo_io import hash_capas


class TestGenerador(unittest.TestCase):
    def test_misma_semilla_mismo_mundo(self):
        a = generar_mundo(42, 128, 128)
        b = generar_mundo(42, 128, 128)
        self.assertEqual(hash_capas(a["capas"]), hash_capas(b["capas"]))
        self.assertEqual(a["meta"], b["meta"])

    def test_semillas_distintas_mundos_distintos(self):
        self.assertNotEqual(hash_capas(generar_mundo(1, 128, 128)["capas"]),
                            hash_capas(generar_mundo(2, 128, 128)["capas"]))

    def test_mapa_conocido_no_cambia(self):
        # Guardia de regresión: si el algoritmo cambia, este mapa cambia y hay que subir VERSION_GENERADOR.
        # Se compara una muestra (no el hash exacto) para tolerar mínimas diferencias de coma flotante entre equipos.
        c = generar_mundo(42, 128, 128)["capas"]
        muestra = c["bioma"][::8, ::8].ravel().tolist()
        iguales = sum(1 for a, b in zip(muestra, REF_42_128) if a == b) / len(REF_42_128)
        self.assertGreaterEqual(iguales, 0.95,
            "El mapa de la semilla 42 cambió (%.0f%% igual). Si fue a propósito: subí VERSION_GENERADOR y actualizá REF_42_128." % (100 * iguales))

    def test_invariantes(self):
        for semilla in (1, 42, 777, 2024, 31337):
            m = generar_mundo(semilla, 192, 192)
            c = m["capas"]
            tierra = c["elevacion"] >= 0
            frac = tierra.mean()
            self.assertTrue(0.30 < frac < 0.60, "fracción de tierra %.2f (semilla %d)" % (frac, semilla))
            # los bordes del mapa son océano: es un continente
            for borde in (c["agua"][0, :], c["agua"][-1, :], c["agua"][:, 0], c["agua"][:, -1]):
                self.assertTrue((borde == B.AGUA_OCEANO).all())
            # hay ríos y varios biomas
            self.assertGreater((c["agua"] == B.AGUA_RIO).sum(), 50)
            self.assertGreaterEqual(len(np.unique(c["bioma"][tierra])), 7)
            # ríos solo en tierra, nunca en el océano
            self.assertFalse(((c["agua"] == B.AGUA_RIO) & ~tierra).any())
            # la lava solo aparece en volcanes
            self.assertEqual(int((c["rasgos"] & B.RASGO_LAVA > 0).sum() > 0), int(len(m["meta"]["volcanes"]) > 0))
            # ids de bioma válidos
            self.assertTrue(set(np.unique(c["bioma"]).tolist()) <= set(B.BIOMAS))

    def test_rios_llegan_al_mar_o_a_un_lago(self):
        m = generar_mundo(42, 192, 192)
        c = m["capas"]
        rio = c["agua"] == B.AGUA_RIO
        agua = c["agua"] > 0
        h, w = rio.shape
        # cada componente de río debe tocar el océano o un lago
        visto = np.zeros_like(rio)
        for y0, x0 in zip(*np.nonzero(rio)):
            if visto[y0, x0]:
                continue
            comp, k, toca = [(y0, x0)], 0, False
            visto[y0, x0] = True
            while k < len(comp):
                y, x = comp[k]; k += 1
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < h and 0 <= xx < w:
                            if agua[yy, xx] and not rio[yy, xx]:
                                toca = True
                            if rio[yy, xx] and not visto[yy, xx]:
                                visto[yy, xx] = True
                                comp.append((yy, xx))
            self.assertTrue(toca, "río aislado en (%d,%d)" % (x0, y0))


# huella exacta en la plataforma de desarrollo: 1297c3c0a2c92d93a96eaa0d94588fe628e4fd051ae1e4beb16368532591bbf7
REF_42_128 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 9, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 6, 9, 6, 9, 6, 6, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 6, 6, 6, 10, 6, 5, 5, 1, 1, 0, 0, 0, 1, 1, 6, 6, 6, 12, 12, 14, 12, 5, 5, 4, 6, 1, 0, 0, 1, 6, 6, 6, 12, 12, 5, 6, 12, 5, 5, 4, 4, 0, 0, 1, 1, 7, 6, 6, 5, 4, 4, 3, 4, 4, 3, 4, 1, 0, 0, 1, 1, 1, 7, 14, 5, 4, 14, 4, 4, 4, 5, 3, 1, 0, 0, 1, 1, 1, 6, 14, 12, 13, 12, 3, 4, 4, 3, 3, 4, 0, 0, 0, 1, 6, 6, 5, 5, 3, 5, 3, 3, 3, 6, 3, 4, 1, 0, 0, 1, 6, 6, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 1, 0, 0, 1, 6, 9, 14, 9, 5, 14, 10, 10, 5, 5, 5, 5, 1, 0, 0, 1, 1, 9, 9, 9, 10, 5, 5, 5, 6, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

if __name__ == "__main__":
    unittest.main()

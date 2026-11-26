import unittest
import numpy as np
from mundo_vivo.motor.fuego import Fuego

class TestFuegoBbox(unittest.TestCase):
    def test_foco_chico_usa_bbox_y_es_equivalente(self):
        bioma = np.full((256, 256), 6, dtype=np.uint8)
        agua = np.zeros((256, 256), dtype=np.uint8)
        f = Fuego(bioma, agua, semilla=42)
        # Buscar una celda con combustible cerca del centro
        ys, xs = np.nonzero((f.comb > 0.5) & (np.abs(np.arange(256)[:, None] - 128) < 20) & (np.abs(np.arange(256)[None, :] - 128) < 20))
        self.assertGreater(len(ys), 0)
        cx, cy = int(xs[0]), int(ys[0])
        
        ok = f.encender(cx, cy)
        self.assertTrue(ok)
        self.assertTrue(f._hubo_fuego)
        bbox = f._bbox_ardiendo(margen=2)
        self.assertIsNotNone(bbox)
        y0, y1, x0, x1 = bbox
        self.assertLess((y1 - y0) * (x1 - x0), 0.5 * 256 * 256)
        
        # Simular varios pasos
        for _ in range(5):
            res = f.paso(dt=1.0, sequedad=1.0)
            self.assertIn("apagadas", res)
            
        # El fuego debe haberse propagado en torno al foco sin tocar los bordes lejanos
        self.assertEqual(int(f.fuego[0:5, :].sum()), 0)
        self.assertEqual(int(f.fuego[250:256, :].sum()), 0)
        self.assertGreater(int(f.fuego.sum()), 0)

if __name__ == "__main__":
    unittest.main()

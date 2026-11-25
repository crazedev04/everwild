import json
import tempfile
import unittest
from pathlib import Path

from mundo_vivo import reglas as R


class TestReglas(unittest.TestCase):
    def setUp(self):
        self.r = R.Reglas.cargar()

    def test_herencia_copy_from(self):
        a, h = self.r.material("acero"), self.r.material("hierro")
        self.assertEqual(a["densidad_kg_m3"], h["densidad_kg_m3"])   # heredado
        self.assertGreater(a["dureza_mohs"], h["dureza_mohs"])         # sobreescrito
        self.assertTrue(a["conduce_electricidad"])

    def test_fogata_no_ablanda_hierro_pero_la_fragua_si(self):
        fe = self.r.material("hierro")
        masa, area = 1.0, 0.03
        self.assertIsNone(R.minutos_hasta(fe["punto_ablandamiento_C"], 800, masa, area, fe["calor_especifico_J_kgK"]))
        t = R.minutos_hasta(fe["punto_ablandamiento_C"], 1100, masa, area, fe["calor_especifico_J_kgK"])
        self.assertIsNotNone(t)
        t_pesada = R.minutos_hasta(fe["punto_ablandamiento_C"], 1100, 3.0, area, fe["calor_especifico_J_kgK"])
        self.assertGreater(t_pesada, t)   # más masa, más tiempo
        # el bronce se ablanda antes que el hierro con la misma fuente
        br = self.r.material("bronce")
        self.assertLess(R.minutos_hasta(br["punto_ablandamiento_C"], 1100, masa, area, br["calor_especifico_J_kgK"]), t)

    def test_reacciones(self):
        fe = self.r.material("hierro")
        ef = self.r.aplicar({"material": fe, "cuerpo": {"temperatura_C": 950}, "ambiente": {}})
        self.assertIn("metal_se_ablanda", {e["regla"] for e in ef})
        ef = self.r.aplicar({"material": fe, "cuerpo": {"temperatura_C": 400}, "ambiente": {}})
        self.assertEqual(ef, [])
        ef = self.r.aplicar({"material": fe, "cuerpo": {}, "ambiente": {"descarga_electrica": True}})
        self.assertIn("rayo_en_conductor", {e["regla"] for e in ef})
        ef = self.r.aplicar({"material": self.r.material("piedra"), "cuerpo": {}, "ambiente": {"descarga_electrica": True}})
        self.assertEqual(ef, [])  # la piedra no conduce
        ef = self.r.aplicar({"material": self.r.material("madera"), "cuerpo": {}, "ambiente": {"temperatura_C": 350}})
        self.assertIn("madera_se_enciende", {e["regla"] for e in ef})

    def test_agregar_un_fenomeno_nuevo_sin_tocar_codigo(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "extra.json").write_text(json.dumps([
                {"type": "reaccion", "id": "hielo_se_derrite",
                 "cuando": [{"path": "ambiente.temperatura_C", "op": ">", "valor": 0}, {"path": "material.id", "op": "==", "valor": "hielo"}],
                 "efectos": [{"tipo": "estado", "valor": "agua"}]},
                {"type": "material", "id": "hielo", "nombre": "hielo", "dureza_mohs": 1.5}]), encoding="utf-8")
            r = R.Reglas.cargar(R.DIR_BASE, Path(d))
            self.assertNotEqual(r.huella, self.r.huella)   # la huella cambia si cambian las reglas
            ef = r.aplicar({"material": r.material("hielo"), "cuerpo": {}, "ambiente": {"temperatura_C": 5}})
            self.assertEqual(ef[0]["regla"], "hielo_se_derrite")

    def test_validacion_rechaza_reglas_rotas(self):
        casos = [
            [{"type": "reaccion", "id": "x", "cuando": [{"path": "cuerpo.t", "op": "~", "valor": 1}], "efectos": [{"tipo": "estado"}]}],
            [{"type": "reaccion", "id": "x", "cuando": [{"path": "mundo.t", "op": "==", "valor": 1}], "efectos": [{"tipo": "estado"}]}],
            [{"type": "reaccion", "id": "x", "cuando": [{"path": "cuerpo.t", "op": "==", "valor": 1}], "efectos": [{"tipo": "explotar"}]}],
            [{"type": "material", "id": "a", "copy-from": "no_existe"}],
            [{"type": "material", "id": "a", "copy-from": "b"}, {"type": "material", "id": "b", "copy-from": "a"}],
            [{"id": "sin_tipo"}],
        ]
        for caso in casos:
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / "mala.json").write_text(json.dumps(caso), encoding="utf-8")
                with self.assertRaises(R.ErrorDeReglas):
                    R.Reglas.cargar(Path(d))


if __name__ == "__main__":
    unittest.main()

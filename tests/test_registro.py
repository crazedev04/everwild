"""Fase A: el registro único de contenido y el evaluador de condiciones."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from mundo_vivo import condiciones as C
from mundo_vivo.registro import ErrorDeRegistro, Registro, clave


def _pack(dir_: Path, nombre: str, entradas: list) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / nombre).write_text(json.dumps(entradas, ensure_ascii=False), encoding="utf-8")


class TestRegistro(unittest.TestCase):
    def _tmp(self) -> Path:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return Path(d.name)

    def test_carga_el_contenido_del_juego(self):
        r = Registro.cargar()
        self.assertGreater(len(r.de_tipo("receta")), 100)
        self.assertGreater(len(r.de_tipo("material")), 30)
        self.assertGreater(len(r.de_tipo("especie")), 30)
        self.assertTrue(r.huella)

    def test_el_tipo_lo_decide_el_campo_no_la_carpeta(self):
        """Así los archivos que ya existen siguen funcionando donde están."""
        d = self._tmp()
        _pack(d / "cualquier_carpeta", "x.json", [{"type": "material", "id": "vidrio", "dureza_mohs": 6}])
        r = Registro.cargar(d)
        self.assertIn("vidrio", r.de_tipo("material"))

    def test_un_paquete_externo_agrega_y_reemplaza(self):
        base, extra = self._tmp(), self._tmp()
        _pack(base / "materiales", "a.json", [{"type": "material", "id": "piedra", "dureza_mohs": 6}])
        _pack(extra / "materiales", "b.json", [{"type": "material", "id": "piedra", "dureza_mohs": 9},
                                               {"type": "material", "id": "cemento", "estructural": True}])
        r = Registro.cargar(base, extra)
        self.assertEqual(r.uno("material", "piedra")["dureza_mohs"], 9, "el paquete externo tiene que pisar")
        self.assertIn("cemento", r.de_tipo("material"), "y tiene que poder agregar cosas nuevas")

    def test_herencia_encadenada(self):
        d = self._tmp()
        _pack(d / "m", "a.json", [
            {"type": "material", "id": "_base", "abstracto": True, "densidad_kg_m3": 100, "rigido": True},
            {"type": "material", "id": "medio", "copy-from": "_base", "dureza_mohs": 3},
            {"type": "material", "id": "hoja", "copy-from": "medio", "dureza_mohs": 7}])
        r = Registro.cargar(d)
        hoja = r.uno("material", "hoja")
        self.assertEqual(hoja["densidad_kg_m3"], 100, "tiene que heredar del abuelo")
        self.assertTrue(hoja["rigido"])
        self.assertEqual(hoja["dureza_mohs"], 7, "y lo propio pisa a lo heredado")

    def test_las_plantillas_no_existen_en_el_mundo(self):
        d = self._tmp()
        _pack(d / "m", "a.json", [{"type": "material", "id": "_plantilla", "abstracto": True, "rigido": True},
                                  {"type": "material", "id": "real", "copy-from": "_plantilla"}])
        r = Registro.cargar(d)
        self.assertNotIn("_plantilla", r.de_tipo("material"))
        self.assertTrue(r.uno("material", "real")["rigido"])
        self.assertNotIn("abstracto", r.uno("material", "real"), "ser plantilla no se hereda")

    def test_la_herencia_circular_se_detecta_y_dice_donde(self):
        d = self._tmp()
        _pack(d / "m", "a.json", [{"type": "material", "id": "a", "copy-from": "b"},
                                  {"type": "material", "id": "b", "copy-from": "a"}])
        with self.assertRaises(ErrorDeRegistro) as e:
            Registro.cargar(d)
        self.assertIn("circular", str(e.exception).lower())

    def test_heredar_de_algo_que_no_existe_falla_al_cargar(self):
        d = self._tmp()
        _pack(d / "m", "a.json", [{"type": "material", "id": "x", "copy-from": "fantasma"}])
        with self.assertRaises(ErrorDeRegistro) as e:
            Registro.cargar(d)
        self.assertIn("a.json", str(e.exception), "el error tiene que nombrar el archivo")

    def test_espacio_de_nombres(self):
        self.assertEqual(clave("mundo:piedra"), "piedra")
        self.assertEqual(clave("piedra"), "piedra")
        self.assertEqual(clave("otro:piedra"), "otro:piedra", "lo de terceros conserva su prefijo")
        r = Registro.cargar()
        self.assertIsNotNone(r.uno("material", "mundo:piedra"))

    def test_etiquetas(self):
        r = Registro.cargar()
        self.assertEqual(r.etiqueta("#lena"), r.etiqueta("lena"))
        self.assertIn("palo", r.etiqueta("#lena"))
        self.assertEqual(r.ids(["piedra", "#lena"]), {"piedra"} | r.etiqueta("lena"))

    def test_la_huella_cambia_al_agregar_contenido(self):
        base, extra = self._tmp(), self._tmp()
        _pack(base / "m", "a.json", [{"type": "material", "id": "x"}])
        h1 = Registro.cargar(base).huella
        _pack(extra / "m", "b.json", [{"type": "material", "id": "y"}])
        self.assertNotEqual(h1, Registro.cargar(base, extra).huella)


class TestCondiciones(unittest.TestCase):
    RAICES = ("material", "cuerpo", "ambiente")

    def test_comparaciones_y_referencias(self):
        ctx = {"material": {"dureza_mohs": 6, "punto_ignicion_C": 300}, "cuerpo": {"temperatura_C": 350}}
        self.assertTrue(C.evaluar({"path": "material.dureza_mohs", "op": ">=", "valor": 5}, ctx))
        self.assertFalse(C.evaluar({"path": "material.dureza_mohs", "op": "<", "valor": 5}, ctx))
        self.assertTrue(C.evaluar({"path": "cuerpo.temperatura_C", "op": ">=",
                                   "valor": "@material.punto_ignicion_C"}, ctx), "referencia con @")
        self.assertTrue(C.evaluar({"path": "material.dureza_mohs", "op": "existe"}, ctx))
        self.assertTrue(C.evaluar({"path": "material.nada", "op": "no_existe"}, ctx))

    def test_operadores_nuevos(self):
        ctx = {"material": {"id": "palo", "biomas": ["bosque", "pradera"], "temp": 15}}
        self.assertTrue(C.evaluar({"path": "material.id", "op": "en", "valor": ["palo", "paja"]}, ctx))
        self.assertTrue(C.evaluar({"path": "material.biomas", "op": "contiene", "valor": "pradera"}, ctx))
        self.assertTrue(C.evaluar({"path": "material.temp", "op": "entre", "valor": [9, 20]}, ctx))
        self.assertFalse(C.evaluar({"path": "material.temp", "op": "entre", "valor": [20, 30]}, ctx))

    def test_combinadores_y_lista_suelta(self):
        ctx = {"material": {"a": 1, "b": 2}}
        c1 = {"path": "material.a", "op": "==", "valor": 1}
        c2 = {"path": "material.b", "op": "==", "valor": 99}
        self.assertTrue(C.evaluar([c1], ctx), "una lista suelta es un «todas»")
        self.assertFalse(C.evaluar([c1, c2], ctx))
        self.assertTrue(C.evaluar({"cualquiera": [c1, c2]}, ctx))
        self.assertTrue(C.evaluar({"no": c2}, ctx))

    def test_cuantificadores_sobre_una_lista_de_materiales(self):
        """Es lo que reemplaza a las lambdas de conocimiento.py: «alguno es duro», «todos flotan»."""
        mats = [{"densidad_kg_m3": 600, "dureza_mohs": 2}, {"densidad_kg_m3": 2700, "dureza_mohs": 7}]
        listas = {"material": mats}
        duro = {"alguno": [{"path": "material.dureza_mohs", "op": ">=", "valor": 5}]}
        flota = {"todos": [{"path": "material.densidad_kg_m3", "op": "<", "valor": 1000}]}
        self.assertTrue(C.evaluar(duro, {}, listas), "alguno es duro")
        self.assertFalse(C.evaluar(flota, {}, listas), "la piedra no flota")

    def test_un_json_mal_escrito_falla_al_cargar_y_no_en_mitad_del_mundo(self):
        with self.assertRaises(C.ErrorDeCondicion):
            C.validar({"path": "material.x", "op": "mayor_que", "valor": 1}, self.RAICES, "prueba")
        with self.assertRaises(C.ErrorDeCondicion):
            C.validar({"path": "inventado.x", "op": "==", "valor": 1}, self.RAICES, "prueba")
        with self.assertRaises(C.ErrorDeCondicion):
            C.validar({"op": "==", "valor": 1}, self.RAICES, "prueba")
        with self.assertRaises(C.ErrorDeCondicion):
            C.validar({"path": "material.x", "op": "entre", "valor": 5}, self.RAICES, "prueba")
        C.validar({"todas": [{"path": "material.x", "op": ">", "valor": 1}]}, self.RAICES, "ok")

    def test_comparar_texto_con_numero_no_revienta(self):
        ctx = {"material": {"x": "hola"}}
        self.assertFalse(C.evaluar({"path": "material.x", "op": ">", "valor": 5}, ctx))


if __name__ == "__main__":
    unittest.main()

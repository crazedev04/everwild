"""E1 — Aislamiento cognitivo entre mundos: identidad, base por mundo, lectura/escritura y recuperación.

Flujo real: `mundo_io.crear_mundo` + `CerebroCognitivo(con)` (adaptador + servicio + repositorio).
No son pruebas del generador de IDs: ejercitan adaptador/servicio/repositorio reales.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from mundo_vivo.agentes.cerebro_cognitivo import CerebroCognitivo, motor_cognitivo_disponible
from mundo_vivo.persistencia import db, mundo_io

_HAY_MOTOR = motor_cognitivo_disponible()


@unittest.skipUnless(_HAY_MOTOR, "falta Cognitive Engine")
class TestAislamientoCognitivo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "mundos"

    def tearDown(self):
        self.tmp.cleanup()

    def _mundo(self, semilla=42, ancho=128, alto=128):
        ruta = mundo_io.crear_mundo(self.dir, semilla, ancho, alto, tam_celda_m=50)
        return ruta, db.abrir(ruta)

    # ---- Identidad -------------------------------------------------------
    def test_1_misma_semilla_world_uid_distinto(self):
        _, a = self._mundo(semilla=42)
        _, b = self._mundo(semilla=42)
        self.assertNotEqual(mundo_io.world_uid(a), mundo_io.world_uid(b))
        a.close(); b.close()

    def test_2_world_uid_persistente_tras_reabrir(self):
        ruta, a = self._mundo(semilla=7)
        u1 = mundo_io.world_uid(a)
        a.close()
        con = db.abrir(ruta)
        u2 = mundo_io.world_uid(con)
        con.close()
        self.assertEqual(u1, u2)

    def test_3_world_uid_no_es_la_semilla_ni_el_nombre(self):
        ruta, con = self._mundo(semilla=99)
        u = mundo_io.world_uid(con)
        con.close()
        self.assertNotEqual(u, "99")
        self.assertNotIn(u, ruta.stem)

    def test_4_mismos_ids_locales_no_colisionan(self):
        _, a = self._mundo(semilla=1)
        _, b = self._mundo(semilla=2)
        ca, cb = CerebroCognitivo(a), CerebroCognitivo(b)
        self.assertNotEqual(ca._world_uid, cb._world_uid)
        ida = "%s:d0:h1" % ca._world_uid
        idb = "%s:d0:h1" % cb._world_uid
        self.assertNotEqual(ida, idb)
        a.close(); b.close()

    # ---- Base por mundo --------------------------------------------------
    def test_5_base_cognitiva_por_mundo_distinta(self):
        _, a = self._mundo(semilla=1)
        _, b = self._mundo(semilla=2)
        ca, cb = CerebroCognitivo(a), CerebroCognitivo(b)
        self.assertIsNot(ca._repo, cb._repo)
        # La base nueva es por mundo, no la compartida legacy.
        self.assertNotEqual(Path(ca._repo.db_path).name, "cerebros_cognitivos.db")
        self.assertNotEqual(ca._repo.db_path, cb._repo.db_path)
        a.close(); b.close()

    # ---- Escritura/lectura aislada --------------------------------------
    def test_6_leer_A_no_ve_lo_de_B_y_viceversa(self):
        _, a = self._mundo(semilla=1)
        _, b = self._mundo(semilla=2)
        ca, cb = CerebroCognitivo(a), CerebroCognitivo(b)
        ida = "%s:d0:h1" % ca._world_uid
        idb = "%s:d0:h1" % cb._world_uid
        ca._adapter.service.create_brain(brain_id=ida, name="A1")
        cb._adapter.service.create_brain(brain_id=idb, name="B1")
        # A carga lo suyo; no lo de B.
        self.assertEqual(ca._repo.load(ida)["identity"].name, "A1")
        with self.assertRaises(Exception):
            ca._repo.load(idb)
        a.close(); b.close()

    def test_7_guardar_B_no_modifica_A(self):
        _, a = self._mundo(semilla=1)
        _, b = self._mundo(semilla=2)
        ca, cb = CerebroCognitivo(a), CerebroCognitivo(b)
        ida = "%s:d0:h1" % ca._world_uid
        ca._adapter.service.create_brain(brain_id=ida, name="A1")
        cb._adapter.service.create_brain(brain_id="%s:d0:h1" % cb._world_uid, name="B1")
        self.assertEqual(ca._repo.load(ida)["identity"].name, "A1")
        a.close(); b.close()

    def test_8_concurrencia_dos_mundos_escriben_sin_interferir(self):
        _, a = self._mundo(semilla=1)
        _, b = self._mundo(semilla=2)
        ca, cb = CerebroCognitivo(a), CerebroCognitivo(b)
        for c in (ca, cb):
            for hid in (1, 2, 3):
                c._adapter.service.create_brain(brain_id="%s:d0:h%d" % (c._world_uid, hid), name="n%d" % hid)
        ca._adapter.service.create_brain(brain_id="%s:d0:h1" % ca._world_uid, name="A1b")  # upsert A
        self.assertEqual(ca._repo.load("%s:d0:h1" % ca._world_uid)["identity"].name, "A1b")
        self.assertEqual(cb._repo.load("%s:d0:h1" % cb._world_uid)["identity"].name, "n1")
        a.close(); b.close()

    def test_9_recuperacion_no_mezcla(self):
        ruta, a = self._mundo(semilla=5)
        uid = mundo_io.world_uid(a)
        ca = CerebroCognitivo(a)
        ca._adapter.service.create_brain(brain_id="%s:d0:h1" % uid, name="A1")
        a.close()
        # Reabrir el mundo: mismo world_uid, misma base, recupera su cerebro.
        con = db.abrir(ruta)
        self.assertEqual(mundo_io.world_uid(con), uid)
        ca2 = CerebroCognitivo(con)
        self.assertEqual(ca2._repo.load("%s:d0:h1" % uid)["identity"].name, "A1")
        con.close()

    def test_11_list_brain_ids_devuelve_los_creados(self):
        _, a = self._mundo(semilla=1)
        ca = CerebroCognitivo(a)
        uid = ca._world_uid
        ca._adapter.service.create_brain(brain_id="%s:d0:h1" % uid, name="A1")
        ca._adapter.service.create_brain(brain_id="%s:d0:h2" % uid, name="A2")
        ids = set(ca.list_brain_ids())
        self.assertIn("%s:d0:h1" % uid, ids)
        self.assertIn("%s:d0:h2" % uid, ids)
        a.close()

    def test_12_recuperar_cerebros_al_reabrir_no_duplica(self):
        ruta, a = self._mundo(semilla=3)
        ca = CerebroCognitivo(a)
        uid = ca._world_uid
        ca._adapter.service.create_brain(brain_id="%s:d0:h1" % uid, name="A1")
        antes = ca._adapter.service.scheduler.brain_count
        a.close()
        con = db.abrir(ruta)
        ca2 = CerebroCognitivo(con)  # __init__ recupera automáticamente
        despues = ca2._adapter.service.scheduler.brain_count
        self.assertEqual(despues, antes)  # no duplica al recuperar
        self.assertEqual(ca2.list_brain_ids(), ["%s:d0:h1" % uid])
        con.close()

    def test_13_recuperar_cerebros_automatico_al_abrir_mundo(self):
        ruta, a = self._mundo(semilla=4)
        uid = mundo_io.world_uid(a)
        ca = CerebroCognitivo(a)
        ca._adapter.service.create_brain(brain_id="%s:d0:h1" % uid, name="A1")
        a.close()
        # Reabrir: el nuevo puente recupera solo en __init__ sin llamada explícita.
        con = db.abrir(ruta)
        ca2 = CerebroCognitivo(con)
        self.assertEqual(ca2.list_brain_ids(), ["%s:d0:h1" % uid])
        self.assertEqual(ca2._cerebros_restaurados, 1)
        con.close()

    def test_10_legacy_no_se_toca(self):
        # La base compartida legacy no se crea ni se usa: cada mundo abre la suya.
        _, a = self._mundo(semilla=1)
        CerebroCognitivo(a)
        self.assertFalse((self.dir / "cerebros_cognitivos.db").exists())
        a.close()


if __name__ == "__main__":
    unittest.main()
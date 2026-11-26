import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

from mundo_vivo.generador.pipeline import generar_mundo
from mundo_vivo.persistencia import db, mundo_io
from mundo_vivo.persistencia.memoria import MemoriaPrivada


def _habitante(con, nombre):
    with con:
        cur = con.execute("INSERT INTO habitantes (uuid, nombre) VALUES (?, ?)", (nombre + "-uuid", nombre))
    return cur.lastrowid


class TestPersistencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_guardar_y_cargar_es_identico(self):
        ruta = mundo_io.crear_mundo(self.dir, 123, 130, 100, tam_celda_m=50)  # tamaño que NO es múltiplo de 64
        con = db.abrir(ruta)
        capas = mundo_io.cargar_capas(con, verificar=True)
        original = generar_mundo(123, 130, 100)["capas"]
        for n in original:
            self.assertTrue(np.array_equal(capas[n], original[n]), n)
        con.close()

    def test_no_sobrescribe_mundos(self):
        r1 = mundo_io.crear_mundo(self.dir, 5, 64, 64, tam_celda_m=50)
        r2 = mundo_io.crear_mundo(self.dir, 5, 64, 64, tam_celda_m=50)
        self.assertNotEqual(r1, r2)
        self.assertTrue(r1.exists() and r2.exists())
        con = db.abrir(r1)
        with self.assertRaises(mundo_io.MundoYaExiste):
            mundo_io.guardar_mundo(con, generar_mundo(5, 64, 64))
        con.close()

    def test_migracion_con_backup_y_sin_perder_datos(self):
        ruta = mundo_io.crear_mundo(self.dir, 7, 64, 64, tam_celda_m=50)
        con = db.abrir(ruta)
        hid = _habitante(con, "Ayla")
        MemoriaPrivada(con, hid).agregar(500, "episodica", "Vi un río.")
        con.close()
        # simulamos una versión futura del programa con una migración 0002
        mig = self.dir / "migs"
        mig.mkdir()
        for _, _, f in db.listar_migraciones():
            (mig / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        (mig / "0099_agrega_apodo.sql").write_text("ALTER TABLE habitantes ADD COLUMN apodo TEXT;", encoding="utf-8")
        con = db.abrir(ruta, dir_backups=self.dir / "bk", directorio_migraciones=mig)
        self.assertEqual(db.version_actual(con), 99)
        self.assertEqual(MemoriaPrivada(con, hid).contar(), 1)  # la memoria sigue ahí
        self.assertEqual(con.execute("SELECT nombre FROM habitantes").fetchone()[0], "Ayla")
        con.close()
        backups = list((self.dir / "bk").glob("*.db"))
        self.assertEqual(len(backups), 1)  # se hizo backup antes de migrar
        b = sqlite3.connect(backups[0])
        self.assertEqual(b.execute("SELECT COUNT(*) FROM memorias").fetchone()[0], 1)
        b.close()

    def test_migracion_fallida_hace_rollback(self):
        ruta = mundo_io.crear_mundo(self.dir, 8, 64, 64, tam_celda_m=50)
        mig = self.dir / "migs"
        mig.mkdir()
        for _, _, f in db.listar_migraciones():
            (mig / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        (mig / "0099_rota.sql").write_text(
            "ALTER TABLE habitantes ADD COLUMN ok TEXT; ESTO NO ES SQL;", encoding="utf-8")
        with self.assertRaises(Exception):
            db.abrir(ruta, dir_backups=self.dir / "bk", directorio_migraciones=mig)
        con = db.abrir(ruta)  # con las migraciones reales sigue funcionando
        self.assertEqual(db.version_actual(con), db.listar_migraciones()[-1][0])
        cols = [r[1] for r in con.execute("PRAGMA table_info(habitantes)")]
        self.assertNotIn("ok", cols)
        con.close()

    def test_base_de_version_futura_no_se_toca(self):
        ruta = mundo_io.crear_mundo(self.dir, 9, 64, 64, tam_celda_m=50)
        con = sqlite3.connect(ruta)
        con.execute("INSERT INTO schema_migraciones VALUES (99, 'futura', 'hoy')")
        con.commit()
        con.close()
        with self.assertRaises(db.ErrorVersionFutura):
            db.abrir(ruta)

    def test_memoria_privada_aislada(self):
        con = db.abrir(self.dir / "t.db")
        a, b = _habitante(con, "A"), _habitante(con, "B")
        MemoriaPrivada(con, a).agregar(1, "episodica", "secreto de A")
        MemoriaPrivada(con, b).agregar(2, "episodica", "secreto de B")
        textos_b = [m["contenido"] for m in MemoriaPrivada(con, b).recientes(50)]
        self.assertEqual(textos_b, ["secreto de B"])
        with self.assertRaises(ValueError):
            MemoriaPrivada(con, a).agregar(3, "inventada", "x")
        con.close()

    def test_eventos(self):
        ruta = mundo_io.crear_mundo(self.dir, 3, 64, 64, tam_celda_m=50)
        con = db.abrir(ruta)
        h = _habitante(con, "Juancito")
        mundo_io.registrar_evento(con, 600, "herida", "Juancito se quebró un dedo escalando.",
                                  actor_id=h, causa="caída", importancia=2, datos={"parte": "dedo"})
        todos = mundo_io.listar_eventos(con)
        self.assertEqual(len(todos), 2)  # mundo_creado + herida
        self.assertEqual(mundo_io.listar_eventos(con, tipo="herida")[0]["texto"],
                         "Juancito se quebró un dedo escalando.")
        self.assertEqual(len(mundo_io.listar_eventos(con, actor_id=h)), 1)
        con.close()

    def test_exportar_e_importar_restaura_todo(self):
        ruta = mundo_io.crear_mundo(self.dir, 11, 100, 80, tam_celda_m=50)
        con = db.abrir(ruta)
        hid = _habitante(con, "Celia")
        MemoriaPrivada(con, hid).agregar(10, "semantica", "El agua del río se puede beber.")
        con.close()
        zip_path = mundo_io.exportar_paquete(ruta, self.dir / "salida" / "paquete.zip")
        with zipfile.ZipFile(zip_path) as z:
            self.assertEqual(sorted(z.namelist()), ["LEEME.txt", "meta.json", "mundo.db"])
            info = json.loads(z.read("meta.json"))
            self.assertEqual(info["habitantes"], 1)
        nueva = mundo_io.importar_paquete(zip_path, self.dir / "restaurado")
        con = db.abrir(nueva)
        self.assertEqual(MemoriaPrivada(con, hid).recientes(1)[0]["contenido"], "El agua del río se puede beber.")
        a = mundo_io.cargar_capas(con, verificar=True)
        b = generar_mundo(11, 100, 80)["capas"]
        self.assertTrue(all(np.array_equal(a[n], b[n]) for n in b))
        con.close()


if __name__ == "__main__":
    unittest.main()

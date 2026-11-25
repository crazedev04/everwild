import json
import tempfile
import unittest
from pathlib import Path

from mundo_vivo.agentes.vigilancia import detectar_sospecha
from mundo_vivo.persistencia import db, mundo_io, social
from mundo_vivo.persistencia.memoria import MemoriaPrivada


def _hab(con, nombre):
    with con:
        return con.execute("INSERT INTO habitantes (uuid, nombre) VALUES (?, ?)", (nombre + "-u", nombre)).lastrowid


class TestVigilancia(unittest.TestCase):
    def test_detecta_sospechas(self):
        casos = ["Creo que vivimos en una simulación.", "Esto no es real, Pepito.", "Quiero salir del mundo.",
                 "Alguien nos observa desde arriba.", "Somos programados por una computadora.",
                 "¿Y si todo es una MATRIX?"]
        for c in casos:
            self.assertTrue(detectar_sospecha(c), c)

    def test_no_marca_conversacion_normal(self):
        casos = ["Hay un rio cerca, ven a beber.", "Tengo hambre, voy al bosque.", "Anoche dormi mal por el frio.",
                 "Es real que los hongos enferman, Dante."]
        for c in casos:
            self.assertEqual(detectar_sospecha(c), [], c)

    def test_texto_vacio(self):
        self.assertEqual(detectar_sospecha(""), [])


class TestSocial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name) / "s.db"
        self.con = db.abrir(self.ruta)
        self.j, self.p, self.c = _hab(self.con, "Juancito"), _hab(self.con, "Pepito"), _hab(self.con, "Celia")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_dialogo_queda_registrado_y_recordado_por_ambos(self):
        did = social.registrar_dialogo(self.con, 600, self.j, [self.p], "Hay un rio al norte.")
        self.assertGreater(did, 0)
        self.assertEqual(social.listar_dialogos(self.con)[0]["mensaje"], "Hay un rio al norte.")
        mem_p = [m["contenido"] for m in MemoriaPrivada(self.con, self.p).recientes(5)]
        mem_j = [m["contenido"] for m in MemoriaPrivada(self.con, self.j).recientes(5)]
        self.assertIn("Juancito te dijo: «Hay un rio al norte.»", mem_p)
        self.assertIn("Le dijiste a Pepito: «Hay un rio al norte.»", mem_j)
        # un tercero que no estaba no recuerda nada
        self.assertEqual(MemoriaPrivada(self.con, self.c).contar(), 0)
        ev = mundo_io.listar_eventos(self.con, tipo="conversacion")
        self.assertEqual(len(ev), 1)

    def test_pelea_deja_rencor_que_persiste(self):
        social.registrar_dialogo(self.con, 700, self.j, [self.p], "¡Eres un inutil, te quedaste con mi comida!")
        social.ajustar_relacion(self.con, 700, self.p, self.j, d_afecto=-0.6, d_confianza=-0.5, motivo="lo insultó y le robó comida")
        social.ajustar_relacion(self.con, 700, self.j, self.p, d_afecto=-0.4, motivo="pelea por comida")
        self.con.close()
        self.con = db.abrir(self.ruta)  # "reinicio" del programa
        rel = social.relaciones_de(self.con, self.p)
        self.assertEqual(len(rel), 1)
        self.assertEqual(rel[0]["otro_nombre"], "Juancito")
        self.assertLess(rel[0]["afecto"], -0.25)
        self.assertIn("peleado", social.describir_relacion(rel[0]["afecto"], rel[0]["confianza"]) + " peleado")
        recuerdos = [m["contenido"] for m in MemoriaPrivada(self.con, self.p).recientes(10)]
        self.assertTrue(any("empeoró" in r for r in recuerdos))

    def test_reconciliacion_y_limites(self):
        for _ in range(5):
            social.ajustar_relacion(self.con, 800, self.p, self.j, d_afecto=-0.5)
        self.assertEqual(social.relaciones_de(self.con, self.p)[0]["afecto"], -1.0)  # no pasa de -1
        r = social.ajustar_relacion(self.con, 900, self.p, self.j, d_afecto=0.8, motivo="le pidió perdón")
        self.assertAlmostEqual(r["afecto"], -0.2)
        recuerdos = [m["contenido"] for m in MemoriaPrivada(self.con, self.p).recientes(10)]
        self.assertTrue(any("mejoró" in r for r in recuerdos))

    def test_relaciones_son_privadas(self):
        social.ajustar_relacion(self.con, 1, self.p, self.j, d_afecto=-0.5)
        self.assertEqual(social.relaciones_de(self.con, self.j), [])  # lo que siente Pepito no lo ve Juancito

    def test_alerta_de_sospecha_para_el_observador(self):
        social.registrar_dialogo(self.con, 1000, self.c, [self.p], "Creo que vivimos en una simulación y hay que salir del mundo.")
        social.registrar_dialogo(self.con, 1001, self.p, [self.c], "Mejor busquemos agua.")
        alertas = mundo_io.listar_eventos(self.con, tipo="sospecha_simulacion")
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["origen"], "sistema")
        self.assertEqual(alertas[0]["actor_id"], self.c)
        marcados = [d for d in social.listar_dialogos(self.con) if d["sospecha"]]
        self.assertEqual(len(marcados), 1)

    def test_los_dialogos_viajan_en_el_paquete_exportado(self):
        ruta = mundo_io.crear_mundo(Path(self.tmp.name) / "mundos", 4, 64, 64, tam_celda_m=50)  # un mundo real, con mapa
        con = db.abrir(ruta)
        a, b = _hab(con, "A"), _hab(con, "B")
        social.registrar_dialogo(con, 5, a, [b], "Hola.")
        con.close()
        zip_path = mundo_io.exportar_paquete(ruta, Path(self.tmp.name) / "p.zip")
        nueva = mundo_io.importar_paquete(zip_path, Path(self.tmp.name) / "r", nombre="r")
        con2 = db.abrir(nueva)
        self.assertEqual(social.listar_dialogos(con2)[0]["mensaje"], "Hola.")
        con2.close()

    def test_dialogo_sin_receptor_falla(self):
        with self.assertRaises(ValueError):
            social.registrar_dialogo(self.con, 1, self.j, [], "¿Hay alguien?")


if __name__ == "__main__":
    unittest.main()

import tempfile
import time
import unittest
from pathlib import Path

from mundo_vivo.agentes import ajustes as aj
from mundo_vivo.agentes.mente import CerebroHibrido
from mundo_vivo.motor import vida
from mundo_vivo.persistencia import db, mundo_io, sim_io
from tests.ollama_falso import _H, iniciar


class TestVidaSocial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.srv, self.url = iniciar()
        _H.estado, _H.llamadas = {}, 0
        ruta = mundo_io.crear_mundo(Path(self.tmp.name), 42, 128, 128, tam_celda_m=50)
        self.con = db.abrir(ruta)
        sim_io.crear_habitantes_iniciales(self.con, 4)
        # Esta prueba guioniza al modelo (inventa una balsa y la enseña): se apagan los módulos que deciden
        # por su cuenta, porque si no los objetivos inventan otra cosa antes y el LOD puede dejarlo sin turno.
        aj.guardar(self.con, {"host": self.url, "timeout_s": 20,
                              "modulos": {"objetivos": False, "atencion": False, "hambre": False}})
        self.cerebro = CerebroHibrido(self.con)
        self.sim = sim_io.cargar_simulacion(self.con, cerebro=self.cerebro)
        self._gest, self._adulto = vida.GESTACION_MIN, vida.ADULTO_MIN
        vida.GESTACION_MIN = 300
        # los 4 juntos, con sed y sueño tranquilos
        h0 = self.sim.habitantes[1]
        for h in self.sim.habitantes.values():
            h.x, h.y = h0.x + (h.id % 2), h0.y + (h.id // 2) % 2
            h.sed, h.energia = 20.0, 95.0

    def tearDown(self):
        vida.GESTACION_MIN, vida.ADULTO_MIN = self._gest, self._adulto
        self.cerebro.cliente._pool.shutdown(wait=False, cancel_futures=True)
        self.srv.shutdown()
        self.con.close()
        self.tmp.cleanup()

    def _correr(self, minutos):
        for _ in range(minutos):
            self.sim.avanzar(1)
            for h in self.sim.habitantes.values():   # mantiene el cuerpo tranquilo: la prueba es social
                if h.vivo:
                    h.sed, h.energia, h.salud = min(h.sed, 30.0), max(h.energia, 80.0), 100.0
            sim_io.volcar_eventos(self.con, self.sim)
            time.sleep(0.004)

    def test_circuito_completo(self):
        self._correr(900)
        tipos = {r[0] for r in self.con.execute("SELECT DISTINCT tipo FROM eventos")}
        self.assertIn("encuentro", tipos)
        self.assertIn("conversacion", tipos)
        self.assertGreater(_H.llamadas, 5)
        # diálogos registrados y recuerdos privados de ambos lados
        self.assertGreater(self.con.execute("SELECT COUNT(*) FROM dialogos").fetchone()[0], 3)
        self.assertGreater(self.con.execute("SELECT COUNT(*) FROM relaciones").fetchone()[0], 3)
        self.assertGreater(self.con.execute("SELECT COUNT(*) FROM memorias WHERE contenido LIKE '%te dijo%'").fetchone()[0], 3)
        # decisiones del modelo registradas para explicar el porqué
        self.assertGreater(self.con.execute("SELECT COUNT(*) FROM decisiones WHERE ok = 1").fetchone()[0], 3)
        # el afecto crece con conversaciones agradables (nadie se lo ordenó: salió de lo que dijeron)
        self.assertGreater(self.con.execute("SELECT MAX(afecto) FROM relaciones").fetchone()[0], 0.05)

    def test_familia_nacimiento_y_herencia(self):
        self._correr(2500)
        ev = {r[0] for r in self.con.execute("SELECT DISTINCT tipo FROM eventos")}
        self.assertIn("familia", ev)
        self.assertIn("nacimiento", ev)
        hijos = self.con.execute("SELECT id, madre_id, padre_id, genoma FROM habitantes WHERE madre_id IS NOT NULL").fetchall()
        self.assertGreaterEqual(len(hijos), 1)
        import json
        g = json.loads(hijos[0]["genoma"])
        self.assertEqual(g["generacion"], 1)
        self.assertEqual(len(g["pesos"]), 82)
        self.assertEqual(self.sim.edad_anios(self.sim.habitantes[hijos[0]["id"]]) < 1, True)

    def test_inventar_y_ensenar(self):
        self._correr(2500)
        cono = self.con.execute("SELECT nombre, propiedad, creador_id FROM conocimientos").fetchall()
        self.assertEqual(len(cono), 1)                        # «balsa» se registra una sola vez
        self.assertEqual((cono[0]["nombre"], cono[0]["propiedad"]), ("balsa", "flota"))
        saben = self.con.execute("SELECT COUNT(*) FROM conoce").fetchone()[0]
        self.assertGreaterEqual(saben, 2)                     # lo aprendió alguien más (enseñanza o redescubrimiento)
        self.assertGreaterEqual(self.con.execute("SELECT COUNT(*) FROM eventos WHERE tipo='descubrimiento'").fetchone()[0], 1)

    def test_apagar_el_modelo_no_rompe_y_no_hay_charla(self):
        aj.guardar(self.con, {"modulos": {"cerebro_llm": False}})
        self.sim.ajustes = aj.obtener(self.con)
        self._correr(600)
        self.assertEqual(_H.llamadas, 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM dialogos").fetchone()[0], 0)
        self.assertGreater(self.con.execute("SELECT COUNT(*) FROM eventos WHERE tipo='encuentro'").fetchone()[0], 0)

    def test_modelo_caido_cae_a_reglas_simples(self):
        aj.guardar(self.con, {"host": "http://127.0.0.1:1", "timeout_s": 10})
        self.sim.ajustes = aj.obtener(self.con)
        self._correr(120)    # no se cuelga ni explota
        self.assertFalse(self.cerebro.cliente.disponible() and self.cerebro.cliente.llamadas_ok > 0)

    def test_recetas_imposibles_se_rechazan(self):
        from mundo_vivo.agentes.conocimiento import validar
        r = self.sim.reglas
        self.assertFalse(validar(r, "balsa de hierro", ["hierro"], "flota")[0])
        self.assertFalse(validar(r, "magia", ["madera"], "vuela")[0])
        self.assertFalse(validar(r, "x", ["oro"], "flota")[0])
        self.assertTrue(validar(r, "cuchillo de piedra", ["piedra"], "corta")[0])


if __name__ == "__main__":
    unittest.main()

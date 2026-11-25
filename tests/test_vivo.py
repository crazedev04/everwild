import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from mundo_vivo.api.servidor import crear_app

from .ayuda import crear_mundo_api


class TestVivo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = crear_app(Path(self.tmp.name))
        self.cli = TestClient(self.app)
        self.nombre = crear_mundo_api(self.cli, semilla=42, ancho=128, alto=128)

    def tearDown(self):
        self.cli.close()
        self.tmp.cleanup()

    def test_websocket_hola_estado_y_comandos(self):
        with self.cli.websocket_connect("/ws/" + self.nombre) as ws:
            hola = json.loads(ws.receive_text())
            self.assertEqual(hola["tipo"], "hola")
            self.assertEqual(len(hola["estado"]["habitantes"]), 4)
            ws.send_text(json.dumps({"cmd": "velocidad", "v": 100}))
            visto_estado = False
            for _ in range(60):
                m = json.loads(ws.receive_text())
                if m["tipo"] == "estado":
                    visto_estado = True
                    if m["t_min"] > hola["estado"]["t_min"] + 20:
                        break
            self.assertTrue(visto_estado)
            ws.send_text(json.dumps({"cmd": "velocidad", "v": 7}))
            for _ in range(40):
                m = json.loads(ws.receive_text())
                if m["tipo"] == "error":
                    break
            else:
                self.fail("debía rechazar una velocidad no permitida")

    def test_el_mundo_se_guarda_al_desconectar_y_hay_ficha(self):
        with self.cli.websocket_connect("/ws/" + self.nombre) as ws:
            ws.receive_text()
            ws.send_text(json.dumps({"cmd": "velocidad", "v": 500}))
            for _ in range(30):
                ws.receive_text()
        hs = self.cli.get("/api/mundos/%s/habitantes" % self.nombre).json()
        self.assertEqual(len(hs), 4)
        ficha = self.cli.get("/api/mundos/%s/habitantes/%d" % (self.nombre, hs[0]["id"])).json()
        self.assertEqual(ficha["nombre"], hs[0]["nombre"])
        self.assertIn("rasgos", ficha)
        ev = self.cli.get("/api/mundos/%s/eventos" % self.nombre).json()["eventos"]
        self.assertTrue(any(e["tipo"] == "llegada" for e in ev))
        r = self.cli.get("/api/mundos/%s/dinamico/quemado" % self.nombre)
        self.assertEqual(len(r.content), 128 * 128)

    def test_mundo_inexistente_y_fuego_del_observador(self):
        with self.assertRaises(Exception):
            with self.cli.websocket_connect("/ws/no_existe") as ws:
                ws.receive_text()
        with self.cli.websocket_connect("/ws/" + self.nombre) as ws:
            hola = json.loads(ws.receive_text())
            h = hola["estado"]["habitantes"][0]
            ws.send_text(json.dumps({"cmd": "fuego", "x": int(h["x"]) + 25, "y": int(h["y"])}))
            for _ in range(40):
                m = json.loads(ws.receive_text())
                if m["tipo"] == "fuego":
                    break
            else:
                self.fail("sin respuesta al comando fuego")

    def test_poderes_del_observador(self):
        with self.cli.websocket_connect("/ws/" + self.nombre) as ws:
            hola = json.loads(ws.receive_text())
            h0 = hola["estado"]["habitantes"][0]
            # 1. Spawn habitante nómada
            ws.send_text(json.dumps({"cmd": "spawn", "x": int(h0["x"]), "y": int(h0["y"]), "nombre": "ViajeroTest", "sexo": "M"}))
            spawn_ok = False
            spawn_id = None
            for _ in range(30):
                m = json.loads(ws.receive_text())
                if m.get("tipo") == "spawn":
                    spawn_ok = True
                    spawn_id = m.get("id")
                    break
            self.assertTrue(spawn_ok, "El comando spawn falló")
            self.assertIsNotNone(spawn_id)

            # 2. Curar
            ws.send_text(json.dumps({"cmd": "curar", "id": spawn_id}))
            curar_ok = False
            for _ in range(30):
                m = json.loads(ws.receive_text())
                if m.get("tipo") == "curar":
                    curar_ok = True
                    break
            self.assertTrue(curar_ok, "El comando curar falló")

            # 3. Infectar zona
            ws.send_text(json.dumps({"cmd": "infectar", "x": int(h0["x"]), "y": int(h0["y"]), "radio": 15}))
            infect_ok = False
            for _ in range(30):
                m = json.loads(ws.receive_text())
                if m.get("tipo") == "infectar":
                    infect_ok = True
                    break
            self.assertTrue(infect_ok, "El comando infectar falló")

            # 4. Romper lazo
            ws.send_text(json.dumps({"cmd": "romper_lazo", "id": spawn_id}))
            romper_ok = False
            for _ in range(30):
                m = json.loads(ws.receive_text())
                if m.get("tipo") == "romper_lazo":
                    romper_ok = True
                    break
            self.assertTrue(romper_ok, "El comando romper_lazo falló")


if __name__ == "__main__":
    unittest.main()

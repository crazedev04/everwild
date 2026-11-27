import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

try:
    from fastapi.testclient import TestClient
    HAY_CLIENTE = True
except Exception:  # httpx no instalado
    HAY_CLIENTE = False

from mundo_vivo.api.servidor import crear_app
from mundo_vivo.motor.generador import generar_mundo

from .ayuda import crear_mundo_api


def meta_tam(cliente, nombre) -> int:
    return int(cliente.get("/api/mundos/%s/meta" % nombre).json()["tam_celda_m"])


@unittest.skipUnless(HAY_CLIENTE, "falta httpx (pip install -r requirements-dev.txt)")
class TestAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = TestClient(crear_app(Path(self.tmp.name)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_eliminar_mundo(self):
        a = crear_mundo_api(self.c, semilla=1, ancho=64, alto=64)
        b = crear_mundo_api(self.c, semilla=2, ancho=64, alto=64)
        self.c.get("/api/mundos/%s/meta" % a)                       # llena el caché
        r = self.c.delete("/api/mundos/%s" % a)
        self.assertEqual(r.status_code, 200)
        self.assertEqual([m["nombre"] for m in self.c.get("/api/mundos").json()], [b])
        self.assertEqual(self.c.get("/api/mundos/%s/meta" % a).status_code, 404)
        self.assertEqual(self.c.delete("/api/mundos/%s" % a).status_code, 404)
        self.assertEqual(self.c.delete("/api/mundos/..%2Fx").status_code in (400, 404), True)
        self.assertEqual(self.c.get("/ui/vivo.js").headers.get("cache-control"), "no-cache")

    def test_familias(self):
        a = crear_mundo_api(self.c, semilla=3, ancho=64, alto=64)
        r = self.c.get("/api/mundos/%s/familias" % a)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("personas", d)
        self.assertIn("uniones", d)

    def test_flujo_completo(self):
        self.assertEqual(self.c.get("/api/mundos").json(), [])
        nombre = crear_mundo_api(self.c, semilla=42, ancho=96, alto=96)
        self.assertEqual([m["nombre"] for m in self.c.get("/api/mundos").json()], [nombre])
        meta = self.c.get("/api/mundos/%s/meta" % nombre).json()
        self.assertEqual((meta["semilla"], meta["ancho"], meta["alto"]), (42, 96, 96))
        raw = self.c.get("/api/mundos/%s/capa/bioma" % nombre).content
        esperado = generar_mundo(42, 96, 96, meta_tam(self.c, nombre))["capas"]["bioma"]
        self.assertTrue(np.array_equal(np.frombuffer(raw, dtype=np.uint8).reshape(96, 96), esperado))
        elev = np.frombuffer(self.c.get("/api/mundos/%s/capa/elevacion" % nombre).content, dtype="<i2")
        self.assertEqual(elev.size, 96 * 96)
        ev = self.c.get("/api/mundos/%s/eventos" % nombre).json()
        tipos = [e["tipo"] for e in ev["eventos"]]
        self.assertIn("mundo_creado", tipos, "falta el evento de creación del mundo")
        z = self.c.post("/api/mundos/%s/exportar" % nombre)
        self.assertEqual(z.status_code, 200)
        self.assertTrue(z.content.startswith(b"PK"))

    def test_la_generacion_informa_su_progreso(self):
        """La pantalla de carga se alimenta de esto: POST devuelve un trabajo y se va preguntando cómo viene."""
        r = self.c.post("/api/mundos", json={"semilla": 77, "ancho": 64, "alto": 64})
        self.assertEqual(r.status_code, 200)
        tid = r.json()["trabajo"]
        self.assertEqual(self.c.get("/api/mundos/generando/noexiste").status_code, 404)
        vistos, nombre = [], None
        for _ in range(2000):
            t = self.c.get("/api/mundos/generando/%s" % tid).json()
            self.assertIsNone(t["error"])
            vistos.append(round(t["frac"], 2))
            if t["hecho"]:
                nombre = t["nombre"]
                break
            time.sleep(0.02)
        self.assertIsNotNone(nombre, "la generación nunca terminó")
        self.assertEqual(vistos[-1], 1.0)
        self.assertEqual(vistos, sorted(vistos), "el progreso no puede ir para atrás")
        self.assertIn(nombre, [m["nombre"] for m in self.c.get("/api/mundos").json()])

    def test_seguridad_de_nombres(self):
        self.assertEqual(self.c.get("/api/mundos/..%2F..%2Fetc%2Fpasswd/meta").status_code, 404)
        self.assertEqual(self.c.get("/api/mundos/no..existe/meta").status_code, 400)
        self.assertEqual(self.c.get("/api/mundos/inexistente/meta").status_code, 404)
        self.assertEqual(self.c.post("/api/mundos", json={"ancho": 5000, "alto": 64}).status_code, 400)

    def test_paginas(self):
        self.assertEqual(self.c.get("/api/biomas").status_code, 200)
        # los 15 de siempre; todo bioma nuevo (cavernas, senderos) va con id desde 100
        ids = [b["id"] for b in self.c.get("/api/biomas").json()]
        self.assertEqual([i for i in ids if i < 100], list(range(15)))


@unittest.skipUnless(HAY_CLIENTE, "falta httpx (pip install -r requirements-dev.txt)")
class TestConexionCCA(unittest.TestCase):
    """El switch 'Conectar con Cognition Chain' del modal de creación."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = TestClient(crear_app(Path(self.tmp.name)))

    def tearDown(self):
        self.tmp.cleanup()

    def _meta(self, nombre):
        from mundo_vivo.persistencia import db, mundo_io
        con = db.abrir(Path(self.tmp.name) / "mundos" / (nombre + ".db"))
        try:
            return mundo_io.cargar_meta(con)
        finally:
            con.close()

    def test_switch_activado_persiste_cerebro_remoto_true(self):
        nombre = crear_mundo_api(self.c, semilla=31, ancho=64, alto=64, conectar_cca=True)
        self.assertIs(self._meta(nombre)["cerebro_remoto"], True)

    def test_switch_desactivado_persiste_cerebro_remoto_false(self):
        nombre = crear_mundo_api(self.c, semilla=32, ancho=64, alto=64, conectar_cca=False)
        self.assertIs(self._meta(nombre)["cerebro_remoto"], False)

    def test_default_sin_switch_es_false(self):
        nombre = crear_mundo_api(self.c, semilla=33, ancho=64, alto=64)
        self.assertIs(self._meta(nombre)["cerebro_remoto"], False)

    def test_coexistencia_remoto_y_local(self):
        remoto = crear_mundo_api(self.c, semilla=34, ancho=64, alto=64, nombre="remoto", conectar_cca=True)
        local = crear_mundo_api(self.c, semilla=35, ancho=64, alto=64, nombre="local", conectar_cca=False)
        self.assertIs(self._meta(remoto)["cerebro_remoto"], True)
        self.assertIs(self._meta(local)["cerebro_remoto"], False)


if __name__ == "__main__":
    unittest.main()
    def test_modelo_elegido_al_crear_queda_guardado(self):
        import tempfile
        from fastapi.testclient import TestClient
        from mundo_vivo.api.servidor import crear_app
        from mundo_vivo.agentes import ajustes
        from mundo_vivo.persistencia import db
        with tempfile.TemporaryDirectory() as d:
            c = TestClient(crear_app(Path(d)))
            nombre = crear_mundo_api(c, semilla=5, ancho=64, alto=64, modelo="qwen3.5:9b")
            con = db.abrir(Path(d) / "mundos" / (nombre + ".db"))
            try:
                self.assertEqual(ajustes.obtener(con)["modelo"], "qwen3.5:9b")
            finally:
                con.close()
            self.assertIn("modelos", c.get("/api/modelos").json())


@unittest.skipUnless(HAY_CLIENTE, "falta httpx (pip install -r requirements-dev.txt)")
class TestSpawnDeHabitantes(unittest.TestCase):
    """Fase 6 del plan del motor: sangre nueva en un mundo que ya corre.

    Lo que esto destraba (fase 8): cuando uno engendra con todas, la generación siguiente son medio
    hermanos entre sí y `parentesco_cercano` les prohíbe procrear. El que llega de afuera no es pariente
    de nadie, así que la colonia deja de extinguirse por diseño.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = TestClient(crear_app(Path(self.tmp.name)))
        self.mundo = crear_mundo_api(self.c, semilla=11, ancho=96, alto=96)

    def tearDown(self):
        self.tmp.cleanup()

    def _habitantes(self):
        return self.c.get("/api/mundos/%s/habitantes" % self.mundo).json()

    def test_suma_una_persona_de_verdad(self):
        antes = len(self._habitantes())
        r = self.c.post("/api/mundos/%s/habitantes" % self.mundo, json={})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertIn(d["sexo"], ("F", "M"))
        self.assertEqual(len(self._habitantes()), antes + 1)
        ficha = self.c.get("/api/mundos/%s/habitantes/%d" % (self.mundo, d["id"])).json()
        self.assertEqual(ficha["nombre"], d["nombre"])

    def test_llega_sin_padres_asi_que_no_es_pariente_de_nadie(self):
        d = self.c.post("/api/mundos/%s/habitantes" % self.mundo, json={}).json()
        ficha = self.c.get("/api/mundos/%s/habitantes/%d" % (self.mundo, d["id"])).json()
        self.assertIsNone(ficha.get("madre_id"))
        self.assertIsNone(ficha.get("padre_id"))

    def test_el_sexo_se_puede_forzar_y_si_no_balancea(self):
        r = self.c.post("/api/mundos/%s/habitantes" % self.mundo, json={"sexo": "F"})
        self.assertEqual(r.json()["sexo"], "F")
        r = self.c.post("/api/mundos/%s/habitantes" % self.mundo, json={"sexo": "M"})
        self.assertEqual(r.json()["sexo"], "M")
        self.assertEqual(self.c.post("/api/mundos/%s/habitantes" % self.mundo,
                                     json={"sexo": "X"}).status_code, 400)

    def test_aparece_en_suelo_caminable_y_dentro_del_mapa(self):
        tam = meta_tam(self.c, self.mundo)
        for _ in range(5):
            d = self.c.post("/api/mundos/%s/habitantes" % self.mundo, json={}).json()
            self.assertTrue(0 <= d["x"] / tam < 96 and 0 <= d["y"] / tam < 96)

    def test_el_nombre_se_puede_elegir_y_se_valida(self):
        d = self.c.post("/api/mundos/%s/habitantes" % self.mundo, json={"nombre": "Zoraida"}).json()
        self.assertEqual(d["nombre"], "Zoraida")
        self.assertEqual(self.c.post("/api/mundos/%s/habitantes" % self.mundo,
                                     json={"nombre": "a"}).status_code, 400)

    def test_la_llegada_queda_como_suceso_del_mundo(self):
        d = self.c.post("/api/mundos/%s/habitantes" % self.mundo, json={}).json()
        eventos = self.c.get("/api/mundos/%s/eventos" % self.mundo).json()["eventos"]
        llegadas = [e for e in eventos if e["tipo"] == "llegada" and e["actor_id"] == d["id"]]
        self.assertEqual(len(llegadas), 1)
        self.assertIn(d["nombre"], llegadas[0]["texto"])

    def test_un_mundo_que_no_existe_da_404(self):
        self.assertEqual(self.c.post("/api/mundos/nada/habitantes", json={}).status_code, 404)

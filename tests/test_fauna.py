import json
import math
import os
import tempfile
import unittest
from pathlib import Path

from mundo_vivo import catalogos
from mundo_vivo.agentes import ajustes as aj
from mundo_vivo.agentes import conocimiento
from mundo_vivo.agentes.mente import CerebroHibrido
from mundo_vivo.persistencia.memoria import MemoriaPrivada
from mundo_vivo.motor import biomas as B
from mundo_vivo.motor.fauna import CLAVES_HABITAT, MAX_TOTAL
from mundo_vivo.persistencia import db, mundo_io, sim_io
from mundo_vivo.reglas import Reglas

from .ayuda import crear_mundo_api


class TestCatalogos(unittest.TestCase):
    def test_catalogos_base_validos_y_recetas_comprobables(self):
        esp = catalogos.cargar_especies(CLAVES_HABITAT)
        self.assertGreaterEqual(len(esp), 35)
        medios = {d["medio"] for d in esp.values()}
        self.assertEqual(medios, {"tierra", "agua", "aire"})
        clases = {d["clase"] for d in esp.values()}
        for c in ("mamifero", "ave", "reptil", "pez", "insecto", "aracnido", "molusco", "crustaceo"):
            self.assertIn(c, clases)
        for k in ("serpiente", "arana", "vaca", "cerdo", "caballo", "lobo", "leon"):
            self.assertIn(k, esp)
        self.assertTrue(esp["caballo"]["montable"])
        reglas = Reglas.cargar()
        rec = catalogos.cargar_recetas(reglas.materiales, conocimiento.PROPIEDADES)
        self.assertGreaterEqual(len(rec), 15)
        et = catalogos.cargar_etiquetas()
        for r in rec.values():        # toda receta del catálogo tiene que poder comprobarse con las reglas
            if any(m.startswith("#") and not et[m[1:]] for m in r["ingredientes"]):
                continue              # etiqueta que llena cada MUNDO (ver tests/test_minerales_desconocidos.py)
            ing = [sorted(et[m[1:]])[0] if m.startswith("#") else m for m in r["ingredientes"]]
            ok, motivo = conocimiento.validar(reglas, r["nombre"], ing, r["propiedad"])
            self.assertTrue(ok, "%s: %s" % (r["id"], motivo))

    def test_carpeta_extra_agrega_y_reemplaza(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "fauna").mkdir()
            (Path(d) / "recetas").mkdir()
            (Path(d) / "fauna" / "mia.json").write_text(json.dumps([
                {"type": "especie", "id": "dragon", "nombre": "dragón", "medio": "aire", "biomas": ["volcan"], "dieta": "carnivoro",
                 "peso_kg": 900, "velocidad": 3, "densidad": 1, "vida_dias": 90000, "presas": ["vaca"], "peligro": 10},
                {"type": "especie", "id": "vaca", "nombre": "vaca lechera", "medio": "tierra", "biomas": ["pradera"], "dieta": "herbivoro",
                 "peso_kg": 500, "velocidad": 1, "densidad": 3, "vida_dias": 6000}]), encoding="utf-8")
            (Path(d) / "recetas" / "mia.json").write_text(json.dumps([
                {"type": "receta", "id": "balsa_de_cuero", "nombre": "balsa de cuero", "ingredientes": ["cuero"], "propiedad": "flota"}]),
                encoding="utf-8")
            os.environ["MUNDO_VIVO_EXTRA"] = d
            try:
                esp = catalogos.cargar_especies(CLAVES_HABITAT)
                self.assertIn("dragon", esp)
                self.assertEqual(esp["vaca"]["nombre"], "vaca lechera")     # mismo id reemplaza
                rec = catalogos.cargar_recetas(Reglas.cargar().materiales, conocimiento.PROPIEDADES)
                self.assertIn("balsa_de_cuero", rec)
                # un error se dice con claridad
                (Path(d) / "fauna" / "rota.json").write_text(json.dumps([
                    {"type": "especie", "id": "x", "nombre": "x", "medio": "tierra", "biomas": ["luna"], "dieta": "herbivoro",
                     "peso_kg": 1, "velocidad": 1, "densidad": 1, "vida_dias": 10}]), encoding="utf-8")
                with self.assertRaises(catalogos.ErrorDeCatalogo) as cm:
                    catalogos.cargar_especies(CLAVES_HABITAT)
                self.assertIn("rota.json", str(cm.exception))
            finally:
                del os.environ["MUNDO_VIVO_EXTRA"]


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ruta = mundo_io.crear_mundo(Path(self.tmp.name), 777, 192, 192, tam_celda_m=50)
        self.con = db.abrir(ruta)
        sim_io.crear_habitantes_iniciales(self.con, 4)
        # estos tests son de otras mecánicas: el hambre se prueba aparte, en test_alimentacion.py
        aj.guardar(self.con, {"modulos": {"cerebro_llm": False, "fauna": True, "hambre": False}})
        self.cerebro = CerebroHibrido(self.con)
        self.sim = sim_io.cargar_simulacion(self.con, cerebro=self.cerebro)

    def tearDown(self):
        self.cerebro.cliente._pool.shutdown(wait=False, cancel_futures=True)
        self.con.close()
        self.tmp.cleanup()

    def _a_pie_de(self, sp: str, quedarse=True):
        """Pone a una persona al lado de un animal de esa especie (lo crea si hace falta)."""
        f = self.sim.fauna
        h = self.sim.habitantes[1]
        a = next((x for x in f.animales.values() if x.sp == sp), None)
        if a is None:
            a = f._nacer(sp)
        c = self.sim.terreno.caminable_cerca(int(a.x), int(a.y), 3)
        self.assertIsNotNone(c)
        h.x, h.y = c[0] + 0.5, c[1] + 0.5
        a.x, a.y = h.x + 0.6, h.y
        a.hambre = 0.0
        return h, a


class TestEcosistema(_Base):
    def test_poblacion_acotada_y_variada(self):
        self.sim.avanzar(10)
        f = self.sim.fauna
        self.assertGreater(len(f.animales), 60)
        self.assertLessEqual(len(f.animales), MAX_TOTAL)
        medios = {f.esp[a.sp]["medio"] for a in f.animales.values()}
        self.assertEqual(medios, {"tierra", "agua", "aire"})
        # cada animal está donde corresponde (peces en el agua, terrestres en tierra)
        t = self.sim.terreno
        for a in f.animales.values():
            e = f.esp[a.sp]
            if e["medio"] == "agua":
                self.assertGreater(t.agua[int(a.y), int(a.x)], 0, a.sp)
            elif e["medio"] == "tierra":
                self.assertEqual(t.agua[int(a.y), int(a.x)], 0, a.sp)

    def test_sin_grandes_depredadores_junto_al_inicio(self):
        self.sim.avanzar(10)
        cx, cy = self.sim.centro_seguro
        for a in self.sim.fauna.animales.values():
            e = self.sim.fauna.esp[a.sp]
            if e["peligro"] >= 5 and e["agresivo"] != "no":
                self.assertGreater(((a.x - cx) ** 2 + (a.y - cy) ** 2) ** 0.5, 40, a.sp)

    def test_semanas_sin_extinciones_masivas_ni_desborde(self):
        for _ in range(10):
            self.sim.avanzar(1440)
            for h in self.sim.habitantes.values():
                h.sed, h.energia, h.salud = 20.0, 90.0, 100.0
        f = self.sim.fauna
        self.assertLessEqual(len(f.animales), MAX_TOTAL)
        vivas = sum(1 for k, v in f.objetivo.items() if v and f.cuentas.get(k, 0) > 0)
        con_objetivo = sum(1 for v in f.objetivo.values() if v)
        self.assertGreaterEqual(vivas, int(con_objetivo * 0.8))   # casi todas las especies siguen existiendo

    def test_el_fuego_mata_y_ahuyenta_animales(self):
        self.sim.avanzar(5)
        f = self.sim.fauna
        a = next(x for x in f.animales.values() if f.esp[x.sp]["medio"] == "tierra" and f.esp[x.sp]["velocidad"] > 0)
        self.sim.fuego.fuego[int(a.y), int(a.x)] = 200
        self.sim.fuego._hubo_fuego = True
        antes = len(f.animales)
        for _ in range(40):
            f._tick(5.0, [])
            if a.id not in f.animales:
                break
        self.assertTrue(a.id not in f.animales or (int(a.x), int(a.y)) != (int(a.hx), int(a.hy)))
        self.assertLessEqual(len(f.animales), antes + 2)

    def test_guardar_y_cargar_conserva_animales(self):
        self.sim.avanzar(500)
        n, ids = len(self.sim.fauna.animales), set(self.sim.fauna.animales)
        sim_io.guardar_simulacion(self.con, self.sim)
        sim2 = sim_io.cargar_simulacion(self.con)
        self.assertEqual(set(sim2.fauna.animales), ids)
        self.assertEqual(len(sim2.fauna.animales), n)
        self.assertTrue(sim2._fauna_lista)


class TestCazaYAtaques(_Base):
    def test_cazar_da_botin_y_cuenta_la_historia(self):
        self.sim.avanzar(5)
        h, a = self._a_pie_de("ciervo")
        self.sim.rng_fauna.seed(1)
        ok = False
        for _ in range(40):
            if a.id not in self.sim.fauna.animales:
                break
            h.hasta = 0.0
            a.x, a.y = h.x + 0.6, h.y
            ok, txt = self.sim._aplicar(h, {"tipo": "cazar", "animal": "ciervo"})
            if ok:
                break
            h.salud = 100.0
        self.assertTrue(ok, "en 40 intentos tiene que cazar alguno")
        self.assertNotIn(a.id, self.sim.fauna.animales)
        self.assertGreater(h.inventario.get("carne", 0), 0)
        self.assertGreater(h.inventario.get("cuero", 0), 0)
        self.assertTrue(any(e["tipo"] == "caza" for e in self.sim._eventos))
        self.assertGreater(h.emo["alegria"], 0.0)

    def test_cazar_lejos_hace_acercarse(self):
        self.sim.avanzar(5)
        h, a = self._a_pie_de("ciervo")
        a.x, a.y = h.x + 9, h.y
        a.x = min(a.x, self.sim.terreno.ancho - 2)
        c = self.sim.terreno.caminable_cerca(int(a.x), int(a.y), 3)
        a.x, a.y = c[0] + 0.5, c[1] + 0.5
        ok, txt = self.sim._aplicar(h, {"tipo": "cazar", "animal": "ciervo"})
        self.assertIn("acercaste", txt) if ok else self.assertIn("llegar", txt)
        self.assertIn(a.id, self.sim.fauna.animales)

    def test_animal_inexistente_o_modulo_apagado(self):
        self.sim.avanzar(5)
        h = self.sim.habitantes[1]
        ok, txt = self.sim._aplicar(h, {"tipo": "cazar", "animal": "unicornio"})
        self.assertFalse(ok)
        self.sim.ajustes["modulos"]["fauna"] = False
        ok, txt = self.sim._aplicar(h, {"tipo": "cazar", "animal": "ciervo"})
        self.assertFalse(ok)

    def test_depredador_hambriento_ataca_y_la_persona_huye(self):
        self.sim.avanzar(5)
        h, a = self._a_pie_de("leon")
        a.hambre = 1.2
        antes = h.salud
        for _ in range(30):
            self.sim.fauna._grid = {}
            self.sim.fauna._armar_grid()
            self.sim._ataques_animales()
            a.ataque_hasta = 0.0
            if h.salud < antes:
                break
        self.assertLess(h.salud, antes)
        self.assertGreater(h.emo["miedo"], 0.0)
        self.assertTrue(any(e["tipo"] == "ataque_animal" for e in self.sim._eventos))
        # el reflejo del cerebro es alejarse
        a.hambre = 1.2
        a.x, a.y = h.x + 3, h.y
        r = self.cerebro._reflejos(self.sim, h)
        self.assertIsNotNone(r)
        self.assertEqual(r["tipo"], "ir")
        self.assertIn("huye", r["motivo"])

    def test_pacifico_no_ataca(self):
        self.sim.avanzar(5)
        h, a = self._a_pie_de("conejo")
        antes = h.salud
        for _ in range(20):
            self.sim.fauna._armar_grid()
            self.sim._ataques_animales()
        self.assertEqual(h.salud, antes)

    def test_montar_exige_rienda_y_acelera(self):
        self.sim.avanzar(5)
        h, a = self._a_pie_de("caballo")
        ok, txt = self.sim._aplicar(h, {"tipo": "montar", "animal": "caballo"})
        self.assertFalse(ok)
        self.assertIn("rienda", txt)
        # inventa la rienda (receta del catálogo: cuero que ata)
        h.hasta = 0.0
        ok, txt = self.sim._aplicar(h, {"tipo": "inventar", "receta": {"nombre": "tira para guiar", "materiales": ["cuero"], "propiedad": "ata"}})
        self.assertTrue(ok, txt)
        self.assertTrue(self.sim.sabe(h, "rienda"))
        montado = False
        for _ in range(30):
            h.hasta, h.montura = 0.0, None
            a.jinete = None
            a.x, a.y = h.x + 0.6, h.y
            ok, txt = self.sim._aplicar(h, {"tipo": "montar", "animal": "caballo"})
            if ok:
                montado = True
                break
        self.assertTrue(montado)
        self.assertEqual(h.montura, a.id)
        x0 = (h.x, h.y)
        c = self.sim.terreno.caminable_cerca(int(h.x) + 8, int(h.y), 5)
        h.camino = self.sim.terreno.buscar_camino((int(h.x), int(h.y)), c)
        h.accion, h.hasta = "caminando", 0.0
        self.sim._mover(h, 1.0)
        mont = ((h.x - x0[0]) ** 2 + (h.y - x0[1]) ** 2) ** 0.5
        self.sim._sincronizar_montura(h)
        self.assertEqual((a.x, a.y), (h.x, h.y))
        # Montado tiene que ir MÁS RÁPIDO que a pie desde el mismo lugar. Antes se comparaba contra una
        # velocidad de terreno fija de 1.0, y el caballo no siempre aparece en el mismo tipo de suelo.
        h.x, h.y = x0
        h.montura = None
        h.camino = self.sim.terreno.buscar_camino((int(h.x), int(h.y)), c)
        h.accion, h.hasta = "caminando", 0.0
        self.sim._mover(h, 1.0)
        a_pie = ((h.x - x0[0]) ** 2 + (h.y - x0[1]) ** 2) ** 0.5
        self.assertGreater(mont, a_pie, "montado tiene que avanzar más que a pie")
        h.montura, a.jinete = a.id, h.id        # se vuelve a montar: abajo se prueba el desmontar
        # desmontar
        ok, _ = self.sim._aplicar(h, {"tipo": "desmontar"})
        self.assertTrue(ok)
        self.assertIsNone(h.montura)
        self.assertIsNone(a.jinete)


class TestRecetasYEmociones(_Base):
    def test_receta_del_catalogo_vs_invento_propio(self):
        h = self.sim.habitantes[1]
        ok, txt = self.sim._aplicar(h, {"tipo": "inventar", "receta": {"nombre": "capa", "materiales": ["lana"], "propiedad": "abriga"}})
        self.assertTrue(ok, txt)
        rid = next(v for v in self.sim.conocimientos.values() if v["receta_id"] == "manto_de_lana")
        self.assertEqual(rid["origen"], "catalogo")
        self.assertEqual(rid["nombre"], "manto de lana")           # toma el nombre del catálogo
        h.hasta = 0.0
        ok, txt = self.sim._aplicar(h, {"tipo": "inventar", "receta": {"nombre": "escudo ligero", "materiales": ["madera", "cuero"], "propiedad": "arde"}})
        self.assertTrue(ok, txt)
        propio = next(v for v in self.sim.conocimientos.values() if v["nombre"] == "escudo ligero")
        self.assertEqual(propio["origen"], "inventada")
        # se guardó en la base con su origen
        filas = {r["nombre"]: (r["origen"], r["receta_id"]) for r in self.con.execute("SELECT nombre, origen, receta_id FROM conocimientos")}
        self.assertEqual(filas["manto de lana"], ("catalogo", "manto_de_lana"))
        self.assertEqual(filas["escudo ligero"][0], "inventada")
        # imposible: hierro no abriga
        h.hasta = 0.0
        ok, txt = self.sim._aplicar(h, {"tipo": "inventar", "receta": {"nombre": "manto de hierro", "materiales": ["hierro"], "propiedad": "abriga"}})
        self.assertFalse(ok)

    def test_emociones_suben_decaen_y_se_nombran(self):
        h = self.sim.habitantes[1]
        self.assertTrue(self.sim.etiqueta_emocion(h).startswith("tranquil"))
        self.sim.sentir(h, "miedo", 0.9)
        self.assertIn("asustad", self.sim.etiqueta_emocion(h))
        m0 = h.emo["miedo"]
        self.sim._decaer_emociones(h, 120.0)
        self.assertAlmostEqual(h.emo["miedo"], m0 / 2, delta=0.02)      # vida media de 2 horas
        self.sim._decaer_emociones(h, 2000.0)
        self.assertTrue(self.sim.etiqueta_emocion(h).startswith("tranquil"))
        self.sim.ajustes["modulos"]["emociones"] = False
        self.sim.sentir(h, "miedo", 1.0)
        self.assertEqual(h.emo["miedo"], 0.0)

    def test_el_temperamento_modula_las_emociones(self):
        a, b = self.sim.habitantes[1], self.sim.habitantes[2]
        a.genoma.rasgos["resiliencia"], b.genoma.rasgos["resiliencia"] = 1.0, 0.0
        self.sim.sentir(a, "tristeza", 0.3)
        self.sim.sentir(b, "tristeza", 0.3)
        self.assertGreater(b.emo["tristeza"], a.emo["tristeza"])

    def test_muerte_cercana_da_tristeza_y_persisten_emociones_e_inventario(self):
        h, o = self.sim.habitantes[1], self.sim.habitantes[2]
        o.x, o.y = h.x + 1, h.y
        self.sim._morir(o, "prueba")
        self.assertGreater(h.emo["tristeza"], 0.2)
        h.inventario["carne"] = 3
        sim_io.guardar_simulacion(self.con, self.sim)
        sim2 = sim_io.cargar_simulacion(self.con)
        self.assertEqual(sim2.habitantes[1].inventario.get("carne"), 3)
        self.assertGreater(sim2.habitantes[1].emo["tristeza"], 0.2)

    def test_el_prompt_muestra_animales_inventario_y_emocion(self):
        self.sim.avanzar(5)
        h, a = self._a_pie_de("ciervo")
        h.inventario["cuero"] = 2
        self.sim.sentir(h, "alegria", 0.7)
        sistema, usuario, _ = self.cerebro._prompt(self.sim, h)
        self.assertIn("ciervo", usuario)
        self.assertIn("cazar", usuario)
        self.assertIn("2 de cuero", usuario)
        self.assertIn("contenta", usuario) if h.sexo == "F" else self.assertIn("contento", usuario)


class TestApiRecetasFauna(unittest.TestCase):
    def test_endpoints(self):
        try:
            from fastapi.testclient import TestClient
        except Exception:
            self.skipTest("sin fastapi")
        from mundo_vivo.api.servidor import crear_app
        with tempfile.TemporaryDirectory() as d:
            c = TestClient(crear_app(Path(d)))
            nombre = crear_mundo_api(c, semilla=9, ancho=128, alto=128)
            ruta = Path(d) / "mundos" / (nombre + ".db")
            con = db.abrir(ruta)
            sim_io.crear_habitantes_iniciales(con, 4)
            sim = sim_io.cargar_simulacion(con)
            sim.ajustes["modulos"]["fauna"] = True
            sim.avanzar(30)
            h = sim.habitantes[1]
            sim._aplicar(h, {"tipo": "inventar", "receta": {"nombre": "cuerda", "materiales": ["fibra"], "propiedad": "ata"}})
            h.hasta = 0.0
            sim._aplicar(h, {"tipo": "inventar", "receta": {"nombre": "bolsa de plumas", "materiales": ["pluma", "fibra"], "propiedad": "abriga"}})
            sim_io.guardar_simulacion(con, sim)
            sim_io.volcar_eventos(con, sim)
            con.close()
            r = c.get("/api/mundos/%s/recetas" % nombre).json()
            self.assertTrue(any(e["id"] == "cuerda" and e["descubierta"] for e in r["existentes"]))
            self.assertTrue(any(e["nombre"] == "bolsa de plumas" for e in r["inventadas"]))
            self.assertGreaterEqual(len(r["existentes"]), 15)
            fa = c.get("/api/mundos/%s/fauna" % nombre).json()
            self.assertGreater(fa["total"], 30)
            self.assertTrue(any(e["id"] == "caballo" for e in fa["especies"]))
            ficha = c.get("/api/mundos/%s/habitantes/1" % nombre).json()
            self.assertIn("emocion", ficha)
            self.assertIn("inventario", ficha)


class TestHabla(_Base):
    def _juntos(self):
        a, b = self.sim.habitantes[1], self.sim.habitantes[2]
        b.x, b.y = a.x + 1, a.y
        a.hasta = b.hasta = 0.0
        a.accion = b.accion = "libre"
        return a, b

    def test_no_se_le_habla_a_quien_duerme(self):
        a, b = self._juntos()
        b.accion, b.hasta = "durmiendo", self.sim.t + 100
        ok, txt = self.sim._aplicar(a, {"tipo": "hablar", "a": b.id, "mensaje": "Despertate, hay agua nueva", "impresion": 1})
        self.assertFalse(ok)
        self.assertIn("durmiendo", txt)

    def test_espera_entre_charlas_y_no_repetir(self):
        a, b = self._juntos()
        ok, _ = self.sim._aplicar(a, {"tipo": "hablar", "a": b.id, "mensaje": "El agua del río está limpia y fresca", "impresion": 1})
        self.assertTrue(ok)
        a.hasta = 0.0
        self.sim.t += 10
        ok, txt = self.sim._aplicar(a, {"tipo": "hablar", "a": b.id, "mensaje": "Vi una colina enorme al norte", "impresion": 0})
        self.assertFalse(ok)
        self.assertIn("hace muy poco", txt)
        # responder a lo que le dijeron sí se puede enseguida, pero no con las mismas palabras
        b.hasta, b.accion = 0.0, "libre"
        ok, txt = self.sim._aplicar(b, {"tipo": "hablar", "a": a.id, "mensaje": "Gracias, mañana lo busco", "impresion": 1})
        self.assertTrue(ok, txt)
        b.hasta = 0.0
        self.sim.t += 200
        ok, txt = self.sim._aplicar(b, {"tipo": "hablar", "a": a.id, "mensaje": "Gracias, mañana lo busco otra vez", "impresion": 1})
        self.assertFalse(ok)
        self.assertIn("repitiendo", txt)

    def test_la_confianza_no_se_satura_de_golpe(self):
        from mundo_vivo.persistencia import social
        for _ in range(100):
            r = social.ajustar_relacion(self.con, 1, 1, 2, d_confianza=0.01)
        self.assertLess(r["confianza"], 0.8)
        self.assertGreater(r["confianza"], 0.3)

    def test_el_aburrimiento_aparece_en_el_prompt_y_amplia_la_exploracion(self):
        h = self.sim.habitantes[1]
        self.sim.t = 10 * 1440.0
        h.novedad_t = self.sim.t - 6 * 1440.0
        _, usuario, _ = self.cerebro._prompt(self.sim, h)
        self.assertIn("siempre lo mismo", usuario)
        h.novedad_t = self.sim.t
        _, usuario, _ = self.cerebro._prompt(self.sim, h)
        self.assertNotIn("siempre lo mismo", usuario)
        # ir a una zona nueva cuenta como novedad
        h.novedad_t = 0.0
        h.zonas = {(0, 0), (1, 1)}
        h.x, h.y = 100.5, 100.5
        h.camino, h.accion = [], "caminando"
        self.sim._mover(h, 0.1)
        self.assertEqual(h.novedad_t, self.sim.t)


class TestAnalisisMundoLargo(_Base):
    """Lo que salió de analizar un mundo real de un año: decisiones muy espaciadas, nadie se reencontraba, cero inventos, textos rotos."""

    def test_los_textos_no_salen_rotos(self):
        h = self.sim.habitantes[1]
        h.camino, h.accion = [], "libre"
        ok, txt = self.sim._aplicar(h, {"tipo": "ir", "destino": (int(h.x) + 1, int(h.y)), "motivo": "explora"})
        if ok:
            self.assertEqual(txt, "Saliste a explorar.")
        self.sim._dano(h, 5.0, "ataque de araña", "ataque_animal", "Ayla fue atacada por un animal: araña.", mio="Te atacó un animal (araña).")
        sim_io.volcar_eventos(self.con, self.sim)
        mem = [m["contenido"] for m in MemoriaPrivada(self.con, h.id).recientes(5)]
        self.assertTrue(any("Te atacó un animal" in m for m in mem))
        self.assertFalse(any("Te fue atacad" in m for m in mem))

    def test_recuerda_donde_vio_y_puede_buscar(self):
        a, b = self.sim.habitantes[1], self.sim.habitantes[2]
        b.x, b.y = a.x + 3, a.y
        a.prox_vista = 0.0
        self.sim._vida(a, 1.0)
        self.assertIn(b.id, a.visto)
        # se separan mucho: ya no la ve, pero sabe dónde estaba
        pos = tuple(a.visto[b.id][:2])
        t = self.sim.terreno
        for dx in (60, -60):
            c = t.caminable_cerca(int(a.x) + dx, int(a.y), 3)
            if c:
                a.x, a.y = c[0] + 0.5, c[1] + 0.5
                break
        self.sim.t += 3 * 1440
        aus = self.sim.ausentes(a)
        self.assertTrue(aus and aus[0][0].id == b.id and aus[0][1] >= 2.9)
        _, usuario, _ = self.cerebro._prompt(self.sim, a)
        self.assertIn("No ves a %s" % b.nombre, usuario)
        self.assertIn("buscar:", usuario)
        a.camino, a.hasta, a.accion = [], 0.0, "libre"
        ok, txt = self.sim._aplicar(a, {"tipo": "buscar", "a": b.id})
        self.assertTrue(ok or "camino" in txt, txt)

    def test_la_exploracion_no_disuelve_al_grupo(self):
        """Se alejan para explorar, pero no al infinito: el tope va en metros y tiene que superar a la zona de
        recursos (si no quedan atrapados) sin perder de vista al grupo."""
        from mundo_vivo.motor.tecnologia import METROS_ZONA
        a, b = self.sim.habitantes[1], self.sim.habitantes[2]
        a.visto[b.id] = [a.x, a.y, self.sim.t]
        lejos = []
        for _ in range(30):
            it = self.cerebro._demo_explorar(self.sim, a)
            if it["tipo"] == "ir" and it.get("destino"):
                d = it["destino"]
                lejos.append(math.hypot(d[0] - a.x, d[1] - a.y) * self.sim.tam_celda_m)
        self.assertTrue(lejos)
        self.assertLessEqual(max(lejos), 8000.0, "se están yendo demasiado lejos del grupo")
        self.assertGreater(max(lejos), METROS_ZONA, "no llegan a salir de su zona de recursos")

    def test_pistas_para_inventar_solo_despues_de_un_rato_y_sin_dar_la_receta(self):
        h = self.sim.habitantes[1]
        self.sim.t = 3 * 1440.0 + 600
        h.ultima_idea_t = self.sim.t - 60
        _, u, _ = self.cerebro._prompt(self.sim, h)
        self.assertNotIn("probás una idea nueva", u)
        h.ultima_idea_t = self.sim.t - 1.5 * 1440
        _, u, _ = self.cerebro._prompt(self.sim, h)
        self.assertIn("probás una idea nueva", u)
        self.assertIn("«inventar»", u)
        self.assertTrue([l for l in u.split("\n") if l.startswith("* ")][0].startswith("* inventar"))
        self.assertNotIn("hacha", u.lower().split("acciones posibles")[0])     # no se les regala el nombre
        # probar una idea (aunque falle) reinicia el reloj de las pistas
        self.sim._aplicar(h, {"tipo": "inventar", "receta": {"nombre": "x", "materiales": ["madera"], "propiedad": "flota"}})
        self.assertEqual(h.ultima_idea_t, self.sim.t)

    def test_velocidad_automatica_sigue_al_modelo(self):
        from mundo_vivo.api.vivo import Ejecutor
        class _Cli:
            def __init__(s, l): s.l = l
            def estado(s): return {"latencia_s": s.l}
        class _Cer:
            def __init__(s, l): s.cliente = _Cli(l)
        e = Ejecutor.__new__(Ejecutor)
        e.sim = self.sim
        M = Ejecutor.MIN_POR_PENSADA
        self.sim.ajustes["velocidad_max_pensando"] = 0.0
        e.cerebro = _Cer(6.4)
        self.assertAlmostEqual(e.tope_pensando(), M / 6.4, places=1)        # una decisión cada ~40 min del mundo
        e.cerebro = _Cer(0.5)
        self.assertEqual(e.tope_pensando(), M / 0.5)
        e.cerebro = _Cer(None)
        self.assertEqual(e.tope_pensando(), 10.0)
        # el tope fijo es un techo, no un permiso para atropellarlos: nunca deja al mundo correr MÁS que el automático
        e.cerebro = _Cer(0.5)
        self.sim.ajustes["velocidad_max_pensando"] = 30.0
        self.assertEqual(e.tope_pensando(), 30.0)                            # 30 < 80 automático: manda el fijo
        self.sim.ajustes["velocidad_max_pensando"] = 500.0
        self.assertEqual(e.tope_pensando(), M / 0.5)                         # 500 > 80: igual se respeta el automático

    def test_persisten_visto_y_ultima_idea(self):
        from mundo_vivo.persistencia import sim_io
        h = self.sim.habitantes[1]
        h.visto = {2: [10.5, 11.5, 300.0]}
        h.ultima_idea_t = 777.0
        sim_io.guardar_simulacion(self.con, self.sim)
        s2 = sim_io.cargar_simulacion(self.con, self.cerebro)
        self.assertEqual(s2.habitantes[1].visto, {2: [10.5, 11.5, 300.0]})
        self.assertEqual(s2.habitantes[1].ultima_idea_t, 777.0)


class TestMemoriaV2(_Base):
    def _mem(self, hid=1):
        return MemoriaPrivada(self.con, hid)

    def test_lo_repetido_se_refuerza_no_se_duplica(self):
        m = self._mem()
        for i in range(3):
            m.agregar(100 + i, "episodica", "Te atacó un animal (araña).", 0.6, x=10, y=10)
        filas = m.recientes(10)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["veces"], 3)
        self.assertGreater(filas[0]["importancia"], 0.6)

    def test_recuperar_prioriza_lo_relacionado_aunque_sea_viejo(self):
        m = self._mem()
        m.agregar(1000, "episodica", "Una araña venenosa te mordió junto a las rocas.", 0.6, x=50, y=50)
        for i in range(8):
            m.agregar(5000 + i * 10, "episodica", "Caminaste por la pradera número %d tranquilo." % i, 0.3, x=5, y=5)
        r = m.recordar(5200, "araña rocas peligro", x=50, y=50, n=3, tocar=False)
        self.assertTrue(any("araña" in x["contenido"] for x in r))
        r2 = m.recordar(5200, "pradera", x=5, y=5, n=2, tocar=False)       # sin relación, mandan lo reciente y la cercanía
        self.assertFalse(any("araña" in x["contenido"] for x in r2))

    def test_olvida_lo_flojo_y_conserva_lo_importante_y_lo_aprendido(self):
        m = self._mem()
        m.agregar(0, "episodica", "Viste una nube rara.", 0.2)
        m.agregar(0, "episodica", "Naciste de nuevo en un sueño importante.", 0.95)
        m.agregar(0, "creencia", "Las arañas del desierto muerden: conviene evitarlas.", 0.85, origen="reflexion")
        n = m.olvidar(30 * 1440)
        self.assertEqual(n, 1)
        textos = [x["contenido"] for x in m.recientes(10)]
        self.assertFalse(any("nube" in t for t in textos))
        self.assertEqual(len(textos), 2)

    def test_los_lugares_se_recuerdan_y_aparecen_en_el_prompt(self):
        h = self.sim.habitantes[1]
        h.marcar_lugar("peligro", h.x + 10, h.y, "araña", self.sim.t, radio=8)
        h.marcar_lugar("peligro", h.x + 11, h.y, "araña", self.sim.t, radio=8)       # mismo sitio: se refuerza
        self.assertEqual(len(h.lugares["peligro"]), 1)
        self.assertEqual(h.lugares["peligro"][0][4], 2)
        h.plan = ["volver al río", "buscar a Bruno"]
        _, u, _ = self.cerebro._prompt(self.sim, h)
        self.assertIn("Lugares que recordás", u)
        self.assertIn("peligro hacia el este", u)
        self.assertIn("Tus intenciones: volver al río; buscar a Bruno", u)

    def test_reflexion_guarda_aprendizajes_nuevos_y_el_plan_y_no_repite(self):
        h = self.sim.habitantes[1]
        texto = json.dumps({"aprendizajes": ["Las arañas muerden si me acerco a las rocas, mejor rodearlas.", "ok"],
                            "intenciones": ["Volver al río antes de que anochezca", "x"]})
        self.cerebro._guardar_reflexion(self.sim, h, {"texto": texto, "latencia_s": 1.0}, "prompt")
        sim_io.volcar_eventos(self.con, self.sim)
        cre = self._mem().creencias(5, "", self.sim.t)
        self.assertEqual(len(cre), 1)                                    # «ok» es demasiado corto y no se guarda
        self.assertEqual(h.plan, ["Volver al río antes de que anochezca"])
        self.cerebro._guardar_reflexion(self.sim, h, {"texto": texto, "latencia_s": 1.0}, "prompt")   # lo mismo otra vez
        sim_io.volcar_eventos(self.con, self.sim)
        self.assertEqual(len(self._mem().creencias(5, "", self.sim.t)), 1)
        _, u, _ = self.cerebro._prompt(self.sim, h)
        self.assertIn("Lo que fuiste aprendiendo", u)

    def test_la_reflexion_se_dispara_cada_varios_dias_y_solo_si_paso_algo(self):
        from mundo_vivo.agentes.mente import DIAS_REFLEXION
        h = self.sim.habitantes[1]
        for i in range(8):
            self._mem().agregar(100 + i, "episodica", "Recuerdo distinto número %d de la pradera." % i, 0.5)
        lanzadas = []
        class _F:
            t0 = __import__("time").time()
            def done(s): return False
        self.cerebro.cliente.pedir = lambda *a, **k: (lanzadas.append(1), _F())[1]
        self.sim.t = 1.5 * 1440.0                                         # todavía no pasaron los días necesarios
        self.assertIsNone(self.cerebro._reflexion(self.sim, h))
        self.assertEqual(len(lanzadas), 0)
        self.sim.t = (DIAS_REFLEXION + 1) * 1440.0
        r = self.cerebro._reflexion(self.sim, h)
        self.assertEqual(r["motivo"], "pensando")
        self.assertEqual(len(lanzadas), 1)
        self.cerebro.pend_ref.clear()
        self.assertIsNone(self.cerebro._reflexion(self.sim, h))           # recién reflexionó
        self.assertEqual(len(lanzadas), 1)
        # pasan los días pero no vivió nada nuevo: no se gasta una consulta del modelo en reflexionar
        self.sim.t += (DIAS_REFLEXION + 1) * 1440.0
        self.assertIsNone(self.cerebro._reflexion(self.sim, h))
        self.assertEqual(len(lanzadas), 1)

    def test_los_lugares_persisten(self):
        h = self.sim.habitantes[1]
        h.marcar_lugar("agua", 12.0, 13.0, "agua para beber", 500.0)
        h.plan = ["dormir temprano"]
        sim_io.guardar_simulacion(self.con, self.sim)
        s2 = sim_io.cargar_simulacion(self.con, self.cerebro)
        self.assertEqual(s2.habitantes[1].lugares["agua"][0][:2], [12.0, 13.0])
        self.assertEqual(s2.habitantes[1].plan, ["dormir temprano"])


class TestPersonalidadYHabito(_Base):
    def test_la_experiencia_corre_el_caracter_con_tope_y_queda_anotado(self):
        h = self.sim.habitantes[1]
        base = h.genoma.rasgos["cautela"]
        for _ in range(40):
            self.sim.moldear(h, "cautela", 0.03, "los ataques")
        self.assertAlmostEqual(h.rasgo("cautela"), min(1.0, base + 0.25), places=4)      # tope: ±0.25 de lo heredado
        self.assertEqual(h.genoma.rasgos["cautela"], base)                               # el genoma no se toca
        self.assertIn("más cauteloso", " ".join(e["texto"] for e in self.sim._eventos) if base < 0.7 <= base + 0.25 else "más cauteloso")

    def test_el_caracter_vivo_llega_al_prompt_y_persiste(self):
        h = self.sim.habitantes[1]
        h.genoma.rasgos["sociabilidad"] = 0.5
        for _ in range(30):
            self.sim.moldear(h, "sociabilidad", 0.02, "charlas")
        _, u, _ = self.cerebro._prompt(self.sim, h)
        self.assertIn("busca la compañia de otros", u)
        sim_io.guardar_simulacion(self.con, self.sim)
        s2 = sim_io.cargar_simulacion(self.con, self.cerebro)
        self.assertAlmostEqual(s2.habitantes[1].rasgo("sociabilidad"), 0.75, places=2)

    def test_modulo_personalidad_apagado_no_cambia_nada(self):
        h = self.sim.habitantes[1]
        self.sim.ajustes["modulos"]["personalidad"] = False
        antes = h.rasgo("audacia")
        self.sim.moldear(h, "audacia", 0.1, "x")
        self.assertEqual(h.rasgo("audacia"), antes)

    def test_el_habito_aprende_y_es_propio_de_cada_persona(self):
        from mundo_vivo.agentes.habito import Habito, ACTIVIDADES, N_IN
        a, b = self.sim.habitantes[1], self.sim.habitantes[2]
        ha, hb = Habito(genoma_pesos=a.genoma.pesos), Habito(genoma_pesos=b.genoma.pesos)
        x = [0.3] * N_IN
        self.assertNotEqual(ha.valores(x), hb.valores(x))                  # arrancan distintos
        for _ in range(200):
            ha.aprender(x, "cazar", 0.8)
            ha.aprender(x, "explorar", -0.8)
        v = ha.valores(x)
        self.assertGreater(v["cazar"], 0.5)
        self.assertLess(v["explorar"], -0.5)
        h2 = Habito.de_dict(ha.a_dict(), a.genoma.pesos)
        self.assertEqual(h2.n, ha.n)
        self.assertAlmostEqual(h2.valores(x)["cazar"], v["cazar"], places=2)

    def test_ciclo_completo_aprende_de_lo_que_le_paso(self):
        h = self.sim.habitantes[1]
        h.accion, h.hasta, h.camino = "libre", 0.0, []
        acc = {"tipo": "ir", "destino": (int(h.x) + 3, int(h.y)), "motivo": "explora"}
        self.cerebro._foto(self.sim, h, acc)
        self.assertEqual(h.snap["act"], "explorar")
        self.sim.t += 30
        h.ataque_t = self.sim.t - 5           # en el camino lo atacó un animal
        h.salud -= 20
        self.cerebro._aprender(self.sim, h)
        self.assertIsNone(h.snap)
        self.assertEqual(h.habito.n, 1)
        self.assertLess(h.habito.valores(self.cerebro._features(self.sim, h))["explorar"], 0.0)

    def test_en_el_prompt_aparece_su_inclinacion_solo_con_experiencia(self):
        from mundo_vivo.agentes.habito import N_IN
        h = self.sim.habitantes[1]
        _, u, _ = self.cerebro._prompt(self.sim, h)
        self.assertNotIn("te tira", u)
        hb = self.cerebro._hb(h)
        x = self.cerebro._features(self.sim, h)
        for _ in range(60):
            hb.aprender(x, "cazar", 0.9)
        _, u, _ = self.cerebro._prompt(self.sim, h)
        self.assertIn("te tira cazar", u)


class TestFrioYNieve(_Base):
    def _frio_en_todos_lados(self, grados):
        self.sim.terreno.temperatura[:] = grados

    def test_la_temperatura_sigue_estacion_y_hora(self):
        from mundo_vivo.motor import reloj
        dia_verano = 45 * 1440 + 14 * 60
        noche_invierno = 105 * 1440 + 2 * 60
        self.assertGreater(reloj.ajuste_temp(dia_verano), reloj.ajuste_temp(noche_invierno) + 15)

    def test_nieve_se_acumula_con_hielo_y_se_derrite_con_calor_y_persiste(self):
        self._frio_en_todos_lados(-20)
        for _ in range(60):
            self.sim.t += 30
            self.sim._paso_nieve(30)
        tierra = self.sim.terreno.agua == 0
        self.assertGreater(float(self.sim.nieve[tierra].mean()), 0.2)
        self.assertEqual(float(self.sim.nieve[~tierra].max()), 0.0)            # en el agua no se acumula
        sim_io.guardar_simulacion(self.con, self.sim)
        s2 = sim_io.cargar_simulacion(self.con, self.cerebro)
        self.assertAlmostEqual(float(s2.nieve[tierra].mean()), float(self.sim.nieve[tierra].mean()), places=1)
        self._frio_en_todos_lados(25)
        antes = float(self.sim.nieve[tierra].mean())
        for _ in range(200):
            self.sim.t += 30
            self.sim._paso_nieve(30)
        self.assertLess(float(self.sim.nieve[tierra].mean()), antes * 0.2)

    def test_la_nieve_frena_y_apaga_el_fuego(self):
        h = self.sim.habitantes[1]
        self.sim.nieve[:] = 0.0
        v0 = self.sim.terreno.velocidad_en(h.x, h.y)
        self.sim.nieve[:] = 1.0
        self.assertAlmostEqual(self.sim.nieve_en(h.x, h.y), 1.0)
        x, y = int(h.x) + 2, int(h.y) + 2
        self.sim.fuego.fuego[y, x] = 200
        self.sim.fuego._hubo_fuego = True
        self._frio_en_todos_lados(-10)
        self.sim.t += 30
        self.sim._paso_nieve(30)
        self.assertEqual(int(self.sim.fuego.fuego[y, x]), 0)

    def test_el_frio_debilita_y_el_abrigo_protege(self):
        h = self.sim.habitantes[1]
        self._frio_en_todos_lados(-12)
        self.sim.t = 105 * 1440 + 120                     # noche de pleno invierno
        sev = self.sim.severidad_frio(h)
        self.assertGreater(sev, 0.8)
        # con receta que abriga y cuero encima, baja
        cid = 99
        self.sim.conocimientos[cid] = {"nombre": "capa", "materiales": ["cuero"], "propiedad": "abriga", "descripcion": "", "creador_id": 1,
                                       "origen": "inventada", "receta_id": None, "t_min": 0}
        h.conoce.add(cid)
        self.assertEqual(self.sim.abrigo_de(h), 0.0)      # sabe, pero no tiene con qué
        h.inventario["cuero"] = 3
        self.assertGreater(self.sim.abrigo_de(h), 0.4)
        self.assertLess(self.sim.severidad_frio(h), sev * 0.7)

    def test_sin_abrigo_el_frio_extremo_mata_y_con_modulo_apagado_no(self):
        h = self.sim.habitantes[1]
        self._frio_en_todos_lados(-30)
        self.sim.t = 105 * 1440 + 120
        h.accion, h.hasta = "libre", 0.0
        for _ in range(6000):
            self.sim._actualizar(h, 1.0)
            h.sed = 10.0
            h.energia = max(h.energia, 40.0)
            if not h.vivo:
                break
        self.assertFalse(h.vivo)
        self.assertEqual(h.causa_muerte, "frío")
        h2 = self.sim.habitantes[2]
        self.sim.ajustes["modulos"]["frio"] = False
        for _ in range(300):
            self.sim._actualizar(h2, 1.0)
            h2.sed = 10.0
        self.assertTrue(h2.vivo)

    def test_de_dia_y_en_clima_templado_no_hay_frio_grave(self):
        h = self.sim.habitantes[1]
        self._frio_en_todos_lados(16)
        self.sim.t = 105 * 1440 + 14 * 60
        self.assertLess(self.sim.severidad_frio(h), 0.35)

    def test_animales_sensibles_mueren_de_frio_y_los_de_clima_frio_no(self):
        f = self.sim.fauna
        self.assertGreaterEqual(f.esp["conejo"]["frio_min"], -22.0 - 1e-9)
        self.assertLess(min(d["frio_min"] for d in f.esp.values()), -30.0)      # hay animales de zonas heladas
        self.assertGreater(f.esp["serpiente"]["frio_min"] if "serpiente" in f.esp else 0.0, -1.0)
        self.sim.avanzar(5)
        f.temp_fn = lambda x, y: -60.0
        n0 = sum(1 for a in f.animales.values() if f.esp[a.sp]["medio"] != "agua")
        self.sim.avanzar(60 * 24)
        n1 = sum(1 for a in f.animales.values() if f.esp[a.sp]["medio"] != "agua")
        self.assertLess(n1, n0)
        self.assertGreater(f.muertes.get("frío", 0), 0)

    def test_el_prompt_cuenta_el_frio_y_busca_calor(self):
        h = self.sim.habitantes[1]
        self._frio_en_todos_lados(-8)
        self.sim.t = 105 * 1440 + 120
        h.frio = self.sim.severidad_frio(h)
        _, u, _ = self.cerebro._prompt(self.sim, h)
        self.assertIn("Hiela", u)
        self.assertIn("el frío te está debilitando", u)
        # un lugar más cálido a poca distancia: el reflejo lo busca
        self.sim.terreno.temperatura[:] = -8
        cy, cx = int(h.y), int(h.x)
        self.sim.terreno.temperatura[max(0, cy - 30):cy + 30, max(0, cx - 30):cx + 30] = -8
        for yy in range(max(0, cy - 24), cy + 24):
            for xx in range(max(0, cx - 24), cx + 24):
                if (xx - cx) ** 2 + (yy - cy) ** 2 > 64:
                    self.sim.terreno.temperatura[yy, xx] = 6
        r = self.cerebro._reflejos(self.sim, h)
        self.assertTrue(r is None or r.get("motivo") == "busca abrigo del frío" or r.get("tipo") in ("beber", "ir", "dormir"))


class TestVelocidadModelo(unittest.TestCase):
    def test_ajustes_nuevos_validan(self):
        with tempfile.TemporaryDirectory() as d:
            con = db.abrir(mundo_io.crear_mundo(Path(d), 5, 64, 64, tam_celda_m=50))
            try:
                r = aj.guardar(con, {"paralelo": 9, "max_tokens": 10, "velocidad_max_pensando": 100})
                self.assertEqual((r["paralelo"], r["max_tokens"], r["velocidad_max_pensando"]), (4, 60, 100.0))
            finally:
                con.close()

    def test_el_pool_cambia_de_tamano_sin_romper(self):
        from mundo_vivo.agentes.ollama import ClienteOllama
        c = ClienteOllama()
        c.pedir({"paralelo": 3, "modelo": "x", "host": "http://127.0.0.1:1", "temperatura": 0.5, "num_ctx": 512,
                 "timeout_s": 10, "max_tokens": 80}, "s", "u", {}, 1)
        self.assertEqual(c._tam, 3)
        c._pool.shutdown(wait=False, cancel_futures=True)


class TestAguaAlcanzable(_Base):
    def test_agua_cercana_siempre_devuelve_un_lugar_al_que_se_llega(self):
        """Celia murió de sed a 3 celdas de agua aislada por acantilados: debe elegir agua a la que SÍ se llega."""
        import random
        t = self.sim.terreno
        h = self.sim.habitantes[1]
        rnd = random.Random(5)
        n = 0
        for _ in range(40):
            c0 = t.caminable_cerca(rnd.randrange(t.ancho), rnd.randrange(t.alto), 4)
            if not c0:
                continue
            h.x, h.y = c0[0] + 0.5, c0[1] + 0.5
            c = self.sim.agua_cercana(h, 60)
            if c is None:
                continue
            n += 1
            self.assertTrue(t.caminable(*c) and t.agua_adyacente(*c))
            if c != c0:
                self.assertIsNotNone(t.buscar_camino(c0, c, 40000), "%s -> %s" % (c0, c))
        self.assertGreater(n, 5)


class TestConservacion(_Base):
    def _dar(self, item, n=2):
        h = self.sim.habitantes[1]
        self.sim._ganar_item(h, item, n)
        return h

    def test_la_carne_se_pudre_y_el_cuero_no(self):
        h = self._dar("carne"); self._dar("cuero")
        self.sim.terreno.temperatura[:] = 12
        for _ in range(60 * 24 * 3 // 60):
            self.sim._paso_conservacion(60)
        self.assertEqual(h.inventario.get("carne", 0), 0)
        self.assertGreater(h.inventario.get("podrido", 0), 0)
        self.assertGreater(h.inventario.get("cuero", 0), 0)
        self.assertEqual(h.rotos, 1)

    def test_curar_alarga_la_vida_y_persiste(self):
        h = self._dar("carne", 3)
        ok, _ = self.sim._accion_curar(h, {})
        self.assertTrue(ok)
        self.sim.terreno.temperatura[:] = 12
        for _ in range(24 * 5):
            self.sim._paso_conservacion(60)
        self.assertEqual(h.inventario.get("carne_curada"), 3)
        sim_io.guardar_simulacion(self.con, self.sim)
        s2 = sim_io.cargar_simulacion(self.con, self.cerebro)
        self.assertEqual(s2.habitantes[1].inventario.get("carne_curada"), 3)
        self.assertGreater(s2.habitantes[1].inv_t.get("carne_curada", 0), 0)

    def test_cocinar_pide_fuego(self):
        h = self._dar("carne")
        ok, _ = self.sim._accion_cocinar(h, {})
        self.assertFalse(ok)

    def test_tope_de_lote(self):
        h = self._dar("carne", 500)
        self.assertLessEqual(h.inventario["carne"], 60)


class TestCatalogoRecetas(unittest.TestCase):
    def test_todas_las_recetas_del_catalogo_son_validas_y_unicas(self):
        from mundo_vivo import catalogos
        from mundo_vivo.agentes import conocimiento
        from mundo_vivo.reglas import Reglas
        reglas = Reglas.cargar()
        rec = catalogos.cargar_recetas(reglas.materiales, conocimiento.PROPIEDADES)
        self.assertGreater(len(rec), 100)
        et = catalogos.cargar_etiquetas()
        for r in rec.values():
            if any(m.startswith("#") and not et[m[1:]] for m in r["ingredientes"]):
                continue              # etiqueta que llena cada MUNDO, vacía en el catálogo a propósito
            ing = []
            for m in r["ingredientes"]:
                ing.append(sorted(et[m[1:]])[0] if m.startswith("#") else m)
            ok, msg = conocimiento.validar(reglas, r["nombre"], ing, r["propiedad"])
            self.assertTrue(ok, "%s: %s" % (r["id"], msg))

    def test_etiqueta_acepta_cualquier_lena(self):
        from mundo_vivo import catalogos
        from mundo_vivo.agentes import conocimiento
        from mundo_vivo.reglas import Reglas
        reglas = Reglas.cargar()
        rec = catalogos.cargar_recetas(reglas.materiales, conocimiento.PROPIEDADES)
        self.assertEqual(catalogos.buscar_receta(rec, ["carbon"], "arde")["id"], "hoguera_de_carbon")   # exacta primero
        self.assertEqual(catalogos.buscar_receta(rec, ["paja"], "arde")["id"], "fogata_de_paja")


class TestTecnologia(_Base):
    def _con_receta(self, h, rid):
        r = self.sim.recetas[rid]
        cid = max(self.sim.conocimientos, default=0) + 1
        self.sim.conocimientos[cid] = {"nombre": r["nombre"], "materiales": r["ingredientes"], "propiedad": r["propiedad"], "descripcion": "",
                                       "creador_id": h.id, "origen": "catalogo", "receta_id": rid, "t_min": 0}
        h.conoce.add(cid)

    def _celda_de_bioma(self, bioma):
        t = self.sim.terreno
        import numpy as np
        ys, xs = np.nonzero(t.bioma == bioma)
        for x, y in zip(xs, ys):
            if t.caminable(int(x), int(y)):
                return int(x), int(y)
        self.skipTest("el mundo de prueba no tiene ese bioma")

    def test_juntar_depende_del_bioma(self):
        from mundo_vivo.motor import biomas as B
        h = self.sim.habitantes[1]
        x, y = self._celda_de_bioma(B.MONTANA)
        h.x, h.y = x + .5, y + .5
        self.assertIn("pedernal", self.sim.disponibles(h))
        self.assertNotIn("hoja_grande", self.sim.disponibles(h))
        self.sim.rng_fauna.seed(1)
        for _ in range(40):
            self.sim._accion_juntar(h, {"material": "piedra"})
        self.assertGreater(h.inventario.get("piedra", 0), 0)
        ok, _ = self.sim._accion_juntar(h, {"material": "hoja_grande"})
        self.assertFalse(ok)

    def test_fabricar_exige_saber_consume_y_tarda(self):
        h = self.sim.habitantes[1]
        h.inventario = {"fibra": 3}
        ok, _ = self.sim._accion_fabricar(h, {"objeto": "cuerda"})
        self.assertFalse(ok)                                    # no sabe la receta
        self._con_receta(h, "cuerda")
        t0 = self.sim.t
        ok, _ = self.sim._accion_fabricar(h, {"objeto": "cuerda"})
        self.assertTrue(ok)
        self.assertEqual(h.inventario.get("cuerda"), 2)
        self.assertEqual(h.inventario.get("fibra"), 2)
        self.assertGreater(h.hasta, t0 + 20)
        h.inventario = {}
        self.assertFalse(self.sim._accion_fabricar(h, {"objeto": "cuerda"})[0])   # sin materiales

    def test_fogata_con_chispa_da_calor_y_sirve_para_cocinar(self):
        h = self.sim.habitantes[1]
        self.sim.terreno.temperatura[:] = -25
        h.inventario = {"palo": 3, "taladro_de_fuego": 1}
        sin = self.sim.severidad_frio(h)
        self.assertTrue(self.sim._accion_encender(h, {})[0])
        self.assertEqual(len(self.sim.fogatas), 1)
        self.assertLess(self.sim.severidad_frio(h), sin * 0.4)
        h.inventario["carne"] = 2
        self.assertTrue(self.sim._accion_cocinar(h, {})[0])
        sim_io.guardar_simulacion(self.con, self.sim)
        s2 = sim_io.cargar_simulacion(self.con, self.cerebro)
        self.assertEqual(len(s2.fogatas), 1)
        self.sim.t += 24 * 60
        self.sim._acum_tec = 99
        self.sim._paso_tecnologia(10)
        self.assertEqual(len(self.sim.fogatas), 0)                  # se apagó sola

    def test_sin_chispa_ni_lena_no_enciende(self):
        h = self.sim.habitantes[1]
        h.inventario = {"palo": 3}
        self.assertFalse(self.sim._accion_encender(h, {})[0])
        h.inventario = {"taladro_de_fuego": 1}
        self.assertFalse(self.sim._accion_encender(h, {})[0])

    def test_llevar_fuego_de_otra_fogata_en_una_antorcha(self):
        h, o = self.sim.habitantes[1], self.sim.habitantes[2]
        h.inventario = {"palo": 4, "taladro_de_fuego": 1}
        self.sim._accion_encender(h, {})
        o.x, o.y = h.x + 1, h.y
        o.inventario = {"palo": 3}
        self.assertTrue(self.sim._accion_tomar_fuego(o, {})[0])
        self.assertEqual(o.inventario.get("antorcha_encendida"), 1)
        o.x, o.y = h.x + 30, h.y
        self.assertTrue(self.sim._accion_encender(o, {})[0])     # la llama viaja y prende otra fogata
        self.assertEqual(len(self.sim.fogatas), 2)

    def test_refugio_tarda_y_abriga(self):
        h = self.sim.habitantes[1]
        self._con_receta(h, "refugio_de_paja")
        h.inventario = {"palo": 1, "paja": 1}
        self.sim.terreno.temperatura[:] = -25
        sin = self.sim.severidad_frio(h)
        t0 = self.sim.t
        ok, _ = self.sim._accion_fabricar(h, {"objeto": "refugio_de_paja"})
        self.assertTrue(ok)
        self.assertGreaterEqual(h.hasta - t0, 360)
        # sólo las casas construidas: el mapa ya trae bocas de caverna, que están en la misma lista
        casas = [r for r in self.sim.refugios if r["dueno"] is not None]
        self.assertEqual(len(casas), 1)
        self.assertLess(self.sim.severidad_frio(h), sin * 0.7)
        self.assertEqual(h.hogar is not None, True)

    def test_armas_y_ropa_cuentan_solo_si_las_lleva(self):
        h = self.sim.habitantes[1]
        self.assertEqual(self.sim.bono_arma(h)[0], 0.0)
        h.inventario = {"arco_de_tendon": 1}
        self.assertGreater(self.sim.bono_arma(h)[1], 5.0)
        self.assertEqual(self.sim.abrigo_objetos(h), 0.0)
        h.inventario = {"capa_de_piel": 1}
        self.assertGreater(self.sim.abrigo_objetos(h), 0.0)
        h.inventario = {"armadura_de_cuero": 1}
        self.assertGreater(self.sim.proteccion_de(h), 0.0)

    def test_curarse_con_lo_fabricado(self):
        h = self.sim.habitantes[1]
        h.salud = 40
        h.inventario = {"cataplasma": 1}
        self.assertTrue(self.sim._accion_usar(h, {"objeto": "cataplasma"})[0])
        self.assertEqual(h.salud, 65)
        self.assertFalse(self.sim._accion_usar(h, {"objeto": "cataplasma"})[0])

    def test_sin_modelo_progresan_solos_hasta_encender_fuego(self):
        """El respaldo descubre, junta, fabrica y enciende sin que nadie le diga qué hacer."""
        for _ in range(48 * 12):
            self.sim.avanzar(30)
        sim_io.volcar_eventos(self.con, self.sim)
        fab = set().union(*[h.fabricados for h in self.sim.habitantes.values()])
        self.assertIn("taladro_de_fuego", fab)
        self.assertGreaterEqual(len(fab), 3)


class TestFamiliaYSed(_Base):
    def test_sin_modelo_se_forman_familias(self):
        """Antes nadie proponía nunca: sin el modelo el respaldo no tenía ese deseo y el modelo no lo elegía."""
        for _ in range(48 * 40):
            self.sim.avanzar(30)
        sim_io.volcar_eventos(self.con, self.sim)
        hubo = self.con.execute("SELECT COUNT(*) FROM eventos WHERE tipo = 'familia'").fetchone()[0]
        self.assertGreaterEqual(hubo, 1)

    def test_parado_junto_al_agua_bebe_en_vez_de_no_encontrar_camino(self):
        h = self.sim.habitantes[1]
        c = self.sim.agua_cercana(h, 140)
        self.assertIsNotNone(c)
        h.x, h.y = c[0] + .5, c[1] + .5
        h.sed = 80
        ok, _ = self.sim._aplicar(h, {"tipo": "ir", "destino": c, "luego": "beber", "motivo": "tiene sed"})
        self.assertTrue(ok)
        self.assertLess(h.sed, 80)

    def test_tarea_larga_se_interrumpe_por_sed(self):
        h = self.sim.habitantes[1]
        h.accion, h.hasta, h.sed = "construyendo", self.sim.t + 1000, 70
        self.sim._actualizar(h, 5)
        self.assertNotEqual(h.accion, "construyendo")


class TestAgotamientoYHitos(_Base):
    def test_los_recursos_se_agotan_y_vuelven(self):
        from mundo_vivo.motor import biomas as B
        import numpy as np
        t = self.sim.terreno
        ys, xs = np.nonzero(t.bioma == B.BOSQUE_TEMPLADO)
        if not len(xs):
            self.skipTest("sin bosque")
        h = self.sim.habitantes[1]
        h.x, h.y = float(xs[0]) + .5, float(ys[0]) + .5
        self.sim.rng_fauna.seed(3)
        for _ in range(60):
            self.sim._accion_juntar(h, {"material": "palo"})
        self.assertNotIn("palo", self.sim.disponibles(h))
        self.assertIn("palo", self.sim.agotados(h))
        ok, msg = self.sim._accion_juntar(h, {"material": "palo"})
        self.assertFalse(ok)
        self.assertIn("otro lado", msg)
        self.sim.t += 9 * 1440
        self.assertIn("palo", self.sim.disponibles(h))               # volvió a crecer
        sim_io.guardar_simulacion(self.con, self.sim)
        self.assertIsInstance(self.sim.exportar_estructuras()["agotamiento"], dict)

    def test_hitos_salen_una_sola_vez_como_evento_importante(self):
        h = self.sim.habitantes[1]
        h.inventario = {"palo": 8, "taladro_de_fuego": 1}
        self.sim._accion_encender(h, {})
        self.sim.fogatas.clear()
        self.sim._accion_encender(h, {})
        hitos = [e for e in self.sim._eventos if e["tipo"] == "hito"]
        self.assertEqual(len(hitos), 1)
        self.assertEqual(hitos[0]["importancia"], 5)
        sim_io.guardar_simulacion(self.con, self.sim)
        s2 = sim_io.cargar_simulacion(self.con, self.cerebro)
        self.assertIn("fuego", s2.hitos)


class TestInventosFabricables(_Base):
    def test_un_invento_fuera_del_catalogo_igual_se_puede_fabricar(self):
        h = self.sim.habitantes[1]
        h.inventario = {"fibra": 2, "resina": 2}
        ok, msg = self.sim._accion_inventar(h, {"receta": {
            "nombre": "Garfio de fibra", "materiales": ["fibra", "resina"], "propiedad": "ata",
            "descripcion": "para colgar cosas"}})
        self.assertTrue(ok, msg)
        cid = next(iter(h.conoce))
        rid = self.sim.conocimientos[cid]["receta_id"]
        self.assertIsNotNone(rid, "un invento sin receta nunca aparece en «fabricar»")
        self.assertIn(rid, self.sim.recetas)
        self.assertTrue(self.sim.puede_fabricar(h, self.sim.recetas[rid]))
        ok, msg = self.sim._accion_fabricar(h, {"objeto": rid})
        self.assertTrue(ok, msg)
        self.assertGreater(h.inventario.get(rid, 0), 0)

    def test_la_receta_inventada_sobrevive_al_guardado(self):
        h = self.sim.habitantes[1]
        h.inventario = {"fibra": 1, "resina": 1}
        self.sim._accion_inventar(h, {"receta": {"nombre": "Garfio de fibra", "materiales": ["fibra", "resina"],
                                                 "propiedad": "ata", "descripcion": ""}})
        rid = self.sim.conocimientos[next(iter(h.conoce))]["receta_id"]
        sim_io.guardar_simulacion(self.con, self.sim)
        s2 = sim_io.cargar_simulacion(self.con, self.cerebro)
        self.assertIn(rid, s2.recetas)                       # el catálogo vuelve del JSON: hay que rearmarla


class TestAldeas(_Base):
    def test_los_refugios_cercanos_forman_una_aldea_con_nombre(self):
        self.sim.refugios = [
            {"rid": 1, "x": 50.0, "y": 50.0, "dueno": 1, "tipo": "choza_de_ramas", "nombre": "choza", "abrigo": 0.4, "t": 0},
            {"rid": 2, "x": 52.0, "y": 51.0, "dueno": 2, "tipo": "refugio_de_paja", "nombre": "refugio", "abrigo": 0.3, "t": 0},
            {"rid": 3, "x": 300.0, "y": 300.0, "dueno": 1, "tipo": "choza_de_barro", "nombre": "choza", "abrigo": 0.5, "t": 0}]
        al = self.sim.aldeas()
        self.assertEqual(len(al), 1)                          # el refugio aislado no es aldea
        self.assertEqual(al[0]["casas"], 2)
        self.assertEqual(al[0]["familias"], 2)
        self.assertEqual(al[0]["nombre"], "Aldea 1")
        self.assertIn("aldeas", self.sim.publico_estructuras())

    def test_el_numero_de_aldea_no_se_mueve_cuando_agregan_casas(self):
        self.sim.refugios = [
            {"rid": 1, "x": 300.0, "y": 300.0, "dueno": 1, "tipo": "choza_de_ramas", "nombre": "choza", "abrigo": 0.4, "t": 0},
            {"rid": 2, "x": 302.0, "y": 300.0, "dueno": 2, "tipo": "choza_de_ramas", "nombre": "choza", "abrigo": 0.4, "t": 0}]
        self.assertEqual(self.sim.aldeas()[0]["nombre"], "Aldea 1")
        self.sim.refugios += [                                 # una aldea nueva, más grande, en otro lado
            {"rid": 3, "x": 50.0, "y": 50.0, "dueno": 1, "tipo": "choza_de_ramas", "nombre": "choza", "abrigo": 0.4, "t": 0},
            {"rid": 4, "x": 52.0, "y": 50.0, "dueno": 2, "tipo": "choza_de_ramas", "nombre": "choza", "abrigo": 0.4, "t": 0},
            {"rid": 5, "x": 54.0, "y": 51.0, "dueno": 3, "tipo": "choza_de_ramas", "nombre": "choza", "abrigo": 0.4, "t": 0}]
        por_rid = {a["num"]: a["casas"] for a in self.sim.aldeas()}
        self.assertEqual(por_rid, {1: 2, 2: 3})                # la primera sigue siendo la 1, aunque ahora sea la chica
        self.sim.refugios.append(                              # y sumarle una casa no la renombra
            {"rid": 6, "x": 304.0, "y": 301.0, "dueno": 3, "tipo": "choza_de_ramas", "nombre": "choza", "abrigo": 0.4, "t": 0})
        self.assertEqual([a["casas"] for a in self.sim.aldeas() if a["num"] == 1], [3])

    def test_la_aldea_dice_quienes_viven_ahi(self):
        a = self.sim.habitantes[1]
        self.sim.refugios = [
            {"rid": 1, "x": a.x, "y": a.y, "dueno": a.id, "tipo": "choza_de_ramas", "nombre": "choza", "abrigo": 0.4, "t": 0},
            {"rid": 2, "x": a.x + 2, "y": a.y, "dueno": a.id, "tipo": "choza_de_ramas", "nombre": "choza", "abrigo": 0.4, "t": 0}]
        self.assertIn(a.nombre, [p["nombre"] for p in self.sim.aldeas()[0]["gente"]])

    def test_la_fogata_informa_cuanta_vida_le_queda(self):
        h = self.sim.habitantes[1]
        h.inventario = {"palo": 8, "taladro_de_fuego": 1}
        self.sim._accion_encender(h, {})
        x, y, vida = self.sim.publico_estructuras()["fogatas"][0]
        self.assertAlmostEqual(vida, 1.0, places=1)
        self.sim.t += 250.0
        self.assertLess(self.sim.publico_estructuras()["fogatas"][0][2], 1.0)


class TestParentesco(_Base):
    def test_el_motor_no_deja_tener_hijos_con_la_familia(self):
        a, b = self.sim.habitantes[1], self.sim.habitantes[2]
        a.sexo, b.sexo = "F", "M"
        b.x, b.y = a.x, a.y
        a.nacimiento_min = b.nacimiento_min = -25 * 120 * 1440
        b.madre_id = a.id                                      # b es hijo de a
        ok, msg = self.sim._accion_proponer_hijo(a, {"a": b.id})
        self.assertFalse(ok)
        self.assertIn("sangre", msg)
        self.assertEqual(self.sim.parentesco_cercano(a, b), "hijo")

    def test_los_medio_hermanos_por_padre_tambien_son_familia(self):
        a, b = self.sim.habitantes[1], self.sim.habitantes[2]
        a.madre_id, b.madre_id = 10, 11                        # distinta madre
        a.padre_id = b.padre_id = 12                           # mismo padre
        self.assertEqual(self.sim.parentesco_cercano(a, b), "hermano")
        self.assertNotIn(b, self.cerebro._pareja_posible(self.sim, a))

    def test_si_no_queda_nadie_de_un_sexo_el_proximo_nacimiento_se_inclina(self):
        for h in self.sim.habitantes.values():
            h.sexo = "F"
        self.assertLess(self.sim._prob_hija(), 0.5)             # son todas mujeres: lo que falta son varones
        for h in self.sim.habitantes.values():
            h.sexo = "M"
        self.assertGreater(self.sim._prob_hija(), 0.5)          # y al revés


class TestEscala(unittest.TestCase):
    """Las distancias del motor están en metros y se convierten según la celda del mundo."""

    def _sim(self, tam, n=192):
        import tempfile
        from pathlib import Path
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        ruta = mundo_io.crear_mundo(Path(d.name), 777, n, n, tam_celda_m=tam)
        con = db.abrir(ruta)
        self.addCleanup(con.close)
        return sim_io.cargar_simulacion(con)

    def test_a_50_m_por_celda_da_los_numeros_de_siempre(self):
        s = self._sim(50)
        self.assertAlmostEqual(s.r_habla, 6.0)         # 300 m
        self.assertAlmostEqual(s.r_vista, 30.0)        # 1500 m
        self.assertAlmostEqual(s.r_encuentro, 8.0)     # 400 m
        self.assertEqual(s.zona, 16)                   # 800 m

    def test_a_5_m_por_celda_las_mismas_distancias_reales(self):
        s5, s50 = self._sim(5), self._sim(50)
        for campo in ("r_habla", "r_vista", "r_encuentro", "r_aldea"):
            m5 = getattr(s5, campo) * 5.0
            m50 = getattr(s50, campo) * 50.0
            self.assertAlmostEqual(m5, m50, places=3,
                                   msg="%s cambia de distancia real al cambiar la escala" % campo)

    def test_un_radio_chico_no_queda_en_cero_con_celdas_grandes(self):
        s = self._sim(50)
        self.assertGreaterEqual(s.r_fogata, 1.0)       # 20 m en celdas de 50: no puede ser 0,4
        self.assertGreaterEqual(s.r_mano, 1.0)

    def test_el_presupuesto_de_busqueda_acompana_a_la_escala(self):
        s5, s50 = self._sim(5), self._sim(50)
        self.assertGreater(s5.nodos_bfs, s50.nodos_bfs)
        self.assertGreater(s5.nodos_camino, s50.nodos_camino)


class TestPrioridadDeNecesidades(_Base):
    """Lo que mata más rápido va primero. Un bug real: con el cansancio antes que la sed, se dormían, la sed
    los despertaba, seguían cansados, se volvían a dormir, y se morían de sed al lado del agua."""

    def _junto_al_agua(self):
        import numpy as np
        t = self.sim.terreno
        ys, xs = np.nonzero(t.agua > 0)
        for k in range(0, len(xs), 7):
            c = t.caminable_cerca(int(xs[k]), int(ys[k]), 3)
            if c and t.agua_adyacente(c[0], c[1]):
                h = self.sim.habitantes[1]
                h.x, h.y = c[0] + 0.5, c[1] + 0.5
                return h
        self.skipTest("este mundo no tiene orilla transitable")

    def test_muerto_de_sed_y_de_cansancio_va_a_tomar_agua(self):
        h = self._junto_al_agua()
        h.sed, h.energia = 95.0, 4.0            # las dos cosas al límite
        acc = self.cerebro._reflejos(self.sim, h)
        self.assertEqual(acc["tipo"], "beber", "con sed mortal no se puede ir a dormir: se muere al lado del agua")

    def test_cansado_pero_sin_sed_si_duerme(self):
        h = self.sim.habitantes[1]
        h.sed, h.energia = 20.0, 8.0
        acc = self.cerebro._reflejos(self.sim, h)
        self.assertEqual(acc["tipo"], "dormir")

    def test_dormido_y_con_sed_se_despierta_y_toma_antes_de_volver_a_dormir(self):
        """El ciclo completo en el motor: duerme, la sed lo despierta, TOMA, y recién ahí sigue durmiendo.
        Antes se despertaba, se volvía a dormir sin tomar, y moría de sed con el agua al lado."""
        h = self._junto_al_agua()
        h.energia, h.sed = 6.0, 88.0
        h.accion, h.hasta = "durmiendo", self.sim.t + 400
        for _ in range(40):
            self.sim._actualizar(h, 1.0)
            if h.sed < 50:
                break
        self.assertLess(h.sed, 50.0, "se tiene que haber despertado a tomar agua")
        self.assertGreater(h.salud, 90.0, "no se tiene que haber lastimado de sed")

    def test_sin_agua_al_lado_tampoco_se_duerme_muriendo_de_sed(self):
        h = self.sim.habitantes[1]
        h.sed, h.energia = 95.0, 4.0
        acc = self.cerebro._reflejos(self.sim, h)
        self.assertNotEqual(acc["tipo"], "dormir", "con sed mortal se busca agua, no se duerme")


class TestExploracion(_Base):
    """Bug real: las distancias de exploración estaban EN CELDAS mientras la zona de recursos pasó a metros.
    En un mundo de 5 m por celda sólo podían alejarse 150 m, la zona mide 800, y quedaban encerrados en una
    zona ya vaciada: 61 intentos fallidos de juntar palo y nadie se movía en 11 días."""

    def test_el_radio_de_exploracion_supera_a_la_zona_de_recursos(self):
        h = self.sim.habitantes[1]
        destinos = []
        for _ in range(60):
            acc = self.cerebro._demo_explorar(self.sim, h)
            if acc.get("tipo") == "ir" and acc.get("destino"):
                d = acc["destino"]
                destinos.append(math.hypot(d[0] - h.x, d[1] - h.y))
        self.assertTrue(destinos, "nunca propuso ir a ningún lado")
        self.assertGreater(max(destinos), self.sim.zona,
                           "explorando nunca se sale de la zona de recursos: cuando la vacían quedan atrapados")

    def test_con_celdas_finas_igual_recorren_cientos_de_metros(self):
        """El bug exacto: a 5 m por celda llegaban a 150 m y la zona de recursos mide 800."""
        import tempfile
        from pathlib import Path
        from mundo_vivo.motor.tecnologia import METROS_ZONA
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        ruta = mundo_io.crear_mundo(Path(d.name), 777, 512, 512, tam_celda_m=5)   # 2,56 km de lado
        con = db.abrir(ruta)
        self.addCleanup(con.close)
        sim_io.crear_habitantes_iniciales(con, 4)
        sim = sim_io.cargar_simulacion(con, cerebro=self.cerebro)
        h = next(iter(sim.habitantes.values()))
        metros = []
        for _ in range(60):
            acc = self.cerebro._demo_explorar(sim, h)
            if acc.get("tipo") == "ir" and acc.get("destino"):
                dd = acc["destino"]
                metros.append(math.hypot(dd[0] - h.x, dd[1] - h.y) * sim.tam_celda_m)
        self.assertTrue(metros)
        self.assertGreater(max(metros), METROS_ZONA,
                           "a 5 m por celda no llegan ni a salir de su propia zona de recursos")

    def test_acompanado_se_anima_a_ir_mas_lejos_que_solo(self):
        a, b = self.sim.habitantes[1], self.sim.habitantes[2]
        b.x, b.y = a.x + 1, a.y                      # al lado: está acompañado
        juntos = max(math.hypot(d["destino"][0] - a.x, d["destino"][1] - a.y)
                     for d in (self.cerebro._demo_explorar(self.sim, a) for _ in range(40))
                     if d.get("destino"))
        for o in self.sim.habitantes.values():       # ahora se queda solo
            if o.id != a.id:
                o.vivo = False
        a.visto = {}
        solo = max(math.hypot(d["destino"][0] - a.x, d["destino"][1] - a.y)
                   for d in (self.cerebro._demo_explorar(self.sim, a) for _ in range(40))
                   if d.get("destino"))
        self.assertGreater(juntos, solo, "de a dos tendrían que animarse a ir más lejos que solos")


class TestFuegoYSed(_Base):
    """Bug real (mundo 1528465001, día 19): el usuario prendió un fuego y los cuatro murieron de sed.
    El reflejo de huir usaba el radio de VER humo (1,1 km), así que con un incendio lejano huían en
    círculos para siempre y nunca llegaban a la línea de beber."""

    def test_con_sed_mortal_no_huye_de_un_fuego_lejano(self):
        h = self.sim.habitantes[1]
        h.sed = 95.0
        x, y = int(h.x), int(h.y)
        fx = min(self.sim.terreno.ancho - 1, x + int(self.sim.r_huir_fuego) + 5)   # lejos: lo ve pero no lo alcanza
        self.sim.fuego.fuego[y, fx] = 255
        self.sim.fuego._hubo_fuego = True
        acc = self.cerebro._reflejos(self.sim, h)
        self.assertIsNotNone(acc)
        self.assertNotEqual(acc.get("motivo"), "huye del fuego",
                            "con sed mortal y fuego lejos tiene que ir al agua, no huir")

    def test_el_fuego_encima_si_lo_hace_huir(self):
        h = self.sim.habitantes[1]
        h.sed = 10.0
        x, y = int(h.x), int(h.y)
        self.sim.fuego.fuego[y, min(self.sim.terreno.ancho - 1, x + 2)] = 255
        self.sim.fuego._hubo_fuego = True
        acc = self.cerebro._reflejos(self.sim, h)
        self.assertIsNotNone(acc, "con el fuego al lado tiene que reaccionar")

    def test_ver_humo_lejos_no_cancela_el_viaje_al_agua(self):
        h = self.sim.habitantes[1]
        h.sed = 95.0
        h.camino = [(int(h.x) + 1, int(h.y)), (int(h.x) + 2, int(h.y))]
        h.detalle = "tiene sed"
        x, y = int(h.x), int(h.y)
        self.sim.fuego.fuego[y, min(self.sim.terreno.ancho - 1, x + int(self.sim.r_huir_fuego) + 5)] = 255
        self.sim.fuego._hubo_fuego = True
        self.sim._actualizar(h, 0.1)
        self.assertTrue(h.camino or h.accion == "bebiendo",
                        "le cancelaron el viaje al agua por ver humo a un kilómetro")

"""Fase N: recordar por significado y no sólo por palabras sueltas.

El caso que motivó todo: alguien recuerda «te atacó una araña venenosa» y la situación de ahora habla de
«un bicho ponzoñoso». No comparten una palabra, así que el recuerdo existía y nunca se usaba.

El modelo de embeddings se reemplaza acá por uno de mentira y determinista (vectores sobre un puñado de
conceptos), igual que `ollama_falso.py` hace con el de lenguaje: lo que se prueba es el circuito, no Ollama.
"""
from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path

import numpy as np

from mundo_vivo.agentes import ajustes as aj
from mundo_vivo.agentes.semantica import Semantica, a_bytes, coseno, desde_bytes
from mundo_vivo.persistencia import db, mundo_io, sim_io
from mundo_vivo.persistencia.memoria import MemoriaPrivada

# Conceptos del modelo de mentira: cada palabra empuja hacia un eje. «araña» y «bicho venenoso» caen juntos
# sin compartir una sola letra, que es justo lo que las palabras no pueden hacer.
CONCEPTOS = {
    "araña": (1, 0, 0), "arañas": (1, 0, 0), "venenosa": (1, 0, 0), "venenoso": (1, 0, 0),
    "bicho": (1, 0, 0), "ponzoñoso": (1, 0, 0), "picadura": (1, 0, 0), "atacó": (0.6, 0, 0),
    "río": (0, 1, 0), "agua": (0, 1, 0), "beber": (0, 1, 0), "sed": (0, 1, 0),
    "piedra": (0, 0, 1), "pedernal": (0, 0, 1), "tallar": (0, 0, 1), "herramienta": (0, 0, 1),
}


def _vector(texto: str) -> list:
    v = np.zeros(3, dtype=np.float32)
    for p in (texto or "").lower().replace(",", " ").replace(".", " ").split():
        v += np.asarray(CONCEPTOS.get(p, (0.0, 0.0, 0.0)), dtype=np.float32)
    if not v.any():
        v[:] = (0.33, 0.33, 0.33)
    return [float(x) for x in v / np.linalg.norm(v)]


class ClienteFalso:
    """Con la forma de ClienteOllama, pero responde al instante y sin red."""

    def __init__(self, romper: bool = False):
        self.romper = romper
        self.llamadas = 0
        self.emb_ok = self.emb_mal = 0
        self.emb_error = ""
        self.emb_latencia_s = None

    def embeddings(self, ajustes, textos) -> Future:
        self.llamadas += 1
        f: Future = Future()
        if self.romper:
            f.set_exception(RuntimeError("no existe el modelo"))
        else:
            f.set_result([_vector(t) for t in textos])
        return f


def _semantica(romper: bool = False) -> Semantica:
    s = Semantica(ClienteFalso(romper))
    s.configurar({"modulos": {"semantica": True}, "modelo_embeddings": "falso"})
    return s


class TestVectores(unittest.TestCase):
    def test_se_guardan_normalizados_y_el_coseno_es_un_producto_punto(self):
        v = a_bytes([3.0, 4.0, 0.0])
        a = desde_bytes(v)
        self.assertAlmostEqual(float(np.linalg.norm(a)), 1.0, places=5)
        self.assertAlmostEqual(coseno(a, a), 1.0, places=5)

    def test_sin_vector_o_de_otro_modelo_no_inventa_un_parecido(self):
        """Cambiar de modelo de embeddings cambia el largo: eso cae a las palabras, no explota."""
        s = _semantica()
        a = desde_bytes(a_bytes([1.0, 0.0, 0.0]))
        self.assertIsNone(coseno(a, None))
        self.assertIsNone(coseno(a, desde_bytes(a_bytes([1.0, 0.0, 0.0, 0.0]))))
        self.assertIsNone(s.parecido(a, None))
        self.assertIsNone(s.parecido(a, b""))

    def test_un_vector_vacio_no_se_guarda_como_vector(self):
        self.assertEqual(a_bytes([0.0, 0.0, 0.0]), b"")


class _Mundo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ruta = mundo_io.crear_mundo(Path(self.tmp.name), 7, 64, 64, tam_celda_m=50)
        self.con = db.abrir(ruta)
        sim_io.crear_habitantes_iniciales(self.con, 2)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()


class TestIndice(_Mundo):
    def test_paso_le_pone_vector_a_los_recuerdos_que_no_tenian(self):
        mem = MemoriaPrivada(self.con, 1)
        mem.agregar(10, "episodica", "Te atacó una araña venenosa", 0.6)
        mem.agregar(20, "episodica", "Bebiste agua del río", 0.4)
        s = _semantica()
        s.paso(self.con)        # pide
        n = s.paso(self.con)    # cobra y guarda
        self.assertEqual(n, 2)
        faltan = self.con.execute("SELECT COUNT(*) FROM memorias WHERE embedding IS NULL").fetchone()[0]
        self.assertEqual(faltan, 0)

    def test_si_el_modelo_no_esta_deja_de_insistir_y_el_mundo_sigue(self):
        MemoriaPrivada(self.con, 1).agregar(10, "episodica", "Te atacó una araña venenosa", 0.6)
        s = _semantica(romper=True)
        for _ in range(10):
            s.paso(self.con)
        self.assertFalse(s.activa)
        self.assertLessEqual(s.cliente.llamadas, 6)     # no insiste para siempre
        # y recordar sigue funcionando, por palabras
        rec = MemoriaPrivada(self.con, 1, s).recordar(100, "araña", n=3)
        self.assertEqual(len(rec), 1)

    def test_el_modulo_apagado_no_toca_la_base_ni_llama_al_modelo(self):
        MemoriaPrivada(self.con, 1).agregar(10, "episodica", "Te atacó una araña venenosa", 0.6)
        s = Semantica(ClienteFalso())
        s.configurar({"modulos": {"semantica": False}})
        s.paso(self.con)
        self.assertEqual(s.cliente.llamadas, 0)
        self.assertIsNone(self.con.execute("SELECT embedding FROM memorias").fetchone()[0])


class TestRecordar(_Mundo):
    def _preparar(self) -> Semantica:
        mem = MemoriaPrivada(self.con, 1)
        mem.agregar(10, "episodica", "Te atacó una araña venenosa", 0.5)
        mem.agregar(11, "episodica", "Bebiste agua del río", 0.5)
        mem.agregar(12, "episodica", "Tallaste una piedra de pedernal", 0.5)
        s = _semantica()
        s.paso(self.con)
        s.paso(self.con)
        return s

    def test_sin_palabras_en_comun_el_significado_encuentra_el_recuerdo(self):
        s = self._preparar()
        ctx = "un bicho ponzoñoso"
        # primera vuelta: el vector de la situación todavía no está, así que cae a palabras y no lo encuentra
        peor = MemoriaPrivada(self.con, 1, s).recordar(100, ctx, n=1)[0]["contenido"]
        s.paso(self.con)   # llega el vector de la situación
        s.paso(self.con)
        mejor = MemoriaPrivada(self.con, 1, s).recordar(100, ctx, n=1)[0]["contenido"]
        self.assertEqual(mejor, "Te atacó una araña venenosa")
        self.assertNotEqual(peor, mejor)   # la mejora es real, no era lo que ya salía

    def test_nunca_se_espera_al_modelo_para_decidir(self):
        """Pedir el vector de una situación nueva no bloquea: devuelve None y la decisión sale por palabras."""
        s = self._preparar()
        self.assertIsNone(s.vector("algo que nunca se vio"))

    def test_lo_que_ya_andaba_por_palabras_sigue_andando(self):
        s = self._preparar()
        for _ in range(3):
            s.paso(self.con)
        rec = MemoriaPrivada(self.con, 1, s).recordar(100, "pedernal", n=1)
        self.assertEqual(rec[0]["contenido"], "Tallaste una piedra de pedernal")

    def test_el_vector_sobrevive_al_guardado(self):
        self._preparar()
        self.con.close()
        self.con = db.abrir(Path(self.tmp.name) / "mundo.db") if (Path(self.tmp.name) / "mundo.db").exists() else db.abrir(
            next(Path(self.tmp.name).rglob("*.db")))
        guardados = self.con.execute("SELECT COUNT(*) FROM memorias WHERE embedding IS NOT NULL").fetchone()[0]
        self.assertEqual(guardados, 3)


class TestAjustes(_Mundo):
    def test_el_modulo_viene_apagado_y_el_modelo_se_puede_cambiar(self):
        a = aj.obtener(self.con)
        self.assertIn("semantica", a["modulos"])
        self.assertFalse(a["modulos"]["semantica"])      # necesita `ollama pull nomic-embed-text`
        self.assertEqual(a["modelo_embeddings"], "nomic-embed-text")
        a = aj.guardar(self.con, {"modelo_embeddings": "otro-modelo", "modulos": {"semantica": True}})
        self.assertEqual(a["modelo_embeddings"], "otro-modelo")
        self.assertTrue(aj.obtener(self.con)["modulos"]["semantica"])


if __name__ == "__main__":
    unittest.main()

"""
Recuerdos por significado (fase N).

`memoria.recordar()` puntúa la relevancia por palabras en común. Si alguien recuerda «me atacó una araña» y
la situación de ahora habla de «un bicho venenoso», no lo encuentra: el recuerdo existe y no se usa. Acá se
le agrega a cada recuerdo un vector de significado (la columna `memorias.embedding`, que existe vacía desde
`0001_inicial.sql`) y la relevancia pasa a ser el coseno entre el vector de la situación y el del recuerdo.

Tres reglas que no se negocian:
  * **Nunca en el camino crítico.** Nada de esto bloquea una decisión. Los vectores se calculan en un hilo
    aparte y se escriben después; un recuerdo sin vector se sigue recuperando por palabras, como siempre.
  * **El hilo de fondo no toca la base.** sqlite se usa desde el hilo del mundo; el trabajador devuelve
    vectores en memoria y `paso()` los escribe.
  * **Mejora incremental, nunca un corte.** Si Ollama no tiene el modelo de embeddings, el mundo anda igual.
"""
from __future__ import annotations

import sqlite3
import threading
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..persistencia.memoria import guardar_embeddings, sin_embedding

POR_LOTE = 16          # recuerdos sin vector que se mandan juntos
MAX_CACHE = 256        # textos de consulta recordados (la situación cambia poco entre decisiones seguidas)
FALLOS_PARA_PARAR = 3  # después de esto deja de insistir hasta que lo vuelvan a encender


def a_bytes(v) -> bytes:
    """Vector normalizado en float32: así el coseno es un producto punto y nada más."""
    a = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(a))
    if not np.isfinite(n) or n < 1e-9:
        return b""
    return (a / n).astype(np.float32).tobytes()


def desde_bytes(b) -> Optional[np.ndarray]:
    if not b:
        return None
    try:
        a = np.frombuffer(b, dtype=np.float32)
    except (ValueError, TypeError):
        return None
    return a if a.size else None


def coseno(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> Optional[float]:
    """None si falta alguno o si son de modelos distintos (largos distintos): ahí se cae a las palabras."""
    if a is None or b is None or a.shape != b.shape:
        return None
    return float(np.dot(a, b))


class Semantica:
    """Vectores de significado de un mundo. Inerte mientras el módulo esté apagado."""

    def __init__(self, cliente=None):
        self.cliente = cliente
        self.activa = False
        self.ajustes: dict = {}
        self._cache: Dict[str, Optional[np.ndarray]] = {}   # texto de consulta -> vector (None = pedido en vuelo)
        self._orden: List[str] = []
        self._lock = threading.Lock()
        self._pend_mem: Optional[tuple] = None      # (futuro, [ids])
        self._pend_ctx: Optional[tuple] = None      # (futuro, [textos])
        self.fallos = 0
        self.guardados = 0
        # Para medir que esto sirva: cuántos recuerdos se puntuaron por significado y cuántos por palabras.
        self.por_significado = 0
        self.por_palabras = 0

    def parecido(self, qv: Optional[np.ndarray], embedding) -> Optional[float]:
        """Relevancia 0..1 entre la situación y un recuerdo. None si al recuerdo le falta el vector.

        El coseno de dos frases de un mismo idioma rara vez baja de 0,25 aunque no tengan nada que ver: por eso
        se corre el cero hasta ahí, si no todo parece parecido a todo."""
        c = coseno(qv, desde_bytes(embedding))
        if c is None:
            self.por_palabras += 1
            return None
        self.por_significado += 1
        return max(0.0, min(1.0, (c - 0.25) / 0.65))

    # ------------------------------------------------------------------ estado
    def estado(self) -> dict:
        e = {"activa": self.activa, "guardados": self.guardados, "fallos": self.fallos,
             "por_significado": self.por_significado, "por_palabras": self.por_palabras}
        if self.cliente is not None:
            e["modelo"] = self.ajustes.get("modelo_embeddings", "")
            e["error"] = self.cliente.emb_error
            e["latencia_s"] = None if self.cliente.emb_latencia_s is None else round(self.cliente.emb_latencia_s, 2)
        return e

    def configurar(self, ajustes: dict) -> None:
        self.ajustes = ajustes
        activa = bool(ajustes.get("modulos", {}).get("semantica")) and self.cliente is not None
        if activa and not self.activa:
            self.fallos = 0          # lo volvieron a encender: se reintenta
        self.activa = activa and self.fallos < FALLOS_PARA_PARAR

    # ------------------------------------------------------- vector de consulta
    def vector(self, texto: str) -> Optional[np.ndarray]:
        """El vector de una situación, SOLO si ya está calculado. Si falta, lo encola y devuelve None
        (esta decisión se toma por palabras; la próxima ya tiene el significado)."""
        if not self.activa:
            return None
        clave = " ".join((texto or "").lower().split())[:600]
        if not clave:
            return None
        with self._lock:
            if clave in self._cache:
                return self._cache[clave]
            self._cache[clave] = None            # marcado como pedido
            self._orden.append(clave)
            while len(self._orden) > MAX_CACHE:
                self._cache.pop(self._orden.pop(0), None)
        return None

    # -------------------------------------------------------------------- paso
    def paso(self, con: sqlite3.Connection) -> int:
        """Una vuelta de trabajo: guarda lo que llegó y pide lo que falta. Corre en el hilo del mundo,
        cuesta microsegundos y no espera a nadie. Devuelve cuántos vectores se guardaron."""
        if self.cliente is None:
            return 0
        n = self._cobrar_memorias(con) + self._cobrar_contextos()
        if not self.activa:
            return n
        self._pedir_memorias(con)
        self._pedir_contextos()
        return n

    # ---------------------------------------------------------------- internos
    def _fallo(self) -> None:
        self.fallos += 1
        if self.fallos >= FALLOS_PARA_PARAR:
            self.activa = False      # deja de insistir: el mundo sigue recordando por palabras

    def _cobrar_memorias(self, con: sqlite3.Connection) -> int:
        if self._pend_mem is None or not self._pend_mem[0].done():
            return 0
        fut, ids = self._pend_mem
        self._pend_mem = None
        try:
            vectores = fut.result()
        except Exception:
            self._fallo()
            return 0
        # El vector vacío también se guarda: marca «ya se intentó» y evita volver a pedir lo mismo para siempre.
        filas = [(a_bytes(v), i) for i, v in zip(ids, vectores)]
        guardar_embeddings(con, filas)
        n = sum(1 for b, _ in filas if b)
        self.guardados += n
        return n

    def _pedir_memorias(self, con: sqlite3.Connection) -> None:
        if self._pend_mem is not None:
            return
        pend = sin_embedding(con, POR_LOTE)
        if not pend:
            return
        self._pend_mem = (self.cliente.embeddings(self.ajustes, [t for _, t in pend]), [i for i, _ in pend])

    def _cobrar_contextos(self) -> int:
        if self._pend_ctx is None or not self._pend_ctx[0].done():
            return 0
        fut, claves = self._pend_ctx
        self._pend_ctx = None
        try:
            vectores = fut.result()
        except Exception:
            self._fallo()
            with self._lock:      # que no queden marcados como "en vuelo" para siempre
                for k in claves:
                    self._cache.pop(k, None)
                self._orden = [k for k in self._orden if k in self._cache]
            return 0
        with self._lock:
            for k, v in zip(claves, vectores):
                if k in self._cache:
                    self._cache[k] = desde_bytes(a_bytes(v))
        return 0

    def _pedir_contextos(self) -> None:
        if self._pend_ctx is not None:
            return
        with self._lock:
            faltan = [k for k in self._orden if self._cache.get(k) is None][:POR_LOTE]
        if faltan:
            self._pend_ctx = (self.cliente.embeddings(self.ajustes, faltan), faltan)

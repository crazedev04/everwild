"""Cliente de Ollama que trabaja en un hilo aparte (el mundo nunca se congela esperando al modelo)."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, Optional


class ErrorOllama(Exception):
    pass


class ClienteOllama:
    def __init__(self):
        self._tam = 1
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ollama")
        self._lock = threading.Lock()
        self.fallos_seguidos = 0
        self.bloqueado_hasta = 0.0
        self.ultimo_error = ""
        self.ultima_latencia_s: Optional[float] = None
        self.llamadas_ok = 0
        self.llamadas_mal = 0
        self._pool_emb: Optional[ThreadPoolExecutor] = None   # embeddings: hilo aparte del de decidir
        self.emb_ok = 0
        self.emb_mal = 0
        self.emb_error = ""
        self.emb_latencia_s: Optional[float] = None

    def disponible(self) -> bool:
        return time.time() >= self.bloqueado_hasta

    def estado(self) -> dict:
        return {
            "disponible": self.disponible(),
            "ultimo_error": self.ultimo_error,
            "latencia_s": None
            if self.ultima_latencia_s is None
            else round(self.ultima_latencia_s, 1),
            "ok": self.llamadas_ok,
            "mal": self.llamadas_mal,
        }

    def pedir(
        self,
        ajustes: Dict[str, Any],
        system: str,
        user: str,
        esquema: dict,
        semilla: int = 0,
    ) -> Future:
        n = max(1, min(4, int(ajustes.get("paralelo", 1) or 1)))
        if (
            n != self._tam
        ):  # cambió el paralelismo desde el panel: pool nuevo, el viejo termina lo suyo
            viejo, self._tam = self._pool, n
            self._pool = ThreadPoolExecutor(max_workers=n, thread_name_prefix="ollama")
            viejo.shutdown(wait=False)
        fut = self._pool.submit(
            self._llamar, dict(ajustes), system, user, esquema, semilla
        )
        fut.t0 = time.time()  # type: ignore[attr-defined]
        return fut

    def apagar(self) -> None:
        """Corta los dos pools (decisiones y embeddings) al cerrar un mundo."""
        self._pool.shutdown(wait=False, cancel_futures=True)
        if self._pool_emb is not None:
            self._pool_emb.shutdown(wait=False, cancel_futures=True)

    def embeddings(self, ajustes: Dict[str, Any], textos) -> Future:
        """Vectores de significado, en un hilo propio y aparte del de las decisiones.

        Va a un pool separado a propósito: el modelo de lenguaje es el cuello de botella del mundo y
        esto NUNCA puede meterse en el camino crítico de una decisión."""
        if self._pool_emb is None:
            self._pool_emb = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ollama-emb")
        fut = self._pool_emb.submit(self._embeddings, dict(ajustes), [str(t) for t in textos])
        fut.t0 = time.time()  # type: ignore[attr-defined]
        return fut

    def _embeddings(self, aj: dict, textos) -> list:
        host = aj["host"].rstrip("/")
        modelo = aj.get("modelo_embeddings") or "nomic-embed-text"
        t0 = time.time()
        try:
            try:
                r = self._post(host + "/api/embed", {"model": modelo, "input": textos},
                               aj.get("timeout_s", 180))
                vectores = r.get("embeddings") or []
            except ErrorOllama:
                # Ollama viejo: una llamada por texto contra el endpoint anterior
                vectores = [self._post(host + "/api/embeddings", {"model": modelo, "prompt": t},
                                       aj.get("timeout_s", 180)).get("embedding") or [] for t in textos]
        except Exception as e:
            with self._lock:
                self.emb_mal += 1
                self.emb_error = str(e)[:200]
            raise
        with self._lock:
            self.emb_ok += len(vectores)
            self.emb_error = ""
            self.emb_latencia_s = time.time() - t0
        return vectores

    def _post(self, url: str, cuerpo: dict, timeout: float) -> dict:
        req = urllib.request.Request(
            url,
            data=json.dumps(cuerpo).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise ErrorOllama(
                "HTTP %s: %s" % (e.code, e.read().decode(errors="replace")[:200])
            )
        except (urllib.error.URLError, OSError) as e:
            raise ErrorOllama(
                "No se pudo conectar con Ollama: %s" % getattr(e, "reason", e)
            )

    def _llamar(
        self, aj: dict, system: str, user: str, esquema: dict, semilla: int
    ) -> dict:
        cuerpo = {
            "model": aj["modelo"],
            "stream": False,
            "think": bool(aj.get("razonar", True)),
            "format": esquema,
            "keep_alive": "30m",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": aj["temperatura"],
                "num_ctx": aj["num_ctx"],
                "num_predict": int(aj.get("max_tokens", 1200)),
                "seed": semilla,
            },
        }
        t0 = time.time()
        try:
            try:
                r = self._post(
                    aj["host"].rstrip("/") + "/api/chat", cuerpo, aj["timeout_s"]
                )
            except ErrorOllama as e:
                if "think" in str(e).lower():
                    cuerpo.pop("think")
                    r = self._post(
                        aj["host"].rstrip("/") + "/api/chat", cuerpo, aj["timeout_s"]
                    )
                else:
                    raise
        except Exception as e:
            with self._lock:
                self.fallos_seguidos += 1
                self.llamadas_mal += 1
                self.ultimo_error = str(e)[:200]
                if (
                    self.fallos_seguidos >= 3
                ):  # deja de insistir un rato: el mundo sigue con reglas simples
                    self.bloqueado_hasta = time.time() + 120
            raise
        with self._lock:
            self.fallos_seguidos = 0
            self.llamadas_ok += 1
            self.ultima_latencia_s = time.time() - t0
            self.ultimo_error = ""
        return {
            "texto": (r.get("message") or {}).get("content", ""),
            "latencia_s": time.time() - t0,
        }


def extraer_json(texto: str) -> Optional[dict]:
    txt = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S).strip()
    if not txt:
        return None
    try:
        d = json.loads(txt)
    except ValueError:
        m = re.search(r"\{.*\}", txt, flags=re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except ValueError:
            return None
    return d if isinstance(d, dict) else None

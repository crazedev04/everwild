"""Heartbeat operativo para Mundo Vivo en modalidad cognitiva remota (CCA).

Complementa el ``Latido`` general de ``diagnostico`` (métricas del mundo cada
60s) con un latido específico de la CONEXIÓN cognitiva remota cada ~15s, para
poder responder sin adivinar: ¿el mundo sigue vivo pero dejó de hablar con CE?,
¿los habitantes están "pensando" y desde cuándo?, ¿las propuestas llegan y se
ejecutan?, ¿los resultados/ACK vuelven?

Distingue explícitamente:
- mundo y simulación activos (tick, velocidad),
- modalidad cognitiva efectiva (remota/local),
- estado de la conexión con CE y antigüedad de la última comunicación exitosa,
- habitantes con propuesta pendiente ("pensando") y desde qué tick,
- observaciones enviadas, propuestas recibidas/ejecutadas, resultados y ACK.

Nunca registra tokens ni credenciales.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

logger = logging.getLogger("mundo_vivo.heartbeat")


class RemoteHeartbeat:
    """Hilo daemon que registra el estado de la cognición remota en un intervalo."""

    def __init__(
        self,
        *,
        brain: Any,
        sim: Any,
        world_name: str | None = None,
        interval_s: float = 15.0,
        stale_comm_after_s: float = 60.0,
    ) -> None:
        self.brain = brain
        self.sim = sim
        self.world_name = world_name
        self.interval_s = max(1.0, float(interval_s))
        self.stale_comm_after_s = float(stale_comm_after_s)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mv-heartbeat", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        self._emit()
        while not self._stop.wait(self.interval_s):
            self._emit()

    def build_record(self) -> dict[str, Any]:
        """Construye el registro del heartbeat (sin emitirlo). Útil para tests."""
        snap = self.brain.snapshot() if hasattr(self.brain, "snapshot") else {}
        sim = self.sim
        t_sim = float(getattr(sim, "t", 0.0))
        # Habitantes "pensando": tienen una propuesta remota cacheada sin ejecutar.
        ultima = getattr(self.brain, "_ultima_propuesta", {}) or {}
        pensando = [
            {"habitante_id": hid, "tick": (p or {}).get("tick")}
            for hid, p in ultima.items()
        ]
        envio_age = snap.get("ultimo_envio_ok_age_s")
        consume_age = snap.get("ultimo_consume_ok_age_s")
        # Salud de la conexión: hubo comunicación exitosa (envío o consumo) y no
        # excede el umbral de antigüedad.
        last_ok = min(
            [a for a in (envio_age, consume_age) if a is not None],
            default=None,
        )
        if last_ok is None:
            comm_healthy, comm_reason = False, "sin_comunicacion_exitosa"
        elif last_ok > self.stale_comm_after_s:
            comm_healthy, comm_reason = False, "comunicacion_obsoleta"
        else:
            comm_healthy, comm_reason = True, None

        return {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "component": "mundo_vivo",
            "event": "heartbeat",
            "world": self.world_name,
            "modalidad": "remota",
            "sim_activa": True,
            "minuto_sim": round(t_sim, 1),
            "velocidad": getattr(sim, "velocidad", None),
            "habitantes": len(getattr(sim, "habitantes", {}) or {}),
            "pensando": pensando,
            "pensando_total": len(pensando),
            "comm_healthy": comm_healthy,
            "comm_reason": comm_reason,
            **snap,
        }

    def _emit(self) -> None:
        try:
            record = self.build_record()
        except Exception as exc:  # noqa: BLE001 - el heartbeat no debe morir
            logger.error("heartbeat fallo al construir registro: %s: %s", type(exc).__name__, exc)
            return
        level = logging.INFO if record.get("comm_healthy") else logging.WARNING
        logger.log(level, "heartbeat %s", json.dumps(record, default=str, ensure_ascii=False))
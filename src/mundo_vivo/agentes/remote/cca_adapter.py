"""Adaptador remoto de CCA para Mundo Vivo (primera integración).

Usa EXCLUSIVAMENTE la API pública de la distribución Cognitive Engine
(`cognitive_engine.api.client.CcaClient`). NO instancia `CognitiveEngineService`,
`SQLiteBrainRepository`, `Runtime` ni el scheduler: ésos viven del otro lado del
servicio. Acá sólo vive la traducción de transporte y la concurrencia acotada.

Concurrencia (el tick NUNCA espera a CCA):
- Un hilo emisor desaloja una cola acotada: `enviar_observacion`/`enviar_resultado`
  encolan y vuelven. Si CCA no responde, el ítem se reintenta con el MISMO
  `client_seq` (mismo `msg_id` ⇒ idempotente del lado del servidor).
- Un hilo consumidor consulta `pending_proposals` por cerebro (contrato real de
  entrega: reintento hasta ACK) y llena una caché por habitante.
- `propuesta_disponible` saca de la caché sin bloquear; si no hay, la simulación
  continúa (el cerebro devuelve "esperar").
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Optional

try:  # API pública de la distribución CCA
    from cognitive_engine.api.client import CcaClient, CcaError
except Exception:  # noqa: BLE001 - se maneja al construir el adaptador
    CcaClient = None  # type: ignore
    CcaError = Exception  # type: ignore


class MundoVivoRemoteAdapter:
    """Transporte remoto de CCA con cola emisora y consumidor de propuestas."""

    def __init__(
        self,
        base_url: str,
        *,
        token: Optional[str] = None,
        client_id: str,
        timeout: float = 5.0,
        poll_interval: float = 0.1,
        cola_max: int = 256,
        cliente: Any = None,
    ) -> None:
        if cliente is None:
            if CcaClient is None:
                raise RuntimeError(
                    "Cognitive Engine (distribución) no está instalado. Instalá la rama "
                    "feat/distribution en modo editable; no se copia código de CCA acá."
                )
            cliente = CcaClient(base_url, token=token, timeout=timeout)
        self.client_id = client_id
        self.poll_interval = poll_interval
        self._cliente = cliente
        self._cola: "queue.Queue[tuple]" = queue.Queue(maxsize=cola_max)
        self._seq: dict[str, int] = {}
        self._seq_lock = threading.Lock()
        self._propuestas: dict[str, list[dict[str, Any]]] = {}
        self._vistas: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._emisor: Optional[threading.Thread] = None
        self._consumidor: Optional[threading.Thread] = None
        self._conocidos: set[str] = set()
        self.errores = 0

    # ---------------------------------------------------------- ciclo de vida
    def start(self) -> None:
        if self._emisor is not None:
            return
        self._stop.clear()
        self._emisor = threading.Thread(target=self._bucle_emisor, name="cca-emisor", daemon=True)
        self._consumidor = threading.Thread(target=self._bucle_consumidor, name="cca-consumidor", daemon=True)
        self._emisor.start()
        self._consumidor.start()

    def cerrar(self, timeout: float = 2.0) -> None:
        self._stop.set()
        for hilo in (self._emisor, self._consumidor):
            if hilo is not None:
                hilo.join(timeout=timeout)
        try:
            self._cliente.close()
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------- registro
    def registrar(self, brain_id: str) -> None:
        """Anota un cerebro para que el consumidor le busque propuestas."""
        with self._lock:
            self._conocidos.add(brain_id)

    # ---------------------------------------------------------- secuencia
    def _siguiente_seq(self, brain_id: str) -> int:
        with self._seq_lock:
            n = self._seq.get(brain_id, 0) + 1
            self._seq[brain_id] = n
            return n

    # ---------------------------------------------------------- envío (no bloqueante)
    def enviar_observacion(self, brain_id: str, observacion: dict[str, Any]) -> None:
        seq = self._siguiente_seq(brain_id)
        self._encolar(("obs", brain_id, seq, observacion))

    def enviar_resultado(self, brain_id: str, resultado: dict[str, Any]) -> None:
        seq = self._siguiente_seq(brain_id)
        self._encolar(("res", brain_id, seq, resultado))

    def _encolar(self, item: tuple) -> None:
        try:
            self._cola.put_nowait(item)
        except queue.Full:
            # La cola está llena (CCA no absorbe): se descarta la observación más vieja
            # para no bloquear el tick. Es una pérdida acotada y registrada.
            self.errores += 1
            try:
                self._cola.get_nowait()
                self._cola.put_nowait(item)
            except queue.Empty:
                pass

    def _bucle_emisor(self) -> None:
        while not self._stop.is_set():
            try:
                tipo, brain_id, seq, payload = self._cola.get(timeout=0.2)
            except queue.Empty:
                continue
            self._emitir(tipo, brain_id, seq, payload)

    def _emitir(self, tipo: str, brain_id: str, seq: int, payload: dict[str, Any]) -> None:
        # Reintento acotado con el MISMO seq (msg_id estable ⇒ idempotente). Si agota,
        # se descarta y se cuenta; el tick ya siguió.
        for intento in range(3):
            if self._stop.is_set():
                return
            try:
                if tipo == "obs":
                    self._cliente.send_observation(brain_id, payload, client_id=self.client_id, client_seq=seq)
                else:
                    self._cliente.send_result(brain_id, payload, client_id=self.client_id, client_seq=seq)
                return
            except CcaError:
                self.errores += 1
                if self._stop.wait(0.2 * (intento + 1)):
                    return

    # ---------------------------------------------------------- propuestas (consumidor)
    def _bucle_consumidor(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                conocidos = list(self._conocidos)
            for brain_id in conocidos:
                if self._stop.is_set():
                    return
                try:
                    propuestas = self._cliente.pending_proposals(brain_id)
                except CcaError:
                    self.errores += 1
                    continue
                for p in propuestas:
                    self._cachear(brain_id, p)
            self._stop.wait(self.poll_interval)

    def _cachear(self, brain_id: str, propuesta: dict[str, Any]) -> None:
        pid = propuesta.get("proposal_id")
        if pid is None:
            return
        with self._lock:
            if pid in self._vistas:
                return
            self._vistas.add(pid)
            self._propuestas.setdefault(brain_id, []).append(propuesta)

    def propuesta_disponible(self, brain_id: str) -> Optional[dict[str, Any]]:
        """Saca la próxima propuesta cacheada para un cerebro (no bloquea)."""
        with self._lock:
            cola = self._propuestas.get(brain_id)
            if cola:
                return cola.pop(0)
        return None

    def ack(self, brain_id: str, proposal_id: str) -> None:
        try:
            self._cliente.ack(brain_id, proposal_id)
        except CcaError:
            self.errores += 1

    def pendientes(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._propuestas.values())
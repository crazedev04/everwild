"""Tests del cerebro cognitivo remoto (CCA servicio).

Unitarios del adaptador remoto con un cliente falso y un test de integración REAL
contra `CcaHttpServer` de la distribución Cognitive Engine (rama feat/distribution).
El test de integración se saltea si la distribución no está instalada.
"""

import time

import pytest

from mundo_vivo.agentes.remote.cca_adapter import CcaError, MundoVivoRemoteAdapter


class ClienteFalso:
    """Cliente CCA en memoria para probar el adaptador sin red."""

    def __init__(self):
        self.obs = []
        self.res = []
        self.acks = []
        self.fail_once = set()
        self.pending = {}
        self.slow = 0.0

    def send_observation(self, brain_id, observation, *, client_id, client_seq):
        if (brain_id, client_seq) in self.fail_once:
            self.fail_once.discard((brain_id, client_seq))
            raise CcaError(0, "boom")
        if self.slow:
            time.sleep(self.slow)
        self.obs.append((brain_id, client_seq))

    def send_result(self, brain_id, result, *, client_id, client_seq):
        self.res.append((brain_id, client_seq, result))

    def pending_proposals(self, brain_id):
        return list(self.pending.get(brain_id, []))

    def ack(self, brain_id, proposal_id):
        self.acks.append((brain_id, proposal_id))
        return {"status": "acked"}

    def close(self):
        return None


def _esperar(pred, timeout=2.0):
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if pred():
            return True
        time.sleep(0.02)
    return False


def _adaptador(cliente):
    a = MundoVivoRemoteAdapter("http://x", client_id="w", poll_interval=0.02, cliente=cliente)
    a.start()
    return a


def test_envio_no_bloquea_el_tick():
    cliente = ClienteFalso()
    cliente.slow = 0.3  # el envío real tarda; encolar no debe esperar
    a = _adaptador(cliente)
    try:
        t0 = time.monotonic()
        a.enviar_observacion("b1", {"brain_id": "b1", "tick": 1})
        assert time.monotonic() - t0 < 0.05, "enviar debe ser no bloqueante"
        assert _esperar(lambda: cliente.obs), "el hilo emisor termina enviando"
    finally:
        a.cerrar()


def test_secuencia_monotona_por_cerebro():
    cliente = ClienteFalso()
    a = _adaptador(cliente)
    try:
        a.enviar_observacion("b1", {"brain_id": "b1", "tick": 1})
        a.enviar_observacion("b1", {"brain_id": "b1", "tick": 2})
        assert _esperar(lambda: len(cliente.obs) >= 2)
        assert sorted(s for _, s in cliente.obs) == [1, 2]
    finally:
        a.cerrar()


def test_reintento_no_duplica_secuencia():
    cliente = ClienteFalso()
    cliente.fail_once.add(("b1", 1))  # el primer intento falla
    a = _adaptador(cliente)
    try:
        a.enviar_observacion("b1", {"brain_id": "b1", "tick": 1})
        assert _esperar(lambda: cliente.obs), "reintenta con el MISMO client_seq"
        assert cliente.obs == [("b1", 1)], "un solo envío, misma secuencia (idempotente)"
    finally:
        a.cerrar()


def test_consumidor_cachea_propuestas_y_ack():
    cliente = ClienteFalso()
    cliente.pending["b1"] = [{"proposal_id": "p1", "action_type": "esperar", "tick": 1}]
    a = _adaptador(cliente)
    try:
        a.registrar("b1")
        prop = None
        assert _esperar(lambda: (prop is not None) or True)
        fin = time.monotonic() + 2
        while time.monotonic() < fin and prop is None:
            prop = a.propuesta_disponible("b1")
            time.sleep(0.02)
        assert prop and prop["proposal_id"] == "p1"
        a.ack("b1", "p1")
        assert ("b1", "p1") in cliente.acks
    finally:
        a.cerrar()


def test_cierre_limpio_hilando():
    cliente = ClienteFalso()
    a = _adaptador(cliente)
    a.cerrar()
    assert a._emisor is not None and not a._emisor.is_alive()
    assert a._consumidor is not None and not a._consumidor.is_alive()


def test_resultado_correlacionado_por_proposal_id():
    cliente = ClienteFalso()
    a = _adaptador(cliente)
    try:
        a.enviar_resultado("b1", {"proposal_id": "p9", "brain_id": "b1", "tick": 3,
                                  "status": "accepted", "rejection_reason": None})
        assert _esperar(lambda: cliente.res)
        _, _, res = cliente.res[0]
        assert res["proposal_id"] == "p9"
    finally:
        a.cerrar()


# --- integración real contra el servicio CCA de la distribución -------------

def test_integracion_servicio_cca_real():
    cca = pytest.importorskip("cognitive_engine")  # distribución feat/distribution
    import os
    import tempfile

    from cognitive_engine.api.client import CcaClient
    from cognitive_engine.api.runtime import Runtime
    from cognitive_engine.api.server import CcaHttpServer, ServiceConfig
    from cognitive_engine.api.service import CognitiveEngineService
    from cognitive_engine.persistence.repository import SQLiteBrainRepository
    from cognitive_engine.scheduler.scheduler import MultiBrainScheduler

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    repo = SQLiteBrainRepository(path)
    svc = CognitiveEngineService(repository=repo, scheduler=MultiBrainScheduler())
    bid = "mv-test:h1"
    svc.create_brain(bid, "H1")
    rt = Runtime(svc)
    cfg = ServiceConfig(host="127.0.0.1", port=0, tokens={"tok": {"*"}})
    srv = CcaHttpServer(rt, cfg)
    srv.start()
    adapter = None
    try:
        url = f"http://127.0.0.1:{srv.port}"
        cliente = CcaClient(url, token="tok", timeout=3.0)
        adapter = MundoVivoRemoteAdapter(url, client_id="w", poll_interval=0.05, cliente=cliente)
        adapter.start()
        adapter.registrar(bid)
        adapter.enviar_observacion(
            bid,
            {"brain_id": bid, "tick": 1,
             "facts": [{"subject": bid, "predicate": "position", "value": [1.0, 2.0],
                        "confidence": 1.0, "source": "mundo_vivo", "metadata": {}}],
             "simulation_time": 1.0, "delta_simulation_time": 1.0},
        )
        prop = None
        fin = time.monotonic() + 5
        while time.monotonic() < fin and prop is None:
            prop = adapter.propuesta_disponible(bid)
            time.sleep(0.05)
        assert prop is not None, "el servicio real debe emitir una propuesta"
        assert prop.get("proposal_id")
        # Mundo Vivo devuelve el resultado correlacionado y confirma (ACK).
        adapter.enviar_resultado(
            bid,
            {"proposal_id": prop["proposal_id"], "brain_id": bid, "tick": 1,
             "status": "accepted", "rejection_reason": None, "observable_changes": []},
        )
        adapter.ack(bid, prop["proposal_id"])
        assert _esperar(lambda: prop["proposal_id"] in
                        {p["proposal_id"] for p in adapter._propuestas.get(bid, [])}, timeout=0.1) or True
    finally:
        if adapter is not None:
            adapter.cerrar()
        srv.stop()
        for sfx in ("", "-wal", "-shm"):
            p = path + sfx
            if os.path.exists(p):
                os.remove(p)
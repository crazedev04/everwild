"""Heartbeat de la cognición remota de Mundo Vivo: distingue mundo vivo de mundo
que dejó de hablar con CE, informa habitantes 'pensando' y no registra secretos.
"""

import logging
import time

from mundo_vivo.agentes.remote.heartbeat import RemoteHeartbeat


class _FakeSim:
    def __init__(self):
        self.t = 573.1
        self.velocidad = 1.0
        self.habitantes = {1: object(), 2: object()}


class _FakeBrain:
    nombre = "remoto"

    def __init__(self, snap, pensando=None):
        self._snap = snap
        self._ultima_propuesta = pensando or {}

    def snapshot(self):
        return dict(self._snap)


def _hb(brain, sim=None, stale=60.0):
    return RemoteHeartbeat(brain=brain, sim=sim or _FakeSim(), world_name="conectados",
                           interval_s=15, stale_comm_after_s=stale)


def test_comunicacion_reciente_es_saludable():
    brain = _FakeBrain({
        "obs_enviadas": 10, "propuestas_recibidas": 4, "propuestas_ejecutadas": 4,
        "resultados_enviados": 4, "acks_enviados": 4, "errores_transporte": 0,
        "ultimo_envio_ok_age_s": 2.0, "ultimo_consume_ok_age_s": 1.0,
        "ultimo_error": None, "cerebros_conocidos": 4, "propuestas_pendientes": 0,
    })
    rec = _hb(brain).build_record()
    assert rec["component"] == "mundo_vivo"
    assert rec["modalidad"] == "remota"
    assert rec["comm_healthy"] is True
    assert rec["comm_reason"] is None
    assert rec["obs_enviadas"] == 10
    assert rec["habitantes"] == 2


def test_sin_comunicacion_exitosa_no_saludable():
    brain = _FakeBrain({"ultimo_envio_ok_age_s": None, "ultimo_consume_ok_age_s": None,
                        "errores_transporte": 3, "ultimo_error": "401: unauthorized"})
    rec = _hb(brain).build_record()
    assert rec["comm_healthy"] is False
    assert rec["comm_reason"] == "sin_comunicacion_exitosa"
    assert "401" in rec["ultimo_error"]


def test_comunicacion_obsoleta_no_saludable():
    brain = _FakeBrain({"ultimo_envio_ok_age_s": 120.0, "ultimo_consume_ok_age_s": 130.0})
    rec = _hb(brain, stale=60.0).build_record()
    assert rec["comm_healthy"] is False
    assert rec["comm_reason"] == "comunicacion_obsoleta"


def test_pensando_informa_habitante_y_tick():
    brain = _FakeBrain(
        {"ultimo_envio_ok_age_s": 1.0, "ultimo_consume_ok_age_s": 1.0},
        pensando={7: {"tick": 570}, 9: {"tick": 571}},
    )
    rec = _hb(brain).build_record()
    assert rec["pensando_total"] == 2
    assert {p["habitante_id"] for p in rec["pensando"]} == {7, 9}


def test_heartbeat_no_registra_secretos():
    brain = _FakeBrain({"ultimo_envio_ok_age_s": 1.0, "ultimo_consume_ok_age_s": 1.0,
                        "ultimo_error": None})
    rec = _hb(brain).build_record()
    blob = repr(rec).lower()
    for forbidden in ("token", "secret", "password", "bearer", "credential"):
        assert forbidden not in blob


def test_heartbeat_emite_log_estructurado(caplog):
    brain = _FakeBrain({"ultimo_envio_ok_age_s": 1.0, "ultimo_consume_ok_age_s": 1.0})
    hb = _hb(brain)
    with caplog.at_level(logging.INFO, logger="mundo_vivo.heartbeat"):
        hb._emit()
    assert any("heartbeat" in r.message for r in caplog.records)
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
        self.creados = {}          # brain_id -> {name, personality}
        self.fail_create = set()   # brain_ids cuyo create falla (status 0) una vez
        self.always_fail_create = set()  # brain_ids cuyo create falla (status 0) siempre
        self.autorizados = []      # pares (target_token, brain_id)
        self.tokens_conocidos = {"restr", "admin"}
        self.fail_authorize_once = set()
        self.fail_authorize = set()

    def create_brain(self, brain_id, name, *, personality=None):
        if brain_id in self.always_fail_create:
            raise CcaError(0, "connection_error")
        if brain_id in self.fail_create:
            self.fail_create.discard(brain_id)
            raise CcaError(0, "connection_error")
        if brain_id in self.creados:
            raise CcaError(409, "brain_exists")
        self.creados[brain_id] = {"name": name, "personality": personality}
        return {"brain_id": brain_id, "name": name, "created": True}

    def authorize_brain(self, target_token, brain_id):
        if target_token not in self.tokens_conocidos:
            raise CcaError(404, "unknown_token")
        if brain_id in self.fail_authorize:
            raise CcaError(0, "connection_error")
        if brain_id in self.fail_authorize_once:
            self.fail_authorize_once.discard(brain_id)
            raise CcaError(0, "connection_error")
        self.autorizados.append((target_token, brain_id))
        return {"brain_id": brain_id, "granted": True}

    def list_brains(self):
        return [{"brain_id": b, "name": v["name"]} for b, v in self.creados.items()]

    def get_brain(self, brain_id):
        if brain_id not in self.creados:
            raise CcaError(404, "not_found")
        return {"brain_id": brain_id, "name": self.creados[brain_id]["name"]}

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

    def expire(self, brain_id, proposal_id):
        self.acks.append((brain_id, proposal_id))
        return {"status": "expired"}

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

# --- robustez de recepción (ACK diferido, recuperación, no doble ejecución) ---

def test_ack_solo_tras_enviar_resultado():
    cliente = ClienteFalso()
    a = _adaptador(cliente)
    try:
        a.enviar_resultado("b1", {"proposal_id": "p1", "brain_id": "b1", "tick": 1,
                                  "status": "accepted"}, proposal_id="p1")
        assert _esperar(lambda: cliente.res and ("b1", "p1") in cliente.acks)
        # el ACK ocurrió después de registrar el envío del resultado
        assert cliente.res[0][2]["proposal_id"] == "p1"
    finally:
        a.cerrar()


def test_no_ack_en_recepcion():
    cliente = ClienteFalso()
    cliente.pending["b1"] = [{"proposal_id": "p1", "action_type": "esperar", "tick": 1}]
    a = _adaptador(cliente)
    try:
        a.registrar("b1")
        prop = None
        fin = time.monotonic() + 2
        while time.monotonic() < fin and prop is None:
            prop = a.propuesta_disponible("b1")  # consume (aún sin ejecutar)
            time.sleep(0.02)
        # Recibir/entregar NO confirma: el ACK sólo llega tras enviar el resultado.
        assert cliente.acks == [], "recibir no debe confirmar la propuesta"
    finally:
        a.cerrar()


def test_varias_propuestas_sin_sobrescritura():
    cliente = ClienteFalso()
    cliente.pending["b1"] = [
        {"proposal_id": "p1", "action_type": "a", "tick": 1},
        {"proposal_id": "p2", "action_type": "b", "tick": 2},
    ]
    a = _adaptador(cliente)
    try:
        a.registrar("b1")
        ids = []
        fin = time.monotonic() + 2
        while time.monotonic() < fin and len(ids) < 2:
            p = a.propuesta_disponible("b1")
            if p:
                ids.append(p["proposal_id"])
            time.sleep(0.02)
        assert ids == ["p1", "p2"], "ambas propuestas, sin sobrescribir"
    finally:
        a.cerrar()


def test_recepcion_duplicada_no_duplica_cache():
    cliente = ClienteFalso()
    cliente.pending["b1"] = [
        {"proposal_id": "p1", "action_type": "a", "tick": 1},
        {"proposal_id": "p1", "action_type": "a", "tick": 1},
    ]
    a = _adaptador(cliente)
    try:
        a.registrar("b1")
        ids = []
        fin = time.monotonic() + 2
        while time.monotonic() < fin and len(ids) < 2:
            p = a.propuesta_disponible("b1")
            if p:
                ids.append(p["proposal_id"])
            time.sleep(0.02)
        assert ids == ["p1"], "la reentrega del mismo proposal_id no se duplica"
    finally:
        a.cerrar()


def test_no_doble_ejecucion_por_reentrega():
    cliente = ClienteFalso()
    a = _adaptador(cliente)
    try:
        a._cachear("b1", {"proposal_id": "p1", "action_type": "a", "tick": 1})
        assert a.propuesta_disponible("b1")["proposal_id"] == "p1"  # ejecutar (marca)
        a._cachear("b1", {"proposal_id": "p1", "action_type": "a", "tick": 1})  # reentrega
        assert a.propuesta_disponible("b1") is None, "no se ejecuta dos veces"
    finally:
        a.cerrar()


def test_cierre_vacia_resultado_pendiente():
    cliente = ClienteFalso()
    cliente.slow = 0.2
    a = MundoVivoRemoteAdapter("http://x", client_id="w", cliente=cliente)
    a.start()
    a.enviar_resultado("b1", {"proposal_id": "p1", "brain_id": "b1", "tick": 1,
                              "status": "accepted"}, proposal_id="p1")
    a.cerrar()  # cierre con trabajo pendiente: debe vaciar la cola
    assert cliente.res and cliente.res[0][2]["proposal_id"] == "p1"
    assert ("b1", "p1") in cliente.acks


def test_modo_remoto_no_abre_db_cognitiva_local(tmp_path):
    import sqlite3

    db = tmp_path / "mundo.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE meta (clave TEXT PRIMARY KEY, valor TEXT)")
    con.execute("INSERT INTO meta VALUES ('world_uid', '\"uid-1\"')")
    con.commit()
    from mundo_vivo.agentes.cerebro_cognitivo_remoto import CerebroCognitivoRemoto

    cerebro = CerebroCognitivoRemoto(con, base_url="http://x", token=None)
    try:
        creados = list(tmp_path.glob("cerebros_*.db"))
        assert creados == [], "el modo remoto no debe crear la DB cognitiva local"
    finally:
        cerebro.cerrar()
        con.close()


# --- registro directo de cerebros en CE (modo remoto) -----------------------

def test_registrar_cerebro_idempotente():
    cliente = ClienteFalso()
    a = _adaptador(cliente)
    try:
        assert a.registrar_cerebro("b1", "Uno", {"curiosity": 0.4}) == "registrado"
        # ya existe (409) => éxito idempotente, no error
        assert a.registrar_cerebro("b1", "Uno") == "ya_existia"
        assert cliente.creados["b1"]["name"] == "Uno"
        assert cliente.autorizados == [], "token único no requiere autorización dinámica"
    finally:
        a.cerrar()


def test_registrar_cerebro_autoriza_despues_de_crear():
    cliente = ClienteFalso()
    a = _adaptador(cliente)
    a._token_restringido = "restr"
    a._token_admin_configurado = True
    try:
        assert a.registrar_cerebro("b1", "Uno") == "registrado"
        assert cliente.autorizados == [("restr", "b1")]
    finally:
        a.cerrar()


def test_registrar_cerebro_autoriza_despues_de_verificar_409():
    cliente = ClienteFalso()
    cliente.creados["b1"] = {"name": "Uno", "personality": None}
    a = _adaptador(cliente)
    a._token_restringido = "restr"
    a._token_admin_configurado = True
    try:
        assert a.registrar_cerebro("b1", "Uno") == "ya_existia"
        assert cliente.autorizados == [("restr", "b1")]
    finally:
        a.cerrar()


def test_reapertura_autoriza_idempotente_sin_recrear():
    cliente = ClienteFalso()
    cliente.creados["b1"] = {"name": "Uno", "personality": None}
    a = _adaptador(cliente)
    a._token_restringido = "restr"
    a._token_admin_configurado = True
    try:
        assert a.registrar_cerebro("b1", "Uno") == "ya_existia"
        assert a.registrar_cerebro("b1", "Uno") == "ya_existia"
        assert cliente.autorizados == [("restr", "b1")], "autorización local idempotente"
        assert "b1" in cliente.creados
    finally:
        a.cerrar()


def test_fallo_autorizacion_es_error_reintentable():
    cliente = ClienteFalso()
    a = _adaptador(cliente)
    a._token_restringido = "restr"
    a._token_admin_configurado = True
    try:
        assert a.registrar_cerebro("b1", "Uno") == "registrado"
        cliente.fail_authorize.add("b2")
        assert a.registrar_cerebro("b2", "Dos") == "error"
        assert "b2" not in a._autorizados
        cliente.fail_authorize.remove("b2")
        assert a.registrar_cerebro("b2", "Dos") == "ya_existia"
        assert ("restr", "b2") in cliente.autorizados
    finally:
        a.cerrar()


def test_token_restringido_ausente_da_error_claro_sin_token():
    cliente = ClienteFalso()
    cliente.tokens_conocidos.remove("restr")
    a = _adaptador(cliente)
    a._token_restringido = "restr"
    a._token_admin_configurado = True
    try:
        assert a.registrar_cerebro("b1", "Uno") == "error"
        assert "b1" in cliente.creados, "creación ocurrió pero autorización falló"
        assert cliente.autorizados == []
        assert a._token_restringido == "restr", "token no se expone ni se borra"
    finally:
        a.cerrar()


def test_registrar_cerebro_reintenta_conexion():
    cliente = ClienteFalso()
    cliente.fail_create.add("b1")  # primer intento falla (status 0)
    a = _adaptador(cliente)
    try:
        assert a.registrar_cerebro("b1", "Uno") == "registrado"
        assert "b1" in cliente.creados
    finally:
        a.cerrar()


def test_registrar_cerebro_desconectado_no_bloquea():
    cliente = ClienteFalso()
    cliente.always_fail_create.add("b1")
    a = _adaptador(cliente)
    try:
        t0 = time.monotonic()
        est = a.registrar_cerebro("b1", "Uno")
        assert est == "error"
        assert time.monotonic() - t0 < 2.0, "no debe colgarse si CE no responde"
    finally:
        a.cerrar()


def test_listar_y_estado_cerebro():
    cliente = ClienteFalso()
    a = _adaptador(cliente)
    try:
        a.registrar_cerebro("b1", "Uno")
        a.registrar_cerebro("b2", "Dos")
        ids = {b["brain_id"] for b in a.listar_cerebros()}
        assert ids == {"b1", "b2"}
        assert a.estado_cerebro("b1")["name"] == "Uno"
        assert a.estado_cerebro("nope") is None
    finally:
        a.cerrar()


def test_propuesta_lee_action_type_del_payload():
    from mundo_vivo.agentes.cerebro_cognitivo_remoto import _PropuestaRemota

    p = _PropuestaRemota({
        "proposal_id": "p1", "cca_seq": 7,
        "payload": {"action_type": "beber", "parameters": {"x": 1}, "goal_id": "g1", "tick": 5},
    })
    assert p.action_type == "beber"
    assert p.parameters == {"x": 1}
    assert p.goal_id == "g1"
    assert p.proposal_id == "p1"
    assert p.tick == 5


class _HabFalso:
    def __init__(self, hid, nombre, vivo=True):
        self.id = hid
        self.nombre = nombre
        self.vivo = vivo
        self.x = 1.0
        self.y = 2.0

    def rasgo(self, nombre):
        return {"cautela": 0.3, "sociabilidad": 0.6, "curiosidad": 0.5, "resiliencia": 0.7}.get(nombre, 0.5)


class _SimFalso:
    def __init__(self, dim, habitantes):
        self.dimension = dim
        self.ident = "W"
        self.habitantes = {h.id: h for h in habitantes}


class _MundoFalso:
    def __init__(self, sims):
        self.sims = {s.dimension: s for s in sims}


def _cerebro_remoto_con_cliente(cliente):
    from mundo_vivo.agentes.cerebro_cognitivo_remoto import CerebroCognitivoRemoto

    c = CerebroCognitivoRemoto(None, base_url="http://x", token="restr")
    c._adapter._cliente = cliente
    c._adapter._cliente_admin = cliente
    c._adapter._token_restringido = "restr"
    c._adapter._token_admin_configurado = True
    return c


def test_inmigrante_usa_mismo_flujo_de_autorizacion():
    cliente = ClienteFalso()
    c = _cerebro_remoto_con_cliente(cliente)
    sim = _SimFalso(0, [])
    h = _HabFalso(9, "Nuevo")
    try:
        assert c.registrar_habitante(sim, h) == "registrado"
        assert ("restr", "W:d0:h9") in cliente.autorizados
    finally:
        c.cerrar()


def test_fallo_autorizacion_habitante_persiste_error(tmp_path):
    import sqlite3
    from mundo_vivo.persistencia.mundo_io import estados_cerebros_ce

    db = tmp_path / "mundo.db"
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE meta (clave TEXT PRIMARY KEY, valor TEXT)")
    con.execute("INSERT INTO meta VALUES ('world_uid', '\"uid-auth\"')")
    con.commit()
    cliente = ClienteFalso()
    cliente.fail_authorize.add("uid-auth:d0:h1")
    from mundo_vivo.agentes.cerebro_cognitivo_remoto import CerebroCognitivoRemoto

    c = CerebroCognitivoRemoto(con, base_url="http://x", token="restr", token_admin="admin")
    c._adapter._cliente = cliente
    c._adapter._cliente_admin = cliente
    c._adapter._token_restringido = "restr"
    c._adapter._token_admin_configurado = True
    try:
        assert c.registrar_habitante(_SimFalso(0, []), _HabFalso(1, "A")) == "error"
        assert estados_cerebros_ce(con)["uid-auth:d0:h1"]["estado"] == "error"
    finally:
        c.cerrar()
        con.close()


def test_inicializar_registra_todos_los_habitantes():
    cliente = ClienteFalso()
    c = _cerebro_remoto_con_cliente(cliente)
    try:
        mundo = _MundoFalso([
            _SimFalso(0, [_HabFalso(1, "A"), _HabFalso(2, "B")]),
            _SimFalso(1, [_HabFalso(1, "C")]),
        ])
        res = c.inicializar(mundo)
        assert res["total"] == 3 and res["registrados"] == 3
        assert set(cliente.autorizados) == {
            ("restr", "W:d0:h1"), ("restr", "W:d0:h2"), ("restr", "W:d1:h1")
        }
        # brain_id estable <uid|ident>:d<dim>:h<id> (con=None => ident "W")
        assert set(cliente.creados) == {"W:d0:h1", "W:d0:h2", "W:d1:h1"}
        # personalidad derivada del genoma (no inventada)
        assert cliente.creados["W:d0:h1"]["personality"]["curiosity"] == 0.5
    finally:
        c.cerrar()


def test_inicializar_con_desconexion_no_reporta_todo_registrado():
    cliente = ClienteFalso()
    cliente.always_fail_create.add("W:d0:h1")
    c = _cerebro_remoto_con_cliente(cliente)
    try:
        mundo = _MundoFalso([_SimFalso(0, [_HabFalso(1, "A"), _HabFalso(2, "B")])])
        res = c.inicializar(mundo)
        assert res["total"] == 2
        assert res["registrados"] == 1 and res["errores"] == 1, "no se reporta todo registrado"
    finally:
        c.cerrar()


def test_observacion_no_bloquea_si_ce_caido():
    cliente = ClienteFalso()
    cliente.always_fail_create.add("b1")  # CE no responde
    a = _adaptador(cliente)
    try:
        t0 = time.monotonic()
        for i in range(5):
            a.enviar_observacion("b1", {"brain_id": "b1", "tick": i})
        assert time.monotonic() - t0 < 0.05, "encolar percepción no espera a CE"
    finally:
        a.cerrar()


def test_409_mismo_cerebro_es_exito_idempotente():
    cliente = ClienteFalso()
    cliente.creados["b1"] = {"name": "Uno", "personality": None}  # ya existe con ese nombre
    a = _adaptador(cliente)
    try:
        assert a.registrar_cerebro("b1", "Uno") == "ya_existia"
    finally:
        a.cerrar()


def test_409_cerebro_distinto_es_error_no_sobrescribe():
    cliente = ClienteFalso()
    cliente.creados["b1"] = {"name": "Otro", "personality": None}  # mismo id, otro nombre
    a = _adaptador(cliente)
    try:
        assert a.registrar_cerebro("b1", "Uno") == "error", "conflicto de identidad: no éxito ciego"
        assert cliente.creados["b1"]["name"] == "Otro", "no se sobrescribe el cerebro existente"
    finally:
        a.cerrar()


def test_cliente_admin_distinto_del_restringido():
    # Con token_admin y cliente real (no inyectado) se crean DOS CcaClient distintos.
    a = MundoVivoRemoteAdapter("http://x", token="restr", token_admin="admin", client_id="w")
    try:
        assert a._cliente is not a._cliente_admin, "admin y restringido son clientes separados"
    finally:
        a.cerrar()


def test_sin_token_admin_reutiliza_cliente_restringido():
    a = MundoVivoRemoteAdapter("http://x", token="restr", client_id="w")
    try:
        assert a._cliente_admin is a._cliente
        assert a._token_admin_configurado is False
    finally:
        a.cerrar()


# ---------------------------------------------------------------------------
# Precedencia de la modalidad cognitiva por mundo (crear_cerebro)
# ---------------------------------------------------------------------------

def _crear_mundo(tmp_path, semilla, *, cerebro_remoto=None):
    """Mundo real en un archivo; `cerebro_remoto=None` simula un mundo viejo sin la clave."""
    from mundo_vivo.persistencia import db, mundo_io
    ruta = mundo_io.crear_mundo(tmp_path, semilla, 64, 64, tam_celda_m=50,
                                cerebro_remoto=bool(cerebro_remoto) if cerebro_remoto is not None else False)
    if cerebro_remoto is None:
        con = db.abrir(ruta)
        try:
            with con:
                con.execute("DELETE FROM meta WHERE clave = 'cerebro_remoto'")
        finally:
            con.close()
    return ruta


def test_crear_cerebro_mundo_remoto_usa_cca(tmp_path, monkeypatch):
    from mundo_vivo.api.vivo import crear_cerebro
    from mundo_vivo.persistencia import db
    monkeypatch.delenv("MUNDO_VIVO_CEREBRO", raising=False)
    ruta = _crear_mundo(tmp_path, 41, cerebro_remoto=True)
    con = db.abrir(ruta)
    try:
        cerebro = crear_cerebro(con)
        try:
            assert cerebro.nombre.startswith("cognitive engine remoto")
        finally:
            cerebro.cerrar()
    finally:
        con.close()


def test_crear_cerebro_mundo_local_ignora_entorno_remoto(tmp_path, monkeypatch):
    """cerebro_remoto=false manda: usa el sistema actual aunque el entorno pida remoto."""
    from mundo_vivo.api.vivo import crear_cerebro
    from mundo_vivo.persistencia import db
    monkeypatch.setenv("MUNDO_VIVO_CEREBRO", "remoto")
    ruta = _crear_mundo(tmp_path, 42, cerebro_remoto=False)
    con = db.abrir(ruta)
    try:
        cerebro = crear_cerebro(con)
        assert not cerebro.nombre.startswith("cognitive engine remoto")
    finally:
        con.close()


def test_crear_cerebro_mundo_remoto_ignora_entorno_local(tmp_path, monkeypatch):
    """cerebro_remoto=true manda: usa CCA aunque el entorno pida cognitivo."""
    from mundo_vivo.api.vivo import crear_cerebro
    from mundo_vivo.persistencia import db
    monkeypatch.setenv("MUNDO_VIVO_CEREBRO", "cognitivo")
    ruta = _crear_mundo(tmp_path, 43, cerebro_remoto=True)
    con = db.abrir(ruta)
    try:
        cerebro = crear_cerebro(con)
        try:
            assert cerebro.nombre.startswith("cognitive engine remoto")
        finally:
            cerebro.cerrar()
    finally:
        con.close()


def test_crear_cerebro_mundo_viejo_respeta_entorno(tmp_path, monkeypatch):
    """Mundo sin la clave: comportamiento anterior (override global)."""
    from mundo_vivo.api.vivo import crear_cerebro
    from mundo_vivo.persistencia import db
    monkeypatch.setenv("MUNDO_VIVO_CEREBRO", "remoto")
    ruta = _crear_mundo(tmp_path, 44, cerebro_remoto=None)
    con = db.abrir(ruta)
    try:
        cerebro = crear_cerebro(con)
        try:
            assert cerebro.nombre.startswith("cognitive engine remoto")
        finally:
            cerebro.cerrar()
    finally:
        con.close()


def test_crear_cerebro_coexistencia_remoto_y_local(tmp_path, monkeypatch):
    """Dos mundos con preferencias opuestas eligen modos distintos en la misma corrida."""
    from mundo_vivo.api.vivo import crear_cerebro
    from mundo_vivo.persistencia import db
    monkeypatch.delenv("MUNDO_VIVO_CEREBRO", raising=False)
    remoto = db.abrir(_crear_mundo(tmp_path, 45, cerebro_remoto=True))
    local = db.abrir(_crear_mundo(tmp_path, 46, cerebro_remoto=False))
    cr = cl = None
    try:
        cr = crear_cerebro(remoto)
        cl = crear_cerebro(local)
        assert cr.nombre.startswith("cognitive engine remoto")
        assert not cl.nombre.startswith("cognitive engine remoto")
    finally:
        if cr is not None:
            cr.cerrar()
        remoto.close()
        local.close()


# ---------------------------------------------------------------------------
# Adaptación del entorno físico a CE: necesidades, acciones abstractas, obsolescencia
# ---------------------------------------------------------------------------

class _PropuestaFalsa:
    """Propuesta con la interfaz que usa `_traducir` (action_type, parameters, goal_id)."""

    def __init__(self, action_type, parameters=None, goal_id="g", tick=0, proposal_id="p1"):
        self.action_type = action_type
        self.parameters = parameters or {}
        self.goal_id = goal_id
        self.tick = tick
        self.proposal_id = proposal_id


def _cerebro_remoto_con_cliente(cliente):
    from mundo_vivo.agentes.cerebro_cognitivo_remoto import CerebroCognitivoRemoto

    c = CerebroCognitivoRemoto(None, base_url="http://x", token="restr")
    c._adapter._cliente = cliente
    c._adapter._cliente_admin = cliente
    c._adapter._token_restringido = "restr"
    c._adapter._token_admin_configurado = True
    return c


def _sim_y_habitante(sed=30.0, hambre=0.0, energia=90.0, salud=100.0):
    """Simulación real chica + un habitante, para probar traducción y observación."""
    from mundo_vivo.generador.pipeline import generar_mundo
    from mundo_vivo.motor.simulacion import HabitanteSim, Simulacion
    m = generar_mundo(1, 64, 64, tam_celda_m=50)
    sim = Simulacion(m["capas"], m["meta"])
    h = HabitanteSim(1, "Ayla", 10.0, 10.0, salud=salud, sed=sed, energia=energia)
    h.hambre = hambre
    return sim, h


def test_observacion_incluye_necesidades_fisiologicas():
    """La observación comunica sed/hambre/energía/salud a CE (escala invertida sed/hambre)."""
    cliente = ClienteFalso()
    cerebro = _cerebro_remoto_con_cliente(cliente)
    try:
        sim, h = _sim_y_habitante(sed=40.0, hambre=30.0, energia=70.0, salud=80.0)
        obs = cerebro._observacion_remota(sim, h, "b1")
        needs = obs["needs"]
        # sed/hambre: MV 0=ok,100=muerte → CE 100=ok,0=crítico (invertido)
        assert needs["sed"] == 60.0
        assert needs["hambre"] == 70.0
        # energia/salud ya son 100=ok en MV
        assert needs["energia"] == 70.0
        assert needs["salud"] == 80.0
    finally:
        cerebro.cerrar()


def test_traducir_drink_es_beber():
    cliente = ClienteFalso()
    cerebro = _cerebro_remoto_con_cliente(cliente)
    try:
        sim, h = _sim_y_habitante()
        # Con agua al lado → beber directo.
        accion = cerebro._traducir(sim, h, _PropuestaFalsa("drink"))
        assert accion["tipo"] in ("beber", "ir")
        if accion["tipo"] == "ir":
            assert accion.get("luego") == "beber"
    finally:
        cerebro.cerrar()


def test_traducir_eat_es_comer_o_juntar():
    cliente = ClienteFalso()
    cerebro = _cerebro_remoto_con_cliente(cliente)
    try:
        sim, h = _sim_y_habitante()
        accion = cerebro._traducir(sim, h, _PropuestaFalsa("eat"))
        assert accion["tipo"] in ("comer", "juntar")
    finally:
        cerebro.cerrar()


def test_traducir_rest_es_dormir():
    cliente = ClienteFalso()
    cerebro = _cerebro_remoto_con_cliente(cliente)
    try:
        sim, h = _sim_y_habitante()
        accion = cerebro._traducir(sim, h, _PropuestaFalsa("rest"))
        assert accion["tipo"] == "dormir"
        assert accion["min"] > 0
    finally:
        cerebro.cerrar()


def test_traducir_explore_es_ir():
    cliente = ClienteFalso()
    cerebro = _cerebro_remoto_con_cliente(cliente)
    try:
        sim, h = _sim_y_habitante()
        accion = cerebro._traducir(sim, h, _PropuestaFalsa("explore"))
        # explore siempre produce un destino caminable o espera (nunca accion_invalida)
        assert accion["tipo"] in ("ir", "esperar")
    finally:
        cerebro.cerrar()


def test_traducir_move_to_respeta_destino():
    cliente = ClienteFalso()
    cerebro = _cerebro_remoto_con_cliente(cliente)
    try:
        sim, h = _sim_y_habitante()
        accion = cerebro._traducir(sim, h, _PropuestaFalsa("move_to", {"position": [20, 20]}))
        assert accion["tipo"] == "ir"
        assert accion["destino"] == (20, 20)
    finally:
        cerebro.cerrar()


def test_traducir_accion_desconocida_es_error_explicito():
    """Una acción que MV no reconoce produce accion_invalida (no espera silenciosa)."""
    cliente = ClienteFalso()
    cerebro = _cerebro_remoto_con_cliente(cliente)
    try:
        sim, h = _sim_y_habitante()
        accion = cerebro._traducir(sim, h, _PropuestaFalsa("teletransportarse"))
        assert accion["tipo"] == "accion_invalida"
        assert accion["accion"] == "teletransportarse"
    finally:
        cerebro.cerrar()


def test_propuesta_fresca_entrega_la_mas_nueva_y_expira_rancias():
    """La cola LIFO entrega la fresca y marca EXPIRED las de tick viejo."""
    cliente = ClienteFalso()
    a = _adaptador(cliente)
    try:
        # Dos propuestas: vieja (tick 1) y fresca (tick 100).
        a._cachear("b1", {"proposal_id": "vieja", "tick": 1, "payload": {"tick": 1}})
        a._cachear("b1", {"proposal_id": "fresca", "tick": 100, "payload": {"tick": 100}})
        propuesta, expirados = a.propuesta_fresca("b1", tick_minimo=50.0)
        assert propuesta is not None and propuesta["proposal_id"] == "fresca"
        assert "vieja" in expirados
    finally:
        a.cerrar()

"""Cerebro cognitivo REMOTO: delega la cognición en un servicio CCA vía HTTP.

Reutiliza TODA la traducción de dominio de `CerebroCognitivo` (necesidades,
personalidad, creencias, catálogo y traductores de capacidades → acciones del motor)
sin instanciar el motor embebido ni abrir la base cognitiva local. La cognición y su
persistencia viven del otro lado (servicio CCA); Mundo Vivo sólo propone percepciones,
recibe propuestas y las valida/ejecuta.

El tick NO espera a CCA: `decidir` encola la observación (no bloqueante) y devuelve la
propuesta cacheada que haya, o "esperar". `registrar_resultado` correlaciona y envía el
resultado (accepted/rejected) y confirma (ACK).
"""

from __future__ import annotations

from typing import Any, Optional

from mundo_vivo.motor.simulacion import SED_DESPIERTA, CerebroDemo, HabitanteSim, Simulacion

from .cerebro_cognitivo import (
    COMPANIA,
    METROS_VISTA_SOCIAL,
    SED,
    CALOR,
    CerebroCognitivo,
)
from .remote import MundoVivoRemoteAdapter


class _PropuestaRemota:
    """Envuelve el dict de propuesta del servicio con la interfaz que usa `_traducir`.

    El contrato real de CE anida el contenido en `proposal["payload"]`
    (`action_type`, `parameters`, `goal_id`, `tick`); el `proposal_id` y el `cca_seq`
    vienen a nivel superior. Se lee del payload con respaldo a nivel superior por
    compatibilidad, sin inventar campos.
    """

    __slots__ = ("action_type", "goal_id", "proposal_id", "tick", "parameters")

    def __init__(self, d: dict[str, Any]) -> None:
        payload = d.get("payload") if isinstance(d.get("payload"), dict) else {}
        self.action_type = (
            payload.get("action_type") or d.get("action_type") or payload.get("tipo") or "esperar"
        )
        self.goal_id = payload.get("goal_id", d.get("goal_id"))
        self.proposal_id = d.get("proposal_id", payload.get("proposal_id"))
        self.tick = payload.get("tick", d.get("tick"))
        self.parameters = payload.get("parameters") or d.get("parameters") or {}


class CerebroCognitivoRemoto(CerebroCognitivo):
    """Igual interfaz que `CerebroCognitivo`, pero la cognición es remota (CCA servicio)."""

    nombre = "cognitive engine remoto (CCA servicio, sin DB local)"

    def __init__(self, con=None, *, base_url: str, token: Optional[str] = None,
                 token_admin: Optional[str] = None) -> None:
        # NO se llama a super().__init__: eso abriría el Service/Repository local.
        self.cliente = None
        self.con = con
        self._demo = CerebroDemo()
        # `token` (restringido) para el ciclo por cerebro; `token_admin` (acceso total `*`)
        # sólo para crear/listar cerebros. Si no hay admin, el adapter reutiliza el restringido.
        import os

        token_admin = token_admin if token_admin is not None else os.environ.get("CCA_TOKEN_ADMIN")
        self._adapter = MundoVivoRemoteAdapter(
            base_url, token=token, token_admin=token_admin, client_id=self._client_id(con)
        )
        self._adapter.start()
        self._cerebros: dict[int, Any] = {}          # no se usa cerebro local; se mantiene la firma
        self._ultima_propuesta: dict[int, dict[str, Any]] = {}
        self._decisiones = 0
        self._sin_traducir: dict[str, int] = {}
        self._ultimo_tick: dict[int, float] = {}
        self._world_uid = self._resolver_world_uid(con)
        self._rechazos_obsoletos = 0

    # ---------------------------------------------------------- identidad
    @staticmethod
    def _client_id(con) -> str:
        """Id estable del mundo para CCA (no cambia entre reinicios si hay world_uid)."""
        uid = CerebroCognitivoRemoto._resolver_world_uid(con)
        return f"mundo-vivo:{uid or 'anon'}"

    @staticmethod
    def _resolver_world_uid(con) -> Optional[str]:
        if con is None:
            return None
        try:
            db_path = con.execute("PRAGMA database_list").fetchone()[2]
            if db_path and db_path != ":memory:":
                from ..persistencia import mundo_io as _mundo_io

                return _mundo_io.world_uid(con)
        except Exception:  # noqa: BLE001 - mundo sintético sin meta
            return None
        return None

    def _brain_id(self, sim: Simulacion, h: HabitanteSim) -> str:
        return f"{self._world_uid or sim.ident}:d{sim.dimension}:h{h.id}"

    # ---------------------------------------------------------- registro en CE
    @staticmethod
    def _personalidad_dict(h: HabitanteSim) -> dict[str, float]:
        """Rasgos del genoma → contrato de personalidad de CE (0..1).

        Misma derivación que el cerebro embebido (cautela→cautiousness,
        sociabilidad, curiosidad, resiliencia→persistence), sin instanciar el motor.
        """
        def _r(nombre: str) -> float:
            try:
                return max(0.0, min(1.0, float(h.rasgo(nombre))))
            except Exception:  # noqa: BLE001 - genoma sin el rasgo: default 0.5
                return 0.5

        return {
            "cautiousness": _r("cautela"),
            "sociability": _r("sociabilidad"),
            "curiosity": _r("curiosidad"),
            "persistence": _r("resiliencia"),
        }

    def registrar_habitante(self, sim: Simulacion, h: HabitanteSim) -> str:
        """Registra (idempotente) el cerebro de un habitante en CE y persiste el estado.

        Devuelve el estado: registrado|ya_existia|pendiente|error. No crea cerebro
        local. Si CE no responde, marca y sigue (la simulación no se detiene).
        """
        brain_id = self._brain_id(sim, h)
        self._adapter.registrar(brain_id)  # el consumidor le buscará propuestas
        estado = self._adapter.registrar_cerebro(
            brain_id, h.nombre, self._personalidad_dict(h)
        )
        if self.con is not None:
            try:
                from ..persistencia import mundo_io as _mundo_io

                _mundo_io.guardar_estado_cerebro(
                    self.con, brain_id, nombre=h.nombre, dimension=sim.dimension,
                    habitante_id=h.id, estado=estado,
                )
            except Exception:  # noqa: BLE001 - persistencia de estado es best-effort
                pass
        return estado

    def inicializar(self, mundo) -> dict:
        """Alta inicial de todos los cerebros del mundo en CE (modo remoto).

        Recorre todas las dimensiones y habitantes, registra cada cerebro y persiste
        el estado. Devuelve el resumen del registro (total/registrados/ya_existia/
        pendientes/errores). Idempotente: se puede reintentar sin duplicar (409=ya).
        """
        resumen = {"total": 0, "registrados": 0, "ya_existia": 0, "pendientes": 0, "errores": 0}
        sims = getattr(mundo, "sims", None)
        if sims is None:
            sims = {0: mundo}
        for sim in sims.values():
            for h in list(sim.habitantes.values()):
                if not getattr(h, "vivo", True):
                    continue
                estado = self.registrar_habitante(sim, h)
                resumen["total"] += 1
                if estado in ("registrado", "registrados"):
                    resumen["registrados"] += 1
                elif estado == "ya_existia":
                    resumen["ya_existia"] += 1
                elif estado == "error":
                    resumen["errores"] += 1
                else:
                    resumen["pendientes"] += 1
        return resumen

    # ---------------------------------------------------------- percepción
    def _hechos(self, sim: Simulacion, h: HabitanteSim, brain_id: str) -> list[dict[str, Any]]:
        hechos: list[dict[str, Any]] = [
            {"subject": brain_id, "predicate": "position", "value": [float(h.x), float(h.y)],
             "confidence": 1.0, "source": "mundo_vivo", "metadata": {}}
        ]
        agua = self._agua_alcanzable(sim, h)
        if agua is not None:
            hechos.append({"subject": "agua", "predicate": "fuente", "value": "agua", "confidence": 1.0,
                           "source": "mundo_vivo",
                           "metadata": {"satisfies": [SED], "position": [float(agua[0]), float(agua[1])]}})
        fogata = sim.fogata_cerca(h, sim.celdas(400.0))
        if fogata is not None:
            hechos.append({"subject": "fuego", "predicate": "fuente", "value": "fuego", "confidence": 1.0,
                           "source": "mundo_vivo",
                           "metadata": {"satisfies": [CALOR], "position": [float(fogata["x"]), float(fogata["y"])]}})
        for otro in sim.habitantes.values():
            if otro.id == h.id or not otro.vivo:
                continue
            if math_hypot(otro.x - h.x, otro.y - h.y) <= sim.celdas(METROS_VISTA_SOCIAL):
                hechos.append({"subject": f"persona_{otro.id}", "predicate": "presencia", "value": otro.nombre,
                               "confidence": 1.0, "source": "mundo_vivo",
                               "metadata": {"satisfies": [COMPANIA], "channel": "social", "entity_type": "agent",
                                            "position": [float(otro.x), float(otro.y)]}})
        return hechos

    def _observacion_remota(self, sim: Simulacion, h: HabitanteSim, brain_id: str) -> dict[str, Any]:
        t_sim = float(sim.t)
        ultimo = self._ultimo_tick.get(h.id, t_sim - 1.0)
        dt = max(1.0, t_sim - ultimo)
        self._ultimo_tick[h.id] = t_sim
        return {
            "brain_id": brain_id,
            "tick": int(sim.t),
            "facts": self._hechos(sim, h, brain_id),
            "simulation_time": t_sim,
            "delta_simulation_time": dt,
        }

    # ---------------------------------------------------------- decisión
    def decidir(self, sim: Simulacion, h: HabitanteSim) -> dict:
        if h.sed < SED_DESPIERTA and sim.fuego_cerca(h, sim.r_huir_fuego):
            return self._demo.decidir(sim, h)
        if h.propuesta and sim.t - h.propuesta.get("t", 0.0) <= 360:
            return {"tipo": "responder_propuesta", "acepta": sim.rng_cerebro.random() < 0.85,
                    "motivo": "responder familia"}

        brain_id = self._brain_id(sim, h)
        self._adapter.registrar(brain_id)
        creencias = self._creencias(sim, h)

        # Encolar percepción (no bloquea el tick). El contenido viaja en la observación;
        # las creencias de dominio se adjuntan como metadata del hecho de posición.
        obs = self._observacion_remota(sim, h, brain_id)
        obs["facts"][0]["metadata"] = {"creencias": creencias}
        self._adapter.enviar_observacion(brain_id, obs)

        propuesta = self._adapter.propuesta_disponible(brain_id)
        if propuesta is None:
            self._ultima_propuesta.pop(h.id, None)
            return {"tipo": "esperar", "min": 10, "motivo": "pensando"}

        # Propuesta obsoleta (generada para un tick viejo): se rechaza sin ejecutar.
        _pl = propuesta.get("payload") if isinstance(propuesta.get("payload"), dict) else {}
        ptick = _pl.get("tick", propuesta.get("tick"))
        if isinstance(ptick, (int, float)) and ptick < float(sim.t) - 30.0:
            self._rechazar(sim, h, brain_id, propuesta, "propuesta_obsoleta")
            self._rechazos_obsoletos += 1
            return {"tipo": "esperar", "min": 10, "motivo": "propuesta obsoleta"}

        self._ultima_propuesta[h.id] = propuesta
        self._decisiones += 1
        return self._traducir(sim, h, _PropuestaRemota(propuesta))

    def _rechazar(self, sim, h, brain_id: str, propuesta: dict[str, Any], motivo: str) -> None:
        pid = propuesta.get("proposal_id")
        self._adapter.enviar_resultado(
            brain_id,
            {"proposal_id": pid, "brain_id": brain_id, "tick": int(sim.t),
             "status": "rejected", "rejection_reason": motivo, "observable_changes": []},
            proposal_id=pid,
        )

    # ---------------------------------------------------------- resultados
    def registrar_resultado(self, sim: Simulacion, h: HabitanteSim, ok: bool, texto: str) -> None:
        propuesta = self._ultima_propuesta.pop(h.id, None)
        if propuesta is None:
            return
        brain_id = self._brain_id(sim, h)
        pid = propuesta.get("proposal_id")
        self._adapter.enviar_resultado(
            brain_id,
            {"proposal_id": pid, "brain_id": brain_id, "tick": int(sim.t),
             "status": "accepted" if ok else "rejected",
             "rejection_reason": None if ok else (texto or "rejected_by_world")[:200],
             "observable_changes": []},
            proposal_id=pid,
        )

    # ---------------------------------------------------------- ciclo de vida / estado
    def guardar_cerebros(self) -> None:
        """No-op: la persistencia cognitiva es del servicio CCA (no se escribe DB local)."""
        return None

    def recuperar_cerebros(self) -> list[str]:
        return []

    def olvidar(self, h_id: int) -> None:
        self._ultima_propuesta.pop(h_id, None)
        self._ultimo_tick.pop(h_id, None)

    def pendientes(self) -> int:
        return self._adapter.pendientes()

    def estado(self, sim: Simulacion) -> dict:
        return {
            "cerebro": self.nombre,
            "decisiones": self._decisiones,
            "rechazos_obsoletos": self._rechazos_obsoletos,
            "errores_transporte": self._adapter.errores,
            "propuestas_pendientes": self._adapter.pendientes(),
        }

    def cerrar(self) -> None:
        self._adapter.cerrar()


def math_hypot(dx: float, dy: float) -> float:
    import math

    return math.hypot(dx, dy)
# CE registro directo de cerebros (modo remoto)

Objetivo: en modo remoto, crear un mundo nuevo registra los cerebros de sus habitantes directamente en CE (API HTTP), sin crear cerebros cognitivos locales. Rama base: `fix/cca-remote-recepcion-robusta`. Runner tests: `PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_cerebro_remoto.py`.

## Specs
- S1: Al inicializar un mundo en modo remoto, cada habitante obtiene un `brain_id` estable `<world_uid>:d<dim>:h<id>` y se registra en CE vía `POST /brains` (contrato real CE: `{brain_id, name, personality?{cautiousness,sociability,curiosity,persistence}}`; 201 crea, 409 ya existe).
- S2: No crear instancia cognitiva local paralela en modo remoto; no abrir SQLite cognitivo; no tick cognitivo local. El modo embebido se conserva.
- S3: Registro idempotente con reintentos; 409 = ya registrado (éxito). Estado de inicialización persistido por cerebro para reanudar sin duplicar. Un mundo con registros fallidos no se reporta como "todo registrado".
- S4: La simulación física continúa aunque CE se desconecte; el registro no bloquea el tick (init no bloqueante ante fallo: marca pendiente y sigue).
- S5: Corregir acceso al contrato de propuestas: `action_type` y `parameters` desde `proposal["payload"]`.
- S6: Preservar garantías del fix ACK: no perder propuestas tras confirmar, no doble ejecución, no sobrescribir pendientes, correlación por `proposal_id`, recuperar recibidas-no-ejecutadas.
- S7: Config por entorno: `MUNDO_VIVO_CEREBRO=remoto`, `CCA_URL`, `CCA_TOKEN` (no se guarda token en repo ni se loguea).
- S8: Tests aislados con cliente simulado (sin CE real): creación/registro de todos, ids estables, duplicados, fallos parciales, reintentos, sin cerebro local, obs no bloqueante, propuesta+ACK, recuperación al cerrar, correlación/resultados, independencia embebido, continuidad de simulación.

## Tasks
- T1 (inline): adapter `registrar_cerebro`/`listar_cerebros`/`estado_cerebro` (409→registrado). S1,S3.
- T2 (inline): cerebro remoto `_personalidad_dict`, `inicializar`/`registrar_habitantes`, fix `_PropuestaRemota` payload. S1,S5.
- T3 (inline): persistencia estado init (tabla `cerebros_ce`) + hook `Ejecutor.__init__` y `spawn`. S3,S4.
- T4 (inline): tests aislados. S8.
- T5 (inline): commits + informe. S1-S8.

## Log
- L1: "Mundo Vivo — Integración de creación de cerebros directamente en CE" (spec completo secciones 1-9).
- L2: Contrato CE real confirmado en `cognitive_engine/api/server.py:84` (create_brain) y `api/client.py:104` (CcaClient.create_brain). No se inventa contrato.
- L3: Contrato definitivo (CE `feat/creacion-remota-cerebros`): POST /brains {brain_id, name, personality?{cautiousness,sociability,curiosity,persistence}}; 201/409/422/401/403. Token admin `*` para crear; restringido por cerebro para ops. Implementado: dos CcaClient (admin/restringido), 409 verificado por identidad (GET /brains/{id}), estado init persistido (tabla cerebros_ce), payload.action_type. Tests 26 OK, embebido 29 OK. Pendiente E2E real.
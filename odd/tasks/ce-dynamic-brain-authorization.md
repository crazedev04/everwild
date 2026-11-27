# CE autorización dinámica de cerebros

Objetivo: integrar la concesión idempotente del token restringido sobre cada cerebro remoto, sin modificar CE ni sus contratos. Rama base: `feat/ce-registro-cerebros-remoto`. Runner enfocado: `PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_cerebro_remoto.py`.

## Specs
- S1: El adaptador conserva el token restringido exclusivamente en memoria y utiliza el cliente administrativo para `authorize_brain(token_restringido, brain_id)`.
- S2: `registrar_cerebro` autoriza después de crear con 201 y después de verificar identidad ante 409; no informa éxito hasta que la autorización termine.
- S3: Los fallos de autorización devuelven un estado `error` reintentable y se persisten como `error`, nunca como registrado; reaperturas y reintentos mantienen idempotencia.
- S4: Los inmigrantes usan el mismo `registrar_habitante`, por lo que atraviesan creación/verificación y autorización.
- S5: Sin `CCA_TOKEN_ADMIN`, el adapter conserva compatibilidad de token único administrativo y omite autorización dinámica innecesaria.
- S6: `404 unknown_token` produce un error claro sin exponer el token; el token restringido debe existir previamente en CE.
- S7: Se preservan `cerebros_ce`, reanudación, modo embebido y ausencia de permisos globales.
- S8: Pruebas aisladas cubren 201, 409, reintento idempotente, inmigrante, fallo reintentable, token ausente, token único y embebido sin regresiones. No se ejecuta E2E real.

## Tasks
- T1 (inline): adapter token restringido y autorización post-creación/verificación. S1-S3,S5-S7.
- T2 (inline): integración de estados y flujo de habitantes/inmigrantes sin cambios de contrato. S2-S4,S7.
- T3 (inline): pruebas aisladas de todos los casos. S8.
- T4 (inline): changelog, verificación y commits pequeños. S1-S8.

## Log
- L1: Solicitud de integrar autorización dinámica de cerebros en CE, conservando únicamente cambios en Mundo Vivo.
- L2: Estado base: `feat/ce-registro-cerebros-remoto`, HEAD `f40c65b`; `docs/RENDERER_ARCHITECTURE.md` y `package-lock.json` permanecen untracked y no se tocarán.
- L3: Contrato CE verificado: `CcaClient.authorize_brain` usa POST `/tokens/authorize`, idempotente; servidor exige admin y retorna `404 unknown_token` si falta el token objetivo.
- L4: Implementación inline completada: autorización posterior a 201/409, fallos `error`, compatibilidad de token único y persistencia del estado. Pruebas enfocadas: 33 passed.
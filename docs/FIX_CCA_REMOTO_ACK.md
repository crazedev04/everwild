# Fix CCA remoto — recepción robusta de propuestas

Rama: `fix/cca-remote-recepcion-robusta`. No mergeado ni pusheado. Base `da2bb28`.

## Comportamiento anterior (causa de la pérdida)

El adapter remoto enviaba el ACK de una propuesta **después de encolar** el
resultado, no después de enviarlo. Secuencia que perdía trabajo:

1. Llegaba una propuesta por `pending_proposals` (queda DELIVERED).
2. Mundo Vivo la encolaba y mandaba ACK → CCA la marca ACKNOWLEDGED y **deja de reenviarla**.
3. Si Mundo Vivo se cerraba antes de que el hilo emisor hiciera `send_result`,
   el resultado nunca salía y la propuesta ya estaba confirmada: **pérdida silenciosa**.

El ACK significaba "recibí", pero CCA lo interpretaba como "terminado".

## Cómo queda resuelto

- **ACK diferido**: el ACK se manda **sólo cuando el emisor confirma el envío
  exitoso del resultado** (`send_result` OK → `ack`). Recibir/entregar ya no confirma.
- **Recepción**: el hilo emisor reintenta acotado con el mismo `client_seq`
  (`msg_id` estable ⇒ idempotente en CCA). Si Mundo Vivo cierra en medio del envío,
  el ítem se **reencola** para que `cerrar()` lo vacíe con un último intento.
- **Persistencia**: no se agrega persistencia local nueva. La propuesta queda
  DELIVERED (no-ACK) hasta que el resultado sale.
- **Recuperación ante cierre**: al no confirmar hasta el envío, una propuesta
  recibida pero no consumida sigue DELIVERED y CCA la reexpone en
  `pending_proposals` tras reiniciar ⇒ se recupera sin estado local.
- **No doble ejecución**: `propuesta_disponible` saltea y marca `proposal_id` ya
  ejecutados; una reentrega de la misma propuesta no vuelve a disparar la acción.

## Qué garantizan los 14 tests (`tests/test_cerebro_remoto.py`)

1. ACK sólo tras enviar el resultado.
2. No hay ACK en la recepción.
3. Varias propuestas sin sobrescritura (una por habitante/balde).
4. Recepción duplicada no duplica caché.
5. No hay doble ejecución por reentrega.
6. `cerrar()` vacía el resultado pendiente (lo envía).
7. Resultado correlacionado por `proposal_id`.
8. Modo remoto no abre DB cognitiva local (no Service/Repository/Runtime/scheduler).
9. E2E con cliente simulado (obs → propuesta → resultado → ack).

## Archivos y commits del fix

- `src/mundo_vivo/agentes/remote/cca_adapter.py` — ACK diferido, reencole al cerrar,
  `_emitir` devuelve si envió, `_ejecutadas` para no doble ejecución.
- `src/mundo_vivo/agentes/cerebro_cognitivo_remoto.py` — pasa `proposal_id` al
  enviar resultado; ya no hace `ack` en recepción.
- `tests/test_cerebro_remoto.py` — 14 tests (9 previos + 5 de robustez).
- `CHANGELOG.md` — entrada del fix.

Commits:
- `89f2773` fix(cca-remoto): confirmar ACK sólo tras enviar el resultado.
- `6229bc1` docs(cca-remoto): registrar fix de ACK diferido y garantias.

## Fallo y 13 errores de la suite (preexistentes, ajenos a este fix)

Causa única: `mundo_vivo.motor.generador` **no existe**. `generar_mundo` se movió a
`mundo_vivo.generador.pipeline` (`src/mundo_vivo/generador/pipeline.py:426`) y
`src/mundo_vivo/motor/generador.py` fue eliminado. Los 13 tests de recolección
(`test_api`, `test_atencion`, `test_atributos`, `test_comunicacion`, `test_cultura`,
`test_dimensiones`, `test_estado_liviano`, `test_fenomenos_datos`,
`test_minerales_desconocidos`, `test_motor`, `test_objetivos`, `test_persistencia`,
`test_psique`) y `test_conservacion_datos` siguen importando la ruta vieja. Es un
refactor de módulo que no actualizó esos tests; no se tocó (fuera de scope).

## Estado para retomar E2E

Pendiente: E2E real contra servicio CCA. Requiere `../Cognitive Engine` en
`feat/distribution` con cerebros migrados, `CCA_URL`/`CCA_TOKEN`, y retirar imports
internos del embebido. La rama queda lista para retomar cuando CE esté levantado.
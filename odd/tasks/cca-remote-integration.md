# CCA remoto — primera integración (feature)

## Specs
- S1: Modo remoto configurable `MUNDO_VIVO_CEREBRO=remoto` sin eliminar el embebido (`cognitivo`).
- S2: `MundoVivoRemoteAdapter` usa SOLO API pública de CCA (`CcaClient`); no instancia Service/Runtime/Repository/scheduler.
- S3: Tick no bloquea: observaciones encoladas (hilo emisor), propuestas por consumidor independiente + caché por habitante; sin propuesta => esperar.
- S4: Correlación/idempotencia: brain_id estable, client_id estable por mundo, client_seq monótono por cerebro, msg_id estable en reintento, proposal_id correlaciona resultado; ACK tras entregar.
- S5: Mundo Vivo valida y ejecuta; propuesta inválida/obsoleta => rechazo local + resultado REJECTED a CCA.
- S6: No abrir/escribir la DB cognitiva local en modo remoto.
- S7: Sin migración destructiva; identidad/continuidad se documentan como pendiente.
- S8: No tocar UI/observabilidad; no push/merge; preservar untracked.

## Tasks
- T1 (inline): MundoVivoRemoteAdapter (cola+hilo emisor, consumidor pending_proposals, caché, seq, ack). tests unitarios con cliente falso.
- T2 (inline): CerebroCognitivoRemoto (subclase que reutiliza traducción; decide encola/lee caché; registrar_resultado envía+ack). tests.
- T3 (inline): cablear `crear_cerebro` remoto + ciclo de vida (start/close). regresión embebido.
- T4 (inline): test de integración contra CcaHttpServer real (distribución feat/distribution).

## Log
- L1: "Implementar primera integración remota con Cognitive Engine ... preservar simulación física y evitar que el tick espere una respuesta cognitiva."
- Inspección: CcaClient (REST+SSE, send_observation/pending_proposals/ack/expire/send_result). Observation payload lleva brain_id (extra=forbid); msg_id=obs|res:brain:client:seq (idempotente). Runtime sin sink deja propuestas PENDING expuestas por pending_proposals (contrato de entrega retry-until-ACK). Cerebro debe existir en repo de CCA (no hay endpoint de creación) => migración pendiente. Embebido usa MundoVivoAdapter.process síncrono.
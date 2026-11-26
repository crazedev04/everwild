# E2 — Recuperación de objetivos inalcanzables y ruptura de bucles

## Problema (mundo_709356039)

`satisfy_compania` proponía `ir_hacia` hacia un habitante no visible; el motor rechazaba
(`No ves a Elena; está lejos.`) y el cerebro reintentaba lo mismo tick tras tick: **1217 intentos,
0 éxitos**. Leo, Paula y Bruno quedaron congelados ~3000 t_min. El rechazo se registraba, pero no
degradaba la utilidad del objetivo ni generaba cooldown, y la histéresis lo mantenía seleccionado.

## Mecanismo

Memoria de fallos acotada por **(objetivo, destino, motivo)** en `decision/goal_failures.py`:

- `record(goal_id, target, reason, tick)`: acumula intentos; al llegar a `UMBRAL_FALLOS` (3) marca
  `cooldown_until = tick + COOLDOWN_TICKS` (200 min de mundo).
- `factores_cooldown(tick)`: devuelve `{goal_id: FACTOR_COOLDOWN}` (0.1) para objetivos en
  cooldown vigente; el árbitro multiplica la utilidad del objetivo por ese factor, así una
  alternativa gana sin prohibir el objetivo para siempre.
- `clear_goal` (tras un éxito) y `clear_target` (el destino vuelve a ser visible) permiten
  reconsiderar. También expira el cooldown por tiempo.
- Acotada a `MAX_REGISTROS` (64), determinista (orden por goal/target/reason).

Integración:

- `DeliberationState.failures` vive entre ticks y se persiste.
- `GOAPDecisionEngine.select_action`: calcula `goal_penalties` y los pasa al `GoalArbiter`; tras
  construir creencias, si hay `visible_target` limpia su historial (reconsideración).
- `register_result_for_plan(accepted, reason, tick, target)`: registra el fallo o limpia en éxito.
- `brain.apply_result` pasa `tick` y `target` de la propuesta.
- Persistencia: migración `v10` añade `brains.goal_failures_json`; `save`/`load` lo serializan.

## Decisiones

- **No se penaliza `ir_hacia` globalmente**: la clave incluye destino; un destino inaccesible no
  bloquea a otros. La penalización es a nivel objetivo pero sólo mientras su destino esté en
  cooldown; otro destino visible limpia su historial.
- **No se reduce COMPANIA ni se simula interacción**: la necesidad queda intacta; sólo cambia la
  prioridad del objetivo.
- **No siempre `explorar`**: al penalizar `satisfy_compania`, gana la mejor alternativa según el
  estado real (necesidad, oportunidad, reposo).
- **Reconsideración**: por cooldown expirado, por éxito, o por destino visible. Nunca prohibición
  permanente.

## Otros objetivos (§6)

`buscar`, `ir_hacia_pareja`, `buscar_pareja` son acciones del puente MV bajo el mismo objetivo
`satisfy_compania`/`satisfy_pareja`; el mecanismo es genérico por `goal_id`, así que cubre esos
casos sin penalización indiscriminada. No se tocó su semántica.

## Pruebas

- CE `tests/unit/test_goal_failures.py` (13): umbral, cooldown, destino/motivo no contaminan,
  expiración, éxito limpia, visible limpia, acotada, roundtrip, penalización del árbitro, registro
  del engine, independencia, persistencia.
- MV `tests/test_e2_recuperacion.py` (4): regresión Leo/Paula/Bruno — cooldown + alternativa,
  reconsideración tras cooldown, historiales independientes, éxito limpia; COMPANIA intacta.
- Ajuste `test_memetic_persistence.py`: la prueba de downgrade a v7 ahora borra también la
  migración v10.

## No tocado

Generación de mundos, terreno/biomas/navegación general, `world_uid`/aislamiento E1, persistencia
de mundos existentes, necesidades, personalidades. Sin commits. No se reanudó `mundo_709356039`.

## Verificación

Ver `CHANGELOG.md` para el resultado de las suites MV y CE, ruff y comprobaciones.
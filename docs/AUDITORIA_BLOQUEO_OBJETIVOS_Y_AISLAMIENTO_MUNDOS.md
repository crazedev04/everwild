# Auditoría — Bloqueo de objetivos y aislamiento cognitivo entre mundos

> SOLO LECTURA. No se modificó código, bases, mundos ni simulaciones. `mundo_709356039` quedó
> pausado. SQL sólo SELECT/PRAGMA. Fecha: 2026-11-26.
> Proyectos: Mundo Vivo (`src/mundo_vivo/...`) y Cognitive Engine (`/home/cracken/Mimundo/Cognitive Engine/src/...`).

## 1. Resumen ejecutivo

- **P1 (objetivos imposibles) — CONFIRMADO**: Leo/Paula/Bruno replanifican el MISMO objetivo
  `satisfy_compania` cada tick y el motor rechaza `ir_hacia` ("No ves a Elena; está lejos."). El
  rechazo se procesa (drift, memoria episódica, refuerzo, supervisión de plan) pero **no reduce la
  necesidad COMPANIA** (sólo la sacia interactuar), **no marca a Elena como inalcanzable** (el
  `mark_depleted` exige un parámetro `target` que `ir_hacia` no usa) y **no hay cooldown/abandono**.
  La histéresis por `persistence` refuerza quedarse en ese objetivo. Resultado: bucle infinito.
- **P2 (aislamiento) — CONFIRMADO, roto**: todos los mundos de un mismo `datos/mundos/` comparten
  **un único** `cerebros_cognitivos.db`, y el `brain_id` es `mundo:d0:hN` con `ident="mundo"`
  genérico (no único por mundo). Dos mundos con habitantes `h1..hN` **colisionan y se sobrescriben**
  (PK `brain_id`, `ON CONFLICT DO UPDATE`). La recuperación carga por `brain_id`, así que un mundo
  puede recuperar el cerebro de otro. El scheduler sí es por mundo (por instancia), el repositorio no.
- **P3 (relación) — CONFIRMADO**: la contaminación explica los skills/contadores CCA que no coinciden
  con las acciones reales (p. ej. `ir_al_agua` success 108 para Leo en CCA vs 0 en este mundo).

## 2. Evidencia y archivos inspeccionados

- Mundo: `mundo_709356039.db` (4 hab: Elena/Leo/Paula/Bruno; `decisiones.modelo=cognitive-engine`).
- CCA: `cerebros_cognitivos.db` (10 brains `mundo:d0:h1..h10`; h1..h4 actualizados 15:50, h5..h10 de otro mundo).
- Otro mundo: `cognitiveAI.db` (10 hab, 1792 chunks) — misma carpeta, misma base CCA.
- Código: `agentes/cerebro_cognitivo.py`, `motor/vida.py`, `motor/simulacion.py`,
  `persistencia/sim_io.py`; CE `core/brain.py`, `decision/engine.py`, `decision/goal_selection.py`,
  `planning/plan_manager.py`, `persistence/repository.py`, `api/service.py`, `adapters/mundo_vivo.py`.

## 3. Flujo real de `satisfy_compania` (paso a paso)

1. **Necesidad**: `_necesidades` (cerebro_cognitivo.py:407) calcula `COMPANIA` vía `_compania_de`
   (:507) = f(hace cuánto no habla). No baja por cercanía, sólo por interacción.
2. **Arbitraje (Utility)**: `goal_selection.py` puntúa objetivos por necesidad+personalidad+histéresis;
   `satisfy_compania` gana mientras COMPANIA esté alto. `hysteresis_by_persistence` (:66, bonus :265)
   **favorece repetir** el objetivo vigente.
3. **Plan (GOAP)**: `engine._replan` (:155) planifica `ir_hacia` (precond `PERSONA_LEJOS`, efecto
   `PERSONA_CERCA`; reg :308). Belief `PERSONA_LEJOS` = hay alguien lejos (`_alguien_lejos`, :773).
4. **Acción**: `_t_ir_hacia` (:1267) devuelve `{"tipo":"ir_hacia","a":<id>}`.
5. **Motor**: `simulacion._accion_ir_hacia` → `vida._accion_ir_hacia` (:277) rechaza con
   `"No ves a %s; está lejos."` (:283) si el objetivo no es visible. `ok=False`.
6. **Feedback**: `registrar_resultado` (:1401) → `adapter.result_from_world(ok=False)` →
   `ActionStatus.REJECTED` → `brain.receive_result` (brain.py:433).
7. **Efectos del rechazo** (brain.py:454-509): drift `CHRONIC_FAILURE`, episódica (importance 0.4),
   `learner.update_from_result`, `register_result_for_plan(accepted=False)`,
   y `mark_depleted(params["target"])` **sólo si existe clave `target`**.
8. **Plan**: `plan_manager.register_step_result` (:51) hace `plan.fail()` + `clear_plan()`.
9. **Siguiente tick**: sin plan usable → `_replan` mismo objetivo (COMPANIA sigue alto, `PERSONA_LEJOS`
   sigue True) → `ir_hacia` otra vez. Bucle.

## 4. Causa concreta de los reintentos — CONFIRMADA

Tres hechos, todos en código:
- **La necesidad no baja con el rechazo**: COMPANIA sólo la sacia `hablar/ensenar/proponer_hijo/
  responder_propuesta` (registrar_resultado :1423-1429). `ir_hacia` fallido no toca COMPANIA.
- **No se marca inalcanzable**: `mark_depleted` (brain.py:505) requiere `"target" in params`; `ir_hacia`
  usa `{"a": id}` (cerebro_cognitivo.py:1269). Elena **nunca** se marca agotada.
- **Sin abandono/cooldown**: no hay contador de fallos por objetivo ni penalización de utilidad por
  rechazos; `goal_selection` sólo pondera necesidad+personalidad+histéresis (que refuerza repetir).

Por qué miles de negativos no cambian nada: cada rechazo se registra (memoria/refuerzo) pero **ninguna
vía realimenta la utilidad del objetivo ni la creencia de alcanzabilidad**. El refuerzo
(`learner`) ajusta costo de la habilidad, no la elección del objetivo; y los skills quedan con
`failure_count=0` en la base (ver §7), así que ni el aprendizaje marca el patrón.

Mecanismos similares para otros objetivos imposibles — CONFIRMADO: `buscar` (:309),
`ir_hacia_pareja`/`buscar_pareja` (:326-339) comparten el patrón (precond `*_LEJOS`, sin `target`).
Cualquier objetivo "ir a entidad lejana" sufre el mismo bucle. `mark_depleted` sólo ayuda a acciones
con `target` (p. ej. juntar recurso).

## 5. Arquitectura actual de persistencia cognitiva

- **Un archivo por carpeta, no por mundo**: `cerebro_cognitivo.py:200-212` fija
  `cerebros_db = Path(world_db).parent / "cerebros_cognitivos.db"`. Todos los mundos de
  `datos/mundos/` usan el MISMO archivo.
- **brain_id no único por mundo**: `:548` `brain_id=f"{sim.ident}:d{sim.dimension}:h{h.id}"`.
  `sim.ident` = `d.get("ident") or "mundo"` (sim_io `cargar_simulacion`); `dimensiones` vacío (0 filas)
  ⇒ `ident="mundo"`. Resultado: `mundo:d0:h1` idéntico en todos los mundos.
- **Repositorio keyado por brain_id**: `repository.py` `brains(brain_id TEXT PRIMARY KEY)` (:139-140);
  `save` `ON CONFLICT(brain_id) DO UPDATE` (:351-357); tablas hijas FK `brain_id` (needs, episodic,
  semantic, skills, spatial, milestones, brain_events). Sin columna de mundo.
- **Scheduler por instancia**: `CognitiveEngineService` crea `MultiBrainScheduler()` por servicio
  (service.py), y hay un servicio por `CerebroCognitivo` (por simulación). El scheduler **no** se
  comparte; el **repositorio (archivo) sí**.
- **Recuperación por brain_id**: `_estado_persistido` (:633-642) → `repo.load(brain_id)`;
  `AutonomousBrain.load` (brain.py:586). Carga por `brain_id` únicamente.

## 6. Mapa de identidades, servicios, repositorios, bases

- Identidad: `BrainIdentity(brain_id="mundo:d0:hN")`. No incluye semilla ni nombre de mundo.
- Servicio: `CognitiveEngineService` por simulación; scheduler por simulación.
- Repositorio: `SQLiteBrainRepository(cerebros_cognitivos.db)` — **compartido** por todos los mundos
  de la carpeta.
- Bases: `mundo_*.db` (por mundo, aislado) | `cerebros_cognitivos.db` (compartido) |
  `cognitiveAI.db` (mundo aparte, mismo archivo CCA).

## 7. Riesgos concretos de contaminación — CONFIRMADOS

- **Colisión de brain_id**: mundo A (h1..h4) y mundo B (h1..h10) con `ident="mundo"` →
  `mundo:d0:h1..h4` colisionan. `save` sobrescribe (`ON CONFLICT DO UPDATE`).
- **Contadores que no cuadran**: CCA da a Leo `ir_al_agua success=108`, pero este mundo registró **0**
  `ir_al_agua` para Leo (entrenamiento). Esos 108 vienen del otro mundo (B) que sí usó `ir_al_agua`.
- **Recuperación cruzada**: al reiniciar A, `load("mundo:d0:h1")` puede traer el cerebro escrito por B
  (recuerdos, skills, metas de otro mundo).
- **Memorias/habilidades mezcladas**: episodic/semantic/skills comparten PK `brain_id` sin mundo.
- **Simultáneo**: dos mundos activos a la vez escriben el mismo archivo y los mismos ids → caras de la
  misma moneda, se pisan.
- **Dos semillas distintas**: irrelevante; el id no usa semilla, así que la colisión persiste.

## 8. Qué funciona correctamente

- Scheduler y servicio por simulación (no comparten runtime).
- `mundo_*.db` sí aislado por mundo (mapa, habitantes, decisiones, `entrenamiento_cerebro`).
- `decisiones.modelo=cognitive-engine` y `latencia_ms=0` correctos.
- El rechazo del motor es correcto (no es bug de navegación): "está lejos" es verdad.
- P0/P1/P2 del agua funcionan (ver auditoría previa): sin bloqueo de sed.

## 9. Qué falta para aislamiento completo

- Identificador de mundo **persistente e inequívoco** (semilla+nombre, o UUID de mundo) en `brain_id`.
- Base CCA **por mundo** (archivo por mundo, o columna `world_id` en todas las tablas y en todo
  load/save/consulta).
- Que `ident` no sea genérico ("mundo"): usar identidad real del mundo en `sim.ident` o en el prefijo.
- Verificar aislamiento en scheduler, cachés, listeners y consolidación (no sólo archivo).
- Migración de la base compartida existente (fuera de alcance; no ejecutada).

## 10. Arquitectura recomendada (no implementada)

- `brain_id = f"{world_uid}:d{dim}:h{h.id}"` con `world_uid` persistente (p. ej. semilla, o UUID
  guardado en `meta` del mundo).
- **Un `cerebros_cognitivos.db` por mundo** (mismo nombre que el mundo: `cerebros_<world>.db`), o
  añadir `world_uid` como PK compuesto en `brains` y FK en todas las tablas, con todo load/save
  filtrado por `world_uid`.
- Servicio/scheduler por mundo (ya), repositorio scoped por mundo.
- Recuperación que exige `world_uid` + `brain_id`; nunca carga por `brain_id` solo.

## 11. Orden de implementación sugerido

1. `world_uid` estable en `meta` del mundo; usarlo en `sim.ident`/`brain_id`.
2. Repositorio: `world_uid` en esquema (PK compuesto) y en `save`/`load`/queries.
3. Archivo CCA por mundo (o validación de `world_uid` al abrir).
4. Recuperación y scheduler scoped; probar reinicio A con B vivo.
5. (Objetivos) marcar inalcanzable con la clave correcta (`a`/`target`), cooldown por objetivo, y
   realimentar fallos a la utilidad.

## 12. Pruebas necesarias (para cuando se autorice)

- Dos mundos, mismos ids locales, activo cada uno: brains/recuerdos/skills no se mezclan.
- Reiniciar A con B corriendo: A recupera sólo lo suyo.
- Servicio cognitivo reiniciado: no aparecen cerebros de otro mundo.
- `ir_hacia` a entidad inalcanzable: tras N rechazos el objetivo se abandona/enfría y elige otro.
- Idéntica semilla en dos mundos: `brain_id` distintos (por `world_uid`).
- Skills/contadores CCA coinciden con acciones del mundo (no de otro).

## 13. Respuestas finales

1. **¿Por qué siguen intentando objetivos imposibles?** Porque el rechazo no baja la necesidad
   COMPANIA, no marca la meta como inalcanzable (`mark_depleted` usa `target`, `ir_hacia` usa `a`) y no
   hay cooldown; la histéresis refuerza el mismo objetivo. CONFIRMADO.
2. **¿Cada mundo tiene su propia identidad y persistencia?** No. `brain_id` genérico + archivo CCA
   compartido. CONFIRMADO.
3. **¿Puede un mundo leer/escribir datos de otro?** Sí, por colisión de `brain_id` en el archivo
   compartido (escritura y recuperación). CONFIRMADO.
4. **¿Qué cambios garantizan aislamiento?** `world_uid` persistente en `brain_id`, base/tabla scoped
   por mundo, y load/save filtrados por `world_uid`; más fix del bucle de objetivos. NO IMPLEMENTADO.
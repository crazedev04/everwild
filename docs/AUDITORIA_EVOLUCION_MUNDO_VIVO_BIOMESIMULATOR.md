# Auditoría de evolución — Mundo Vivo (estado local actual) vs BiomeSimulator

**Fecha:** 2026-11-26.
**Alcance:** auditoría técnica de SOLO LECTURA del estado local de Mundo Vivo
(`~/Mimundo/mundo-vivo`), con BiomeSimulator como referencia externa. No se modificó código,
mundos, semillas, bases de datos, configuraciones ni simulaciones; no se alteró CCA; sin commits.
**Referencia externa:** https://github.com/andrenepomuceno/BiomeSimulator (docs `project-specification`,
`architecture`, `simulation/ai`, `simulation/plants`, `renderer/overview`).
**Documento previo:** `docs/AUDITORIA_BIOMESIMULATOR.md` ya cubre 13 sistemas en detalle; este
documento lo complementa con arquitectura verificada, interfaz, investigación de movimiento,
checklist E1 y roadmap. No lo duplica.

---

## 1. Estado real de Mundo Vivo (verificado en código)

- **Motor y ciclo:** `motor/simulacion.py` (`Simulacion` armada con mixins: `vida`, `ecologia`,
  `frio`, `conservacion`, `alimentacion`, `atributos`, `atencion`, `fenomenos_datos`, `objetivos`,
  `psique`, `propagacion`, `tecnologia`). Un `Simulacion` por dimensión (`motor/mundo.py`).
- **Generación:** `generador/` (pipeline modular; `motor/generador.py` es shim). Mundo data-driven:
  materiales, biomas, recetas, fenómenos, minerales son JSON (`datos_base/` + `datos/extra/`).
- **Terreno/biomas/agua/navegación:** `motor/biomas.py`, `motor/navegacion.py` (A* con
  `Terreno.buscar_camino`, costo en dos representaciones `costo`/`_c`), `motor/senderos.py`.
  Escala métrica (`Simulacion.celdas()`, `tam_celda_m`).
- **Flora/fauna/recursos/ecología:** `motor/ecologia.py`, `motor/fauna.py`, `motor/propagacion.py`
  (colonias), `motor/minerales.py` (minerales inventados por dimensión), `motor/conservacion.py`.
- **Habitantes:** `agentes/` (`CerebroHibrido`, `CerebroCognitivo`), `motor/psique.py`,
  `motor/objetivos.py`, `motor/atributos.py`, `motor/atencion.py` (LOD cognitivo).
- **CCA:** puente `agentes/cerebro_cognitivo.py` + adaptador `MundoVivoAdapter` (proyecto aparte
  `Cognitive Engine`). Motor valida, cerebro propone. Seleccionable por entorno.
- **Persistencia/aislamiento:** `persistencia/sim_io.py`, `persistencia/mundo_io.py` (`world_uid`),
  base cognitiva por mundo `cerebros_<world_uid>.db`. Ver §5.
- **Interfaz:** `ui/` (`index.html`, `vivo.js`, `mapa.js`, `sprites.js`, `estilo.css`), WS
  `/ws/<mundo>`, API `/api/mundos/...`. Sprites dibujados en código.
- **Rendimiento:** bucle 20 Hz, estado 10 Hz; `tope_pensando()` limita velocidad por latencia
  cognitiva; LOD cognitivo; optimizaciones A* y sprites radiales (commits recientes).

## 2. Comparación con BiomeSimulator (resumen; detalle en doc previo)

| Eje | BiomeSimulator | Mundo Vivo | Complemento |
|-----|----------------|------------|-------------|
| Motor | Worker + engine puro (sin DOM/React/Pixi), tickFlora→fauna→cleanup | `Simulacion` Python, mixins por sistema, multi-dimensión | World-in-Worker es patrón; MV ya separa motor de UI/CCA |
| IA | Reglas + prioridades estrictas (P1 sed…P9 idle) | CCA (Utility AI + GOAP) determinista; híbrido con LLM opcional | NO reemplazar CCA. Tomar de BS la claridad de prioridades y "acción en curso continúa" |
| Flora | Stages semilla→brote→adulto→fruto→muerto; `effectiveAge` con agua/terreno/estación/crowding | `ecologia`/`conservacion`/`propagacion`, JSON | BS aporta modelo de `effectiveAge` y limpieza de tile por sucesión |
| Fauna | 18 especies, sub-tile 0.25, A* tile, ocupación por cruce | Fauna + `senderos` por desgaste, escala métrica | BS aporta sub-tile y costos por terreno; MV ya tiene costo por bioma |
| Clima/estaciones | ticks/día, día_fraction, is_night, modificador visión | `reloj.py`, `frio.py`, día/noche en UI | BS aporta estaciones estacionales y modificador de visión por período |
| Rendimiento | ~1000×1000, ≥1000 animales, worker + sub-workers | 2048×2048 a 5 m; LOD cognitivo; A* optimizado | BS aporta sync incremental/delta y sub-workers; MV ya tiene LOD |
| Observabilidad | inspector, minimapa, stats, entity summary, report histórico, audio | panel, mapa, eventos, ficha; sin minimapa ni report histórico | BS aporta inspector de entidades, minimapa, report de tendencias |
| UI | Zustand único, capas Pixi, menú save/load | JS vanilla + Canvas, WS | BS aporta separación estricta y inspector; MV necesita rediseño (§4) |

**Qué NO copiar de BS:** su IA de reglas (reemplazaría CCA), su modelo single-map sin dimensiones,
su almacenamiento Uint8 de ids fijos (MV es data-driven), y su licencia (Apache-2.0) en código
portado sin adaptación.

## 3. Sistemas a incorporar/adaptar (sin duplicar cognición)

- **Observabilidad de comportamiento** (inspector de entidades, minimapa, report histórico de
  tendencias) — BS lo tiene maduro; MV carece.
- **Modelo de crecimiento vegetal `effectiveAge`** (agua×terreno×estación×crowding) como dato.
- **Estaciones** y modificador de visión por período (nocturno/diurno) sobre la percepción.
- **Sync incremental/delta** y sub-workers para escalabilidad (MV ya tiene LOD; BS complementa).
- **Costos de movimiento por terreno** y sub-tile (MV ya tiene costo por bioma; BS refina).

## 4. Problemas de interfaz (verificado)

- **Cambio de dimensión/mundo deja paneles viejos (CONFIRMADO).** `ui/vivo.js`:
  `armarDimensiones` (líneas 104-118) al cambiar de dimensión sólo llama `MV_abrirMapa`
  (recarga capas del mapa) y actualiza el `<select>`. **No** limpia `V.habs`, `V.eventos`,
  `V.efectos`, ni refresca paneles (`recetas`, `fauna`, `familias`, `era`, lista `habitantes`).
  Sólo `alAbrir` (línea 71, cambio de mundo completo) resetea esos estados. Resultado: tras
  cambiar de dimensión, mapa nuevo pero habitantes/eventos/paneles del anterior hasta recarga
  manual. **Parcialmente implementado** (el reset existe para cambio de mundo, no para dimensión).
- **Falta rediseño integral de UI**: hoy es panel + mapa + eventos + ficha. No hay vista general
  del mundo, ni inspector de habitante robusto, ni minimapa, ni report histórico.
- **Arquitectura UI propuesta (respeta separación UI/motor/CCA):**
  - `estadoUI` único por mundo (reset total al cambiar mundo/dimensión).
  - Capa de datos: WS `/ws/<mundo>` (estado vivo) + `/api/mundos/<n>/...` (detalle bajo demanda).
  - Paneles: (a) general del mundo (población, biomas, clima, tendencias), (b) inspector de
    habitante (necesidades, objetivo CCA, plan, historial, posición), (c) eventos históricos,
    (d) minimapa con salto de cámara, (e) herramientas de observación (filtros, LOD).
  - Regla: la UI nunca muta motor/CCA; sólo lee estado y envía comandos.

## 5. Investigación: habitantes que "no se mueven" tras reiniciar

Mundos observados (solo lectura): `mundo_709356039` (uid `b9dff…`) y `mundoprueba2`
(uid `8dec…`). Ambos `velocidad=100`, vivos.

**mundo_709356039** (t=30005): `ir_hacia` 0/705 (rechazo por visibilidad, histórico), pero E2 ya
activo: `explorar` 233/308 ok, `esperar`/`wait` ok. Objetivos actuales (cerebros):
h1 `idle`, h2 `satisfy_sed`, h3 `idle`, h4 `explore_environment`. h4 se mueve
(`explorar` "Vas hacia tu destino", pos 1266,1289). `goal_failures` con 2 registros (cooldown E2).
→ No bloqueado: E2 enfrió `ir_hacia` y el habitante alterna; algunos exploran.

**mundoprueba2** (t=21113): **cero** acciones de movimiento (`ir_hacia`/`explorar` no aparecen).
Reparto: `esperar` 1195, `wait` 356, y actos sin locomoción (`beber`, `fabricar`, `inventar`,
`ensenar`, `hablar`). Objetivos actuales: h1 `idle`, h2 `satisfy_herramientas`, h3 `idle`,
h4 `satisfy_sed`. `goal_failures` vacío (sin cooldown). Posiciones agrupadas (~485-489, ~451-458).
→ **No es bloqueo de E2 ni de scheduler/persistencia.** Es que el árbitro elige `idle`/`satisfy_*`
y `explore_environment` no gana; sin objetivo locomotor, no hay desplazamiento. Necesidades
satisfechas (sed/hambre/energía en rango) → sin urgencia; `idle_utility=0.5` y las secundarias
empatan/superan a la curiosidad. Deciden (fabrican, enseñan, hablan) pero no se mueven.

** UI vs motor:** la UI lee posición del estado vivo WS (`vivo.js` 160-164, `h.x/h.y`), no del
snapshot `habitantes.estado` del DB (que no guarda x,y). La posición en cerebros (`position_json`)
sí cambia (h4). → El "no se mueve" es real (objetivos idle), no un artefacto de UI.

**Qué medir en una 2ª etapa (instrumentación faltante):** por tick y habitante: objetivo elegido +
utilidad de cada candidato (incl. `explore_environment`), `goal_penalties`, `visible_target`,
plan GOAP, acción traducida, aceptación del motor, y delta de posición. Hoy sólo hay `decisiones`
(accion/ok/resultado) y `position_json`; falta el ranking de utilidades y el estado del plan.

## 6. Checklist E1 / aislamiento entre mundos (verificada punto por punto)

1. **Inspección del board y metadatos de creación — COMPLETADO Y VERIFICADO.** `mundo_io.crear_mundo`
   persiste `meta` (incl. `world_uid`); `dimensiones` 0 = mundo base. Código + tests.
2. **Persistencia del identificador del mundo — COMPLETADO Y VERIFICADO.** `mundo_io.world_uid(con)`
   lee/genera y persiste en `meta`; estable tras reabrir. Test `test_2_world_uid_persistente`.
3. **UID para cerebros y bases individuales — COMPLETADO Y VERIFICADO.**
   `cerebro_cognitivo.py`: `brain_id={world_uid}:d{dim}:h{id}` y `cerebros_<world_uid>.db`.
   Verificado en los dos mundos (archivos `cerebros_b9dff…db`, `cerebros_8dec…db`).
4. **Pruebas de aislamiento — COMPLETADO Y VERIFICADO.** `tests/test_aislamiento_cognitivo.py` (10),
   incluidas en suite MV `515 passed`.
5. **Otros pendientes de checklist — NO APLICA / sin evidencia de pendientes.** No hay ítems E1
   abiertos en código/tests; los checkboxes sin marcar del agente son de interfaz, no de E1.

**Memoria persistente (Engram):** ACTIVA y verificada (se usa en esta sesión). No requirió
habilitación manual.

## 7. Riesgos y dependencias

- Rediseño UI depende de estabilizar el contrato WS/API y de reset total por mundo/dimensión.
- Instrumentación de movimiento requiere tocar el puente (registro de ranking/plan) — fuera de esta
  auditoría.
- Cualquier cambio de percepción/estaciones toca `atencion`/`reloj` (riesgo de regresión cognitiva).
- No reanudar mundos reales para probar; usar fixtures aislados.

## 8. ROADMAP PROPUESTO

### A. Observabilidad y diagnóstico de comportamiento
- **Problema:** no se ve por qué un habitante no se mueve (falta ranking de utilidades/plan).
- **Beneficio:** diagnóstico directo de bucles y objetivos.
- **Dependencias:** instrumentar puente CCA (solo lectura de estado interno).
- **Riesgo:** bajo (no altera simulación). **Prioridad:** alta. **Aplica:** frontera MV↔CCA.

### B. Corrección del cambio de mundo en la interfaz
- **Problema:** paneles con datos del mundo anterior al cambiar dimensión/mundo.
- **Beneficio:** UI coherente sin recarga manual.
- **Dependencias:** reset total de `estadoUI` en `armarDimensiones`/`alAbrir`.
- **Riesgo:** bajo. **Prioridad:** alta. **Aplica:** MV (UI).

### C. Rediseño integral de UI e inspección de habitantes
- **Problema:** falta vista general, inspector de habitante, minimapa, report.
- **Beneficio:** observación a 3 niveles (entidad/región/histórico) como BS.
- **Dependencias:** B; contrato WS/API estable.
- **Riesgo:** medio (superficie grande). **Prioridad:** media-alta. **Aplica:** MV (UI).

### D. Mejoras ecológicas y ambientales
- **Problema:** crecimiento vegetal y estaciones menos ricos que BS.
- **Beneficio:** `effectiveAge` (agua×terreno×estación×crowding), estaciones, visión por período.
- **Dependencias:** datos JSON; no tocar cognición.
- **Riesgo:** medio (percepción/estaciones afectan decisiones). **Prioridad:** media. **Aplica:** MV (motor).

### E. Rendimiento y escalabilidad
- **Problema:** escalar a más habitantes/mapas.
- **Beneficio:** sync incremental/delta, sub-workers; MV ya tiene LOD y A* optimizado.
- **Dependencias:** instrumentación de hotspots.
- **Riesgo:** medio. **Prioridad:** media. **Aplica:** MV (motor/UI).

### F. Evolución de la integración con CCA (sólo si hay necesidad real)
- **Problema:** `explore_environment` pierde contra `idle`/secundarias sin urgencia; falta
  visibilidad del ranking.
- **Beneficio:** que la exploración/Oportunidades compitan mejor sin forzar movimiento.
- **Dependencias:** A (instrumentación) para confirmar la causa.
- **Riesgo:** medio (afecta selección de objetivos). **Prioridad:** baja-media (confirmar antes).
- **Aplica:** CCA + frontera.

---

**Confirmación:** no se modificó código, mundos, bases de datos, configuraciones ni simulaciones;
no se tocó CCA; sin commits ni push. Cambios locales preexistentes intactos.
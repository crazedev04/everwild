# Auditoría comparativa: BiomeSimulator (JS) vs Mundo Vivo (Python)

**Alcance:** análisis técnico comparativo de 13 sistemas. **No se modifica código en este documento.**
**Fuente externa:** `https://github.com/andrenepomuceno/BiomeSimulator` (Apache License 2.0), clon shallow en `/tmp/opencode/BiomeSimulator`.
**Fuente local:** `~/Mimundo/mundo-vivo`, proyecto Engram `everwild`.
**Restricciones respetadas:** no conversión a JS, no reemplazo del motor, no modificación de BD ni del mundo `ww`, no tocar CCA, no eliminar funcionalidad, preservar semillas/reproducibilidad, respetar licencias.

Cada sistema sigue la plantilla: (1) cómo funciona en BiomeSimulator, (2) archivos/algoritmos, (3) cómo funciona en Mundo Vivo, (4) ventajas de cada uno, (5) qué portar/adaptar, (6) incompatibilidades, (7) tests necesarios.

---

## 1. Generación de terreno

**(1) BiomeSimulator:** terrain via fBM Perlin-like noise + island mask (blobs gaussianos) + edge falloff (costa orgánica) + sea level adaptativo (percentil garantiza min_land_ratio) + ríos (descenso greedy del heightmap con wobble, ensanchamiento downstream, puentes de barro) + BFS de proximidad al agua + detalle secundario (fértil/barro). Semilla mulberry32. Grid tipado (Uint8Array).

**(2) Archivos/algoritmos:** `src/engine/mapGenerator.js` (generateTerrain, fbmNoise, perlinNoise2D, generateIslandMask, generateEdgeFalloff, generateRivers, computeWaterProximity); `src/engine/world.js` (WATER..MUD 9 ids, Clock, grids paralelos). ~542 LOC mapGenerator.

**(3) Mundo Vivo:** `src/mundo_vivo/generador/pipeline.py` (~657 LOC) + `motor/ruido.py` + `motor/mundo.py` + `motor/biomas.py`. Generación de dimensiones, biomas JSON, cavernas, escala `tam_celda_m` (5 m mundos nuevos, 50 m mundos chicos de test), `Simulacion.celdas()`. `motor/generador.py` es shim.

**(4) Ventajas:** BiomeSimulator tiene ríos con meandro y barro, sea level adaptativo, water proximity precomputado. Mundo Vivo tiene cavernas, multi-dimensión, escala métrica real y biomas como datos, sistema de mineralogía.

**(5) Portar/adaptar:** algoritmo de ríos (greedy downhill con ruido) como nuevo módulo de generación data-driven; water proximity BFS como optimización precomputada (Mundo Vivo ya tiene `_agua_ady_mask` parcial); sea level adaptativo por percentil.

**(6) Incompatibilidades:** BiomeSimulator es 2D single-map sin cavernas ni dimensiones; su terrain es Uint8 con 9 ids fijos, Mundo Vivo es data-driven con biomas JSON. BiomeSimulator no tiene escala métrica.

**(7) Tests:** generar mundo con semilla fija y comparar hash del terrain; verificar min_land_ratio; verificar que ríos lleguen a agua; verificar reproducibilidad.

---

## 2. Clima / estaciones / ciclos

**(1) BiomeSimulator:** `Clock` con ticks por día, `currentSeason` (0..3), `temperature`, `dayFraction`, `hungerMultiplier`/`thirstMultiplier` estacionales. Estaciones con nombres (`SEASON_NAMES`). Temperatura publicada al UI.

**(2) Archivos/algoritmos:** `engine/world.js` (Clock), `worker/simWorker.js` (climate object), `constants/simulation.js` (SEASON_NAMES).

**(3) Mundo Vivo:** `motor/reloj.py` (57 LOC), `motor/frio.py` (142 LOC), `motor/ecologia.py`. 1 año = 120 días; bucle 20 Hz, estado 10 Hz. Estaciones y temperatura como datos/constantes. `hungerMultiplier`/`thirstMultiplier` por estación.

**(4) Ventajas:** BiomeSimulator tiene dayFraction y seasons integradas al worker loop. Mundo Vivo tiene el modelo térmico completo con fogata/horno/fragua (600→1500 °C), abrigo, LOD térmico.

**(5) Portar/adaptar:** dayFraction como fracción del día para animación/UI; multiplicadores estacionales ya existen.

**(6) Incompatibilidades:** escala temporal distinta (BiomeSimulator en game-minutes con `ITEM_LIFETIME` en minutos; Mundo Vivo en días/años).

**(7) Tests:** verificar que un tick avance el reloj correctamente; verificar cambio de estación a 30 días; verificar multiplicadores.

---

## 3. Biomas / distribución de hábitat

**(1) BiomeSimulator:** 9 tipos de terreno fijos (WATER..MUD) con nombres en `TERRAIN_NAMES`. Distribución por ruido + agua proximity. `terrainGrowth` en plantSpecies filtra qué plantas crecen en qué terreno.

**(2) Archivos/algoritmos:** `engine/world.js` (TERRAIN_IDS, TERRAIN_NAMES), `engine/plantSpecies.js` (terrainGrowth array).

**(3) Mundo Vivo:** `datos_base/biomas/biomas.json` + `cavernas.json`, `motor/biomas.py` (89 LOC), `motor/minerales.py`. Biomas como datos con velocidad, costo, etc. Plantas se filtran por bioma via `terrainGrowth` equivalente en datos.

**(4) Ventajas:** Mundo Vivo es data-driven (nuevos biomas sin código); BiomeSimulator tiene water proximity precomputado que acelera checks.

**(5) Portar/adaptar:** water proximity precomputado (ya en curso con `_agua_ady_mask`).

**(6) Incompatibilidades:** BiomeSimulator tiene ids fijos; Mundo Vivo es extensible.

**(7) Tests:** verificar que cada bioma tenga velocidad definida; verificar que plantas solo crezcan en biomas válidos.

---

## 4. Registro de especies

**(1) BiomeSimulator:** `animalSpecies.js` (1285 LOC) con `DIET`, `SOUND_GROUP`, population caps por trophic level, species config (max_hp, max_energy, etc.). `plantSpecies.js` (799 LOC) con stageAges, productionChance, terrainGrowth, colors. Registries hardcodeados en JS.

**(2) Archivos/algoritmos:** `engine/animalSpecies.js`, `engine/plantSpecies.js`, `engine/entities.js` (AnimalState, LifeStage, ReproductionType, Direction, sex assignment).

**(3) Mundo Vivo:** `src/mundo_vivo/registro.py` (165 LOC), `catalogos.py` (208 LOC), `reglas.py` (174 LOC), `condiciones.py` (151 LOC). Datos en `datos_base/fauna/especies.json`, `datos_base/etiquetas/etiquetas.json`. Herencia `copy-from`, plantillas `abstracto`, tipo decide carpeta, evaluador declarativo (`condiciones.py`), compilación a tablas planas en `Simulacion.__init__` (`_compilar_materiales`, `_compilar_conservacion`).

**(4) Ventajas:** Mundo Vivo es totalmente data-driven con herencia y evaluador declarativo; BiomeSimulator tiene registros más completos (population caps, trophic levels, sound groups).

**(5) Portar/adaptar:** population caps por trophic level y sound groups como datos JSON en Mundo Vivo.

**(6) Incompatibilidades:** BiomeSimulator registra en código JS; Mundo Vivo en JSON con herencia.

**(7) Tests:** verificar que el catálogo valida al arrancar; verificar que una especie sin receta que la levante falle; verificar ids únicos.

---

## 5. Ciclo de vida vegetal

**(1) BiomeSimulator:** `flora/constants.js` (P_* plant IDs, PLANT_SEX, S_* stages, SEASONS), `flora/lifecycle.js` (173 LOC), `flora/reproduction.js`, `flora/seeding.js`, `flora/modifiers.js`, `flora/lookups.js`, `flora/helpers.js`, `flora/index.js`. Plantas con sexo, etapas con ages, productionChance, consumo por herbívoros, germinación de semillas.

**(2) Archivos/algoritmos:** `engine/flora/*` (~173+ LOC lifecycle + reproduction + seeding + modifiers + lookups + helpers + constants + index).

**(3) Mundo Vivo:** `motor/vida.py` (515 LOC), `motor/ecologia.py` (342 LOC), `motor/fuego.py` (293 LOC), `motor/conservacion.py` (128 LOC). Crecimiento por tick, consumo, rebrote chunked, fogata abriga chozas, senderos por desgaste. Plantas con `plantType/plantStage/plantAge` en grids paralelos.

**(4) Ventajas:** BiomeSimulator tiene reproducción vegetal con sexo y seeding detallado. Mundo Vivo tiene rebrote chunked, fire bbox, propagación por colonias.

**(5) Portar/adaptar:** reproducción vegetal con sexo y productionChance como datos; seeding (semillas en el suelo) como ground items.

**(6) Incompatibilidades:** BiomeSimulator plantas son entidades con estado completo; Mundo Vivo usa grids paralelos (más eficiente para 2048²).

**(7) Tests:** verificar regrowth después de consumo; verificar que fogata abrigue chozas; verificar que senderos se formen.

---

## 6. IA animal / comportamiento

**(1) BiomeSimulator:** máquina de estados (IDLE, EATING, DRINKING, SLEEPING, WANDERING, FLEEING, HUNTING, MATING, etc.) con behaviors modulares: `behaviors/states.js` (_doSleep, _doEat, _doDrink), `behaviors/eating.js`, `behaviors/combat.js`, `behaviors/reproduce.js`, `behaviors/scavenge.js`, `behaviors/movement.js`, `behaviors/seek.js` (377 LOC), `behaviors/utils.js` (STAGE_NUTRITION, _canEatPlant). Sin LLM, determinista.

**(2) Archivos/algoritmos:** `engine/behaviors/*.js` (~358 index + 517 movement + 377 seek + 378 states + ...). `engine/simulation.js` (741 LOC) orquesta.

**(3) Mundo Vivo:** `agentes/mente.py` (961 LOC) — CerebroHibrido: `_reflejos` (genoma) → `_decidir` (LLM Ollama) → `_respaldo`. `agentes/ajustes.py` (107 LOC) lista de módulos. `motor/atencion.py` (85 LOC) LOD cognitivo. `motor/objetivos.py` (213 LOC) Utility AI + encadenado de precondiciones. `agentes/cerebro_cognitivo.py` (1587 LOC) puente a Cognitive Engine (GOAP, sin LLM, determinista).

**(4) Ventajas:** BiomeSimulator tiene IA determinista modular, fácil de testear, sin latencia de LLM. Mundo Vivo tiene LLM real con mente propia, aprendizaje, memoria v2 con procedencia, comunicación con consecuencias (mentir).

**(5) Portar/adaptar:** la modularización de behaviors (eating, combat, reproduce, scavenge, movement, seek como módulos independientes) como patrón de organización; STAGE_NUTRITION y _canEatPlant como datos.

**(6) Incompatibilidades:** BiomeSimulator es puramente determinista; Mundo Vivo tiene LLM no-determinista. CCA es el bridge determinista que ya resuelve esto.

**(7) Tests:** tests de behaviors con mocks (BiomeSimulator tiene __tests__); en Mundo Vivo, tests con objetivos y atencion apagados para guionizar al modelo.

---

## 7. Movimiento / pathfinding / búsqueda de recursos

**(1) BiomeSimulator:** A* acotado (maxDist=50) en `pathfinding.js` con binary min-heap, 4-direccional, goal-snapping a tile walkable adyacente para beber. `spatialHash.js` (O(1) neighbor lookup, cellSize=16, integer key encoding). `TERRAIN_SPEED_FACTOR` y `TERRAIN_ENERGY_MULT` en movement.js. Path cache TTL. Caching de paths imposibles.

**(2) Archivos/algoritmos:** `engine/pathfinding.js` (~100 LOC), `engine/spatialHash.js` (~120 LOC), `behaviors/movement.js` (TERRAIN_SPEED_FACTOR, TERRAIN_ENERGY_MULT).

**(3) Mundo Vivo:** `motor/navegacion.py` (394 LOC) — A* 8-direccional con costo real (bioma × pendiente × río), corner rules, caching de rutas exitosas (LRU 256) y fracasos (4096), `_agua_ady_mask` (uncommitted), `Terreno.costo` (numpy) vs `Terreno._c` (listas compartiendo floats — 3.809 valores distintos en 4.2M celdas). `Terreno.cambiar_bioma()` escribe en ambas. Invalidación de `h.camino`. METROS_ZONA, radios sociales en metros. `VEL_CAMINAR_MPS = 1.33`. `BLOQUE_FRACASO = 4`.

**(4) Ventajas:** Mundo Vivo tiene costo real con pendiente y río, corner rules, caching LRU, invalidación de caminos. BiomeSimulator tiene SpatialHash O(1) y A* más simple/rápido.

**(5) Portar/adaptar:** SpatialHash como estructura de datos para Mundo Vivo (actualmente usa grids de numpy + búsqueda lineal en algunos casos); path cache TTL por tick.

**(6) Incompatibilidades:** Mundo Vivo usa numpy arrays + listas compartiendo floats; BiomeSimulator usa TypedArrays + Maps. Mundo Vivo tiene 8 direcciones con costo diagonal; BiomeSimulator 4.

**(7) Tests:** verificar A* con obstáculos; verificar que `_c` se actualice con `cambiar_bioma`; verificar caching de fracasos; verificar corner rules.

---

## 8. Alimentación / sed / energía / supervivencia

**(1) BiomeSimulator:** `ITEM_TYPE` (MEAT/FRUIT/SEED), `ITEM_NUTRITION`, `meatDropRange(mass_kg)`, item lifecycle en game-minutes. `STAGE_NUTRITION` en utils.js. `_canEatPlant` con edible-stage map. Energía/hambre/sed como barras. Muerte por inanición/deshidratación.

**(2) Archivos/algoritmos:** `engine/items.js` (ITEM_TYPE, ITEM_NUTRITION, meatDropRange, nextItemId con ITEM_ID_BASE=2_000_000_000), `behaviors/utils.js` (STAGE_NUTRITION, _canEatPlant), `behaviors/states.js` (_doEat, _doDrink).

**(3) Mundo Vivo:** `motor/alimentacion.py` (118 LOC), `motor/vida.py` (515 LOC), `motor/conservacion.py` (128 LOC), `motor/atributos.py` (123 LOC). Hambre/sed/energía como barras independientes. TOPE_LOTE por ítem (no carga total). Cocina/conservación de alimentos. Muerte por sed/hambre. `SED_DESPIERTA` compartida entre motor y cerebro.

**(4) Ventajas:** BiomeSimulator tiene items con nutrición y drops de carne por masa. Mundo Vivo tiene conservación de alimentos, cocina, atributos que suben con uso y se oxidan.

**(5) Portar/adaptar:** meatDropRange (carne por masa del animal) como dato; ITEM_NUTRITION como datos JSON; STAGE_NUTRITION (nutrición por etapa de planta).

**(6) Incompatibilidades:** BiomeSimulator items son ground items con germinación; Mundo Vivo tiene inventario + estructuras + persistencia SQLite.

**(7) Tests:** verificar muerte por sed con agua adyacente; verificar TOPE_LOTE por ítem; verificar conservación de alimentos.

---

## 9. Reproducción / mortalidad

**(1) BiomeSimulator:** `ReproductionType`, `LifeStage` (EGG, JUVENILE, ADULT, etc.), sex assignment en Animal constructor, gestation timer, litter size, parentA/parentB, `_isEggStage`, `_incubationPeriod`, `_eggMaxHp`. Huevo con HP propio.

**(2) Archivos/algoritmos:** `engine/entities.js` (Animal class, sex, lifeStage), `engine/behaviors/reproduce.js`.

**(3) Mundo Vivo:** `motor/vida.py` (515 LOC), `agentes/genoma.py` (160 LOC). Genoma heredable, reproducción sexual/asexual, parentesco cercano, gestación, muerte por edad/daño/hambre/sed. Memoria v2 con procedencia.

**(4) Ventajas:** BiomeSimulator tiene sistema de huevos con HP y etapas de vida detalladas. Mundo Vivo tiene genoma heredable, mutaciones, memoria v2 con procedencia, comunicación.

**(5) Portar/adaptar:** sistema de huevos con HP y etapas de vida (EGG/JUVENILE/ADULT) como datos; `_gestationLitterSize` para camadas.

**(6) Incompatibilidades:** BiomeSimulator reproducción es determinista; Mundo Vivo tiene genoma + LLM que influye en decisiones reproductivas.

**(7) Tests:** verificar que huevos no se superpongan con animales; verificar gestation timer; verificar herencia de genoma.

---

## 10. Depredación / competencia

**(1) BiomeSimulator:** `DIET` (herbivore/carnivore/omnivore), `SOUND_GROUP`, trophic levels, population caps por nivel trófico. Combat behavior con cooldown. Scavenge behavior (carroñeo). Threat detection con cache (`_cachedThreat`, `_nextThreatCheckTick`).

**(2) Archivos/algoritmos:** `engine/animalSpecies.js` (DIET, SOUND_GROUP, population caps), `behaviors/combat.js`, `behaviors/scavenge.js`, `behaviors/seek.js` (threat detection cache).

**(3) Mundo Vivo:** `motor/fauna.py` (416 LOC), `motor/ecologia.py` (342 LOC), `datos_base/fauna/especies.json`. Depredador/presa, niveles tróficos, caps de población, competencia por recursos, propagación de colonias.

**(4) Ventajas:** BiomeSimulator tiene threat cache con TTL y sound groups para alertas. Mundo Vivo tiene colonias que se propagan, mutaciones de especies, psique.

**(5) Portar/adaptar:** threat detection cache con TTL (`_cachedThreatTick`, `_nextThreatCheckTick`); sound groups para alertas grupales; scavenge behavior.

**(6) Incompatibilidades:** BiomeSimulator combat es determinista; Mundo Vivo tiene LLM que puede decidir huir/atacar.

**(7) Tests:** verificar que presas detecten depredadores; verificar cooldown de ataque; verificar caps de población.

---

## 11. Objetos persistentes / recursos

**(1) BiomeSimulator:** `GroundItem` con id, x, y, type, source, createdTick, germinationTicks. `ITEM_ID_BASE=2_000_000_000` para evitar colisión con animal IDs. Items consumibles con claims (`_itemClaimMode`, `plantConsumptionClaims`, `itemConsumptionClaims`). Item spatial hash.

**(2) Archivos/algoritmos:** `engine/items.js` (GroundItem, ITEM_TYPE, ITEM_NUTRITION, meatDropRange, nextItemId), `engine/world.js` (items array, _itemById, _itemSpatialHash, _itemTiles).

**(3) Mundo Vivo:** `persistencia/sim_io.py` (616 LOC), `persistencia/mundo_io.py` (285 LOC), `persistencia/memoria.py` (170 LOC), `persistencia/social.py` (127 LOC), `motor/conservacion.py`. Items en SQLite + JSON estado. Estructuras persistentes (hogar, ruinas, senderos). Inventario por habitante + ground items.

**(4) Ventajas:** BiomeSimulator tiene item spatial hash y claim system para evitar doble consumo. Mundo Vivo tiene persistencia SQLite robusta, inventario, estructuras, memoria social.

**(5) Portar/adaptar:** item spatial hash para Mundo Vivo (acelerar búsquedas de items); claim system para evitar doble consumo en paralelo.

**(6) Incompatibilidades:** Mundo Vivo persiste en SQLite con WAL; BiomeSimulator en memoria (Web Worker).

**(7) Tests:** verificar que dos animales no consuman el mismo item; verificar item spatial hash; verificar persistencia round-trip.

---

## 12. Optimización / rendimiento

**(1) BiomeSimulator:** Web Worker architecture (simWorker.js 904 LOC) con fauna sub-workers (faunaWorker.js 227 LOC) para paralelismo (MIN_ANIMALS_FOR_PARALLEL=500, MAX_FAUNA_WORKERS=4). SpatialHash O(1). Benchmark profiler (benchmarkProfiler.js) con métricas por función. Full sync cada 30 ticks. Movement sub-ticks. Batched plant changes (MAX_PLANT_CHANGES_PER_TICK=5000). Incremental animal deltas (dirty flag). PostMessage rate capping (MAX_UI_UPDATE_HZ=30). Fauna worker timeout (800ms). Supervisor (simulationSupervisor.js 373 LOC) con auditoría periódica (cada 30 ticks) y cooldown de log (120 ticks).

**(2) Archivos/algoritmos:** `worker/simWorker.js`, `worker/faunaWorker.js`, `engine/spatialHash.js`, `engine/benchmarkProfiler.js`, `engine/simulationSupervisor.js`.

**(3) Mundo Vivo:** `motor/chunks.py` (47 LOC) — CHUNK=64, chunks_activos. `motor/fuego.py` (293 LOC) — _bbox_ardiendo, chunked rebrote. `motor/atencion.py` (85 LOC) — LOD cognitivo. `api/vivo.py` — _bucle, tope_pensando, MIN_POR_PENSADA. `motor/simulacion.py` (841 LOC) — _tick_rapido_fisica, _tick_amortizado_sistemas, _tick_cerebro, _propuestas_cerebro. Tick 20 Hz, estado 10 Hz. `tope_pensando = 90 / latencia_s`.

**(4) Ventajas:** BiomeSimulator tiene Web Workers reales (paralelismo de procesos), benchmark profiler integrado, supervisor de auditoría. Mundo Vivo tiene chunks activos, fire bbox, LOD cognitivo, amortización de sistemas.

**(5) Portar/adaptar:** benchmark profiler como módulo Python (time.perf_counter por función); supervisor de auditoría periódica; Web Worker equivalente en Python (multiprocessing o asyncio background); dirty flag para incremental deltas.

**(6) Incompatibilidades:** BiomeSimulator corre en browser (Web Workers); Mundo Vivo es Python server-side. Paralelismo real requiere multiprocessing o asyncio.

**(7) Tests:** verificar que chunks_activos retorne subset correcto; verificar que fire bbox no pierda focos; verificar benchmark overhead < 5%.

---

## 13. Arquitectura de simulación / separación de concerns

**(1) BiomeSimulator:** `SimulationEngine` (simulation.js 741 LOC) orquesta. Web Worker (simWorker.js) corre el engine. Fauna sub-workers procesan animales en paralelo. Main thread solo renderiza. Separación: engine (lógica), worker (ejecución), renderer (UI). Config centralizada (config.js). SpatialHash para queries. Benchmark profiler inyectable.

**(2) Archivos/algoritmos:** `engine/simulation.js`, `worker/simWorker.js`, `worker/faunaWorker.js`, `engine/config.js`, `engine/world.js`, `engine/spatialHash.js`.

**(3) Mundo Vivo:** `motor/simulacion.py` (841 LOC) — `Simulacion` armada con mixins (vida, ecologia, frio, conservacion, alimentacion, atributos, atencion, fenomenos_datos, objetivos, psique, propagacion, tecnologia). `motor/mundo.py` (156 LOC) — una Simulacion por dimensión. `agentes/ajustes.py` (107 LOC) — lista única de módulos. `api/servidor.py` + `api/vivo.py` (WebSocket). `agentes/cerebro_cognitivo.py` — puente CCA. `persistencia/sim_io.py` — guardado. Tick order: `_tick_rapido_fisica` → `_tick_amortizado_sistemas` → `_tick_cerebro` → `_propuestas_cerebro`.

**(4) Ventajas:** BiomeSimulator tiene separación limpia engine/worker/renderer con paralelismo real. Mundo Vivo tiene mixins por sistema (extensible), multi-dimensión, persistencia robusta, cerebro desacoplado del tick crítico.

**(5) Portar/adaptar:** separación de concerns más estricta (engine puro sin I/O); benchmark profiler; supervisor de auditoría; Web Worker equivalente.

**(6) Incompatibilidades:** BiomeSimulator es JS single-threaded con Web Workers; Mundo Vivo es Python con mixins y SQLite. La arquitectura de Mundo Vivo es más compleja pero más extensible.

**(7) Tests:** verificar que todos los mixins estén registrados en ajustes.py (test existente); verificar tick order; verificar que el cerebro no bloquee el tick.

---

## Resumen de recomendaciones de portabilidad

| Prioridad | Item | Origen | Destino |
|---|---|---|---|
| Alta | SpatialHash O(1) | BiomeSimulator spatialHash.js | Mundo Vivo motor/navegacion.py |
| Alta | Ríos con meandro | BiomeSimulator mapGenerator.js | Mundo Vivo generador/pipeline.py |
| Alta | Water proximity BFS precomputado | BiomeSimulator mapGenerator.js | Mundo Vivo (ya en curso) |
| Alta | Threat detection cache con TTL | BiomeSimulator behaviors/seek.js | Mundo Vivo motor/fauna.py |
| Media | Benchmark profiler | BiomeSimulator benchmarkProfiler.js | Mundo Vivo (nuevo módulo) |
| Media | Supervisor de auditoría periódica | BiomeSimulator simulationSupervisor.js | Mundo Vivo (nuevo módulo) |
| Media | Population caps por trophic level | BiomeSimulator animalSpecies.js | datos_base/fauna/especies.json |
| Media | Item spatial hash + claim system | BiomeSimulator items.js | Mundo Vivo motor/conservacion.py |
| Baja | Sea level adaptativo por percentil | BiomeSimulator mapGenerator.js | Mundo Vivo generador/pipeline.py |
| Baja | STAGE_NUTRITION por etapa | BiomeSimulator behaviors/utils.js | datos_base/ |
| Baja | Sound groups para alertas | BiomeSimulator animalSpecies.js | datos_base/fauna/especies.json |

## Restricciones respetadas
- No se convirtió nada a JS.
- No se reemplazó el motor.
- No se modificó BD ni mundo `ww`.
- No se tocó CCA.
- No se eliminó funcionalidad.
- Semillas/reproducibilidad preservadas.
- Licencia Apache 2.0 respetada (atribución en este documento).

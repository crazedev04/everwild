# Registro de cambios — Mundo Vivo

## Sin publicar — E2: primera representación visual real (terreno)

### Nuevo
- **Capa de terreno** `ui/render/capa_terreno.js`: bitmap 1 px/celda desde `WorldView.terreno.bioma` + paleta inyectada; `draw` pinta sólo la porción visible (`frame.vis`). Datos ausentes/inválidos ⇒ no dibuja (no engaña); bioma sin color ⇒ magenta.
- **Renderer con capas y cámara** (`ui/render/renderer.js`): `crear(..., {capas})`, `setPaleta(pal)` (inyectada por el adaptador, el renderer no conoce REST), y `dibujar` aplica transform de cámara `s=z·dpr` y pasa `frame{cam,vis,lod,w,h,dpr,t}` a cada capa en orden. `hitTest` intacto.
- **Integración** (`ui/render/integracion.js`): obtiene paleta de `/api/biomas` y la inyecta; arma `capa_terreno` y la pasa al renderer. Sigue opt-in (`?renderer=nuevo`).
- Tests (5 nuevos; 59/59): construcción de bitmap con paleta (little-endian), dibujo sólo de lo visible, ausencia/invalidéz no dibuja, magenta por defecto, y `draw` con cámara/viewport/vis.

### Pendiente
- Capas de profundidad (estructuras/habitantes/fauna/vegetación-sprite), agua/nieve/ceniza, senderos, iluminación y efectos (E3+). `WorldDelta`/`applyDelta` siguen reservados (sin contrato autoritativo).

## Sin publicar — E1-FIX: integración y ciclo de vida del renderer

### Arreglado
- **Doble renderer sobre el mismo canvas (alto)**: el puente E1 ya no dibuja sobre `#lienzo`; crea un **canvas experimental propio** (`#lienzo-exp`, superpuesto, `pointer-events:none`, fondo transparente) dentro de `#lienzo-caja`. El renderer anterior sigue visible e intacto y no hay doble escritura. Ciclo de vida explícito: `puente.destroy()` destruye el renderer y **remueve el canvas**; inicializar dos veces no duplica canvas (destruye el anterior).
- **Clear en HiDPI**: `renderer.setViewport` dimensiona el backing store a `CSS*dpr` (dimensiones CSS y físicas separadas) y `dibujar` limpia en px de dispositivo; el canvas experimental usa `clearRect` (transparente). Evita clear incompleto y doble escalado con `devicePixelRatio > 1`.
- **Cambio de mundo**: `setWorldView` limpia la selección al cambiar `worldId`/`dimension` (no arrastra estado transitorio).

### Nuevo
- Hooks de integración unificados en `RenderIntegracion.despachar(App, evento, arg)` (no-op sin puente; reenvía si existe), usados por `mapa.js`/`vivo.js`.
- Tests de integración (8 nuevos; 54/54 JS): despachar no-op/reenvío, canvas propio sin compartir `#lienzo`, no duplicados, destroy libera canvas+renderer, cambio de mundo con viewport HiDPI, clear HiDPI y reset de selección.

## Sin publicar — E1: fundamentos del renderer definitivo

### Nuevo
- **Núcleo del renderer Canvas 2D (E1)** desacoplado de DOM/REST/WS en `ui/render/`: `worldview.js` (modelo/normalización de `WorldView` provisional, identidad real `id`/`inst`, ausente ⇒ `null`), `adaptador.js` (adaptador provisional con `buildGen`: descarta ciclos viejos, reemplazo completo, fallo parcial no entrega, cambio de mundo = ciclo nuevo), `renderer.js` (API §6.1 `crear/setWorldView/setCam/setViewport/setCapas/setSeleccion/pedirRender/setActivo/destroy/hitTest`; `applyDelta` reservada; loop on-demand con `RaceRender.crearPlanificador` + cola de procesamiento con presupuesto).
- **Integración opt-in** `ui/render/integracion.js`: se activa con `?renderer=nuevo` (o `localStorage.mv_renderer=nuevo`), reutiliza capas/meta de `terreno` y el estado de `vivo`; el renderer viejo (`escena.js`) queda intacto y **desactivar** = quitar el flag. Hooks guardados en `mapa.js`/`vivo.js` (no-op sin el puente).
- `RaceRender.crearPlanificador` incorpora `cancelar()` para que `destroy` libere el rAF pendiente.
- Tests de regresión JS (23 nuevos, 46/46): descarte de ciclos viejos, reemplazo completo, fallo parcial, cambio de mundo/dimensión, invalidaciones/deduplicación de frames, continuación con trabajo pendiente, suspensión, `hitTest` sin render, limpieza por `destroy`.

### Pendiente
- Sin `authoritativeRev` (el backend no lo provee): la cola autoritativa y `applyDelta` quedan deshabilitadas; E1 no dibuja capas visuales (terreno/sprites en E2+).

## Sin publicar — Desacoplamiento estructural y modularización total

### Nuevo

- **Modularización del Generador (`mundo_vivo.generador`)**: Tubería de generación de mundos completamente desacoplada en su propio paquete modular, sin dependencias de WebSocket, red ni simulación viva. `mundo_vivo.motor.generador` conservado como shim de retrocompatibilidad transparente.
- **Física dividida en Ticks Rápidos y Amortizados**: `Simulacion._paso()` separa `_tick_rapido_fisica(paso)` (cinemática, movimiento, vitales) y `_tick_amortizado_sistemas(paso)` (clima, fuego, fauna, senderos, colonias).
- **Desacoplamiento del Cerebro Cognitivo**: `Simulacion._tick_cerebro()` y buffer diferido `_propuestas_cerebro`, aislando la toma de decisiones del camino crítico de la simulación.
- **Suite de fronteras modulares**: `tests/test_modularizacion.py` garantizando el aislamiento de capas y contratos arquitectónicos.

## Sin publicar — Etapas 2, 4, 5 y 6 de WORLD_ARCHITECTURE

### Nuevo

- **Generador 1.1.0**: las constantes físicas que estaban en celdas (micro-relieve, radios de volcán, distancia al agua, tamaño mínimo de lago, precipitación por columna) se escalan por `tam_celda_m`. El mismo mapa físico da la misma pendiente mediana a 50 m y a 5 m por celda (test 96×96@50 vs 960×960@5).
- **Erosión hidráulica y térmica** determinista sobre el D8 que ya calculaba `_hidrologia`: profundiza los valles de los ríos y relaja acantilados. No toca océano ni lagos.
- **`pendiente` en m/m** en la clasificación de biomas; el rango de `pantano` en `datos_base/biomas/biomas.json` se migró a m/m y `dist_agua` a metros.
- **Caché LRU de rutas exitosas** en `Terreno` (`TOPE_RUTAS = 256`): un mismo viaje se pide dos veces por decisión; la segunda ya no corre A*. Se invalida en `cambiar_bioma` y devuelve copia defensiva.
- **`api/presentador.py`**: toda la serialización del visor salió del motor. `Simulacion` ya no tiene `estado_publico*`; hay un test que lo prohíbe.
- **`motor/chunks.py`**: índice de chunks de 64×64 con `chunks_activos(sim)`, publicado en el estado del visor.

### Arreglado

- **Elegir inicio ya no falla en mundos chicos a 5 m/celda**: el umbral de pendiente se relaja por pasos y hay un último recurso de cualquier tierra caminable junto al agua.

### Pendiente

- El fuego todavía recorre el mapa entero cuando hay celdas encendidas; el recorte por bounding box quedó para la próxima pasada.
- Mover la simulación a un proceso aparte (Etapa 5.1/5.2) no se hizo: SQLite está atado al hilo y el bucle ya es una task asíncrona con presupuesto.

## Sin publicar — Etapa 3: estado liviano para el visor

### Nuevo

- **`HabitanteSim.a_publico_mapa()`**: lo mínimo que dibuja el mapa (posición, acción, sexo, emoción, antorcha). Los atributos, las barras finas y el objetivo ya no viajan en cada cuadro.
- **`Simulacion.estado_publico_liviano(bloques=False)`**: mensaje de cada 100 ms. Con `bloques=True` suma fuego, estructuras, colonias y senderos.
- **Bloque pesado una vez por segundo** en el bucle del visor (`api/vivo.py`): fuego, estructuras, colonias y barras finas dejaron de recalcularse y serializarse 10 veces por segundo.
- **`_vitales_sucios()`**: salud, sed, energía, hambre, temperatura y frío solo de los vivos que cambiaron desde el último bloque. Los muertos no llevan barras.

### Arreglado

- **El visor ya no reemplaza el estado entero con cada mensaje.** `aplicarEstado` mergea por habitante y por bloque, así que un mensaje liviano no borra el fuego, las estructuras ni las barras que llegaron en el bloque anterior.
- **El panel de habitantes lee las barras del estado mergeado**, no del mensaje liviano, que ya no las trae.

### Pendiente

- Etapa 4 (caché de rutas exitosas) para bajar el A*, que sigue siendo el 66% del CPU.
- Etapa 2 (generador) y Etapas 5-6.

## Sin publicar — CCA v1.1 + persistencia de cerebros cognitivos

### Nuevo

- **Integración completa de CCA v1.1** en `src/mundo_vivo/agentes/cerebro_cognitivo.py`:
  - `EmotionModule` (VAD) instanciado y conectado en `AutonomousBrain`; recibe tick con `delta_simulation_time` explícito.
  - `ValueSystem` calibrado por rasgos del habitante (`curiosidad` → `curiosity`, `sociabilidad` → `social_connection`, `cautela` → `survival`).
  - `SelfModel` y `SocialCognition` instanciados y cableados por `brain_id`.
  - `Observation` incluye `simulation_time=float(sim.t)` y `delta_simulation_time` calculado desde `_ultimo_tick` para que el motor cognitivo gestione su propio tiempo.
  - Percepts de personas con metadatos `channel="social"` y `entity_type="agent"`.
  - Acceso al plan activo via `decision_engine.plan_manager.active_plan` (retrocompatible con fallback a `state.plan`).
- **Persistencia de cerebros cognitivos** en `cerebros_cognitivos.db` (mismo directorio que el mundo). Se guarda en cada ciclo de `guardar()` y al olvidar un habitante fallecido. No interfiere con la base principal del mundo; si falla, registra el error sin tumbar la simulación.
- **28 tests** de integración pasando, incluido ciclo de 20 días simulados sin muertes con agua al alcance.
- **Recuperación de cerebros al abrir el mundo (E2)**: `CerebroCognitivo` expone `list_brain_ids()` y
  `recuperar_cerebros()`. Al abrir un mundo, los cerebros persistidos se recuperan en el scheduler
  antes de la primera decisión, así la continuidad (memorias, pericia, ids) está lista sin esperar a
  que cada habitante decida. No duplica: el scheduler descarta ids ya registrados y saltea los
  archivados.

### Arreglado

- Acceso al plan activo migrado a `decision_engine.plan_manager.active_plan` (CCA v1.1 movió el plan fuera de `DeliberationState`).
- **La persistencia de cerebros era solo de escritura.** Se guardaba en `cerebros_cognitivos.db` pero nunca se leía, así que al reabrir el mundo cada cerebro arrancaba vacío. Ahora `_cerebro_de` recupera lo que el mundo no guarda —memorias episódicas y semánticas, mapa espacial, pericia, ids y objetivo vigente— y deja que necesidades y personalidad las siga mandando el mundo. El plan en curso no se restaura a propósito: se replanifica, igual que en el motor cognitivo.
- **Contadores separados por tipo de falla.** `guardados_fallidos` / `ultimo_error_guardando` y `restauraciones_fallidas` / `ultimo_error_restaurando` salen en el panel; antes un fallo de guardado se mezclaba con los de anotación. `olvidar()` ya no se traga el error al archivar el cerebro de un muerto.
- **Hugo no bebía aunque tuviera agua pegada.** Con sed ≥ `SED_DESPIERTA`, el árbitro del motor cognitivo podía quedarse con el objetivo vigente (p. ej. `explore_environment`) por hístéresis aunque las otras necesidades quedaran en `NUNCA_CRITICA`. Medido en `artemira`: habitante 4 con sed 100 y `agua_adyacente=True` guardaba `current_goal_id="explore_environment"`. Ahora se fuerza `goal_id=None` y se limpia el plan antes de cada tick mientras la sed sea mortal.

## Sin publicar — L.3: streams RNG independientes por subsistema

### Nuevo

- **RNG independiente por subsistema** en `src/mundo_vivo/motor/simulacion.py`: el RNG compartido `self.rng` se reemplaza por 14 streams derivados con `derivar_semilla(raiz, nombre)`: `cerebro`, `agua`, `rayos`, `derrumbes`, `caídas`, `calor`, `materiales`, `psique`, `fauna`, `objetivos`, `propagacion`, `alimentacion`, `vida` y `fenomenos`. Cada consumidor usa su propio stream; no se interfieren entre sí y cada uno es reproducible dado el mismo par raíz+nombre.
- **Fuego, Fauna y Clima/Fenomenos** derivan su semilla desde `derivar_semilla(semilla, nombre)` en lugar de fórmulas ad hoc (`int(semilla) & 0x7FFFFFFF`, `int(semilla) * 7919 + 13`). Antes Fauna y Clima compartían la misma semilla y por tanto la misma secuencia aleatoria.
- **`tests/test_semilla.py`**: 8 pruebas de aislamiento y reproducibilidad (determinismo, nombres distintos → semillas distintas, streams no comparten estado, mismo mundo → misma secuencia, distinto mundo → distinta secuencia).

### Arreglado

- Uso de `sim.rng` en `agentes/cerebro_cognitivo.py`, `agentes/mente.py` y `motor/simulacion.py` (`CerebroDemo`) migrado al stream correspondiente (`rng_cerebro` para decisiones, `rng_agua` para búsqueda de agua, `rng_rayos` para encendido por rayo, `rng_derrumbes` para daño de derrumbe, `rng_caidas` para resbalones).
- Pruebas de `test_alimentacion.py` y `test_fauna.py` actualizadas para semear `rng_alimentacion` y `rng_fauna` en lugar del eliminado `sim.rng`.


Cada actualización lista lo nuevo, lo acordado, lo arreglado y lo que queda pendiente. La versión actual está en `src/mundo_vivo/__init__.py`.
Las migraciones de base de datos son automáticas y no borran nada: un mundo viejo se abre con la versión nueva y conserva sus recuerdos.

## Sin publicar — Diagnóstico permanente, rendimiento y la muerte por sed

Todo esto salió de **mirar mundos corriendo**, no de los tests: los 453 tests pasaban mientras pasaba
todo lo que está acá abajo.

### Nuevo

- **Registro permanente con rotación, en `<datos>/logs/`** (`src/mundo_vivo/diagnostico.py`, nuevo).
  Arranca solo en todos los comandos. Deja el entorno del arranque (versión, Python, GIL, numpy,
  websockets y si tiene `speedups`, plataforma, cerebro), el mundo (nombre, semilla, tamaño,
  `tam_celda_m`, dimensiones, habitantes) y un **latido cada 60 segundos** con minuto simulado,
  memoria del proceso, vivos, el tamaño de todas las estructuras que crecen, velocidad real y
  `latencia_s` / `rechazos_llm` del cerebro. Cada 10 minutos agrega las filas de las tablas que
  crecen. Detalle completo en `docs/DIAGNOSTICO.md`.
- **`faulthandler` prendido siempre**, volcando a `<datos>/logs/caida.log`. Es lo único que sobrevive
  a una violación de segmento, porque lo escribe el manejador de la señal en C. Probado de punta a
  punta con un segfault provocado: quedan la pila de Python, la de C y la última línea del registro.
  Queda registrado también en `SIGUSR1`, así que a un mundo colgado se le puede pedir la foto de sus
  hilos sin matarlo (`kill -USR1 <pid>`).
- **`./mundo.sh autopsia [mundo]`**: junta en un solo texto el entorno, la última caída, el final del
  registro y el último estado guardado (integridad, filas por tabla, últimos sucesos y últimas
  decisiones con qué cerebro las tomó). Con `--salida` lo deja en un archivo. Y **`./mundo.sh logs`**
  para mirar el registro en vivo.

### Arreglado

- **Se morían de sed al lado del agua, y era un bloqueo de precondiciones de nuestro lado.** En el
  mundo real `gaia`, 23 de 27 muertes fueron de sed; se reconstruyó la posición de cada muerto y **13
  estaban pegados al agua** (`agua_adyacente` verdadero, cero pasos) y otros 9 tenían camino de 1 a 38
  celdas que el A* encontraba en menos de 0,1 s. La cadena era: la sed baja la salud, las dos llegan a
  crítica, el árbitro elige `satisfy_salud` (48% contra 41%), y las únicas capacidades que satisfacen
  la salud son `dormir` —que el motor prohíbe con sed alta, a propósito— y `usar`, que pide un remedio
  encima. Sin ninguna de las dos no hay plan posible (73% de las decisiones con sed ≥ 80 salieron sin
  plan), el planificador devuelve su respaldo y la sed sigue subiendo. Ahora la salud **no se declara
  crítica cuando no hay nada que hacer con ella**: no es una necesidad que se atienda sola. Todo el
  camino medido está en `docs/MUERTE_POR_SED.md`.
- **`"wait"` no estaba traducido en el puente.** Es el respaldo propio de Cognitive Engine
  (`WAIT_ACTION`) para cuando eligió un objetivo y no pudo armar plan. No sale de nuestro catálogo, así
  que caía en el camino de «capacidad desconocida»: 15 minutos de espera a ciegas y una marca en
  `_sin_traducir`. Pasó **790 veces** en `gaia`, 279 con sed por encima de 80. El test que cuida el
  catálogo ahora exige que el respaldo del motor cognitivo esté traducido.
- **El bucle del mundo se moría en silencio.** `_bucle` sólo re-lanzaba `CancelledError`; cualquier
  otra excepción mataba la tarea, que nadie espera, y el mundo se quedaba quieto sin dejar rastro en
  ninguna parte. Ahora queda escrita con su traza completa, igual que las excepciones de asyncio, de
  cualquier hilo y del hilo principal.
- **`./mundo.sh` se caía a `python3` pelado si el venv estaba roto.** Pasó: el `.venv` apuntaba a
  `/usr/bin/python3.14`, que no existe en esta máquina (el bueno es el de linuxbrew). `-x` daba falso,
  se usaba `python3`, y el error aparecía recién al importar numpy sin decir nada del venv. Ahora
  comprueba que el intérprete ande **y** que tenga numpy, y si no, dice cómo recrearlo.

### Rendimiento

Medido con el mismo mundo de 2048×2048 y celdas de 5 m, mismo troceado que usa el servidor:
**41,5 → 234 minutos simulados por segundo real (5,6×)**, y **167 MB menos** al cargar.
(Primer bloque: 41,5 → 81,3. Segundo bloque: 81,3 → 234.)

#### Segundo bloque

- **Caché de viajes imposibles** (`Terreno._fracasos`). Una búsqueda que falla es lo más caro que
  hace el motor, porque agota el presupuesto de nodos antes de rendirse, y se reintentaba en ráfaga:
  el mismo destino imposible 12 veces, a 0,7 s cada una. Ahora el fracaso se recuerda; el éxito
  **no** se guarda, porque un camino caduca en cuanto alguien construye algo, y todo se olvida si el
  mapa cambia (`cambiar_bioma`). `buscar_camino` bajó de 11,8 s a 2,2 s, y los `heappop` de 2,5
  millones a 636 mil.
- **`_paso_nieve`** tenía la misma forma que tenía el fuego: rearmaba dos arrays de 4,2 millones de
  celdas cada vez que corría, para una temperatura y una humedad que no cambian nunca. El factor de
  humedad se arma una sola vez, y si el mapa no baja de cero ni hay nieve que derretir se descarta la
  pasada entera comparando dos escalares. De 1,4 s a 0,3 s. La temperatura **no** se cachea a
  propósito: es un array público y guardar sus valores haría que escribirle no tuviera efecto, que es
  la trampa de `Terreno.costo` contra `Terreno._c`. Un test lo cazó al primer intento.
- **`entrenamiento_cerebro` ahora se poda** (2.000 trayectorias por habitante) y tiene índice, que no
  tenía. Eran 60.989 filas y ~10 MB de JSON creciendo para siempre en un solo mundo.
- **La poda de `decisiones` corría en cada guardado** —cada 10 segundos reales— con una subconsulta
  correlacionada que cuenta filas por cada fila, o sea cuadrática. Pasó a una vez por día del mundo,
  con el resto de las podas, y en dos pasos que sí pueden usar el índice.
- **No se tocó `ver_animales`.** La grilla espacial de la fauna se arma sólo dentro del tick, así que
  usarla desde afuera puede perder un animal que se movió —un depredador al lado— y el beneficio
  había caído a 0,24 s de 36,9 (0,65%) al arreglar el doble `_creencias`. No vale el riesgo.

- **`fuego.paso` era el 52% del CPU del motor en un mundo que nunca se incendió.** Recorría los 4,2
  millones de celdas del mapa seis veces **por minuto simulado** para rebrotar un combustible que
  nadie había gastado y desvanecer una ceniza que no existía. Ahora `_hubo_fuego` evita hasta el
  `fuego > 0`, y el rebrote sólo corre si de verdad se quemó algo (`_sucio`), en tandas de 30 minutos
  con el dt acumulado. Y **cierra el ciclo**: el rebrote es asintótico, así que sin un corte un
  incendio de hace meses dejaba al motor recorriendo el mapa para siempre; por debajo de `REBROTE_FIN`
  se ajusta a los valores exactos y se baja la bandera.
- **`_creencias` se calculaba dos veces por decisión de cada habitante.** `_anotar_decision` la volvía
  a llamar sólo para el registro de entrenamiento, y es la consulta más cara del puente
  (`disponibles()`, `ausentes()`, `ver_animales()`). Ahora reusa las que ya calculó `decidir`. No es
  sólo rendimiento: `registrar_resultado` corre **después** de que el motor aplicó la acción, así que
  recalcularlas guardaba el mundo de después. Para entrenar con pares (estado, acción), el estado que
  sirve es el de antes.
- **`_idea_para_probar` re-ordenaba las ~190 recetas y reconvertía sus ingredientes en cada decisión
  de cada habitante**, y preguntaba `sabe()` antes de la prueba barata. Ahora el catálogo ordenado,
  con los ingredientes ya en conjunto, se arma una sola vez y queda colgado de la simulación (no en un
  diccionario indexado por `id(sim)`: Python recicla los ids y un mundo nuevo podía recibir el
  catálogo de uno viejo).
- **`sabe()` recorría todo lo que la persona conoce, 455.924 veces en 50 días simulados.** Ahora la
  vuelta al revés —de receta a conocimientos que la enseñan— está indexada, y el índice se rearma solo
  cuando aparece un conocimiento nuevo.
- **El terreno guardaba 67 MB de arrays que nadie usaba**: `Terreno.gx` y `Terreno.gy`, los gradientes
  de la elevación, no se leían en ninguna parte. Se calculan, dan la pendiente y se sueltan.
- **`Terreno._c` pasó de 134 MB a 34 MB, con los mismos valores bit a bit.** Es la copia en listas que
  usa el A*; `tolist()` creaba un objeto float por celda, o sea 4,2 millones. Medido en un mundo real:
  en esos 4,2 millones de celdas hay **3.809 valores distintos de costo** (el costo sale de una tabla
  de biomas por un factor de pendiente de elevación entera, y dos tercios del mapa es `inf`), así que
  alcanza con compartir un float por valor.
- `olvidar()` no limpiaba `_ultima_charla`: quedaba una entrada por cada muerto, para siempre.

### Pendiente, con lo medido

- **El relieve no escala con el tamaño de celda, y eso rompe los mundos nuevos.** `ALTURA_MAX_M` y
  `PROFUNDIDAD_MAX_M` son constantes fijas de 3.000 m y no miran `tam_celda_m`, mientras que todos los
  tamaños de rasgo del ruido están en celdas. Resultado medido en un mundo de 2048×2048 con celdas de
  5 m, o sea **10,2 km de lado con 6.405 m de desnivel**: pendiente mediana de 58°, 16% del mapa
  bloqueado por pendiente más 60% de agua (67% intransitable), y caminar cuesta **21,6 veces** el costo
  base. El mismo mapa a 50 m/celda da 9° y costo 1,2, que son los números históricos con los que está
  calibrado todo lo demás. Decidido: el relieve va a escalar con el ancho real del mapa, y para que
  siga habiendo nieve y montaña los umbrales de alta montaña tienen que escalar con él (en 10 km no
  caben a la vez pendientes caminables y picos de 2.000 m: una montaña de 3.000 m mide 20 a 50 km de
  ancho).
- **El A* es ahora el 66% del CPU y falla 2 de cada 3 búsquedas.** Medido en 3 días simulados: 36
  búsquedas, 19,1 s dentro del A*, **24 fallidas** que tiraron 16,7 s a la basura. Toda búsqueda de más
  de 350 celdas falla, y el destino **está en la misma isla** (se comprobó: 1.367.281 celdas
  alcanzables). La causa es la de arriba: con costo mediano 21,6 y una heurística que vale 1 por celda,
  el A* subestima 21,6 veces y degenera en Dijkstra hasta agotar los 120.000 nodos. Falta además una
  **caché de búsquedas fallidas**: el mismo destino imposible se reintentó 12 veces, a 0,7 s cada una.
- **El hambre le gana la puja a la sed mortal.** Es la misma forma de bug que la muerte por sed, un
  escalón más arriba: en el mundo nuevo de prueba, de 68 decisiones con sed ≥ 80 el **72% eligió
  `cazar`** para `satisfy_hambre` y sólo el 12% `beber`. Nadie se murió en 60 días, así que no es
  urgente, pero contradice la regla de que lo que mata más rápido va primero (`CLAUDE.md`). Hay que
  revisar el mismo par para el frío y la energía.
- **La BFS `agua_cercana` falló a 28 celdas** en dos de los muertos. Hay que confirmarlo celda por
  celda antes de darlo por bueno.
- **Nada falla si el mundo mata a todos.** Falta una prueba larga que corra un mundo unos días
  simulados y exija que la población no colapse: es la que hubiera cazado la muerte por sed sin tener
  que mirar un mundo a mano.
- **El crash no se pudo reproducir.** Dos horas de intentos: 42 minutos del servidor asíncrono real con
  cliente conectado, 60 días simulados sin pantalla, 52 días en proceso y una corrida entera con
  `PYTHONMALLOC=debug`. Ninguna se cayó. Lo que sí quedó firme: la línea de la traza
  (`motor/fauna.py:187`) es aritmética de floats puros sobre valores verificados float (10 días
  simulados comprobando el tipo de cada coordenada: ni un escalar de numpy), y con el GIL activo una
  línea así no puede fallar sola. Y dos pistas de la traza original son ruido: `_asyncio.so` está
  debajo de toda corrutina porque `Task.__step` vive ahí, y la línea «Extension modules» la imprime
  `faulthandler` siempre. Queda esperando la próxima caída, ahora con registro.

## Pendiente — Plan de mejoras del motor

Hoja de ruta unificada en `docs/PLAN_MEJORAS_MOTOR.md` (absorbe al viejo `docs/PENDIENTE_MINERALES.md`).
**Las fases 0 a 7 están hechas** (ver 0.11.0 y 0.12.0 más abajo). Lo que queda:

- **Fase 6, la mitad de la UI**: el endpoint `POST /api/mundos/{nombre}/habitantes` existe y anda; el
  modal para usarlo no se hizo porque la interfaz la está tocando otra persona en paralelo. También
  faltan de la UI el dibujo de ruinas y de senderos (los datos ya salen publicados).
- **Fase 8**: celos, infidelidad y relajar `parentesco_cercano` ante colapso poblacional. El spawn de
  habitantes, que era la otra mitad de esa fase, ya está.
- Deuda vieja: los `hitos` siguen siendo **por dimensión** y el cráter de la fase E no excava el terreno.
- Pendientes de contenido más adelante: domesticación, comercio, mareas / ríos nuevos / volcán, y la
  pasada de optimización.
- **Hallazgo de campo (lo que queda es del lado del cerebro)**: auditado `mundo_580927131.db`
  (364 días simulados, 8 habitantes) hay **0 fogatas y 0 refugios construidos**, aunque los 8 saben
  `choza_de_barro` y `refugio_de_paja` y llevan 66–70 unidades de `palo`, `paja` y `arcilla` encima.
  Las 3.747 decisiones guardadas son todas del **motor cognitivo** (el híbrido en ese mundo nunca
  corrió) y se reparten así: 3.002 `esperar`, 316 `juntar_para_inventar`, 121 `beber`, 107 `comer`,
  88 `explorar`, 86 `dormir`, 18 `hablar`, 9 `ir_al_agua`, **0 `fabricar`**. Elegir qué hacer es del
  cerebro y vive en otro proyecto; de este lado queda que el mundo lo haga posible y conveniente.
- El tope por ítem del inventario es **por ítem, no por carga total** (`TOPE_LOTE = 60`, hasta 78 con
  fuerza alta): los 66–70 de cuatro materiales son cuatro topes distintos, no acopio ilimitado.
## 0.12.0 — Hogar, ruinas, minerales que inventa el mundo, senderos y la primera luz (fases 3 a 7)

### Nuevo

- **El calor de la fogata cae con la distancia** (fase 4). Antes era binario: 20 metros planos y un paso
  más afuera cero, daba lo mismo estar encima de las brasas que a 20 metros. Ahora hay núcleo, caída y
  radio, los tres en METROS y los tres dato de la estructura
  (`provee: {calor_C, nucleo_m, caida: "lineal"|"cuadratica"|"escalon"}`). Y son **dos curvas distintas**:
  para abrigarse la caída es gradual, para trabajar es escalonada y corta — no se funde metal «casi al
  lado» de la fragua.
- **La fogata abriga también a las chozas** (`abrigo_efectivo`): la misma choza abriga más si cae dentro
  del alcance de un fuego encendido. Ése es el incentivo físico que convierte un montón de chozas en una
  aldea sin que el motor tenga que saber qué es una aldea.
- **Cama propia**: `h.hogar_rid` apunta al refugio concreto y no a una coordenada suelta, y a igual abrigo
  `refugio_cerca` prefiere el propio antes que el del vecino.
- **Dormir mira DÓNDE se duerme.** Antes se descansaba igual en el barro que en la choza. Bajo techo se
  recupera hasta el doble, y el factor se mide una sola vez al acostarse (`h.cama`), no en cada tick.
- **Ruinas** (fase 4): una casa por la que no pasa nadie pierde abrigo y a la larga queda en ruinas; deja
  de ser el hogar de alguien, no cuenta como casa de una aldea y sale publicada aparte (`ruinas`) para que
  la UI la pueda dibujar sin cambiar lo que ya dibuja. Las bocas de caverna y los pozos no se arruinan.
- **Atractor de la fogata comunitaria**: en las horas de poca luz, tener fuego cerca abarata buscar a los
  demás y encarece irse lejos a explorar.
- **Minerales que el mundo inventa** (fase 3, `motor/minerales.py`): de 2 a 6 minerales por dimensión que
  **no están en ningún JSON de contenido**, con propiedades sorteadas de la semilla dentro del espacio que
  declara `datos_base/generacion/minerales_desconocidos.json`. Cada uno trae su metal, también inventado.
  Los nombres salen de sílabas y adjetivos visuales («veta lechosa») y nunca delatan una propiedad.
  **No se genera ninguna receta**: la de fundición mira la etiqueta `#mena_desconocida`, pide el calor del
  material que se esté usando (`requiere: {calor_C: "@mena"}`) y entrega el metal que ese material declara
  (`resultado: {desde_mena: true}`). Tres campos de datos y ningún `if` de contenido.
- **Desgaste del suelo y senderos** (fase 5, `motor/senderos.py`): el paso repetido abre el bioma
  `sendero_tierra`, que se camina más rápido, y el A* lo aprovecha solo. Sin tránsito durante estaciones
  el desgaste se desvanece y el sendero se cierra.
- **Spawn de habitantes** (fase 6): `POST /api/mundos/{nombre}/habitantes`. Llega sin padres, así que no
  es pariente de nadie: es lo que destraba el cuello de botella de sangre de la fase 8 sin tocar
  `parentesco_cercano`. Si no se le dice el sexo, elige el que esté en minoría entre los adultos vivos.
- **Electricidad** (fase 7): `energia_disponible(h)` calcado del calor, estructuras `pila` (6 W) y
  `dinamo` (80 W), y la cadena cobre → cable → dinamo → lámpara. La dinamo pide fragua: no se hace en la
  edad de piedra.
- **Hitos nuevos**, todos con la clave sacada del dato y no del nombre: «el primer metal» (cualquier
  receta con propiedad `funde`), «la corriente eléctrica» (cualquier estructura que provea `energia_W`) y
  «los primeros caminos».

### Arreglado

- `Terreno.cambiar_bioma()`: cambiar el costo de una celda ahora escribe en **las dos** representaciones
  (`costo`, el array, y `_c`, la copia en listas que usa el A*). Escribir sólo una dejaba al A* caminando
  el mapa viejo para siempre, y era la trampa principal de la fase 5.
- Al abrirse o cerrarse un sendero se **invalida el `h.camino`** de quien venía cerca: su ruta se calculó
  contra el mapa anterior. Sólo a quien pasa cerca, no a todo el mundo.
- `_provisto_en()` unifica calor y energía en una sola función con el campo por parámetro, y
  `requisitos_ok` recorre una tabla de magnitudes (`PROVISIONES`): la próxima magnitud física es una línea.
- `self.etiquetas` se compila una vez por mundo. Antes `_ingredientes_ok` **releía el JSON de etiquetas de
  disco en cada fabricación**; y además las etiquetas de un mundo ahora incluyen lo que ese mundo inventó.
- `fuego_cerca_de(x, y, r)`: la misma consulta desde un punto cualquiera y no sólo desde una persona, que
  es lo que hacía falta para preguntar por el calor que recibe una casa.
- Un horno ya no declara «primera vivienda» ni se vuelve el hogar de nadie.

### Pendiente de esta tanda

- La UI de todo esto (modal de spawn, dibujo de ruinas y senderos) quedó sin hacer **a propósito**: la
  interfaz la está tocando otra persona en paralelo. Los datos ya salen publicados.
- `afila` todavía no mejora herramientas, `aguja_imantada` no orienta a nadie y `calle_empedrada` no
  cambia la velocidad del terreno (son enganches para después).

## 0.11.0 — Se desbloquea el calor y llega la edad de los metales (fases 0, 1 y 2)

### Nuevo

- **El horno y la fragua se pueden construir.** La receta `horno_de_barro` ahora trae el campo
  `estructura` y su id coincide con el de la estructura (se renombró la estructura `horno` a
  `horno_de_barro`, no la receta, para que los mundos que ya guardaron ese conocimiento sigan
  sabiéndolo). La receta `fragua` no existía y ahora existe: pide `piedra` + `arcilla_refractaria` +
  `#carbon_de_fragua` y `requiere: {calor_C: 1000}`, así que **nadie hace una fragua sin tener antes un
  horno**. El techo real de calor del mundo pasó de 600 °C a **1500 °C** y la metalurgia es alcanzable.
- **Vocabulario de propiedades (fase 1)**: `funde`, `golpea`, `clava`, `mezcla`, `muele`, `afila`,
  `imanta` y `aisla`. Son JSON puro en `datos_base/propiedades/propiedades.json`; con ellas van 27.
  `funde` se apoya en el campo que ya existía (`punto_fusion_C`) en vez de inventar un `funde_a_C`
  paralelo: una magnitud física, un solo nombre de campo.
- **19 piedras y menas nuevas** en `datos_base/reglas/minerales.json`, más los metales y productos que
  salen de ellas (estaño, plomo, zinc, plata, oro, latón, aluminio, cal, mortero, cemento, vidrio,
  arcilla refractaria, clavo). Los ids son **descriptivos y no técnicos** (`piedra_rojiza`, no
  `mena_de_hierro`): la lista de materiales se le muestra a la persona y nadie nace sabiendo lo que
  tiene adentro una piedra. Cada mena lleva `mena` y `punto_fusion_C`, que es lo que lee el motor.
- **`cemento` y las calles existen de verdad** (eran un diccionario inventado dentro de un test), y con
  ellos la `casa_de_piedra` (abrigo 0.8), el escalón que le faltaba arriba a la cadena constructiva.
- **La roca dura pide herramienta**: `recoleccion.requiere.propiedad` en el material, y `disponibles()`
  lo respeta. Sin algo que `golpea` encima, las menas duras no se juntan, y el mensaje lo dice («está
  metido en la roca»). Es dato, no código: una mena nueva declara su herramienta sola.
- **La piedra negra (carbón mineral) es leña**, y dura 420 minutos por unidad contra los 150 de la
  vegetal: es el primer motivo concreto para bajar a la caverna.
- **Las recetas de fundición miran etiquetas, no ids** (`#mena_de_hierro`, `#carbon_de_fragua`), que es
  lo que va a dejar entrar sola a la fase 3: una piedra que el mundo invente esta mañana entra en la
  receta si la etiqueta la incluye.
- Un escalón de calor nuevo es un **hito** de la sociedad, y la clave sale del dato (los grados que
  provee), así que agregar una estructura más caliente no pide tocar Python.

### Arreglado

- **Validación de catálogo al arrancar** (`catalogos._validar_estructuras`), para que el agujero del
  horno no pueda volver: toda estructura que `provee` algo tiene que llegar al mundo por una receta con
  el mismo id, un bloque `natural` o `provisto_por: "motor"` (la fogata y el incendio los crea el motor);
  si existe la receta, tiene que traer el campo `estructura`; y ninguna receta puede pedir más calor del
  que da la estructura más caliente que se pueda construir.
- **Dos archivos del mismo catálogo ya no pueden declarar el mismo id.** El último alfabético ganaba en
  silencio: un `pico_de_piedra` nuevo en `metalurgia.json` lo tapaba el de `recetas.json` y el pico no
  servía para romper roca sin que nada lo avisara. Reemplazar desde `datos/extra/` sigue funcionando.
- `pico_de_piedra` pasó de `perfora` a `golpea` (un pico golpea; a `perfora` le quedan 9 recetas) y su
  ligadura ahora es la etiqueta `#ligadura` en vez de `tendon` a secas.
- **El tope de refugios es de casas.** Contaba cualquier estructura propia, así que levantar un horno y
  una fragua dejaba a la persona sin cupo para su propia choza. Ahora sólo cuentan las que abrigan.
- Un horno ya no declara «primera vivienda» ni se vuelve el `hogar` de nadie, y el hito de aldea dejó de
  medirse en **celdas** (`<= 20`) para usar `self.r_aldea`, que son metros convertidos.
- `recetas_con_propiedad()` tiene índice por propiedad: lo consultaba `disponibles()` varias veces por
  llamada recorriendo el catálogo entero, y el catálogo pasó de 127 a 151 recetas.
- `tests/test_calor.py` **fabrica de verdad** con `_aplicar` en vez de inyectar los refugios a mano, que
  es lo que había dejado pasar el bug durante meses. Nuevo `tests/test_metalurgia.py` con la cadena
  completa (pico → horno → cobre → bronce → fragua → hierro → acero → cemento → calle). 391 tests pasan.

## 0.10.1 — Invención autónoma, recolección de muestras y transmisión cultural activa

- **Desbloqueo de invenciones**: `_idea_para_probar` dejó de descartar recetas de 1 solo material. Ahora los habitantes descubren vasijas de barro, esterillas y capas de paja, cuerdas de fibra y cuchillos de piedra a partir de lo que llevan encima, priorizando recetas multi-ingrediente cuando disponen de combinaciones.
- **Cadena GOAP de experimentación**: `juntar_para_inventar` encadena con `inventar`, desacoplando la búsqueda de nuevos descubrimientos de la fabricación de recetas conocidas.
- **Consolidación en sueño y modulación psicoactiva**: `_t_dormir` dispara `consolidate_sleep` en el motor cognitivo para podar memorias e inducir patrones semánticos mientras descansa; `_personalidad` ahora absorbe dinámicamente los efectos temporales de `h.viaje` (aumento de curiosidad, baja de cautela ante plantas psicoactivas u hongos alucinógenos).
- **Drive de curiosidad**: nueva necesidad `CURIOSIDAD` en `NeedsSystem` modulada por el rasgo del genoma y el tiempo transcurrido sin descubrimientos.
- **Transmisión cultural intergeneracional**: la acción `ensenar` adquiere costo preferencial (0.8) sobre la charla casual (1.0), permitiendo que quien descubra una receta se la enseñe a sus parientes y allegados dentro del rango de habla.

## 0.10.0 — El cerebro se puede cambiar: Cognitive Engine manejando a los habitantes

Los habitantes ahora pueden pensar con **Cognitive Engine**, el proyecto aparte, en vez del cerebro
híbrido con modelo de lenguaje. Se elige al arrancar y no hay que tocar código:

```bash
MUNDO_VIVO_CEREBRO=cognitivo PYTHONPATH=src python3 -m mundo_vivo --datos <dir> servir --puerto 8767
```

- **El NPC se amolda al cerebro, no al revés.** El motor cognitivo tiene que poder correr en
  cualquier proyecto, así que no sabe nada de este mundo: ni celdas, ni biomas, ni el nombre de una
  sola cosa. Toda la traducción vive acá, en `agentes/cerebro_cognitivo.py`. Documentado en
  `docs/CEREBRO_COGNITIVO.md`.
- **Las cadenas de acción no están escritas.** El puente declara capacidades con precondiciones y
  efectos (beber pide agua al lado, ir al agua la vuelve alcanzable) y el planificador GOAP arma la
  secuencia solo. Agregar una capacidad nueva abre caminos nuevos sin tocar lógica.
- **Mismo contrato de siempre**: el cerebro propone, `Simulacion._aplicar` valida y ejecuta. El
  reflejo de huir del fuego no se delega.
- **Sin modelo no hay freno**: `pendientes()` es 0, `latencia_s` es 0 y el mundo deja de estar
  limitado por `tope_pensando`. La velocidad la pone la física.
- `Cerebro.cliente` ahora existe en la clase base y vale `None` cuando no hay modelo de lenguaje; el
  ejecutor dejó de asumir que siempre hay un cliente de Ollama al que apagar.
- 18 pruebas nuevas (`tests/test_cerebro_cognitivo.py`) que se saltean solas si el motor cognitivo no
  está en el entorno: Mundo Vivo no depende de él.

Un solo comando
- `./mundo.sh` nuevo en la raíz: `ver`, `adelantar <mundo> <días>`, `correr <mundo> <velocidad>`,
  `nuevo`, `listar`. El cerebro no se ejecuta aparte —corre en el mismo proceso—, así que no hay
  nada más que levantar.
- `simular` (el que adelanta días sin pantalla) **usaba siempre el cerebro de demostración**. Ahora
  respeta `MUNDO_VIVO_CEREBRO` igual que `servir` y `correr`, así que adelantar días por fin prueba
  el cerebro de verdad.
- Velocidad nueva **2000×** en la lista, y medida la real: 256² con 25 habitantes dan ~960 minutos
  de mundo por segundo de CPU; el mapa de 2048² con 4 habitantes, ~99. En el mapa grande el techo lo
  pone el **motor** (A* largo, fuego, nieve y clima sobre 4 millones de celdas), no el cerebro:
  pedir 500× no rompe nada, el bucle recorta y corre a lo que puede. Para adelantar un año conviene
  `adelantar` (sin presupuesto por vuelta): ~30 minutos de reloj para 120 días.

Hiperconectado: las 20 acciones del motor
- El puente declara **26 capacidades** que cubren todo lo que `_aplicar` sabe ejecutar: beber, ir al
  agua, comer, juntar, cazar, cocinar, curar, dormir, encender, tomar fuego, calentarse, hablar, ir
  hacia, buscar, enseñar, proponer hijo, responder propuesta, fabricar, inventar, usar, montar,
  desmontar, atravesar, explorar y esperar. Un test falla si alguna capacidad declarada no tiene
  traductor, o si sobra un traductor de algo que ya no existe.
- **Siete necesidades**, no cuatro: las del cuerpo (sed, hambre, energía, salud, calor) con curva
  cuadrática —no molestan hasta que aprietan—, más compañía y herramientas con curva lineal y
  declaradas «nunca críticas», que empujan de a poco y pierden siempre contra la sed.
- Medido en un día simulado (1.440 minutos, 4 habitantes, semilla 11): bebieron solos, juntaron
  materiales, **inventaron por su cuenta**, fabricaron capas de paja y cercas de palos, y durmieron
  de noche. 225 decisiones, cero capacidades sin traducir.

Arreglado mientras se cableaba
- `encender` e `ir_al_fuego` declaraban satisfacer la necesidad, así que el planificador **«comía»
  prendiendo una fogata**. Conseguir fuego es un medio: ahora lo que saca el frío es quedarse al lado
  (`calentarse`), y hay un test que verifica que el plan del hambre siempre termina comiendo.
- El piso del objetivo de reposo bajó a 0,3 (el default del motor es 0,5). Con 0,5 los habitantes se
  quedaban sentados una vez cubierto el cuerpo: no fabricaban ni buscaban a nadie.
- En el motor cognitivo, la holgura fisiológica que modula la curiosidad ahora mira **sólo** las
  necesidades que pueden volverse críticas. Las blandas (compañía, herramientas) apagaban la
  exploración sin tener nada urgente.
- Explorar cerca del borde del mapa se quedaba sin destino (los tiros al azar caían afuera) y la
  persona terminaba esperando: el tiro ahora se recorta contra los bordes. Es la trampa de
  «quedarse clavado sin poder explorar» anotada en `CLAUDE.md`.

Pendiente de este cerebro
- No miente: el híbrido tiene cuatro intenciones al hablar y acá el mensaje es siempre «contar».
  Tampoco se propone construir refugios, ni nada que dependa de redactar texto.
- Falta la prueba que importa: un mundo largo corriendo con él. Los peores bugs de este proyecto
  salieron de mirar un mundo que corrió horas, no de los tests.
- Costo anotado en `docs/OPTIMIZACION.md`: las creencias se recalculan enteras en cada decisión y
  `disponibles()`, `ausentes()` y `ver_animales()` ahora corren para todos, siempre.

## 0.9.9 — Bocas de caverna en la montaña

Pedido tuyo después de probar la G2: que no haya que construir un pozo para conocer la caverna, que si uno llega a una montaña encuentre el agujero y se meta.

- **Bocas naturales**: toda estructura puede declararse `natural: {biomas, cada_km2, minimo, maximo, separacion_m}` y el mundo la siembra solo, con su propia semilla, donde corresponda. La primera: **boca de caverna** en montaña y nieve, hasta 24 por mundo y separadas al menos 1,2 km. Están desde el día uno, no las construyó nadie, y sobreviven al guardado sin duplicarse.
- **Se ven de lejos**: el prompt las nombra cuando entran en el campo de visión («Ves una boca de caverna hacia el noreste, a 40 celdas. Si te parás al lado, podés meterte a ver qué hay»). Nunca se las nombra como «otro mapa».
- **Bajar y volver te deja donde estabas**: cada paso recuerda a dónde da, y la primera vez que alguien cruza queda del otro lado una salida de vuelta en el mismo punto. Ya no se vuelve a cualquier parte.
- En el visor los pasos se dibujan como un **agujero oscuro en la piedra**, no como una choza.

Pendiente
- **Minerales y metalurgia**, el próximo paso. Los metales existen como materiales y hay recetas que los usan, pero no hay forma de conseguirlos: ninguno tiene `recoleccion` y nada los produce, así que la edad de piedra no tiene salida. El diseño completo quedó escrito en `docs/PENDIENTE_MINERALES.md`: menas con nombres que no regalan nada (`piedra_rojiza`, `piedra_verdosa`, `piedra_gris_pesada`, `piedra_negra`), la propiedad `funde` para que se pueda descubrir solo, seis recetas de fundición que aprovechan la progresión fogata 600 → horno 1000 → fragua 1500 sin tocar código, y más adelante `energia_W` como segunda progresión física calcada de `calor_C`. El borrador de `datos_base/reglas/minerales.json` se borró a propósito: sumaba materiales que se podían juntar y no servían para nada mientras faltaran las recetas.

Arreglado
- Los tests de la fase B congelaban los 15 biomas y exigían «ninguno de más», así que los tres de la caverna los rompían. Ahora exigen lo que de verdad importa: que los 15 originales estén y no hayan cambiado, y que todo bioma nuevo lleve id **desde 100**. Igual en `/api/biomas`.

## 0.9.8 — Fase G2: dimensiones y portales (la última del plan)

Un mundo deja de ser un solo mapa. Ahora puede tener más de uno —el de siempre y, para empezar, **cavernas**— y una persona puede pasar de uno al otro.

Cómo quedó armado
- **Una `Simulacion` por dimensión** (`motor/mundo.py`), no una simulación con la dimensión metida como parámetro. El motivo es práctico: hay ~190 lugares que dicen `self.terreno`, y cada uno habría sido una chance de que alguien camine por el mapa equivocado. Así cada simulación sigue siendo exactamente lo que era.
- **Lo que es del mundo se comparte por referencia** (`Simulacion.compartir_con`): ajustes, conocimientos, relaciones, el cerebro. Inventar algo abajo lo sabe el de arriba; apagar un módulo lo apaga en todas partes. Lo que **no** se comparte es lo que depende del mapa: terreno, fuego, clima, fauna, nieve, estructuras.
- **El reloj es del mundo, no del mapa.** Si no, el que baja y vuelve se encontraría con que arriba pasaron otras horas.
- **Portales como datos**: una estructura con `provee.lleva_a` lleva a esa dimensión, igual que `provee.calor_C` da calor. El motor no sabe qué es un portal ni qué es una caverna. Dos recetas nuevas: **pozo a las cavernas** y **boca a la superficie**.
- **El mapa del otro lado se genera la primera vez que alguien cruza** y queda guardado. Un mundo que nunca vio un portal tiene una sola dimensión y se comporta **exactamente** como antes.
- **Generador de cavernas** (`_generar_cavernas`): autómata celular de roca y hueco, mismo molde que el fuego y las colonias. Se queda con **una sola cueva conectada** (nadie puede aparecer encerrado en una burbuja de roca), pone agua estancada en lo más hondo y hongales donde hay humedad. Tres biomas nuevos (caverna, roca viva, hongal) con ids desde 100, como manda la fase B. Tarda 0,3 s en 512×512.
- **Bajo tierra no hay cielo**: sin estaciones, sin nieve y sin tormentas. Son dos interruptores en los datos de la dimensión (`cielo.dia_noche`, `cielo.estaciones`), no un `if` de contenido.
- En el visor aparece un selector **sólo si el mundo tiene más de un mapa**: mientras haya uno solo, nadie tiene por qué enterarse de que la idea existe.

Migración 0009
- Tabla `dimensiones`, columna `dimension` en `capas` (la tabla se rehace: era `WITHOUT ROWID` con la clave vieja), `habitantes` y `eventos`, todo con default 0.
- `estado_dinamico` no se toca: la dimensión 0 sigue con las claves de siempre y las otras usan el prefijo `d<N>:`. Un mundo viejo abre igual y no pierde ni el fuego ni las casas.

Arreglado
- Construir algo sin abrigo (un horno, una fragua, un pozo) ya no explota por falta de `abrigo` ni lo convierte en «tu refugio».

Con esto el plan queda **completo**: A, B, C, D, E, F, G1, **G2**, H, I, J, K, L, M y N.

## 0.9.7 — Fase N: recordar por significado

Hasta acá un recuerdo se recuperaba por **palabras en común** con la situación. Si alguien recordaba «te atacó una araña venenosa» y lo que estaba viviendo hablaba de «un bicho ponzoñoso», el recuerdo existía y no se usaba nunca.

Nuevo (`agentes/semantica.py`)
- Cada recuerdo recibe un **vector de significado** en la columna `memorias.embedding`, que estaba vacía desde la primera versión: **cero migración**.
- `memoria.recordar()` puntúa la relevancia por **coseno** entre la situación y el recuerdo, y se queda con lo mejor entre eso y las palabras de siempre. Sólo puede sumar: lo que ya se encontraba se sigue encontrando.
- Modelo **chico y aparte** del de lenguaje (`nomic-embed-text`, ~270 MB), en **su propio hilo**: nunca se mete en el camino crítico de una decisión. Si el vector de la situación todavía no está, esa decisión sale por palabras y la siguiente ya tiene el significado.
- El trabajo de fondo **no toca la base**: el hilo devuelve vectores y el hilo del mundo los escribe. sqlite se usa desde un solo hilo.
- Si Ollama no tiene el modelo, después de 3 fallos deja de insistir y el mundo sigue recordando por palabras. Un vector vacío se guarda igual, como marca de «ya se intentó», así no se vuelve a pedir lo mismo para siempre.
- En el panel: modelo de embeddings configurable y la cuenta de **cuántos recuerdos se puntuaron por significado contra cuántos por palabras** (así se mide si sirve, que era parte del pedido).

**Módulo `semantica` APAGADO por defecto**, a diferencia del resto: necesita el modelo bajado (`ollama pull nomic-embed-text`). Encendido sin él sólo llenaría el panel de errores.

Arreglado
- Al cerrar un mundo se apagaban los hilos del modelo de lenguaje; ahora hay dos pools y `ClienteOllama.apagar()` corta los dos.

Pendiente: sólo G2 (dimensiones y portales).

## 0.9.6 — Fases L y M: quién piensa, y que hablar sirva para algo

**Fase L — LOD cognitivo** (`motor/atencion.py`)
- Tres niveles: **en foco** (piensa con el modelo), **segundo plano** (reflejos, hábitos y objetivos: decide igual, sin consultar) y **lejos** (avanza pero no delibera). El modelo es el cuello de botella del proyecto; con 4 personas se banca, con 25 no.
- **Quién está en foco lo decide la urgencia, no la cámara**: el que se muere de sed, el que tiene una propuesta esperando, el que está acompañado o al que le hablaron. Con rotación: el que hace dos días que no piensa sube solo, así nadie queda afuera para siempre.
- El visor muestra cuántos hay en cada nivel.

**Fase M — comunicación con consecuencias** (lo pide la sección 3.11 del documento de arquitectura)
- Hablar deja de ser sólo texto: ahora una conversación **cambia lo que el otro sabe**. Cuatro intenciones (`contar`, `advertir`, `preguntar`, `mentir`) y el modelo elige cuál usa.
- **Advertir** le pasa el peligro al otro y lo asusta un poco. **Contar** le pasa un lugar que uno sí conoce (agua, caza, refugio). **Preguntar** no transfiere nada. No se puede contar lo que no se sabe.
- **Se puede mentir**: el que escucha recibe un lugar que no existe, con la misma certeza que si fuera cierto. No tiene forma de saberlo hasta que vaya y no encuentre nada. El mundo sí lo registra como suceso, y mentir va corriendo el carácter (menos empatía, más agresividad).
- Todo lo que entra por conversación queda como **oído**, con quién lo dijo y su certeza (fase I), así que una mentira se puede propagar como rumor sin que el motor haga trampa.

Arreglado
- `test_inventar_y_ensenar` guioniza al modelo, pero no fijaba los módulos: los objetivos de la fase J inventaban otra cosa antes y el LOD podía dejarlo sin turno. Ahora apaga lo que decide por su cuenta, como ya hacía `test_fauna`.

**316 tests.** Pendiente: sólo G2 (dimensiones y portales).

## 0.9.5 — Fase F: especies que mutan y hongos que se propagan

**Mutaciones**
- Una especie puede declarar en los datos que a veces nace una **variante**, con la condición que haga falta: `{"prob_por_nacimiento": 0.012, "variantes": [{"a": "lobo_blanco", "temperatura_C": [-99, -2]}]}`. Gancho en `fauna._nacer()`.
- Dos para empezar: **lobo blanco** (nace donde hace frío, aguanta hasta -45 °C) y **ciervo pálido**. Con `copy-from` heredan todo de su base: **agregar una variante cuesta cuatro líneas de JSON**.
- La aparición queda como suceso importante y la recuerda quien la vio: «viste un lobo blanco que no era como los otros».
- Eso hace que un mundo largo no tenga siempre la misma fauna: la variante se reproduce sola a partir de ahí.

**Colonias** — `motor/propagacion.py`
- Hongos, líquenes y plagas: lo que se propaga sin caminar. **No son fauna y forzar `Fauna` para esto habría sido un error**: un hongo no se mueve, no caza, no tiene hambre. Es un autómata celular con los umbrales en los datos, mismo molde que `motor/fuego.py`.
- Dos para empezar: **moho verdoso** (pantano y selva, da hongo visionario) y **liquen gris** (montaña y tundra, da hierba medicinal).
- **Lo que se cosecha de una colonia puede llevar un material a donde no existía**, igual que lo que siembra un meteorito. Juntar parado encima de una colonia levanta lo que da.
- **Avanza por muestreo, no barriendo el mapa**: en 2048×2048 barrer cada tick es inviable. Se miran unas pocas celdas por día del mundo y la mancha crece igual, de a poco. Medido: 50 celdas de moho y 29 de liquen en 80 días.

Arreglado
- `catalogos.cargar_especies` era el cargador viejo y **no resolvía `copy-from`**: una variante que hereda de otra especie quedaba sin medio ni dieta y no validaba. Ahora sale del registro, como ya hacían las recetas desde la fase A.
- `test_montar_exige_rienda_y_acelera` comparaba contra una velocidad de terreno **fija de 1.0**, y con dos especies más el caballo aparece en otro suelo. Ahora compara montado contra a pie en el mismo lugar, que es lo que de verdad quiere medir.

**300 tests.** Pendiente: G2 (dimensiones), L (LOD cognitivo), M (comunicación con consecuencias).

## 0.9.4 — Plantas que mueven la cabeza

Pedido tuyo: que existan psicodélicos, que den alucinaciones y cambien cómo piensan.

- **`motor/psique.py`**: una planta declara en los datos qué le hace a quien la come — cuánto dura, qué emociones despierta, qué rasgos corre, con qué probabilidad hace ver cosas, cuánto empuja a probar ideas nuevas y qué riesgo tiene. El motor no conoce ninguna por su nombre.
- Tres para empezar: **hongo de las visiones** (selva y bosque: «el mundo late y los colores gritan», sube mucho la curiosidad), **cactus amargo** (desierto: «el desierto respira y el tiempo se estira», el más fuerte), y **baya del sueño** (bosque frío: pesadez y cautela, el más suave).
- **Los rasgos se corren de forma temporal y vuelven solos.** Un viaje no te cambia el carácter para siempre; lo que recordás de él, sí.

Lo que más me gusta de cómo quedó
- **Una alucinación es un recuerdo con procedencia `inferido` y certeza 0,2** — la pieza que puso la fase I. La persona lo recuerda y lo puede contar como propio, pero el sistema sabe que no lo vivió, y el que lo escucha lo recibe como rumor (`oido`, certeza según la confianza). **Una visión puede volverse leyenda sin que nadie mienta y sin que el motor haga trampa.**
- El prompt avisa que está bajo efecto y que no está seguro de lo que ve, así que el modelo decide sabiendo que su percepción está torcida.

Módulo `psique` en Ajustes. El efecto sobrevive al guardado.

**290 tests.** Pendiente: F (mutaciones y hongos que se propagan), G2 (dimensiones), L (LOD cognitivo), M (comunicación con consecuencias).

## 0.9.3 — Fase G1: los umbrales del generador como datos (y el mapa no cambió ni un píxel)

- **La clasificación de biomas salió del código.** Cada bioma declara en `datos_base/biomas/` en qué rangos aparece y con qué `prioridad` (el número más alto pisa al más bajo, igual que el orden de las líneas que había antes). Se aplica con **máscaras de numpy, no con el evaluador de condiciones**: clasificar 4 millones de celdas pasando por un intérprete de JSON no termina nunca.
- **Los umbrales de generación son un preset de dimensión** (`datos_base/dimensiones/`): altura y profundidad máximas, quantil de mar y de río, umbral de lago y de cascada, y los volcanes (altura mínima, realce, cráter). El **algoritmo** sigue siendo código — un generador nuevo es un algoritmo, no contenido — pero todos sus números son dato, así que una dimensión con el mismo generador y otros umbrales es sólo JSON. Verificado: con `quantil_mar` 0,75 hay 27.632 celdas de océano contra 20.275.
- **Criterio de aceptación cumplido: los mapas son idénticos.** Los hashes de dos semillas se congelaron ANTES de tocar nada y siguen dando lo mismo. Un mundo guardado conserva su mapa igual (se guarda el resultado, no la receta), pero si una semilla diera otro mundo, la semilla dejaría de significar nada.

Lo que costó hacerlo bien
- Mi primer formato de rangos `[mín, máx)` **cambió 3 celdas de 36.864**. La causa: `elev` y `temp` son **float** dentro del clasificador (se redondean recién al guardar), así que `> 2000` y `>= 2001` no son lo mismo. Agregué un tercer elemento `"abierto"` para el borde exclusivo. Sin el test de hash congelado esto pasaba sin que nadie lo notara.

**282 tests.** Pendiente: F (mutaciones y hongos), G2 (dimensiones y portales), L (LOD cognitivo), M (comunicación con consecuencias).

## 0.9.2 — Fases I y H: de dónde salió cada cosa que uno cree, y la cultura como dato

**Fase I — procedencia y certeza** (lo pide la sección 3.1 del documento de arquitectura: «escuchar algo no significa que sea verdadero»)
- Cada recuerdo sabe ahora **de dónde salió** (`vivido`, `oido`, `inferido`), **de quién** y **cuánta certeza** le da. Migración 0008; los recuerdos viejos quedan como vividos con certeza plena, que es lo que eran.
- Lo que a uno le cuentan entra como **oído**, con quién lo dijo y una certeza que sale de si se conocen, si son familia y si se tratan seguido. Un desconocido arranca en 0,5; la familia llega a 0,9.
- **El prompt lo distingue**: «te lo contaron», «te lo contaron pero no sabés si es cierto», «lo pensaste vos, no lo viste». Si se le muestran iguales, el modelo trata un rumor como un hecho.
- La certeza se calcula con lo que el motor SÍ sabe (parentesco, encuentros, trato reciente): el afecto y la confianza viven en la base y el motor no la toca a propósito.

**Fase H — cultura como dato**
- Los **13 disparadores de personalidad** estaban desparramados en cuatro archivos con deltas literales (`moldear(h, "cautela", 0.03, "los ataques...")`). Ahora son una tabla única en `datos_base/cultura/experiencias.json` y los call sites dicen `self.experiencia(h, "ataque_de_animal")`. **Es la perilla para ajustar que no se vuelvan cautelosos demasiado rápido** sin tocar código.
- Las **frases de temperamento** de `describir_temperamento()` pasaron a `datos_base/cultura/temperamento.json`. Es texto que lee el modelo: contenido puro. Se puede matizar o traducir sin tocar Python.

Arreglado
- **Había dos listas de módulos.** `Simulacion.__init__` tenía su propio diccionario que no incluía `personalidad`, `habitos`, `frio`, `atributos` ni `objetivos`: cada módulo nuevo **quedaba sin efecto en silencio** en cualquier simulación creada sin ajustes. Ahora sale de una sola fuente (`agentes/ajustes.py`) y hay un test que falla si alguna queda afuera. Lo encontré porque una experiencia no movía el carácter.
- `social.registrar_dialogo` ya guardaba el recuerdo del que escucha; mi primer intento agregaba otro igual y el deduplicador se quedaba con el viejo. El recuerdo se guarda en un solo lugar, ahora con su procedencia.

**277 tests.** Pendiente: F (mutaciones y hongos), G1 (presets de generación), G2 (dimensiones), L (LOD cognitivo), M (comunicación con consecuencias).

## 0.9.0 — Fase J: objetivos propios y encadenado de precondiciones

El agujero más grande del proyecto. Hasta ahora `h.plan` eran tres frases de texto que salían de la reflexión y que **nadie ejecutaba**: lindas de leer, sin ningún efecto.

Nuevo — `motor/objetivos.py`
- **Utility AI: qué querer.** Cada objetivo candidato se puntúa con el estado del cuerpo, el carácter heredado y lo que la red de hábitos aprendió de cómo le fue antes. No hay una lista de prioridades fija: gana el más urgente *ahora*. Con **histéresis**, para que no cambie de idea cada minuto, pero una urgencia real sí lo hace cambiar.
- **Encadenado de precondiciones (GOAP corto): cómo conseguirlo.** «Quiero una lanza» se desarma hacia atrás: ¿la sé hacer? → si no, inventarla. ¿Tengo los materiales? → si no, juntarlos. ¿Hay bastante calor? → si no, encender fuego. **Esto sólo es posible porque el registro de la fase A sabe qué pide cada receta**: sin él habría que hardcodear la tabla de dependencias, que es justo lo que sacamos del motor.
- **Replanifica cuando el plan deja de ser viable** (la zona se agotó, el material no se consigue acá): abandona el objetivo y prueba con el siguiente candidato en vez de quedarse trabado.
- El objetivo se guarda con la persona (sobrevive al reinicio), va al prompt («te propusiste conseguir un taladro de fuego porque te vendría bien») y se puede mirar desde el visor.
- Módulo `objetivos` en Ajustes.

**Medido, mismo mundo y misma semilla, 60 días, con y sin el módulo:**

| | Sin objetivos | Con objetivos |
|---|---|---|
| Vivos al día 60 | 2 de 3 | **3 de 3** |
| `cazar` | 763 | **144** |
| `comer` | 109 | **132** |

Pasaron de cazar 763 veces (manoteo desesperado detrás de los animales) a 144, **comiendo más**. Dejaron de correr y empezaron a juntar lo que tenían al lado.

Arreglado
- Un script de parcheo murió en la segunda sustitución **antes de escribir el archivo**, así que la primera se perdió en silencio y el módulo quedó desconectado: la corrida comparativa daba números idénticos y «quiere: nada». Vale como recordatorio: el `assert` va antes de empezar a tocar, no en el medio.

**259 tests.** Pendiente: fases F (mutaciones y hongos), G (dimensiones), H (cultura), I (procedencia de la información), L (LOD cognitivo), M (comunicación con consecuencias).

## 0.8.2 — Fase K: fuerza, resistencia y pulso que se construyen viviendo

Lo que pediste: que comer bien sirva para algo más que no morirse, y que las habilidades suban con el uso.

Nuevo — `motor/atributos.py`
- **Tres atributos (0..1), independientes entre sí y de las cuatro barras**: `fuerza` (cargar más, pegar más fuerte, juntar más), `resistencia` (aguantar caminando) y `pulso` (manos finas: fabricar más rápido).
- **Suben con el uso, con rendimientos decrecientes**: subir de 0,9 a 0,95 cuesta mucho más que de 0,3 a 0,4. Cada actividad entrena lo suyo (juntar la fuerza, caminar la resistencia, fabricar el pulso).
- **Para mejorar hay que estar comido y entero**: con hambre alta o salud baja no se progresa, se oxida. Eso es lo que hace que alimentarse bien tenga un premio y no sólo un castigo.
- **Lo que no se usa se oxida**, muy de a poco: nadie pierde en un día lo que le costó un año, y nunca baja de la mitad de la base.
- **Destreza por receta** (0..1): sube practicando ESA receta y no se contagia a las demás. Con pulso y práctica, fabricar lleva hasta un 45% menos de tiempo (nunca menos de la mitad).
- Los atributos **no se heredan** — eso es el genoma. Se construyen viviendo.
- En el prompt la persona siente su cuerpo, no lee números: «de tanto vivir, tenés brazos fuertes de tanto trabajar».
- Módulo `atributos` en Ajustes. Se guardan en el estado (que ya es JSON: sin migración) y sobreviven al reinicio.

Arreglado
- `_paso_atributos` llamaba a `rng.random()` **en cada tick** para decidir si oxidar las destrezas. Eso consume el generador del mundo y **rompe el determinismo de la semilla**. Ahora se acumula y se aplica una vez por día del mundo. Verificado: el mismo mundo con la misma semilla da exactamente lo mismo dos veces.

**Verificado en un mundo de 60 días**: Nico terminó con resistencia 0,44 (de tanto caminar) y la fuerza y el pulso oxidados a 0,21 y 0,17 porque no juntó ni fabricó. Sobrevive al guardado.

**249 tests.** Pendiente: fases F, G, H, I, J, L, M.

## 0.8.1 — El hambre dejó de matarlos a todos (y por fin se mueven)

Lo que reportaste: los tres fundadores muertos el día 3, quietos donde nacieron. Dos bugs, los dos míos.

Arreglado
- **No se movían: el A\* se quedaba sin presupuesto.** `_aplicar` llamaba a `buscar_camino` **sin pasar `self.nodos_camino`**, así que usaba el default de 40.000 nodos. A 5 m por celda, explorar 1,8 km son 360 celdas y eso no alcanza: **312 de 357 intentos fallaban** con «No encontraste camino» y quedaban clavados. Ahora usa el presupuesto de cada mundo. Medido: se alejan 130-690 m en los primeros días, antes 0.
- **El hambre que puse era brutal**: subía 43 por día y sacaba 172 de salud por día al llegar a 100, así que morían el día 3 sin tiempo de aprender a conseguir comida. Ahora sube ~17 por día (casi 6 días de ayuno) y la agonía es mucho más lenta.
- **Con hambre y sin comida encima no salían a buscarla**: el reflejo sólo comía lo que ya tenían. Ahora juntan lo comestible que haya en el lugar o cazan una presa sin riesgo.
- **El hambre iba después del frío**, así que `buscar_calor` se disparaba primero y nunca se llegaba a la línea de comer: 1426 «dormir» y 0 «juntar» en 9 días. Ahora el hambre va antes.
- **`buscar_calor` devolvía destinos inalcanzables** sin verificar que hubiera camino.
- **El despertador del hambre no miraba la energía**: se despertaban sin fuerzas para levantarse, se volvían a dormir, y morían de agotamiento. Mismo patrón que la muerte de sed al lado del agua. Ahora sólo despierta si le queda con qué actuar, y buscar comida pide energía mínima.
- **La causa de muerte decía «heridas»** cuando era hambre: faltaba en la lista de causas.
- Las plantas comestibles alimentaban muy poco y la zona daba 8 unidades: tres personas necesitaban 6 por día de una zona que producía 1. Subidas raíz, frutos, huevo y pescado (anotado en la copia congelada de `test_datos_motor.py` para que se vea que fue a conciencia).

**Medido con el cerebro de respaldo (sin modelo), 60 días, 4 semillas:** antes morían los 3 el día 3 en todas. Ahora una semilla llega con los 3 vivos y el hambre estable en 65-79; las otras pierden 1 o 2. **Sigue sin estar fino**: quedan muertes por agotamiento y por sed que son de balance, no de lógica, y conviene mirarlas con el modelo real andando.

**238 tests.**

## 0.8.0 — Fase E: fenómenos como datos (cae el primer meteorito)

- **`datos_base/fenomenos/`**: un fenómeno es un JSON con su disparador (probabilidad por día, desde qué día), dónde cae y una lista de efectos. El contrato es el de Factorio: **los tipos de efecto son primitivas de código; las combinaciones son datos.** Hay seis primitivas (`marca`, `sembrar`, `encender_fuego`, `dano_area`, `evento`, `recuerdo`) y cada una que se agregue queda disponible para siempre.
- **El meteorito**: deja un cráter, **siembra un material que antes no existía en ese bioma** (`hierro_del_cielo`), prende fuego alrededor, lastima a quien esté cerca, queda como suceso importante y deja un recuerdo fuerte en todos los que lo vieron a 4 km.
- Lo sembrado **se puede juntar**: `disponibles()` y `restante()` ahora suman los depósitos que dejó un fenómeno, así que un material puede llegar al mundo sin estar en ningún bioma.
- Se revisa una vez por hora del mundo, no por tick.
- Módulo `fenomenos` en Ajustes. Persiste en `estado_dinamico` y sobrevive al guardado.

**Límite conocido y documentado**: el terreno (elevación y bioma) se guarda una sola vez al crear el mundo y lleva un hash de integridad, así que un efecto **no puede excavar el mapa** sin invalidarlo. El cráter se guarda como una marca aparte, que persiste y la puede dibujar el visor. Excavar de verdad pide reescribir los chunks tocados y recalcular el hash: queda anotado.

Arreglado
- Metí el import de fenómenos dentro de un `try` ajeno y rompí el bloque. Lo cazaron 7 errores de colección.

**238 tests.** Pendiente: fases F a M (mutaciones y hongos, dimensiones, y las cinco cognitivas).

## 0.7.3 — Fases C y D: hambre, alimentos y progresión por temperatura

**Fase C — hambre y alimentos**
- **Cuarta barra, independiente de las otras tres.** Se puede estar perfectamente comido y con poca energía, o lleno y herido. El hambre sube con el tiempo y con el esfuerzo; desde 100 saca salud (0,12 por minuto, más lento que la sed que saca 0,3). Lo único que la liga a la energía: **dormir con hambre repone peor**. La salud sólo se regenera con hambre y sed bajas.
- **Cuánto alimenta cada cosa es un dato**: `alimento: {crudo, cocinado, podrido}` por material o ítem, con `hambre`, `energia`, `sed`, `salud` y `riesgo` de enfermar. Lo cocido alimenta más que lo crudo, lo podrido alimenta poco y puede descomponerte. El motor no conoce ningún alimento por su nombre.
- `HAMBRE_DESPIERTA` es **la misma constante** para motor y cerebro, como `SED_DESPIERTA`. Sin eso se repite la trampa de la sed: se despierta de hambre, se vuelve a dormir, y se muere con comida encima.
- Orden de necesidades por lo que mata más rápido: **sed (horas) → hambre (días) → cansancio**.
- Migración 0007. **El módulo viene apagado en los mundos que ya existían** (no se les cambian las reglas a mitad de partida) y encendido en los nuevos. Se prende cuando quieras desde Ajustes.
- `agentes/genoma.py:23` ya tenía `"hambre"` como entrada de la red neuronal y valía siempre 0: ahora está conectada. No invalida ningún genoma: la topología no se toca.
- Cuarta barra en el mapa y en la ficha.

**Fase D — progresión por temperatura**
- `requiere: {calor_C}` en las recetas y `provee: {calor_C}` en `datos_base/estructuras/`: fogata 600 °C, incendio 800, horno 1000, fragua 1500.
- `calor_disponible(h)` devuelve el **máximo** al alcance (dos fogatas no son un horno) y `requisitos_ok(h, receta)` reemplaza los seis `fogata_cerca(...) or fuego_cerca(...)` sueltos por una comparación de números.
- **Esto es lo que destraba cemento, calles y tendidos**: cada escalón es una receta con más grados, y la progresión emerge porque nadie hace cemento sin haber descubierto el horno antes. **Cero código por escalón** — hay un test que lo demuestra agregando el cemento sólo con datos.
- `requiere_fuego: true` se entiende como 400 °C, así que las 125 recetas y cualquier `datos/extra` siguen andando igual.
- La cerámica pasó a pedir 900 °C: con una fogata ya no sale, hace falta horno.

**232 tests.** Pendiente: fases E a M (fenómenos, mutaciones, dimensiones y las cinco cognitivas).

## 0.7.1 — Fase B terminada

Últimos tres bloques fuera del código:
- **Cuánto dura cada cosa** (`VIDA_DIAS`) y **en qué se convierte al cocinarla** (`CRUDOS`) pasaron a ser `conservacion: {vida_dias}` y `cocina: {resultado, minutos}` de cada material o ítem. `vida_dias: null` se declara explícito, así se ve en el dato que algo no se pudre.
- **Qué abriga** (`MATERIALES_ABRIGO`) pasó de ser una lista de cuatro nombres a un campo `abrigo` numérico por material: ahora cada uno puede abrigar distinto.
- **Los nombres** (`NOMBRES_F`/`NOMBRES_M`) viven en `datos_base/cultura/nombres.json`.

Arreglado
- `agentes/mente.py` seguía importando `CRUDOS` del motor. Lo cazaron 2 tests.

**216 tests.** De los 126 ids de contenido que el motor tenía escritos a mano quedan los imprescindibles (los que nombran mecánicas propias, no contenido).

Lo que esto habilita, sin tocar una línea de Python: materiales nuevos con dónde se juntan, propiedades nuevas (`funde`, `transmite`), biomas, armas con su alcance en metros, alimentos con su duración y su cocción, y nombres.

Pendiente: fases C a M (hambre con las cuatro barras independientes, progresión por calor, fenómenos, mutaciones, dimensiones y las cinco cognitivas).

## 0.7.0 — Fase B: el motor dejó de conocer el contenido por su nombre

De 126 ids de contenido escritos a mano en el motor quedan **39**. Lo que salió del código y pasó a ser dato:

- **Las 19 propiedades** (`_REGLAS` en `agentes/conocimiento.py`) eran lambdas de Python. Ahora son `datos_base/propiedades/propiedades.json`, con su descripción, su mensaje de error y una condición declarativa que evalúa `condiciones.evaluar` sobre la lista de materiales. **Inventar una propiedad nueva (`funde`, `transmite`) ya es agregar una entrada JSON.** Las entradas se validan al cargar: un JSON mal escrito hace fallar la apertura del mundo, no una partida de tres horas.
- **Los biomas** (`MULT_BIOMA` de `navegacion.py` y `COMBUSTIBLE_BASE` de `fuego.py`) viven en `datos_base/biomas/biomas.json` con su velocidad, su combustibilidad, su color y su `id_numerico` **congelado** — esos ids están guardados en la base de cada mundo y no se pueden reordenar nunca.
- **Armas, antorchas y objetivos** (`ARMAS`, `ANTORCHAS`, `OBJETIVOS` de `tecnologia.py`) en `datos_base/items/` y `datos_base/cultura/`. `SABER_ARMAS` de `ecologia.py` era un duplicado parcial: se borró y quedó una sola tabla.
- **Dónde se junta cada material** (`RECOLECCION`, `PROB`, `CANT`, `CAPACIDAD`, `LENA`) en `datos_base/reglas/materiales.json`.

Arreglado en el camino
- El alcance de las armas estaba **en celdas**: a 5 m por celda tenían 10 veces menos alcance que a 50 m. Ahora va en metros en el dato y se pasa a celdas al compilar.
- El orden de las antorchas importa (se prueba la primera que uno tenga encima) y lo había ordenado alfabéticamente. Ahora se respeta el orden del archivo.
- Al sacar las constantes me llevé puestos `_BOSQUES` y `_PASTOS`, que no son contenido sino atajos del motor.

Todo se hizo igual: **el test de red de seguridad primero** (copia congelada de los valores viejos), el JSON **generado desde las propias constantes** y no a mano, y recién después borrar el código. **210 tests.**

Pendiente de la fase B: `VIDA_DIAS`/`CRUDOS` (`conservacion.py`), `MATERIALES_ABRIGO` (`frio.py`) y los nombres de `vida.py`. Después: fases C a M.

## 0.6.7 — Fase B (1 de 7): dónde se junta cada material ya es un dato

Nuevo
- **`RECOLECCION`, `PROB`, `CANT`, `CAPACIDAD` y `LENA` ya no existen en Python.** Cada material declara en `datos_base/reglas/materiales.json` dónde sale, con qué suerte, cuánto rinde y cuánto aguanta la zona:
  `"recoleccion": {"biomas": ["bosque_templado","selva"], "prob": 0.9, "cantidad": [2,5], "capacidad_zona": 14}` y `"lena": {"minutos_por_unidad": 150}`.
  **Agregar un material que se pueda juntar ya no toca una línea de código.**
- `_compilar_materiales()` pasa el registro a tablas planas **una sola vez** al crear el mundo: el bucle de 20 Hz nunca toca el registro ni el evaluador (regla de `docs/OPTIMIZACION.md`).
- **La red de seguridad primero**: `tests/test_datos_motor.py` tiene una copia congelada de los valores originales y afirma que el registro devuelve exactamente lo mismo. Se escribió ANTES de mover nada y el JSON se generó desde las propias constantes de Python, no a mano: cero deriva de balanceo.

Arreglado
- Al sacar las constantes me llevé puestos `_BOSQUES` y `_PASTOS`, que no son contenido sino atajos del motor. Repuestos. (Lo cazaron 25 tests.)

Pendiente de la fase B: `ARMAS`, `VIDA_DIAS`/`CRUDOS`, las 19 propiedades de `conocimiento.py`, `MULT_BIOMA`, `COMBUSTIBLE_BASE`, los hitos y los biomas. **186 tests.**

## 0.6.6 — Fase A: el registro de contenido, y el fuego deja de matarlos de sed

Arreglado
- **Prendés un fuego y se mueren todos de sed.** Pasó de verdad (mundo 1528465001, día 19: los cuatro con `sed=100`). El reflejo de huir usaba el radio de **ver** humo (1,1 km), y `CerebroDemo` revisa el fuego **antes** que la sed: con un incendio a un kilómetro huían, llegaban, lo volvían a ver, huían de nuevo — y nunca llegaban a la línea de beber. Los datos lo muestran: d18 con 7 tragos de agua, d19 con cero. Ahora se separan **ver humo** (1,1 km, va al prompt) de **huir** (220 m), la sed mortal gana siempre, y ver humo lejano ya no cancela un viaje al agua a mitad de camino. Tres tests lo dejan clavado.
- Los radios de `refugio_de_fuego` seguían en celdas (24 y 55): a 5 m por celda buscaban refugio a 120 m del frente. Ahora van en metros.

Nuevo — **Fase A del plan data-driven** (`.claude/plans/`)
- **`src/mundo_vivo/registro.py`**: un registro único para todo el contenido. El tipo lo decide el campo `type` y no la carpeta, así los archivos que ya existen siguen funcionando donde están. Mezcla `datos_base/` con `datos/extra/`, resuelve herencia `copy-from` **encadenable** (`hoja → medio → base`) con detección de ciclos que nombra el archivo, soporta plantillas (`abstracto: true`) que sirven para heredar pero no existen en el mundo, y espacio de nombres opcional (`mundo:piedra` ≡ `piedra`, `otro:cosa` conserva su prefijo). Verificado sobre el contenido real: 125 recetas, 42 especies, 39 materiales, 6 etiquetas.
- **`src/mundo_vivo/condiciones.py`**: el evaluador único de condiciones en JSON, generalizado desde el que ya usaban las reacciones. Combinadores (`todas`, `cualquiera`, `no`), cuantificadores sobre listas (`alguno`, `todos` — lo que va a reemplazar a las 19 lambdas de `conocimiento.py`), y cuatro operadores nuevos (`en`, `no_en`, `contiene`, `entre`). `validar()` revisa la forma **al cargar**: un JSON mal escrito hace fallar la apertura del mundo, no una partida de tres horas.
- 16 tests nuevos de registro y condiciones. **181 en total.**

Pendiente: fases B a M. El plan ahora incluye también la arquitectura cognitiva (`docs/arquitectura/`): la auditoría dice que memoria, reflexión, Sistema 1/2 y personalidad **ya están**; lo que falta es procedencia de la información, objetivos con planificación real, destreza por habilidad, LOD cognitivo y comunicación con consecuencias.

## 0.6.5 — Salen a explorar, y los materiales ya se pueden agregar por JSON

Arreglado
- **Estaban encerrados y no se movían.** En el refactor de escala pasé a metros las distancias sociales y de tecnología, pero **me olvidé las de movimiento**, que quedaron en celdas: explorar llegaba a 30 celdas y el radio del grupo a 60. A 50 m por celda eso eran 1500 y 3000 m; a 5 m pasaron a ser **150 y 300 m**, mientras la zona de recursos sigue midiendo 800. Resultado real observado al día 11: los cuatro fundadores a menos de 130 m unos de otros, **61 intentos fallidos de juntar palo** en una zona ya vaciada, cero fogatas (encendieron una, se apagó y no pudieron juntar más leña) y lo único que hacían era hablarse. Ahora todas las distancias de movimiento van en metros y el radio del grupo **siempre supera a la zona de recursos**, con un test que lo bloquea.
- **`datos/extra/reglas/` no se leía nunca.** `Reglas.cargar()` se llamaba sin argumentos, así que solo miraba `datos_base/`. Se podía agregar una receta por JSON, pero si usaba un material nuevo fallaba la validación. Las recetas y especies sí respetaban `datos/extra` desde siempre: era una inconsistencia. **Ahora se pueden agregar materiales nuevos sin tocar código** (verificado: `piedra_caliza` en `datos/extra/reglas/` carga bien).
- El tope de velocidad mientras piensan subió de 40 a 90 minutos del mundo por decisión: casi duplica la velocidad y siguen decidiendo unas 16 veces por día. Los reflejos (sed, fuego, dormir) nunca dejaron de correr cada minuto.
- Volvió la opción **«Sin tope»** en Ajustes, ahora con una salida de verdad (antes el automático la pisaba igual) y diciendo claro qué pasa: el mundo corre a fondo pero dejan de construir, inventar y explorar.

Nuevo
- **Exploran lo que no conocen.** Antes tiraban un ángulo al azar, así que volvían siempre al mismo lado. Ahora puntúan varios destinos y prefieren las zonas donde nunca estuvieron (reusa `h.zonas`). Eso es lo que hace que recorran la isla en vez de dar vueltas.
- **Solos se animan menos**: hasta 1,8 km por su cuenta, hasta 4,5 km acompañados, y el aburrimiento los empuja más lejos. Siempre vuelven con los suyos.

Pendiente: el refactor del motor data-driven (fases A–H del plan) sigue **sin empezar**; lo único hecho de la fase A es el arreglo de `datos/extra`. Además, el pedido de que la comida suba fuerza y habilidades amplía la fase C: no es solo hambre, es un sistema de atributos que crecen con el uso.

## 0.6.4 — Escala real, sprites y el mundo deja de matarse solo
**Acordado con vos:** celdas de 5 m para que no se amontonen, gráficos 2D con sprites dibujados en código (nada de archivos), y arreglar lo que iba apareciendo al dejarlo correr.

Arreglado
- **Se morían de sed con el agua al lado.** Lo causé en esta misma tanda: el reflejo de dormir por cansancio iba antes que el de la sed, así que se dormían, la sed los despertaba a los pocos minutos, seguían cansados y se volvían a dormir. Ahora manda lo que mata más rápido (la sed saca 0,3 de salud por minuto desde 90; el cansancio 0,1 desde 5) y el umbral de despertarse y el de no volver a dormirse son **la misma constante** (`SED_DESPIERTA`), para que no puedan volver a separarse. Cuatro tests lo dejan clavado.
- **Todo se dibujaba con medidas fijas en celdas.** A 5 m por celda una fogata quedaba de 13 metros, más grande que una persona. Fogatas, refugios, antorchas, barras de estado, nombres y luz de noche pasaron a medidas **físicas en metros** con un mínimo en píxeles, igual que la gente.
- **Los cuatro fundadores arrancaban uno encima del otro**: se los ponía en celdas contiguas, pero `caminable_cerca` los encajaba a todos en la misma celda si la de origen no era transitable. Ahora se reparten en celdas distintas a ~25 m, y cada uno nace con su punto propio dentro de la celda.
- **Caminaban todos al centro exacto de la celda** (`tx+0.5, ty+0.5`), así que dos personas en la misma celda quedaban en coordenadas idénticas. Cada una tiene ahora su lugarcito, repartido por ángulo dorado y estable (sale del id, así que es reproducible desde la semilla).
- **El formulario de mundo nuevo ofrecía hasta 512×512**, que a 5 m son 2,5 km. Ahora se elige por tamaño real (5, 10 o 15 km) y avisa cuánto tarda.
- **El zoom llegaba hasta 48×**: con celdas de 5 m hace falta mucho más para separar a dos personas que están a dos metros. Ahora llega a 260×.
- `drawImage` con la capa de noche en 0×0 tiraba `InvalidStateError` si el lienzo se estaba re-acomodando.
- Un `from .persistencia import mundo_io` dentro de `main()` hacía local al nombre en toda la función y rompía el arranque de la línea de comandos.

Nuevo
- **Escala en metros.** Las distancias del motor estaban en celdas, así que cambiar el tamaño de celda rompía todo el comportamiento social. Ahora van en metros y se convierten una vez por mundo (`Simulacion.celdas()`). A 50 m por celda dan **exactamente** los números de antes, así que los mundos viejos no cambian. El presupuesto de nodos del A\* y de la BFS acompaña a la escala.
- **Mundos nuevos de 2048×2048 con celdas de 5 m** (10,2 km de lado). Medido: 86 s de generación, 1,1 GB de pico, 33,6 MB de capas. El bucle da 101 min-sim/seg contra 880 del mundo viejo, pero no importa: el modelo ya limita a ~3,6, que es 28 veces más estricto.
- **Sprites dibujados en código** (`ui/sprites.js`, sin archivos que bajar): cuatro edades (cría, joven, adulto y viejo encorvado con bastón), cuatro direcciones, caminata de tres cuadros, melena si es mujer. El ciclo de pasos avanza con lo que caminó, no con el reloj, así no patina.
- **Animales con forma propia**: una silueta por clase (cuadrúpedo, ave, pez, insecto, arácnido) orientada hacia donde va, y con el largo que le da su peso real — un ratón de 50 g y una ballena de 30 t ya no se dibujan iguales.
- **Terreno con textura**: grano determinista por celda, y con zoom alto una capa de detalle con matitas, árboles y piedras según el bioma, solo sobre lo visible.

- **Pantalla de carga de verdad**, con las etapas reales del generador (relieve, clima, ríos, biomas, guardado), barra, porcentaje y consejos que rotan. Para eso `POST /api/mundos` ya no bloquea: devuelve un trabajo y se consulta `GET /api/mundos/generando/{id}`. Antes el navegador quedaba 90 segundos sin saber si pasaba algo.
- **Los fundadores son distintos en cada mundo.** Antes eran siempre Ayla, Bruno, Celia y Dante, los cuatro en el medio. Ahora la composición sale de la semilla: una pareja sola, una pareja con un hijo, dos desconocidos en puntas distintas, una banda de 3 a 5, o varios grupitos repartidos. Los nombres se sortean. **Siempre hay al menos un hombre y una mujer adultos**: sin eso el mundo se muere sin empezar.
- Los grupos arrancan **en lugares distintos pero en la misma masa de tierra** (`Terreno.zona_conectada`): en islas separadas no se encontrarían nunca. La separación máxima es de 2 km a propósito, porque la vista llega a 1,5 km; más lejos pueden no cruzarse jamás y el mundo se extingue sin que se note.

Pendiente: hambre y plantas comestibles, domesticación, comercio, mareas/volcanes, caminos marcados por el uso, pasada de optimización. **Falta correr un mundo largo con el modelo real**: el bug de la sed apareció recién al dejarlo andar, no en los tests. Sería bueno un chequeo automático de sanidad (muertes absurdas, nadie que fabrique nada en N días). Y falta ver si dos grupos que arrancan separados **efectivamente se encuentran**; si se encuentran siempre, se puede subir el tope de 2 km.

## 0.6.3 — El mundo dejó de atropellar a las mentes
**Acordado con vos:** mirar el mundo que venía corriendo (día 405, 6 vivos, 2 muertos), entender por qué nadie construía nada, y que se vean las fogatas, las antorchas y las aldeas.

**Lo que se encontró en el mundo 377114351** (405 días, 8 personas, 131 sucesos): 0 fogatas, 0 refugios, 0 fabricaciones. Hablaban del «techo del nido» y de «mantener el fuego encendido», pero nada de eso existía. La causa: cada persona decidía **una vez cada 4 días del mundo**.

Arreglado
- **El tiempo ya no corre más rápido que las mentes**: con velocidad 500 y el modelo tardando ~11 s, cada pensada tapaba 5500 minutos del mundo (3,8 días). Ahora el automático deja pasar como mucho 40 min del mundo por pensada, y un tope fijo en los ajustes es un **techo**, no un permiso para atropellarlos (antes `velocidad_max_pensando: 500` anulaba el automático). Las **reflexiones también frenan el reloj**: antes no contaban como «pensando» y el mundo corría a fondo mientras alguien reflexionaba.
- **La reflexión se comía la mitad del modelo**: 427 de 753 consultas eran reflexiones (13,5 s cada una). Ahora es cada 3 días y solo si pasó algo nuevo (≥3 recuerdos desde la última). Libera ~40% del modelo para decisiones de verdad.
- **Los inventos ya se pueden fabricar**: lo que inventaban y no coincidía con el catálogo quedaba con `receta_id` vacío, así que nunca aparecía en «fabricar». 6 de 9 conocimientos del mundo eran saberes muertos. Ahora cada invento genera una receta real, que se vuelve a armar al cargar el mundo.
- **`plan_tecnologico` ya se usa**: el sentido común del motor (prender fuego, juntar lo que falta, construir) solo corría cuando el modelo estaba caído, o sea nunca. Ahora entra al prompt como una corazonada («se te viene a la cabeza armar una fogata acá»).
- **Las pistas de ideas tenían el fuego trancado**: la necesidad de `enciende` pedía saber `arde` primero, y `ata` (la menos urgente) siempre entraba y tapaba al resto por el sorteo. De ahí que 3 de 9 inventos fueran cuerdas y que nadie descubriera el `taladro_de_fuego` (palo + paja) en 405 días. Ahora las necesidades van por urgencia: fuego y abrigo primero, y se agregaron `construye`, `cura` y `contiene`.
- **Muertes por agotamiento** (Bruno día 393, Dante día 398, los dos fundadores varones): el reflejo de dormir iba después del de sed, así que con sed alta no se dormía nunca. Ahora con energía ≤ 12 se duerme antes que nada.
- **«Nació Sara, hijoa de Ayla»** → «hija».
- **El motor no validaba parentesco**: el cerebro podía proponerle formar familia a su propia madre y pasaba. Ahora lo valida el motor (`parentesco_cercano`), y se bloquean también los medio hermanos por padre (antes solo por madre).

Nuevo
- **Fogatas que se ven**: leños cruzados, brasas, llama que titila, hilo de humo y el tamaño según la leña que le queda. De noche iluminan mucho más (9 celdas) y son el centro de la escena.
- **Antorchas**: quien se llevó el fuego la lleva en la mano, con su llamita y su luz propia de noche.
- **Aldeas en el mapa**: los refugios a 20 celdas o menos forman una aldea, con su claro de tierra pisada y su nombre. `aldeas()` en el motor y en el estado público.
- **Refugios dibujados** como chozas (pared, techo a dos aguas, puerta) según el tipo, en vez de un emoji suelto; los muros de piedra se ven distinto.
- **Seguro contra la rama muerta**: si de un sexo no queda nadie vivo, el próximo nacimiento se inclina para ese lado.

Aldeas e interfaz
- **Las aldeas necesitan casas**: la pestaña Familias llamaba «Aldea N» a cualquier grupo de gente parada junta, aunque no hubiera construido nada, y las renumeraba cada 4 segundos ordenándolas por tamaño. Ahora usa las aldeas del motor (2 refugios o más a ≤20 celdas), el número es **estable** (una aldea sigue siendo «Aldea 3» aunque le agreguen casas o aparezca otra más grande al lado) y se guarda en el mundo. Cada casa tiene su `rid` propio; los mundos viejos reciben uno al cargarse.
- La aldea dice **quiénes viven ahí**, cuántas casas, cuántas fogatas y cuántas familias. Los que andan juntos sin construir aparecen aparte como «Sin aldea — duermen a la intemperie».
- **Edad en años del mundo**: antes decía «3000 d» y no se entendía nada. Ahora «3 años y 45 días», y «3a 45d» donde hay poco espacio (lista Gente, ficha y árbol genealógico usan la misma función).
- **El ajuste que rompió el mundo ya no está**: la opción «Sin tope» del tope de velocidad era justamente el 500 que hacía que cada persona decidiera una vez cada 4 días. Se sacó, y el texto explica que esto es aparte de la velocidad del mundo y que solo frena mientras alguien piensa (el mundo puede quedar en 500× tranquilo).
- **Pestañas que se escondían**: con 6 pestañas en una columna angosta, «Animales» y «Ajustes» quedaban detrás de un scroll horizontal sin barra. Ahora envuelven. Y Familias, Recetas y Animales tienen contador como ya tenía Gente, para no entrar a cada una a ver si pasó algo.
- Recetas y Animales entraban directo a una lista sin título; ahora tienen encabezado.

**Medido en un mundo nuevo al día 3** (contra el viejo al día 405): ~20 decisiones por día contra ~5; `reflexionar` pasó del 57% de las consultas al 5%; y descubrieron el `taladro_de_fuego` (palo + paja) el día 3, algo que en 405 días del mundo viejo no había pasado nunca.

Pendiente: hambre y plantas comestibles, domesticación, comercio, mareas/volcanes, caminos marcados por el uso, pasada de optimización. **Falta ver el mundo largo con el modelo real** (al día 3 el 57% de las decisiones son `hablar`: si sigue así a los 20 días, hay que mirarlo). Gráficos: se decidió ir a **2D con sprites** antes que 3D, porque la VRAM de 8 GB la necesita el modelo; la elevación ya está en los datos, así que el 3D queda disponible más adelante.

## 0.6.2 — Exploración, familias y una interfaz más clara
**Acordado con vos:** que no se queden pegados al agua; ver familias, aldeas y casitas; avisos de lo importante; arreglar barras, reloj y globos.

Arreglado
- **Quedarse quietos junto al agua**: los materiales de cada zona (16 celdas) se agotan al juntar y rebrotan en ~8 días; el prompt les avisa qué se agotó, qué «no se consigue acá» y cuántos días llevan sin alejarse. Así explorar pasa a ser necesario.
- **Reloj**: de noche la luna arranca del lado donde se puso el sol y recorre la mitad de abajo hacia donde sale; la mitad nocturna se pinta aparte.
- **Barras** de vida, sed y energía ahora también debajo de cada persona en el mapa (desde zoom medio).
- **Globos de chat** cortados: hasta 160 caracteres, 28 por línea, 6 líneas, y duran más cuanto más largo el texto.

Nuevo
- **Avisos emergentes** (importancia ≥ 4 y cambios de etapa); al tocarlos el mapa se centra en quien lo protagonizó.
- **Eras («hitos»)**: primer fuego, primer hijo, nietos, aldeas de 10/25/60 personas, etc., guardadas en el mundo.
- **Pestaña Familias**: aldeas (grupos cercanos, con casitas 🏠 y fogatas 🔥 y botón para ir a verlas) y árbol genealógico (parejas lado a lado, hijos debajo, nietos más abajo). API `GET /api/mundos/{n}/familias`.
- Edad en días en la lista de gente.

Pendiente: hambre y plantas comestibles, domesticación, comercio, mareas/volcanes, caminos marcados por el uso, pasada de optimización.

## 0.6.1 — Mentes propias, memoria de verdad y arreglos del mundo de un año
**Acordado con vos:** la memoria como eje de la evolución de cada persona; que cada una tenga su propia forma de pensar y cambie; zip solo al final de un bloque de mejoras.

Nuevo
- **Memoria v2** (migración 0006): recuperación por *recencia + importancia + relevancia* (palabras de la situación y cercanía del lugar), lo repetido se refuerza («ya pasó 3 veces») en vez de duplicarse, olvido diario de lo poco importante, tope de 400 recuerdos por persona.
- **Reflexión diaria**: una vez por día del mundo cada persona repasa lo vivido con el modelo y saca *aprendizajes* (duran 30 días de vida media) e *intenciones* para el día siguiente. Queda registrada en `decisiones` (acción «reflexionar»).
- **Lugares recordados**: agua, peligro, buena caza (con rumbo y distancia en lo que siente). Se persisten.
- **Memoria de dónde vio a cada persona** y acción **`buscar`** para reencontrarse; el prompt lista a los ausentes con rumbo y días.
- **Personalidad plástica** (módulo `personalidad`): los 7 rasgos cambian con la experiencia (ataques → cautela, buenas charlas → sociabilidad, inventar → curiosidad, soledad, muertes cercanas...) hasta ±0.25 de lo heredado. El genoma no se toca; los hijos heredan el genoma, no lo vivido. Los cambios de categoría quedan como suceso «personalidad».
- **Red propia que aprende** (módulo `habitos`, `agentes/habito.py`): cada persona tiene una red chica (~250 pesos, arranca distinta según su genoma) que aprende de las recompensas que vive (salud, sed, novedad, charla, descubrir, cazar) qué actividades le convienen. Sesga lo que siente el modelo («te tira cazar») y manda cuando el modelo no responde. En la ficha se ve lo que aprendió.
- **Velocidad automática** (`velocidad_max_pensando = 0`, predeterminada): el tope sale de lo que tarda el modelo (≈75 min del mundo por decisión).
- **Pistas para inventar** (`_ideas`): necesidades reales (animal que lastimó, agua, noche, frío...) sin regalar la receta.
- **UI rediseñada**: reloj completo siempre visible («Día N · hora · Estación · Año N»), pestañas, ficha que no salta ni cierra secciones, eventos como línea de tiempo por día con filtros.

- **Frío y nieve** (módulo `frio`, `motor/frio.py`): la temperatura = media del mapa + ajuste por estación (verano ≈ +14 °C de día, pleno invierno ≈ −12 °C de noche) y hora. Con ≤ 0 °C se acumula nieve (se ve en el mapa, 7º mapa dinámico persistido); con calor se derrite. La nieve frena el paso, apaga el fuego y evita que un rayo prenda la vegetación. El frío (< 6 °C) quita energía, y con frío fuerte impide recuperar salud y la debilita (muerte posible por «frío»). Se mitiga con la receta «abriga» + cuero/lana/pluma/fibra encima, con resiliencia y yendo a un sitio más cálido (reflejo). De día en clima templado casi nunca es grave. Los animales tienen `frio_min` (en `especies.json`, o deducido por clase y hábitat): los sensibles se mueren de a poco con frío y la inmigración repone. El prompt cuenta el frío y la nieve; el visor muestra °C y nieve.

- **Conservación de alimentos** (`motor/conservacion.py`): cada lote del inventario tiene edad; la carne cruda se pudre en ~1,5 días (pescado 1, carne cocida 5, curada 40, cuero 90, hueso/pluma/lana no). El calor acelera, el frío frena. Al pudrirse queda «podrido», un suceso y un aprendizaje («hay que cocinarla o curarla a tiempo»). Acciones nuevas **`cocinar`** (hace falta un fuego a ≤ 4 celdas) y **`curar`** (secar al aire, 3 h). Quien ya perdió comida aprende a conservarla solo (reflejo a ~35 % de la vida). El prompt muestra la frescura. Tope de 60 por ítem.
- **Edad a la vista**: la ficha muestra la edad (días/años) y los días del lote de carne; los animales muestran su edad media y su vida esperada.
- **Topes anti-acumulación**: efectos visuales ≤ 400 sin observador, caché de capas del servidor ≤ 3 mundos, poda diaria de eventos menores de más de 150 días (muertes y nacimientos se conservan), recuerdos y decisiones ya estaban acotados, decisiones del modelo en vuelo ≤ 1 por persona con descarte por timeout.

- **Catálogo grande de recetas y materiales** (`docs/RECETAS.md`): 39 materiales (palo, pedernal, pirita, resina, paja, arcilla, hilo, cuerda, tela, piel, tendón, grasa, sal, carbón, hierbas…), 123 recetas y 19 propiedades comprobables (enciende, ilumina, perfora, teje, contiene, construye, impermeabiliza, protege, dispara, pega, cura, conserva…). Fuego por frotar palos, por pedernal/pirita, eslabón, yesquero, arco de fuego y antorchas; armas, cuerdas, telas, ropa, vasijas, chozas, conservas y curación. Nadie las sabe de entrada: las descubren probando. Formato estilo Minecraft: etiquetas `#lena`, `tiempo_min`, `resultado`, `herramienta`, `requiere_fuego`.
- **Mapa que dibuja solo lo visible**: la porción de mapa en pantalla, ceniza, nieve, noche, fuegos, tormentas, animales y personas se recortan a lo visible; la capa de noche ya no es del tamaño del mundo. Con el mundo entero a la vista se usa una miniatura (baja calidad) y se dibuja a ~8 cuadros/s; de cerca, ~30.

- **Tecnología de verdad** (`motor/tecnologia.py`): ahora las recetas hacen cosas.
  - *Juntar* (`juntar`): cada bioma da sus materiales (palo, fibra, paja, hojas, resina, piedra, pedernal, pirita, sal, hierbas, frutos, raíces, huevos; arcilla y pescado junto al agua; madera con una herramienta de corte; ceniza y carbón junto a una fogata).
  - *Fabricar* (`fabricar`): hay que saber la receta, tener los ingredientes (se consumen; las etiquetas `#lena` aceptan cualquier material de la lista) y dedicarle `tiempo_min`. Entrega `resultado` (cuerda, hilo, tela, ladrillo, cerámica, carbón o el objeto). Si `requiere_fuego`, hace falta una fogata al lado.
  - *Fuego* (`encender`, `tomar_fuego`): con una fuente de chispa fabricada (taladro de fuego, pedernal, eslabón, yesquero, arco de fuego) y 2 de leña se enciende una fogata que dura horas, calienta (frío ×0,25 a ≤ 5 celdas), ilumina de noche y sirve para cocinar; se apaga sola (antes con la nieve). Se puede prender una rama en un incendio o en otra fogata y llevar la llama (antorcha encendida, dura ~5 h).
  - *Refugios* (`fabricar` de chozas/tiendas/cabaña/muro): tardan 5 a 24 h, quedan en el mapa, son el «hogar» de quien los hizo y reducen el frío (30–70 %). Máximo 3 por persona.
  - *Objetos que valen*: ropa fabricada abriga, la armadura reduce el daño de los ataques, las armas dan bono y alcance de caza **solo si las lleva encima** (antes valía con solo saber la receta), `usar` una cura recupera salud. Los animales grandes ahora dan además grasa, tendón, piel, cuerno o colmillo.
  - Sin modelo, el respaldo avanza solo: inventa lo que necesita, junta, fabrica, enciende y construye (en 12 días de prueba: taladro de fuego, cuerda, cuchillo, hacha, cesta, lanza, cataplasma).
  - El prompt lista qué se puede juntar acá, qué se puede fabricar ahora y qué falta. Fogatas y refugios se persisten y se ven en el mapa.
- **Deseo de formar familia**: sin esto nadie proponía hijos (el modelo no lo elegía y el respaldo ni lo tenía: en un mundo de 754 días no nació nadie). Ahora cada adulto siente ganas que crecen con los días sin hijo (≈1 a los 20 días, según sociabilidad), busca a una pareja posible (adulta, de otro sexo, no familia directa, sin embarazo), se acerca, propone y responde. En el prompt aparece como un sentimiento, no como una orden.

- **Eliminar mundos**: botón «Eliminar mundo» en la barra superior (pide confirmación; borra el mundo elegido y su estado, detiene su simulación sin guardar; los backups de migración no se tocan). API `DELETE /api/mundos/{nombre}`.

Arreglado
- **Interfaz con archivos viejos**: el navegador podía mezclar un `vivo.js`/`estilo.css` viejo con un `index.html` nuevo (se pierden barras de salud/sed/energía y relaciones de la ficha). Ahora el servidor manda `Cache-Control: no-cache` en toda la interfaz.
- **Muertes por sed**: una tarea larga (fabricar, construir) ya no deja pasar la sed (se interrumpe a 65); estar parado junto al agua ya no da «No encontraste camino»; huir de un animal elige un destino al que de verdad se puede llegar (antes repetía una huida imposible y no bebía).
- **Celia murió de sed a 3 celdas del agua**: la búsqueda probaba ≤ 12 caminos y se rendía si el agua más cercana estaba tras acantilados. Ahora es un recorrido (BFS) desde donde está y devuelve el agua *alcanzable* más próxima, aunque esté parada en una celda empinada.
- Los habitantes se dispersaban y no volvían a verse (7 % → 65 % del tiempo en vista en una prueba de 120 días).
- 0 inventos y casi todo «explorar» en un mundo de un año: causa = el mundo corría más rápido que sus mentes (una decisión cada ~2,2 días del mundo con 9b a 500×).
- Textos rotos: «Fuiste hacia explora.», «Te fue atacado por araña», derrumbes sin testigos como 194 eventos.

Pendiente (en este orden)
0. Que las recetas produzcan objetos de verdad (fogata, antorcha tomada de un incendio, ropa que abriga, armas), juntar materiales del mundo y domesticación/comercio. Ya están los datos; falta la mecánica.
1. Refugio y fuego de campamento (el frío ya está; falta dónde resguardarse).
2. Mundo que cambia: marea, ríos nuevos, volcán que se forma y erupciona.
3. Caminitos que se gastan, choza que lleva un día construir, hogar al que vuelven, mudanza tras incendio/inundación.
4. Optimización general (ver `docs/OPTIMIZACION.md`): medir y mejorar CPU, GPU, memoria, disco y visor en cada versión.
5. Recetas como datos más ricos (ingredientes, herramienta, tiempo, resultado, qué se puede hacer con cada material): ver nota en `docs/REGISTRO_DECISIONES.md`.
6. Hambre y plantas comestibles; fabricar objetos; domesticación; comercio.

## 0.5.0 — Animales, recetas y emociones
- 42 especies en `datos_base/fauna` (tierra, agua, aire; depredadores, venenosos, montables), ecosistema estable, cazar, ataques, montar con «rienda».
- Recetas editables (`datos_base/recetas`, `datos/extra/recetas`): catálogo vs. inventadas; panel de recetas.
- Emociones (miedo, tristeza, alegría, enojo) con decaimiento y una palabra en el prompt.
- Reglas sociales: no hablarle a quien duerme, espera entre charlas, no repetir; aburrimiento/novedad.
- Modelo elegible al crear el mundo y comando `ajustes`; `paralelo` 1–4 y tope de velocidad elegible.

## 0.4.x y anteriores
- Mundo procedural, ríos, fuego, tormentas, derrumbes; habitantes con genoma (7 rasgos + red de 82 pesos de reflejos), relaciones, conversación, reproducción por consentimiento, conocimientos y enseñanza; exportar/importar; visor y eventos. Ver `docs/REGISTRO_DECISIONES.md`.

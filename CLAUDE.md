# Mundo Vivo — guía para Claude

Mundo 2D procedural, persistente y autónomo. Cada habitante tiene mente propia (LLM local Ollama + genoma heredable + aprendizaje propio), relaciones, charlas, reproducción e inventos. Meta a largo plazo: ciudades y tecnología a lo largo de generaciones. La UI es solo de observación (mapa + eventos).

## Reglas del usuario (argentino, informal, a veces dictado)
1. **No entregar zip después de cada respuesta.** Analizar, arreglar y recién al final de un bloque de mejoras generar el zip. Nunca zipear con cosas prometidas sin arreglar.
2. Respuestas **concisas** cuando se conversa; sin listas largas. El modo `/caveman` (nivel `full`) va activo en **todas** las conversaciones de este proyecto, desde el primer mensaje y sin anunciarlo. Lo que queda escrito afuera del chat —código, comentarios, `CHANGELOG.md`, `docs/`— va en prosa normal igual.
3. No esperar procesos largos: correrlos en segundo plano.
4. **Registro de cambios**: toda actualización va en `CHANGELOG.md` (nuevo / arreglado / pendiente) y docs en `docs/`.
5. Backlog de recursos en `docs/OPTIMIZACION.md`. La eficiencia importa.
6. **El motor no conoce contenido por su nombre.** Materiales, propiedades, biomas, armas, alimentos, recetas y nombres son datos: `datos_base/<tipo>/*.json` + `datos/extra/`. El tipo lo decide el campo `type`, no la carpeta. Ver `registro.py` (carga, herencia `copy-from`, plantillas `abstracto`) y `condiciones.py` (el evaluador declarativo). **El evaluador NUNCA corre por celda por tick:** todo se compila a tablas planas en `Simulacion.__init__` (`_compilar_materiales`, `_compilar_conservacion`).
7. Las **recetas son datos** (JSON, estilo Minecraft): `datos_base/recetas/recetas.json`, `datos_base/reglas/materiales.json`, `datos_base/etiquetas/etiquetas.json`. Ver `docs/RECETAS.md`.
7. Todo se **descubre**, nada se sabe de entrada (`sabe(h, receta_id)`).
8. Los habitantes **nunca deben sospechar que viven en una simulación**: ni en prompts ni en textos que ven.
9. Zip: excluir `__pycache__`, `.venv`, `datos`, `.pytest_cache`, `*.pyc`.

## Stack
Python 3.13, FastAPI/uvicorn/websockets, numpy, SQLite (WAL), JS vanilla + Canvas. Ollama (qwen3.5:9b / 4b), usuario con Linux y RTX 4060 8 GB. Tests: Playwright para UI.

## Comandos
- Tests: `PYTHONPATH=src:. python3 -m pytest -q tests` (~140 s; correr en segundo plano)
- Servidor: `PYTHONPATH=src python3 -m mundo_vivo --datos <dir> servir --puerto 8767`
- UI en `ui/` (se sirve sin caché; recargar con Ctrl+Shift+R).

## Arquitectura
- Tiempo: 1 año = 120 días; bucle 20 Hz, estado 10 Hz; velocidad auto limitada por `tope_pensando()`.
- Cerebro por capas: reflejos del genoma → intenciones del LLM → respaldo (`CerebroHibrido` en `agentes/mente.py`: `_reflejos`, `_decidir`, `_respaldo`). **El motor valida, el cerebro propone.**
- `motor/simulacion.py`: `Simulacion`, armada con mixins. Uno por sistema: `vida`, `ecologia`, `frio`, `conservacion`, `alimentacion` (hambre), `atributos` (fuerza/resistencia/pulso), `atencion` (LOD cognitivo), `fenomenos_datos`, `objetivos`, `psique`, `propagacion` (colonias), `tecnologia`.
- `persistencia/sim_io.py`: guardado. `estado` de cada habitante es JSON, así que agregar un campo no pide migración.
- API: `api/servidor.py` (incl. `/api/mundos/{n}/familias`, `DELETE /api/mundos/{n}`, creación en segundo plano con progreso), `api/vivo.py` (WebSocket).
- UI: `ui/vivo.js`, `ui/mapa.js`, `ui/sprites.js`, `ui/index.html`.

## Estado (v0.12.0)
452 tests pasan. **El cerebro se puede cambiar**: `MUNDO_VIVO_CEREBRO=cognitivo` delega a Cognitive Engine (proyecto aparte en `/home/cracken/Mimundo/Cognitive Engine`, GOAP + Utility AI, sin LLM, determinista). El puente está en `agentes/cerebro_cognitivo.py` y declara las 20 acciones del motor como capacidades; las cadenas (cazar → cocinar → comer) las arma el planificador. Ver `docs/CEREBRO_COGNITIVO.md`. **El motor cognitivo no importa nada de Mundo Vivo**: el NPC se amolda al cerebro, nunca al revés. El motor ya **no conoce contenido por su nombre**: materiales, propiedades, biomas, armas, alimentos, estructuras, fenómenos, colonias, nombres y umbrales de generación son JSON.

Sistemas: metalurgia completa y **minerales que el mundo inventa** (ver `docs/MINERALES.md`), hogar propio, ruinas y **senderos por desgaste** (`docs/HOGAR_Y_SENDEROS.md`), electricidad (`energia_W`), memoria v2 con **procedencia** (`vivido|oido|inferido` + `de_quien` + `certeza`), hambre como cuarta barra independiente, **progresión por temperatura** (fogata 600 °C → horno 1000 → fragua 1500, de ahí salen cemento y calles), **objetivos propios** (Utility AI + encadenado de precondiciones), **atributos** que suben con el uso y se oxidan, **LOD cognitivo** (sólo unos pocos usan el modelo a la vez), **comunicación con consecuencias** (contar/advertir/preguntar/**mentir**), fenómenos como datos (meteorito), mutaciones de especies, colonias que se propagan, plantas psicoactivas, **recuerdos por significado** (embeddings, módulo `semantica`, apagado hasta bajar `nomic-embed-text`) y **dimensiones** (un mundo puede tener más de un mapa; una `Simulacion` por dimensión, ver `motor/mundo.py`).

**Escala:** distancias del motor en METROS, convertidas por mundo (`Simulacion.celdas()`, ver `_calcular_escala`). A 50 m/celda dan los números históricos. Mundos nuevos: 2048×2048 con celdas de **5 m** (10,2 km); generarlos tarda ~90 s.
**Gráficos:** 2D con sprites dibujados en código (`ui/sprites.js`), sin archivos. 2D y no 3D porque la VRAM de 8 GB la necesita el modelo.
**Límite conocido:** nada validado con el LLM real en un mundo largo. Los bugs graves (muerte de sed al lado del agua, 0 fogatas en 405 días, quedarse clavados sin poder explorar) aparecieron **mirando un mundo que corrió horas**, no en los tests.

## Plan vigente
`/home/cracken/.claude/plans/no-y-as-todas-cheerful-stallman.md`. **Terminado**: A, B, C, D, E, F, G1, G2, H, I, J, K, L, M y N.
Lo que sigue ya no sale de ese plan: contenido (abajo) y la pasada de optimización.

## Pendientes de contenido
Todo unificado en **`docs/PLAN_MEJORAS_MOTOR.md`** (8 fases; absorbió al viejo `docs/PENDIENTE_MINERALES.md`, que quedó como nota histórica).
**Fases 0 a 7 hechas** (v0.11.0 y v0.12.0; detalle en `docs/MINERALES.md` y `docs/HOGAR_Y_SENDEROS.md`):
- 0 a 2: el horno y la fragua se construyen y el techo de calor pasó de 600 °C a **1500**; 8 propiedades nuevas (`funde`, `golpea`, `clava`, `mezcla`, `muele`, `afila`, `imanta`, `aisla`); 19 piedras y menas con ids que no delatan su contenido; la cadena entera hasta el acero; `cemento`, calles y casa de piedra existen de verdad. El catálogo se valida al arrancar: una estructura que provee calor sin receta que la levante ya no puede pasar, ni dos archivos declarar el mismo id.
- 3: **minerales que el mundo inventa** (`motor/minerales.py`), 2 a 6 por dimensión, sorteados de la semilla, sin generar ni una receta (etiqueta `#mena_desconocida` + `requiere: {calor_C: "@mena"}` + `resultado: {desde_mena: true}`).
- 4: el calor **cae con la distancia** (núcleo, radio y curva, todo dato), la fogata **abriga a las chozas** (`abrigo_efectivo`: eso es lo que hace la aldea), cama propia (`h.hogar_rid`), dormir mira dónde, y ruinas.
- 5: **senderos** por desgaste (`motor/senderos.py`), con `Terreno.cambiar_bioma` que escribe en las DOS representaciones del costo.
- 6: `POST /api/mundos/{nombre}/habitantes` (sangre nueva, sin padres).
- 7: **electricidad**, calcada del calor (`energia_disponible`, pila y dinamo, cadena hasta la lámpara).
Lo que queda: la **UI** de la fase 6 (modal de spawn, dibujo de ruinas y senderos: los datos ya salen publicados) y la **fase 8** (celos, infidelidad, relajar `parentesco_cercano` ante colapso).
Más adelante: domesticación, comercio, mareas/ríos nuevos/volcán, pasada de optimización.
Deuda anotada de G2: los `hitos` quedaron **por dimensión** (lo descubierto abajo se puede volver a anunciar arriba) y el cráter de la fase E sigue sin excavar el terreno.

## Trampas ya vistas
- **No confiar en un conteo de SQL sin saber si eso se guarda o se deriva.** «Cero aldeas en la base» no prueba nada: `aldeas()` las **deriva** de `refugios` en cada llamada y nunca las guarda. El cero real era otro y peor: en un mundo de 364 días había **0 chozas y 0 fogatas** con los 8 habitantes sabiendo las recetas y llevando 66–70 de `palo`, `paja` y `arcilla` encima. Ver la sección «Hallazgo de campo» de `docs/PLAN_MEJORAS_MOTOR.md`.
- **Y tampoco confiar en un conteo de EVENTOS.** Los «6 eventos de fabricación en todo el año» de ese mismo mundo no son 6 fabricaciones: los repetidos salen con `importancia: 1` y no quedan todos. Mara tenía 34 capas de paja encima. Para saber qué decidieron, la tabla es `decisiones`; para saber qué tienen, el `estado` de `habitantes`.
- **Ese mundo corrió con el cerebro COGNITIVO, no con el híbrido.** Las 3.747 decisiones guardadas son todas de `cognitive-engine`: 3.002 `esperar` y **0 `fabricar`**. Antes de atribuirle una conducta a un cerebro, mirar la columna `modelo`.
- **`TOPE_LOTE` es un tope por ÍTEM, no de carga total.** 66–70 unidades de cuatro materiales son cuatro topes distintos (60, hasta 78 con fuerza alta), no acopio ilimitado.
- **Una estructura declarada no es una estructura alcanzable.** El horno y la fragua vivieron meses en `estructuras.json`, leídos por `calor_disponible()`, sin ninguna receta que los levantara. El test pasaba porque hacía `refugios.append(...)` a mano: verificaba el lector y nunca el escritor. Al agregar algo que el mundo tiene que poder construir, el test tiene que **fabricarlo de verdad** y recién después medir. Y el id de la receta con `estructura` tiene que ser **el mismo** que el de la estructura: `_accion_fabricar` guarda `tipo: r["id"]`. Desde la fase 0 hay validación de catálogo (`catalogos._validar_estructuras`) que no deja arrancar el mundo si eso se rompe.
- **Un id, un solo archivo.** Dos archivos de la misma carpeta de catálogo declarando el mismo id: ganaba el último alfabético y la otra entrada no existía para nadie (un `pico_de_piedra` nuevo lo tapaba el viejo). Ahora es error de catálogo; reemplazar desde `datos/extra/` sigue andando.
- **Prioridad de necesidades**: lo que mata más rápido va primero. `SED_DESPIERTA` la comparten motor y cerebro; si se separan, el que duerme se despierta por sed, se vuelve a dormir y muere con el agua al lado.
- **Ninguna distancia va en celdas**: ni las sociales, ni las de movimiento, ni las de dibujo. Siempre metros convertidos con `Simulacion.celdas()`. El radio de exploración TIENE que superar a `METROS_ZONA` o quedan atrapados en una zona vaciada.
- **El costo del terreno vive en DOS lados.** `Terreno.costo` es el array y `Terreno._c` es una copia en listas que es la que usa el A*. Cambiar una celda sin tocar las dos deja al A* caminando el mapa viejo para siempre: usar `Terreno.cambiar_bioma()`. Y al cambiar el costo hay que invalidar los `h.camino` de quien venga cerca.
- **Nada se dibuja con tamaño fijo en celdas**: a 5 m/celda una fogata de 2,6 celdas son 13 metros. Siempre `max(px/escala, metros/tam_celda_m)`.
- Los tests crean mundos chicos (64–192 celdas): **fijan `tam_celda_m=50`** a propósito. A 5 m serían de menos de 1 km y los radios sociales taparían el mundo entero.
- La BFS `agua_cercana` debe respetar la regla de esquinas del A* (`Terreno.buscar_camino`).
- Tareas largas deben chequear sed (interrupción en ≥65).
- En `vivo.js`, definir `const` antes de usarlos (zona muerta temporal).
- El sandbox no tiene `sqlite3` CLI: usar Python.
- **El modelo tiene que entrar en la placa.** Con 8 GB, un modelo de 27B (17 GB) entra en ciclo de carga y desalojo (`predicted to exceed available memory, evicting`): ninguna respuesta llega y el panel muestra «timed out». 4b y 9b andan.
- **Una sola lista de módulos**: sale de `agentes/ajustes.py`. Hubo un diccionario aparte en `Simulacion.__init__` y cada módulo nuevo quedaba **sin efecto en silencio**. Hay un test que falla si alguno queda afuera.
- **Antes de mover una tabla del código a datos**: escribir primero el test con la copia congelada de los valores viejos, y generar el JSON **desde las propias constantes de Python**, nunca a mano. Así se cazaron el alcance de armas en celdas, el orden de las antorchas y 3 celdas de bioma que cambiaban por `>` contra `>=`.
- **Rangos de clasificación**: el formato es `[mín, máx)`. Un tercer elemento `"abierto"` deja el mínimo afuera. Hace falta porque elevación y temperatura son **float** dentro del clasificador.
- **El generador aleatorio del mundo es sagrado**: no gastarlo en el bucle (ej. `rng.random()` por tick) o se rompe el determinismo de la semilla.
- **Los tests que guionizan al modelo** tienen que apagar `objetivos` y `atencion`: si no, el respaldo decide antes o el LOD le saca el turno.
- Al tocar el prompt o el modelo, mirar `latencia_s` y `rechazos_llm` en el panel: `tope_pensando = 90 / latencia`, así que la latencia **es** la velocidad del mundo.

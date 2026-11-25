# Etapas 2, 4, 5 y 6 de WORLD_ARCHITECTURE

Objetivo: cerrar las etapas pendientes del plan de arquitectura del mundo (generador, caché de rutas,
desacople motor/visor y chunks/LOD), sin romper mundos guardados ni los 465 tests actuales.
Rama: `etapa1-unidades-fisicas` (sin commits nuevos; el usuario decide cuándo commitear).
Entrega: `ask-on-risk`. Runner: `PYTHONPATH=src:. python3 -m pytest -q tests`.

## Specs

### S1 — Etapa 2, generador (WORLD_ARCHITECTURE.md §7)
> 1. Escalar todos los parámetros de fbm por `tam_celda_m`.
> 2. Escalar `_a_metros` por `tam_celda_m / 50` (ya hecho).
> 3. Agregar erosión hidráulica (D8) para ríos.
> 4. Verificar que la pendiente mediana sea ~1-2 a cualquier escala.

Criterio de aceptación propio, porque el punto 1 literal (`w / (4 * tam_celda_m)`) es dimensionalmente
incorrecto: el tamaño físico de una feature debe conservarse, no encogerse al bajar `tam_celda_m`.
Se escalan las constantes **físicas** que hoy están en celdas (micro-relieve, suavizado, distancia al
agua, radios de volcán, tamaño mínimo de lago), se deja `w/4` (ya es invariante si el mapa físico no
cambia) y se pasa `tam_celda_m` a la clasificación para que `pendiente` sea m/m. Test de invariancia
de pendiente mediana entre 64×64@50 m y 640×640@5 m (mismo tamaño físico).

### S2 — Etapa 4, caché de rutas
> 1. Cachear rutas exitosas con key (origen, destino).
> 2. Invalidar por `cambiar_bioma` y por tiempo.
> 3. Limitar tamaño de caché (LRU).

Criterio: la invalidación por tiempo no aplica mientras el terreno sea estático; la única mutación real
del costo es `cambiar_bioma` (senderos). Se documenta y se invalida ahí. Se devuelve una copia para que
el llamador no corrompa la caché al hacer `pop(0)`.

### S3 — Etapa 5, desacoplar motor/visor
> 1. Mover la simulación a un proceso/thread separado.
> 2. Comunicación por cola (multiprocessing.Queue o Redis).
> 3. El renderer solo recibe deltas.
> 4. El motor no conoce al visor.

Criterio realista: el bucle ya corre en una task asyncio dedicada con presupuesto (`api/vivo.py`), y la
conexión SQLite está atada al hilo. Un proceso aparte es un cambio de despliegue, no de arquitectura
interna. Se extrae la serialización a `api/presentador.py` y se borra del motor: `Simulacion` deja de
tener `estado_publico*`. El test fija ese invariante. Los deltas ya existen (Etapa 3, `vitales`).

### S4 — Etapa 6, chunks y LOD
> 1. Dividir el mapa en chunks de 64×64 celdas.
> 2. Solo simular chunks con entidades.
> 3. LOD: habitantes lejanos se actualizan cada N ticks.
> 4. Spatial hashing para fauna y proximidad.

Criterio: se implementa el índice de chunks y se usa donde hay una ganancia medida y sin cambiar
conducta: el autómata de fuego deja de recorrer el mapa entero y trabaja sobre el bounding box de las
celdas encendidas + margen (con caída al camino completo en mapas chicos, que es lo que usan los tests).
El LOD cognitivo ya existe (`motor/atencion.py`) y la grilla espacial de fauna ya existe (`motor/fauna.py`);
no se duplican. `chunks_activos` se publica para el visor.

## Tasks

- T1 (S1) Escalar constantes físicas del generador por `tam_celda_m`. — inline
- T2 (S1) `pendiente` en m/m en `_clasificar` + migrar el rango de `datos_base/biomas/biomas.json`. — inline
- T3 (S1) Erosión hidráulica y térmica determinista, sin tocar océano. — inline
- T4 (S1) Tests de invariancia y erosión + regenerar `REF_42_128` + subir `VERSION_GENERADOR`. — inline
- T5 (S2) LRU de rutas exitosas en `Terreno`, copia defensiva e invalidación en `cambiar_bioma`. — inline
- T6 (S2) Tests de caché: hit, copia, invalidación, tope. — inline
- T7 (S3) `api/presentador.py` con `estado_*`, `habitante_mapa`, `habitante_completo`. — inline
- T8 (S3) Borrar serialización de `Simulacion`; actualizar `vivo.py`, `__main__.py` y tests. — inline
- T9 (S3) Test de invariante: el motor no expone `estado_publico`. — inline
- T10 (S4) `motor/chunks.py` con actividad por chunks de 64. — inline
- T11 (S4) Fuego por bounding box + margen, con fallback completo. — inline
- T12 (S4) Publicar `chunks_activos` en el presentador + tests. — inline

## Log

- L1: «dale termina todas» (pedido original, reconstruido del resumen de sesión).
- L2: «Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.»
- L3: el plan literal de S1.1 (`w / (4 * tam_celda_m)`) no conserva el tamaño físico; se implementa la
  versión dimensionalmente correcta y se deja anotado en el CHANGELOG.
- L4: S3.1/S3.2 (proceso aparte, cola) no se ejecutan: SQLite atado al hilo y el bucle ya es una task
  asíncrona con presupuesto. Se entrega el desacople lógico verificable (presentador) y se documenta.

## Etapas que quedan (plan armado 2026-11-25)

Ordenadas por relación valor/riesgo. A y B son técnicas y cerrables sin mirar un mundo; C es la que
alimenta tu prueba en vivo; D y E son contenido; F es la pasada de optimización.

### A — Fuego por bounding box (cierra T11)
Objetivo: cuando hay celdas encendidas, el autómata de propagación trabaja sobre el bbox + halo de 2
celdas en vez del mapa entero; si el bbox cubre >50% del mapa, cae al camino completo (mapas chicos de
los tests). El rebrote sigue como está (ya está gateado por `_sucio` y por `REBROTE_CADA_MIN`).
Tareas:
- A1. Extraer `_bbox_ardiendo()` (ys/xs nonzero → y0,y1,x0,x1).
- A2. En `paso`, si el área del bbox < 0.5·total, correr `_suma_vecinos` sobre la región con halo tomado
  del mapa completo y escribir de vuelta solo el interior; el resto igual.
- A3. Test: un foco chico en 256² da el mismo resultado que el camino completo (comparar `fuego` y
  `comb` tras N pasos), y un mapa chico sigue usando el camino completo.
Aceptación: mismo estado final que antes, sin tocar la semántica; el test de equivalencia es obligatorio.

### B — Chunks que simulan de verdad
Objetivo: `chunks_activos` deja de ser solo informativo; los sistemas caros por celda se gatean por
chunk. Candidatos con ganancia medible: rebrote de combustible, propagación de colonias y actualización
de fauna fuera de cámara.
Tareas:
- B1. Medir antes/después con un mundo de 2048² (perfilar `paso` por sistema; guardar números).
- B2. Gatear el rebrote de fuego por chunk (solo chunks con comb<umbral o quemado).
- B3. Gatear la propagación de colonias por chunk activo (no cambiar resultado, solo evitar el barrido).
- B4. Test de equivalencia de estado con y sin gateo en un mundo de prueba.
Aceptación: mismos resultados, CPU del sistema medido baja; si no hay ganancia, no se mergea.

### C — Observación de campo (la que dispara tu prueba en vivo)
Objetivo: convertir lo que veas en el mundo levantado en fixes priorizados, no en parches a ciegas.
Qué mirar (panel + DB):
- `latencia_s` y `rechazos_llm` → si la latencia sube, `tope_pensando` baja y el mundo se frena: atacar prompt,
  modelo o presupuesto de atención.
- `decisiones` filtradas por `modelo`: si es `cognitive-engine`, la conducta es GOAP; si es híbrido, es LLM.
  Nunca atribuir conducta sin mirar la columna.
- `estado` de habitantes (no eventos): qué tienen encima, si construyen, si se quedan clavados.
- Derivas de conteo: chozas/fogatas (#), senderos, colonias, muertes por sed al lado del agua.
Tareas:
- C1. Agregar al presentador (o endpoint de estado) un bloque de métricas: A* hits/misses de la caché,
  ms por sistema, habitantes por chunk activo, fuego activo.
- C2. Checklist de campo en `docs/` con síntoma → sistema → hipótesis → test que lo fija.
- C3. Cada bug que aparezca se fija con un test que **fabrique de verdad** (no `append` a mano) y se
  registra en `CHANGELOG.md`.
Aceptación: ningún fix sin reproducción; el mundo largo es la fuente de verdad, no los tests solos.

### D — UI de la fase 6 del plan de mejoras
Objetivo: cerrar lo que los datos ya publican y la UI no dibuja.
Tareas:
- D1. Modal de spawn (`POST /api/mundos/{n}/habitantes`) con nombre/sexo opcional.
- D2. Dibujar ruinas y senderos (ya salen publicados en el bloque pesado).
- D3. Capa de chunks activos (debug, apagable) para ver el LOD espacial.
Aceptación: se ve en el mapa sin recargar; sin costo perceptible por cuadro.

### E — Fase 8 de relaciones
Objetivo: celos, infidelidad y relajar `parentesco_cercano` ante colapso poblacional.
Tareas:
- E1. Datos primero: umbrales y pesos en `datos_base/` (no hardcodear).
- E2. Motor: celos/infidelidad con consecuencias observables (no solo texto).
- E3. Colapso: si la población cae bajo N, permitir parentesco más lejano con degradación avisada.
- E4. Tests de comportamiento y de que el colapso no explota la población.
Aceptación: consecuencias visibles en `decisiones` y `eventos`, sin sospecha de simulación en prompts.

### F — Pasada de optimización general
Objetivo: lo que el backlog de `docs/OPTIMIZACION.md` deje después de A–C.
Tareas:
- F1. Compresión/chunking de capas guardadas (~30 MB por mundo).
- F2. Costo de movimiento por pendiente² (hoy pendiente).
- F3. Perfilar el tick completo y atacar el próximo 20%.
Aceptación: números antes/después; nada de micro-optimizar sin perfil.

## Log (continuación)
- L5: «armate las etapas para eso que queda mientras levanto un mundo para probar».

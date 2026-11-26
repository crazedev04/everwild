# Auditoría y diseño del sistema RNG — Etapa L

Repositorio: `~/Mimundo/mundo-vivo`
Referencia: `docs/ARQUITECTURA_OBJETIVO_MUNDO_VIVO_A1.md`

Esta etapa es exclusivamente de auditoría y diseño. No se modifica código funcional, configuraciones, documentación existente, mundos, semillas, simulaciones, bases de datos ni CCA. No se inician etapas M–P. No hay commits ni push.

## 1. Inventario completo de generadores

Se identificaron quince sitios de creación de generadores de aleatoriedad en el inventario principal. La generación de mundo añade un sitio temporal más en `generador/pipeline.py:483` (cavernas), derivado de la semilla de generación y usado solo al crear el mundo, por lo que el total de sitios de creación es dieciséis.

El inventario distingue cuatro categorías mutuamente excluyentes, clasificadas por ciclo de vida y consumo real:

* **A. Ciclo de vida propio (4):** persisten entre ticks y se reutilizan en cada decisión del subsistema.
* **B. Local/temporal con derivación por semilla (5):** creados y consumidos dentro de una operación puntual; se reconstruyen de la semilla raíz; no necesitan persistencia de estado.
* **C. RNG global sin control de semilla (4):** consumen del generador global de Python o crean `random.Random()` sin semilla derivada del mundo.
* **D. Pendiente de verificar (2):** ciclo de vida o clasificación no confirmados por el código leído.

La suma es 4 + 5 + 4 + 2 = 15 sitios principales. El generador de cavernas es el sitio 16, fuera del inventario principal.

### A. Generadores con ciclo de vida propio (4)

| # | Generador | Archivo:línea | Tipo | Semilla base | Consumidores directos |
|---|-----------|---------------|------|--------------|-----------------------|
| 1 | `Simulacion.rng` | `src/mundo_vivo/motor/simulacion.py:239` | `random.Random` | `semilla * 31 + t_min` | mente, cerebro_cognitivo, mixins (frio, materiales, psique, ecologia_fauna, objetivos, propagacion, alimentacion, vida) + `simulacion.py` (483, 484, 555, 573, 725) |
| 2 | `Fuego.rng` | `src/mundo_vivo/motor/fuego.py:54` | `np.random.default_rng` | `int(semilla) & 0x7FFFFFFF` | fuego.py (80, 147, 182) |
| 3 | `Fauna.rng` | `src/mundo_vivo/motor/fauna.py:57` | `random.Random` | `semilla * 7919 + 13` | fauna.py (119, 130, 150, 164, 165, 261, 281, 284, 295) |
| 4 | `Fenomenos.rng` | `src/mundo_vivo/motor/fenomenos.py:42` | `random.Random` | `semilla * 7919 + 13` | fenomenos.py (86, 96, 97, 100, 106, 108, 110, 111, 112, 116) |

### B. Generadores locales o temporales con derivación por semilla (5)

Estos generadores sí derivan de la semilla del mundo, pero se crean y consumen dentro de una operación puntual. No comparten estado con otros subsistemas.

| # | Generador | Archivo:línea | Tipo | Semilla base | Consumidores directos |
|---|-----------|---------------|------|--------------|-----------------------|
| 5 | `Estructuras.rng` | `src/mundo_vivo/motor/estructuras.py:103` | `random.Random` | `semilla * 2246822519 + dimension * 97 + sum(eid.encode())` | estructuras.py (103-105) |
| 6 | `Minerales.rng` | `src/mundo_vivo/motor/minerales.py:46` | `random.Random` | `semilla * PRIMO + dimension * 7919 + 101` | minerales.py (46-68) |
| 7 | `Mundo.rng` | `src/mundo_vivo/motor/mundo.py:103` | `random.Random` | `destino.semilla * 7919 + rid * 31 + dimension` | mundo.py (103) |
| 8 | `sim_io.rng` (spawn) | `src/mundo_vivo/persistencia/sim_io.py:272` | `random.Random` | `semilla * 31 + t_min` | sim_io.py (272-288) |
| 9 | `sim_io.rng` (fundadores) | `src/mundo_vivo/persistencia/sim_io.py:324` | `random.Random` | `sem * 7919 + 13` | sim_io.py (324-336) |

### C. Usos del RNG global sin control de semilla (4)

| # | Generador | Archivo:línea | Tipo | Problema |
|---|-----------|---------------|------|----------|
| 10 | `api/vivo.py` | `src/mundo_vivo/api/vivo.py:186,191` | `random` global | Sin semilla; no reproducible |
| 11 | `api/servidor.py` | `src/mundo_vivo/api/servidor.py:207,210` | `random` global | Sin semilla; no reproducible |
| 12 | `__main__.py` | `src/mundo_vivo/__main__.py:80` | `random` global | Sin semilla; no reproducible |
| 13 | `reglas.py` | `src/mundo_vivo/reglas.py:144-147` | `random.Random()` o pasada | Crea `random.Random()` sin semilla cuando no se pasa `rng` |

### D. Pendiente de verificar (2)

| # | Generador | Archivo:línea | Tipo | Motivo de pendiente |
|---|-----------|---------------|------|---------------------|
| 14 | `Fuego.parches` | `src/mundo_vivo/motor/fuego.py:48` | `np.random.default_rng` | Creado al iniciar el fuego; no se confirmó si continúa consumiéndose después de la inicialización |
| 15 | `habito.py` | `src/mundo_vivo/agentes/habito.py:33` | `random.Random(1)` | Seed fijo `1` (no derivado de la semilla del mundo); ciclo de vida no confirmado |

El generador de mundo (pipeline) usa `np.random.default_rng(s)` en `src/mundo_vivo/generador/pipeline.py:483` para cavernas, derivado de la semilla de generación y usado solo al crear el mundo. Es el sitio 16, fuera del inventario principal de quince sitios.

## 2. Mapa de consumidores por subsistema

| Subsistema | Archivo | Líneas | Generador usado |
|---|---|---|---|
| Cerebro híbrido (mente) | `agentes/mente.py` | 199, 368, 379, 821, 868, 909, 928, 929 | `sim.rng` |
| Cerebro cognitivo | `agentes/cerebro_cognitivo.py` | 1129, 1258, 1313, 1395, 1396, 1406 | `sim.rng` |
| Vida | `motor/vida.py` | 104, 147, 150, 253, 254, 264 | `sim.rng` |
| Frío | `motor/frio.py` | 135, 136 | `sim.rng` |
| Materiales / recolección | `motor/materiales.py` | 153, 156, 158 | `sim.rng` |
| Psique | `motor/psique.py` | 66, 67, 100, 101, 107 | `sim.rng` |
| Ecología / fauna-interacción | `motor/ecologia_fauna.py` | 86, 88, 90, 94 | `sim.rng` |
| Objetivos | `motor/objetivos.py` | 143 | `sim.rng` |
| Propagación (colonias) | `motor/propagacion.py` | 73, 75, 76, 87, 88 | `sim.rng` |
| Alimentación | `motor/alimentacion.py` | 104, 106 | `sim.rng` |
| Simulación (agua lejos, fuego, derrumbes) | `motor/simulacion.py` | 483, 484, 555, 573, 725 | `sim.rng` |
| Fuego | `motor/fuego.py` | 80, 147, 182 | `Fuego.rng` + `Fuego.parches` |
| Fauna | `motor/fauna.py` | 119, 130, 150, 164, 165, 261, 281, 284, 295 | `Fauna.rng` |
| Fenómenos | `motor/fenomenos.py` | 86, 96, 97, 100, 106, 108, 110, 111, 112, 116 | `Fenomenos.rng` |
| Estructuras naturales | `motor/estructuras.py` | 103-105 | `Estructuras.rng` (local) |
| Minerales desconocidos | `motor/minerales.py` | 46-68 | `Minerales.rng` (local) |
| Mundo (amenazas) | `motor/mundo.py` | 103 | `Mundo.rng` (local) |
| Spawn de habitantes (persistencia) | `persistencia/sim_io.py` | 272, 324 | `sim_io.rng` (local) |
| Generación de mundo (cavernas) | `generador/pipeline.py` | 483 | `np.random.default_rng(s)` |
| API spawn (inmigrante) | `api/vivo.py` | 186, 191 | `random` global |
| API creación de mundo | `api/servidor.py` | 207, 210 | `random` global |
| CLI | `__main__.py` | 80 | `random` global |

## 3. Semillas y fórmulas de derivación actuales

- `Simulacion.rng`: `semilla * 31 + int(t_min)` (simulacion.py:239). Depende de `t_min`, por lo que cambia al cargar un mundo en un momento distinto del reloj.
- `Fuego.rng`: `int(semilla) & 0x7FFFFFFF` (fuego.py:54).
- `Fuego.parches`: `(semilla * 2654435761) & 0x7FFFFFFF` (fuego.py:48).
- `Fauna.rng`: `semilla * 7919 + 13` (fauna.py:57).
- `Fenomenos.rng`: `semilla * 7919 + 13` (fenomenos.py:42). Misma fórmula que Fauna; dos generadores independientes con misma semilla producen secuencias idénticas pero no comparten estado.
- `Estructuras.rng`: `semilla * 2246822519 + dimension * 97 + sum(eid.encode())` (estructuras.py:103).
- `Minerales.rng`: `semilla * PRIMO + dimension * 7919 + 101` (minerales.py:46).
- `Mundo.rng`: `destino.semilla * 7919 + rid * 31 + dimension` (mundo.py:103).
- `sim_io.rng` (spawn): `semilla * 31 + t_min` (sim_io.py:272). Igual fórmula que Simulacion.rng.
- `sim_io.rng` (fundadores): `sem * 7919 + 13` (sim_io.py:324). Igual fórmula que Fauna.

## 4. Dependencias y acoplamientos detectados

1. **Acoplamiento central en `sim.rng`**: quince subsistemas comparten el mismo generador (`sim.rng` vía `self.rng` en mixins, y `sim.rng` directo en mente/cerebro_cognitivo). El consumo de uno altera la secuencia de todos los demás. No hay independencia entre subsistemas.
2. **`sim.rng` depende de `t_min`**: la semilla incluye el reloj del mundo. Al guardar y cargar en un `t_min` distinto, `sim.rng` se reinicia con una semilla distinta, rompiendo la reproducibilidad de la secuencia aleatoria tras carga.
3. **Fórmulas duplicadas**: `Fauna.rng` y `Fenomenos.rng` usan `semilla * 7919 + 13`; `Simulacion.rng` y `sim_io.rng` (spawn) usan `semilla * 31 + t_min`. Dos generadores independientes con la misma semilla pueden producir secuencias idénticas, pero no comparten estado ni se interfieren actualmente. La derivación por nombre estable de subsistema busca evitar esa colisión lógica: cada subsistema recibe su propia secuencia aunque la semilla base coincida.
4. **Sin aislamiento por dimensión**: `sim.rng` no incorpora `dimension` (salvo Estructuras y Minerales que sí lo hacen localmente). Dos dimensiones del mismo mundo comparten `sim.rng`.
5. **API y CLI usan `random` global**: `api/vivo.py`, `api/servidor.py`, `__main__.py` consumen del generador global de Python sin semilla, no reproducible y acoplado a cualquier otro uso de `random` en el proceso.
6. **`habito.py` usa semilla fija `1`**: `random.Random(1)` no deriva del mundo.
7. **`reglas.py` acepta `rng` opcional**: si no se pasa, crea `random.Random()` sin semilla.

## 5. Estado actual de persistencia y restauración

- `sim_io.py` **no guarda ni restaura el estado de ningún RNG**. No hay `getstate()`/`setstate()` en ninguna tabla ni en `estado_mundo`/`estado_dinamico`.
- Al cargar un mundo, `sim_io.py` reconstruye rng locales desde `semilla` y `t_min` (líneas 272, 324), pero no restaura el estado exacto que tenía `sim.rng` en el momento del guardado.
- Las tablas persistidas son: `habitantes`, `estado_mundo` (incluye `t_min`), `estado_dinamico` (fuego, ceniza, combustible, tormentas). Ninguna almacena estado RNG.
- Un mundo guardado y cargado en el mismo `t_min` regenera `sim.rng` con la misma semilla (`semilla * 31 + t_min`), pero la secuencia interna de `sim.rng` no es la que tenía al guardar: se reinicia desde cero. Por tanto, no es reproducible tras carga salvo que `t_min` sea 0 (mundo nuevo).

## 6. Riesgos para reproducibilidad

1. Dos mundos con la misma semilla **no producen resultados equivalentes** si se cargan en `t_min` distinto, porque `sim.rng` se reinicia con semilla distinta.
2. El consumo aleatorio de un subsistema (p. ej. mente) desplaza la secuencia de otro (p. ej. vida o materiales). No hay forma de aislar el efecto de un cambio en un subsistema sobre los demás.
3. `api/vivo.py` y `api/servidor.py` usan `random` global sin semilla: llamadas a la API introducen azar no controlado por la semilla del mundo.
4. No hay forma de reproducir una sesión concreta tras guardar/cargar: el estado de `sim.rng` se pierde.
5. Al agregar un nuevo consumidor aleatorio a un subsistema existente, se desplazan todas las secuencias posteriores de todos los subsistemas que comparten `sim.rng`.

## 7. Arquitectura objetivo recomendada

- **Una semilla raíz por mundo** (la ya existente en `meta["semilla"]`).
- **Streams independientes por subsistema**, derivados de forma determinista de la semilla raíz y un nombre estable de subsistema (p. ej. `sim`, `fuego`, `fauna`). La derivación no depende del orden de inicialización ni de `hash()` de Python: usar derivación por nombre sobre la semilla raíz (por ejemplo `sha256(f\"{raiz}:{nombre}\")` truncado a entero) o una mezcla aritmética con primos fijos asignados por nombre. Agregar un subsistema no cambia la secuencia de los existentes.
- Cada subsistema conserva su tipo de generador actual: `random.Random` para los que ya lo usan, `np.random.default_rng` para los de numpy (fuego, cavernas). No migrar todos a una misma API.
- `sim.rng` deja de ser el generador compartido: cada mixin recibe su propio generador derivado, o `sim` expone `subrng(nombre)` que devuelve un stream aislado por nombre.
- `reglas.py` recibe un generador derivado de la semilla raíz cuando se invoca sin `rng` explícito; nunca crea `random.Random()` sin semilla controlada.
- **Persistencia del estado RNG**: guardar `getstate()`/`setstate()` para `random.Random` y `bit_generator.state` para NumPy, individualmente por cada stream que continúe consumiéndose entre ticks. Candidatos a verificar: `sim.rng` y sus streams derivados por subsistema (mente, vida, frío, materiales, psique, ecología, objetivos, propagación, alimentación), `Fuego.rng`, `Fauna.rng` y `Fenomenos.rng`. `Fuego.parches` no se asume como persistente sin verificar si continúa consumiéndose después de la inicialización del fuego. Los generadores de un solo uso al generar (estructuras, minerales, mundo) y los de un solo evento (spawn, fundadores) no necesitan persistencia: se reconstruyen de la semilla raíz.
- La captura del estado RNG es coherente con el snapshot de la simulación (mismo `t_min`). No se modifica la DB ni archivos de persistencia en esta etapa.
- **Validación de persistencia**: tras guardar y cargar, cada stream persistido debe producir exactamente el mismo siguiente valor que antes del guardado, comprobado stream por stream.
- **Compatibilidad con mundos existentes**: los mundos creados antes del cambio no tienen estado RNG guardado; al cargarse se inicializan streams nuevos derivados de su semilla raíz. No se afirma continuidad histórica de la secuencia aleatoria de sesiones previas. No se modifican ni migran mundos existentes.
- **No imponer un RNG global**: cada subsistema conserva su propio stream.

## 8. Estrategia de compatibilidad con mundos existentes

- No se modifica ningún mundo, semilla, simulación, DB ni archivo de persistencia existente.
- Los mundos creados antes del cambio no tienen estado RNG guardado; al cargarse, se inicializan generadores frescos derivados de su semilla raíz. El comportamiento puede diferir de la sesión original, pero es determinista dadas las mismas condiciones.
- La tabla `estado_mundo` conserva `t_min`; ya no debe usarse para derivar la semilla de `sim.rng`. Se añade una columna opcional o tabla nueva para estado RNG solo cuando se implemente la persistencia (fuera de esta etapa).
- No se alteran fórmulas ni secuencias aleatorias actuales sin justificar el impacto en cada subsistema.

## 9. Plan de implementación en pasos verificables

Cada paso es verificable de forma independiente y no modifica comportamiento hasta que se indique.

| Paso | Acción | Verificación |
|---|---|---|
| L.1 | Inventariar y documentar (este documento). | Revisar que el inventario coincida con el código (búsqueda global de `rng`, `random.`, `np.random`, `SeedSequence`). |
| L.2 | Crear utilidad de derivación de streams a partir de la semilla raíz (función pura, sin efectos en el motor). | Test: misma semilla raíz → mismos streams derivados; streams distintos → secuencias distintas. |
| L.3 | Reemplazar `sim.rng` compartido por streams aislados por subsistema, derivados de la semilla raíz. Cada mixin recibe su propio generador. | Test: consumo en un subsistema no desplaza la secuencia de otro. |
| L.4 | Eliminar usos de `random` global en `api/vivo.py`, `api/servidor.py`, `__main__.py`; derivar de la semilla del mundo o del contexto de la petición. | Test: mismas llamadas API con misma semilla → mismos resultados. |
| L.5 | Reemplazar semilla fija `random.Random(1)` en `habito.py` y el `random.Random()` sin semilla en `reglas.py` por derivación de semilla del mundo. | Test: diferente semilla del mundo → diferente comportamiento de hábitos y reglas; ningún generador sin semilla controlada fuera del plan. |
| L.6 | Hacer opcional la persistencia de estado RNG (`getstate()`/`setstate()` para `random.Random`, `bit_generator.state` para NumPy) por cada stream que continúe entre ticks (sim y sus streams por subsistema, fuego, fauna, fenómenos); guardar en `estado_dinamico` o tabla nueva. Validar stream por stream que tras guardar y cargar cada generador produzca el mismo siguiente valor. | Test: guardar y cargar restaura la secuencia exacta de cada stream persistido, verificado individualmente. |
| L.7 | Asegurar que agregar un nuevo consumidor aleatorio a un subsistema no altere las secuencias de los demás. | Test: añadir consumo en un subsistema y verificar que los demás mantienen su secuencia esperada. |

Pasos L.2 a L.5 pueden hacerse sin cambiar fórmulas de subsistemas que ya derivan de semilla (estructuras, minerales, mundo, fuego, fauna, fenómenos), solo aislando sus streams.

## 10. Tests necesarios

| Test | Qué verifica |
|---|---|
| `test_semilla_raiz_deriva_streams_independientes` | Dos streams derivados de la misma semilla raíz son distintos y no se afectan entre sí. |
| `test_consumo_subsistema_no_desplaza_otro` | Consumir N valores en el stream de "mente" no altera la secuencia del stream de "vida" ni de "materiales". |
| `test_misma_semilla_misma_secuencia_al_cargar` | Guardar y cargar un mundo restaura el estado exacto de `sim.rng` y de los subsistemas persistibles (requiere L.6). |
| `test_api_reproducible_con_semilla` | Dos llamadas al API de spawn con la misma semilla del mundo producen el mismo inmigrante (sexo, nombre). |
| `test_no_uso_random_global_sin_semilla` | Búsqueda estática: `api/vivo.py`, `api/servidor.py`, `__main__.py` no usan `random.` global sin semilla derivada del mundo. |
| `test_habito_deriva_de_semilla_mundo` | Diferente semilla del mundo → diferente secuencia de hábitos; `random.Random(1)` eliminado. |
| `test_reglas_sin_semilla_no_controlada` | `reglas.py` nunca crea `random.Random()` sin semilla; cuando no se pasa `rng`, usa uno derivado de la semilla del mundo. |
| `test_agregar_consumidor_no_afecta_otros` | Añadir un consumo aleatorio nuevo en un subsistema no desplaza las secuencias de los demás subsistemas. |

## Archivos que requerirían cambios en la implementación (sin modificar aún)

- `src/mundo_vivo/motor/simulacion.py` (línea 239 y usos de `self.rng` / `sim.rng`)
- `src/mundo_vivo/motor/fuego.py` (líneas 48, 54)
- `src/mundo_vivo/motor/fauna.py` (línea 57)
- `src/mundo_vivo/motor/fenomenos.py` (línea 42)
- `src/mundo_vivo/motor/estructuras.py` (línea 103)
- `src/mundo_vivo/motor/minerales.py` (línea 46)
- `src/mundo_vivo/motor/mundo.py` (línea 103)
- `src/mundo_vivo/persistencia/sim_io.py` (líneas 272, 324; persistencia de estado RNG)
- `src/mundo_vivo/agentes/mente.py` (usos de `sim.rng`)
- `src/mundo_vivo/agentes/cerebro_cognitivo.py` (usos de `sim.rng`)
- `src/mundo_vivo/motor/frio.py` (líneas 135, 136)
- `src/mundo_vivo/motor/materiales.py` (líneas 153, 156, 158)
- `src/mundo_vivo/motor/psique.py` (líneas 66, 67, 100, 101, 107)
- `src/mundo_vivo/motor/ecologia_fauna.py` (líneas 86, 88, 90, 94)
- `src/mundo_vivo/motor/objetivos.py` (línea 143)
- `src/mundo_vivo/motor/propagacion.py` (líneas 73, 75, 76, 87, 88)
- `src/mundo_vivo/motor/alimentacion.py` (líneas 104, 106)
- `src/mundo_vivo/motor/vida.py` (líneas 104, 147, 150, 253, 254, 264)
- `src/mundo_vivo/api/vivo.py` (líneas 186, 191)
- `src/mundo_vivo/api/servidor.py` (líneas 207, 210)
- `src/mundo_vivo/__main__.py` (línea 80)
- `src/mundo_vivo/agentes/habito.py` (línea 33)
- `src/mundo_vivo/reglas.py` (líneas 144-147)
- `src/mundo_vivo/generador/pipeline.py` (línea 483)

## Validación de esta auditoría

- Se inspeccionaron los cinco streams identificados en A1 (sim, fuego, fauna, fenómenos, estructuras/minerales/mundo como derivados de semilla).
- El inventario incluye usos indirectos (vía `self.rng` en mixins, `sim.rng` en mente/cerebro_cognitivo).
- El diff de este cambio contiene únicamente la creación de `docs/AUDITORIA_RNG_L.md`.
- No se modificó ningún mundo, semilla, simulación, DB ni estado persistente.
- No se impuso un RNG global.
- No se cambiaron fórmulas ni secuencias aleatorias.

Etapa L concluida: auditoría y diseño listos. Esperando autorización para pasar a implementación (L.1 en adelante).

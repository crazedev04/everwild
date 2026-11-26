# Auditoría y diseño: `Terreno.costo` / `Terreno._c`

**Etapa K — Auditoría y diseño únicamente. No hay cambios de código en este documento.**

## 1. Estado actual y responsabilidades

`src/mundo_vivo/motor/navegacion.py` define la clase `Terreno`, que modela el costo de moverse por una celda del mapa: `costo = (tam_celda_m / VEL_CAMINAR_MPS) * mult_bioma * (1 + 8 * min(pendiente, PENDIENTE_MAX)^2)`, ajustado luego por ríos (vadeo/nado) y bloqueado (`inf`) para océano, lago, lava, cascada y pendiente > `PENDIENTE_MAX`.

El terreno mantiene **dos representaciones del mismo dato**:

| Atributo | Tipo | Responsabilidad | ¿Quién lo lee? |
|---|---|---|---|
| `self.costo` | `np.ndarray` (float64) | Array vectorizado de segundos por celda. Fuente de datos para operaciones numpy (máscaras, reducciones, slices). | `simulacion.py:_costo_ruta`, `simulacion.py:refugio_de_fuego`, `fauna.py`, `estructuras.py`, `mundo.py`, `navegacion.py:_factor_terreno` (en `__init__`) |
| `self._c` | `List[List[float]]` | Copia en listas de Python, con un solo objeto `float` por valor distinto (optimización de memoria: ~100 MB menos en mapa 2048²). Es la que usa el A* (`buscar_camino`) y las consultas de caminabilidad (`caminable`, `velocidad_en`, `caminable_cerca`, `componente`, `zona_conectada`). | `navegacion.py` (A*, `caminable`, `velocidad_en`, `caminable_cerca`, `componente`, `zona_conectada`) |

Ambas se escriben en exactamente dos lugares:

1. `Terreno.__init__` (líneas 111-112): calcula `costo` como array numpy, luego `self._c = _listas_compartiendo_floats(costo)`.
2. `Terreno.cambiar_bioma` (líneas 153-154): actualiza una celda en `self.costo[y, x]` y en `self._c[y][x]`, luego llama a `olvidar_fracasos()` y `olvidar_rutas()`.

### Invariante documentada

El docstring de `cambiar_bioma` (líneas 136-156) y el CLAUDE.md ("Trampas ya vistas") dejan claro el contrato:

> "Existe por un detalle que no se ve: `self.costo` es el array y `self._c` es una COPIA en listas de Python, que es la que usa el A*. Escribir sólo una de las dos deja al A* caminando el mapa viejo para siempre."

## 2. Mapa de lectores y escritores

### Escritores (arquivo, método, línea)

| Archivo | Método | Línea | Qué escribe |
|---|---|---|---|
| `src/mundo_vivo/motor/navegacion.py` | `Terreno.__init__` | 111-112 | `self.costo` (array completo) y `self._c` (copia completa) |
| `src/mundo_vivo/motor/navegacion.py` | `Terreno.cambiar_bioma` | 153-154 | `self.costo[y, x]` y `self._c[y][x]` (una celda) |
| `src/mundo_vivo/motor/senderos.py` | `SenderosMixin._abrir_sendero` | 109 | Llama a `self.terreno.cambiar_bioma(x, y, self.bioma_sendero)` → escribe ambos |
| `src/mundo_vivo/motor/senderos.py` | `SenderosMixin._cerrar_sendero` | 118 | Llama a `self.terreno.cambiar_bioma(x, y, antes)` → escribe ambos |
| `src/mundo_vivo/motor/senderos.py` | `SenderosMixin.importar_desgaste` | 174 | Llama a `self.terreno.cambiar_bioma(x, y, self.bioma_sendero)` → escribe ambos |

No hay ningún otro escritor de `costo` ni de `_c` en el códigobase. Ningún tick del bucle de 20 Hz toca el costo celda por celda (ver `senderos.py`, líneas 12-13).

### Lectores (arquivo, método, línea)

| Archivo | Método | Línea | Qué lee |
|---|---|---|---|
| `src/mundo_vivo/motor/navegacion.py` | `Terreno.caminable` | 162 | `self._c[y][x] != INF` |
| `src/mundo_vivo/motor/navegacion.py` | `Terreno.velocidad_en` | 165 | `self._c[...][...]` |
| `src/mundo_vivo/motor/navegacion.py` | `Terreno.caminable_cerca` | 186, 196, 202 | `c[y][x] != INF` (donde `c = self._c`) |
| `src/mundo_vivo/motor/navegacion.py` | `Terreno.componente` | 217, 226 | `c[ny][nx] != INF` (donde `c = self._c`) |
| `src/mundo_vivo/motor/navegacion.py` | `Terreno.zona_conectada` | 241, 250 | `c[ny][nx] != INF` (donde `c = self._c`) |
| `src/mundo_vivo/motor/navegacion.py` | `Terreno.buscar_camino` | 312, 329, 372, 380, 384 | `c[y][x]` en todo el A* (donde `c = self._c`) |
| `src/mundo_vivo/motor/navegacion.py` | `Terreno.__init__` | 113-118 | `self.costo` para calcular `_factor_terreno` |
| `src/mundo_vivo/motor/simulacion.py` | `Simulacion._costo_ruta` | 476 | `t.costo[cy, cx]` (array numpy, suma por celda de ruta) |
| `src/mundo_vivo/motor/simulacion.py` | `Simulacion.buscar_agua_cerca` | 451 | `self._costo_ruta(ruta)` → lee `costo` |
| `src/mundo_vivo/motor/simulacion.py` | `Simulacion.refugio_de_fuego` | 501 | `np.isfinite(self.terreno.costo[ys0:ys1, xs0:xs1])` |
| `src/mundo_vivo/motor/fauna.py` | (módulo) | 78 | `np.isfinite(t.costo) & (t.agua == 0)` |
| `src/mundo_vivo/motor/estructuras.py` | (módulo) | 96 | `np.isfinite(self.terreno.costo)` |
| `src/mundo_vivo/motor/mundo.py` | (módulo) | 104 | `np.argwhere(np.isfinite(destino.terreno.costo))` |

**Resumen:** `_c` es leído exclusivamente por el sistema de navegación (A* y caminabilidad). `costo` es leído por navegación (solo en `__init__` para `_factor_terreno`), simulación (costo de ruta, refugio de fuego), fauna, estructuras y mundo (máscaras numpy).

## 3. Flujo de actualización y puntos de desincronización

### Flujo normal de actualización

1. **Generación del mundo:** `Simulacion.__init__` crea `Terreno(capas, tam_celda_m)`. `__init__` calcula `costo` (array numpy) y `_c` (lista compartida) de un saque, nunca celda por celda.
2. **Desgaste del suelo (senderos):** `pisar()` acumula en diccionario disperso `_pisadas`. Cada `VUELCA_CADA_MIN` minutos, `_volcar_pisadas()` llama a `_abrir_sendero()` o `_cerrar_sendero()`, que invocan `terreno.cambiar_bioma(x, y, bioma)`. `cambiar_bioma` escribe en `costo` y `_c`, e invalida cachés de rutas y fracasos.
3. **Carga de mundo persistido:** `importar_desgaste()` reconstruye senderos desde el array `desgaste` (uint8, guardado por `mundo_io`). Llama a `cambiar_bioma` para cada celda que cruzó el umbral, escribiendo en `costo` y `_c`.

### Puntos de desincronización

| Punto | Descripción | Gravedad |
|---|---|---|
| Escritura parcial | Cualquier código que escriba `self.costo[y, x] = c` sin `self._c[y][x] = c` (o viceversa) deja al A* viendo el mapa viejo. | **Alta** — fallo silencioso, caminos incorrectos |
| Persistencia | `cambiar_bioma` no escribe al disco ni a la UI. La capa de biomas queda congelada en la generación. Los senderos se reconstruyen al cargar desde `desgaste`, no desde la capa de biomas. | **Media** — los senderos pintados no sobreviven una recarga sin reconstrucción desde desgaste |
| Caché de rutas | `cambiar_bioma` llama a `olvidar_rutas()` y `olvidar_fracasos()`. Si se omite, rutas cacheadas son inválidas. | **Media** — ya manejado por `cambiar_bioma`, pero frágil si alguien escribe directo |
| `_factor_terreno` | Se calcula en `__init__` desde `costo / mult`. Si `costo` cambia sin recalcular `_factor_terreno`, la descomposición "costo del terreno vs costo del bioma" se rompe. | **Baja** — solo se usa en `cambiar_bioma` para el cálculo de `c` |

## 4. Dependencias de navegación, generación y persistencia

### Navegación

El A* (`buscar_camino`) usa `self._c` exclusivamente. La heurística y el costo de transición leen de `c`. `caminable()` lee `_c`. Todo el pathfinding del motor (agua, refugio, huida, exploración) depende de que `_c` esté sincronizado con `costo`.

### Generación

`Terreno.__init__` recibe `capas` (elevación, agua, bioma, humedad, temperatura, caudal, rasgos) y calcula:
- `pendiente` desde `np.gradient(elevacion)`
- `mult` desde la tabla de velocidad de biomas
- `costo` = distancia / velocidad × mult × factor de pendiente
- Ajuste por río (caudal > 200 → ×8, else ×3)
- Bloqueo (inf) para agua profunda, lava, cascada, pendiente > max

Todo esto es determinista dado la semilla y las capas de generación.

### Persistencia

- `costo` y `_c` **no se guardan** en disco. Se recalculan al crear el mundo.
- Los cambios de bioma (senderos) sobreviven a la recarga solo indirectamente: `desgaste` (uint8 array, comprimido con zlib) se guarda por `mundo_io.guardar_capas`, y al cargar `importar_desgaste()` reconstruye los senderos llamando a `cambiar_bioma`.
- **Brecha conocida** (documentada en `senderos.py:159-164`): `mundo_io.guardar_capas` corre una sola vez al crear el mundo/dimensión. La capa de biomas queda congelada. `cambiar_bioma` no llega al disco ni a la UI. Medido: 33 celdas pintadas como sendero, 0 después de recargar, 0 en la capa que sirve la API. Los senderos no se veían ni se guardaban hasta que `importar_desgaste` los reconstruye desde `desgaste`.

## 5. Evaluación de impacto y riesgos

### Riesgo alto: desincronización silenciosa `costo` vs `_c`

Si algún código futuro escribe en `costo` sin escribir en `_c` (o viceversa), el A* seguirá viendo el mapa viejo para siempre hasta que se invalide por otro cambio. Es un fallo silencioso: los tests pueden pasar porque verifican una representación, mientras la otra está desactualizada. El docstring de `cambiar_bioma` y CLAUDE.md ya advierten de esto, pero no hay protección en código (no hay setter, no hay propiedad, no hay aserción de consistencia).

### Riesgo medio: rendimiento de doble representación

Mantener dos copias del costo (array numpy de 33.6 MB + lista de Python con ~33.6 MB de punteros en 2048²) duplica la memoria. `_listas_compartiendo_floats` mitiga esto compartiendo objetos float por valor distinto (3.809 valores únicos en 4.2M celdas), pero sigue habiendo dos estructuras en memoria. Cada `cambiar_bioma` toca ambas.

### Riesgo medio: persistencia incompleta de senderos

Los senderos no se guardan directamente; se reconstruyen desde `desgaste` al cargar. Si `desgaste` está corrupto o falta, los senderos se pierden. La capa de biomas en disco nunca refleja `cambiar_bioma`.

### Riesgo bajo: `_factor_terreno` desactualizado

Solo se calcula en `__init__`. Si `costo` cambiara masivamente sin recalcularlo, la descomposición terreno-vs-bioma se rompería. Actualmente solo `cambiar_bioma` modifica `costo` celda a celda y usa `_factor_terreno` para el nuevo valor, así que no hay desactualización en la práctica.

## 6. Arquitectura recomendada

### Opción A: Unificar en una sola fuente de verdad (recomendada a largo plazo)

Eliminar `_c` y hacer que el A* lea directamente de `costo` (array numpy). El problema de rendimiento (indexar numpy es más lento que lista de Python) se mitiga con:
- Convertir `costo` a listas una sola vez y cachear, o
- Usar numpy vectorizado donde sea posible, o
- Mantener `_c` como una vista derivada de `costo` (propiedad que construye la lista bajo demanda y la cachea).

Ventaja: un único punto de escritura, imposible la desincronización.
Desventaja: posible regresión de rendimiento en el A* si no se optimiza el acceso.

### Opción B: Mantener dualidad con protección (mínimo cambio)

Mantener `costo` y `_c` pero:
- Encapsular la escritura en un único método `Terreno.establecer_costo(x, y, valor)` que escriba en ambas representaciones y invalide cachés.
- Hacer `costo` y `_c` privados (`_costo`, `_c`) con acceso solo a través de métodos.
- Añadir una aserción de consistencia opcional (modo debug) que verifique `costo[y][x] == _c[y][x]` en muestreo aleatorio.

Ventaja: bajo impacto, corrige el punto frágil actual.
Desventaja: sigue habiendo dos copias en memoria.

### Recomendación

Para la etapa K (diseño), se recomienda **Opción B como paso intermedio** (protección inmediata contra desincronización) y **Opción A como objetivo a mediano plazo** (unificación), perfilando el A* antes y después para confirmar que no hay regresión de rendimiento en mapas 2048².

## 7. Plan de implementación en pasos verificables

Cada paso es verificable de forma independiente y no afecta a los demás.

| Paso | Acción | Verificación |
|---|---|---|
| K.1 | Añadir método `Terreno.establecer_costo(x, y, valor)` que escriba en `costo` y `_c` e invalide cachés. Refactorizar `cambiar_bioma` para usarlo. | Test: `costo[y][x] == _c[y][x]` después de `cambiar_bioma`. |
| K.2 | Añadir aserción de consistencia opcional (variable de entorno o flag debug) que verifique `costo` vs `_c` en muestreo aleatorio tras cada `cambiar_bioma`. | Test: la aserción pasa en mundo con senderos activos. |
| K.3 | Auditar que ningún código fuera de `navegacion.py` escriba directamente en `costo` o `_c`. | Búsqueda global de `costo[` y `_c[` fuera de `navegacion.py`. Cero hallazgos. |
| K.4 | Documentar en CLAUDE.md y docstring de `Terreno` la regla de "siempre escribir en ambas" y el método autorizado. | Docstring y CLAUDE.md actualizados. |
| K.5 (opcional, mediano plazo) | Evaluar unificación (Opción A): perfil del A* con `costo` directo vs `_c`. Si no hay regresión, eliminar `_c`. | Benchmark A* en mapa 2048² antes y después. |

## 8. Tests necesarios

### Test existente (ya pasa)

- `tests/test_senderos.py::test_el_costo_cambia_en_LAS_DOS_representaciones` — verifica que `costo[y][x] == _c[y][x]` tras abrir un sendero, y que el costo es menor que el base.
- `tests/test_senderos.py::test_sin_transito_el_sendero_se_cierra` — verifica sincronía tras cerrar sendero.

### Tests nuevos recomendados

| Test | Qué verifica |
|---|---|
| `test_costo_y_c_sincronizados_despues_de_cambiar_bioma` | Tras llamar `cambiar_bioma(x, y, bioma)`, `terreno.costo[y][x] == terreno._c[y][x]` y `terreno.caminable(x, y)` usa `_c`. |
| test_el_a_star_usa_c_y_no_costo | Modificar `costo` directamente (sin `_c`) y verificar que el A* sigue usando el valor viejo de `_c` (demuestra la desincronización si no se protege). Con la protección de K.1, este test debería fallar si alguien escribe directo en `costo`. |
| test_cambiar_bioma_invalida_rutas_cacheadas | Tras calcular una ruta, cambiar el bioma de una celda intermedia, y verificar que la ruta cacheada se olvida (`buscar_camino` recalcula). |
| test_importar_desgaste_reconstruye_senderos | Cargar `desgaste` con celdas >= `PISADAS_SENDERO`, verificar que `cambiar_bioma` fue llamado y `costo`/`_c` están sincronizados. |
| test_ningun_codigo_escribe_directo_en_costo_fuera_de_navegacion | Búsqueda estática (test de metadatos o grep en test) que falle si hay `costo[` o `_c[` fuera de `navegacion.py`. |

### Alcance de los tests

- Todos en `tests/test_senderos.py` o un nuevo `tests/test_terreno_costo.py`.
- Usar el helper `_mundo()` de `tests/test_calor.py` para crear mundos de prueba.
- Ningún test toca mundos, semillas, simulaciones persistentes ni DBs (cumple restricción de etapa K).
- Ningún test modifica `CCA`.

---

**Restricciones de etapa K (verificadas):**
- ✅ Sin cambios a mundos, semillas, simulaciones, DBs ni archivos de persistencia.
- ✅ Sin tocar CCA.
- ✅ Sin iniciar L–P.
- ✅ Sin commits ni push.
- ✅ Cambios preexistentes preservados.
- ✅ No se eliminan atributos por suposición de obsolescencia.

# Auditoría técnica: generación procedural, accesibilidad del agua y navegación

> Auditoría de solo lectura. No se modificó código, configuraciones, bases de datos ni mundos.
> El único artefacto nuevo es este informe. Fecha: 2026-11-26.
> Alcance: por qué los habitantes detectan agua, eligen `satisfy_sed`, ejecutan `ir_al_agua`
> y aun así mueren de sed sin llegar.

---

## 1. Resumen ejecutivo

El síntoma (habitantes que repiten `ir_al_agua` con `ok=1` o con `SED-SIN-CAMINO` y mueren de sed
a pocas celdas de un río) **no tiene una sola causa**. La auditoría confirmó **tres defectos
estructurales** que se combinan, más un problema de semántica de feedback:

1. **Detección y enrutado usan presupuestos de búsqueda distintos y la detección es más
   permisiva que el enrutado.** `agua_cercana` (BFS) explora hasta `nodos_bfs` y devuelve una
   celda de orilla alcanzable; `buscar_camino` (A*) sólo explora `nodos_camino`, que es **4 veces
   menor**. Hay rutas que la detección "ve" pero que el A* no alcanza a cerrar antes de agotar su
   presupuesto. Eso produce el `SED-SIN-CAMINO`: detección exitosa + enrutado fallido.
   (`src/mundo_vivo/motor/simulacion.py:355-357`, `:403-432`, `:757-771`.)

2. **El fracaso de enrutado se cachea como "imposible" y no se reintenta.** Un `buscar_camino`
   que agota su presupuesto de nodos se anota en la caché negativa `_fracasos` y se devuelve
   `None` para siempre (hasta que el mapa cambie), aunque la BFS siga devolviendo ese mismo
   destino. El habitante queda clavado en un destino que "existe" para la detección y "no existe"
   para el enrutado. (Confirmado por el propio test `test_motor.py:50-79`.)
   (`src/mundo_vivo/motor/navegacion.py:315-317`, `:358-359`, `:389-394`.)

3. **El radio de detección (3–7 km) supera ampliamente lo que se puede recorrer antes de morir.**
   A 5 m/celda, `r_agua_cerca = 600` celdas y `r_agua_lejos = 1400` celdas. Cruzar 3–7 km de
   terreno con biomas y pendientes que multiplican el costo (hasta ×201 en pendiente máxima)
   puede llevar horas; la sed a 100 mata en ~5,5 h. El agua "detectada" puede ser inalcanzable
   **en tiempo**, no sólo en espacio. (`simulacion.py:352-353`, `:627-630`, `:643-644`;
   `navegacion.py:89-93`.)

4. **`ok=1` significa "el A* devolvió una ruta y empezó a caminar", NO "llegó" ni "bebió".**
   El registro cognitivo (`decisiones.ok`) copia ese `ok` del motor, así que un habitante puede
   acumular muchos `ok=1` de `ir_al_agua` sin haber bebido nunca. El feedback es engañoso para
   cualquiera que lea la tabla `decisiones`. (`cerebro_cognitivo.py:1454-1481`;
   `simulacion.py:753-771`.)

Además, **el generador no valida accesibilidad del agua**: sólo se valida que el punto de inicio
esté en una componente transitable de ≥3000 celdas, no que haya orilla alcanzable ni que las zonas
habitables tengan agua a distancia recorrible. (`persistencia/sim_io.py:68-102`;
`generador/pipeline.py` no contiene validación de transitabilidad — ver §5.)

El bug previo de sed (bloqueo de precondiciones en el puente cognitivo) ya está corregido y
documentado en `docs/MUERTE_POR_SED.md`; lo que queda abierto ahí ("la BFS falla a 28 celdas",
"no hay test de supervivencia") es la continuación directa de esta auditoría.

**Qué corregir primero (ver §10–§12):** unificar detección y enrutado bajo un mismo presupuesto y
una misma noción de "alcanzable" (defecto 1+2), y acotar el radio de detección a lo recorrible
antes de morir (defecto 3). El feedback (4) y la validación de mundos (5) son necesarios pero
secundarios.

---

## 2. Arquitectura actual (generador, navegación, necesidades)

### 2.1 Generación procedural
- `src/mundo_vivo/generador/pipeline.py` genera el mapa por etapas deterministas
  (`VERSION_GENERADOR = "1.1.0"`): relieve → clima → hidrología/erosión → biomas/capas.
- Hidrología (`etapa_hidrologia_y_erosion`, `:353-379`): red de drenaje por "priority-flood",
  lagos en depresiones (`_seleccionar_lagos`), ríos por umbral de acumulación, cascadas por salto
  de elevación.
- Capas finales (`etapa_biomas_y_capas`, `:382-421`): `agua` (0 ninguna, 1 océano, 2 lago,
  3 río), `caudal`, `rasgos` (cascada/lava), `bioma`, `elevacion`, etc.
- El generador de **cavernas** (`:480-528`) sí restringe el agua a huecos alcanzables
  (`agua[alcanzable & (elev <= corte)] = AGUA_LAGO`), pero el mundo de superficie **no** tiene
  esa restricción.

### 2.2 Terreno y transitabilidad
- `src/mundo_vivo/motor/navegacion.py` construye `Terreno` a partir de las capas.
- Costo por celda (`:89-93`): `(tam/VEL) * mult_bioma * (1 + 8*min(pendiente,5)^2)`; los ríos se
  multiplican ×3 o ×8 (`:94-97`).
- **Intransitables (INF)** (`:98-105`): océano, lago, lava, cascada y `pendiente > PENDIENTE_MAX`
  (5.0). Los ríos **sí** se caminan (se vadear/nadan).
- `caminable(x,y)` = celda dentro y con costo finito (`:155-156`).
- `mult_bioma` sale de `datos_base/biomas/biomas.json` (velocidad `null` = intransitable).
  Valores: océano/lago `null`; `sendero_tierra` 0.75; el resto ≥1.0. **Un único bioma (sendero)
  tiene multiplicador <1**, lo que vuelve la heurística del A* levemente inadmisible en su
  presencia (ver §3, hipótesis H6).

### 2.3 Necesidades (sed)
- La sed la lleva el motor, no el cerebro: `simulacion.py:627-630` (+0,11/min despierto,
  +0,07/min dormido), `>90` resta salud (`:643-644`), muerte por sed si `sed>=90` (`:674`).
- `SED_DESPIERTA = 80` (`simulacion.py:46`): umbral que despierta y que el cerebro usa para
  priorizar. `UMBRAL_SED = 55` (`cerebro_cognitivo.py:56`): umbral de urgencia del árbitro.
- El puente cognitivo traduce la necesidad sed a `satisfy_sed` y fuerza replanificación cuando
  `sed>=UMBRAL_SED` y el objetivo vigente no es `satisfy_sed` (`cerebro_cognitivo.py:1140-1145`).

### 2.4 Cerebros
- `CerebroDemo` (reglas) y `CerebroHibrido` (`agentes/mente.py`) y `CerebroCognitivo`
  (`agentes/cerebro_cognitivo.py`, puente a Cognitive Engine). El motor **valida**, el cerebro
  **propone**. La ejecución real de cualquier `ir` pasa por `Simulacion._aplicar`.

---

## 3. Flujo completo de detección → búsqueda → desplazamiento → consumo

1. **Necesidad**: `h.sed` sube; a `>=UMBRAL_SED` el árbitro elige `satisfy_sed`.
2. **Capacidad**: `ir_al_agua` (registrada en `cerebro_cognitivo.py:269`,
   precondición `AGUA_CONOCIDA`, efecto `AGUA_AL_LADO`).
3. **Traducción**: `_t_ir_al_agua` (`:1206-1208`) llama `_agua_alcanzable` (`:809-814`):
   - si `agua_adyacente(pos)` → devuelve la posición actual;
   - si no, `agua_cercana(h, r_agua_cerca) or agua_cercana(h, r_agua_lejos)`.
   Devuelve `{"tipo":"ir","destino":dest,"luego":"beber"}`.
4. **Detección (`agua_cercana`, `simulacion.py:403-432`)**: BFS en 8 direcciones desde la celda
   del habitante, con la **misma regla de no cortar esquinas que el A*** (`:424`), limitada por
   `radio` (celdas) y por `nodos_bfs`. Devuelve la **primera celda transitable adyacente a agua**
   (`agua_adyacente`). Si no encuentra, imprime `AGUA-CERCANA-NONE` y devuelve `None`.
5. **Enrutado (`_aplicar` tipo `ir`, `simulacion.py:753-771`)**: `buscar_camino(origen,dest,
   nodos_camino)`:
   - `camino == []` (ya está en el destino) → si `luego=="beber"` → beber; si no, "ya está ahí".
   - `camino` no vacío → `h.camino=camino`, `accion="caminando"`, `al_llegar="beber"`,
     texto de éxito (`"Fuiste hacia <motivo>."`), `ok=True`.
   - `camino is None` → `accion="esperando"`, `ok=False`, `"No encontraste camino."`, e imprime
     `SED-SIN-CAMINO` si `sed>=55`.
6. **Movimiento (`_mover`, `:720-744`)**: avanza a `velocidad_en(x,y)` (m/s→celdas), consume
   `h.camino`; al vaciarlo `accion="libre"`.
7. **Consumo**: al tick siguiente, si `al_llegar=="beber"` (`:703-706`) → `_aplicar({"tipo":"beber"})`.
8. **Beber (`:799-812`)**: si `agua_adyacente(pos)` → `sed -= 60`, `accion="bebiendo"`; si no →
   `ok=False`, "Aquí no hay agua."
9. **Feedback**: `registrar_resultado` (`cerebro_cognitivo.py:1401-1432`) entrega el resultado al
   cerebro y anota en `decisiones` con `ok = 1 if ok else 0` (`:1477`).

**A* (`buscar_camino`, `navegacion.py:287-394`)**: heurística octile; si el destino no es
`caminable` → `None` inmediato (`:305`); caché de éxitos (LRU) y **caché negativa de fracasos**
(`:315-317`); presupuesto `max_exp` (`:358-359`); al fallar anota el fracaso (`:389-394`).

---

## 4. Archivos, clases y funciones implicados

| Archivo | Símbolo | Rol |
|---|---|---|
| `motor/simulacion.py` | `agua_cercana` `:403-432` | Detección BFS de orilla alcanzable |
| `motor/simulacion.py` | `buscar_agua_lejos` `:434-443` | Búsqueda exploratoria lejos |
| `motor/simulacion.py` | `_calcular_escala` `:331-357` | Radios y presupuestos (`r_agua_*`, `nodos_*`) |
| `motor/simulacion.py` | `_aplicar` (tipo `ir`/`beber`) `:746-839` | Ejecución, `SED-SIN-CAMINO` `:771` |
| `motor/simulacion.py` | `_mover` `:720-744`, sed `:627-644` | Desplazamiento y sed |
| `motor/navegacion.py` | `Terreno.buscar_camino` `:287-394` | A* + caché negativa |
| `motor/navegacion.py` | `Terreno.caminable/agua_adyacente` `:155-203` | Transitabilidad y adyacencia |
| `motor/navegacion.py` | costos `:89-107`, `velocidad_en` `:158-168` | Costo/velocidad por celda |
| `agentes/cerebro_cognitivo.py` | `_agua_alcanzable` `:809-814`, `_t_ir_al_agua` `:1206-1208` | Traducción de la capacidad |
| `agentes/cerebro_cognitivo.py` | `_necesidades` `:407-478`, `registrar_resultado`/`_anotar_decision` `:1401-1481` | Necesidades y feedback |
| `persistencia/sim_io.py` | `elegir_inicio` `:68-102`, `_puntos_de_partida` `:138-169` | Spawn y validación de inicio |
| `generador/pipeline.py` | `etapa_hidrologia_y_erosion` `:353-379`, `etapa_biomas_y_capas` `:382-421` | Generación de agua |
| `datos_base/biomas/biomas.json` | `velocidad` | Transitabilidad por bioma |

---

## 5. Causas confirmadas (con evidencia)

### C1 — Presupuesto de detección ≠ presupuesto de enrutado (CONFIRMADA)
`agua_cercana` usa `nodos_bfs`; `buscar_camino` usa `nodos_camino`. En `_calcular_escala`
(`simulacion.py:355-357`):
```
k = (50/tam)^2
nodos_bfs    = min(300_000, 30_000*k)
nodos_camino = min(120_000, 12_000*k)
```
A 50 m/celda: `nodos_bfs=30.000`, `nodos_camino=12.000`. A 5 m/celda: `300.000` vs `120.000`.
**El enrutado siempre dispone de 4× menos expansiones que la detección.** Como la BFS devuelve
una celda alcanzable con hasta `nodos_bfs` expansiones y el A* (heurística admisible en terreno
normal) necesita un número comparable o mayor para cerrar rutas largas con desvíos, hay destinos
que la detección "ve" y el A* no logra enrutar antes de agotar `nodos_camino`. Resultado:
`agua_cercana` devuelve `dest` (no es `None`) y `buscar_camino` devuelve `None` → `SED-SIN-CAMINO`
(`simulacion.py:769-771`). La ruta existe (la BFS la recorrió con las mismas reglas), pero el A* no
la encuentra dentro de su presupuesto.

### C2 — El fracaso de enrutado se cachea y nunca se reintenta (CONFIRMADA)
`buscar_camino` anota el fracaso por `(origen//4, destino_exacto)` y lo devuelve sin rebuscar
(`navegacion.py:315-317`, `_anotar_fracaso` `:389-394`). El propio proyecto lo documenta y lo
testea: `test_motor.py:50-79` verifica que un destino fallido "con presupuesto de sobra NO se
busca de nuevo". Consecuencia: si un `buscar_camino` agota `nodos_camino` para un destino que
**sí** es alcanzable (C1), ese destino queda marcado como imposible. Como el habitante no se mueve,
su origen no cambia y `agua_cercana` (determinista) sigue devolviendo el **mismo** destino, que el
A* resuelve al instante desde la caché negativa con `None`. **Bloqueo permanente** hasta que
`cambiar_bioma` vacíe `_fracasos` (el desgaste de senderos lo hace, pero no es fiable ni
inmediato). Esto explica que la posición "permanezca igual mientras los destinos cambian": para un
mismo habitante el destino es fijo; lo que cambia es qué habitante logra el `SED-SIN-CAMINO`.

### C3 — Radio de detección mayor que el alcance recorrible antes de morir (CONFIRMADA)
`r_agua_cerca = celdas(3000 m)`, `r_agua_lejos = celdas(7000 m)` (`simulacion.py:352-353`). A
5 m/celda son 600 y 1400 celdas. El costo por celda crece con el bioma (×0,75–2,5) y con la
pendiente (`1+8*min(pend,5)^2`, hasta ×201) (`navegacion.py:89-93`); `velocidad_en` topa en
4× el costo base (`:166-168`). Un recorrido de 3–7 km por terreno accidentado puede tomar horas.
La sed a 100 resta 0,3 de salud/min → muerte en ~5,5 h (`simulacion.py:643-644`). Por tanto, agua
**detectada** a 3–7 km puede ser **inalcanzable en tiempo** aunque exista la ruta. La detección
promete más de lo que el cuerpo puede cumplir.

### C4 — `ok=1` no significa "llegó ni bebió" (CONFIRMADA)
`_anotar_decision` escribe `ok = 1 if ok else 0` copiando el `ok` de `_aplicar`
(`cerebro_cognitivo.py:1477`). En la rama `ir` con ruta, `ok=True` se fija al **iniciar** la
marcha (`simulacion.py:763-765`), no al llegar ni al beber. Por eso la tabla `decisiones` muestra
`"Fuiste hacia satisfy_sed." ok=1` repetido: cada entrada es "ruta encontrada y marcha iniciada",
no "agua bebida". Es un defecto de **semántica de feedback**, no de la ejecución en sí.

### C5 — El generador no valida accesibilidad del agua (CONFIRMADA)
`elegir_inicio` (`sim_io.py:68-102`) exige: celda caminable, llana, a ≤3 celdas de agua dulce y en
una componente transitable ≥ `MIN_ZONA_CONECTADA=3000` (`:100`). **No** verifica que exista una
ruta a una celda de orilla, ni que la orilla esté en la misma componente. Además, si ninguna de
los 40 candidatos cumple el umbral, cae en `return cand[0]` (`:102`), que puede ser una componente
pequeña. Los grupos de habitantes se reparten dentro de la componente del inicio
(`_puntos_de_partida`, `:138-169`), así que todos arrancan conectados entre sí, pero **nada
garantiza** que esa componente tenga agua a distancia recorrible. `pipeline.py` no contiene
ninguna validación de transitabilidad/accesibilidad (búsqueda de `validar|conect|transitab|
orilla|accesib` en `generador/` sólo coincide con un comentario de cavernas, `:480`).

### C6 — Diagnóstico sin canal formal (CONFIRMADA, menor)
`SED-SIN-CAMINO` y `AGUA-CERCANA-NONE` son `print(... file=sys.stderr)` crudos
(`simulacion.py:429-432`, `:770-771`), no eventos del motor ni del `diagnostico.py`. No quedan en
la base, no se pueden filtrar por habitante/mundo y se pierden al redirigir stderr. Por eso el
diagnóstico es "ruido" y no evidencia persistente.

---

## 6. Hipótesis NO verificadas (requieren datos del mundo, que esta auditoría no toca)

- **H1 (mecanismo exacto del `ok=1` sin avance de Emil).** Para el cerebro cognitivo, llegar a una
  celda de orilla siempre permite beber (`agua_cercana` garantiza `agua_adyacente`), así que 39
  `ok=1` sin beber implica que **no llega**: o el destino se recalcula a otra celda antes de llegar
  (oscilación), o el viaje dura más que su margen de supervivencia (C3). Confirmar con la traza
  `x,y` por tick de Emil en su mundo.
- **H2 (agua geométricamente cercana pero aislada).** El usuario vio muertos a 3–4 celdas de un
  río. Hipótesis: esa agua es lago/océano (intransitable, sin orilla) o está tras un acantilado
  (`pendiente>5`) o cascada; la orilla alcanzable por BFS queda a 32–70 celdas (coincide con los
  destinos de `SED-SIN-CAMINO`). Confirmar celda por celda sobre el mapa del mundo.
- **H3 (componentes habitables aisladas sin agua).** Posible según C5, no medido. Confirmar
  calculando, por componente transitable, la distancia mínima a una orilla alcanzable.
- **H4 (fracasos cacheados en el mundo real).** Cuántos `SED-SIN-CAMINO` provienen de caché
  negativa vs. agotamiento de presupuesto la primera vez. Confirmar instrumentando (no tocando la
  base) o con un mundo de prueba.
- **H5 (el 3–7 km no recorrible domina sobre el bloqueo por presupuesto).** Confirmar midiendo la
  distribución de distancias de `agua_cercana` y el tiempo de marcha por bioma/pendiente.
- **H6 (heurística inadmisible por `sendero_tierra` 0,75).** Costo de celda < base ⇒ heurística
  octile sobreestima ⇒ A* subóptimo/incompleto con presupuesto. Impacto real probablemente bajo
  (los senderos son pocos), no medido.

---

## 7. Diferencia entre detección geométrica y accesibilidad real

- **Adyacencia geométrica** (`agua_adyacente`, `navegacion.py:200-203`): celda vecina a **cualquier**
  `agua>0` (océano, lago o río). No distingue agua bebible de agua intransitable. Beber sólo
  comprueba esto (`simulacion.py:800`), así que estar junto a un lago/océano **sí** permite beber.
- **Accesibilidad real** (`agua_cercana`): exige una celda **transitable** adyacente a agua,
  alcanzada por BFS desde la posición. Es la noción correcta, pero con techo de `nodos_bfs`.
- **Enrutabilidad** (`buscar_camino`): exige cerrar la ruta con `nodos_camino` y sin cortar
  esquinas. Es la noción más estricta y la que decide si el habitante se mueve.
- **La brecha**: "cerca en línea recta" ≠ "adyacente" ≠ "alcanzable por BFS" ≠ "enrutable por A*
  dentro de presupuesto" ≠ "recorrible antes de morir". El habitante muere en el eslabón
  "enrutable/recorrible": ve agua cerca (geométrica), la BFS la ve lejos (alcanzable), el A* no la
  cierra (C1) o la cachea como imposible (C2), y aunque la cerrara, el viaje excede su tiempo (C3).

---

## 8. Problemas en el feedback de acciones

- **`ok=1` ambiguo** (C4): mezcla "acción aceptada", "ruta encontrada" y "marcha iniciada". No
  distingue "llegó" ni "bebió". La tabla `decisiones` es el "pensamiento" que ve el visor
  (`cerebro_cognitivo.py:1437`), así que el observador percibe éxito donde no lo hay.
- **Sin señal de "llegué pero no había agua"**: si al llegar la celda no fuera adyacente (no
  ocurre con `agua_cercana`, pero sí con `ir_hacia`/`buscar`), el texto sería "Aquí no hay agua"
  con `ok=0`; el caso `ir_al_agua` lo evita por construcción, lo que refuerza que el problema es
  "no llega", no "llega y no bebe".
- **Diagnósticos volátiles** (C6): `SED-SIN-CAMINO`/`AGUA-CERCANA-NONE` no son eventos
  persistidos; no hay forma de auditar a posteriori sin stderr.
- **El habitante no "sabe" que falló**: `registrar_resultado` entrega el `ok` al cerebro, pero la
  replanificación de sed es automática (`:1140-1145`), así que el ciclo se repite idéntico.

---

## 9. Pruebas existentes y pruebas faltantes

### Existentes
- `tests/test_fauna.py:856-875` `test_agua_cercana_siempre_devuelve_un_lugar_al_que_se_llega`:
  el test más cercano al bug (docstring: "Celia murió de sed a 3 celdas de agua aislada por
  acantilados"). **Limitación crítica**: usa `agua_cercana(h, 60)` y
  `buscar_camino(c0, c, 40000)` con **presupuesto fijo 40000**, no el `nodos_camino` de
  producción (12000 a 50 m). En el mundo de prueba (64–192 celdas) las rutas son cortas y el
  presupuesto nunca se agota. **No cubre C1 ni C2.**
- `tests/test_fauna.py:1270-1273` verifica que el presupuesto escala con la resolución (no que
  sea suficiente).
- `tests/test_motor.py:50-79` fija (y por tanto "bendice") la semántica de caché negativa que
  causa C2.
- `tests/test_cerebro_cognitivo.py:72,99,587-602` y `test_sim_io.py:27` cubren el caso feliz
  (agua adyacente / `satisfy_sed` elegido).

### Faltantes (prioritarios)
1. **Test de consistencia detección↔enrutado con presupuesto de PRODUCCIÓN**: para muchas
   posiciones, si `agua_cercana(h, r)` devuelve `c`, entonces
   `buscar_camino(c0, c, sim.nodos_camino)` no debe ser `None`. Debe fallar hoy (C1).
2. **Test de no-cacheo de alcanzables**: un destino alcanzable cuyo primer `buscar_camino` agota
   `nodos_camino` no debe quedar cacheado como imposible (C2).
3. **Test de mundo grande a 5 m/celda** (no 64–192 celdas) con agua lejana y terreno con
   acantilados.
4. **Test de supervivencia** (ya pedido en `MUERTE_POR_SED.md`): correr un mundo N días y exigir
   que la población no colapse por sed.
5. **Validación de generación**: tras generar, comprobar que la componente del inicio tiene orilla
   alcanzable a distancia recorrible (C5).

---

## 10. Propuesta de corrección ordenada por prioridad

**P0 — Unificar "alcanzable" entre detección y enrutado (C1+C2).**
Que `agua_cercana` y `buscar_camino` compartan presupuesto y criterio. Opciones:
(a) `agua_cercana` devuelve `None` si `buscar_camino(origen, c, nodos_camino)` es `None` (la
detección se vuelve honesta sobre lo enrutable); o (b) igualar `nodos_bfs` y `nodos_camino` y
documentar por qué. Además, **no cachear como imposible un destino alcanzable por BFS**: si la BFS
lo vio, el fallo es de presupuesto, no de topología; excluir esos destinos de `_fracasos` o
permitir reintento con presupuesto mayor.

**P1 — Acotar el radio de detección a lo recorrible (C3).**
`r_agua_cerca`/`r_agua_lejos` deben derivarse del tiempo de marcha disponible antes de la muerte
por sed, no de una constante fija en metros. P. ej. radio ≈ (margen_min_s × velocidad_media) en
metros, con tope. Si no hay agua a esa distancia, `buscar_agua_lejos` ya cubre la exploración.

**P2 — Feedback honesto (C4).** Separar en `decisiones`/eventos: "acción aceptada", "ruta
encontrada", "llegó", "bebió", "sed satisfecha". `ok=1` no debe significar éxito de la necesidad.

**P3 — Validación post-generación (C5).** Añadir una pasada que exija, por cada componente
transitable poblada, una orilla alcanzable dentro del radio recorrible; si no, recolocar o
rechazar el mundo. Eliminar el `return cand[0]` que acepta componentes pequeñas.

**P4 — Diagnóstico persistente (C6).** Convertir `SED-SIN-CAMINO`/`AGUA-CERCANA-NONE` en eventos
del motor (tabla de eventos / `diagnostico.py`), con `habitante_id`, pos, destino y motivo.

**P5 — Heurística (H6).** Si se confirma impacto, hacer la heurística admisible también para
biomas con multiplicador <1 (usar el costo mínimo de celda como base de la heurística).

---

## 11. Riesgos de modificar cada subsistema

- **P0 (presupuestos/detección/enrutado):** tocar `agua_cercana`/`buscar_camino` afecta a **todo**
  el movimiento (explorar, huir del fuego, buscar personas, refugio). Riesgo de regresión global;
  exige los tests de §9 y la comparación diferencial de `ir`, `ir_hacia`, `buscar`,
  `refugio_de_fuego`. La caché negativa es una optimización de rendimiento: aflojarla puede
  reencarecer el A* (vigilar latencia).
- **P1 (radios):** cambiar `r_agua_*` altera la conducta observada y la velocidad del mundo
  (latencia). Afecta también al prompt del LLM (lo que "ve"). Riesgo de que explore menos.
- **P2 (feedback):** bajo riesgo funcional; es contrato de datos que consume el visor y el
  entrenamiento (`entrenamiento_cerebro`). Mantener columnas existentes y **agregar** campos.
- **P3 (validación de mundos):** puede **rechazar mundos** que antes se generaban; subir
  `VERSION_GENERADOR` y regenerar (los mundos guardados conservan su mapa). Riesgo de
  incompatibilidad con mundos viejos ya guardados.
- **P4 (diagnóstico):** bajo riesgo; añade escrituras (eventos) — vigilar volumen.
- **P5 (heurística):** bajo riesgo, localizado en `buscar_camino`.

---

## 12. Plan de implementación por etapas (criterios de aceptación verificables)

**Etapa 1 — Reproducir y medir (sin arreglar).**
- Test A (falla hoy): `agua_cercana(h,r)` devuelve `c` ⇒ `buscar_camino(c0,c,sim.nodos_camino)`
  no es `None`, sobre ≥N posiciones de un mundo a 5 m/celda con acantilados.
- Test B (falla hoy): destino alcanzable cuyo primer `buscar_camino` agota `nodos_camino` no queda
  en `_fracasos`.
- Criterio: A y B fallan y se adjunta su traza.

**Etapa 2 — P0 (unificar + no cachear alcanzables).**
- A y B pasan. Suite completa verde. Comparación diferencial de `ir/ir_hacia/buscar/refugio`
  contra el commit base (mismos stdout/exit en los tests). Latencia del A* no empeora >X%.

**Etapa 3 — P1 (radio recorrible).**
- Test: con sed 100 y agua a distancia D, el habitante llega y bebe antes de morir en ≥90% de
  corridas; el radio efectivo se deriva del margen de sed.
- Suite verde; velocidad del mundo (latencia) dentro de lo esperado.

**Etapa 4 — P2 (feedback).**
- Test: una decisión `ir` con ruta y sin beber posterior NO marca "necesidad satisfecha"; los
  campos nuevos existen y las columnas viejas siguen pobladas.

**Etapa 5 — P3 (validación de generación).**
- Test: un mundo cuya componente inicial no tiene orilla recorrible es rechazado/recolocado;
  `elegir_inicio` ya no cae a `cand[0]` sin verificar accesibilidad.
- Subir `VERSION_GENERADOR`; documentar en `CHANGELOG.md` y `docs/`.

**Etapa 6 — P4/P5 (diagnóstico y heurística).**
- Test: `SED-SIN-CAMINO` queda como evento consultable; heurística admisible con biomas <1.

**Criterio global de aceptación:** el test de supervivencia (§9.4) corre un mundo ~10 días y la
población no colapsa por sed; los tests A/B permanecen verdes.

---

## Anexo: cambios previos en la distancia de detección

El historial Git del repositorio es **un único commit squash** (`96916eb "chore: base estado
inicial mundo-vivo"`); `git log -S "r_agua_cerca"` y `-S "agua_cercana"` no devuelven evolución.
La historia de la distancia de detección sólo sobrevive en **comentarios del código** y en
`docs/MUERTE_POR_SED.md`:
- `simulacion.py:347-351`: "con un solo radio de 1,1 km … se morían de sed sin llegar nunca al
  agua" → se separaron `r_ver_fuego`/`r_huir_fuego`.
- `simulacion.py:352-353`: valores actuales `r_agua_cerca=3000 m`, `r_agua_lejos=7000 m`.
- `MUERTE_POR_SED.md`: el bug previo era de **decisión** (precondiciones), ya corregido; queda
  abierto "la BFS `agua_cercana` falla a 28 celdas" y "no hay test de supervivencia".
No es posible atribuir un commit concreto a cada cambio de `r_agua_*` con el historial disponible.
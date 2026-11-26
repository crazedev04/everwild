# Implementación P1 — Feedback real de acciones y alcance de búsqueda de agua

> Implementación de P1 del informe `docs/AUDITORIA_GENERACION_NAVEGACION_AGUA.md`, sobre P0 ya
> aplicado (`docs/IMPLEMENTACION_P0_AGUA.md`). No se reimplementó P0.
> Alcance: P1.1 (semántica del feedback) y P1.2 (radio de detección por costo/tiempo).
> No se tocó el generador, biomas, hidrología, CCA, bases de datos ni mundos. Sin commits ni push.

## 1. Causa corregida

- **P1.1 (feedback engañoso):** la acción `ir` devolvía `ok=True` con el texto
  `"Fuiste hacia satisfy_sed."` al **iniciar** la marcha. El registro `decisiones.ok` y el visor lo
  leían como éxito, aunque el habitante no había llegado ni bebido. El `ok` del motor es el
  `accepted` que el adaptador CCA traduce a `ACCEPTED/REJECTED`; no significa "necesidad
  satisfecha".
- **P1.2 (alcance no viable):** `agua_cercana` usaba un radio geométrico fijo
  (`r_agua_cerca=3000 m`, `r_agua_lejos=7000 m`). A 5 m/celda son 600–1400 celdas; cruzarlas por
  terreno con pendiente/bioma puede exceder el tiempo hasta que la sed se vuelve letal. La
  detección ofrecía agua inalcanzable **en tiempo** aunque existiera la ruta.

## 2. Semántica del feedback: anterior vs nueva

Contrato conservado (lado Mundo Vivo, sin tocar CCA): `_aplicar` devuelve `(ok: bool, texto)`;
`registrar_resultado` lo pasa al adaptador, que arma `ActionResult(status=ACCEPTED if ok else
REJECTED, rejection_reason=texto si rechaza)`. No se inventaron estados nuevos.

| Situación | Antes | Ahora |
|---|---|---|
| `ir` inicia marcha | `ok=True`, "Fuiste hacia satisfy_sed." | `ok=True` (ACCEPTED = acción aceptada), texto explícito de **en camino**: "Vas hacia el agua; todavía no bebiste." |
| `ir` ya en el lugar (no adyacente) | "Ya estás ahí." | igual; no bebe, sed intacta |
| `ir` sin camino | `ok=False`, "No encontraste camino." | igual (REJECTED) |
| Beber adyacente | `ok=True`, "Bebiste agua.", sed −60 | igual; es el **único** evento que refleja consumo |
| Beber no adyacente | `ok=False`, "Aquí no hay agua." | igual (REJECTED), sed intacta |

Claves:
- Iniciar ruta = **progreso** (ACCEPTED, texto "en camino"), no llegada ni consumo.
- Llegada y consumo son eventos separados (`beber`), con su propio `ok` y texto.
- El texto ya no nombra el `goal_id` como si estuviera cumplido.
- `ok` conserva su significado para el adaptador y para el resto de acciones (explorar, `ir_hacia`,
  `buscar`): ACCEPTED = "el mundo aceptó y ejecuta", REJECTED = "no pudo".

## 3. Fórmula y parámetros del alcance de búsqueda (P1.2)

En vez de un radio geométrico, el alcance se mide por **costo de ruta** contra el **tiempo
disponible** hasta la sed crítica.

- Tiempo de marcha disponible (segundos):
  `t_marcha = (SED_CRITICO − sed) / SED_SUBE_MIN × 60 × MARGEN_MARCHA_AGUA`
  - `SED_CRITICO = 90.0` (sed desde la cual la salud baja; antes `90` inline en `_vida`).
  - `SED_SUBE_MIN = 0.11` (sed por minuto despierto; antes `0.11` inline en `_vida`).
  - `MARGEN_MARCHA_AGUA = 0.6` (se usa 60 % del tiempo para caminar; el resto es margen).
- Costo de una ruta (segundos): suma de `Terreno.costo[y,x]` de cada celda (bioma × pendiente ×
  río), `_costo_ruta`.
- Una orilla candidata se acepta sólo si es enrutable (P0) **y** `_costo_ruta(ruta) ≤ t_marcha`.

Justificación (no arbitrario): sale de las constantes reales de sed de `_vida` y del costo por
celda del terreno. Con sed baja, `t_marcha` es enorme (p. ej. sed 30 → ~5,5 h de marcha), así que
el agua lejana sigue siendo viable; con sed alta se achica (sed 89 → ~0,5 min) y el agua lejana en
tiempo se descarta. El radio geométrico `r_agua_*` queda como cota superior del BFS (rendimiento);
el filtro real es el tiempo.

## 4. Archivos modificados

- `src/mundo_vivo/motor/simulacion.py`
  - Constantes nuevas `SED_SUBE_MIN`, `SED_CRITICO`, `MARGEN_MARCHA_AGUA` (fuente única; se usan en
    `_vida` y en el alcance).
  - `_vida`: `0.11` → `SED_SUBE_MIN`; `90` → `SED_CRITICO` (sin cambio de valor).
  - `agua_cercana`: acepta orilla sólo si `_costo_ruta(ruta) ≤ _t_marcha_agua(h)`.
  - `_t_marcha_agua(h)` y `_costo_ruta(ruta)` (nuevos).
  - `_aplicar` (tipo `ir`): texto honesto de "en camino"; no nombra `goal_id` como cumplido.
- `tests/test_fauna.py`: clase `TestFeedbackAgua` (10 tests deterministas sobre el sim de `_Base`).

## 5. Pruebas y resultados

`TestFeedbackAgua` (sim 192×192 a 50 m, determinista):
1. `test_iniciar_ruta_no_es_llegar_ni_beber` — `ir` ok, `caminando`, sed intacta, texto "no bebiste".
2. `test_desplazamiento_parcial_no_es_llegada` — tras `_mover` diminuto sigue `caminando`, sed intacta.
3. `test_estar_en_un_lugar_no_es_beber` — `ir` al propio lugar (no adyacente): "ya está ahí", sed intacta.
4. `test_beber_reduce_la_sed_y_se_refleja` — adyacente, sed 80 → <80, "Bebiste".
5. `test_beber_sin_agua_es_fracaso` — no adyacente → `ok=False`, sed intacta.
6. `test_el_presupuesto_de_marcha_se_achica_con_la_sed` — `t_marcha` baja al subir la sed.
7. `test_agua_retorno_es_viable_en_tiempo_o_none` — con sed crítica, lo devuelto es viable en
   tiempo (costo ≤ `t_marcha`) o `None`.
8. `test_agua_cercana_y_alcanzable_con_sed_baja` — con sed baja devuelve orilla enrutable.
9. `test_explorar_sigue_funcionando` — `ir` "explora" ok, `caminando` (otras acciones intactas).
10. `test_contrato_cca_mapea_ok_a_aceptado_rechazado` — `result_from_world(ok=True)→ACCEPTED`,
    `ok=False→REJECTED` (se salta si `cognitive_engine` no está instalado).

Cobertura de los 9 requisitos: 1↔test1; 2↔test2; 3↔test3; 4↔test4; 5↔test5; 6↔test6/7;
7↔test8; 8↔test9; 9↔test10.

Resultado targeted: `9 passed, 1 skipped` (CCA skip por entorno sin `cognitive_engine`).
`py_compile` OK en los archivos modificados.

## 6. Compatibilidad con CCA

- No se modificó CCA ni el adaptador `MundoVivoAdapter` (repo aparte).
- El contrato `(ok, texto)` se conserva; `ok` sigue mapeando a `ACCEPTED/REJECTED`. Sólo cambió el
  **texto** (honesto) y la **semántica de cuándo** se emite cada evento (progreso vs consumo), que
  ya eran eventos separados.
- `test_contrato_cca_...` verifica el mapeo; en este entorno `cognitive_engine` no está instalado y
  el test se salta (igual que el resto de tests del puente cognitivo).

## 7. Riesgos y limitaciones pendientes

- El filtro por tiempo añade un `_costo_ruta` por orilla candidata (suma sobre la ruta ya calculada
  por P0); costo despreciable frente al A*.
- `MARGEN_MARCHA_AGUA=0.6` y `SED_CRITICO=90` son parámetros justificados por el código, pero no
  calibrados contra un mundo largo real (no se corrieron mundos; alcance de código + tests).
- El radio geométrico `r_agua_*` no se modificó; ahora es cota secundaria del BFS.
- No se tocó el balance de sed/hambre/salud (sólo se extrajeron constantes con el mismo valor).

## 8. Qué queda para P2

- **P2 — validación de habitabilidad:** el generador sigue sin garantizar que cada componente
  poblada tenga orilla alcanzable a distancia recorrible; no abordado.
- No afirmar que las muertes por sed estén resueltas: falta validar la habitabilidad de los mundos
  (P2) y, opcionalmente, calibrar los márgenes con un mundo largo.
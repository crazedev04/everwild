# El cerebro de los habitantes: Cognitive Engine

Mundo Vivo puede manejar a sus habitantes con dos cerebros distintos:

| Cerebro | Qué es | Cuándo conviene |
|---|---|---|
| `hibrido` (default) | Reflejos + modelo de lenguaje local (Ollama) + respaldo. Es el de siempre, en `agentes/mente.py`. | Cuando interesa el lenguaje: charlas, mentiras, inventos narrados. |
| `cognitivo` | **Cognitive Engine**, el proyecto aparte: GOAP + Utility AI, sin modelo, determinista y microsegundos por decisión. | Cuando interesa correr mucho tiempo, rápido y reproducible, o probar el cerebro sin que la latencia del modelo tape todo. |

## Cómo se corre

El cerebro **no se ejecuta aparte**: Cognitive Engine corre dentro del mismo proceso, así que hay un
solo comando. Lo más corto es el script del repo:

```bash
./mundo.sh ver                      # visor en http://localhost:8767, cerebro cognitivo
./mundo.sh ver hibrido              # lo mismo con el cerebro de siempre (modelo de lenguaje)
./mundo.sh adelantar <mundo> 120    # adelanta 120 días a fondo, sin pantalla
./mundo.sh correr <mundo> 500       # lo deja corriendo a 500× sin pantalla (Ctrl+C guarda)
./mundo.sh nuevo                    # mundo nuevo + 4 habitantes
```

A mano es la variable de entorno `MUNDO_VIVO_CEREBRO` (`cognitivo` o `hibrido`), que respetan
`servir`, `correr` y `simular`:

```bash
MUNDO_VIVO_CEREBRO=cognitivo PYTHONPATH=src python3 -m mundo_vivo --datos datos servir --puerto 8767
```

### Velocidad real (medido en 0.10.0)

| Mundo | Habitantes | Minutos de mundo por segundo de CPU |
|---|---|---|
| 256×256 | 25 | ~960 |
| 2048×2048 (el de verdad) | 4 | ~99 |

En el mapa grande el costo es del **motor** (A* largo, fuego, nieve y clima sobre 4 millones de
celdas), no del cerebro. Así que `500×` en el visor no rompe nada: el bucle recorta el avance y el
mundo corre a lo que puede, alrededor de 100×. Para adelantar de verdad —un año son 120 días— el
camino es `adelantar`, que no tiene presupuesto por vuelta: a 14,6 s por día, un año son unos 30
minutos de reloj.

Si el motor cognitivo no se encuentra, el arranque **falla con un mensaje claro** en vez de seguir a
medias. Se lo busca en este orden: la variable `COGNITIVE_ENGINE_SRC`, o una carpeta hermana del
repo llamada `Cognitive Engine/src`.

## La regla que manda: el NPC se amolda al cerebro

El motor cognitivo tiene que poder correr en cualquier proyecto, así que **no sabe nada de Mundo
Vivo**: ni celdas, ni biomas, ni recetas, ni el nombre de una sola cosa de este mundo. Toda la
traducción vive de este lado, en `agentes/cerebro_cognitivo.py`. Si mañana el cerebro maneja los NPC
de otro juego, ese juego escribe su propio adaptador y el motor no se toca.

El contrato es el mismo de los dos lados, y es el que ya tenía Mundo Vivo: **el cerebro propone, el
entorno valida y ejecuta, y devuelve el resultado**. `Simulacion._aplicar` sigue siendo la única
autoridad.

## Qué traduce el puente

**De ida (mundo → cerebro)**

- **Las barras del cuerpo a necesidades.** Acá `sed` alta es mala y `energia` alta es buena; en el
  motor cognitivo todas las necesidades van de 0 (crítica) a 100 (saciada). La inversión se hace una
  sola vez y en un solo lugar.
- **La percepción a hechos.** Posición propia, agua al alcance y gente cerca, cada uno con sus
  coordenadas. El agua se declara con `satisfies: ["sed"]`: el motor no sabe qué es el agua, sabe
  que eso sirve para esa necesidad.
- **Las creencias que sólo el mundo conoce** (`extra_state`): si el agua está adyacente o sólo
  recordada, si hay comida en el inventario o sólo algo juntable acá.
- **El genoma a personalidad**: curiosidad → `curiosity`, cautela → `cautiousness`, sociabilidad →
  `sociability`, resiliencia → `persistence`.

**De vuelta (cerebro → mundo)**

Las capacidades declaradas se llaman igual que las acciones de Mundo Vivo, así que la propuesta se
traduce casi directo. Lo que resuelve el puente es el dato concreto: a qué agua ir, qué comer, a
dónde explorar (siempre en **metros**, convertidos con `Simulacion.celdas()`).

### Necesidades

Siete, y el tipo de curva importa:

| Necesidad | Sale de | Curva | ¿Puede ser crítica? |
|---|---|---|---|
| `sed` | `100 - h.sed` | cuadrática | sí, desde 55 |
| `hambre` | `100 - h.hambre` | cuadrática | sí, desde 60 |
| `energia` | `h.energia` | cuadrática | sí, bajo 30 |
| `salud` | `h.salud` | cuadrática | sí, bajo 45 |
| `calor` | `100 - 100·h.frio` | cuadrática | sí, sobre 0,65 de frío |
| `compania` | gente cerca / ausentes | lineal | **nunca** |
| `herramientas` | si lleva algo que sirva | lineal | **nunca** |

Las del cuerpo usan curva cuadrática: no molestan hasta que aprietan, y entonces explotan. Las otras
dos usan curva lineal y están declaradas **nunca críticas**, así que empujan de a poco y pierden
siempre contra la sed. Eso además evita que apaguen la curiosidad.

El piso del objetivo de reposo está en **0,3** (el default del motor es 0,5). Con 0,5 los habitantes
se quedaban sentados una vez cubierto el cuerpo: no fabricaban ni buscaban a nadie.

### Capacidades

Las que declara el puente, cubriendo las 20 acciones del motor:

| Necesidad | Capacidades (precondición → efecto) |
|---|---|
| sed | `beber` (agua al lado → saciado) · `ir_al_agua` (agua conocida → agua al lado) |
| hambre | `comer` (comida en mano) · `juntar_comida` (juntable acá) · `cazar` (presa cerca → crudo) · `cocinar` (crudo + fuego → comida) · `curar_carne` (crudo → comida) |
| energía / salud | `dormir` · `usar` (remedio en mano, sólo salud) |
| calor | `encender` (chispa + leña → fuego) · `ir_al_fuego` (fuego conocido → fuego) · `calentarse` (fuego al alcance → saciado) · `tomar_fuego` (fuego + palo → antorcha) |
| compañía | `hablar` (alguien cerca) · `ir_hacia` y `buscar` (alguien lejos → alguien cerca) · `ensenar` (cerca + algo que el otro no sabe) · `proponer_hijo` (cerca + pareja posible) · `responder_propuesta` (propuesta pendiente; el costo más bajo del catálogo, contestar es casi un reflejo) |
| herramientas | `fabricar` (receta lista) · `juntar_material` (material acá → receta lista) · `inventar` (combinación para probar → receta lista) |
| cualquiera | `montar` · `desmontar` · `atravesar` (pasaje al lado) · `explorar` · `esperar` |

**Ninguna secuencia está escrita.** La cadena cazar → cocinar → comer sale de que cazar deja carne
cruda, cocinar pide carne cruda **y** fuego, y comer pide comida en mano. Hay tests que lo verifican,
incluido el detalle de que con el fuego ya hecho cocinar le gana a curar por costo, y sin fuego es al
revés.

Dos errores que esto destapó y vale anotar:

- `encender` e `ir_al_fuego` **no** satisfacen ninguna necesidad: conseguir fuego es un medio. Cuando
  declaraban `need_satisfied`, el planificador «comía» prendiendo una fogata. Lo que calienta es
  quedarse al lado (`calentarse`).
- `explorar` tiene efectos **optimistas** (deja todo como «conocido») y el costo más alto del
  catálogo. Si sale a explorar y no aparece nada, el plan se cae, se replanifica y la pericia
  aprendida encarece esa salida. Es a propósito: el que no explora nunca no encuentra nada.

## Lo que el puente NO delega

- **El fuego encima.** Si hay fuego cerca y la sed no está matando, manda el reflejo de huir. El
  fuego no admite deliberación.
- **La validación.** Toda acción pasa por `_aplicar` igual que antes.

## Diferencias que se ven en el panel

- `pendientes()` es siempre 0: el cerebro es sincrónico, no espera a ningún modelo.
- `latencia_s` es 0 y **el mundo deja de estar limitado por `tope_pensando`**: la velocidad la pone
  la física, no la inferencia.
- Números nuevos: `cerebros` (cuántos hay vivos), `replanificaciones`, `pericia` (lo que cada uno fue
  aprendiendo por acción) y `sin_traducir`, que tiene que quedar **vacío**: si algo aparece ahí, el
  cerebro propuso una capacidad que el puente no sabe convertir en acción.

## Estado y límites conocidos

Probado en `tests/test_cerebro_cognitivo.py` (18 pruebas que se saltean solas si el motor no está
instalado): la acción propuesta siempre es una que el motor sabe ejecutar; las cadenas emergentes
(cazar → cocinar → comer, juntar → fabricar, buscar → hablar, encender → calentarse); que conseguir
fuego no saque el hambre; que el costo elija entre curar y cocinar según haya fuego o no; el objetivo
que sale de la necesidad más urgente; el rechazo que invalida el plan; el aprendizaje del resultado;
el determinismo; las personalidades que deciden distinto; que toda capacidad declarada tenga su
traductor; y un mundo de 4 habitantes corriendo 10 horas simuladas sin romperse.

Lo que de verdad hacen, medido en un día simulado (1.440 minutos, 4 habitantes, semilla 11): bebieron
solos, juntaron materiales, **inventaron** por su cuenta, fabricaron capas de paja y cercas de palos,
y se fueron a dormir de noche. 225 decisiones, cero capacidades sin traducir.

Lo que **todavía no hace**: mentir (el híbrido tiene cuatro intenciones al hablar y acá el mensaje es
siempre «contar»), construir refugios como objetivo propio, y nada que dependa de redactar texto. Las
20 acciones del motor están cubiertas, pero la riqueza del lenguaje no se reemplaza con un
planificador.

Lo que falta medir: un mundo largo de verdad. Los peores bugs de este proyecto aparecieron mirando un
mundo que corrió horas, no en los tests.

## Costo

El puente recalcula todas las creencias en cada decisión, y tres consultas son caras:
`disponibles()`, `ausentes()` y `ver_animales()`. Son las mismas que ya hacía el respaldo del cerebro
híbrido, pero antes sólo corrían para quien no estaba en foco del modelo. Está anotado en
`docs/OPTIMIZACION.md`.

## CCA v1.1 — Módulos activos y cambios de API

Desde la integración de CCA v1.1, el adaptador instancia y cablea los siguientes módulos dentro de cada `AutonomousBrain`:

| Módulo | Clase | Parámetros clave |
|--------|-------|-----------------|
| Emoción | `EmotionModule` | `brain_id`, `initial_state=AffectState(valence=0.5, arousal=0.3, dominance=0.5)` |
| Valores | `ValueSystem` | Calibrado por rasgos: `curiosidad→curiosity`, `sociabilidad→social_connection`, `cautela→survival` |
| Autoconcepto | `SelfModel` | `brain_id=...` |
| Cognición social | `SocialCognition` | `brain_id=...` |

### Tiempos explícitos en Observation

`Observation` recibe ahora dos campos temporales que el motor cognitivo usa internamente:

```python
Observation(
    facts=hechos,
    simulation_time=float(sim.t),           # minutos simulados absolutos
    delta_simulation_time=dt_sim,           # delta desde el tick anterior de este habitante
)
```

`delta_simulation_time` se calcula desde `self._ultimo_tick[h.id]` y limita a `[0, 1440]` para evitar
saltos grandes al inicializar o reiniciar.

### Persistencia

Los cerebros cognitivos se guardan en un archivo SQLite **separado** de la base del mundo:

```
<carpeta_del_mundo>/cerebros_cognitivos.db
```

El guardado ocurre:
- En cada ciclo de `guardar()` (misma frecuencia que `GUARDAR_CADA_S`).
- Al olvidar un habitante fallecido (`olvidar(h_id)`).

Al crear el cerebro de un habitante que ya existía, `_cerebro_de` intenta recuperarlo con
`_estado_persistido(brain_id)`. Se restaura sólo lo que la base del mundo no guarda: memorias
episódicas y semánticas, mapa espacial, pericia aprendida, ids deterministas y el objetivo vigente.
Las necesidades y la personalidad no se cargan del archivo: las manda el mundo (estado del
habitante y genoma), que es la fuente de verdad. El plan en curso tampoco se restaura —se
replanifica desde las creencias actuales—, igual que en el motor cognitivo.

Si el guardado falla (tabla corrupta, disco lleno, etc.) **no tumba la simulación**: el error queda
registrado en `_guardados_fallidos` y `_ultimo_error_guardando`. Si lo que falla es la carga, queda
en `_restauraciones_fallidas` / `_ultimo_error_restaurando`. Ambos salen en el estado del cerebro.
Un cerebro nuevo no cuenta como falla de carga: su `BrainNotFoundError` es el caso normal.

Al abrir un mundo, `CerebroCognitivo.__init__` llama a `recuperar_cerebros()`, que recupera todos los
cerebros persistidos de ese mundo y los registra en el scheduler antes de la primera decisión. Así la
continuidad está lista de entrada sin esperar a que cada habitante decida por primera vez. `list_brain_ids()`
devuelve los ids de todos los cerebros persistidos para el mundo. La recuperación no duplica: el scheduler
descarta ids ya registrados y `recover_brains` saltea los archivados. Cada restauración cuenta en
`cerebros_restaurados` del estado del cerebro.

### Correr tests de integración

```bash
cd /home/cracken/Mimundo/mundo-vivo
PYTHONPATH="src:/home/cracken/Mimundo/Cognitive Engine/src" \
    .venv/bin/pytest tests/test_cerebro_cognitivo.py -q
```

Debe terminar con `28 passed`.

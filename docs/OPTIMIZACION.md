# Optimización — pendiente para ir mejorando en cada actualización

Objetivo: gastar lo mínimo de CPU, GPU, memoria y disco, sin perder lo que se ve ni lo que pasa en el mundo. Nada de esto está hecho todavía salvo lo marcado.

## Ya hecho
- Bucle del motor con presupuesto de 35 ms por vuelta (recorta en vez de acumular atraso); estado al visor a 10 Hz.
- Fauna con grilla espacial y ticks de 5–30 min según distancia; tope de 450 animales.
- Velocidad automática según lo que tarda el modelo (no se gasta GPU en pensar más rápido de lo que se puede usar).
- Visor: la lista de gente y la ficha solo tocan el DOM si cambió el contenido.

## Medido el 24/11/2026 — mundo de 2048×2048 con celdas de 5 m, cerebro cognitivo

Perfilado con el mismo troceado que usa el servidor (tandas de 2 minutos simulados, `PASO_AVANCE`).
El punto 1 de la lista de abajo («medir primero») está hecho; esto es el resultado.

**41,5 → 234 minutos simulados por segundo real (5,6×). 167 MB menos al cargar.**
(Primer bloque 41,5 → 81,3; segundo bloque 81,3 → 234.)

### Lo que se arregló y cuánto era

| qué | era | por qué |
|---|---|---|
| `fuego.paso` | **52% del CPU** | recorría las 4,2 M de celdas seis veces por minuto simulado para rebrotar combustible que nadie gastó y borrar ceniza que no existía, en un mundo que nunca se incendió |
| `_creencias` | 11% del CPU, el doble de lo necesario | `_anotar_decision` la recalculaba sólo para el registro de entrenamiento |
| `sabe()` | 455.924 llamadas en 50 días simulados | recorría todo lo que la persona conoce; ahora la vuelta de receta a conocimiento está indexada |
| `_idea_para_probar` | re-ordenaba ~190 recetas por decisión | catálogo compilado una vez, y la prueba barata (ingredientes) antes de la cara (`sabe`) |
| `Terreno._c` | 134 MB | `tolist()` hacía un float por celda; hay **3.809 valores distintos** en 4,2 M de celdas, así que se comparten |
| `Terreno.gx`, `.gy` | 67 MB | no se leían en ninguna parte |

Y una regla que conviene dejar escrita, porque es la forma del bug del fuego: **una operación sobre
el campo entero del mapa no puede correr por minuto simulado si no hay nada que hacer.** En 2048² son
4,2 millones de celdas; seis pasadas son ~100 MB de memoria movida por minuto del mundo. Lo que hay
que preguntarse antes de cada pasada no es «cuánto cuesta» sino «¿hace falta?». Y si la operación es
asintótica (como el rebrote, que se acerca a su objetivo sin llegar nunca), tiene que **cerrar el
ciclo**: sin un corte se paga para siempre el costo de un incendio de hace meses.

### Lo que ahora manda, con número

**El A* es el 66% del CPU y falla 2 de cada 3 búsquedas.** Medido en 3 días simulados: 36 búsquedas,
19,1 s dentro del A*, **24 fallidas** que tiraron 16,7 s a la basura. Ninguna búsqueda de más de 350
celdas tuvo éxito. Y no es que el destino sea inalcanzable: se comprobó que está en la **misma isla**
(1.367.281 celdas alcanzables desde el origen).

La causa no está en el A*, está en el relieve. En ese mundo el costo mediano de pisar una celda es
**21,6** y la heurística del A* vale **1 por celda**: subestima 21,6 veces, así que deja de guiar y el
A* degenera en Dijkstra hasta agotar los 120.000 nodos de presupuesto, a 0,7 s por búsqueda. Y el
costo es 21,6 porque `ALTURA_MAX_M` y `PROFUNDIDAD_MAX_M` son constantes fijas de 3.000 m que **no
miran `tam_celda_m`**, mientras los tamaños de rasgo del ruido están en celdas: un mapa de 2048² con
celdas de 5 m son 10,2 km de lado con 6.405 m de desnivel, o sea pendiente mediana de 58° y 67% del
mapa intransitable. El mismo mapa a 50 m/celda da 9° y costo 1,2, que son los números con los que
está calibrado todo el resto del motor.

La **caché de búsquedas fallidas** ya está hecha (segundo bloque, más abajo): el mismo destino
imposible se reintentaba 12 veces, a 0,7 s cada una. Eso tapa el síntoma más caro, pero la causa
—el relieve— sigue ahí, y con ella que haya destinos alcanzables que el A* no encuentra. El orden es:
primero el relieve, después volver a medir el A*, y recién entonces decidir si hace falta tocar la
heurística.

### Crecimiento: qué crece y qué no

Medido con 52 días simulados seguidos en proceso, sondeando cada 2 días:

- **La memoria del proceso NO crece**: quedó plana en 869.884 kB desde el día 25 hasta el final.
  `refugios`, `agotamiento`, `fogatas`, `aldea_num`, `_pisadas`, `_bioma_previo`, `colonias`, animales
  y especies se quedaron todos quietos. El desgaste del suelo sube y baja, porque se desvanece.
- **Lo que sí crece sin techo es el disco**: `entrenamiento_cerebro` **no se poda nunca**, mientras
  `decisiones` sí. Es una fila con seis JSON por cada decisión de cada habitante: 45.269 filas en el
  mundo `gaia`, 40.695 en otro. Eso es lo que hay que acotar.
- `_eventos` y `_efectos` crecen sólo si nadie los vacía; el servidor los vuelca cada 2 segundos y
  `correr` también, así que en los dos caminos reales están acotados. Sólo crecen en una corrida que
  llame a `sim.avanzar` a mano sin volcar, como un script de medición.

### Segundo bloque (mismo día)

| qué | era | ahora |
|---|---|---|
| `buscar_camino` | 11,8 s, 2,5 M de `heappop` | 2,2 s, 636 mil — caché de viajes imposibles |
| `_paso_nieve` | 1,4 s | 0,3 s — mismo truco que el fuego |
| `entrenamiento_cerebro` | sin poda y sin índice, 60.989 filas | poda diaria de 2.000 por habitante, con índice |
| poda de `decisiones` | en cada guardado, cuadrática | una vez por día del mundo, por índice |

Dos cosas que conviene no olvidar de este bloque:

- **El éxito no se cachea, sólo el fracaso.** Un camino caduca en cuanto alguien construye algo; un
  viaje imposible no caduca hasta que cambia el mapa. Y cuando el mapa cambia (`cambiar_bioma`) hay
  que olvidar los fracasos: ésa es la **tercera** cosa que invalidar ahí, además de `costo` y `_c`.
- **La temperatura del mapa no se cachea.** Se probó y un test lo cazó enseguida: `terreno.temperatura`
  es un array público, y guardar sus valores derivados hace que escribirle no tenga efecto. Es la
  misma trampa que `Terreno.costo` contra `Terreno._c`. Los extremos se calculan en vivo: son dos
  reducciones sobre int8, del orden del milisegundo, y eso corre una vez cada media hora del mundo.

### Lo que queda por medir

- ¿Alguna fase nueva (0 a 7) rompió la regla de que el evaluador declarativo no corre por celda por
  tick? **No.** En el perfil no aparece `condiciones.py` ni ninguna tabla compilada;
  `_paso_senderos`, `_paso_conservacion`, `_paso_tecnologia`, `_paso_colonias` y `_paso_fenomenos`
  juntos no llegan al 1% del CPU.
- `fauna._tick` es ahora el más caro después del A*: 1,2 s de 12,8 (9%), con 450 animales. `Fauna` ya tiene grilla espacial
  (`_vecinos`), pero el camino que usa el puente (`ver_animales` → `cerca`) **recorre todos los
  animales del mundo**, no la grilla. **No se tocó a propósito**: la grilla se arma sólo dentro del
  tick de fauna, así que usarla desde afuera puede perder un animal que se movió —un depredador al
  lado—, y el beneficio había caído a 0,24 s al arreglar el doble `_creencias`. Para hacerlo bien
  hay que poder saber si la grilla está vieja, y eso ya no es gratis.

## A investigar y medir (en este orden)
1. **Medir primero**: perfil por fase (motor, fauna, clima, persistencia, visor) con un mundo de 1 año, y registrar el costo por día del mundo en el CHANGELOG de cada versión.
2. **Modelo de lenguaje** (el mayor costo): prompts más cortos (resumir lo repetido), caché del prefijo fijo (SISTEMA + acciones), `num_ctx` ajustado al largo real, `keep_alive`, cuantización y comparar 4b/9b por calidad vs. segundos por decisión; agrupar decisiones de varias personas cuando se pueda.
3. **Decidir menos**: las acciones largas (caminar, dormir, cazar) no vuelven a consultar al modelo hasta terminar; decisión por eventos (algo cambió) en vez de por reloj.
4. **Motor**: vectorizar con numpy lo que se repite por celda (fuego, nieve, clima); pasos de tiempo adaptativos (grandes si no hay nada cerca); mover la fauna lejana a un modo «estadístico» (no individual) cuando nadie la ve.
5. **Persistencia**: guardar solo lo que cambió (no todo el estado cada vez), comprimir los mapas dinámicos, `VACUUM`/`wal_checkpoint` periódico, límites para tablas que crecen (diálogos, decisiones, eventos triviales).
6. **Visor**: dibujar el mapa base en un canvas aparte y solo redibujar lo que se mueve; el mapa de nieve/ceniza como textura, no por celda; pausar el dibujo si la pestaña está oculta; enviar al visor solo lo que cambió.
7. **Memoria de recuerdos**: índice por etiquetas y límite por tipo, para que recuperar siga siendo O(pocas filas) con años de mundo.
   - Hecho en la fase N: los vectores de significado (`memorias.embedding`) se calculan **en un hilo aparte, en lotes de 16 y con un modelo chico**, nunca en el camino crítico de una decisión. El coseno es un producto punto de float32 ya normalizados (se guardan normalizados justamente para eso) sobre las ≤300 filas que `recordar()` ya traía.
   - A medir: `recordar()` hace `SELECT *`, así que ahora también trae los blobs (≈3 KB por recuerdo con nomic-embed-text). Con 300 filas son ~900 KB por llamada. Si pesa, seleccionar columnas y cachear la matriz por habitante.
8. **Cerebro cognitivo** (nuevo en 0.10.0, ver `docs/CEREBRO_COGNITIVO.md`): el puente recalcula **todas** las creencias en cada decisión, y tres consultas son caras: `disponibles()`, `ausentes()` y `ver_animales()`. Antes sólo corrían para quien no estaba en foco del modelo; ahora corren siempre y para todos. A medir con 25 habitantes y, si pesa, dos salidas: cachear las creencias por habitante durante unos minutos del mundo (casi nada de lo que miran cambia tick a tick), o calcular sólo las claves que necesita el objetivo que ya ganó. Ojo que este cerebro **no** usa GPU ni frena el mundo por latencia, así que cambia el perfil entero: el costo se va del modelo al motor.
9. **Contenedor / otra máquina**: recién cuando se quiera correr en un servidor; no ahora.

## Dimensiones (fase G2) — lo que hay que vigilar
- **Cada dimensión corre su propio paso cada tick, aunque no la mire nadie.** Hoy son dos mapas y la caverna es de 512×512 (la cuarta parte de un mundo de 2048²), así que se nota poco. Lo primero a medir cuando haya más de dos: si una dimensión está vacía de gente, sus animales, su fuego y sus colonias igual avanzan.
- Idea para cuando moleste: una dimensión **sin nadie vivo** puede avanzar por resumen (como el nivel 3 del LOD cognitivo), no tick a tick.
- El mapa de una dimensión se genera **al primer cruce** y queda guardado: no se paga nada hasta que alguien abre un paso. 512×512 tarda 0,3 s.

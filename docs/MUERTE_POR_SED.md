# Por qué se morían de sed al lado del agua

Hallazgo de campo del 24 de noviembre de 2026, sacado de mirar el mundo real `gaia` (1024×1024,
celdas de 5 m, cerebro cognitivo, 152.000 minutos simulados). No salió de ningún test: los 453 tests
pasaban mientras esto ocurría.

## Lo que se veía

De 27 muertes del mundo, **23 fueron de sed**. El latido del registro nuevo
(`src/mundo_vivo/diagnostico.py`) mostraba la población cayendo de 21 habitantes a 3, a 2 y a 1 en
tres minutos reales, con **0 fogatas** construidas.

## Lo que no era

Antes de acusar al terreno o a la búsqueda de caminos, se midió. Para cada habitante muerto se
reconstruyó su posición al morir y se le volvió a preguntar al motor si podía llegar al agua:

| muertos de sed | situación medida |
|---|---|
| 13 | estaban **pegados al agua**: `agua_adyacente` daba verdadero, cero pasos de distancia |
| 9 | tenían camino de 1 a 38 celdas, encontrado por el A* en menos de 0,1 s |
| 1 | a 140 m del agua, con la BFS `agua_cercana` sin encontrarla (eso sigue abierto, ver abajo) |

O sea: el agua estaba ahí y el motor sabía decirlo. **El problema era la decisión, no el mundo.**

Conviene anotar también un error que se cometió en el camino, porque es una trampa del proyecto: las
columnas `x`, `y` de la tabla `habitantes` guardan **metros**, no celdas (`sim_io` escribe `h.x * tam`
y al cargar divide). Leerlas en crudo daba coordenadas de 2.788 en un mapa de 1024, y por un rato
pareció que la gente se moría fuera del mapa. No era así.

## Lo que era: un bloqueo de precondiciones en el puente

La cadena completa, medida sobre la tabla `entrenamiento_cerebro` (60.989 decisiones):

1. La sed sube y pasa `UMBRAL_SED` (55). `satisfy_sed` entra en crítica.
2. La sed le baja la salud. La salud pasa `UMBRAL_SALUD` (45). `satisfy_salud` **también** entra en
   crítica.
3. El árbitro elige `satisfy_salud`. Medido con sed ≥ 80: eligió `satisfy_salud` el **48%** de las
   veces contra `satisfy_sed` el **41%**.
4. Las únicas dos capacidades que satisfacen la salud son:
   - `dormir`, cuya precondición es `PUEDE_DORMIR`, que el motor define como `h.sed < SED_DESPIERTA`
     (80). Con sed mortal es **falsa a propósito**: existe para que nadie se duerma y se muera de
     sed (ver «Prioridad de necesidades» en `CLAUDE.md`).
   - `usar`, que pide `OBJETO_USABLE`, o sea llevar un remedio encima.
5. Sin ninguna de las dos, el planificador no puede armar plan. Medido: el **73%** de las decisiones
   con sed ≥ 80 salieron con `plan: None`.
6. Cognitive Engine devuelve entonces su propio respaldo, `WAIT_ACTION` (`"wait"`).
7. **`"wait"` no estaba en `_TRADUCTORES`**, así que el puente caía en el camino de «capacidad
   desconocida»: esperar 15 minutos y sumar uno a `_sin_traducir`. En `gaia` pasó **790 veces**, 279
   de ellas con sed por encima de 80. Medido con sed ≥ 80, `wait` fue el **57,6%** de las decisiones.
8. La sed sigue subiendo durante esos 15 minutos. Volver al paso 3. Se muere.

El motor cognitivo hizo lo correcto con lo que le dijimos. Los dos errores son de este lado del
puente (`src/mundo_vivo/agentes/cerebro_cognitivo.py`).

## Lo que se arregló

**1. La salud no se declara crítica cuando no hay nada que hacer con ella.** En `_necesidades`, el
umbral de `SALUD` pasa a `NUNCA_CRITICA` si la sed ya pasó `SED_DESPIERTA` y no hay remedio encima.
No es un parche al árbitro: es que la salud no es una necesidad que se atienda sola, se arregla
arreglando lo que la está bajando. Con un remedio encima sí es crítica, porque ahí sí hay algo que
hacer.

**2. `"wait"` se traduce.** Es lo mismo que `esperar`, pero ahora queda dicho y deja de contarse como
capacidad desconocida. El contador `_sin_traducir` vuelve a significar lo que tiene que significar:
que el motor cognitivo propuso algo que el puente no sabe traducir.

El test `test_con_sed_mortal_la_salud_no_le_gana_la_puja_a_la_sed` falla si vuelve el bloqueo, y
`test_toda_capacidad_declarada_se_puede_traducir` ahora exige que el respaldo propio del motor
cognitivo esté traducido.

Medido después del arreglo, con el mismo mundo `gaia`: de las decisiones con sed ≥ 80, la que
apareció eligió `satisfy_sed` y la acción `beber`. Antes, de 484 decisiones con sed ≥ 80, **ninguna**
había sido `beber`.

## Lo que queda abierto

- **La BFS `agua_cercana` falla a 28 celdas.** Dos muertos (h26, h27) estaban a 140 m del agua y
  `agua_cercana` no la encontraba, con `r_agua_cerca` en 600 celdas. En un mapa donde sólo el 20% de
  las celdas son caminables puede estar genuinamente bloqueada, pero hay que confirmarlo celda por
  celda antes de darlo por bueno.
- **Siguen muriéndose por otras causas.** Quitar el bloqueo de la sed no deja un mundo estable: hay
  que repetir esta misma medición para el hambre, el frío y la salud. La forma del bug —una
  necesidad crítica cuyas capacidades están todas bloqueadas por otra necesidad crítica— puede
  repetirse en cualquier par.
- **Un test que mida la supervivencia.** Hoy nada falla si el mundo mata a todos. Haría falta una
  prueba larga que corra un mundo unos días simulados y exija que la población no colapse; sería la
  que hubiera cazado esto sin tener que mirar un mundo a mano.

# Hogar, aldeas, ruinas y senderos

Cómo el mundo hace que **convenga** construir y volver al mismo lugar. Implementa las fases 4 y 5 de
`docs/PLAN_MEJORAS_MOTOR.md`. La idea que atraviesa todo: **el motor no sabe qué es una aldea.** Lo que
hace que un montón de chozas se vuelva una aldea es físico, y de ahí sale el resto solo.

---

## 1. El calor cae con la distancia

Antes el calor era binario: `METROS_CALOR_FOGATA = 20` planos, y un paso más afuera cero. Daba lo mismo
estar encima de las brasas que a veinte metros, y después se cortaba de golpe.

Ahora cada estructura declara su forma, en metros y en el JSON:

```json
"provee": {"calor_C": 600, "nucleo_m": 6.0, "caida": "cuadratica"}, "radio_m": 20.0
```

- **`nucleo_m`**: adentro de esto el calor es pleno.
- **`radio_m`**: pasado esto no hay nada.
- **`caida`**: `lineal`, `cuadratica` o `escalon` (el escalón corta seco al salir del núcleo).

Nada de esto se mide en celdas. A 5 m por celda un «3×3 de celdas» serían 15 metros y a 50 m serían 150:
es el mismo error que ya se pagó con el alcance de las armas.

### Dos curvas, no una

| para qué | función | cómo cae |
|---|---|---|
| **trabajar** (fabricar, fundir, cocinar) | `calor_disponible(h)` | sólo el núcleo. No se funde metal «casi al lado» de la fragua |
| **abrigarse** (el frío) | `calor_de_estructuras(h)` | toda la caída: estar cerca ayuda un poco |

Las dos salen de `_provisto_en(x, y, campo, trabajo)`, que toma el campo por parámetro. Por eso la fase 7
(la electricidad) no necesitó un sistema nuevo: `energia_disponible` es la misma función con
`campo="energia_W"`. Y por eso `requisitos_ok` recorre una tabla (`PROVISIONES`) en vez de tener un `if`
por magnitud.

El costo está acotado: la caída se calcula con la distancia que ya se mide, nunca con un barrido de celdas.

---

## 2. La fogata abriga a las chozas

Esto es el corazón de la fase 4. `abrigo_efectivo(refugio)` devuelve el abrigo de la casa **más lo que le
suma el fuego que tenga alrededor**:

```
abrigo_efectivo = abrigo + (1 - abrigo) * 0.5 * (grados en la casa / grados de una fogata)
```

La misma choza de barro abriga 0.6 sola y más de 0.7 al lado de una fogata encendida. Con eso, construir
pegado al fuego es mejor que construir desparramado, y un grupo de chozas alrededor de un fuego es una
aldea sin que el motor haya tenido que saber qué es una aldea. `aldeas()` sigue agrupando por vecindad
entre casas (`METROS_ALDEA = 150`); la fogata entra como **atractor**, no como requisito.

El abrigo efectivo es el que usan `refugio_cerca` para elegir el mejor techo, el frío, y el descanso.

---

## 3. La casa es de alguien, y dormir en ella sirve

- `h.hogar_rid` apunta al **refugio concreto** (su `rid`), no a una coordenada suelta. `h.hogar` se
  conservó al lado porque lo usa el prompt; lo que se agregó es la identidad.
- `refugio_cerca` elige por abrigo efectivo, y **a igual abrigo gana el propio**: la cama de uno antes que
  la del vecino.
- **Dormir mira dónde se duerme.** Antes `_aplicar` con `tipo == "dormir"` sólo seteaba la hora de
  despertarse: se descansaba igual en el barro que en la choza. Ahora la recuperación de energía se
  multiplica por `1 + abrigo_efectivo` (hasta el doble con el mejor refugio), y el texto lo dice («te
  pusiste a dormir en tu choza de barro» / «a la intemperie»).
- El factor se mide **una sola vez, al acostarse** (`h.cama`). Durmiendo nadie se mueve, y `_actualizar`
  corre a 20 Hz por persona: calcular el refugio más cercano ahí adentro habría sido caro por nada.

Un horno, una fragua o un pozo tienen abrigo 0: no son la casa de nadie, no cuentan para el tope de
refugios por persona y no disparan el hito de «primera vivienda».

---

## 4. Ruinas

Lo que nadie usa se cae. `_paso_ruinas()` corre **una vez por día simulado** (no por tick: son 400
refugios contra 25 personas y esto tarda estaciones):

1. Si alguien está dentro del radio del techo, se marca `visto` y no pasa nada.
2. Si no pasó nadie en `DIAS_SIN_USO = 20` días, el abrigo empieza a bajar (`DESGASTE_POR_DIA = 0.004`).
3. Abajo de `MIN_ABRIGO = 0.05` la casa queda como **ruina**: abrigo 0, deja de ser el hogar de quien
   fuera, sale de las aldeas (que piden abrigo > 0) y queda publicada en una lista `ruinas` aparte.

Se guarda `abrigo0`, lo que abrigaba cuando era nueva, así que la ruina sabe lo que fue. Las bocas de
caverna y los pozos (`natural: true`) no se arruinan: estaban desde antes que nadie.

La lista `ruinas` va **aparte** y no como un campo más en `refugios` para no cambiarle la forma a lo que
la UI ya dibuja.

---

## 5. Senderos (fase 5)

El paso repetido abre camino y el camino hecho se vuelve a usar. Lo que hace a esta fase la más invasiva
no es la idea sino tres detalles del motor:

### 5.1 `Terreno` congela una copia del costo

`self.costo` es el array de numpy y `self._c = costo.tolist()` es la lista que usa el A*. Cambiar una
celda tiene que escribir en **las dos**, o el A* sigue viendo el mapa viejo para siempre. Para eso existe
`Terreno.cambiar_bioma(x, y, bioma)`, que además guarda de antemano `_factor_terreno` (lo que el costo le
debe a la pendiente y al río, no al bioma) para que cambiar el bioma sea una multiplicación.

### 5.2 Los caminos en curso quedan viejos

Si una celda cambia de costo, quien ya venía con un `h.camino` calculado sigue el trazado anterior. Se le
invalida — **sólo a quien pasa cerca** (300 m), porque invalidarle el camino a todo el mundo sería peor
que el problema.

### 5.3 Nada celda por celda por tick

`pisar(x, y)` sólo incrementa un diccionario disperso. Cada `VUELCA_CADA_MIN = 30` minutos simulados eso
se vuelca al mapa de desgaste, y el desvanecimiento corre una vez por día simulado y **vectorizado**
sobre el array entero.

### Números

| constante | valor | qué es |
|---|---|---|
| `PISADAS_SENDERO` | 60 | pisadas para que una celda se abra como sendero |
| `TOPE_DESGASTE` | 200 | no se cuenta más: una autopista no existe todavía |
| `POR_DIA` | 2 | cuánto se desvanece por día sin tránsito |

El sendero es un **bioma** (`sendero_tierra`, `id_numerico` 103 — todo bioma nuevo va desde 100), con
`velocidad: 0.75` en el JSON, así que se camina más rápido y la UI lo dibuja gratis. Si nadie vuelve a
pasar, el desgaste baja, y debajo de medio umbral la celda **vuelve al bioma que tenía**: el mapa recuerda
lo que la gente usa, no lo que hizo una vez.

El desgaste se guarda como blob comprimido en `estado_dinamico` (igual que la nieve) y no como capa nueva
del mapa: una capa nueva habría pedido tocar `esquema_capas` y migrar todos los mundos viejos.

---

## 6. Lo que queda

- **La UI**: el modal de spawn de habitantes, y el dibujo de ruinas y de senderos. Los datos ya salen
  publicados (`ruinas` en `publico_estructuras()`, y el sendero es un bioma como cualquier otro). Quedó
  sin hacer porque la interfaz la está tocando otra persona en paralelo.
- `calle_empedrada` todavía no cambia la velocidad del terreno: es el enganche natural con esta fase
  (una calle debería ser un sendero que no se cierra).
- El atractor de la fogata está del lado del motor (`atractor_fogata`, usado por las utilidades de
  `motor/objetivos.py`). Pasarlo al puente del cerebro cognitivo como costo de capacidad es trabajo del
  lado del cerebro, que es otro proyecto.

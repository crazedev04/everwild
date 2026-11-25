# Dimensiones y pasajes

Un mundo puede tener más de un mapa. El de siempre es la dimensión **0**; las demás se generan la primera
vez que alguien cruza un pasaje que lleve ahí.

## Agregar una dimensión (sólo JSON)

`datos_base/dimensiones/<lo-que-sea>.json` (o `datos/extra/dimensiones/`):

```json
{"type": "dimension", "id": "cavernas", "nombre": "Cavernas", "generador": "cavernas",
 "tamano": {"ancho": 512, "alto": 512},
 "preset": {"densidad_roca": 0.47, "pasadas": 5, "vecinos_roca": 5,
            "profundidad_m": -400.0, "relieve_m": 70.0, "temperatura_C": 12.0,
            "humedad": 0.78, "quantil_agua": 0.08, "quantil_hongal": 0.30},
 "cielo": {"dia_noche": false, "estaciones": false}}
```

- `generador`: qué algoritmo la dibuja. Hay dos: `continental` (el del mundo) y `cavernas`. **El algoritmo
  es código** —un algoritmo no es contenido—, pero todos sus números son dato.
- `tamano`: si no está, usa el del mundo. `tam_celda_m` también se hereda.
- `cielo`: `dia_noche: false` apaga tormentas y nieve y deja el mapa siempre oscuro; `estaciones: false`
  deja la temperatura quieta (la del mapa, sin verano ni invierno).
- La semilla sale de la del mundo mezclada con el id, así que **el mismo mundo da siempre la misma caverna**
  y dos dimensiones del mismo mundo nunca salen iguales.

Los biomas que use esa dimensión son biomas como cualquier otro (`datos_base/biomas/`), con `id_numerico`
desde 100 para los nuevos. Un bioma con `velocidad: null` es intransitable: así se hace la roca.

## Agregar un pasaje (también sólo JSON)

Una estructura que **lleva a** una dimensión, igual que una fogata **provee** calor:

```json
{"type": "estructura", "id": "pozo_a_las_cavernas", "nombre": "pozo a las cavernas",
 "provee": {"lleva_a": "cavernas"}, "radio_m": 10.0}
```

y la receta que la construye, con `"estructura": {"abrigo": 0.0}` y el id **igual al de la estructura**.
Quien tenga una al alcance de la mano ve la acción `atravesar` entre sus opciones. El motor no sabe qué es
un portal ni qué es una caverna: lee `provee.lleva_a` y mueve a la persona, nada más.

## Bocas naturales (lo que no construyó nadie)

Una estructura puede estar **desde siempre** en el mapa:

```json
{"type": "estructura", "id": "boca_de_caverna", "nombre": "boca de caverna",
 "provee": {"lleva_a": "cavernas"}, "radio_m": 15.0,
 "natural": {"biomas": ["montana", "nieve"], "cada_km2": 0.25, "minimo": 2, "maximo": 24,
             "separacion_m": 1200.0}}
```

`sembrar_estructuras_naturales()` corre una vez por dimensión al cargarla, con un RNG propio derivado de la
semilla (el del mundo es sagrado): el mismo mundo tiene siempre las mismas bocas. Quedan guardadas con el
resto de las estructuras y no se duplican al recargar.

Cada paso recuerda **a dónde da** (`destino` en el refugio). La primera vez que alguien cruza se elige el
punto de llegada y se deja del otro lado una salida de vuelta en ese mismo punto, así bajar y volver te deja
donde estabas.

## Lo que comparte y lo que no

| Es del MUNDO (compartido) | Es del MAPA (propio de cada dimensión) |
|---|---|
| ajustes y módulos | terreno |
| conocimientos y recetas inventadas | fuego y ceniza |
| relaciones y memoria (están en la base) | clima y nieve |
| el cerebro y los vectores de significado | fauna |
| el reloj | estructuras, fogatas y colonias |

Pendiente anotado: los **hitos** quedaron por dimensión, así que algo descubierto abajo se puede volver a
anunciar arriba.

## Dónde está cada cosa

- `motor/mundo.py` — `Mundo`: tiene una `Simulacion` por dimensión, las avanza con el mismo reloj y mueve
  gente de una a otra.
- `motor/generador.py` — `_generar_cavernas` y `algoritmo()`.
- `persistencia/mundo_io.py` — `crear_dimension`, `listar_dimensiones`, capas por dimensión.
- `persistencia/sim_io.py` — `cargar_mundo`, `guardar_mundo_vivo`, `clave_dim`.
- Migración `0009_dimensiones.sql`.

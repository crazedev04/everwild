# Diagnóstico: qué queda para mirar cuando el mundo se cae de madrugada

Hasta ahora, un mundo que se caía a las 4 de la mañana no dejaba nada. Redirigir la salida a un
archivo no alcanza: Python guarda la salida en un buffer y ese buffer se pierde cuando el proceso
muere de golpe, porque una violación de segmento no ejecuta ni una línea más del lado de Python.

Todo esto vive en `src/mundo_vivo/diagnostico.py` y arranca solo, en todos los comandos, desde
`__main__.main()`. No hay nada que prender.

## Dónde queda

Todo en `<carpeta_de_datos>/logs/`:

| archivo | qué tiene |
|---|---|
| `mundo.log` | el registro, con rotación: 8 MB por archivo y 6 archivos viejos |
| `mundo.log.1` … `.6` | los anteriores |
| `caida.log` | lo que escribe `faulthandler`: la traza de una violación de segmento |

El registro se escribe y se vacía en el acto (`logging` hace flush por cada línea), así que lo
último que se anotó ya está en el disco cuando el proceso muere. Y `./mundo.sh` corre Python con
`-u` en `ver`, `correr` y `adelantar`, así que lo que sale por pantalla tampoco se pierde.

## Las tres cosas que deja

**1. El arranque.** Versión de Mundo Vivo, versión y ruta de Python, si el GIL está activo, versión
de numpy, de websockets y si tiene las `speedups` compiladas, plataforma, cerebro elegido, y después
el mundo: nombre, semilla, tamaño del terreno, `tam_celda_m`, dimensiones y cuánta gente hay. Es la
primera pregunta de cualquier autopsia y antes había que adivinarla.

**2. `faulthandler`, siempre.** Es lo único que deja rastro de una violación de segmento, porque lo
escribe el propio manejador de la señal, en C, sin pasar por el intérprete. Está probado de punta a
punta: con un segfault provocado a propósito, en `caida.log` quedan la pila de Python, la pila de C
con los nombres de las bibliotecas y la lista de módulos de extensión cargados; y en `mundo.log`
queda la última línea anterior al choque.

Queda registrado también en `SIGUSR1`, así que a un mundo **colgado** se le puede pedir la foto de
sus hilos sin matarlo:

    kill -USR1 $(pgrep -f "mundo_vivo.*servir")

Dos cosas que conviene saber leer, porque las dos engañan:

- **`_asyncio.so` en la pila de C no acusa a asyncio.** `Task.__step` está implementado ahí, así que
  esas líneas están debajo de *toda* corrutina. Es ruido de fondo, no una pista.
- **La línea «Extension modules: …» no es una lista de sospechosos.** `faulthandler` imprime siempre
  todo lo que había cargado. numpy y `websockets.speedups` aparecen en cualquier traza de este
  proyecto, se hayan portado bien o mal.

**3. Un latido cada 60 segundos reales.** Una línea JSON con: minuto simulado, memoria residente del
proceso, habitantes totales y vivos, refugios, ruinas, fogatas, colonias, animales, especies,
`agotamiento`, eventos y efectos sin volcar, pisadas y senderos abiertos, celdas de camino en curso,
velocidad pedida y velocidad real, clientes conectados, y del cerebro `latencia_s`, `rechazos_llm`,
decisiones y último error. Cada 10 minutos agrega la cuenta de filas de las tablas que crecen
(`eventos`, `decisiones`, `entrenamiento_cerebro`, `memorias`, `dialogos`, `capas`), que es con lo
que se ve si algo crece sin techo.

Toda excepción que llegue arriba sin que nadie la agarre queda escrita con su traza completa, en el
hilo principal, en cualquier hilo y en las tareas de asyncio. Antes, si el bucle del mundo se moría
por una excepción, la tarea quedaba sin que nadie la esperara y **el mundo se detenía en silencio**,
sin dejar nada en ninguna parte.

## Lo que NO cuesta

El latido se cierra con una comparación de `time.monotonic()` y vuelve enseguida si todavía no es la
hora, así que a 20 Hz son 20 comparaciones de reloj por segundo. Las métricas sólo se calculan
cuando de verdad toca escribir, y las sondas son todas `len()`, que es O(1): acá no se recorre
ningún array del mapa. La cuenta de filas usa `max(rowid)`, que también es O(1), y va en una cadencia
aparte, diez veces más lenta.

## La autopsia

    ./mundo.sh autopsia            # el mundo más reciente
    ./mundo.sh autopsia gaia       # uno en particular

Junta en un solo texto el entorno de ahora, el último bloque de `caida.log` (la corrida que se
murió), el final de `mundo.log`, y del último estado guardado: tamaño, `PRAGMA quick_check`, filas
por tabla, el último minuto con decisión guardada, los últimos 12 sucesos y las últimas 12
decisiones con qué cerebro las tomó. Con `--salida informe.txt` lo deja también en un archivo.

Para mirar el registro en vivo mientras corre:

    ./mundo.sh logs

## Para qué se armó esto

Por el crash que nunca se pudo reproducir. El 24 de noviembre de 2026 se intentó durante dos horas:
42 minutos del servidor asíncrono real con cliente conectado, 60 días simulados sin pantalla, 52 días
en proceso, y una corrida entera con `PYTHONMALLOC=debug` (que aborta con un mensaje preciso si una
extensión en C pisa el heap). **Ninguna se cayó.** Lo único que se encontró con certeza fue que el
`.venv` apuntaba a `/usr/bin/python3.14`, un intérprete que no existe en esta máquina; el bueno es el
de linuxbrew. `./mundo.sh` ahora avisa de eso en lugar de caerse a `python3` pelado, que no tiene
numpy.

Del crash que sí ocurrió queda esto en firme: la línea que aparece en la traza
(`motor/fauna.py:187`) es aritmética de floats puros sobre valores que se verificaron float —se
corrieron 10 días simulados comprobando el tipo de cada coordenada de cada animal y de cada
habitante, y no apareció ni un escalar de numpy—. Una línea así no puede fallar por sí misma con el
GIL activo: es el sitio más denso en asignación de memoria del recorrido más caliente, o sea el
candidato estadístico a quedar como testigo inocente de un problema que ocurrió antes y abajo. Así
que la causa está por debajo de Python, y el entorno (Python 3.14.6 con numpy 2.5.5, una combinación
nuevísima) es el sospechoso principal, **sin pruebas todavía**.

Por eso existe este módulo: la próxima vez que se caiga, va a haber con qué mirarlo.

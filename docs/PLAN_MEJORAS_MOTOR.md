# Plan de mejoras del motor (Mundo Vivo)

Documento único de la hoja de ruta del motor de simulación. **Unifica y reemplaza a
`docs/PENDIENTE_MINERALES.md`**, que quedó como nota histórica del diseño del 2026-11-23.

Estado: **las fases 0 a 7 están hechas** (ver `docs/MINERALES.md`, `docs/HOGAR_Y_SENDEROS.md` y las
entradas 0.11.0 y 0.12.0 de `CHANGELOG.md`). Queda abierta la **fase 8** y la mitad de UI de la fase 6
(el modal de spawn y el dibujo de ruinas y senderos, que no se hicieron porque la interfaz la está
tocando otra persona en paralelo). Cada fase dice qué es dato (JSON) y qué es código, porque la regla 6
de `CLAUDE.md` sigue valiendo: el motor no conoce contenido por su nombre.

---

## Hallazgo de campo: por qué hay cero aldeas

Se auditó `datos/mundos/mundo_580927131.db`, un mundo de 1024×1024 con celdas de 5 m que corrió
**523.905 minutos simulados (unos 364 días)** con 8 habitantes y el cerebro híbrido
(`cerebro_llm: true`, `qwen3.5:9b`). Los números, leídos de la base:

- **0 fogatas.**
- **0 refugios construidos.** Los 2 que hay en `estado_dinamico.estructuras` son bocas de caverna
  naturales, con `abrigo: 0.0` y `dueno: null`.
- **Los 8 saben construir**: `choza_de_barro`, `refugio_de_paja` y `muro_de_piedra` figuran en la
  tabla `conoce` para los 8, aprendidas unas de otras (hay 138 eventos de `ensenanza`).
- **Los 8 tienen los materiales**: entre 66 y 70 unidades de `palo`, `paja` y `arcilla` cada uno. La
  choza de barro pide `palo` + `arcilla`. Les sobra para decenas de chozas.
- **6 eventos de `fabricacion` en todo el año.** Contra 478 de `conversacion`, 294 de `podrido` y
  **1034 de `enfermo`**.

### Qué está mal en el diagnóstico de «las aldeas no existen como sistema»

Es al revés. `aldeas()` (`motor/tecnologia.py:583`) existe, agrupa refugios con abrigo por vecindad a
`METROS_ALDEA = 150`, descarta pozos y bocas de caverna, numera estable (guarda `aldea_num` y
`prox_aldea` en la base) y se publica en `publico_estructuras()`. La UI ya las lista y las dibuja.
**Declararía una aldea en el tick siguiente a la segunda choza.**

Lo que sí es cierto es que **las aldeas no se guardan en la base**: se derivan de `refugios` en cada
llamada. Buscarlas en la base da cero siempre, incluso con diez chozas pegadas. Si el cero salió de
una consulta SQL, ese número no prueba nada.

La causa real del cero es anterior y más grave: **nadie construye nada**. Con la receta sabida, los
materiales encima y un año de tiempo, 6 fabricaciones. El ancla de hogar no cambiaría esto: no hay
casa a la que volver. Y el cero de fogatas arrastra el resto de la cadena — sin fuego no se cocina,
de ahí los 294 `podrido` y los 1034 `enfermo`.

### Corrección del diagnóstico: el mundo corrió con el cerebro COGNITIVO, no con el híbrido

Las 3.747 decisiones que quedan en la tabla `decisiones` de ese mundo (minuto 623.644 al 633.278) son
**todas** del motor cognitivo: 3.002 `esperar`, 316 `juntar_para_inventar`, 121 `beber`, 107 `comer`,
88 `explorar`, 86 `dormir`, 18 `hablar`, 9 `ir_al_agua` y **0 `fabricar`**. El cerebro híbrido en ese
mundo nunca decidió nada, así que todo lo que diga «el respaldo del híbrido» en este documento es una
hipótesis sin evidencia de campo.

Dos números del diagnóstico original tampoco prueban lo que parecían:

- **Los «6 eventos de fabricación»** no son 6 fabricaciones. Mara lleva 34 `capa_de_paja` encima y Fiona
  3 vasijas y 2 cestas: los eventos repetidos salen con `importancia: 1` y no todos quedan guardados.
- **El acopio de 66–70 unidades no es acopio sin tope**: `TOPE_LOTE` es un tope **por ítem** (60, hasta
  78 con fuerza alta), no de carga total. Son cuatro topes distintos, uno por material.

Elegir qué hacer es del cerebro, y el cerebro vive en otro proyecto. De este lado queda que el mundo lo
haga **posible y conveniente**: que el horno exista (fase 0), que haya para qué construir (fase 2) y que
convenga construir junto al fuego (fase 4).

### Lo que hay que investigar antes de construir arriba

1. **Por qué el cerebro casi nunca elige `fabricar`.** Hay que mirar el respaldo (`_plan` en
   `motor/tecnologia.py:640`), las utilidades de `motor/objetivos.py` y, en el cerebro cognitivo,
   `_receta_lista` (`agentes/cerebro_cognitivo.py:781`), que devuelve **la primera receta por orden
   alfabético** que la persona pueda hacer. Con `capa_de_paja` sabida, siempre gana la capa y nunca
   se llega a `choza_de_barro`. Hay que elegir por **necesidad**, no por orden de id.
2. **Que construir un refugio no satisface ninguna necesidad.** En el puente cognitivo, la capacidad
   `fabricar` sólo aplica a `HERRAMIENTAS` (línea 286) y la necesidad `CALOR` sólo se puede satisfacer
   con fuego. Falta que levantar una choza sea una forma de resolver el frío, o GOAP no la va a
   planificar nunca.
3. **El acopio sin tope.** 66–70 unidades de cuatro materiales por persona es un síntoma: juntan
   para siempre porque nada consume. Mirar si hay límite de inventario y si la utilidad de juntar baja
   cuando ya hay de sobra.
4. **`ABRIGO_PUESTO` está mal nombrado**: se calcula como `bool(sim.fogata_cerca(h, sim.r_mano))`
   (`agentes/cerebro_cognitivo.py:573`). «Tener abrigo puesto» y «hay fuego al lado» no son lo mismo.

Esto va **antes o en paralelo a la fase 4**, y es la prioridad real junto con la fase 0. Es
exactamente el patrón de siempre: los bugs se ven corriendo un mundo, no en los tests.

---

## Fase 0 — Desbloquear la progresión de calor ✅ HECHA (0.11.0)

Lo de abajo quedó como está, de registro de lo que estaba roto. Lo que se hizo y en qué quedó cada
decisión está en `docs/MINERALES.md`. Dos desvíos de lo que decía el plan, los dos a conciencia:
se renombró **la estructura** (`horno` → `horno_de_barro`) y no la receta, para que los mundos que ya
guardaron ese conocimiento sigan sabiéndolo; y las validaciones de catálogo quedaron en tres reglas
(estructura alcanzable, receta con campo `estructura`, techo de calor), más una cuarta contra ids
duplicados entre archivos de la misma carpeta, que es otro bug silencioso del mismo tipo.


Esto no estaba en el plan original y es el escalón que falta abajo de todo. **Sin esta fase, la
metalurgia es inalcanzable aunque se siembren todas las menas.**

### El problema, verificado

- `datos_base/estructuras/estructuras.json` declara `horno` (1000 °C) y `fragua` (1500 °C), y
  `calor_disponible()` (`motor/tecnologia.py:161`) sabe leerlas.
- La receta `fragua` **no existe**.
- La receta `horno_de_barro` existe pero **no tiene el campo `estructura`**. `catalogos.py:119` le
  completa `resultado` por omisión, así que fabricarla entrega un **ítem de inventario** llamado
  `horno_de_barro` en vez de levantar una estructura en `self.refugios`.
- Encima hay un segundo desajuste: `_accion_fabricar` guarda `tipo: r["id"]`, y `calor_disponible`
  busca `self.estructuras.get(r["tipo"])`. El id de la receta (`horno_de_barro`) no coincide con el
  id de la estructura (`horno`). Ni poniéndole el campo `estructura` andaría.
- Consecuencia: el techo real de calor del mundo es **600 °C**, el de la fogata. Ninguna receta pide
  más de 900 (`ceramica_cocida`), así que nadie lo nota hasta que se intenta fundir algo.

`tests/test_calor.py` no lo detecta porque **inyecta los refugios a mano**
(`s.refugios.append({... "tipo": "horno"})`) y nunca fabrica nada. El `cemento` de la línea 60 es un
diccionario inventado dentro del test, no un dato del catálogo: `cemento` y las calles que
`CLAUDE.md` da por hechas no existen en las 127 recetas.

### Tareas

1. **Datos**: receta `horno` (id igual al de la estructura) con `estructura: {abrigo: 0.0}`,
   ingredientes `arcilla` + `piedra`. Receta `fragua` con `estructura: {abrigo: 0.0}`, ingredientes
   `piedra` + `arcilla_refractaria` + `carbon`, y `requiere: {calor_C: 1000}` para que **nadie haga
   una fragua sin tener antes un horno**. Borrar `horno_de_barro`.
2. **Código**: que el desajuste de ids no pueda volver a pasar. En `catalogos.cargar_recetas`,
   validar que toda receta con `estructura` tenga un id que exista en el registro de estructuras, y
   al revés: toda estructura con `provee.calor_C` debe tener una receta o un `natural` que la ponga en
   el mundo. Error de catálogo al arrancar, no silencio.
3. **Tests**: uno que **fabrique de verdad** (`_aplicar` con la acción `fabricar`) y después mida
   `calor_disponible` y `requisitos_ok`. Nada de `refugios.append` a mano.

Esfuerzo: chico. Es casi todo dato más una validación.

---

## Fase 1 — Vocabulario de propiedades ✅ HECHA (0.11.0)

Desvío: `funde` se apoya en el campo que ya existía (`punto_fusion_C`) en vez del `funde_a_C` nuevo que
proponía la tabla de abajo. Una magnitud física, un solo nombre de campo. Detalle en `docs/MINERALES.md`.


Las propiedades son el idioma con el que los habitantes **inventan**: proponen materiales y una
propiedad, y `condiciones.py` valida contra las magnitudes físicas del material. Hoy hay 19
propiedades y ninguna sirve para la edad de los metales. Son JSON puro, en
`datos_base/propiedades/propiedades.json`, con el formato que ya existe
(`{"requiere": {"alguno"|"todos": [{"path", "op", "valor"}]}}`).

| propiedad | condición | para qué |
|---|---|---|
| `funde` | `material.funde_a_C` existe | fundición: la que destraba las menas |
| `golpea` | densidad ≥ 2500 **y** dureza ≥ 5 | picos, mazas, martillos |
| `clava` | material metálico, resistente y dúctil | clavos, bisagras, vigas unidas |
| `mezcla` | `material.aglomerante` es verdadero | mortero, cemento, revoque |
| `muele` | densidad ≥ 2000 y dureza ≥ 6 | molino, piedra de moler grano |
| `afila` | dureza ≥ 7 | piedra de afilar: mejora herramientas existentes |
| `imanta` | `material.magnetico` es verdadero | brújula y, más adelante, dinamo |
| `aisla` | `conductividad_W_mK` < 1 **y** no conduce electricidad | mango que no quema, cable forrado |

Dos cuidados:

- **Antes de agregar una propiedad hay que revisar qué recetas viejas la cumplen sin querer.** El
  evaluador corre sobre los materiales de la receta, así que una condición floja convierte en válidas
  recetas que no deberían serlo.
- Hay que **inventariar qué campos de material usa cada condición nueva** (`aglomerante`,
  `magnetico`, `ductil`) y agregarlos a los materiales que correspondan. Un `path` que no existe en
  ningún material deja la propiedad inalcanzable y nadie inventa nada con ella.

---

## Fase 2 — Minerales, menas y metalurgia ✅ HECHA (0.11.0)

Desvíos, todos en `docs/MINERALES.md`: las temperaturas de fundición se alinearon con los escalones que
existen (el cobre quedó en 1000, el del horno, no en 1100, que no lo alcanzaba nada), el «río» de la
tabla de abajo no es un bioma y se reemplazó por caverna/roca viva/playa, y las recetas de fundición
piden **etiquetas** (`#mena_de_cobre`, `#carbon_de_fragua`) en vez de ids, que es el enganche de la
fase 3. El aluminio quedó inalcanzable a propósito y la validación C del catálogo lo cuida.


### Objetivo

Romper el estancamiento de la edad de piedra. Los metales (`hierro`, `cobre`, `bronce`, `acero`) ya
existen como materiales con propiedades físicas y hay recetas que los **usan** (cuchillo de acero,
cable de cobre, punta de bronce), pero **ninguno tiene `recoleccion` y ninguna receta los produce**.
El único metal alcanzable hoy es `hierro_del_cielo`, que siembra un meteorito.

### Regla de nombres

Los ids tienen que ser **descriptivos, no técnicos**. Nadie nace sabiendo que la piedra rojiza tiene
hierro adentro, y el prompt le lista los ids de los materiales a la persona: `mena_de_hierro` sería
contarle el final (regla 8 de `CLAUDE.md`). Cada mena lleva `mena: "<metal>"` y `funde_a_C`, que es
lo que lee el motor; el nombre es sólo para los ojos.

### Menas y piedras a sembrar

Todas van en `datos_base/reglas/materiales.json` con `recoleccion: {biomas, prob, cantidad,
capacidad_zona}`. Las de caverna son el motivo por el que existen las bocas de caverna de la v0.9.9:
sin bajar no hay metal, y eso es a propósito.

| id | qué es en realidad | da | funde_a_C | biomas |
|---|---|---|---|---|
| `piedra_rojiza` | hematita | hierro | 1200 | montana, caverna, volcan |
| `piedra_parda` | limonita | hierro (rinde menos) | 1200 | pantano, pradera, caverna |
| `piedra_pesada_oscura` | magnetita (`magnetico`) | hierro | 1250 | montana, caverna |
| `piedra_verdosa` | malaquita | cobre | 1100 | montana, caverna |
| `piedra_azulada` | azurita | cobre | 1100 | caverna, montana |
| `piedra_gris_pesada` | casiterita | estaño | 700 | montana, playa, caverna |
| `piedra_gris_blanda` | galena | plomo | 330 | caverna |
| `piedra_resinosa` | esfalerita | zinc | 420 | caverna |
| `piedra_plateada` | argentita | plata | 960 | caverna |
| `pepita_amarilla` | oro nativo | oro (raro) | 1060 | caverna, río |
| `piedra_opaca_rosada` | bauxita | aluminio (fuera de alcance por ahora) | 2050 | desierto, sabana |
| `piedra_negra` | carbón mineral | leña: arde más y más tiempo que el vegetal | — | caverna, montana |
| `piedra_grasa` | grafito (`conduce`, `aisla` el calor) | — | — | caverna |
| `piedra_blanca_blanda` | caliza (`aglomerante` al calcinarse) | cal | — | montana, playa, caverna |
| `barro_blanco` | caolín | arcilla refractaria | — | caverna, pantano |
| `piedra_cristalina` | cuarzo (dureza 7, `afila`, `chispa`) | — | — | montana, caverna, río |
| `piedra_amarilla_quebradiza` | azufre | — | 115 | volcan, caverna |
| `costra_blanca` | salitre | — | — | desierto, caverna |
| `arena` | — | vidrio | — | playa, desierto |

**Caliza y caolín no son opcionales**: la cal es lo que falta para el cemento y las calles que
`CLAUDE.md` promete, y la arcilla refractaria es lo que hace que una fragua cueste más que una choza.

### Recolección con herramienta

Hoy `disponibles()` (`motor/tecnologia.py:297`) sólo mira el bioma y el agotamiento de la zona. Las
menas duras tienen que pedir un pico: `recoleccion: {requiere: {propiedad: "golpea"}}`, y
`disponibles()` tiene que filtrarlas si la persona no lleva nada con esa propiedad (ya existe
`recetas_con_propiedad()` y se usa igual para la madera y el hacha, en la línea 317). Es código, no
sólo dato, y el plan original lo daba por JSON.

### Recetas de fundición

Con `requiere.calor_C` y `resultado`. La progresión ya existe y no hay que tocar código una vez
cerrada la fase 0: fogata 600, horno 1000, fragua 1500.

| receta | ingredientes | calor | resultado |
|---|---|---|---|
| fundir estaño | piedra gris pesada + carbón | 700 | estaño |
| fundir plomo | piedra gris blanda + carbón | 400 | plomo |
| fundir cobre | piedra verdosa (o azulada) + carbón | 1100 | cobre |
| fundir plata | piedra plateada + carbón | 1000 | plata |
| fundir hierro | piedra rojiza (o parda, o pesada oscura) + carbón | 1200 | hierro |
| bronce | cobre + estaño | 950 | bronce |
| latón | cobre + piedra resinosa | 1000 | latón |
| acero | hierro + carbón | 1400 | acero |
| vidrio | arena + carbón | 1500 | vidrio |
| cal | piedra blanca blanda + carbón | 900 | cal |
| cemento | cal + arena + arcilla | 1450 | cemento |
| calle empedrada | cemento + piedra | — | estructura: camino |

Nadie hace acero sin haber descubierto antes la fragua. El cobre sale con horno; el estaño y el plomo
con fogata buena, así que el bronce es el primer metal alcanzable y eso está bien.

---

## Fase 3 — Minerales desconocidos: materiales que el mundo inventa ✅

Hecha (0.12.0). Implementación en `src/mundo_vivo/motor/minerales.py`, espacio de lo posible en
`datos_base/generacion/minerales_desconocidos.json`. Desvío: los minerales **se sortean siempre de la
semilla** y además se guardan con el mundo; lo guardado manda, así que editar el espacio no le cambia la
geología a una partida empezada. El punto 5 del plan (recetas por propiedad) quedó como tres campos de
datos: etiqueta `#mena_desconocida`, `requiere: {calor_C: "@mena"}` y `resultado: {desde_mena: true}`.


Idea nueva y el rasgo más propio del proyecto: **que una cueva pueda tener un mineral que no está en
ningún JSON**, con propiedades físicas propias, y que de esas propiedades salgan invenciones que ni
el diseñador anticipó. Es la regla 6 llevada hasta el final: ni el motor ni el autor conocen el
contenido.

### Cómo funciona

1. **Al crear el mundo** (una vez por dimensión), se generan unos pocos minerales desconocidos
   —orden de 2 a 6— a partir de la semilla. El generador aleatorio del mundo es sagrado y no se gasta
   acá: RNG propio sembrado con `semilla * primo + dimension`, igual que
   `sembrar_estructuras_naturales` (`motor/tecnologia.py:205`).
2. **El nombre sale de una tabla de sílabas en JSON** (`datos_base/cultura/nombres.json` ya tiene el
   patrón para la gente), más un adjetivo visual: «piedra cerúlea», «veta lechosa». Nunca un nombre
   que delate una propiedad.
3. **Las propiedades se sortean dentro de rangos declarados en datos**, no en código:
   `datos_base/reglas/minerales_desconocidos.json` define el espacio (densidad 1500–9000, dureza
   1–9, `funde_a_C` 300–1600 o nada, probabilidad de `conduce_electricidad`, de `magnetico`, de
   `aglomerante`, de `inflamable`, etc.). Cambiar el espacio de posibles es editar un JSON.
4. **Se persisten en el mundo, no en `datos/extra/`.** `datos/extra` es global y estos minerales son
   de un mundo. Van en la base del mundo (tabla nueva o `meta`) y se inyectan en el registro de esa
   `Simulacion` antes de `_compilar_materiales`. Ninguno de los cargadores tiene caché
   (`Registro.cargar`, `Reglas.cargar` y `catalogos.cargar_recetas` releen de disco), así que hay
   lugar para el punto de inyección; lo que falta es que `catalogos.cargar` acepte un paquete extra
   en vez de tener `dir_extra()` fijo.
5. **Las recetas no se generan.** Esto es lo importante y lo que lo hace barato: el catálogo de
   recetas sigue siendo fijo, pero las recetas de fundición y de herramientas se escriben **contra
   etiquetas y propiedades**, no contra ids. Una receta que pide `#mena` y 1200 °C acepta cualquier
   material con `funde_a_C ≤ 1200`, incluido uno que el mundo inventó esta mañana. El metal que sale
   es el `mena` del mineral, que para un desconocido es… otro material desconocido, con las
   propiedades que le tocaron. De ahí sale solo: si el metal resultante es duro, `corta` y entra en
   las recetas de cuchillo; si es denso y duro, `golpea`; si conduce, `conduce` y sirve para el cable.
6. **El descubrimiento es el de siempre.** `_accion_inventar` (`motor/vida.py`) ya valida una
   combinación contra el evaluador de propiedades y la cruza con el catálogo. No hay que tocar la
   mecánica de descubrimiento: alcanza con que los materiales nuevos existan y que las recetas miren
   propiedades.

### Lo que hay que cuidar

- **Determinismo**: el mismo mundo tiene siempre los mismos minerales desconocidos. Un test que cree
  dos mundos con la misma semilla y compare la lista entera.
- **Que no rompan el equilibrio**: los rangos tienen que estar acotados para que un mineral sorteado
  no sea mejor que el acero sin costar nada. El costo lo da `funde_a_C` alto y la rareza
  (`capacidad_zona` baja, biomas de caverna profunda).
- **El prompt**: sumar 19 menas más unos cuantos desconocidos engorda la lista de materiales que se
  le inyecta a la persona. Está anotado como riesgo desde el principio y acá se vuelve urgente:
  **mandar sólo lo que la persona conoce** (`h.recursos`, que ya se lleva), no el catálogo entero.
- Que no descubran nada y vivan toda una vida en la edad de piedra **no es un bug**.

---

## Fase 4 — Asentamientos, hogar y ruinas ✅

Hecha (0.12.0), menos el dibujo en la UI. Ver `docs/HOGAR_Y_SENDEROS.md`. `h.hogar` se conservó como
coordenada (la usa el prompt) y se **agregó** `h.hogar_rid` al lado, en vez de cambiarle el tipo.


### Lo que ya existe (el plan original lo pedía de nuevo)

- `aldeas()` (`motor/tecnologia.py:583`) agrupa refugios por vecindad con `METROS_ALDEA = 150`,
  descarta pozos y bocas de caverna, numera de forma estable (una aldea sigue siendo «Aldea 3» aunque
  le agreguen chozas) y sale publicada en `publico_estructuras()`.
- La UI ya lista las aldeas (`ui/index.html:277`, `ui/vivo.js:427`), las dibuja en el mapa y hasta
  separa «sin aldea» para la gente que anda junta pero sin casas.
- `h.hogar` existe, pero es **sólo una coordenada** que se setea al construir un refugio con abrigo.

El plan original definía la aldea como «2+ refugios a 30 m de una fogata activa». Eso **contradice**
la definición que ya anda. Hay que quedarse con una: la de vecindad entre casas, que es la que tiene
tests y UI. La fogata entra como atractor, no como requisito.

### El calor de la fogata tiene que caer con la distancia

Hoy el calor es **binario**: `METROS_CALOR_FOGATA = 20.0` (`motor/tecnologia.py:22`), que a 5 m/celda
son 4 celdas de radio. Adentro de esas 4 celdas, `calor_de_estructuras` aplica un `k *= 0.25` plano y
`calor_disponible` devuelve los 600 °C completos; un paso más afuera, cero. Da lo mismo estar encima
de las brasas que a 20 metros, y después se corta de golpe.

Lo que se quiere:

1. **Núcleo fuerte y caída suave.** La celda de la fogata y sus 8 vecinas (el 3×3) reciben el calor
   pleno; de ahí para afuera baja con la distancia hasta apagarse en el radio máximo. En metros, no en
   celdas: el núcleo es `nucleo_m` y la caída llega hasta `radio_m`, los dos en el JSON de la
   estructura, porque **nada se mide en celdas** (a 50 m/celda un 3×3 son 150 metros).
2. **Dos curvas distintas, no una.** Para abrigarse (`calor_de_estructuras`) la caída es gradual:
   estar cerca ayuda un poco. Para fabricar (`calor_disponible`) conviene que sea **escalonada y
   corta**: no se funde metal «casi al lado» de la fragua. La fragua y el horno ya tienen `radio_m:
   6.0`, que a 5 m/celda es poco más de una celda, y eso está bien: hay que trabajar encima.
3. **La fogata calienta las chozas, no sólo a la gente.** Esto no existe: `calor_de_estructuras` sólo
   mira la posición de la persona. Un refugio que cae dentro del alcance de una fogata activa tiene
   que abrigar más que el mismo refugio solo, y eso es lo que hace que convenga construir **alrededor**
   del fuego en vez de desparramado. Es el incentivo físico que convierte un montón de chozas en una
   aldea, sin que el motor tenga que saber qué es una aldea.
4. **Que la caída sea dato y no código.** `provee: {calor_C, nucleo_m, radio_m, caida: "lineal"|"cuadratica"|"escalon"}`
   en la estructura. Agregar una estructura que caliente distinto no debería tocar Python.

Cuidado con el costo: esto se consulta seguido, así que la caída se calcula **con la distancia que ya
se mide** en `fogata_cerca` y `calor_disponible`, no con un barrido de celdas por tick.

### Tareas

1. **Cama propia**: que `h.hogar` apunte al `rid` del refugio, no a una coordenada, y que dormir
   prefiera el refugio propio sobre el mejor refugio cercano (hoy `refugio_cerca` devuelve el de
   mayor abrigo sin mirar el dueño). Y que `dormir` mire **dónde** se duerme: hoy
   `_aplicar` con `tipo == "dormir"` (`motor/simulacion.py:712`) sólo setea `h.accion` y la hora de
   despertarse, sin consultar la posición. Se duerme igual de bien en el barro que en la choza.
2. **Atractor comunitario**: la fogata de la aldea abarata relajarse, charlar y enseñar en las horas
   de poca luz. Es un multiplicador de utilidad en `motor/objetivos.py`, y hay que pasarlo también al
   puente del cerebro cognitivo como costo de capacidad.
3. **Deterioro y ruinas**: las estructuras sin dueño vivo ni tránsito se degradan (baja el `abrigo`)
   hasta quedar como ruina. Se engancha con la fase 5: el desgaste mide el tránsito.
4. **Cadena constructiva**: ya existen choza de ramas (0.3), refugio de paja (0.4), tienda de piel
   (0.5), de cuero (0.55), choza de barro (0.6) y cabaña de troncos (0.7). Lo que falta arriba es la
   casa de piedra con mortero, que depende de la cal de la fase 2.

---

## Fase 5 — Desgaste del terreno y senderos ✅

Hecha (0.12.0). Ver `docs/HOGAR_Y_SENDEROS.md`. Desvío: el desgaste se guarda como blob comprimido en
`estado_dinamico` (igual que la nieve) y **no** como capa nueva del mapa: una capa nueva habría pedido
tocar `esquema_capas` y migrar los mundos viejos.


### Objetivo

Que el paso repetido deje huella y que el A* canalice el tránsito por los caminos ya hechos.

### Lo que el plan original subestimaba

`Terreno.__init__` calcula `costo` una sola vez y **congela una copia** en
`self._c = costo.tolist()` (`motor/navegacion.py:55`), que es la lista que usa el A*. Un sendero
dinámico no es un contador por celda: pide

1. un overlay mutable que actualice **las dos** representaciones (`costo` y `_c`) en la celda que
   cambia;
2. una **capa nueva persistida**. `mundo_io.guardar_capas` ya comprime cada capa con zlib, así que un
   `uint8` de 2048×2048 casi todo en cero no pesa nada;
3. **invalidar los `h.camino` en curso** cuando una celda cambia de costo, o la gente sigue caminos
   calculados contra el mapa viejo;
4. no tocar el costo celda por celda por tick. El desgaste se acumula en un diccionario disperso y se
   volca a la capa cada tantos minutos simulados, igual que hace `_paso_tecnologia`.

### Tareas

1. **Matriz de pisadas** (`desgaste_suelo`), dispersa mientras se acumula.
2. **Umbral de transición** a `sendero_tierra`: bioma nuevo en `datos_base/biomas/`, con su
   `velocidad` mejor que la del pasto. Ojo con `id_numerico`: las tablas de bioma se indexan por ese
   número y hay que respetar los rangos ya usados (naturales 0–99, cavernas 100+).
3. **Regeneración**: sin tránsito durante varias estaciones, el desgaste se desvanece y el sendero
   vuelve a cerrarse.
4. **Dibujo**: el sendero se pinta como cualquier bioma, así que la UI sale casi gratis.

Es la fase más invasiva: toca navegación, persistencia y generación. Va última a propósito.

---

## Fase 6 — Herramientas de administración en la UI ✅

Hecha a medias (0.12.0): el endpoint `POST /api/mundos/{nombre}/habitantes` anda y tiene tests; la UI
(modal de spawn, ruinas, senderos) quedó sin tocar a propósito.


1. **Spawn de habitantes**: `POST /api/mundos/{nombre}/habitantes` **no existe** (los únicos POST
   son crear mundo y exportar). Modal con selector de sexo (masculino, femenino, balance automático),
   genoma equilibrado y ubicación cerca de un asentamiento o en bioma templado.
2. **Visualización de aldeas y caminos**: las aldeas ya están; faltan las ruinas y los senderos, que
   salen de las fases 4 y 5.

---

## Fase 7 — Electricidad (`energia_W`) ✅

Hecha (0.12.0). Salió calcada como se esperaba: `_provisto_en()` toma el campo por parámetro, así que
`calor_disponible` y `energia_disponible` son la misma función.


Hoy `requiere.calor_C` / `provee.calor_C` con `calor_disponible()` es el único escalón físico. La luz
pide el mismo patrón con energía, calcado:

- `provee: {energia_W}` en estructuras (pila, dinamo, molino, turbina) y `requiere: {energia_W}` en
  recetas.
- `energia_disponible(h)` calcado de `calor_disponible(h)`: el **máximo** en radio, no la suma.
- Son unas 20 líneas en `motor/tecnologia.py` y el resto es JSON. **Y la validación de la fase 0 vale
  igual acá**: toda estructura que provea energía necesita una receta que la construya, o se repite
  exactamente el agujero del horno.

Cadena: cobre → cable → dinamo (cobre + hierro + madera) → lámpara (vidrio + cable). Hitos: «el
primer metal», «la primera luz».

---

## Fase 8 — Dinámica reproductiva, celos y cuellos de botella genéticos

### 1. El cuello de botella de sangre (problema actual del mundo)
Hoy `parentesco_cercano(a, b)` en `motor/vida.py` prohíbe tajantemente la procreación entre medio hermanos (`a.padre_id == b.padre_id`).
Cuando un habitante dominante (como Aldo) engendra hijos con todas las mujeres (Rita y Fiona), **toda la siguiente generación (Nico, Mara, Emil, Joaquín) son medio hermanos entre sí**, quedando biológicamente incapacitados de procrear. Si Fausto no procrea o muere, la colonia se extingue por diseño.

**Soluciones a implementar:**
1. **Inmigrantes vía botón de spawn (Fase 6):** Inyecta sangre nueva sin quebrar la coherencia.
2. **Relajar la prohibición ante colapso poblacional:** Si no existen parejas fértiles no emparentadas en el mundo (población < 10), permitir procreación entre medio hermanos (distinta madre) aplicando una penalización de resiliencia o salud genética en el recién nacido, emulando la depresión por endogamia natural en lugar de una extinción forzada por código.

### 2. Compromiso, infidelidad y celos
1. Al aceptar `formar_familia`, asignar `h.pareja_id = o.id` y `o.pareja_id = h.id`.
2. Si un habitante con pareja formalizada engendra o propone familia a un tercero, disparar evento de traición sobre la pareja engañada:
   - `d_afecto = -0.6`, `d_confianza = -0.9`.
   - Generación de recuerdo traumático en memoria episódica.
   - Detonación del impulso de agresión / ruptura de pareja.

---

## Coordinación con el cerebro

El Cognitive Engine (`/home/cracken/Mimundo/Cognitive Engine`, fases 0 a 16 cerradas, 114 tests) se
está mejorando en paralelo. **Nicolás avisa cuando haya un cambio que conectar.** Lo que este plan
toca del lado del puente (`agentes/cerebro_cognitivo.py`) y que hay que revisar cuando eso pase:

- la elección de receta por necesidad en vez de por orden alfabético (`_receta_lista`);
- que construir un refugio satisfaga la necesidad de `CALOR`, no sólo el fuego;
- las capacidades nuevas de la metalurgia (juntar mena con pico, fundir) con sus precondiciones;
- el atractor de la fogata comunitaria como costo de capacidad en las horas de poca luz;
- `ABRIGO_PUESTO`, que hoy se calcula como «hay fuego al lado».

El contrato no cambia: **el motor valida, el cerebro propone**, y el motor cognitivo no importa nada
de Mundo Vivo. Toda la traducción vive en el puente.

---

## Deuda arrastrada

- Los `hitos` quedaron **por dimensión** (deuda de la fase G2): lo descubierto en la caverna se puede
  volver a anunciar en la superficie.
- El cráter de la fase E sigue sin excavar el terreno.
- `src/mundo_vivo/__init__.py` dice `0.9.9` mientras el `CHANGELOG.md` va en 0.10.1 y `CLAUDE.md`
  dice 0.10.0. Hay que elegir una y que el test de versión la fije.

# Minerales, metalurgia y la progresión del calor

Cómo funciona la edad de los metales en Mundo Vivo, qué es dato y qué es código. Implementa las fases 0,
1 y 2 de `docs/PLAN_MEJORAS_MOTOR.md`. Lo que quedó pendiente está al final.

---

## 1. La progresión del calor

Un solo número gobierna toda la cadena técnica: los grados que una persona tiene al alcance de la mano.
`calor_disponible(h)` (`motor/tecnologia.py`) devuelve el **máximo** de lo que haya en radio, no la suma:
dos fogatas no son un horno. De ahí salen tres escalones, y los tres son dato:

| estructura | grados | cómo llega al mundo |
|---|---|---|
| `fogata` | 600 | la crea el motor (`_accion_encender`), marcada `provisto_por: "motor"` |
| `incendio` | 800 | la crea el motor (sistema de fuego) |
| `horno_de_barro` | 1000 | receta `horno_de_barro`: `arcilla` + `piedra` |
| `fragua` | 1500 | receta `fragua`: `piedra` + `arcilla_refractaria` + `#carbon_de_fragua`, y **pide 1000 °C** |

La fragua pide el calor del horno, así que el orden no se puede saltear: fuego → horno → fragua. Una
receta pide calor con `requiere: {calor_C: N}`; `requiere_fuego: true` es la forma vieja y vale 400 °C.

### El agujero que esto cerró

El horno y la fragua vivieron meses **declarados** en `estructuras.json` y leídos por
`calor_disponible()` sin ninguna receta que los levantara. La receta `horno_de_barro` existía pero no
tenía el campo `estructura`, así que fabricarla entregaba un ítem de inventario llamado «horno de barro»;
y encima el id de la receta no coincidía con el de la estructura (`horno`), que es lo que busca
`calor_disponible`. El techo real del mundo era 600 °C y la metalurgia era inalcanzable. El test no lo
cazaba porque **inyectaba los refugios a mano** (`refugios.append({... "tipo": "horno"})`): verificaba el
lector y nunca el escritor.

Ahora hay tres validaciones al cargar el catálogo (`catalogos._validar_estructuras`), y fallan al
arrancar el mundo, no tres horas después:

- **A.** Toda estructura que `provee` algo tiene que poder llegar al mundo: una receta **con el mismo
  id**, un bloque `natural`, o `provisto_por: "motor"`.
- **B.** Si existe la receta con ese id, tiene que traer el campo `estructura`.
- **C.** Ninguna receta puede pedir más calor del que da la estructura más caliente que se pueda
  construir. Esto es el techo del mundo convertido en test.

Y una cuarta, de otro orden pero del mismo tipo de bug silencioso: **dos archivos de la misma carpeta de
catálogo no pueden declarar el mismo id.** Ganaba el último alfabético y la otra entrada no existía para
nadie.

---

## 2. Las piedras

Todas en `datos_base/reglas/minerales.json`, con `recoleccion: {biomas, prob, cantidad,
capacidad_zona}` como cualquier material.

**Los ids son descriptivos, no técnicos.** La lista de materiales se le muestra a la persona y nadie nace
sabiendo que la piedra rojiza tiene hierro adentro: `mena_de_hierro` sería contarle el final (regla 8 de
`CLAUDE.md`). Cada mena lleva `mena: "<metal>"` y `punto_fusion_C`, que es lo que lee el motor; el nombre
es sólo para los ojos. Hay un test que falla si un id o un nombre delata su contenido.

| id | qué es en realidad | da | funde a | biomas |
|---|---|---|---|---|
| `piedra_rojiza` | hematita | hierro | 1200 | montaña, caverna, roca viva, volcán |
| `piedra_parda` | limonita | hierro (rinde menos) | 1200 | pantano, pradera, caverna |
| `piedra_pesada_oscura` | magnetita (`magnetico`) | hierro | 1250 | montaña, caverna, roca viva |
| `piedra_verdosa` | malaquita | cobre | 1000 | montaña, caverna, roca viva |
| `piedra_azulada` | azurita | cobre | 1000 | caverna, roca viva, montaña |
| `piedra_gris_pesada` | casiterita | estaño | 700 | montaña, playa, caverna |
| `piedra_gris_blanda` | galena | plomo | 330 | caverna, roca viva |
| `piedra_resinosa` | esfalerita | zinc | 420 | caverna, roca viva |
| `piedra_plateada` | argentita | plata | 960 | caverna, roca viva |
| `pepita_amarilla` | oro nativo | oro (raro) | 1060 | caverna, roca viva, playa |
| `piedra_opaca_rosada` | bauxita | aluminio (**fuera de alcance**) | 2050 | desierto, sabana |
| `piedra_negra` | carbón mineral | leña: 420 min/unidad | — | caverna, roca viva, montaña |
| `piedra_grasa` | grafito (`conduce`) | — | — | caverna, roca viva |
| `piedra_blanca_blanda` | caliza | cal | — | montaña, playa, caverna, roca viva |
| `barro_blanco` | caolín | arcilla refractaria | — | caverna, roca viva, pantano |
| `piedra_cristalina` | cuarzo (dureza 7, `afila`, `chispa`) | — | — | montaña, caverna, roca viva |
| `piedra_amarilla_quebradiza` | azufre | — | 115 | volcán, caverna, roca viva |
| `costra_blanca` | salitre (`conservante`) | — | — | desierto, caverna, roca viva |
| `arena` | — | vidrio | — | playa, desierto |

El aluminio es **inalcanzable a propósito**: 2050 °C no los da nada que se pueda construir. La piedra se
junta igual, y el día que exista un escalón de calor más alto se funde sin tocar código. Si alguien le
escribe la receta antes, la validación C del catálogo no deja arrancar el mundo.

Casi todas piden bajar: ése es el motivo por el que existen las bocas de caverna.

### La roca dura pide herramienta

`recoleccion: {requiere: {propiedad: "golpea"}}` en el material. `disponibles()` filtra ese material si
la persona no lleva encima nada que cumpla esa propiedad (el mismo trato que ya tenían la madera y el
hacha). El mensaje del motor lo dice en palabras: «hay piedra rojiza acá, pero está metida en la roca:
con las manos no sale». Es dato: una mena nueva declara su herramienta sola.

El primer pico es el de piedra (`palo` + `piedra` + `#ligadura`), que ya existía en el catálogo con la
propiedad equivocada (`perfora`) y ahora es `golpea`.

---

## 3. La fundición

Las recetas están en `datos_base/recetas/metalurgia.json` y **miran etiquetas, no ids**: una receta que
pide `#mena_de_cobre` acepta cualquier piedra que la etiqueta incluya. Eso es lo que va a dejar entrar
sola a la fase 3 (los minerales que el mundo invente).

| receta | ingredientes | calor | sale |
|---|---|---|---|
| plomo fundido | `#mena_de_plomo` + `#carbon_de_fragua` | 400 | plomo |
| zinc fundido | `#mena_de_zinc` + carbón | 420 | zinc |
| estaño fundido | `#mena_de_estano` + carbón | 700 | estaño |
| plata fundida | `#mena_de_plata` + carbón | 960 | plata |
| cal | caliza + carbón | 900 | cal (×2) |
| bronce | cobre + estaño | 950 | bronce (×2) |
| cobre fundido | `#mena_de_cobre` + carbón | 1000 | cobre |
| latón | cobre + piedra resinosa | 1000 | latón (×2) |
| oro fundido | `#mena_de_oro` + carbón | 1060 | oro |
| hierro fundido | `#mena_de_hierro` + carbón | 1200 | hierro |
| acero | hierro + carbón | 1400 | acero |
| cemento | cal + arena + arcilla | 1450 | cemento (×2) |
| vidrio | arena + carbón | 1500 | vidrio |

Con una fogata se saca plomo y zinc; con el horno, cobre, estaño, plata y **bronce**, que es el primer
metal que sirve de verdad; el hierro y el acero sólo con fragua. La edad del bronce y la del hierro
quedan separadas por una estructura, no por un `if`.

### Lo que sale de ahí

`mortero` (cal + arena) y `cemento` abren la `casa_de_piedra` (abrigo 0.8, el techo de la cadena
constructiva: choza de ramas 0.3 → refugio de paja 0.4 → tienda de piel 0.5 → de cuero 0.55 → choza de
barro 0.6 → cabaña de troncos 0.7 → casa de piedra 0.8) y la `calle_empedrada`, las dos cosas que
`CLAUDE.md` daba por hechas y no existían.

---

## 4. El vocabulario de propiedades

Las propiedades son el idioma con el que los habitantes **inventan**: proponen materiales y una
propiedad, y el evaluador declarativo (`condiciones.py`) la valida contra las magnitudes físicas del
material. Con la fase 1 son 27; éstas son las 8 nuevas:

| propiedad | se cumple si algún material… | para qué |
|---|---|---|
| `funde` | tiene `punto_fusion_C` | la fundición: lo que destraba las menas |
| `golpea` | densidad ≥ 2500 **y** dureza ≥ 5 | picos, mazas, martillos |
| `clava` | es `ductil` **y** `resistente` | clavos, vigas unidas |
| `mezcla` | es `aglomerante` | mortero, cemento, revoque |
| `muele` | densidad ≥ 2000 **y** dureza ≥ 6 | piedra de moler |
| `afila` | dureza ≥ 7 | piedra de afilar |
| `imanta` | es `magnetico` | la aguja imantada y, más adelante, la dinamo |
| `aisla` | conductividad < 1 **y** no conduce electricidad | mangos que no queman, cable forrado |

Dos decisiones que conviene no redescubrir:

- **`funde` usa `punto_fusion_C`, no un `funde_a_C` nuevo.** El plan original proponía un campo nuevo,
  pero esa magnitud ya existía en los materiales. Una magnitud física, un solo nombre de campo.
- Las condiciones con dos requisitos (`golpea`, `clava`, `muele`, `aisla`) piden que **un mismo
  material** cumpla los dos, no uno cada uno. Un palo liviano más una piedra blanda no son una maza.

Campos de material que hubo que agregar para que el vocabulario sea alcanzable: `ductil` (hierro, acero,
cobre, bronce, y los metales nuevos), `aglomerante` (arcilla, cal, mortero, cemento, barro blanco) y
`magnetico` (la piedra pesada y oscura). Hay dos tests que lo cuidan: uno exige que **cada** propiedad la
cumpla algún material del mundo (un `path` que nadie tiene deja la propiedad inalcanzable y nadie inventa
nada con ella) y otro que **cada** propiedad la use alguna receta (una propiedad sin receta es
decoración). Un tercero corre el evaluador sobre las 151 recetas del catálogo con sus materiales reales,
que es la red contra el otro riesgo: una condición floja vuelve válido lo que no debería.

---

## 5. Lo que queda pendiente

- **Fase 3**: minerales que el mundo genera solo, con propiedades sorteadas de la semilla. Las etiquetas
  de mena y las recetas por propiedad ya están puestas pensando en eso.
- `afila` todavía no mejora nada: la propiedad y la receta existen, pero no hay una mecánica de filo.
- `calle_empedrada` es por ahora una estructura sin efecto: la velocidad del terreno llega con la fase 5
  (desgaste y senderos).
- `aguja_imantada` no orienta a nadie todavía; es el enganche de la brújula y, más adelante, de la
  dinamo de la fase 7.

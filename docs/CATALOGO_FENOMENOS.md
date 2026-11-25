# Catálogo de fenómenos del mundo

Lista de lo que puede pasar en el mundo, agrupado por sistema. Para cada uno: qué regla general lo produce (nada es un guion),
cómo se simplifica y en qué fase entra. Estado: ✅ ya funciona · 🔧 parcial · ⬜ pendiente.

**Principio:** pocas reglas universales y consistentes (como en *Breath of the Wild*), con propiedades por material en JSON
(`datos_base/reglas/`), en lugar de miles de casos especiales. Lo nuevo se agrega como una receta JSON, no como código.
Los combos que no se pensaron salen solos de combinar reglas; los que no están balanceados se descubren mirando el registro de eventos.

## 1. Gravedad y suelo
| Fenómeno | Regla que lo produce | Estado |
|---|---|---|
| Caída por pendiente empinada al caminar | probabilidad según pendiente; daño según pendiente | ✅ |
| Rocas que ruedan cuesta abajo (derrumbe) | llueve/tormenta sobre pendiente ≥ umbral; la roca sigue el vecino más bajo; golpea a quien esté en el camino | ✅ |
| Caída de objetos / frutos / árboles | gravedad sobre objetos con soporte; viento y fuego rompen el soporte | ⬜ Fase 4 |
| Avalancha de nieve, deslizamiento de barro | derrumbe + humedad alta o nieve | ⬜ |
| Hundimiento en pantano, arenas movedizas | material del suelo + peso | ⬜ |
| Caída desde cornisa, daño por altura | diferencia de altura × peso | 🔧 (pendiente) |

## 2. Clima y atmósfera
| Fenómeno | Regla | Estado |
|---|---|---|
| Día y noche, estaciones (4 × 30 días) | reloj del mundo | ✅ |
| Tormenta (se forma según estación y humedad, viaja con el viento) | probabilidad por estación; se mueve | ✅ |
| Lluvia (apaga fuego, moja) | intensidad por tormenta | ✅ (apaga fuego) |
| Rayos (pueden herir o prender fuego) | frecuencia ∝ intensidad² | ✅ |
| Viento (empuja el fuego) | dirección fija por mundo, por ahora | 🔧 |
| Tornado, granizo, nieve, niebla, ola de calor/frío, sequía, inundación por lluvia | extensiones del sistema de tormentas | ⬜ Fase 4 |
| Temperatura corporal (frío/calor) | temperatura de la celda vs. abrigo | ⬜ Fase 3 |

## 3. Geología
Terremoto, erupción de volcán (lava que fluye cuesta abajo, ceniza), cuevas que se derrumban, deslizamientos, formación de cuevas
con agua subterránea. Todo ⬜ (Fase 4–5). La lava ya existe como rasgo del mapa y es intransitable.

## 4. Agua
Ríos que se vadean (más caudal = más lento), lagos, océano y cascadas ✅ (generación y navegación).
Pendientes: crecidas, inundaciones tras lluvia fuerte, congelamiento, corrientes que arrastran, ahogamiento, pesca ⬜.

## 5. Fuego y calor
| Fenómeno | Regla | Estado |
|---|---|---|
| Incendio que se propaga (más rápido a favor del viento, con vegetación seca) | autómata celular con combustible por bioma y estación | ✅ |
| El agua y el suelo pelado frenan el fuego; la lluvia lo apaga | agua = sin combustible; lluvia reduce propagación | ✅ |
| Ceniza y rebrote lento | combustible quemado vuelve despacio | ✅ |
| Quemaduras a personas; huida del fuego | daño por intensidad | ✅ |
| Fuego prendido por rayo / por el observador | origen registrado | ✅ |
| Calor que ablanda o funde metales según dureza y masa | `reglas.py`: `calentar()` y `metal_se_ablanda` (fogata 800 °C no ablanda hierro; fragua 1100 °C sí) | ✅ motor de reglas · ⬜ conectado a objetos del mundo |
| Cocinar, humo, carbón, hornos, fraguas | recetas de material + temperatura | ⬜ Fase 4 |
| Combustión de edificios | material "inflamable" en construcciones | ⬜ |

## 6. Electricidad y materiales
Descarga que recorre conductores (`rayo_en_conductor`) ✅ en reglas; pendiente conectarla al juego.
Pendiente: circuitos, pararrayos, imanes, baterías (tecnología tardía).

## 7. Cuerpo y salud
Sed, sueño/energía, salud ✅. Hambre, comida, venenos y hongos (probado en `pruebas_cerebro`), heridas/fracturas ("Juancito se quebró un dedo"),
infecciones, enfermedades, hipotermia, envejecimiento y muerte natural ⬜ (Fase 3).

## 8. Ecología
Plantas que crecen y se agotan, frutos de estación, animales (herbívoros, depredadores, manadas), caza, domesticación, plagas, migraciones ⬜ (siguiente fase grande).

## 9. Sociedad (la parte que hace el cerebro, no el motor)
Conversaciones registradas ✅, amistades y rencores (relaciones que cambian según lo que se dicen) ✅, enseñanza ✅, invención de conocimientos validada contra materiales ✅,
parejas e hijos por decisión de cada uno (sin escenas explícitas) con herencia del genoma ✅. Pendiente: comercio (dos gallinas por un árbol), cultura, construcción de refugios,
ciudades, caminos, vehículos, objetos fabricables y tecnología ⬜ (Fases 4–6).

## Cómo se agrega un fenómeno nuevo
1. Si es una propiedad de material: sumar una entrada `material` en un JSON (puede heredar con `copy-from`).
2. Si es una reacción: sumar una entrada `reaccion` con `cuando` (condiciones) y `efectos`.
3. Se valida al cargar (el mundo no arranca con una regla rota) y la huella de las reglas se puede guardar junto al mundo.
4. Si necesita una física nueva (por ejemplo, propagar líquidos), se programa una vez como *sistema* y desde ahí sus variantes son datos.


## Fauna y emociones (Fase 4 parcial)
Fauna terrestre/acuática/aérea con depredadores y presas ✅, caza ✅, ataques ✅, monta (con rienda descubierta) ✅, botín en inventario ✅, recetas existentes/inventadas ✅,
emociones simples ✅. Pendiente ⬜: hambre y plantas, fabricar objetos, domesticar/criar, comercio.

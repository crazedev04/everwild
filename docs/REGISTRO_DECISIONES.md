# Registro de decisiones y cambios

Regla: no cambiar silenciosamente decisiones acordadas ni borrar datos de una partida.

## 2026-11-22 — Ajustes al plan v0.1 (revisión previa a construir)

Estado: **propuestos por Claude, aceptados por el usuario** ("si conviene lo que vos me decís").
Impacto en datos guardados: ninguno (todavía no existe ninguna partida).

| # | Decisión | Motivo | Fase |
|---|---|---|---|
| 1 | Agregar Fase 0.5: probar el cerebro (LLM) antes de construir el mundo | El mayor riesgo es si un modelo de 4B decide con coherencia y JSON válido | 0.5 |
| 2 | El agente devuelve intenciones de alto nivel; el motor las descompone en pasos | Evita llamar al LLM por cada tick; permite velocidades altas | 3 |
| 3 | Materiales con propiedades (dureza, peso, inflamabilidad...) desde la Fase 2 | Sin propiedades, "inventar" es solo buscar en una tabla | 2 |
| 4 | Memoria recuperada con embeddings (modelo chico en Ollama) + recencia + importancia | El plan pedía "relevancia" sin definir cómo | 4 |
| 5 | Mapa en chunks (ej. 64x64) comprimidos en SQLite con WAL; entidades/eventos/memorias en tablas | Una fila por tile es lenta | 0-1 |
| 6 | Determinismo: mundo 100% reproducible; partida reproducible guardando cada decisión del LLM como evento | El LLM no es determinista | 0-3 |
| 7 | Modo headless (sin interfaz) con métricas desde el inicio | Los criterios de éxito solo se miden corriendo años simulados | 3 |
| 8 | Fase 1 recortada: superficie, relieve, agua, ríos, biomas en 256x256 o 512x512; cuevas/subsuelo como capa posterior | Reducir riesgo y llegar antes a algo visible | 1 |
| 9 | Definir conocimiento inicial (instintos sí, recetas no) y calibrar dificultad | Un LLM ya "sabe" qué es el fuego | 3 |
| 10 | Desactivar el modo "thinking" de Qwen en decisiones; salida con JSON Schema | Ahorra tokens y latencia | 0.5 |

## Entorno del usuario (referencia)

- Ollama 0.40.17 en Linux
- Modelos instalados: qwen3.5:4b, qwen2.5:7b, gemma4:31b
- GPU: RTX 4060 (VRAM por confirmar)

## 2026-11-22 — Visión ampliada acordada con el usuario

Impacto en datos guardados: ninguno (todavía no existe partida). Fases: 1 a 7.

- Mundo realista por simulación de temperatura, humedad y altura (biomas reales); pocas especies al inicio, con roles ecológicos reales.
- Más terreno: volcanes y lava (peligro), cascadas (salen del relieve), agua subterránea en cuevas.
- Combate y defensa: animales con fuerza, velocidad y salud; los habitantes pueden huir, pelear o usar objetos; el motor resuelve.
- Preferencias y forma de pensar cambiantes, guardadas con historia (cuándo y por qué cambian). Relaciones, orientación e hijos son decisión de cada habitante; el motor solo resuelve lo biológico. Sin contenido explícito.
- Pendiente (Fase 6): con 4 fundadores hay riesgo de extinción y endogamia; decidir si se arranca con más habitantes.
- Comercio no enseñado: el motor ofrece propiedad, dar/recibir, proponer/responder y memoria de trato; el resto debe surgir.
- Render por código, sin sprites: casillas pintadas desde datos y figuras simples. Posiciones guardadas como (x, y, z) continuas para permitir 3D después con los mismos personajes.
- Panel web aparte con registro de eventos, filtros, fichas e historia; los eventos se guardan estructurados (quién, qué, dónde, cuándo, causa, resultado).
- Eventos emergen de sistemas generales (cuerpo, física, ecología, sociedad) más una tabla ampliable de sucesos aleatorios.
- Rendimiento: el límite real es tiempo de GPU, no costo. El LLM se consulta solo cuando hay un cambio relevante.

## 2026-11-22 — Resultados de la prueba del cerebro (qwen3.5:4b, modo normal, 48 h)

JSON válido 100%, latencia mediana 1,7 s, 53 tok/s, 3,1 GB de GPU, 15,1% de acciones rechazadas, 4/4 sobrevivientes, 4,4 h simuladas por minuto real. La prueba fue demasiado fácil (1 caso urgente): no sirve para comparar modelos. Se agregó el modo `--dificil`.

## 2026-11-22 — Implementación de Fase 0 y primera versión de Fase 1

Impacto en datos guardados: define el formato inicial (esquema v1, generador 1.0.0). Desde ahora cambios de esquema = migración nueva.

- Persistencia: SQLite con WAL; mapa en chunks de 64x64 comprimidos (una fila por capa y chunk); migraciones en `persistencia/migraciones/` (nunca se editan las ya publicadas); backup automático antes de migrar; una migración fallida hace rollback; una base de versión futura no se toca.
- Mundos: cada mundo es un archivo propio en `datos/mundos/`; generar o importar nunca pisa un archivo existente. Se guarda huella (SHA-256) del mapa para verificar integridad al importar.
- Memoria privada: solo se accede con `MemoriaPrivada(habitante_id)`; no existe API que mezcle memorias de varios habitantes.
- Eventos: tabla estructurada (quién, qué, dónde, cuándo, causa, resultado, importancia, origen autónomo/usuario/sistema). Las intervenciones del usuario deben usar origen `usuario`.
- Posiciones de habitantes y eventos: x, y, z continuas en metros (celda = 50 m), preparado para 3D.
- Generador 1.0.0: ruido determinista propio (no depende de numpy.random), relieve, nivel del mar, volcanes sobre cumbres, temperatura por latitud y altura, lluvia por viento húmedo con sombra de montañas, hidrología con priority-flood (ríos, lagos, cascadas), 15 biomas. Si se cambia el algoritmo: subir `VERSION_GENERADOR`.
- Limitación conocida: sin cuevas ni subsuelo todavía (Fase 1 recortada, ver ajuste 8). Pantanos muy escasos; parámetros de clima a afinar mirando más semillas.
- Interfaz: web (FastAPI + HTML/JavaScript con canvas), sin sprites, solo lee datos del servidor.

## 2026-11-22 — Comparación de modelos y niveles de la prueba del cerebro

Resultados en nivel difícil (48 h, semilla 42): qwen3.5:4b atendió lo urgente 40% (19% acciones imposibles, 0 bucles, vivieron 12-40 h); qwen2.5:7b 14% (30%, 4 bucles, 7-10 h), y más lento (2,1 vs 4,8 h simuladas/min). **Decisión: modelo base = qwen3.5:4b.** qwen2.5:7b descartado; gemma4:31b no probado (no entra en 8 GB de VRAM).
El nivel difícil resultó casi imposible incluso para un jugador programado con conocimiento total: sirve para estresar, no para medir. Se agregó `--nivel medio` (comida limitada pero suficiente, hongos venenosos) y métricas de aprendizaje por experiencia (reincidencias con hongos).
Aclaración de diseño: la escasez es una perilla de la prueba, no una regla del mundo. En el mundo real la comida surge de la ecología; lo que deben descubrir es qué es comestible, venenoso o cazable.

## 2026-11-22 — El mundo es modificable por los habitantes (decisión de diseño)

Impacto en datos guardados: ninguno hoy; implica una migración futura (0002+) con capas de modificaciones. Fases: 5 y 7.

- El mapa generado (terreno base) no se edita: lo que construyen o cambian los habitantes (edificios, caminos, cultivos, excavaciones, canales, vehículos) se guarda en capas separadas y con historial (quién, cuándo). Así actualizar el generador no destruye lo construido, y se puede ver el mundo "original" frente al transformado.
- La tecnología avanza por reglas físicas componibles (materiales con propiedades, herramientas, energía, tiempo), no por un árbol fijo.
- El conocimiento colectivo (enseñanza, registros escritos, bibliotecas) es el mecanismo para que el grupo supere la capacidad de un solo habitante.
- Escalado: cuando haya muchos habitantes, no todos consultan al modelo en cada paso; se prioriza a quien está en una situación relevante.

## 2026-11-22 — Informe nivel medio (qwen3.5:4b, prompt v1) y cambios derivados

Resultado: JSON válido 100%, 15,8% rechazadas, 3 de 4 vivos a las 48 h (Dante murió de hambre a las 32 h), 4 intoxicaciones con hongos y **0 reincidencias** (aprenden de la experiencia), "atiende lo urgente" 32% de 68 casos.
Lectura: la métrica solo contaba la necesidad más urgente según un orden fijo (sed > hambre > cansancio); eso subestima decisiones válidas. Se corrigió: cuenta como correcta si la acción atiende CUALQUIER necesidad urgente, y el informe lista los primeros 10 fallos con el pensamiento del habitante. Los resultados nuevos no son comparables con los anteriores.
- Prompt v2 (por defecto; v1 sigue disponible con `--prompt v1`): señales del cuerpo con palabras, lista de acciones posibles en el lugar actual (percepción de lo que puede hacer, no órdenes), pensamiento de máximo 15 palabras, y sin lenguaje técnico ("JSON") dentro del mundo.

## 2026-11-22 — Genoma, vida social y vigilancia

Impacto en datos guardados: **migración 0002** (columnas madre_id, padre_id, genoma en habitantes; tablas dialogos y relaciones). Una base existente se migra con backup automático. Fases: 3, 4 y 6.

- **Genoma** (`agentes/genoma.py`): 7 rasgos de temperamento (audacia, sociabilidad, curiosidad, agresividad, cautela, empatía, resiliencia) + red neuronal de 82 pesos (8 señales -> 6 ocultas -> 4 impulsos: huir, pelear, buscar recursos, descansar). Herencia por cruce y mutación, determinista con semilla. Lo heredable es solo el genoma: los recuerdos y lo aprendido no se heredan.
- **Limitaciones conocidas del genoma:** hoy los pesos son aleatorios y el texto de temperamento no está acoplado a la red; todavía no influyen en el comportamiento. El acoplamiento (rasgos que sesgan impulsos y reciben el modelo de lenguaje como sensación) se diseña en la Fase 3. La evolución real necesita presión de selección (amenazas, escasez) y muchas generaciones; con 4 fundadores será lenta y habrá que vigilar la endogamia (`distancia`).
- **Diálogos:** registro completo en `dialogos` (auditoría del observador; los habitantes no lo leen). Quien habla y quien escucha reciben su recuerdo privado. Evento `conversacion` visible en el panel.
- **Relaciones:** afecto y confianza dirigidos, privados de cada habitante, persistentes. Un cambio fuerte deja un recuerdo importante, así una pelea puede mantenerse o reconciliarse con el tiempo.
- **Vigilancia de sospecha de simulación:** detección por patrones sobre lo que dicen; genera el evento `sospecha_simulacion` (origen sistema, importancia 4) solo para el observador. Puede dar falsos positivos.
- **Principio de seguridad y naturalidad:** los habitantes no tienen herramientas para ejecutar código ni acceder a la red o al sistema: solo emiten acciones de un menú que el motor valida. Ningún prompt de habitante menciona simulación, modelos, servidores ni archivos, y no se induce ni refuerza esa idea. Que lo sospechen es un resultado posible; actuar fuera del menú no.


## Mundo vivo: motor, tiempo real y reglas en JSON
- **Qué:** reloj (año de 4 estaciones × 30 días, empieza día 1 08:00), terreno transitable con A*, incendios (autómata celular), clima (tormentas, lluvia, rayos), gravedad (caídas y derrumbes), habitantes con necesidades y un *Cerebro* intercambiable. Hoy el cerebro es una **demostración con reglas simples** (solo para ver el mundo moverse); el real (LLM + genoma) se conecta por la misma interfaz `decidir(sim, habitante)`.
- **Persistencia:** migración 0003 (`estado_dinamico`). Se guardan habitantes, reloj, fuego, ceniza, combustible y tormentas; los eventos van a la tabla `eventos`. Los habitantes iniciales (4) nacen junto a agua dulce, en tierra llana y conectada.
- **Tiempo real:** WebSocket `/ws/{mundo}`. El mundo solo corre mientras alguien lo mira (guarda cada ~10 s y al desconectar). Velocidades 0/1/5/20/100/500 min simulados por segundo; si la PC no llega, se recorta el avance en lugar de congelar la pantalla (presupuesto de 35 ms por vuelta).
- **Visor:** habitantes que se mueven (suavizado), zoom, día/noche con luz de fuego y de personas, llamas, ceniza, tormentas, rayos, derrumbes, ficha del habitante solo para el observador, botón "Prender fuego" (queda como origen `usuario`).
- **Reglas en JSON:** materiales y reacciones declarativos (`datos_base/reglas/`), con `copy-from`, validación al cargar y carpeta de usuario que agrega o reemplaza por id. Investigado: Noita (tabla de reacciones), Dwarf Fortress (propiedades de material), Cataclysm DDA (JSON `type`/`id`/`copy-from`), Breath of the Wild (pocas reglas universales). Calor con capacitancia concentrada: una fogata no ablanda hierro, una fragua sí. **Pendiente:** conectar estas reglas a objetos reales del mundo.
- **Calibración honesta:** en 20 días con 4 habitantes de demostración los resultados varían mucho según la semilla (de 0 a 4 sobrevivientes); el fuego sigue siendo la principal causa de muerte. Los parámetros (`K_PROPAGACION`, probabilidad de ignición por rayo, tasa de caídas) están al principio de `fuego.py` y `simulacion.py` para ajustarlos.

### Corrección del fuego (informe de 25 días del usuario)
Un único rayo (día 10) siguió ardiendo hasta el día 24 y quemó ~1/3 del mapa; murieron 4 de 4 (2 por fuego, 2 por sed con el agua cortada). Causa: el fuego no tenía ningún freno natural. Ahora: (1) 38% de las celdas son parches sin combustible (roca, suelo pelado, vegetación verde) que cortan el avance, (2) la humedad reduce el combustible, (3) el avance se debilita con la edad del incendio (rocío, humedad del suelo), (4) de noche avanza más lento. Resultado medido: incendios de 0,1 a 1,5 días que queman 12–3.200 celdas, y 4 de 4 sobrevivientes en 20 días en 3 semillas. Test de regresión incluido. Pendiente de diseño: fogatas hechas por los habitantes (se descubren, no se programan).

## Todo conectado: cerebro híbrido, vida social, familia y conocimientos
- **Cerebro híbrido** (`agentes/mente.py`): (1) reflejos —huir del fuego, beber, dormir— cuyos umbrales salen de la **red heredada (genoma)**; (2) modelo de lenguaje por Ollama **en un hilo aparte** (el mundo no se congela), que decide intenciones: explorar, ir al agua, hablar, acercarse, proponer una familia, responder, enseñar, inventar; (3) si el modelo falla o no está, siguen con reglas simples y reintenta solo a los 2 minutos. El cerebro solo propone; el motor valida.
- **Tiempo y modelo:** mientras alguien está pensando, el mundo no pasa de `velocidad_max_pensando` (3 min por segundo real). Así los habitantes no se quedan "quietos" sin querer cuando se elige una velocidad alta.
- **Social** (`motor/vida.py`, `persistencia/sim_io.py`): al cruzarse (≤ 8 celdas) se conocen; pueden hablarse a ≤ 6 celdas; cada charla queda en `dialogos` (solo observador) y como recuerdo privado de cada lado; el afecto cambia según la "impresión" que cada uno declara (no se programa que se lleven bien). Quien recibe un mensaje deja lo que hacía para atenderlo.
- **Familia:** propuesta + respuesta libre (consentimiento de ambos), adultos de distinto sexo, mujer no embarazada; gestación de 60 días del mundo, hijo con genoma heredado de los dos (cruce + mutación, `heredar`), nombre propio, recuerdos NO heredados. Los niños se mueven con reflejos y siguen a su madre hasta los 12 años del mundo; vejez desde los 60. Sin escenas explícitas: solo "decidieron formar una familia" y "nació X".
- **Conocimientos descubiertos:** un habitante **propone** una receta (materiales + propiedad) y el motor la **valida** contra `materiales.json`: la balsa de madera flota (densidad < agua), la de hierro no; propiedades que todavía no se pueden comprobar se rechazan ("no se puede comprobar en este mundo"). Lo válido queda en `conocimientos` con quién lo inventó, se difunde solo por enseñanza (`conoce`) y puede perderse si muere el único que lo sabe. **Limitación honesta:** hoy es conocimiento, todavía no hay objetos fabricables.
- **Interruptores** (tabla `ajustes`, panel del visor): percepción social, conversación, memoria, reflejos con genoma, modelo de lenguaje, reproducción, conocimientos, más modelo y parámetros. Se guardan en el mundo.
- **Para dejarlo corriendo:** `./iniciar.sh correr NOMBRE --velocidad 20` (sin pantalla; guarda cada 10 s y al cerrar, también con kill).
- **Probado con un Ollama simulado** (tests/ollama_falso.py): conocerse, charlar con recuerdos y relaciones, familia y nacimiento con genoma heredado, invención validada y enseñanza, apagar el modelo, modelo caído. **No probado todavía con el modelo real**: el prompt puede necesitar ajustes (ver "decisiones rechazadas" en el panel).
- **Migración 0004** (ajustes, conocimientos, conoce). Los mundos anteriores se migran solos con backup.

## Fauna, emociones y recetas (investigación + decisiones)
**Qué dice la investigación y qué hicimos con eso**
- *Project Sid (Altera, 2024)*: los agentes se rompen cuando lo que dicen y lo que hacen salen de llamadas distintas, y una alucinación chica se acumula (alguien dice "ya comí" y deja de comer). Lo que funcionó: reflejos rápidos separados del razonamiento lento, un único "cuello de botella" que decide y todo lo demás obedece, y comparar lo esperado con lo que realmente pasó. → Acá una sola respuesta del modelo trae habla y acción juntas; el motor valida y le devuelve el RESULTADO REAL ("Se te escapó el ciervo"), nunca lo que el modelo dijo que pasó; los reflejos (huir del fuego/depredadores, beber, dormir) no pasan por el modelo.
- *Sentipolis (2026)*: un estado emocional continuo con decaimiento (vida media ~120 min) y etiquetas en lenguaje natural mejoró la continuidad y el comportamiento social; pero con modelos chicos las pistas emocionales explícitas pueden hacerlos sobreactuar. → Cuatro canales (miedo, tristeza, alegría, enojo) con vida media de 2 horas del mundo, que se muestran como UNA palabra ("muy asustada"), sin números, y el temperamento heredado modula cuánto afecta cada cosa (resiliencia, empatía, audacia, agresividad, sociabilidad). Se puede apagar con un interruptor.
- *Trampas de simular con modelos de lenguaje* (fluidez que parece verdad, exceso de amabilidad, todos parecidos): se juzga por los registros y no por lo bien que hablan (tabla `decisiones` con prompt, respuesta, resultado y si el motor la aceptó), el modelo es solo una pieza dentro de un motor inspeccionable, y hay reflejos y reglas contra las que comparar.
- *RimWorld / Dwarf Fortress*: elenco chico y legible, eventos que se cruzan (el fuego espanta y mata animales), nunca eliminar de golpe (si una especie casi se extingue llega algún ejemplar, como el "narrador" de RimWorld), relaciones con peso. → Fauna acotada (tope de 450 y 40 por especie), arranque amable (sin grandes depredadores a menos de 45 celdas del inicio) y fuego conectado con la fauna.
**Fauna** (`datos_base/fauna/especies.json`, `motor/fauna.py`): 42 especies (terrestres, acuáticas, voladoras; mamíferos, aves, reptiles, anfibios, peces, insectos, arácnidos, moluscos, crustáceos). Cada una define biomas, dieta, presas, peligro, veneno, velocidad, vida, botín (carne, cuero, hueso, lana, plumas, miel, fibra) y si se puede montar. Herbívoros comen del suelo (no si se quemó), carnívoros cazan (más saciedad con presas más grandes), mueren de vejez, hambre, fuego o cazados, y se reproducen si hay lugar. Prueba de 40 días: casi todas las especies se mantienen. Las personas pueden `cazar` (mejor con lanza/arco, que se descubren), ser atacadas, huir (reflejo) y `montar` (solo si descubrieron la rienda).
**Recetas** (`datos_base/recetas/recetas.json`): catálogo de 17 recetas existentes (balsa, fogata, lanza, abrigo, cuerda, rienda, arco, carne asada...), todas comprobables con las reglas de materiales. Cuando un habitante prueba una idea que coincide (mismos materiales y misma propiedad) cuenta como "descubrió cómo hacer X" (origen catálogo, toma su nombre); si es válida pero distinta, queda como "inventada" con su creador. El visor tiene un panel con las tres listas. **Para agregar más:** archivos en `datos/extra/recetas/*.json` y `datos/extra/fauna/*.json` (mismo id reemplaza; error claro si algo está mal).
**Pendiente (a propósito):** hambre y plantas comestibles (sin eso no hay motivo real para cazar y activarlo sin plantas haría morir a todos de hambre), fabricar objetos de verdad (hoy lo botín y lo que se aprende son conocimiento + inventario), domesticar y criar animales, comercio.

## Análisis del mundo exportado (día 54, qwen3.5:9b) y correcciones
Resultado: 4/4 vivos, 808 charlas, 1602 decisiones (98,6 % aceptadas por el motor), 3 s por decisión. Pero: cero inventos, cero enseñanzas, cero propuestas de familia, y los cuatro se quedaron junto al agua 54 días (beber, dormir, esperar, charlar). Charlas casi siempre sobre el agua y el miedo; hablaban con personas dormidas; la confianza llegó a 1,0 en pocos días.
Causas y arreglos: (1) no había nada que los empujara a salir de la rutina → "inquietud": se registra la última novedad (zona nueva, caza, idea, enseñanza) y, si pasan 1,5 días sin ninguna, el prompt lo dice; con el aburrimiento crece el radio de exploración; (2) charlas vacías → no se le habla a quien duerme, hay 2 h de espera entre charlas a la misma persona (salvo para responder) y se rechaza repetir casi lo mismo; (3) confianza/afecto con rendimientos decrecientes.

## Por qué el mundo iba a ~22× con 100× elegido y el procesador libre
Medido: el motor solo hace ~900 minutos del mundo por segundo con fauna (~2900 sin ella) en un solo núcleo, o sea que NO era el procesador. El freno es el modelo: mientras alguien piensa el mundo se limita a `velocidad_max_pensando` (3×), y con 4 personas casi siempre hay alguien pensando; encima las consultas iban de a una (4 × 3 s = 12 s por ronda), así que la GPU, no la CPU, era el cuello de botella. El aviso decía "tu PC llega a" y confundía.
Cambios: el aviso ahora dice "esperando al modelo"; el tope mientras piensan se elige en el panel (3×, 10×, 30×, 100×, sin tope); "consultas a la vez" (1–4; requiere OLLAMA_NUM_PARALLEL); largo máximo de respuesta configurable (220 tokens por defecto, antes 400).

## Rediseño del visor (UI)
- Sistema visual compartido en `ui/estilo.css` (tinta azul nocturna, ámbar para lo importante, tipografía serif en números y títulos).
- Reloj siempre completo y fijo arriba de la columna lateral: "Día N · hora · Estación · Año N · día X de 120", con dial sol/luna y botones de velocidad/pausa debajo.
- Columna lateral en pestañas (Gente, Mundo, Recetas, Animales, Ajustes); la elegida se recuerda.
- Fin del "salto" en refresco: la lista de gente se actualiza por elementos (no se reconstruye), la ficha escribe solo si cambió el contenido, conserva el scroll y recuerda qué secciones (`<details>`) estaban abiertas.
- Página de Eventos: línea de tiempo agrupada por día, filtros por tipo en chips, búsqueda, importancia por defecto ≥3, plegado automático de tandas de sucesos triviales repetidos (derrumbes, charlas).
- El feed en vivo del mapa omite lo de importancia 1 (queda en Eventos).

## Análisis del mundo de un año (qwen3.5:9b, paralelo 4, sin tope) y arreglos
Datos del export: 361 días del mundo (3 años + 1 de 120 días: **el año del mundo dura 120 días**), 4 habitantes vivos, 762 decisiones (≈1,7 por día entre todos),
504 «explorar», 0 «inventar», 1 «caza», 1 «proponer_hijo», 37 charlas (casi todas en los primeros 4 días y en tandas de 5 días sueltas), 0 recetas.
Causas:
1. **El mundo corría más rápido que sus mentes.** Latencia mediana 6,4 s × 500 min/s = 3200 min: cada persona decidía una vez cada ~2,2 días del mundo y
   el resto del tiempo esperaba «pensando». Con eso no hay conversación, ni reencuentro, ni caza, ni invento posibles. → Tope de velocidad **automático**
   (`velocidad_max_pensando = 0`): 75 min del mundo / latencia del modelo (≈12× con 9b a 6 s, ≈35× con 2 s). Sigue pudiendo fijarse a mano.
2. **Se dispersaron y no tenían cómo volver a encontrarse.** El «aburrimiento» empujaba a explorar cada vez más lejos (hasta 45 celdas por salto) y hablar/ir_hacia
   exige ver a la otra persona (30 celdas). → Recuerdan **dónde vieron por última vez** a cada persona (`visto`, persistido), el prompt las lista con rumbo y
   distancia («No ves a Bruno; la última vez estaba hacia el este, a unas 80 celdas»), hay acción **`buscar`**, exploración acotada (≤30 por salto y ≤60 celdas
   del grupo) y, tras 2 días solo, el cerebro de reglas prefiere buscar a alguien.
3. **Nadie tenía motivo para inventar.** El prompt solo ofrecía «inventar» con el ejemplo de la balsa y nada en su vida lo pedía. → `_ideas`: tras ~18 h sin
   probar una idea, el prompt señala una **necesidad real** (te hirió un animal → algo con filo; junto al agua → algo que flote; de noche → fuego; sin abrigo; sin
   forma de atar) y una pista de materiales **sin dar el nombre**; «inventar» pasa a ser la primera opción. Probar (aunque falle) reinicia el reloj.
4. Textos rotos: «Fuiste hacia explora.» (479 veces), «Te fue atacado por araña» (memoria personal), derrumbes sin testigos como 194 eventos (ahora solo se anotan si
   alguien los vio o los sufrió; el efecto en el mapa sigue).
Cosas que NO son bug: los años de 120 días (decisión de diseño para que las estaciones se noten), la edad (28 a los 3 años: parte de 25).
Pendiente de comprobar con el modelo real: cuántos «inventar»/«buscar» elige de verdad qwen3.5:9b con estas pistas.

## Sistema de recetas: qué copiar y qué no (a implementar en una versión próxima)
Pregunta del usuario: ¿cuál es el mejor gestor de recetas (¿el de Microsoft?). Respuesta: no hay uno «de Microsoft» como producto; lo más probable es que se refiera a **Minecraft** (de Microsoft),
cuyas recetas son archivos de datos (JSON) con ingredientes, patrón y resultado, y **etiquetas** (tags: «cualquier madera»). Es un buen modelo de *formato*, pero Minecraft tiene recetas fijas.
Lo nuestro es distinto: las recetas se *descubren o inventan* a partir de propiedades de los materiales. Lo que conviene combinar:
- **Minecraft**: recetas y etiquetas como datos editables (ya lo hacemos en `datos_base/recetas` y `datos/extra/recetas`); sumar etiquetas de material («madera», «piedra», «cuero») para que una receta no dependa de un material exacto.
- **Dwarf Fortress / Noita**: propiedades físicas en cada material (densidad, punto de ignición, flexible, aislante); la receta se *comprueba* contra ellas (ya lo hacemos para flota/corta/arde/conduce/abriga/ata/alimenta).
- **RimWorld / Cataclysm DDA**: receta = ingredientes + herramienta/calidad requerida + tiempo + habilidad + resultado (objeto o capacidad). Es lo que falta: hoy una receta solo da un *saber*, no un objeto fabricado ni tarda tiempo.
Plan: ampliar el formato (campos `herramienta`, `tiempo_min`, `resultado`, `etiquetas`), mostrar en el panel qué se puede hacer con cada material y qué necesita cada receta.

## Fase N — recuerdos por significado: qué se decidió y por qué
- **El trabajo de fondo no escribe en sqlite.** El hilo de embeddings devuelve vectores en memoria y el hilo del mundo los guarda en `volcar_eventos`. Una conexión sqlite se usa desde un solo hilo; cualquier otra cosa es una carrera esperando a pasar en un mundo que corre horas.
- **El vector de la situación nunca se espera.** `Semantica.vector()` contesta sólo si ya está calculado; si falta, lo encola y esa decisión sale por palabras. Frenar una decisión por un embedding sería repetir el error que ya costó caro (el mundo corriendo más rápido que las mentes).
- **Relevancia = máximo entre coseno y palabras**, no reemplazo. Así la fase sólo puede sumar y no hay forma de que un modelo de embeddings flojo empeore lo que ya andaba.
- **Se guardan normalizados** para que el coseno sea un producto punto, y **el cero se corre a 0,25**: dos frases cualesquiera del mismo idioma dan coseno alto aunque no tengan nada que ver.
- **Un vector vacío se guarda igual** (blob de largo 0) como marca de «ya se intentó»: si no, los mismos recuerdos se vuelven a pedir en cada vuelta para siempre.
- **El módulo viene apagado**, al revés que todos los demás salvo `hambre`: sin `ollama pull nomic-embed-text` sólo serviría para llenar el panel de errores.
- **Cambiar de modelo de embeddings no rompe nada**: el largo del vector cambia, `coseno()` devuelve None y se cae a palabras.
- Se agregó `memoria.sin_embedding()`, la única consulta que cruza habitantes. Es para el índice, no para una mente: el texto va al modelo de embeddings y vuelve como vector; nadie ve el recuerdo de otro.

## Fase G2 — dimensiones: qué se decidió y por qué
- **Una `Simulacion` por dimensión, no una simulación con `dimension` adentro.** Contados: 71 usos de `self.terreno`, 63 de `self.fuego`, 29 de `self.fauna`, 27 de clima/nieve. Meter la dimensión como parámetro era tocar ~190 lugares y dejar 190 chances de que alguien camine por el mapa equivocado. Con una simulación por mapa, cada una sigue siendo exactamente lo que ya era y probada como ya estaba.
- **Lo del mundo se comparte por referencia; lo del mapa, no.** `Simulacion.compartir_con()` hace que ajustes, conocimientos, relaciones, el cerebro y los vectores de significado sean EL MISMO objeto. Terreno, fuego, clima, fauna, nieve y estructuras son propios: son otro mapa.
- **Un solo reloj.** Todas las dimensiones avanzan el mismo `dt`. Si cada una llevara el suyo, bajar y volver movería el tiempo de arriba.
- **El mapa del otro lado se genera al primer cruce**, no al crear el mundo: un mundo que nunca abre un portal no paga ni un segundo ni un byte. 512×512 tarda 0,3 s, así que se puede hacer en el acto sin pantalla de carga.
- **`capas` había que rehacerla**: era `WITHOUT ROWID` con clave `(capa, cx, cy)`. Meter la dimensión en la clave pide tabla nueva + copia + rename; es lo único no aditivo de la migración.
- **`estado_dinamico` NO se migra**: la dimensión 0 conserva sus claves (`fuego`, `nieve`, `estructuras`...) y las nuevas usan `d<N>:`. Así un mundo que venía andando no pierde nada.
- **Los `hitos` quedan por dimensión** (no se comparten). Es deuda anotada: si alguien descubre el fuego abajo, arriba puede volver a anunciarse. Compartirlos pide que `importar_estructuras` deje de reasignar el set.
- **El generador de cavernas es código; sus números, datos.** Mismo contrato que el resto: `datos_base/dimensiones/cavernas.json` elige el algoritmo (`generador`) y todos sus umbrales (`preset`). Los tres biomas nuevos llevan `id_numerico` desde 100, como quedó fijado en la fase B.
- **Una sola cueva conectada**: la región hueca más grande se calcula por dilatación con numpy (no BFS en Python, que tarda segundos en 512²). Sin eso, un portal podía dejar a alguien encerrado en una burbuja de roca para siempre.

## Bocas de caverna (v0.9.9)
- **Las bocas son estructuras, no terreno.** El generador dibuja el suelo; un agujero que lleva a otro mapa es una estructura con `provee.lleva_a`. Ponerlo en las capas habría pedido una capa nueva y una migración; como estructura se siembra al cargar la dimensión y se guarda con el resto.
- **Se siembran al cargar, no al crear el mundo**, y es idempotente (`naturales_sembradas`). Así un mundo que ya existía también las tiene sin migración ninguna.
- **RNG propio.** `random.Random(semilla * 2246822519 + dimension + id)`: el generador del mundo es sagrado y gastarlo acá rompería el determinismo de la semilla.
- **Cada paso recuerda a dónde da** (`destino` en el refugio) y al primer cruce deja una salida de vuelta en el punto de llegada. Sin eso, volver te dejaba en cualquier parte y el viaje de ida no tenía vuelta posible.

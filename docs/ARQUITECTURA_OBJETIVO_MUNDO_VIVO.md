# Arquitectura objetivo — Evolución integral de Mundo Vivo

**Estado:** propuesta de análisis, diseño y planificación. **Solo lectura:** no se modificó código, mundos, bases de datos, configuraciones ni simulaciones para escribir este documento. Nada de lo que sigue está implementado salvo lo que se señala explícitamente como "verificado en código".  
**Referencia externa:** BiomeSimulator (https://github.com/andrenepomuceno/BiomeSimulator).  
**Documento de partida:** `docs/AUDITORIA_EVOLUCION_MUNDO_VIVO_BIOMESIMULATOR.md` (auditoría verificada del estado local) y `docs/PLAN_MEJORAS_MOTOR.md` (fases 0–7 hechas, fase 8 abierta).

---

## 1. Diagnóstico de arquitectura actual (verificado en código)

### 1.1 Qué existe y funciona hoy

| Área | Módulos | Estado verificado |
|------|---------|-------------------|
| Motor y ciclo temporal | `motor/simulacion.py` (`Simulacion` con mixins: `vida`, `ecologia`, `frio`, `conservacion`, `alimentacion`, `atributos`, `atencion`, `fenomenos_datos`, `objetivos`, `psique`, `propagacion`, `tecnologia`), `motor/mundo.py` | Una `Simulacion` por dimensión; bucle 20 Hz, estado 10 Hz; reloj día/estación/año (`motor/reloj.py`, 1 año = 120 días). |
| Generación procedural | `generador/pipeline.py`, `motor/generador.py` (shim de compatibilidad) | 4 etapas: relieve → clima → hidrología/erosión → biomas/capas. Determinista por semilla + `VERSION_GENERADOR`. Resultado se guarda, no la receta. |
| Terreno, biomas, agua, navegación | `motor/biomas.py`, `motor/navegacion.py` (A*, `costo`/`_c` en dos representaciones), `motor/senderos.py` | Escala métrica (`tam_celda_m`, `Simulacion.celdas()`); A* con presupuesto de nodos y caché de fracasos/rutas/incompletos. |
| Flora, fauna, ecología | `motor/ecologia.py`, `motor/fauna.py` (grilla espacial, tope 450 animales), `motor/propagacion.py` (colonias), `motor/minerales.py` | Fauna con dieta, hambre, vejez, caza, mutaciones por datos. Ecología desde la mirada del habitante (ver, cazar, montar, emociones 4 canales). |
| Habitantes y cognición | `agentes/mente.py` (`CerebroHibrido`: reflejos con genoma + LLM Ollama + respaldo), `agentes/cerebro_cognitivo.py` (puente a Cognitive Engine, GOAP + Utility AI), `motor/atencion.py` (LOD cognitivo 3 niveles), `motor/psique.py`, `motor/objetivos.py`, `motor/atributos.py` | Motor valida, cerebro propone. Frontera CCA preservada: `brain_id={world_uid}:d{dim}:h{id}`, `cerebros_<world_uid>.db`. |
| Persistencia | `persistencia/sim_io.py`, `persistencia/mundo_io.py`, `persistencia/db.py`, `persistencia/memoria.py`, `persistencia/social.py` | SQLite WAL, `world_uid` persistente, estado JSON por habitante (sin migración al agregar campos), aislamiento cognitivo verificado (10 tests). |
| API y comunicación | `api/servidor.py` (FastAPI, REST), `api/vivo.py` (WebSocket `/ws/<mundo>`), `api/presentador.py` | Solo lectura del motor salvo creación de mundos; capas comprimidas (deflate); estado vivo por WS; detalle bajo demanda por REST. |
| Interfaz | `ui/index.html`, `ui/vivo.js`, `ui/mapa.js`, `ui/sprites.js`, `ui/estilo.css` | Vanilla JS + Canvas, sprites dibujados en código, sin caché (Ctrl+Shift+R). Mapa, eventos, ficha de habitante, lista de habitantes. |

### 1.2 Problemas verificados (hechos, no conjeturas)

1. **Datos obsoletos al cambiar de dimensión.** `ui/vivo.js:104-119` (`armarDimensiones`) recarga capas del mapa y actualiza el `<select>`, pero no limpia `V.habs`, `V.eventos`, `V.efectos` ni refresca paneles (`recetas`, `fauna`, `familias`, `era`, lista `habitantes`). Solo `alAbrir` (cambio de mundo completo) resetea esos estados. Resultado: mapa nuevo, habitantes/eventos/paneles de la dimensión anterior hasta recarga manual. (Audit §4, confirmado en código.)
2. **No hay minimapa, ni inspector de habitante robusto, ni reporte histórico de tendencias.** La UI es "panel + mapa + eventos + ficha". BiomeSimulator sí tiene inspector de entidades, minimapa y reporte de tendencias. (Audit §2, §4.)
3. **A* degenera en Dijkstra a 5 m/celda.** Hecho medido en `docs/OPTIMIZACION.md`: en 2048² a 5 m, el costo mediano de celda es 21,6 y la heurística del A* vale 1 por celda → subestima 21,6×; 2 de cada 3 búsquedas fallan y agotan el presupuesto de 120 000 nodos (0,7 s cada una). Causa raíz: `ALTURA_MAX_M` / `PROFUNDIDAD_MAX_M` fijas a 3000 m sin mirar `tam_celda_m`, mientras los rasgos del ruido están en celdas → pendiente mediana 58°, 67 % del mapa intransitable. Caché de fracasos ya alivia el síntoma, no la causa.
4. **No hay ciclo de vida vegetal completo.** Existe `ecologia`/`conservacion`/`propagacion`, pero no germinación → crecimiento → fruto → muerte como etapas con `effectiveAge` (agua × terreno × estación × hacinamiento) como dato. BiomeSimulator lo tiene maduro. (Audit §2, §3.)
5. **No hay estaciones con efecto sobre vegetación ni visión por período.** Existe `reloj.py` (estaciones, día/noche, sequedad para fuego) pero no inciden en crecimiento vegetal ni en modificador de visión. (Audit §2.)
6. **Fauna sin cadena completa.** Depredador/presa existe a nivel de código (`depredadores_de`, caza), pero no carroñeros, cadáveres ni descomposición como sistema explícito. (Audit §3.)
7. **UI sin vista general del mundo, ni estadísticas de población/ecosistema, ni controles de observación/diagnóstico.** (Audit §4.)
8. **Falta instrumentación de movimiento/objetivos.** Solo hay `decisiones` (acción/ok/resultado) y `position_json`; falta ranking de utilidades, estado del plan GOAP, objetivo elegido por tick y habitante. (Audit §5.)

### 1.3 Qué NO es problema (y no hay que tocar)

- La separación motor/UI/CCA ya existe y está validada: la UI solo lee; el motor valida y ejecuta; el cerebro propone. No se reemplaza CCA por IA de reglas.
- El aislamiento cognitivo entre mundos (`world_uid`, bases `cerebros_<world_uid>.db`) está verificado.
- El generador actual es determinista y válido para semillas existentes; no hay que reescribirlo, solo evolucionarlo por etapas con validaciones.

---

## 2. Arquitectura objetivo propuesta

### 2.1 Principios de diseño

1. **Evolución modular, no reescritura.** Se conserva `Simulacion` + mixins, el generador por etapas, la persistencia JSON por habitante y la frontera CCA. Se separan responsabilidades, se consolidan duplicados y se agregan capas donde falta.
2. **El motor no conoce contenido por nombre.** Materiales, biomas, recetas, fenómenos, minerales, especies siguen siendo JSON (`datos_base/` + `datos/extra/`); el tipo lo decide el campo `type`. (Regla 6 de `CLAUDE.md`, ya vigente.)
3. **Un mundo = una identidad persistente.** `world_uid` aísla mundos, bases cognitivas y estados. Las dimensiones son mapas adicionales del mismo mundo, mismo reloj.
4. **UI observa, nunca simula.** La interfaz lee estado vivo (WS) y detalle bajo demanda (REST); no duplica lógica de simulación ni cognición.
5. **CCA fuera del motor.** Mundo Vivo conoce el entorno y ejecuta acciones; CCA procesa percepción, memoria, razonamiento, aprendizaje y decisiones; el adaptador conecta ambos. No se mueve cognición al motor.
6. **Dato vs código claro.** Un algoritmo nuevo (generador, navegador) es código; sus umbrales, clasificaciones y contenido son dato. Cambiar el algoritmo sube `VERSION_GENERADOR`; cambiar los números es JSON.

### 2.2 Capas y responsabilidades (diálogo de módulos)

```
                     UI (observación)
              index.html / vivo.js / mapa.js
                        WS / REST
                          |
       +------------------+------------------+
       |  API (servidor.py / vivo.py)        |
       |  - solo lectura del motor salvo     |
       |    creación de mundos               |
       +------------------+------------------+
                          |
       +------------------v------------------+
       |  MOTOR DE SIMULACIÓN                |
       |  Simulacion (mixins por sistema)    |
       |  - mundo/terreno/biomas/navegación  |
       |  - ecología / fauna / clima         |
       |  - habitantes (estado, acción)      |
       |  - persistencia (sim_io)            |
       +------------------+------------------+
                          |
       +------------------v------------------+
       |  ADAPTADOR CCA (cerebro_cognitivo)  |
       |  - percepción → CCA                 |
       |  - decisión CCA → motor (_aplicar)  |
       |  - GOAP + Utility AI (otro proyecto)|
       +------------------------------------+
```

**Responsabilidades por módulo:**

| Módulo (capa) | Responsabilidad | Origen / evolución |
|---|---|---|
| `motor/mundo.py` | Orquesta dimensiones, mismo reloj, pasajes entre mapas (`Mundo`) | Existe; se conserva |
| `motor/simulacion.py` + mixins | Tick, físicas, vitales, fuego, clima, fauna, acciones del habitante | Existe; se consolida (ver 2.3) |
| `motor/navegacion.py` | Terreno transitable, A*, costo por bioma/pendiente/río, caché de rutas | Existe; se evoluciona (heurística acorde a escala) |
| `generador/pipeline.py` | Generación por etapas con validaciones entre etapas | Existe; se expande (etapa islas, cuevas, validación de habitabilidad) |
| `motor/ecologia.py` | Ciclo vegetal, interacción planta/terreno/clima, comida en suelo | Existe; se añade ciclo de vida completo |
| `motor/fauna.py` | Alimentación, reproducción, depredador/presa/carroñero, cadáveres | Existe; se extiende |
| `motor/reloj.py` | Estación, día/noche, luz, sequedad | Existe; se usa en ecología |
| `motor/atencion.py` | LOD cognitivo (3 niveles) | Existe; se conserva |
| `persistencia/sim_io.py`, `mundo_io.py` | Guardado/carga, `world_uid`, migraciones aditivas | Existe; estrategia de migración (ver 8) |
| `api/servidor.py`, `api/vivo.py` | WS estado vivo, REST detalle, creación en segundo plano | Existe; contrato estable (ver 6) |
| `ui/*` | Vistas de observación, sin reglas del mundo | Existe; rediseño integral (ver 7) |
| `agentes/mente.py`, `cerebro_cognitivo.py` | Puente CCA: percepción, decisiones, respaldo | Existe; frontera preservada (ver 6) |
| `datos_base/` + `datos/extra/` | Contenido: biomas, recetas, especies, fenómenos, minerales | Existe; formato JSON sin cambio |

### 2.3 Módulos a separar, consolidar o evolucionar

| Acción | Módulos | Razón |
|---|---|---|
| **Consolidar** | `motor/generador.py` → eliminar shim; todo vive en `generador/pipeline.py` | El shim solo reexporta; añade una capa innecesaria |
| **Consolidar** | `motor/conservacion.py`, `motor/alimentacion.py`, `motor/ecologia.py` → unificar bajo una capa "ecología y recursos" con fronteras claras | Hoy comparten conceptos (comida, pudrirse, inventario) dispersos en 3 mixins |
| **Separar** | Nueva capa `motor/geografia.py` (relieve, cuencas, costas, humedales, cuevas) desprendida del generador | La generación y las consultas geográficas (¿es esta celda costa? ¿drenaje?) merecen una API estable independiente del pipeline |
| **Evolucionar** | `motor/navegacion.py` → heurística de A* escalada a `tam_celda_m`, nodos de jerarquía (opcional, ver 4) | Problema verificado de A* a 5 m/celda |
| **Evolucionar** | `motor/ecologia.py` → ciclo de vida vegetal con `effectiveAge` como dato | Falta verificada (BiomeSimulator lo tiene) |
| **Crear** | `motor/clima_estacional.py` o extender `reloj.py` → estaciones con efecto sobre vegetación y visión | Falta verificada |
| **Crear** | `ui/observador.js` (minimapa, inspector, cronología, herramientas de diagnóstico) | Falta verificada |
| **Crear** | Contrato WS/REST versionado (`/api/v1/...`) | Para evitar datos obsoletos al cambiar mundo/dimensión |

### 2.4 Flujo del tick (no cambia el contrato motor/cerebro)

```
tick(dt)
├── físicas rápidas (movimiento, vitales, sed/hambre/energía, fuego sobre celda)
│   └── cada habitante: _vida → _actualizar → decaer emociones
├── sistemas amortizados (clima, nieve, fuego, fauna, senderos, colonias, fenómenos)
│   └── fauna con grilla espacial; LOD cognitivo (atención)
├── decisiones: cerebro propone → Simulacion._aplicar valida y ejecuta
│   └── CCA recibe percepción; devuelve acción; motor aplica o rechaza
└── volcado a persistencia (eventos, estado dinámico) y WS al visor (estado vivo)
```

No se adoptan workers ni subprocesos sin justificación de beneficio medido (ver 4).

---

## 3. Pipeline de generación por etapas (propuesta)

El generador actual ya es por etapas. La evolución lo formaliza como **pipeline con etapas, dependencias y validaciones entre etapas**, de modo que el mundo resultante sea geográficamente coherente, no solo visualmente variado.

### 3.1 Etapas y dependencias

```
Entrada: semilla, ancho, alto, tam_celda_m, preset (datos_base/dimensiones/*.json)
         └─ preset = dato; algoritmo = código (cambiarlo sube VERSION_GENERADOR)

Etapa 1 — Relieve y masas terrestres
  continua, cresta, continente, nivel del mar, volcanes
  → elevación (m), máscara océano/tierra, volcanes
  Depende de: semilla, preset (quantil_mar, volcanes)
  Validación V1: hay al menos una masa terrestre contigua de tamaño mínimo

Etapa 2 — Hidrología (priority-flood + erosión)
  relleno de depresiones, dirección de flujo, ríos, lagos, cascadas, erosión hidráulica/térmica
  → llenado, destino de flujo, acumulado, lago, río, cascada, elevación revisada
  Depende de: elevación (etapa 1), precipitación bruta (etapa 3 usa esto, no al revés)
  Validación V2: cada celda de tierra tiene destino de flujo hacia océano o lago cerrado

Etapa 3 — Clima
  temperatura (latitud + altitud), precipitación (viento húmedo, sombra de lluvia)
  → temperatura (°C), precipitación normalizada
  Depende de: elevación (etapa 1)
  Validación V3: rango de temperatura y precipitación dentro de los umbrales del preset

Etapa 4 — Biomas y capas finales
  clasificación temperatura × humedad × elevación × distancia al agua (dato en datos_base/biomas)
  → capa de bioma, capa de agua (océano/lago/río), caudal, rasgos (cascada/lava)
  Depende de: temperatura (3), precipitación (3), elevación (1), lago/río (2)
  Validación V4: cada bioma declarado tiene al menos una celda; no hay biomas huérfanos

Etapa 5 — Recursos y vegetación inicial
  distribución de vegetación, minerales desconocidos (motor/minerales.py), puntos de interés
  → capa de vegetación/recursos, lista de minerales del mundo
  Depende de: biomas (4), elevación (1), agua (2)
  Validación V5: cada recurso declarado existe en algún bioma coherente

Etapa 6 — Validación de habitabilidad
  punto de inicio: tierra llana, agua dulce alcanzable por A* real (audit P0/P2 ya hecho)
  → punto(s) de inicio, centro seguro
  Depende de: todo lo anterior
  Validación V6: al menos un punto de inicio con orilla de agua enrutable dentro del presupuesto de nodos (misma métrica que el motor en producción)
```

### 3.2 Validaciones entre etapas (puertas)

| Puerta | Qué comprueba | Si falla |
|---|---|---|
| V1 (post etapa 1) | Masa terrestre mínima contigua | Regenerar con misma semilla o rechazar preset |
| V2 (post etapa 2) | Drenaje completo sin pozos aislados sin salida | Ajustar relleno de depresiones |
| V3 (post etapa 3) | Temperatura/precipitación dentro de umbrales | Reajustar preset de clima |
| V4 (post etapa 4) | Ningún bioma declarado sin representación | Revisar rangos de clasificación |
| V6 (post etapa 6) | Punto de inicio habitable y alcanzable | Rechazar mundo; no generar inicio inválido (ya verificado en `sim_io.elegir_inicio`) |

### 3.3 Ideas de BiomeSimulator adaptadas (y justificación)

| Idea de BS | ¿Adaptarse? | Justificación / cómo en MV |
|---|---|---|
| World-in-Worker (motor aislado del render) | No como worker obligatorio | MV ya separa motor de UI/CCA; worker solo si se mide beneficio (ver 4) |
| Claridad de prioridades (P1 sed…P9 idle) | Sí, como referencia | MV usa utilidades + LOD; tomar la claridad de prioridades, no reemplazar CCA por reglas |
| `effectiveAge` (semilla→brote→adulto→fruto→muerto; agua×terreno×estación×hacinamiento) | Sí | Da al ciclo vegetal un modelo de dato claro; MV lo incorpora como dato JSON |
| Limpieza de tile por sucesión vegetal | Sí | Evita acumulaciones infinitas; se paga por ciclo de muerte |
| Estaciones y modificador de visión por período | Sí | MV tiene estaciones en `reloj`; falta el efecto sobre vegetación y visión |
| Sync incremental / delta + sub-workers | Sí como opción posterior | MV ya tiene LOD; delta se evalúa en etapa D solo si se justifica |
| Costos de movimiento por terreno y sub-tile | Parcial | MV ya tiene costo por bioma; BS refina con sub-tile, evaluar costo/beneficio |
| Almacenamiento Uint8 de ids fijos | No | MV es data-driven; no conviene |
| IA de reglas (reemplazaría CCA) | No | Viola el principio central |
| Modelo single-map sin dimensiones | No | MV ya es multi-dimensión; es una ventaja |

### 3.4 Diversidad entre semillas y generaciones

- Determinismo: misma semilla + misma `VERSION_GENERADOR` = mismo mapa (ya vigente).
- Minerales desconocidos por dimensión (ya implementado en `motor/minerales.py`) se conservan y se extienden: 2–6 por dimensión, sorteados de la semilla, sin generar recetas (etiqueta `#mena_desconocida`).
- Los presets por dimensión (`datos_base/dimensiones/*.json`) permiten mundos con mismo generador y otros umbrales: solo JSON.

---

## 4. Simulación y rendimiento

### 4.1 Análisis del coste actual (verificado)

- A* es el 66 % del CPU y falla 2 de cada 3 búsquedas en 2048² a 5 m (`docs/OPTIMIZACION.md`).
- `fuego.paso` era 52 % del CPU en campos enteros sin actividad (ya corregido: regla "sin actividad, sin pasada").
- Terreno: `costo` (array) + `_c` (lista compartida) — duplicación intencionada por velocidad del A*; `cambiar_bioma` debe tocar ambas (trampa documentada).
- Fauna: grilla espacial, tope 450 animales, ticks 5–30 min.
- LOD cognitivo: 3 niveles, cupo base 4 consultas LLM simultáneas.

### 4.2 Objetivos de rendimiento medibles (propuesta, a validar por medición)

| Métrica | Objetivo | Condición |
|---|---|---|
| Minutos simulados por segundo real | ≥ 200 | 2048², celdas 5 m, 100 habitantes, cerebro híbrido disponible |
| Tiempo de una búsqueda A* | < 50 ms p99, < 5 ms camino caché | Dentro del presupuesto de nodos del mundo |
| Memoria del terreno a 2048² | < 200 MB | Evitar `tolist()` por celda; compartir floats (ya hecho) |
| Tick del motor sin LLM | ≤ 35 ms (presupuesto actual, se mantiene) | Mundo sin habitantes en foco consultando al modelo |
| Tiempo de reset de estado UI al cambiar mundo/dimensión | < 100 ms | Sin recarga de página |

### 4.3 Decisiones de arquitectura de rendimiento (propuestas, no implementadas)

- **No workers ni subprocesos por defecto.** La arquitectura actual (bucle único + LOD cognitivo + A* con presupuesto) es suficiente mientras las métricas anteriores se cumplan. Workers solo se añaden si una medición demuestra que el cuello de botella es el tick del motor y no la latencia del LLM o el A*.
- **Estructuras de datos para mundos grandes:** mantener arrays numpy para capas (elevación, bioma, agua, costo) y dicts/set para entidades; no adoptar estructuras complejas (chunked quadtrees, ECS) sin evidencia de que el A* o la consulta espacial las necesiten. La grilla espacial de fauna y chunks (`motor/chunks.py`) ya existen y son el punto de partida.
- **Costo de navegación y consultas espaciales:** corregir la heurística del A* para que escale con `tam_celda_m` (causa raíz verificada); considerar nodos de jerarquía solo si el A* sigue fallando tras la corrección del relieve.
- **Actualizaciones incrementales:** aplicar solo donde haya crecimiento medible (eventos, efectos visuales, nieve/ceniza); no generalizar a toda la simulación sin medir.

---

## 5. Diseño de simulación ecológica (propuesta)

### 5.1 Sistemas actuales vs faltantes

| Sistema | ¿Existe? | Estado | Qué incorporar primero |
|---|---|---|---|
| Ciclo de vida vegetal | Parcial | `ecologia`/`conservacion`/`propagacion` existen, pero no etapas semilla→brote→adulto→fruto→muerto con `effectiveAge` | Modelo de crecimiento vegetal como dato (agua × terreno × estación × hacinamiento) |
| Germinación, crecimiento, reproducción, muerte | No | No como etapas explícitas | Etapa C del roadmap |
| Frutos, semillas, recursos en suelo | Parcial | `drops` de caza, `juntar` de materiales | Recursos vegetales en suelo (frutos, semillas) como datos |
| Fauna con alimentación, reproducción, ciclos | Parcial | `fauna.py`: dieta, hambre, vejez, caza, mutación | Reproducción explícita, ciclo de vida, envejecimiento |
| Depredadores, presas, carroñeros | Parcial | Depredador/presa existe; carroñeros no | Cadáveres y descomposición como sistema |
| Cadáveres y descomposición | No | Ausente | Etapa C |
| Estaciones del año | Parcial | `reloj.py`: estaciones, sequedad para fuego | Efecto sobre vegetación, disponibilidad de agua, movimiento |
| Temperatura, precipitaciones, clima | Parcial | `reloj.py`, `motor/frio.py`, generador | Ya funcionan; integrar con ecología |
| Ciclo día/noche | Parcial | `reloj.luz`, `es_noche` en UI y prompts | Modificador de visión y percepción (BiomeSimulator) |
| Disponibilidad de agua y alimento | Parcial | `agua_cercana`, `alimentos`, `comestibles` | Índice de disponibilidad por zona/bioma para decisiones |
| Interacciones terreno-clima-organismos | Parcial | Frio afecta a animales y personas | Temperatura/precipitación afectan crecimiento vegetal y comportamiento |

### 5.2 Modelo de crecimiento vegetal (dato, inspirado en BiomeSimulator)

**Etapa del vegetal (dato):** `semilla → brote → adulto → fruto → muerto`. Cada avance consume un `effectiveAge` calculado como:

```
effectiveAge += f(agua_disponible, calidad_terreno, estacion, hacinamiento_local)
```

- `agua_disponible`: dato de proximidad al agua (río/lago/lluvia).
- `calidad_terreno`: dato del bioma.
- `estación`: dato del `reloj` (primavera/verano/otoño/invierno).
- `hacinamiento`: densidad de vegetación en la celda vecina (evita campos infinitos).

**Validación:** el modelo es dato JSON; el motor lee la etapa actual y avanza por ticks amortizados. Nada de esto toca la cognición.

### 5.3 Cadena alimentaria y fauna

- Herbívoros comen vegetación del suelo (no si se quemó); carnívoros cazan presas; carroñeros consumen cadáveres.
- Equilibrio: nacen más si hay espacio y comida; mueren de vejez, hambre, fuego o cazados. Reposición por inmigración si una especie casi se extingue (ya existe en `fauna._llegadas`).
- Cadáveres: entidad temporal en el suelo con descomposición; liberan nutrientes al terreno (dato) y atraen carroñeros.

### 5.4 Agua y alimento como datos de decisión

- Índice de disponibilidad de agua por zona (para `agua_cercana` y decisiones del cerebro).
- Índice de alimento por bioma/estación.
- Estos índices se calculan en ticks amortizados y se publican en el estado vivo para la UI y la percepción CCA.

### 5.5 Qué NO se incorpora (fuera de alcance de esta etapa)

- No reemplazar la fauna por reglas que dupliquen CCA.
- No añadir necesidades que el motor deba validar sin datos de respaldo.
- No cambiar el formato de persistencia existente (solo campos aditivos).

---

## 6. Organización de la interfaz (rediseño integral)

### 6.1 Problema arquitectónico a resolver

**Datos obsoletos al cambiar de mundo/dimensión** (verificado en `ui/vivo.js:104-119`). La causa raíz es que no existe un `estadoUI` único por mundo que se resetee totalmente al cambiar de mundo o de dimensión.

### 6.2 Solución arquitectónica

- **Estado UI único por mundo (`estadoUI`).** Al cambiar de mundo o de dimensión: reset total de `V.habs`, `V.eventos`, `V.efectos`, paneles (`recetas`, `fauna`, `familias`, `era`, lista `habitantes`, ficha). Solo se reconstruye desde el estado vivo del nuevo mundo/dimensión.
- **Capa de datos:**
  - WS `/ws/<mundo>`: estado vivo (habitantes, animales, fuego, clima, efectos, eventos recientes) — push cada 100 ms/1 s según peso.
  - REST `/api/mundos/<n>/...`: detalle bajo demanda (ficha de habitante, recetas, familias, eventos históricos, fauna, ajuste).
  - Nunca hay dos fuentes de verdad para el mismo mundo; el WS es la única fuente de estado vivo.
- **Regla de oro:** la UI nunca muta el motor ni CCA; solo lee estado y envía comandos (`cmd` por WS).

### 6.3 Vistas de la nueva interfaz

| Vista | Contenido | Origen de datos |
|---|---|---|
| Selector y administración de mundos | Lista de mundos (semilla, tamaño, fecha, estado), creación, eliminación | REST `/api/mundos` |
| Vista principal del mundo | Mapa 2D principal, habitantes, animales, fuego, clima, día/noche | WS + capas REST |
| Minimapa | Visión general con salto de cámara | Capas del mapa (bioma/agua) + posiciones WS |
| Información general del mundo | Día, estación, año, temperatura, población, biomas | WS + REST meta |
| Estadísticas de población y ecosistema | Habitantes vivos/muertos, especies fauna, natalidad/mortalidad, tendencias | REST + eventos |
| Eventos y cronología | Lista de eventos con filtro por tipo/actor, importancia | REST `/api/mundos/<n>/eventos` |
| Inspector individual de habitante | Posición, vitales, acción, objetivo, estado | WS vitales + REST ficha |
| Perfil cognitivo y personalidad | Rasgos, temperamento, emociones, LOD | REST ficha + estado WS |
| Memorias, conocimientos y habilidades | Memorias (origen, certeza), conocimientos, recetas sabidas | REST ficha / memorias |
| Objetivos y decisiones recientes | Objetivo actual, plan, últimas decisiones, resultado | REST ficha / decisiones |
| Inventario, construcciones y relaciones | Inventario, refugios, aldeas, relaciones (afecto/confianza) | REST ficha / familias / estructuras |
| Controles de simulación | Play/pausa, velocidad, tiempo, clima (observación solo) | WS comando + estado |
| Herramientas de observación y diagnóstico | Filtros, LOD, métricas A*, caché de rutas, inspector de entidades | REST `/metricas` + WS |

### 6.4 Experiencia visual

- Coherente y escalable: una hoja de estilos (`estilo.css`) con tokens de color/tipografía; paneles que se pliegan (`<details>`) con estado recordado en `localStorage`; mapa como lienzo principal; los paneles son capas sobre el mapa, no una acumulación independiente.
- Sprites dibujados en código (ya existente), sin archivos de imagen.
- Escalable a cientos de entidades: render por capas, solo lo visible, sin duplicar lógica.

### 6.5 Datos obsoletos: cómo se evita

Al cambiar de dimensión (`armarDimensiones`) o de mundo (`alAbrir`):
1. `desconectar()` del WS anterior.
2. Reset total: `V.habs = {}`, `V.efectos = []`, `V.eventos = []`, `V.estado = null`, `V.sel = null`, paneles vacíos.
3. Reconectar al WS del nuevo mundo/dimensión y reconstruir todo desde `hola`/`estado`.

---

## 7. Frontera CCA / Mundo Vivo

### 7.1 Presupuesto de responsabilidades (se preserva)

| Mundo Vivo (motor) | CCA (cerebro) | Adaptador (conexión) |
|---|---|---|
| Conoce el entorno: terreno, biomas, clima, agua, fuego, fauna, estructuras, otros habitantes | Procesa percepción, memoria, razonamiento, aprendizaje, personalidad | Traduce percepción del motor al formato de CCA |
| Ejecuta y valida acciones: movimiento, comer, beber, fabricar, cazar, hablar, construir | Genera objetivos, planes, decisiones, intenciones | Traduce decisión de CCA a acción del motor (`_aplicar`) |
| Expone percepción: lo que el habitante ve, sabe, siente, recuerda | Almacena memoria (episódica, semántica, social, autobiográfica) | Aísla cognitivamente por `world_uid` (`cerebros_<world_uid>.db`) |
| Publica estado vivo y eventos | No toca el mundo nunca; solo propone | Gestiona latencia, tiempo de espera, respaldo si CCA no responde |

### 7.2 Intercambio de información (contrato)

**De Mundo Vivo → CCA (percepción):**
- Estado del habitante: sed, hambre, energía, salud, posición, acción, inventario, emociones.
- Entorno inmediato: bioma, temperatura, lluvia, agua cercana, animales cercanos (especie, peligro, comestible), personas cercanas, fuego, estructuras con pasos a otras dimensiones.
- Memoria y conocimientos del habitante: recuerdos relevantes, creencias, habilidades, relaciones, objetivo y plan actuales.
- Disponibilidad de acciones: qué recetas sabe, qué materiales lleva, qué puede fabricar.

**De CCA → Mundo Vivo (decisión):**
- Acción con parámetros (`tipo`, `destino`, `animal`, `mensaje`, `intención`, `receta`, etc.).
- El motor valida contra reglas del mundo y devuelve `ok/texto`; CCA no asume éxito.

### 7.3 Qué NO se hace

- No mover sistemas cognitivos (memoria, razonamiento, planificación) al motor de Mundo Vivo.
- No introducir duplicación de responsabilidades: si el motor ya sabe calcular `agua_cercana`, CCA no lo reimplementa; lo recibe en la percepción.
- No reemplazar CCA por IA de reglas (principio central).

---

## 8. Estrategia de compatibilidad y migración

### 8.1 Impacto sobre lo existente

| Elemento | Impacto | Acción |
|---|---|---|
| Mundos existentes | Se abren igual (`world_uid` estable) | Sin cambios; los nuevos campos son aditivos en JSON `estado` |
| Bases de datos SQLite | Esquema existente se conserva | Migraciones solo aditivas (tablas/columnas nuevas), nunca `ALTER` que destruya datos |
| Seeds | Determinismo mantenido | `VERSION_GENERADOR` sube solo si cambia el algoritmo; mundos viejos conservan su mapa guardado |
| Identificadores de mundo | `world_uid` persiste | Sin cambios |
| Aislamiento cognitivo | `cerebros_<world_uid>.db` por mundo | Sin cambios; nuevas dimensiones hereden el mismo `world_uid` |
| Integración CCA | `brain_id={world_uid}:d{dim}:h{id}` | Sin cambios; contrato WS/REST estable |

### 8.2 Estrategia de migración gradual

1. **Backup antes de cualquier migración.** Copia de la carpeta `datos/mundos/` antes de tocar esquemas o datos.
2. **Solo cambios aditivos.** Campos nuevos en `estado` JSON (sin migración, como ya ocurre); tablas nuevas solo si es indispensable.
3. **Validación por mundo.** Al abrir un mundo existente, validar que `world_uid`, capas y habitantes cargan; si falla, ofrecer abrir con respaldo o abandonar ese mundo (no corromper).
4. **Nunca modificar datos existentes.** Los registros actuales (`habitantes`, `eventos`, `conocimientos`, `estado_dinamico`) se leen; se escriben solo nuevos registros o campos aditivos.
5. **Compatibilidad explícita.** Cada etapa del roadmap declara qué versiones de mundo y de `VERSION_GENERADOR` soporta.

### 8.3 Riesgos de compatibilidad

- Cambiar `ALTURA_MAX_M` / `PROFUNDIDAD_MAX_M` afecta mapas generados, no los ya guardados (el mapa se guarda, no la receta). Los mundos nuevos usarán los nuevos valores; los viejos se abren con sus capas guardadas.
- Cambiar el algoritmo del generador sube `VERSION_GENERADOR`; los mundos existentes no se regeneran.

---

## 9. Roadmap de implementación (etapas A–F)

Cada etapa es independiente y ordenada. Las criterios de finalización son objetivos y medibles.

### A. Arquitectura y fundamentos

| Campo | Contenido |
|---|---|
| Objetivo | Establecer límites de módulo, contratos WS/REST versionados, harness de pruebas y línea base de rendimiento |
| Módulos afectados | `api/servidor.py`, `api/vivo.py`, `persistencia/sim_io.py`, `motor/simulacion.py` (contratos), `docs/` (contratos) |
| Dependencias | Ninguna (etapa inicial) |
| Beneficio | Contrato estable para UI y CCA; evita datos obsoletos; base medible |
| Riesgos | Bajo (no cambia comportamiento del motor) |
| Pruebas | Tests de contrato API/WS; tests de carga del mundo existente; tests de aislamiento cognitivo (ya existen, 10) |
| Criterio de finalización | Contrato WS/REST documentado y testeado; línea base de rendimiento publicada (minutos simulados/s, A* p99, memoria); tests existentes pasando (452) |

### B. Generación procedural

| Campo | Contenido |
|---|---|
| Objetivo | Pipeline por etapas con validaciones (relieve → hidrología → clima → biomas → recursos → habitabilidad); islas, archipiélagos, cuevas; biomas coherentes con geografía y clima |
| Módulos afectados | `generador/pipeline.py`, `motor/geografia.py` (nueva), `datos_base/dimensiones/*.json`, `datos_base/biomas/*.json` |
| Dependencias | A (contratos de datos) |
| Beneficio | Mundos geográficamente coherentes, deterministas por semilla, diversos entre semillas |
| Riesgos | Medio (cambios en relieve afectan navegación; validar V1–V6) |
| Pruebas | Tests de generación por semilla (determinismo); tests de validación V1–V6; test de habitabilidad (punto de inicio con agua alcanzable, ya en `sim_io`) |
| Criterio de finalización | Pipeline ejecuta 6 etapas con puertas V1–V6; generación determinista; mundos de prueba abren y son habitables |

### C. Ecosistema y ambiente

| Campo | Contenido |
|---|---|
| Objetivo | Ciclo de vida vegetal (`effectiveAge`), estaciones con efecto sobre vegetación, día/noche con modificador de visión, cadena alimentaria (depredador/presa/carroñero), cadáveres y descomposición, disponibilidad de agua y alimento |
| Módulos afectados | `motor/ecologia.py`, `motor/fauna.py`, `motor/reloj.py` (uso, no cambio), `datos_base/` (vegetación, especies) |
| Dependencias | B (biomas, agua, terreno) |
| Beneficio | Ecosistema dinámico; mundo rico sin tocar cognición |
| Riesgos | Medio (percepción/estaciones afectan decisiones del cerebro; validar no regresión) |
| Pruebas | Tests de ciclo vegetal (etapas y `effectiveAge`); tests de cadena alimentaria; tests de estaciones y día/noche; tests de regresión en pruebas existentes (452) |
| Criterio de finalización | Vegetación avanza por etapas como dato; estaciones afectan crecimiento; cadáveres se descomponen; tests verdes |

### D. Simulación y rendimiento

| Campo | Contenido |
|---|---|
| Objetivo | Corregir heurística del A* escalada a `tam_celda_m`; estructurar datos para mundos grandes; cumplir métricas de rendimiento; evaluar workers solo si se justifica por medición |
| Módulos afectados | `motor/navegacion.py`, `motor/chunks.py`, `motor/simulacion.py` (tick), `motor/fauna.py` (grilla) |
| Dependencias | B (mapa generado), C (ecología) |
| Beneficio | Escalabilidad a cientos/miles de entidades; mundo fluido a 5 m/celda |
| Riesgos | Medio (cambiar heurística puede afectar rutas existentes; medir antes y después) |
| Pruebas | Profiling de A* antes/después; tests de navegación en mapa grande; tests de rendimiento (no regressión) |
| Criterio de finalización | A* p99 < 50 ms; minutos simulados/s ≥ objetivo; no regresión en tests de navegación |

### E. Interfaz

| Campo | Contenido |
|---|---|
| Objetivo | Rediseño integral: estado UI único por mundo, reset total al cambiar mundo/dimensión, minimapa, inspector de habitante, perfil cognitivo, memorias, objetivos, inventario, construcciones, relaciones, controles, herramientas de diagnóstico |
| Módulos afectados | `ui/vivo.js`, `ui/mapa.js`, `ui/sprites.js`, `ui/estilo.css`, `ui/index.html`, `ui/observador.js` (nueva) |
| Dependencias | A (contrato WS/REST), C (datos de ecología para estadísticas) |
| Beneficio | UI coherente, observa el estado real del motor, sin datos obsoletos |
| Riesgos | Medio-alto (superficie grande de UI; no duplicar lógica de simulación) |
| Pruebas | Tests de reset de estado al cambiar dimensión/mundo; tests de renderizado de capas; tests de que UI no envía comandos de simulación (solo lectura + comandos) |
| Criterio de finalización | Reset total verificado al cambiar mundo/dimensión; todas las vistas listadas funcionan; UI lee estado real sin duplicar lógica |

### F. Integración y observabilidad de CCA

| Campo | Contenido |
|---|---|
| Objetivo | Instrumentar frontera CCA (ranking de utilidades, estado del plan GOAP, objetivo elegido por tick) para diagnóstico; asegurar contrato estable CCA/Mundo Vivo |
| Módulos afectados | `agentes/mente.py`, `agentes/cerebro_cognitivo.py`, `motor/objetivos.py`, `persistencia/` (decisiones, plan) |
| Dependencias | A (contratos) |
| Beneficio | Diagnóstico directo de por qué un habitante no se mueve (problema verificado en audit §5) |
| Riesgos | Medio (tocar el puente puede afectar selección de objetivos; confirmar causa antes) |
| Pruebas | Tests de instrumentación (ranking, plan); tests de decisión del cerebro; tests de aislamiento cognitivo |
| Criterio de finalización | Ranking de utilidades y estado del plan disponibles por habitante y tick; diagnostico del caso "no se mueve" reproducible |

### 9.1 Paralelismo y dependencias entre etapas

```
A (arquitectura/fundamentos)
 ├── B (generación) ──┐
 ├── C (ecosistema) ──┼── D (rendimiento) ──┐
 └── F (CCA) ─────────┘                   └── E (interfaz)
```

- **A va primero:** define contratos que usan B, C, E, F.
- **B y C pueden ir en paralelo** una vez A define los datos de terreno/biomas/agua.
- **D depende de B y C** (mapa y ecología generados).
- **E depende de A** (contrato WS/REST estable) y de C para estadísticas de ecosistema.
- **F depende de A** y se beneficia de la instrumentación de movimiento (ya identificada en audit §5).

### 9.2 Orden recomendado

1. **A** (fundamentos y contratos).
2. **B** (generación por etapas con validaciones).
3. **C** (ecosistema y ambiente) — en paralelo con B después de A.
4. **D** (rendimiento) — después de B y C, con medición obligatoria.
5. **E** (interfaz) — después de A; puede solaparse con D.
6. **F** (observabilidad CCA) — después de A; bajo riesgo, se puede hacer temprano para diagnóstico.

---

## 10. Decisiones técnicas pendientes

| Decisión | ¿Por qué está pendiente? | Qué se necesita para decidir |
|---|---|---|
| Corrección definitiva de la heurística A* (escalar a `tam_celda_m` vs nodos de jerarquía) | Causa raíz conocida (relieve a 5 m), pero no se ha medido el efecto de la corrección en rutas reales | Profiling post-corrección en mapa 2048² a 5 m |
| Uso de workers/subprocesos para simulación | No hay evidencia de que el bucle único sea el cuello de botella (el LLM y el A* lo son más) | Medición que demuestre cuello de botella en tick de motor, no en LLM ni A* |
| Formato exacto de `estadoUI` y versionado WS/REST | Por definir en etapa A | Acuerdo de contrato entre API y UI |
| Alcance de la instrumentación CCA (qué métricas de utilidad/plan se guardan) | Por definir en etapa F | Medición del impacto en persistencia y rendimiento de guardar ranking por tick |
| Estrategia de renderizado del minimapa (capa precalculada vs calcular en cliente) | Por definir en etapa E | Prueba de rendimiento con mapa 2048² |

---

## 11. Referencias a BiomeSimulator

- **Usado como referencia externa** (no como código a copiar): docs `project-specification`, `architecture`, `simulation/ai`, `simulation/plants`, `renderer/overview`.
- **Adaptaciones justificadas:** `effectiveAge` y ciclo vegetal; estaciones y modificador de visión; claridad de prioridades (como referencia, no reemplazo de CCA); inspector de entidades, minimapa, reporte de tendencias (para la UI); sync incremental/delta como opción de rendimiento; costos de movimiento por terreno (refinamiento opcional).
- **No se copia:** IA de reglas (reemplazaría CCA), modelo single-map sin dimensiones, almacenamiento Uint8 de ids fijos (MV es data-driven), licencia Apache-2.0 en código portado sin adaptación.

---

## 12. Resumen de decisiones arquitectónicas más importantes

1. **Evolución modular, no reescritura.** Se conserva `Simulacion` + mixins, generador por etapas, persistencia JSON y frontera CCA; se separan y consolidan responsabilidades donde hay duplicación o falta.
2. **Pipeline de generación con 6 etapas y 6 puertas de validación** (V1–V6), para mundos geográficamente coherentes, deterministas por semilla y habitables.
3. **UI con estado único por mundo y reset total al cambiar mundo/dimensión**, resolviendo el problema verificado de datos obsoletos; WS para estado vivo y REST para detalle bajo demanda; la UI nunca duplica lógica de simulación ni cognición.
4. **Frontera CCA preservada:** Mundo Vivo conoce el entorno y ejecuta; CCA percibe, memoriza, razona y decide; el adaptador traduce. No se mueve cognición al motor ni se reemplaza por reglas.
5. **Compatibilidad estricta:** mundos existentes, `world_uid`, seeds y bases cognitivas se preservan; solo cambios aditivos; backup antes de migración; nunca modificar datos existentes.
6. **Rendimiento medido, no asumido:** objetivo de ≥200 min simulados/s a 2048² 5 m con 100 habitantes; A* p99 < 50 ms; workers solo si se justifica por medición.
7. **Roadmap A–F** con dependencias claras: A primero, B y C en paralelo, D después de B/C, E después de A, F para diagnóstico de CCA.

**Ruta del entregable:** `docs/ARQUITECTURA_OBJETIVO_MUNDO_VIVO.md` (este documento).

**Próximo paso recomendado:** revisar este diseño con el usuario y, una vez aprobado, empezar por la etapa A (arquitectura y fundamentos) sin modificar código existente hasta que los contratos estén acordados.

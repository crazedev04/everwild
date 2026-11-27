# Auditoría de interfaz y propuesta de rediseño visual — Everwild

> Alcance: **solo interfaz, experiencia de usuario, renderer y presentación visual**.
> No se modifica el motor de simulación, la persistencia, los cerebros, la generación
> procedural ni los contratos del backend. Esta etapa es de **auditoría y diseño**: no se
> implementa el rediseño. Documento único; no duplica `CHANGELOG.md`, `docs/OPTIMIZACION.md`
> ni la documentación de motor.

---

## 1. Estado actual

- **Repositorio:** `https://github.com/crazedev04/everwild.git` (el proyecto se llamó "Mundo Vivo"; el paquete Python sigue siendo `mundo_vivo`).
- **Rama inspeccionada:** `main`.
- **Commit:** `2ef21ee docs(changelog): registrar L.3 streams RNG independientes`.
- **Estado de Git al iniciar:** árbol de trabajo **limpio**, `main` sincronizada con `origin/main`, sin archivos no trackeados. No se cambió de rama ni se tocó trabajo existente.
- **Stack frontend:** HTML + CSS + JavaScript nativo (sin framework, sin bundler) y **Canvas 2D**. Servidor FastAPI que sirve `ui/` sin caché y expone REST + WebSocket.
- **Entrypoints de UI:** `/` → `ui/index.html` (visor principal); `/eventos` → `ui/eventos.html` (crónica).

### Validación visual (limitación explícita)

Se ejecutó la app en un entorno aislado (`--datos /tmp/...`, puerto 8799, mundo `AuditChico` 192×192, semilla 42, 6 habitantes) y se capturó con Chrome headless. **El modelo que redacta esta auditoría no dispone de entrada de imágenes**, por lo que no se inspeccionaron los PNG; la validación se apoyó en evidencia textual del DOM renderizado y en ausencia de errores de consola:

- Página principal: DOM poblado → reloj `Día 1`, **6 fichas de habitante renderizadas**, conexión `● en vivo` (WebSocket activo), `Era: Piedra`, `<canvas id="lienzo">` presente. **Sin errores de consola** (filtrado el ruido de GPU/DBus del entorno headless).
- Página de eventos: `7 sucesos · 1 día de historia`, crónica renderizada.
- `GET /api/mundos/{n}/metricas` responde (chunks, fuego, habitantes_vivos, t_min).

**No evaluable en esta auditoría:** estética fina, legibilidad real, comportamiento táctil en móvil y transiciones, al no poder ver píxeles. Las secciones 4 y 10 se basan en el código y en la estructura, no en inspección visual directa. Para validación visual real se requiere un navegador con operador humano o un agente con capacidad de imagen.

---

## 2. Inventario de archivos y responsabilidades

| Archivo | Líneas | Responsabilidad real | Problemas de responsabilidad |
|---|---|---|---|
| `ui/index.html` | 458 | Estructura de pantallas (header, canvas, panel lateral, modales, carga) **+ ~215 líneas de `<style>` embebido** | Mezcla estructura y presentación; estilos críticos fuera de `estilo.css` |
| `ui/estilo.css` | 425 | Sistema visual (tokens, tipografías, controles, header, dock, barras, modales spawn) | Incompleto: layout principal vive en el `<style>` de `index.html` |
| `ui/mapa.js` | 424 | Renderer de **terreno** (capas rasterizadas a bitmap), cámara (zoom/pan/teclado), carga de mundos y capas, creación/borrado/exportación, info bajo cursor, leyenda | Acoplamiento por globals; sin secuenciación de peticiones; mezcla "carga de datos" con "control de UI" |
| `ui/vivo.js` | 1177 | Capa en vivo: WebSocket, estado mergeado, lista de habitantes, ficha/inspector, recetas, fauna, familias/aldeas, era, avisos, feed, **y todo el dibujo dinámico** (vegetación, fuego, noche, nieve/ceniza, senderos, animales, personas, burbujas de diálogo) | **Dios monolítico**: estado + fetch + DOM + render en un solo IIFE; ~500 líneas de dibujo |
| `ui/sprites.js` | 735 | Generador de sprites **en código** (personas por edad/sexo/dirección/paso, animales, estructuras) con caché por combinación | Es lo más desacoplado y sano; API pública clara (`window.Sprites`) |
| `ui/eventos.html` | 225 | Crónica de sucesos: filtros, agrupación por día, paginación, auto-sync | `<style>` y `<script>` embebidos; lógica de datos/paginación duplicada respecto del patrón de `vivo.js` |

**Dependencias en runtime (orden de carga en `index.html`):** `sprites.js` → `mapa.js` (define `window.MVBase`, `window.MV_abrirMapa`) → `vivo.js` (define `window.MV`, usa `window.MVBase` y `window.Sprites`). `mapa.js` llama a `window.MV.sobreMapa()` dentro de su `dibujar()`; `vivo.js` llama a `base().dibujar()`. Hay **acoplamiento circular por globals** entre `mapa.js` y `vivo.js`.

---

## 3. Dependencias

- **Acoplamiento por variables globales** (`window.MV`, `window.MVBase`, `window.Sprites`, `window.MV_abrirMapa`): es el mecanismo de integración entre los tres módulos. No hay `import`/módulos ES; todo son IIFE que se pisan el namespace global.
- **Dependencia de datos:** toda la UI depende de REST (`/api/...`) y de un único WebSocket `/ws/{nombre}`. No hay caché de cliente más allá de `localStorage` para UI (mundo elegido, pestaña, `<details>` abiertos, modelo).
- **Dependencia de red por ficha:** cada selección dispara `fetch` a `/habitantes/{id}`; recetas/fauna a `/recetas` y `/fauna`; familias a `/familias`; era a `/era`; nieve/ceniza a `/dinamico/*` (deflate, mundo entero).
- **Sin dependencias de terceros** salvo fuentes de Google Fonts (`@import` en `estilo.css`): dependencia de red externa para tipografía (riesgo de privacidad/rendimiento y fallo silencioso offline).
- **Acoplamiento con el motor:** nulo a nivel de reglas (correcto). El único punto de contacto es el **presentador** (`api/presentador.py`), que serializa el estado. La UI no conoce el motor.

---

## 4. Auditoría visual

Basada en código y estructura (no en inspección de píxeles, ver §1).

- **Identidad actual:** "Obsidian Field Guide / Tactical Chronicle": paleta oscura profunda, acentos dorados, tipografías Cinzel (display) + Plus Jakarta Sans + JetBrains Mono, glassmorphism sutil. Es coherente y de cierta calidad, pero **fuertemente "HUD de estrategia/RPG"** (dock de poderes, era bar, barras), que compite con el requisito de "el mundo es el protagonista".
- **Jerarquía:** el panel lateral (`clamp(340px,28vw,420px)`) concentra reloj + 6 pestañas + inspector; el mapa ocupa el resto. En escritorio el mundo domina; la densidad del panel es alta (muchas secciones `<details>`).
- **Terreno:** predominantemente **rasterizado** (bitmap por mundo a 1 px/celda, escalado con `imageSmoothingEnabled=false`). A zoom alto se ve pixelado; el "detalle" (matas/árboles/piedras) se dibuja por celda en vivo (solo `z>=10`).
- **Agua:** color plano por celda (océano/lago/río) sin animación ni orilla; ríos se tiñen en modo "ríos".
- **Vegetación:** procedural por celda con formas simples (3 trazos de pasto, círculo + tronco para árbol). Consistente pero "de prototipo".
- **Senderos/caminos:** puntos de tierra pisada (`fillRect` 1×1) y claro radial en aldeas. Funcional, visualmente tosco.
- **Fauna:** sprites por clase + emoji de apoyo a zoom alto; de lejos, puntos de color por medio.
- **Construcciones:** `Sprites.estructura` (casas, hornos, fraguas, pilas, dinamos, ruinas) con tamaño físico; es de lo mejor resuelto.
- **Personas:** sprites por edad/sexo/dirección/paso con suavizado de movimiento; barras de vida/sed/energía/comida y nombre en píxeles de pantalla. Bien pensado.
- **Noche/iluminación:** capa oscura con "agujeros" de luz (sprite radial pre-renderizado) para fogatas/antorchas/refugios. Logro notable.
- **Adaptación móvil:** un único `@media (max-width:860px)` que apila canvas y panel; el canvas pasa a `52vh`. No hay diseño táctil real (pinch-zoom ausente; zoom solo por rueda/botones/teclado), ni reorganización de paneles.

**Conclusión visual:** hay una base con personalidad, pero saturada de chrome de "juego de estrategia" y con terreno/vegetación/agua de nivel prototipo. El rediseño debe **reducir el HUD**, jerarquizar por inmersión y elevar terreno/agua/vegetación sin assets comprados.

---

## 5. Problemas funcionales y causas

Confirmados por lectura de código (no se corrigen en esta etapa).

1. **Cambio de mundo sin secuenciación (carrera de capas).** `mapa.js:abrirMundo()` dispara 8 `fetch` en `Promise.all` y escribe `estado.capas` al resolverse. No hay token de secuencia ni cancelación. Si se cambia de mundo (o de dimensión vía `MV_abrirMapa`) rápido, **gana el último en resolver, no el último pedido** → se puede mostrar el terreno de un mundo con habitantes de otro. Causa raíz: ausencia de guardia de "petición vigente".
2. **Ficha obsoleta / de otro mundo y de otro habitante.** `vivo.js:refrescarFicha()` es `async`, usa `V.sel` y `V.nombre` globales y un único cerrojo `_fichaOcupado`. Si la selección cambia (o se cambia de mundo) con un `fetch` en vuelo, al resolver escribe en `#ficha`/`#fc-*` con `hb = V.habs[V.sel]` **del habitante actual**, no del pedido → cabecera y barras pueden corresponder a otra persona. Tras `alAbrir` (que pone placeholder), una respuesta en vuelo del mundo viejo puede sobrescribir la ficha. Causa raíz: no captura el id/mundo al inicio ni valida al resolver.
3. **Peticiones concurrentes de paneles sin guardia de vigencia.** `refrescarRecetas`, `pintarFamilias`, `actualizarEra`, `pedirNieve/pedirCeniza` usan cerrojos de "ocupado" pero **no descartan por mundo**: si `V.nombre` cambió, una respuesta vieja aún escribe en el DOM. Causa raíz: el `nombre` se lee al inicio pero no se revalida al resolver.
4. **WebSocket viejo vs nuevo.** `alAbrir` llama `desconectar()` que **nulifica `onclose`** del socket viejo y cierra; el `onclose` del viejo no reintenta (correcto), pero el reintento se gobierna por `V.ws === ws && V.nombre === nombre`, lo que es correcto. Riesgo menor: `recibir()` no filtra por mundo; si un mensaje del socket viejo llega en la ventana entre `close()` y el nuevo `onopen`, se procesa. Causa raíz: `onmessage` no valida identidad del socket.
5. **Eventos: `ultimo` calculado y no usado como guarda; auto-sync cada 3 s** que hace `fetch` completo (300) y reconstruye DOM (guardando/restaurando scroll y `<details>`). Funciona, pero el rediseño/paginación debe unificar criterio. La crónica **no filtra por dimensión** (los hitos quedaron por dimensión, deuda G2 del motor).
6. **Bucle de render continuo a 60 fps** (`vivo.js:cuadro` → `requestAnimationFrame` permanente mientras `V.conectado`). Redibuja terreno + capa en vivo **aunque nada cambió**. No es un bug funcional pero es el mayor costo y la base de los "tirones" (junto a la descompresión de nieve/ceniza de 4 MB en hilo principal cada 10–15 s).

**Pruebas de regresión sugeridas (para la etapa de implementación):** cambio rápido de mundo A→B→A debe mostrar siempre capas y habitantes del mundo vigente; seleccionar habitante X y luego Y con latencia de red simularizada debe dejar la ficha de Y; cambio de dimensión con `fetch` en vuelo no debe pintar la dimensión anterior.

---

## 6. Datos disponibles y faltantes

Fuente: `api/servidor.py` (REST), `api/vivo.py` (WS `hola`/`estado`/`eventos`/efectos), `api/presentador.py` (serialización).

### Matriz (breve)

| Dato | Origen | Uso actual en UI |
|---|---|---|
| Metadatos mundo (semilla, tamaño, `tam_celda_m`, versión generador, dimensiones) | REST `/meta`, WS `hola` | Sí (`mapa.js`, header) |
| Capas raster (elev, temp, hum, bioma, agua, caudal, rasgos) | REST `/capa/*` (deflate) | Sí (terrain + info cursor + capas) |
| Fecha/hora/estación/año/luz/temp_media | WS `estado` (`presentador.estado_base`) | Sí (reloj, dial sol/luna) |
| Habitantes (mapa: id, x, y, acción, vivo, color, sexo, nac, en_fuego, antorcha, emo, detalle) | WS `estado`/`hola` | Sí (lista + dibujo) |
| Vitales (salud, sed, energía, hambre, temp, frío) | WS `estado` bloque pesado (`vitales`) | Sí (barras lista + ficha) |
| Fuego (celdas), fogatas, estructuras/refugios, colonias, senderos, ruinas, tormentas, viento | WS `estado` bloque pesado | Sí (capa en vivo) |
| Fauna (posición por instancia) + catálogo | WS `estado.fauna` + `hola.fauna_cat` + REST `/fauna` | Sí |
| Ficha individual (genoma/rasgos, rasgos_vivos, memorias, aprendizajes, plan, hábito, lugares, relaciones, inventario, conocimientos, pensamientos, eventos, temperamento, emoción, padres) | REST `/habitantes/{id}` | Sí (inspector) |
| Recetas (existentes/inventadas, descubridor, saben) | REST `/recetas` | Sí (pestaña recetas) |
| Familias/aldeas (personas, uniones, aldeas derivadas, fogatas por aldea) | REST `/familias` + `estado.aldeas` | Sí (pestaña familias) |
| Era (propiedades descubiertas) | REST `/era` | Sí (era bar) |
| Eventos (crónica, tipos, paginación `antes_id`) | REST `/eventos` + WS `eventos` | Sí (feed + página eventos) |
| Diálogos completos | REST `/dialogos` | **No usado** |
| Métricas en vivo (A*, fuego, chunks, latencia) | REST `/metricas` | **No usado** (solo chunks debug vía WS) |
| Nieve / quemado (mapas dinámicos) | REST `/dinamico/*` | Sí (capas nieve/ceniza) |

### Clasificación

1. **Disponibles y usados:** casi todo lo anterior (ver tabla).
2. **Disponibles pero no usados:** `/dialogos` (registro de conversaciones), `/metricas` (telemetría fina), `meta.t_min` del servidor, `chunks_activos` como dato (solo se usa el flag debug), `viento` (se recibe pero no se visualiza), `caudal` (solo en info de celda).
3. **Calculables desde datos existentes:** densidad de población por aldea/región, tasas de natalidad/mortalidad (eventos + fechas), "qué está haciendo la mayoría" (agregado de `accion`), mapa de calor de actividad (posiciones + senderos), progreso tecnológico por habitante (conocimientos), árbol de afectos (relaciones).
4. **No disponibles (requerirían contrato nuevo, **sin** tocar backend en esta etapa):** texturas/tiles de terreno (solo hay capas numéricas), animaciones de sprites (sprites se generan en código), estado "histórico" del clima, previsualización de estructuras futuras.

**Contrato de integración propuesto (para el rediseño, no implementar aún):** la UI debe depender de un **adaptador de datos** único que encapsule REST+WS y exponga un `WorldState` inmutable con `worldId`/`dimension` para poder descartar respuestas viejas (ataca §5.1–5.4). No requiere cambios de backend; solo reencapsula lo existente.

---

## 7. Evaluación del renderer

- **Terreno (Canvas 2D, bitmap cacheado por mundo):** `prepararImagen()` compone un `ImageData` 1 px/celda (camino rápido por paleta 32-bit; variantes con relieve/ríos/rasgos). `dibujar()` hace `drawImage` de la **porción visible** del offscreen; a `z<1` usa miniatura a media resolución. **Es correcto y barato**: no necesita "chunks" porque ya es un bitmap único blit por viewport.
- **LOD por zoom ya existe:** miniatura (`z<1`), detalle de suelo por celda (`z>=10`), fauna como puntos (`z<4`) vs sprites (`z>=4`) vs +emoji (`z>=9`), nombres/barras a partir de umbrales. **No se justifica introducir chunking del terreno estático**; sería optimización especulativa.
- **Capa en vivo (`vivo.js:sobreMapa`):** se redibuja **cada frame** (fuego titila, humo, noche, burbujas, suavizado de personas). Es lo que obliga al rAF continuo.
- **Sprites (`sprites.js`):** generación en código + caché por combinación. Sano; es la pieza a **conservar y ampliar** (más variantes/estados), no reescribir.
- **Costos detectados:** (a) rAF continuo sin "dirty" check; (b) descompresión de nieve/ceniza del mundo entero (hasta ~4 MB) en hilo principal cada 10–15 s; (c) detalle de vegetación por celda cada frame a `z>=10`; (d) recreación de canvas de noche por frame (dimensionado al viewport).
- **Optimizaciones justificadas (no especulativas):** render **on-demand** (redibujar solo si cambió estado, hay animación activa o se movió cámara), mover descompresión de nieve/ceniza a `requestIdleCallback`/worker o bajar frecuencia, cachear la capa de detalle de vegetación a un bitmap por tiles **solo si** el perfilado muestra que domina a zoom alto.
- **Qué conservar:** bitmap de terreno + LOD por zoom + sprites en código + iluminación nocturna por sprites radiales.
- **Qué reorganizar:** separar "estado/cámara" de "dibujo"; unificar el bucle (un solo `requestAnimationFrame` con política dirty); extraer la capa en vivo de `vivo.js`.

---

## 8. Dirección artística recomendada

Referencias del proyecto (Wild Lands, Cozy Village & Farm, SpriteShip, Fantasy Dungeon RPG Kit, AssetHoard, Factorio, Minecraft, Godot MultiMesh) leídas como **soluciones concretas**, no para copiar assets:

- **Wild Lands / Cozy Village:** paleta naturalista cálida, terreno con textura suave y vegetación por capas → elevar el **suelo y la vegetación** manteniendo el bitmap (overlay de textura procedural, no assets).
- **SpriteShip / Fantasy Dungeon kit:** sprites con silueta clara y estados → ampliar `sprites.js` (más poses/estados, mejor fauna) **en código**.
- **Factorio / Minecraft (LOD) / Godot MultiMesh:** enseñan **instancing por tiles** y LOD; aplican a la *capa dinámica* (vegetación/fauna), **no** al terreno estático ya cacheado.

**Estilos evaluados:** ilustración naturalista (costoso sin assets), pintado digital (inmanejable por celda), cartoon naturalista (buen equilibrio), **pixel art HD** (coherente con el bitmap actual y `image-rendering: pixelated`), combinación de recursos propios + (futuros) externos.

**Identidad propia recomendada:** **"Pixel art HD naturalista con iluminación atmosférica"**. Aprovecha lo ya resuelto (bitmap a 1 px/celda, sprites en código, noche con luces), reduce dependencia de assets externos (cumple "no comprar/integrar assets"), y permite subir calidad de agua/vegetación con técnicas procedurales. Mantener la paleta "field guide" pero **retirar el lenguaje de HUD de estrategia** (dock/era/barras) hacia una presentación más inmersiva y opcional. **No seleccionar ni comprar assets** sin aprobación.

---

## 9. Arquitectura frontend propuesta

Mantener **JavaScript nativo + Canvas 2D** (no migrar): la migración no se justifica por evidencia; el costo actual es de **arquitectura**, no de tecnología. Separar responsabilidades con módulos ES nativos (`<script type="module">`), sin framework:

- **`core/store.js`** — estado de UI (mundo vigente, dimensión, selección, pestaña, capas, cámara) con `worldId`/`dimension` y suscriptores. Fuente única de verdad para descartar respuestas viejas.
- **`core/data.js`** (adaptador) — encapsula REST + WebSocket; expone `WorldState` inmutable y descarta por `worldId`. Reemplaza los `fetch` dispersos.
- **`render/terrain.js`** — bitmap de terreno + LOD + capas (hoy `mapa.js` parte datos).
- **`render/live.js`** — capa en vivo (hoy `sobreMapa` de `vivo.js`).
- **`render/sprites.js`** — se conserva (`sprites.js`).
- **`render/loop.js`** — único `requestAnimationFrame` con política dirty/on-demand.
- **`ui/components/*.js`** — lista habitantes, inspector/ficha, paneles (familias, recetas, fauna, mundo, ajustes), reloj, avisos, feed, modales.
- **`ui/camera.js`** — zoom/pan/táctil (pinch) y teclado.
- **`styles/`** — tokens + layout; **eliminar el `<style>` embebido** de `index.html`/`eventos.html`.

**Assets:** sprites siguen generándose en código; texturas de terreno procedurales. Sin dependencias externas nuevas (incl. revisar el `@import` de Google Fonts → autoalojar o fallback de sistema).

---

## 10. Experiencia y organización de pantallas

 Principio: **el mundo es el protagonista; el chrome es mínimo y contextual.** Evitar dashboard administrativo y HUD de RPG.

- **Selección/carga de mundos:** selector + "nuevo mundo" + exportar/borrar como **overlay** discreto, no barra permanente.
- **Vista principal inmersiva:** canvas a pantalla completa; controles (zoom, capas, poderes de observador) en **barra contextual** que aparece al interactuar; reloj/era como **indicadores ligeros** (no panel fijo grande).
- **Ecosistema (general):** popover/panel lateral plegable con clima, población, era — bajo demanda.
- **Inspección de habitante:** **panel lateral contextual** (drawer) que se abre al seleccionar; el resto del tiempo no estorba. Reorganizar la ficha (hoy ~8 `<details>`) en secciones priorizadas (identidad → vitales → mente → relaciones → historia).
- **Cronología de eventos:** mantener página `/eventos` dedicada + feed flotante en el mapa; unificar criterio de paginación/auto-sync.
- **Navegación contextual:** mapa ↔ eventos ↔ inspector sin recargar; estado en `store`.
- **Móvil:** diseño real: canvas `100dvh`, paneles como **bottom sheets**, **pinch-zoom** y pan táctil, controles accesibles; un solo `@media` no alcanza.
- **Estados de carga/error:** unificar (hoy hay `#estado`, `#carga`, `#carga-error`, avisos). Banner de error consistente y reintento.

Jerarquía de información: **Mapa (protagonista) → Habitante/estado (secundario, contextual) → Detalle profundo (ficha, historia) (terciario, bajo demanda).**

---

## 11. Plan de implementación

Pocas etapas, ordenadas; separar **correcciones funcionales** de **rediseño**. (No implementar en esta tarea.)

### Etapa 0 — Correcciones funcionales (sin rediseño visual)
- **Objetivo:** eliminar carreras y respuestas viejas (§5.1–5.5).
- **Afecta:** `ui/mapa.js` (token de secuencia en `abrirMundo`), `ui/vivo.js` (capturar `worldId`+`id` en `refrescarFicha`/paneles; validar al resolver; filtrar `onmessage` por socket), `ui/eventos.html` (paginación).
- **Dependencias:** ninguna.
- **Riesgo:** bajo; no cambia contratos.
- **Pruebas:** cambio rápido A→B→A; selección X→Y con latencia; cambio de dimensión en vuelo.
- **Aceptación:** nunca se muestran capas/habitantes/ficha de un mundo o selección que ya no es la vigente.
- **Estado (implementada):** token de secuencia en `mapa.js:abrirMundo` (`cargaSeq`); `vivo.js:refrescarFicha` con token `fichaSeq` + contexto (mundo/dimensión) y sin cerrojo que bloquee la selección nueva; guardas de mundo en `refrescarRecetas`/`pintarFamilias`/`actualizarEra`/`pedirNieve`/`pedirCeniza`; `onmessage` ignora sockets que ya no son el vigente; `eventos.html` descarta respuestas y paginación de otro mundo. Helper puro `ui/race-util.js` (token/contexto) + pruebas de regresión `tests/js/race_util.test.cjs` (node --test). No se tocó renderer, estilos ni backend.

### Etapa 1 — Render on-demand + higiene de rendimiento
- **Objetivo:** eliminar rAF continuo y descompresión en hilo principal (§7).
- **Afecta:** `vivo.js:cuadro`/`sobreMapa` (dirty flag), nieve/ceniza (idle/worker/bajar frecuencia).
- **Riesgo:** medio (puede afectar animaciones); mitigar con pruebas de regresión visual.
- **Aceptación:** sin redibujar cuando nada cambia; CPU en reposo baja; animaciones (fuego, personas) intactas.

### Etapa 2 — Arquitectura modular (sin cambiar la estética)
- **Objetivo:** extraer `store`, `data`, `render/*`, `components/*`, `camera`; pasar a `<script type=module>`; sacar `<style>` embebido a `styles/`.
- **Afecta:** reestructura `ui/` (mismos behavior); `index.html` limpio.
- **Dependencias:** Etapa 0 y 1.
- **Riesgo:** medio (refactor grande); cada módulo con su prueba.
- **Aceptación:** paridad funcional total (mismos datos y acciones), sin globals.

### Etapa 3 — Rediseño visual y de experiencia
- **Objetivo:** identidad "pixel art HD naturalista", HUD mínimo, drawer contextual, móvil real, terreno/agua/vegetación elevados, autoalojar fuentes.
- **Afecta:** `styles/`, `render/terrain.js` (textura/agua), `render/sprites.js` (más estados), componentes de paneles, `camera` (pinch).
- **Dependencias:** Etapa 2.
- **Riesgo:** medio-alto (estética + móvil); validación visual **con operador humano** (el modelo auditor no ve imágenes).
- **Aceptación:** el mundo es protagonista; sin dashboard; móvil usable; sin assets comprados; sin regresiones funcionales de Etapa 0.

### Etapa 4 — Datos no usados (opcional, si se aprueba)
- **Objetivo:** surfacing de `/dialogos` y `/metricas` (p. ej. "actividad del mundo").
- **Riesgo:** bajo; **no requiere** tocar backend.
- **Aceptación:** feature integrada al rediseño sin saturar.

---

## 12. Riesgos y decisiones pendientes

**Riesgos:**
- Refactor (Etapa 2) grande sin framework: riesgo de regresión; mitigar con paridad y pruebas por módulo.
- Rediseño visual (Etapa 3) no validable por el modelo auditor (sin entrada de imagen): requiere humano.
- Rendimiento móvil y pinch-zoom: no cubierto hoy.
- Dependencia de Google Fonts (offline/privacidad).
- Deuda G2 del motor (hitos por dimensión) afecta la crónica; **no se toca** (es motor).

**Decisiones que requieren aprobación:**
1. **Dirección artística** (§8): confirmar "pixel art HD naturalista" vs. alternativa.
2. **Mantener JS nativo + Canvas 2D** (no migrar) — se recomienda mantener; confirmar.
3. **Alcance de Etapa 4** (exponer `/dialogos`, `/metricas`).
4. **Fuentes**: autoalojar vs. fallback de sistema (quitar `@import` externo).
5. **Reordenamiento de la ficha** y jerarquía de paneles (§10).
6. **Assets**: confirmar que no se compran/integran externos en esta fase.

_No se implementó nada. Se detiene aquí y se espera autorización._
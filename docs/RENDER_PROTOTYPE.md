# Prototipo de renderer 2D por capas — Etapa 3A

> Prototipo **aislado** para decidir cómo se representará gráficamente el mundo de
> Everwild. No modifica la app, el motor ni `sprites.js`. Sirve el propio servidor en
> `/ui/prototipo/index.html`. Canvas 2D puro, sin dependencias.

## Cómo ejecutarlo

1. Levantar el servidor (no toca mundos persistentes; usa datos temporales):
   `PYTHONPATH=src:. .venv/bin/python -m mundo_vivo --datos /tmp/ew-proto servir --puerto 8804`
2. Abrir `http://127.0.0.1:8804/ui/prototipo/index.html` (opcional `?z=8` para zoom inicial).
3. Controles: zoom (slider), **Nuevo mundo** (semilla nueva), **Mutar terreno**
   (actualización parcial), **Pausar**, y toggles por capa. Arrastrar para desplazar,
   clic para seleccionar el animal más cercano.

## Arquitectura visual propuesta (capas, atrás → frente)

Adaptación de la pila de BiomeSimulator a Canvas 2D, sobre la base modular de Etapa 2
(`render/escena.js`, `core/app.js`):

1. **TerrainLayer** — biomas/agua/montaña/costa como **textura 1 px/celda** (offscreen
   canvas, `imageSmoothingEnabled=false` = NEAREST). `updateTiles(celdas)` reescribe
   sólo las celdas cambiadas y sube la zona sucia (actualización parcial).
2. **VegetationLayer** — overlay 1 px/celda por etapa de crecimiento; a zoom alto se
   pasa a **sprites** (la planta se dibuja en la capa de profundidad).
3. **StructureLayer** — casas/hornos/fraguas como sprites, en la capa de profundidad.
4. **ShadowLayer** — elipses en el plano del suelo (alpha ~0.30), **debajo** de todos
   los sprites; se dibuja una sola pasada con las posiciones de la lista de profundidad.
5. **EntityLayer** — habitantes/fauna; de lejos puntos de color, de cerca sprites con
   orientación. Comparte la lista de profundidad con plantas y estructuras.
6. **EffectsLayer** — ciclo día/noche (tinte) y partículas ambientales.
7. **OverlayLayer** — anillo de selección, barras/indicadores y HUD de diagnóstico.

**Comunicación con los datos:** las capas reciben un `WorldView` (grids + listas) ya
normalizado; **no** conocen el motor. En la app real ese `WorldView` lo arma el adaptador
de datos (Etapa 2 `data/`), igual que hoy `presentador.py` serializa el estado.

## Técnicas tomadas de BiomeSimulator (referencia, no código)

Adoptadas:
- **Terreno 1 px/celda + actualización parcial** (`updateTiles` en vez de re-rasterizar).
- **Pila de capas** con profundidad por **Y** (`zIndex = y*1000` en Pixi → orden por Y en
  Canvas) y **anchor a los pies** (los sprites se apoyan en su coordenada del mundo).
- **Contenedor de sombras separado** en el plano del suelo.
- **Dual-mode LOD por zoom** (puntos/overlay de lejos → sprites de cerca, con umbral ~6 y
  detalle por celda ~10).
- **Sprite pooling / caché** y **culling** por viewport (sólo se dibuja lo visible).
- **Overlay** (selección/HP) siempre por encima de la escena.

Descartadas (no encajan con Everwild/Canvas 2D sin justificación):
- **PixiJS/Three.js y su `sortableChildren`/zIndex**: se logra lo mismo ordenando por Y en
  Canvas 2D, sin dependencias ni migración.
- **Texturas de emoji a 64 px** y el stack React/Vite: apuntan a otra estética y stack.
- **Editor de terreno con undo/redo** y **panel de estadísticas**: fuera del alcance del
  renderer (es UI de app, no de este prototipo).
- **Partículas por evento de combate/nacimiento** (1200): Everwild ya tiene su capa de
  efectos/ecología; no se duplica aquí.

## Representación según zoom (LOD)

| Zoom | Modo | Terreno | Vegetación | Fauna | Sombras | Detalle celda |
|---|---|---|---|---|---|---|
| `< 1` | puntos | textura | overlay 1px | puntos | — | no |
| `1–6` | híbrido | textura | overlay 1px | puntos | — | no |
| `≥ 6` | sprites | textura | sprites (Y-sort) | sprites | sí | `≥10` |

## Evaluación de rendimiento (cualitativa; ver limitaciones)

- **Terreno**: 1 `drawImage` de un bitmap del tamaño del mundo por frame; el costo es del
  blit escalado, no por celda. `updateTiles` evita re-rasterizar todo ante cambios.
- **Culling**: a z=8 el HUD mostró ~215 plantas / 24 animales visibles (vs 438/40 a z=0.6):
  sólo se procesa lo visible.
- **Caché/pool**: los sprites se generan una vez por (tipo,etapa,variante); el HUD reporta
  el tamaño de la caché (p. ej. 28 a z=8). Evita recrear canvas por frame.
- **LOD**: de lejos no se dibujan sprites ni sombras (menos trabajo); de cerca se activa
  detalle por celda.
- **Bucle bajo demanda**: un solo `requestAnimationFrame`; continúa sólo mientras hay
  animación (animales en movimiento) y se detiene en pausa.
- **Cuellos de botella esperados**: el blit del terreno a zoom alto y el nº de sprites en
  viewport; ambos se acotan con culling + LOD. No se midió CPU/GPU de forma cuantitativa.

## Limitaciones de esta etapa

- Es un prototipo con **datos ficticios** y sprites **procedurales simples** (no la
  estética definitiva; no se impone pixel art).
- **No** mide rendimiento cuantitativo (headless sin instrumentación; el modelo auditor no
  ve imágenes). La evidencia es el HUD textual y la ausencia de errores de consola.
- No reutiliza `sprites.js` real (se mantiene aislado); la integración con la app se decide
  en la etapa de implementación, no aquí.

## Archivos

- `ui/prototipo/index.html` — superficie + panel de control + HUD.
- `ui/prototipo/layers.js` — helpers puros (rng, fbm, LOD, culling, orden Y, pool).
- `ui/prototipo/prototipo.js` — generación ficticia + orquestación de capas + bucle.
- `tests/js/prototipo_layers.test.cjs` — regresión de los helpers puros.
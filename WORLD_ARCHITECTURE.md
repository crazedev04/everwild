# WORLD_ARCHITECTURE.md — Mundo Vivo

## 1. Qué está implementado

### Motor (src/mundo_vivo/motor/)
- `simulacion.py`: `Simulacion` armada con mixins (vida, ecología, frío, conservación, alimentación, atributos, atención, fenómenos, objetivos, psique, propagación, tecnología). Tiempo en minutos simulados (`t`). Habitantes con posición fraccionaria (x, y en float).
- `navegacion.py`: `Terreno` con `costo` (numpy array) y `_c` (listas). A* con heurística octile × 2.0 (weighted). Caché de fracasos (`_fracasos`).
- `generador.py`: relieve con fbm, clima, hidrología, biomas, fauna, minerales. `_a_metros` convierte elevación a metros. `ALTURA_MAX_M` y `PROFUNDIDAD_MAX_M` escalados por `tam_celda_m` (fix reciente).
- `vida.py`: reproducción, parentesco, embarazo, nacimiento, muerte.
- `tecnologia.py`: recetas, inventos, propiedades, calor/energía disponible.
- `fauna.py`: animales con grilla espacial.
- `senderos.py`: desgaste de terreno.
- `minerales.py`: minerales inventados por el mundo.
- `mundo.py`: dimensiones (múltiples mapas).
- `atencion.py`: LOD cognitivo.

### Persistencia (src/mundo_vivo/persistencia/)
- SQLite con migraciones versionadas. Estado de habitante en JSON.
- `sim_io.py`: guardar/cargar mundo, habitantes, eventos, decisiones.
- `mundo_io.py`: meta, capas, dimensiones.
- `memoria.py`: memoria privada de habitantes.
- `social.py`: relaciones, afecto, confianza.

### Agentes (src/mundo_vivo/agentes/)
- `mente.py`: `CerebroHibrido` (LLM + reflejos + respaldo).
- `cerebro_cognitivo.py`: puente a Cognitive Engine (GOAP + Utility AI, sin LLM).
- `genoma.py`, `ollama.py`, `conocimiento.py`, `semantica.py`, `habito.py`.

### API (src/mundo_vivo/api/)
- `servidor.py`: FastAPI, REST endpoints, generación en hilo.
- `vivo.py`: WebSocket, bucle de simulación, estado al visor.

### UI (ui/)
- Canvas 2D con sprites dibujados en código.
- Mapa con zoom y arrastre.
- Ficha de habitante, eventos, recetas, familias.

## 2. Qué está mal

### 2.1 Sistema de unidades inconsistente
- `VEL_BASE = 1.6` celdas/min, calibrado para 50 m/celda. A 5 m/celda, la velocidad real es 0,48 km/h (10× más lento).
- `r_habla`, `r_vista`, `r_encuentro` se calculan con `sim.celdas()` en algunos lugares y en celdas crudas en otros.
- `agua_cercana` usa `radio` en celdas (600 = 600 celdas a 5 m = 3 km, debería ser 120 celdas).
- `nodos_camino = 120000` es un número mágico en celdas, no en metros.
- `BLOQUE_FRACASO = 4` celdas, no metros.

### 2.2 Terreno y navegación
- El costo por celda combina bioma × pendiente × río. La pendiente se calcula en celdas (`np.gradient(elev) / tam_celda_m`), lo cual es correcto en metros. Pero el multiplicador de bioma (`mult_bioma`) es adimensional y no escala.
- El A* usa heurística octile × 2.0 (weighted, inadmisible). La causa raíz es que el costo real por celda es ~3-21, mientras la heurística vale 1-2 por celda.
- `PENDIENTE_MAX = 5.0` es un umbral en pendiente (m/m), correcto. Pero el costo de trepar (`8.0 * pendiente²`) no escala con la distancia real.
- La caché de fracasos (`_fracasos`) se vacía en `cambiar_bioma`, pero no hay invalidación por distancia/tiempo.

### 2.3 Generación procedural
- `_relieve` usa fbm con parámetros en celdas (`w / 4`, `w / 5`, etc.). A distinta resolución, el relieve cambia de escala.
- `_a_metros` escala altura por `tam_celda_m / 50` (fix reciente). Pero la profundidad del océano y la forma del continente no escalan.
- El nivel del mar (`quantil_mar`) es relativo al relieve bruto, no a metros.
- No hay erosión hidráulica ni térmica (está en la lista de pendientes de Everwild).
- No hay tectónica (placas, volcanes dinámicos).
- Las cavernas/subsuelo están pendientes.

### 2.4 Simulación y rendimiento
- El motor corre en el mismo proceso que el servidor web (FastAPI + WebSocket).
- El estado completo se envía al visor cada 100 ms (10 Hz) con todos los habitantes.
- El A* es el 66% del CPU (medido).
- `fuego.paso` recorría 4,2 M de celdas 6 veces por minuto (ya arreglado).
- `_creencias` se recalculaba en cada decisión (ya arreglado, parcialmente).
- No hay chunks ni LOD espacial para el terreno (solo LOD cognitivo para habitantes).

### 2.5 Acoplamiento motor-renderer
- `Simulacion.estado_publico()` genera el JSON completo para el visor. El motor sabe del visor.
- `Terreno` tiene `costo` (numpy) y `_c` (listas) — dos representaciones del mismo dato.
- El renderer (Canvas 2D) dibuja sprites por código. No hay separación de capas de renderizado.

### 2.6 Persistencia
- Estado de habitante en JSON dentro de SQLite. Agregar un campo no pide migración (bueno).
- Pero el formato no está versionado por campo: si se renombra un campo, los mundos viejos se rompen.
- No hay compresión ni chunking de capas (4,2 M de celdas × 7 capas = ~30 MB por mundo).

## 3. Qué debería cambiarse

### 3.1 Sistema físico universal
- Definir constantes en metros: `VEL_CAMINAR_MPS = 1.33` (4,8 km/h), `VEL_CORRER_MPS = 2.5`, etc.
- Convertir a celdas por segundo: `vel_celdas_por_seg = VEL_MPS / tam_celda_m`.
- El costo de A* debe ser en **tiempo** (segundos), no en unidades abstractas.
- `pendiente` ya está en m/m (correcto). El costo de pendiente debe ser `1 + k * pendiente²` donde k es adimensional.

### 3.2 Cuadrícula
- `tam_celda_m` ya es configurable. Bien.
- Posiciones fraccionarias ya se usan (`h.x`, `h.y` en float). Bien.
- Falta: conversión centralizada. Hoy `sim.celdas(metros)` hace la conversión, pero no todos los módulos la usan.

### 3.3 Generación procedural
- Escalar TODOS los parámetros de fbm por `tam_celda_m`: `w / (4 * tam_celda_m)` en vez de `w / 4`.
- Escalar `ALTURA_MAX_M` por `tam_celda_m / 50` (ya hecho).
- Agregar erosión hidráulica (D8) para ríos realistas.
- Agregar tectónica (placas, volcanes dinámicos) — Everwild.

### 3.4 Navegación
- A* con costos en tiempo (segundos). Heurística = distancia euclidiana / velocidad_máxima.
- `VEL_BASE` debe ser en m/s, no en celdas/min.
- Pendiente: costo = `distancia_metros * (1 + k * pendiente²) / velocidad`.
- Caché de rutas exitosas con invalidación por `cambiar_bioma`.
- Caché de fracasos ya implementada.

### 3.5 Simulación multiescala
- Separar geografía (estática, chunks) de entidades (dinámicas, posiciones continuas).
- El fuego ya tiene su propio sistema (`Fuego` con grilla). Bien.
- El agua (ríos, lagos) debería tener su propio sistema con niveles dinámicos.

### 3.6 Chunks y rendimiento
- Dividir el mapa en chunks de N×N celdas.
- Solo simular chunks con habitantes/animales.
- Spatial hashing para consultas de proximidad (fauna ya tiene grilla espacial).
- LOD: habitantes lejanos se actualizan cada N ticks.

### 3.7 Compatibilidad
- Versionar el formato de mundo (`version_generador` ya existe).
- No cambiar silenciosamente las dimensiones físicas: si un mundo viejo tiene `tam_celda_m=50`, mantenerlo.
- Migración: si se agrega un campo, el default debe ser razonable.

## 4. Algoritmos recomendados

| Dominio | Algoritmo actual | Recomendado |
|---|---|---|
| Elevación | fbm + simplex | Ridged Multifractal para montañas |
| Erosión | No hay | Hydraulic + Thermal (GPU o NumPy vectorizado) |
| Hidrología | cuencas simples | D8/D∞ flow routing |
| Biomas | tabla por elevación/temp/humedad | Whittaker diagram (elevación × precipitación) |
| Pathfinding | A* weighted (inadmisible) | A* con heurística octile × costo_min (admisible) o JPS |
| LOD | Atención cognitiva (solo habitantes) | Spatial LOD para terreno y fauna |

## 5. Dependencias entre módulos

```
generador.py → navegacion.py (Terreno)
simulacion.py → navegacion.py, vida.py, ecologia.py, tecnologia.py, ...
vida.py → sim (habitantes, refugios, relaciones)
tecnologia.py → sim (recetas, inventos, inventario)
agentes/mente.py → sim (decidir, estado)
agentes/cerebro_cognitivo.py → sim + Cognitive Engine
persistencia/sim_io.py → sim, mundo_io
api/vivo.py → sim, mundo, cerebro
api/servidor.py → sim_io, mundo_io
ui/*.js → api (REST + WebSocket)
```

Acoplamiento crítico: `sim.estado_publico()` genera JSON para el visor. El motor conoce al renderer.

## 6. Riesgos para mundos guardados

- Cambiar `ALTURA_MAX_M` escala: los mundos viejos tienen elevación en metros con la escala vieja. Si se cambia la fórmula, los mundos viejos no se regeneran (se cargan de SQLite). El terreno se reconstruye de las capas guardadas, no del generador. Así que el fix es seguro para mundos viejos (no se regeneran).
- Cambiar `VEL_BASE`: afecta la velocidad de movimiento en mundos viejos. Si se cambia, los habitantes caminan a distinta velocidad. Pero como `VEL_BASE` se usa en tiempo real (no guardado), el cambio es inmediato y seguro.
- Cambiar el formato de estado (agregar campos): los mundos viejos tienen el campo en None. Hay que manejar el default.

## 7. Plan de implementación por etapas

### Etapa 1 — Fix de unidades (1-2 días)
1. Convertir `VEL_BASE` a m/s: `VEL_CAMINAR_MPS = 1.33`.
2. Calcular `vel_celdas_por_seg = VEL_CAMINAR_MPS / tam_celda_m`.
3. Escalar el costo de pendiente por `tam_celda_m`.
4. Verificar que la heurística del A* sea admisible (multiplicar por `costo_min`).
5. Actualizar `r_habla`, `r_vista`, etc. para usar metros consistentemente.

### Etapa 2 — Fix del generador (2-3 días)
1. Escalar todos los parámetros de fbm por `tam_celda_m`.
2. Escalar `_a_metros` por `tam_celda_m / 50` (ya hecho).
3. Agregar erosión hidráulica (D8) para ríos.
4. Verificar que la pendiente mediana sea ~1-2 a cualquier escala.

### Etapa 3 — Reducir payload (1 día)
1. Enviar solo campos necesarios al visor (id, x, y, vivo, accion, nombre).
2. Enviar detalle solo para el habitante seleccionado.
3. Usar dirty flag: solo enviar habitantes que se movieron.

### Etapa 4 — Caché de rutas (1 día)
1. Cachear rutas exitosas con key (origen, destino).
2. Invalidar por `cambiar_bioma` y por tiempo.
3. Limitar tamaño de caché (LRU).

### Etapa 5 — Desacoplar motor/renderer (1-2 semanas, SDD)
1. Mover la simulación a un proceso/thread separado.
2. Comunicación por cola (multiprocessing.Queue o Redis).
3. El renderer solo recibe deltas.
4. El motor no conoce al visor.

### Etapa 6 — Chunks y LOD (1-2 semanas, SDD)
1. Dividir el mapa en chunks de 64×64 celdas.
2. Solo simular chunks con entidades.
3. LOD: habitantes lejanos se actualizan cada N ticks.
4. Spatial hashing para fauna y proximidad.

## 8. Primer cambio concreto propuesto

**Etapa 1, punto 1-2**: Convertir `VEL_BASE` de celdas/min a m/s.

Cambio en `navegacion.py`:
```python
VEL_CAMINAR_MPS = 1.33  # 4,8 km/h en metros por segundo
# en Terreno.__init__:
self.vel_celdas_por_seg = VEL_CAMINAR_MPS / tam_celda_m
```

Y en el costo:
```python
costo = mult * (1.0 + 8.0 * np.minimum(self.pendiente, PENDIENTE_MAX) ** 2)
# costo está en "segundos por celda" (tiempo para cruzar una celda)
# velocidad = 1.0 / costo  (celdas por segundo)
```

Esto hace que la velocidad sea consistente a cualquier resolución.

¿Aprobás este primer cambio?
# Mundo Vivo — Estado de trabajo (para continuar en nuevo chat)

Fecha: 2026-11-25. Rama: `etapa1-unidades-fisicas` (no commiteado, no pusheado).

## Lo que se hizo en esta sesión

### Etapa 3 — Payload liviano (COMPLETA, 465 tests pasan)
- `HabitanteSim.a_publico_mapa()`: solo lo que dibuja el mapa (id, x, y, vivo, acción, sexo, emoción, antorcha).
- `Simulacion.estado_publico_liviano(bloques=False)`: mensaje de 10 Hz sin fuego, estructuras, colonias ni barras finas.
- El bloque pesado (fuego, estructuras, colonias, senderos, vitales) se manda **una vez por segundo**.
- `_vitales_sucios()`: salud/sed/energía/hambre/temp/frío solo de vivos que cambiaron.
- UI: `aplicarEstado` mergea en vez de reemplazar; el panel lee las barras del estado mergeado.
- Tests nuevos: `tests/test_estado_liviano.py` (4) + integración WS en `tests/test_vivo.py` (1).

### Etapa 1 — Unidades físicas (COMPLETA, 460 tests pasan)
- `navegacion.py`: `VEL_BASE` (1.6 celdas/min) → `VEL_CAMINAR_MPS = 1.33` m/s.
- Costo de A* en **segundos** por celda: `(tam_celda_m / VEL_CAMINAR_MPS) * mult * (1 + 8 * pendiente²)`.
- `velocidad_en()` = `60.0 / costo` (consistente a cualquier resolución).
- Heurística del A* **admisible**: octile × `(tam_celda_m / VEL_CAMINAR_MPS)`. Sin weighted A*.
- Tope de velocidad de 4× (trepar cuesta pero no es tortuga).
- `tam_celda_m` guardado en `Terreno`.
- `tests/test_senderos.py`: umbral actualizado a `tam_celda_m / 1.33`.
- Velocidad verificada: 1,33 m/s en terreno plano a 5 m y 50 m.

### Trabajo anterior (de sesiones previas, todo en working tree)
- **Persistencia de cerebros**: write-only → ahora lee y restaura (memorias, mapa espacial, pericia, ids, objetivo).
- **Autopsia**: dice el cerebro real (de `decisiones.modelo`), no el env del proceso.
- **`iniciar.sh`**: default cognitivo.
- **Sed**: forzado de replanificación desde umbral 55 (no 80). Logs de diagnóstico (`AGUA-CERCANA-NONE`, `SED-SIN-CAMINO`).
- **Curiosidad**: sube a umbral 70 cuando el cuerpo está cubierto y hay idea concreta.
- **Hábito**: el cognitivo mantiene la red, la ficha muestra "lo que aprendió por experiencia".
- **Spawn de inmigrantes**: respeta sexo elegido (modal).
- **Fase 8** (reproducción): pareja_id, infidelidad con traición, endogamia por colapso con penalización.
- **Lápida** en el mapa en vez de cruz.
- **Spawn count** en modal de crear mundo (2-100, default 4).
- **Barra de era** en el dock (Piedra → ... → Electricidad).
- **Zoom** botones + teclado (flechas, +, -).
- **Burbujas**: filtro de importancia, mood emoji, nombres resaltados en bold azul.
- **WORLD_ARCHITECTURE.md**: análisis arquitectónico completo + plan por etapas.

### Lo que se revirtió (porque el usuario dijo que andaba peor)
- `HZ_ESTADO` 10→2 → volvió a 10.
- Polling UI (5s/12s/15s) → valores originales.
- `PENDIENTE_MAX` 3→5 → volvió a 3.0.
- Escala de elevación en `_a_metros` → volvió a 3000 m fijo.

## Lo que falta

### Etapas de arquitectura (WORLD_ARCHITECTURE.md)
- **Etapa 2** — Fix del generador: escalar fbm por `tam_celda_m`, erosión hidráulica/térmica, D8/D∞.
- ~~**Etapa 3** — Reducir payload~~ (hecha, ver arriba).
- **Etapa 4** — Caché de rutas: exitosas (LRU) + fracasos (ya hecho).
- **Etapa 5** — Desacoplar motor/renderer: motor en proceso separado.
- **Etapa 6** — Chunks y LOD espacial.

### Contenido (PLAN_MEJORAS_MOTOR.md)
- **Fase 6 UI**: modal de spawn, dibujo de ruinas y senderos.
- **Fase 8**: celos/infidelidad con consecuencias (parcialmente hecho), cuello de botella genético (hecho).
- **Deuda**: hitos por dimensión, cráter sin excavar, versión desincronizada (0.9.9 vs 0.10.1).

### Everwild (pendiente, visión a largo plazo)
- Tectónica, hidrología dinámica (mareas, nuevos ríos), eventos climáticos, domesticación, agricultura, sociedad/comercio/economía, árbol tecnológico, eventos dinámicos, subsuelo/cuevas.

## Notas importantes
- Los agentes SDD (`sdd-explore`, etc.) no funcionan: modelo `mimo-v2.5-free` no existe. Todo se hace inline.
- Etapa 3 (payload) ya está: el bloque pesado viaja 1 vez por segundo, no 10. El A* sigue siendo el 66% del CPU; eso lo baja Etapa 4 (caché de rutas).
- Los mundos viejos (tierranordica, kratos) tienen el terreno generado con la pendiente rota. Solo mundos nuevos se benefician de Etapa 1.
- El usuario maneja commit, push y merge. Rama: `etapa1-unidades-fisicas`.

## Comandos útiles
- Tests: `PYTHONPATH=src:. .venv/bin/python -m pytest -q tests` (~2 min).
- Servidor: `PYTHONPATH=src python3 -m mundo_vivo --datos datos servir --puerto 8767`.
- Mundo nuevo: `./mundo.sh nuevo` o desde la UI.
- Autopsia: `./mundo.sh autopsia NOMBRE`.
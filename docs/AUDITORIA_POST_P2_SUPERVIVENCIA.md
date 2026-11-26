# Auditoría post-P2 — Supervivencia y acceso al agua

> Auditoría de SOLO LECTURA. No se modificó código, mundos, bases de datos ni configuración.
> Único artefacto: este informe. Fecha: 2026-11-26.
> Resultado: **BLOQUEADA** — no existe un mundo generado después de implementar P2.

## 1. Identificación del mundo y bases de datos analizadas

No se encontró ningún mundo generado **después** de P2. Evidencia (búsqueda en todo el filesystem,
excluyendo `.venv`):

- Mundo persistente real (único): `mundo_1763761029.db`, en
  `/home/cracken/Mimundo/mundo-vivo (2)/mundo-vivo/datos/mundos/`.
  - `creado_en = 2026-11-22T20:11:32`, `semilla = 1763761029`, `512×512`, `tam_celda_m = 50`.
  - 7 habitantes (2 muertos), no 10.
  - El checkout que lo contiene (`mundo-vivo (2)`) **no tiene el código de P2**
    (`_orilla_alcanzable` ausente en su `persistencia/sim_io.py`). Es un mundo **anterior a P2**.
- No existe `mundo_872674866` en ninguna parte del filesystem.
- `datos/mundos/` del repo principal (donde corre P2) **no contiene ningún `mundo_*.db`**: sólo
  `cognitiveAI.db`, `cerebros_cognitivos.db` (y sus `-wal`/`-shm`) y `datos.txt`.
- Los `mundo_*.db` en `/tmp/tmp*/` son **fixtures de tests** (mundo_2, mundo_3, mundo_5, mundo_7,
  mundo_9, mundo_11, mundo_42, mundo_77, mundo_777), no simulaciones reales, y ninguno es posterior
  a P2 (búsqueda `-newermt "2026-11-26 14:00"` sin resultados).

Bases de datos cognitivas (no aportan habitabilidad; se distinguen):
- `cerebros_cognitivos.db`: estado de cerebros cognitivos por mundo/habitante (puente cognitivo).
- `cognitiveAI.db`: base del motor Cognitive Engine (GOAP/Utility, determinista).
Ninguna contiene el mapa, las posiciones iniciales ni la validación de P2; esa información vive en
el `mundo_*.db` del mundo, que no existe post-P2.

## 2. Integridad y disponibilidad de los datos

- Mundo post-P2: **no disponible** (no existe).
- Mundo pre-P2 `mundo_1763761029.db`: íntegro y legible en modo lectura, pero **no válido** para
  auditar P2 (anterior a P2, 7 habitantes, otro checkout sin P2). No se usa como sustituto.

## 3. Habitabilidad inicial individual

No calculable: sin mundo post-P2 no hay posiciones iniciales validadas por P2 que auditar.

## 4. Cronología de los diez habitantes

No calculable: no hay mundo post-P2 con 10 habitantes.

## 5. Métricas globales

No calculable. No se inventan métricas. Falta el mundo post-P2.

## 6. Fallos detectados y evidencia

- **Falta el insumo de la auditoría**: no se generó ningún mundo tras implementar P2. Esta es la
  causa del bloqueo, no un fallo del motor.

## 7. Clasificación de causas por subsistema

- Generación/entorno de prueba: no se generó el mundo post-P2 en `datos/mundos/`. (No es fallo de
  motor, generador ni CCA: es ausencia de datos.)

## 8. Conclusión: qué funciona, qué no y qué falta demostrar

- No se puede afirmar ni negar que P0/P1/P2 funcionen en una simulación real: **falta el mundo
  post-P2**. Los tests (501 passing) validan el código, no la conducta observada.
- Falta demostrar con datos reales: nacimientos habitables, acceso al agua, detección de sed,
  enrutado, llegada, consumo, no repetición de fallos y supervivencia.

## 9. Próxima corrección recomendada

No implementar corrección (tarea de diagnóstico). Para poder auditar:

1. Generar un mundo post-P2 en el repo con P2, p. ej.:
   `PYTHONPATH=src python3 -m mundo_vivo --datos datos generar` (o `./mundo.sh generar`), con 10
   habitantes, y dejar que corra varios días simulados.
2. Anotar nombre del mundo, semilla, `creado_en` y confirmar que el `mundo_*.db` quedó en
   `datos/mundos/`.
3. Reejecutar esta auditoría sobre ese mundo (SELECT-only), sin tocar `mundo_872674866` ni mundos
   viejos.

## Qué falta (resumen para el usuario)

- Un mundo generado **después** de P2, con **10 habitantes**, en `datos/mundos/` del repo con P2.
- Confirmar su nombre/`creado_en`/semilla y que corrió tiempo simulado suficiente.
- Sin eso, la auditoría no puede producir métricas reales y no se inventan.
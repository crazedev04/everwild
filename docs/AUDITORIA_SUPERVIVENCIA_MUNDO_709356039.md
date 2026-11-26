# Auditoría de supervivencia — mundo_709356039

Mundo de campo real (no test), corrido con el **cerebro cognitivo** (`cognitive-engine`,
determinista, sin LLM). Lectura de solo lectura sobre `datos/mundos/mundo_709356039.db`.
Pausado: `estado_mundo.velocidad = 0.0`, `t_min = 26252`.

- Semilla `709356039`, `2048×2048`, `tam_celda_m = 5` (10,2 km), creado `2026-11-26T11:48:42`.
- **Pre-E1**: `meta` no tiene `world_uid` (corrió antes del aislamiento cognitivo).
- 4 habitantes vivos, `salud = 100` los cuatro. Ninguna muerte.
- 1841 decisiones (`modelo = cognitive-engine` en el 100%), 121 eventos, 23 diálogos.

## Supervivencia individual (todos vivos, salud 100)

| Hab | sed | hambre | energía | inventario |
|-----|-----|--------|---------|------------|
| Elena (h1) | 0.55 | 39.3 | 36.1 | — |
| Leo (h2) | 28.5 | 49.9 | 53.4 | arcilla×3 |
| Paula (h3) | 14.0 | 52.1 | 83.4 | cesta×13, vasija×14, frutos_secos×12, arcilla×2, fibra×2, hoja×3, palo×5 |
| Bruno (h4) | 1.3 | 40.6 | 49.2 | fibra×4, arcilla×3, hoja×3 |

Necesidades en rango, sin colapso. El ciclo de agua y comida funcionó perfecto (ver abajo).
**Los arreglos P0/P1/P2 de agua NO se validan con este mundo**: aquí el agua nunca fue el
problema (beber/ir_al_agua 100% aceptado). No atribuir a esos parches la supervivencia.

## Hallazgo central: `ir_hacia` rechazado el 100% de las veces (congelamiento social)

| Acción | Aceptadas / total | % |
|--------|-------------------|---|
| ir_hacia | **0 / 1217** | **0.0%** |
| explorar | 259 / 347 | 74.6% |
| esperar | 173 / 173 | 100% |
| juntar_comida | 43 / 43 | 100% |
| beber | 21 / 21 | 100% |
| dormir | 15 / 15 | 100% |
| comer | 13 / 13 | 100% |
| ir_al_agua | 12 / 12 | 100% |

- `ir_hacia` = 1217 decisiones (66% del total), **todas rechazadas** con `No ves a Elena; está lejos`.
- Repartido: Leo 438, Paula 392, Bruno 387. Elena 0 (ella explora).
- Ventana completa `t_min 23256 → 26251`: primeros 200 = 0 ok, últimos 200 = 0 ok. No es un
  transitorio: es un **bucle permanente**.
- Objetivo declarado `satisfy_compania`. El cerebro cognitivo propone `ir_hacia` hacia un
  habitante que no ve; el motor lo rechaza; **no hay plan B** (no cae a `explorar`/navegar hacia
  el último visto). El habitante repite la misma acción fallida tick tras tick.
- Consecuencia: Leo, Paula y Bruno quedan **congelados** ~3000 t_min. Elena es la única que
  explora, junta comida y sobrevive; los otros tres queman ciclos sin avanzar.

### Evidencia social
- Todos los `encuentro` son de `t_min = 480` (spawn conjunto). Después, 23 conversaciones
  decrecientes; la última social es ~`t_min 11583`. Luego sólo el bucle `ir_hacia`.
- La necesidad de compañía no se vuelve a satisfacer tras el spawn.

## Ciclo de agua y comida (sano)
- Agua: `beber` 21/21, `ir_al_agua` 12/12 (100%).
- Comida: `juntar_comida` 43/43, `comer` 13/13 (100%).
- Fabricación: 40 eventos (cesta_de_fibra, vasija_de_barro, frutos_secos). Paula es la que más
  produce (inventario lleno).

## Eventos menores
- `frio` 1, `enfermo` 2, `herida` 2, `podrido` 2, `hito` 1, `colonia` 2. Sin impacto en salud.

## Diagnóstico por subsistema
- **Supervivencia física**: OK. Agua, comida, temperatura y salud en verde.
- **Navegación social (`ir_hacia`)**: ROTO. 0% aceptación, sin fallback → congelamiento.
- **Cognición (cognitive-engine)**: determinista; el planificador no reencola una alternativa
  cuando `ir_hacia` se rechaza por objetivo no visible.
- **Economía/fabricación**: OK (40 fabricaciones, inventario coherente).

## Causa raíz (hipótesis con evidencia)
`satisfy_compania` emite `ir_hacia(objetivo)` que exige **visibilidad** del objetivo. Si el
objetivo está lejos, el motor rechaza con `está lejos` y el cerebro **no** convierte eso en
`explorar` hacia la última posición conocida. Elena (exploradora) nunca cae en el bucle; los
demás sí. Es la clase "quedarse clavados sin poder explorar" ya anotada en `CLAUDE.md`.

## Recomendación (no aplicada en esta auditoría)
1. `ir_hacia` a objetivo no visible debe degradar a `explorar`/navegación hacia el último visto,
   no rechazarse en seco.
2. Si `ir_hacia` se rechaza N veces seguidas, forzar `explorar` (romper el bucle).
3. Revalidar con un mundo post-E1 (con `world_uid`) y, si es posible, con el híbrido+LLM.

## No tocado
Datos del mundo intactos (solo lectura). Sin commits. La auditoría no modificó el motor.
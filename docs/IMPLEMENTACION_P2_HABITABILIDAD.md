# Implementación P2 — Habitabilidad del generador (acceso real al agua al inicio)

> Implementación de P2 del informe `docs/AUDITORIA_GENERACION_NAVEGACION_AGUA.md`, sobre P0 y P1 ya
> aplicados (`docs/IMPLEMENTACION_P0_AGUA.md`, `docs/IMPLEMENTACION_P1_AGUA.md`). No se rehicieron
> P0/P1. No se tocaron mundos guardados, bases de datos, biomas, hidrología ni el módulo de
> navegación. Sin commits ni push.

## 1. Problema detectado

`elegir_inicio` (`persistencia/sim_io.py`) elegía el punto de partida con estos criterios: celda
caminable, llana, a ≤3 celdas de agua dulce y en una componente transitable ≥ `MIN_ZONA_CONECTADA`
(3000 celdas). **No** comprobaba que existiera una ruta real a una orilla de agua, y si ninguno de
los 40 candidatos cumplía el umbral caía en `return cand[0]`, aceptando en silencio una celda que
podía estar en una componente sin agua a distancia recorrible. El agua podía estar cerca
geométricamente pero ser inalcanzable para A* (acantilados, lagos/océanos intransitables, lava).

Consecuencia: habitantes que arrancan sin acceso real al agua y mueren de sed sin poder llegar
(cf. hipótesis H2/H3 del informe).

## 2. Flujo de generación inspeccionado

- `generador/pipeline.py`: produce el mapa por etapas deterministas; la hidrología y los biomas no
  se modificaron.
- `persistencia/mundo_io.crear_mundo`: genera y guarda el mapa; no valida transitabilidad.
- `persistencia/sim_io.elegir_inicio`: selecciona el inicio (único punto donde se decidió validar).
- `persistencia/sim_io.crear_habitantes_iniciales` y `api/servidor._generar_en_hilo`: llaman a
  `elegir_inicio` al poblar el mundo; si `elegir_inicio` rechaza, la generación falla de forma
  explícita (el visor muestra el error).
- `motor/navegacion.Terreno`: API pública usada para validar sin tocar el módulo:
  `caminable`, `agua_adyacente`, `componente`, `buscar_camino(origen, destino, max_exp)`.

La validación se puso en `elegir_inicio` (problema exclusivo de selección inicial), **sin** tocar
`motor/navegacion.py` (restricción respetada): el BFS de orillas y el enrutado viven en `sim_io` y
reutilizan `Terreno.buscar_camino` como juez real de alcanzabilidad.

## 3. Solución implementada y archivos modificados

`src/mundo_vivo/persistencia/sim_io.py`:
- Constantes acotadas: `TOPE_ORILLAS=8`, `TOPE_BFS_ORILLA=4000`, `RADIO_ORILLA_MIN=12`,
  `RADIO_ORILLA_M=2000.0`, `MAX_CANDIDATOS_INICIO=40` (antes el 40 estaba hardcodeado).
- `_presupuesto_camino(tam_celda_m)`: devuelve el **mismo** `nodos_camino` que usa el motor a esa
  resolución (`min(120000, 12000*(50/tam)^2)`), así "habitable al generar" = "enrutable dentro del
  presupuesto de producción".
- `_orilla_alcanzable(t, x, y, presupuesto)`: reúne orillas caminables con un BFS acotado (tope de
  nodos y radio) y las enruta con `Terreno.buscar_camino`; devuelve la primera orilla enrutable o
  `None`. Si la celda ya es orilla (`agua_adyacente`), es habitable sin caminar.
- `elegir_inicio`: tras filtrar candidatos y ordenarlos (determinista), recorre hasta
  `MAX_CANDIDATOS_INICIO`, exige `componente >= MIN_ZONA_CONECTADA` **y** `_orilla_alcanzable`
  no `None`; devuelve el primero que cumple. **Eliminado el `return cand[0]`**: si ninguno cumple,
  lanza `ValueError` explícito.

Tests:
- `tests/test_sim_io.py::TestHabitabilidadInicio` (7 tests deterministas, mapas chicos).
- Ajuste de fixtures que generaban mundos irreales: `tests/test_api.py`, `tests/test_vivo.py` y un
  test de `tests/test_fauna.py` pasan a mundos `128×128` a `tam_celda_m=50` (ver §7).

## 4. Criterio exacto de "habitable"

Una celda inicial `(x, y)` es habitable si cumple **todo**:
1. `t.caminable(x, y)` (costo finito).
2. `t.componente(x, y) >= MIN_ZONA_CONECTADA` (3000 celdas conectadas).
3. Existe una orilla `o` (celda caminable con `agua_adyacente(o)`) tal que
   `t.buscar_camino((x, y), o, presupuesto)` **no** es `None`, con
   `presupuesto = _presupuesto_camino(tam) = min(120000, 12000*(50/tam)^2)`.
   La orilla se busca con un BFS acotado (radio `max(12, 2000/tam)` celdas, tope 4000 nodos) y se
   enrutan hasta 8 orillas por inicio, por orden determinista de cercanía.

No basta con distancia euclidiana, detección geométrica de agua, ni una orilla "vista" por BFS: el
juez es el A* real dentro del presupuesto de producción.

## 5. Límites de rendimiento y complejidad

- Por inicio: 1 BFS acotado (≤4000 nodos, radio acotado) + ≤8 llamadas a `buscar_camino`, cada una
  con presupuesto `nodos_camino`. En el caso normal la primera orilla cercana se enruta en el
  primer o segundo intento.
- `elegir_inicio` prueba como mucho `MAX_CANDIDATOS_INICIO=40` candidatos y corta en el primero
  habitable; el orden es determinista (distancia al centro, desempate por coordenada).
- Peor caso (mundo sin inicio habitable): 40 candidatos × (BFS + 8 A*), acotado; termina en
  `ValueError` (rechazo explícito), no en un bucle.
- No se recorre el mapa entero por candidato más allá de `componente` (BFS que ya existía) y el BFS
  de orillas acotado.

## 6. Comportamiento cuando no hay candidatos válidos

`elegir_inicio` lanza `ValueError("No se encontró un lugar habitable con acceso real al agua
(orilla enrutable por A*).")`. No hay `cand[0]` silencioso. La generación del mundo falla de forma
visible (el trabajo de la API reporta `error`), y no se crean habitantes en una ubicación no
validada. Esto es "rechazar el mundo" (una de las dos opciones del informe, §10-P3); "recolocar"
queda fuera de alcance.

## 7. Pruebas agregadas y resultados

`TestHabitabilidadInicio` (mapas controlados, sin mundos aleatorios):
1. `test_1_orilla_alcanzable_se_acepta` — río abierto, orilla enrutable: aceptada.
2. `test_1b_inicio_ya_en_orilla_es_habitable` — celda ya adyacente: habitable sin caminar.
3. `test_2_agua_infranqueable_se_rechaza` — agua tras muro de lava: `None` de ese lado; el lado
   con agua sí.
4. `test_3_entre_varios_candidatos_elige_habitable` — dos zonas de agua (una con orilla alcanzable,
   otra aislada por lava): elige la alcanzable.
5. `test_4_sin_candidato_habitable_comportamiento_explicito` — lago rodeado de lava: `ValueError`.
6. `test_5_determinismo_misma_entrada_mismo_resultado` — misma entrada, mismo resultado.
7. `test_6_no_crea_en_ubicacion_rechazada` — todo inicio devuelto pasa `_orilla_alcanzable`.

Cobertura de los 6 requisitos obligatorios: 1↔test1; 2↔test2; 3↔test3; 4↔test4; 5↔test5;
6↔test6.

Resultado: `7 passed`. Suites relacionadas (`test_sim_io`, `test_fauna`, `test_motor`,
`test_api`, `test_vivo`) verdes; suite completa: ver §8.

### Fixtures ajustadas (no es omitir validación)

Los tests de API/vivo generaban mundos de 64–128 celdas a `tam_celda_m=5` (por defecto). A 5 m esos
mundos son diminutos (≈0,3–0,6 km) y su componente transitable máxima queda muy por debajo de
`MIN_ZONA_CONECTADA=3000`; antes "pasaban" sólo por el `cand[0]` silencioso que P2 elimina. Se
pasaron a `128×128` a `tam_celda_m=50` (convención del proyecto para mundos de test, ver `CLAUDE.md`),
donde sí son habitables. La validación de habitabilidad corre completa en todos los casos; no se
relajó ninguna validación.

## 8. Limitaciones pendientes

- No se valida que **cada** grupo de `_puntos_de_partida` tenga orilla a distancia recorrible: se
  garantiza el inicio y que el resto arranque en la misma componente; la habitabilidad fina de cada
  punto lejano no se cubre (fuera de alcance de P2).
- "Rechazar" es la única política ante un mundo sin inicio habitable; no hay "recolocar".
- No se calibró `MIN_ZONA_CONECTADA` ni los topes contra un mundo largo real; los topes son
  conservadores y deterministas.
- No se tocó el generador, biomas, hidrología, navegación, CCA ni el cerebro cognitivo.
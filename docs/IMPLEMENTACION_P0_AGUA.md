# Implementación P0 — Accesibilidad del agua y recuperación de navegación

> Implementación de las correcciones P0 del informe `docs/AUDITORIA_GENERACION_NAVEGACION_AGUA.md`.
> Alcance: P0.1 (presupuestos coherentes), P0.2 (caché de fallos), P0.3 (recuperación).
> No se tocó el generador, biomas, hidrología, radios de detección, feedback (P1) ni balance.
> No se hicieron commits ni push. No se modificaron bases de datos ni mundos.

## 1. Causa técnica corregida

- **C1 (presupuestos incoherentes):** `agua_cercana` (BFS) usaba `nodos_bfs`, cuatro veces mayor
  que `nodos_camino` (A*). La detección ofrecía orillas que el enrutado no podía cerrar dentro de
  su presupuesto, produciendo `SED-SIN-CAMINO` con la celda ya detectada.
- **C2 (caché negativa permanente):** `buscar_camino` anotaba en `_fracasos` tanto los destinos
  genuinamente inalcanzables como las búsquedas que sólo habían **agotado el presupuesto**
  (incompletas). Un falso negativo por presupuesto quedaba bloqueado para siempre (hasta cambiar
  el mapa), dejando al habitante inmóvil repitiendo el mismo destino.

## 2. Archivos y funciones modificados

- `src/mundo_vivo/motor/simulacion.py`
  - `_calcular_escala`: `nodos_camino` es ahora la **única fuente de verdad** de presupuesto;
    `nodos_bfs` queda como alias de `nodos_camino` (compatibilidad). No se aumenta el presupuesto
    del A*; se iguala la BFS al del A* (que es menor).
  - `agua_cercana`: la BFS usa `self.nodos_camino` y **confirma cada orilla candidata** con
    `buscar_camino(origen, c, nodos_camino)` antes de ofrecerla (máx. `TOPE_VERIF = 8`
    verificaciones). Si la orilla no es enrutable, sigue buscando otra; si no hay ninguna, devuelve
    `None`.
- `src/mundo_vivo/motor/navegacion.py`
  - Constante `TOPE_INCOMPLETOS = 2048` y conjunto `_incompletos` (nuevo).
  - `buscar_camino`: la rama de **presupuesto agotado** llama a `_anotar_incompleto` (no a
    `_anotar_fracaso`); la rama de **lista de abiertos vacía** sigue llamando a `_anotar_fracaso`
    (inalcanzabilidad genuina). La búsqueda comprueba ambos conjuntos al inicio.
  - `_anotar_incompleto` (nuevo): registra la búsqueda incompleta en `_incompletos`, acotada y con
    recambio (se vacía al superar `TOPE_INCOMPLETOS`).
  - `olvidar_fracasos`: ahora vacía `_fracasos` **y** `_incompletos` (lo llama `cambiar_bioma`).
- `tests/test_motor.py`: reemplazo del test de caché negativa por cuatro tests de la nueva
  semántica + helper `_terreno` (mapas sintéticos deterministas).
- `tests/test_fauna.py`: dos tests nuevos en `TestAguaAlcanzable` (coherencia con presupuesto real
  y no-clavado con presupuesto mínimo).

> Nota: `navegacion.py` y `simulacion.py` ya tenían cambios sin commitear en el árbol de trabajo
> antes de esta tarea (reformateo y la máscara `_agua_ady_mask`). Esos cambios preexistentes no son
> de esta implementación; lo de esta tarea es exclusivamente lo listado arriba.

## 3. Comportamiento anterior y nuevo

| Aspecto | Antes | Ahora |
|---|---|---|
| Presupuesto detección | `nodos_bfs` = 4× `nodos_camino` | `= nodos_camino` (coherente) |
| Destino ofrecido por `agua_cercana` | 1ª orilla alcanzable por BFS (aunque el A* no la cierre) | 1ª orilla **enrutable** confirmada con A* |
| Fallo por presupuesto | `_fracasos` (definitivo) | `_incompletos` (reciclable, reintentable) |
| Fallo por componente cerrada | `_fracasos` | `_fracasos` (definitivo) — sin cambio |
| Habitante sin agua enrutable | podía clavarse en destino cacheado | `agua_cercana` da `None` → el cerebro espera/replanifica o prueba otra fuente |

## 4. Decisiones sobre presupuestos y caché

- **Presupuesto (P0.1):** igualar la BFS del detector al presupuesto del enrutado (una sola
  constante, `nodos_camino`) en vez de multiplicar el A* por cuatro. Multiplicar el A* habría
  encarecido **toda** la navegación del motor (explorar, fuego, personas), que es justo lo que el
  alcance prohíbe. Igualar hacia abajo no pierde agua enrutable (la que la BFS veía con presupuesto
  mayor y el A* no cerraba era, por definición, inservible) y mantiene el costo acotado.
- **Verificación por candidato:** confirmar la orilla con `buscar_camino` es la única forma de
  garantizar el contrato "la detección no ofrece lo que el enrutado no puede comprobar". Costo:
  una llamada de A* por orilla candidata; el viaje exitoso queda en la caché LRU de rutas, así que
  el `buscar_camino` posterior de `_aplicar` es un hit. Acotado a 8 verificaciones por búsqueda.
- **Caché (P0.2):** separar dos causas de fallo. Inalcanzabilidad **probada** (abiertos vacíos) →
  `_fracasos` (definitivo, evita trabajo redundante). Presupuesto **agotado** (incompleto) →
  `_incompletos` (acotado, con recambio, reintentable). Ambas se vacían al cambiar el mapa. Así se
  conserva la optimización anti-ráfaga sin bloquear destinos que podrían ser alcanzables.

## 5. Pruebas agregadas y resultados

`tests/test_motor.py` (Terreno sintético determinista):
- `test_destino_inalcanzable_se_cachea_como_definitivo` — inalcanzable real va a `_fracasos`, no a
  `_incompletos`; no se rebusca con presupuesto alto; `cambiar_bioma` lo olvida.
- `test_busqueda_incompleta_no_se_marca_como_imposible` — presupuesto agotado va a `_incompletos`,
  no a `_fracasos`; tras `olvidar_fracasos` se reconsidera y llega.
- `test_un_exito_nunca_se_guarda_como_fracaso` — un camino existente no ensucia ninguna caché.
- `test_cambiar_el_mapa_olvida_las_incompletas` — `cambiar_bioma` vacía `_incompletos`.

`tests/test_fauna.py` (`TestAguaAlcanzable`, sim 192×192 a 50 m):
- `test_agua_cercana_solo_ofrece_orillas_enrutables_con_presupuesto_real` — para muchas posiciones,
  si `agua_cercana` devuelve `c`, `buscar_camino(c0, c, sim.nodos_camino)` no es `None`.
- `test_agua_cercana_no_se_clava_si_el_presupuesto_no_alcanza` — con `nodos_camino = 1` no ofrece
  orilla inalcanzable (devuelve `None` o celda enrutable con presupuesto 1) y no se cuelga.

Cobertura de los 7 requisitos obligatorios:
1. BFS→A* con presupuesto coherente: `test_agua_cercana_solo_ofrece_orillas_enrutables...`.
2. Incompleta no es inaccesibilidad definitiva: `test_busqueda_incompleta...`.
3. Inalcanzable real sin intentos infinitos: `test_destino_inalcanzable...` (caché definitiva).
4. Reconsiderar al cambiar condiciones/expirar descarte: `test_busqueda_incompleta...` +
   `test_cambiar_el_mapa_olvida_las_incompletas`.
5. Fuente alternativa: `agua_cercana` salta orillas no enrutables y devuelve otra (o `None`); el
   flujo del cerebro prueba `buscar_agua_lejos`/espera. Verificado por el test de presupuesto mínimo.
6. La caché evita trabajo redundante con fallo válido: `test_destino_inalcanzable...` (2ª llamada
   con presupuesto alto sigue `None` sin rebuscar).
7. Sin regresiones: suite completa.

Resultado de los tests nuevos/afectados: `8 passed` (TestNavegacion + TestAguaAlcanzable).

## 6. Suite y linter

- **Suite completa:** `484 passed, 1 warning in 213.86s` (0 fallos). La suite base tenía 452; los
  nuevos tests y los previos suman 484.
- **Linter:** el proyecto **no tiene Ruff instalado ni configurado** (`requirements-dev.txt` sólo
  fija `httpx`; no hay `pyproject.toml`/`ruff.toml` y `ruff` no está en el `.venv`). Como
  verificación equivalente se corrió `python -m py_compile` sobre los cuatro archivos modificados:
  OK. No se instaló nada (fuera de alcance y sin red).

## 7. Riesgos o limitaciones pendientes

- La verificación por candidato añade un A* por orilla en la búsqueda de agua; acotado a 8 y
  amortiguado por la caché de rutas. Vigilar latencia en mundos grandes a 5 m/celda.
- `_incompletos` con recambio bruto: bajo ráfagas muy grandes de viajes incompletos distintos puede
  vaciarse y reintentar; es el compromiso aceptado para no bloquear destinos alcanzables.
- No se midió el efecto real sobre un mundo largo (no se corrieron mundos; alcance de solo código
  y tests deterministas).
- `navegacion.py`/`simulacion.py` arrastran cambios sin commitear previos a esta tarea; el diff
  git los mezcla con los de P0.

## 8. Pendiente explícito para P1 (y posteriores)

- **P1 — feedback de acciones:** `ok=1` debe distinguir "ruta iniciada" de "llegó" y "bebió"; no
  abordado aquí.
- **P1 — radio de detección:** `r_agua_cerca`/`r_agua_lejos` (3–7 km) siguen sin acotarse a lo
  recorrible antes de morir; no modificado.
- **P2 — validación de habitabilidad:** el generador sigue sin garantizar orilla alcanzable por
  componente; no modificado.
- **Diagnóstico persistente** (`SED-SIN-CAMINO` como evento) y heurística admisible: pendientes.

**Las muertes por sed NO se declaran resueltas.** Esta entrega corrige el bloqueo de navegación
(P0), pero faltan el feedback de acciones, el radio de detección y la validación de habitabilidad.
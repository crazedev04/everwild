# E1 — Aislamiento cognitivo entre mundos

## Problema

El cerebro cognitivo persistía en un único `cerebros_cognitivos.db` compartido por todos los
mundos de una carpeta, y los `brain_id` se formaban con `sim.ident` (`mundo:d0:h1`). Dos mundos
distintos —incluso con la misma semilla— compartían repositorio y namespace, así que un habitante
podía recuperar el cerebro de otro mundo con el mismo id local.

## Solución

1. **Identidad persistente por mundo** (`persistencia/mundo_io.py`):
   - `WORLD_UID_KEY = "world_uid"`.
   - `world_uid(con)`: lee `meta.world_uid`; si no existe, genera un `uuid4().hex`, lo persiste y
     lo devuelve. Estable entre reinicios e importaciones; distinto por mundo aunque la semilla y
     el nombre coincidan.
   - `crear_mundo` persiste el `world_uid` en `meta`.
   - `cargar_simulacion` (`persistencia/sim_io.py`) puebla `meta["world_uid"]` (lo genera si falta)
     antes de construir la `Simulacion`.
   - `Simulacion.__init__` levanta `self.world_uid = meta.get("world_uid")`.

2. **Base cognitiva por mundo** (`agentes/cerebro_cognitivo.py`):
   - La ruta del repositorio pasa de `cerebros_cognitivos.db` a `cerebros_<world_uid>.db`, en la
     misma carpeta que la base del mundo.
   - `CerebroCognitivo._world_uid` conserva el uid para namespazar la identidad.

3. **`brain_id` namespaced**: `BrainIdentity.brain_id = f"{world_uid}:d{dim}:h{id}"`.

## Compatibilidad

- La base legacy `cerebros_cognitivos.db` **no se borra ni se migra**. Los mundos viejos generan su
  `world_uid` la primera vez que cargan y pasan a usar su archivo propio.
- Un `con` sintético sin tabla `meta` (sólo aparece en tests) no tiene identidad persistente: cae al
  archivo compartido legacy, **nunca** a `:memory:` (que perdería el cerebro al reabrir).

## No se tocó

Selección de metas, utilidad, `satisfy_compania`, navegación, necesidades, personalidades,
generación de mundo, semillas ni terreno.

## Verificación

- `tests/test_aislamiento_cognitivo.py` (10 tests): UID distinto con misma semilla, persistencia
  tras reabrir, UID ≠ semilla ≠ nombre, no colisión de ids locales, base por mundo distinta,
  lectura A no ve B y viceversa, guardar B no modifica A, concurrencia, recuperación sin mezcla,
  legacy intacta.
- Suite MV completa: ver `CHANGELOG.md`.
- Suite CE completa: `287 passed`.
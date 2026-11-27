# Integración remota de Cognitive Engine (CCA)

Primera vía de ejecución **remota** de la cognición. Mundo Vivo sigue siendo dueño
exclusivo del mundo físico (valida y ejecuta acciones); CCA es dueño de la cognición y
su persistencia. El tick de simulación **nunca espera** una respuesta cognitiva.

## Dependencia (instalación reproducible)

Se consume la **distribución** de Cognitive Engine (rama `feat/distribution`), no una
copia local. Instalación editable para desarrollo:

```bash
# desde el repo hermano, en la rama feat/distribution
cd "../Cognitive Engine" && git switch feat/distribution
# desde mundo-vivo, en su venv:
.venv/bin/pip install -e "../Cognitive Engine"
```

No hay paquete publicado en PyPI; no se declara una versión inexistente. La cognición
vive del otro lado del servicio: **no** se copian `CcaClient`, Runtime ni módulos
internos de CCA dentro de Mundo Vivo.

## Configuración

```bash
export MUNDO_VIVO_CEREBRO=remoto         # override global (sólo para mundos viejos sin la clave)
export CCA_URL=http://127.0.0.1:8000     # servicio CCA
export CCA_TOKEN=...                     # token restringido (ciclo por cerebro)
export CCA_TOKEN_ADMIN=...               # token admin `*` (crear/autorizar cerebros)
```

`MUNDO_VIVO_CEREBRO=cognitivo` (por defecto) sigue usando el modo embebido; `remoto`
usa el servicio. El modo remoto **no** abre ni escribe la base cognitiva local.

> **Arranque rápido (desarrollo local).** El servicio CE arrancado sin `--token` ni
> `CCA_TOKEN` expone el token determinista `local-8000` con acceso total. Mundo Vivo
> debe apuntar a él y presentar ese token, o CE rechazará el alta de cerebros con
> **HTTP 401** (antes silencioso; hoy queda registrado con la causa raíz en el log):
>
> ```bash
> CCA_URL=http://127.0.0.1:8000 CCA_TOKEN=local-8000 \
>   .venv/bin/python -m mundo_vivo --datos datos servir --puerto 8767
> ```
>
> Sin `CCA_TOKEN`, el mundo remoto abre pero **no registra cerebros** (401) y la
> simulación sigue sin cognición. Revisá `datos/logs/mundo.log` ante un
> `registro cerebros CE: {..., "errores": N}` con N > 0.

### Modalidad por mundo (switch del modal)

El modal de creación tiene el switch **Conectar con Cognitive Engine**. La preferencia
queda en `meta.cerebro_remoto` del propio mundo y **prevalece sobre el entorno**:

1. `cerebro_remoto = true` → usa CCA (remoto).
2. `cerebro_remoto = false` → usa el sistema de cerebros actual, sin importar
   `MUNDO_VIVO_CEREBRO`.
3. Mundo viejo sin la clave → comportamiento anterior (`MUNDO_VIVO_CEREBRO`).

Así conviven mundos locales y remotos. La conexión (tokens, URL) se toma del entorno;
el frontend no expone credenciales. Si CCA no responde al abrir el mundo, el alta de
cerebros queda `error`/pendiente en `cerebros_ce` y la simulación continúa (no hay
fallback silencioso a cerebros locales: el mundo sigue en modo remoto).

## Arquitectura y flujo

- `MundoVivoRemoteAdapter` (`agentes/remote/cca_adapter.py`): usa sólo la API pública
  `cognitive_engine.api.client.CcaClient`. Inicia un **hilo emisor** (cola acotada) y un
  **hilo consumidor** (`pending_proposals` por cerebro, contrato real de entrega
  retry-until-ACK) con caché por habitante. `client_seq` monótono por cerebro; el reintento
  reutiliza el mismo `client_seq` (mismo `msg_id` ⇒ idempotente). `ack` tras entregar.
- `CerebroCognitivoRemoto` (`agentes/cerebro_cognitivo_remoto.py`): subclase de
  `CerebroCognitivo` que **reutiliza toda la traducción de dominio** (necesidades,
  creencias, catálogo, traductores capacidad→acción) sin instanciar Service/Repository/
  scheduler. `decidir` encola la observación y devuelve la propuesta cacheada o
  `esperar`. Propuesta obsoleta (tick viejo) ⇒ rechazo local + resultado `rejected`.
  `registrar_resultado` correlaciona por `proposal_id` y envía accepted/rejected.
- Ciclo de vida: `crear_cerebro` en `api/vivo.py` añade `remoto`; `Ejecutor.cerrar`
  llama `cerebro.cerrar()` (une hilos y cierra el cliente).

## Adaptación del entorno físico a CE

Mundo Vivo es la **fuente de verdad del estado físico**; CE es dueño de la cognición.
El adaptador remoto traduce ambas direcciones sin duplicar lógica cognitiva:

### Necesidades fisiológicas (MV → CE)

`_observacion_remota` incluye `needs: dict[str, float]` en la observación. CE
(`Observation.needs`, `sync_from_host`) refleja el estado pero **no lo persiste como
autoridad** ni lo decae mientras el host lo reporte. Escala invertida para sed/hambre
(MV 0=ok, 100=muerte → CE 100=ok, 0=crítico); energia/salud ya son 100=ok en MV. Se
mandan `sed`, `hambre`, `energia`, `salud`; CE crea las que no existan con decaimiento
local 0 (host-driven). MV nunca permite que CE sobrescriba los valores físicos.

### Traducción de acciones abstractas (CE → MV)

CE emite capacidades genéricas (`ActionCatalog.humanoid_defaults`): `explore`,
`move_to`, `gather`, `drink`, `eat`, `rest`, `wait`. `_traducir` del remoto las mapea
a las capacidades físicas reales de MV, preservando parámetros/destinos:

| CE (abstracta) | MV (física) |
|---|---|
| `explore` | `ir` a destino de exploración |
| `move_to` (position) | `ir` al destino; `luego: beber/comer` según `need` |
| `gather` (need=sed) | `beber` / `ir` al agua |
| `gather` (otra) | `comer` / `juntar` |
| `drink` | `beber` / `ir` al agua |
| `eat` | `comer` / `juntar` |
| `rest` | `dormir` |
| `wait`/`esperar` | `esperar` |
| desconocida | `accion_invalida` (error explícito, no espera silenciosa) |

Una acción abstracta que no puede concretarse (sin destino, sin comida) devuelve
`esperar` corto para que CE replanifique; una acción **desconocida** produce
`accion_invalida` (resultado `rejected` a CE), nunca `esperar` silencioso.

### Obsolescencia de propuestas

`propuesta_fresca` entrega la propuesta más **nueva** (LIFO) y marca EXPIRED en CE
las de tick viejo (`expire` del cliente), en vez de rechazar la vieja y dejar la
fresca atascada. Corrige la obsolescencia sistemática sin subir el umbral de 30 min.
La correlación observación→propuesta→resultado se mantiene por `proposal_id` y `client_seq`.

## Pruebas

`tests/test_cerebro_remoto.py`: unitarios del adaptador (no bloqueo, secuencia,
reintento sin duplicar, caché de propuestas, ACK, cierre) e **integración real** contra
`CcaHttpServer` de la distribución (observación → propuesta → resultado correlacionado).
Cubre además: `needs` en la observación, traducción de abstractas (`drink`/`eat`/`rest`/
`explore`/`move_to`/`gather`), `accion_invalida` para desconocidas, `propuesta_fresca`
(expira rancias, entrega fresca), y el circuito de supervivencia (CE propone drink →
MV ejecuta beber → sed baja → resultado accepted a CE) con motor real y con CE real.

## Limitaciones / pendientes

- **Migración de cerebros**: los cerebros actuales viven en la DB cognitiva local del
  modo embebido. En remoto deben existir en el repositorio del servicio CCA. El alta se
  hace por la API pública `POST /brains` (idempotente: 201 crea, 409 si ya existe), que
  el adaptador invoca al abrir el mundo. La migración de identidad/memoria (no sólo el
  alta) sigue **explícitamente pendiente**; no se improvisa conversión. Mundo Vivo y CCA
  no deben escribir la misma persistencia cognitiva a la vez.
- **Imports internos que aún permanecen** (a retirar en una etapa posterior): el modo
  embebido `cerebro_cognitivo.py` sigue importando `cognitive_engine.*` (Service,
  SQLiteBrainRepository, scheduler, componentes). El modo remoto no los usa.
- Para activar el modo remoto de forma segura falta: servicio CCA corriendo con los
  cerebros ya migrados, y `CCA_URL`/`CCA_TOKEN` configurados.
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

### Modalidad por mundo (switch del modal)

El modal de creación tiene el switch **Conectar con Cognition Chain**. La preferencia
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

## Pruebas

`tests/test_cerebro_remoto.py`: unitarios del adaptador (no bloqueo, secuencia,
reintento sin duplicar, caché de propuestas, ACK, cierre) e **integración real** contra
`CcaHttpServer` de la distribución (observación → propuesta → resultado correlacionado).

## Limitaciones / pendientes

- **Migración de cerebros**: los cerebros actuales viven en la DB cognitiva local del
  modo embebido. En remoto deben existir en el repositorio del servicio CCA (no hay
  endpoint de creación). La migración de identidad/memoria es una operación separada,
  **explícitamente pendiente**; no se improvisa conversión. Mundo Vivo y CCA no deben
  escribir la misma persistencia cognitiva a la vez.
- **Imports internos que aún permanecen** (a retirar en una etapa posterior): el modo
  embebido `cerebro_cognitivo.py` sigue importando `cognitive_engine.*` (Service,
  SQLiteBrainRepository, scheduler, componentes). El modo remoto no los usa.
- Para activar el modo remoto de forma segura falta: servicio CCA corriendo con los
  cerebros ya migrados, y `CCA_URL`/`CCA_TOKEN` configurados.
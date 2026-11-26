# A1 — Arquitectura objetivo de Mundo Vivo (consolidación de A0)

**Estado:** diseño de arquitectura objetivo, solo lectura del repositorio.
**Proyecto:** mundo-vivo (`everwild`)
**Ubicación:** `/home/cracken/Mimundo/mundo-vivo`
**Documento de partida:** `docs/AUDITORIA_ARQUITECTURA_MODULAR_A0.md`
**Fecha:** 2026-11-26

---

## Convenciones de clasificación

Cada afirmación técnica de este documento lleva una etiqueta:

- **VERIFICADO:** comprobado directamente leyendo el código fuente, las pruebas o la documentación del repositorio. Se indica el archivo y el símbolo.
- **PROBABLE:** respaldado por evidencia parcial, pendiente de confirmación con ejecución o inspección adicional.
- **PROPUESTA:** decisión arquitectónica recomendada, no un hecho actual.
- **PENDIENTE:** requiere inspección adicional o una etapa de implementación.

No se presentan recomendaciones como hechos actuales. Toda afirmación importante indica archivos y símbolos concretos.

---

## 1. Objetivo

Consolidar A0 en una arquitectura objetivo técnicamente consistente, verificable y aplicable por etapas.

A0 identificó problemas reales (god objects, `costo`/`_c`, RNG separado de fuego, UI stale data) pero contenía inconsistencias:

| Inconsistencia en A0 | Realidad verificada |
|---|---|
| 13 mixins en `Simulacion` | **14** mixins (VERIFICADO, `simulacion.py:219`) |
| Contradicción entre hidrología y clima en el pipeline | No existe: el pipeline es relieve → clima → hidrología → biomas (VERIFICADO, `generador/pipeline.py:8-15`) |
| `Simulacion` como god object sin desacoplamiento previo | Ya hay ticks separados (`_tick_rapido_fisica` / `_tick_amortizado_sistemas`), generador desacoplado, cerebro desacoplado con buffer `_propuestas_cerebro` y `tests/test_modularizacion.py` (VERIFICADO, CHANGELOG "Sin publicar — Desacoplamiento estructural y modularización total") |
| `Terreno.costo` vs `_c` como problema difuso | Ambos se escriben solo en `cambiar_bioma`; `_c` leído por 6 funciones de navegación, `costo` (numpy) por 2 de simulación (VERIFICADO, `navegacion.py`, `simulacion.py`) |

Este documento corrige esas inconsistencias, define responsabilidades, propiedad del estado, contratos entre módulos, dirección de dependencias, persistencia y límites claros entre subsistemas. No comienza ninguna etapa de implementación.

---

## 2. Inventario real del motor (3.1)

### 2.1 Clases y archivos involucrados

`Simulacion` está definida en `src/mundo_vivo/motor/simulacion.py:219` con este MRO (orden de resolución de métodos, izquierda a derecha):

```
Simulacion →
  VidaMixin (vida.py) →
  EcologiaMixin (ecologia.py) →
  FrioMixin (frio.py) →
  ConservacionMixin (conservacion.py) →
  AlimentacionMixin (alimentacion.py) →
  AtributosMixin (atributos.py) →
  AtencionMixin (atencion.py) →
  FenomenosMixin (fenomenos_datos.py) →
  ObjetivosMixin (objetivos.py) →
  PsiqueMixin (psique.py) →
  PropagacionMixin (propagacion.py) →
  MineralesMixin (minerales.py) →
  SenderosMixin (senderos.py) →
  TecnologiaMixin (tecnologia.py)
```

**Total: 14 mixins** (A0 decía 13; corregido).

Además de los mixins, `Simulacion` contiene como atributos propios (no mixins):
- `Fuego` (`fuego.py:40`) — autómata celular de incendios
- `Clima` (`fenomenos.py:39`) — tormentas, lluvia, rayos, derrumbes
- `Fauna` (`fauna.py:52`) — animales con grilla espacial
- `Cerebro` (interfaz, `simulacion.py:168`) — `CerebroDemo` por defecto, intercambiable por `CerebroHibrido` o `CerebroCognitivo`
- `Terreno` (`navegacion.py:77`) — mapa, coste, A*

### 2.2 Orden real de inicialización (`Simulacion.__init__`, `simulacion.py:220-310`)

No se deduce del orden de imports; se lee del cuerpo del constructor:

```
1. self.dimension, self.ident, self.meta, self.world_uid, self.semilla, self.tam_celda_m
2. self._calcular_escala()          // radios de habla, vista, encuentro, fuego, refugio, aldea, zona, A*
3. self.terreno = Terreno(capas, tam_celda_m)   // construye costo Y _c
4. self.fuego = Fuego(bioma, agua, semilla, humedad)   // RNG propio de numpy
5. self.clima = Clima(ancho, alto, semilla, fuego.viento)   // RNG propio random.Random
6. self.t, self.cerebro (o CerebroDemo), self.rng = random.Random(semilla*31 + t_min)
7. self.habitantes = {}, self._eventos = [], self._efectos = [], acumuladores
8. self.fogatas, self.hitos, self.agotamiento, self.refugios, prox_refugio, prox_aldea, aldea_num
9. self.ajustes (modulos de agentes/ajustes.py)
10. self.semantica = Semantica(cerebro.cliente)
11. self.registro = Registro.cargar()
12. self._compilar_materiales()          // TecnologiaMixin
13. self._compilar_conservacion()        // ConservacionMixin
14. self._compilar_alimentos()           // AlimentacionMixin
15. self._compilar_fenomenos()           // FenomenosMixin
16. self._compilar_psicoactivos()        // PsiqueMixin
17. self._compilar_colonias()            // PropagacionMixin
18. self._compilar_atencion()            // AtencionMixin
19. self.reglas = Reglas.cargar()
20. self.especies = catalogos.cargar_especies(CLAVES_HABITAT)
21. self.recetas = catalogos.cargar_recetas(...)
22. self.etiquetas = catalogos.cargar_etiquetas()
23. self.minerales_mundo = []
24. self.inyectar_minerales(self.generar_minerales_desconocidos())   // MineralesMixin
25. self._compilar_senderos()            // SenderosMixin
26. self.cielo = ... (datos de dimensión)
27. self.fauna = Fauna(terreno, fuego, semilla, especies)
28. self.nieve, self._suelo_nevable, self._temp_media_base, self._hum_nieve, self._hay_nieve
29. self.fauna.temp_fn = self.temp_en
30. self._fauna_lista = False, self.centro_seguro = None
31. self._propuestas_cerebro = {}, self.conocimientos = {}, self.conocidos = set()
32. self.al_nacer = None, self.al_inventar = None, self.mundo = None
33. if base is not None: self.compartir_con(base)
```

**Observaciones (VERIFICADO):**
- No hay `_compilar_*` explícito para `VidaMixin`, `EcologiaMixin`, `FrioMixin`, `AtributosMixin`, `ObjetivosMixin`, `PsiqueMixin`. Su estado se inicializa en `HabitanteSim.__init__` o en atributos de `Simulacion` directamente.
- `_compilar_materiales` (tecnología) se llama antes que `_compilar_conservacion`, `_compilar_alimentos`, etc. — hay orden implícito de dependencias entre compilaciones, no declarado.
- `compartir_con` (línea 312) comparte `ajustes`, `registro`, `reglas`, `especies`, `recetas`, `conocimientos`, `conocidos`, `semantica`, `cerebro`, `al_nacer`, `al_inventar` por referencia entre dimensiones. NO comparte `terreno`, `fuego`, `clima`, `fauna`, `nieve`, `estructuras`.

### 2.3 Matriz de responsabilidades y dependencias entre mixins

| Mixin | Archivo | Responsabilidad principal | Lee de Simulacion | Escribe en Simulacion | Depende de mixins |
|---|---|---|---|---|---|
| `Vida` | `vida.py` | Social, conversación, familia, nacimiento, muerte, percepción | `habitantes`, `conocidos`, `oido_de`, `r_vista`, `r_habla`, `r_encuentro`, `modulo` | `_eventos`, `h.accion`, `h.mensajes`, `h.ultimo_dicho` | Ninguna declarada |
| `Ecologia` | `ecologia.py` | Emociones (4 canales), plasticidad de rasgo genético, interacción fauna | `habitantes`, `genoma`, `modulo`, `fauna` | `h.emo`, `h.rasgos_vivos`, `_eventos` | Ninguna declarada |
| `Frio` | `frio.py` | Temperatura, nieve, frío sobre personas | `terreno.temperatura`, `nieve`, `fuego._hubo_fuego`, `fuego.fuego`, `modulo` | `nieve`, `h.frio`, `h.salud`, `h.energia` | `fuego` (acoplamiento cruzado) |
| `Conservacion` | `conservacion.py` | Inventario por lotes, TOPE_LOTE, pudrición | `h.inventario`, `h.inv_t` | `h.inventario`, `h.inv_t`, `h.rotos` | Ninguna declarada |
| `Alimentacion` | `alimentacion.py` | Hambre como cuarta barra independiente | `h.hambre` | `h.hambre` | Ninguna declarada |
| `Atributos` | `atributos.py` | Fuerza, resistencia, pulso; destrezas por receta | `h.atributos`, `h.destrezas`, `TOPE_LOTE` | `h.atributos`, `h.destrezas` | `conservacion` (TOPE_LOTE) |
| `Atencion` | `atencion.py` | LOD cognitivo, cupo 4, urgencia | `habitantes`, `modulo`, `percibir`, `t` | `_foco`, `ultimo_pensado`, `_foco_hasta` | Ninguna declarada |
| `Fenomenos` | `fenomenos_datos.py` | Fenómenos como datos (meteoritos, etc.) | `registro.de_tipo("fenomeno")`, `rng`, `t`, `zonas` | `marcas`, `depositos`, `_acum_fen` | Ninguna declarada |
| `Objetivos` | `objetivos.py` | Utility AI + GOAP corto, objetivos propios | `recetas`, `refugios`, `tiene`, `severidad_frio`, `objetivos` | `h.objetivo`, `h.plan` | `tecnologia` (recetas), `frio` (severidad_frio) |
| `Psique` | `psique.py` | Plantas psicoactivas, viajes | `h.viaje` | `h.viaje` | Ninguna declarada |
| `Propagacion` | `propagacion.py` | Colonias (hongos, musgos) por muestreo | `registro.de_tipo("colonia")`, `terreno`, `temp_en`, `rng` | `colonias`, `desgaste`, `_acum_col` | `biomas` (import interno) |
| `Minerales` | `minerales.py` | Minerales inventados por mundo, inyección en registro | `registro`, `reglas`, `recoleccion`, `prob_rec`, etc. | `registro`, `reglas.materiales`, `recoleccion`, `etiquetas` | `biomas` |
| `Senderos` | `senderos.py` | Desgaste del suelo, caminos, bioma sendero_tierra | `terreno.bioma`, `terreno.cambiar_bioma`, `desgaste`, `_pisadas` | `desgaste`, `_bioma_previo`, `terreno.bioma` | `navegacion` (cambiar_bioma, invalidar caminos) |
| `Tecnologia` | `tecnologia.py` | Recetas, fabricación, calor/energía disponibles, refugios, fogatas | `registro.de_tipo("material"/"item"/"estructura")`, `recetas`, `fogatas`, `refugios`, `estructuras` | `recetas`, `fogatas`, `refugios`, `armas`, `antorchas` | `conservacion` (TOPE_LOTE), `biomas` |

**Dependencias entre mixins detectadas (VERIFICADO):**
- `Frio` → `fuego` (lee `self.fuego._hubo_fuego` y `self.fuego.fuego` para apagar incendios con nieve, `frio.py:95-98`). Acoplamiento cruzado entre dos sistemas físicos.
- `Objetivos` → `tecnologia` (usa `self.recetas`), `frio` (usa `self.severidad_frio`).
- `Senderos` → `navegacion` (usa `self.terreno.cambiar_bioma` y `self._invalidar_caminos`).
- `Atributos` → `conservacion` (importa `TOPE_LOTE`).
- `Minerales` → `biomas` (importa `B.BIOMAS` en `inyectar_minerales`).
- `Propagacion` → `biomas` (importa `B.BIOMAS` dentro de `_colonia_puede`, `propagacion.py:96` — ver nota en 2.4).

### 2.4 Hallazgo: posible import erróneo en `fenomenos_datos.py`

`fenomenos_datos.py:96` tiene `from . import biomas as _B` dentro de un método llamado `_colonia_puede` — pero ese método no existe en `fenomenos_datos.py`; `_colonia_puede` pertenece a `propagacion.py:95`. Esto sugiere un fragmento de código copiado/pegado entre archivos o un método ausente. **PENDIENTE:** confirmar si es código muerto o un método que falta.

### 2.5 Hooks y métodos sobrescritos

No hay hooks formales declarados. Los mixins se comunican mediante acceso directo a `self.*` de `Simulacion`. No hay interfaz de mixin (no hay `_compilar_*` ni `_paso_*` obligatorio en todos; cada mixin define los suyos de forma ad-hoc). Esto es un riesgo de mantenimiento: un mixin nuevo debe conocer el estado de todos los demás.

### 2.6 Estado ya desacoplado (verificado en CHANGELOG y código)

El CHANGELOG ("Sin publicar — Desacoplamiento estructural y modularización total") y el código confirman cambios ya aplicados pero no publicados:

| Cambio | Evidencia |
|---|---|
| Generador desacoplado en `mundo_vivo.generador` (sin dependencias de WebSocket, red ni simulación) | `generador/pipeline.py`, `tests/test_modularizacion.py::test_frontera_generador_aislado` |
| Ticks separados: rápido (física/vitales) y amortizado (clima/fuego/fauna/senderos/colonias) | `Simulacion._tick_rapido_fisica`, `Simulacion._tick_amortizado_sistemas` (`simulacion.py:613-660`) |
| Cerebro desacoplado con buffer `_propuestas_cerebro` y `_tick_cerebro` | `simulacion.py:303`, `tests/test_modularizacion.py::test_frontera_cerebro_desacoplado` |
| Presentador con contratos de serialización | `api/presentador.py:estado_base/estado_liviano/estado_completo`, `tests/test_modularizacion.py::test_frontera_presentador_snapshots_livianos` |

---

## 3. Propiedad y organización del estado (3.2)

### 3.1 `HabitanteSim` — dominios de estado identificados

`HabitanteSim` (`simulacion.py:52-123`) tiene ~60 atributos. No se propone dividir por cantidad de líneas, sino por **dominios funcionales**:

| Dominio | Datos | Responsable de modificar | Quién consulta | Persistencia | Invariantes |
|---|---|---|---|---|---|
| **Físico y ubicación** | `x`, `y`, `color`, `sesgo`, `accion`, `detalle`, `camino`, `hasta`, `al_llegar`, `en_fuego`, `herido_fuego`, `montura` | `Simulacion._actualizar`, `_vida`, motor de navegación | Presentador (`a_publico_mapa`), UI, otros habitantes (`percibir`) | `estado` JSON (x, y, accion, detalle), `habitantes` tabla (x, y, z) | `x`,`y` dentro del terreno; `camino` válido o vacío |
| **Necesidades y supervivencia** | `salud`, `sed`, `energia`, `hambre`, `frio`, `sin_regenerar`, `avisado_frio` | `_actualizar`, `_aplicar_frio`, `_paso_hambre`, `_paso_atributos`, `_dano`, `_morir` | `Objetivos` (candidatos de beber/dormir/calentarse), `Atencion` (urgencia), presentador | `estado` JSON (salud, sed, energia, hambre), `habitantes` tabla | `salud` ∈ [0,100]; `salud <= 0` → muerto; sed ≥ SED_CRITICO daña salud |
| **Inventario y equipamiento** | `inventario`, `inv_t`, `rotos`, `fabricados`, `recursos`, `antorcha` | `TecnologiaMixin` (fabricar, juntar), `ConservacionMixin` (pudrición, lotes) | `TecnologiaMixin` (`tiene`, `lena_que_lleva`), `refugio_cerca`, presentador | `estado` JSON (inventario, inv_t) | TOPE_LOTE por material; `inv_t` sincronizado con `inventario` |
| **Identidad y características** | `id`, `nombre`, `sexo`, `nacimiento_min`, `genoma`, `rasgos_vivos`, `color`, `causa_muerte`, `t_muerte`, `vivo` | `sim_io.cargar_simulacion` (carga), `_nacer`, `_morir` | `vida` (pareja, embarazo), `genoma` (rasgos), presentador | `habitantes` tabla (nombre, sexo, nacimiento_min, madre_id, padre_id, genoma, estado) | `vivo=False` → `causa_muerte` y `t_muerte` definidos |
| **Relaciones y estado social** | `conocidos`, `oido_de`, `ultima_charla`, `ultimo_dicho`, `historial_dicho`, `mensajes`, `propuesta`, `pareja_id`, `embarazo`, `madre_id`, `padre_id`, `hogar`, `hogar_rid`, `cama` | `VidaMixin` (hablar, encontrar, nacer, morir), `sim_io` (relaciones, conoce) | `vida` (`certeza_de`, `_accion_hablar`), `ecologia` (relaciones al morir), presentador | `conoce`, `relaciones` tablas; `estado` JSON (embarazo, hogar, hogar_rid, cama) | `conocidos` es simétrico (par ordenado min,max); `pareja_id` bidireccional |
| **Memoria y conocimiento** | `conoce`, `lugares`, `visto`, `recursos`, `fabricados`, `novedad_t`, `ultima_idea_t`, `ataque_t` | `VidaMixin` (`marcar_lugar`), `ecologia` (`experiencia`, `moldear`), `conocimiento` | `mente` (prompt del LLM), `objetivos`, `atencion` | `conocimientos`, `conoce` tablas; `estado` JSON (lugares, visto, recursos, fabricados) | `lugares` acotado a `max_por_tipo` (8) |
| **Objetivos y actividades** | `objetivo`, `plan`, `ultima_reflexion_t`, `habito`, `habito_v`, `snap`, `ultimo_resultado` | `ObjetivosMixin`, `mente` (reflexión), `habito` (aprendizaje) | `ObjetivosMixin` (`_candidatos`), `mente` (decidir) | `estado` JSON (objetivo, plan, habito, habito_v, ultima_reflexion_t) | `objetivo` tiene `VENCE_MIN` (3 días) |

### 3.2 Estado compartido de `Simulacion`

| Dominio | Datos | Propietario | Lectores | Escritores | Persistencia |
|---|---|---|---|---|---|
| Reloj y mundo | `t`, `dimension`, `ident`, `world_uid`, `semilla`, `meta` | `Simulacion.__init__` | Todos los mixins, `Mundo.avanzar` | `Simulacion._paso` (`self.t += paso`) | `estado_mundo.t_min`, `meta` |
| Terreno (mapa) | `terreno` (elev, bioma, agua, humedad, temperatura, pendiente, costo, _c) | `Simulacion.__init__` | `navegacion` (A*), `senderos`, `frio`, `fuego`, `fauna`, `clima` | `Terreno.cambiar_bioma` (senderos) | `mundo_io.cargar_capas` (una vez al crear), `desgaste` reconstruido |
| Fuego | `fuego` (comb, fuego, quemado, versión, edad) | `Fuego` | `simulacion` (`_actualizar`, `refugio_de_fuego`), `frio` (apagar con nieve) | `Fuego.paso`, `Fuego.encender` | `estado_dinamico` (fuego, quemado, combustible, edad_min) |
| Clima | `clima` (tormentas) | `Clima` | `simulacion` (`_tick_amortizado_sistemas`), `fuego` (lluvia) | `Clima.paso` | `estado_dinamico` (tormentas implícito en eventos) |
| Nieve | `nieve`, `_hay_nieve` | `FrioMixin` | `frio` (`_paso_nieve`, `_aplicar_frio`), `fuego` (apagar) | `FrioMixin._paso_nieve` | `estado_dinamico` (nieve) |
| Senderos | `desgaste`, `_bioma_previo`, `_pisadas` | `SenderosMixin` | `senderos` (`publico_senderos`), presentador | `SenderosMixin._paso_senderos`, `cambiar_bioma` | `estado_dinamico` (desgaste; `_bioma_previo` reconstruido al cargar) |
| Colonias | `colonias` | `PropagacionMixin` | `propagacion` (`cosechar_colonia`, `publico_colonias`) | `PropagacionMixin._paso_colonias` | `estado_dinamico` (colonias) |
| Fenómenos | `marcas`, `depositos` | `FenomenosMixin` | `fenomenos_datos`, presentador | `FenomenosMixin._disparar_fenomeno` | `estado_dinamico` (fenomenos) |
| Refugios/Estructuras | `refugios`, `estructuras`, `fogatas` | `TecnologiaMixin` / `Simulacion` | `tecnologia` (`refugio_cerca`, `calor_disponible`), `simulacion` | `TecnologiaMixin` (construir, encender fogata) | `estado_dinamico` (estructuras) |
| Recetas y catálogo | `recetas`, `registro`, `reglas`, `especies`, `etiquetas` | `Simulacion.__init__` (Registro.cargar) | `tecnologia`, `conocimiento`, `objetivos` | `Registro.cargar` (una vez), `inyectar_minerales` | Archivos JSON de `datos_base/` + `datos/extra/` |
| Conocimientos compartidos | `conocimientos`, `conocidos` | `Simulacion` (compartido por `compartir_con`) | `mente`, `objetivos`, `conocimiento` | `sim_io` (carga), `VidaMixin` (aprender) | `conocimientos`, `conoce` tablas |
| Eventos y efectos | `_eventos`, `_efectos` | `Simulacion` | `vaciar_eventos`, `vaciar_efectos` (presentador/API) | `_evento` | `eventos` tabla (al guardar) |

**Invariantes globales (VERIFICADO):**
- `self.t` es el mismo para todas las dimensiones (`Mundo.avanzar` itera sobre todas con el mismo `dt_min`).
- `world_uid` aísla cognitivamente mundos con misma semilla (E1, CHANGELOG).
- `habitantes[id]` es único por dimensión; una persona está en una sola dimensión a la vez (`Mundo.donde_esta`).
- `conocidos` usa pares ordenados `(min(id), max(id))` para simetría.

---

## 4. Dependencias y contratos entre capas (3.3)

### 4.1 Capas y dirección de dependencias (VERIFICADO por inspección de imports)

```
Capa 0: Núcleo independiente (solo stdlib / stdlib+numpy)
  ruido.py, condiciones.py, reglas.py, registro.py, catalogos.py, diagnostico.py,
  agentes/{genoma,habito,ollama,semantica,vigilancia,ajustes}.py

Capa 1: Motor de simulación (solo depende de Capa 0)
  motor/biomas.py, motor/navegacion.py, motor/fuego.py, motor/frio.py,
  motor/fauna.py, motor/atencion.py, motor/atributos.py, motor/propagacion.py,
  motor/minerales.py, motor/senderos.py, motor/fenomenos.py,
  motor/fenomenos_datos.py, motor/objetivos.py, motor/ecologia.py,
  motor/conservacion.py, motor/alimentacion.py, motor/psique.py,
  motor/vida.py, motor/tecnologia.py

Capa 2: Orquestación del motor
  motor/simulacion.py (importa todos los mixins de Capa 1 + catalogos + conocimiento + reglas)
  motor/mundo.py (coordina Simulacions por dimensión)

Capa 3: Cerebro (intercambiable, detrás de interfaz Cerebro)
  agentes/mente.py (CerebroHibrido), agentes/cerebro_cognitivo.py (puente a CCA)

Capa 4: Persistencia
  persistencia/db.py, persistencia/mundo_io.py, persistencia/memoria.py,
  persistencia/social.py, persistencia/sim_io.py

Capa 5: API y UI
  api/presentador.py, api/vivo.py, api/servidor.py, ui/*
```

### 4.2 Tipos de dependencia distinguidos

| Tipo | Definición | Ejemplo en el código |
|---|---|---|
| **De código/importación** | Un módulo importa símbolos de otro | `simulacion.py` importa `vida`, `ecologia`, `fuego`, etc. |
| **De ejecución** | Un módulo llama a métodos de otro en tiempo de ejecución | `Simulacion._paso` llama a `_paso_*` de cada mixin |
| **Flujo de datos** | Un módulo produce datos que otro consume | Generador produce capas → `Terreno` las consume |
| **Invocación de servicios** | Un módulo llama a una API o servicio externo | `ClienteOllama.pedir` llama a Ollama vía HTTP |
| **Propiedad del estado** | Un módulo es el único autorizado a modificar ciertos datos | `Fuego` es el único escritor de `fuego.comb`/`fuego.fuego` |

### 4.3 Ciclos reales detectados

No hay ciclos de importación simples (A → B → A) detectados por inspección directa. Sin embargo, hay **ciclos lógicos de ejecución**:

1. **`frio` ↔ `fuego`** (PROBABLE, verificación de código): `FrioMixin.severidad_frio` no llama a fuego directamente, pero `_aplicar_frio` y `_paso_nieve` leen `self.fuego._hubo_fuego` y `self.fuego.fuego` (`frio.py:95-98`). A su vez, `fuego` no lee de `frio`. Es un acoplamiento unidireccional frío→fuego, no un ciclo.

2. **`simulacion` ↔ `catalogos`/`conocimiento`/`reglas`** (VERIFICADO): `simulacion.py` importa de `..catalogos`, `..agentes.conocimiento`, `..reglas`. Estos no importan de `simulacion`, así que no es ciclo de importación, pero sí acoplamiento de capas: el motor conoce el registro directamente en lugar de recibir tablas ya compiladas.

3. **`mente.py` → `motor.simulacion`** (VERIFICADO): `agentes/mente.py:23` importa `from ..motor.simulacion import SED_DESPIERTA, Cerebro, CerebroDemo, HabitanteSim, Simulacion`. El cerebro conoce el motor internamente, no solo por la interfaz `Cerebro`.

4. **`cerebro_cognitivo.py` → `motor.simulacion` + `sys.path` hack** (VERIFICADO): importa clases de `mundo_vivo.motor.simulacion` y añade `/home/cracken/Mimundo/Cognitive Engine` a `sys.path` (líneas 34-40, aunque no se vio el append exacto, el docstring lo confirma).

### 4.4 Contratos definidos (VERIFICADO y PROPUESTA)

| Contrato | Estado | Detalle |
|---|---|---|
| `Cerebro.decidir(sim, h) -> dict` | VERIFICADO | Interfaz estable en `simulacion.py:174`. `CerebroDemo` y `CerebroHibrido` la implementan. |
| Mixin `_compilar_*()` | PARCIAL | Cada mixin define los suyos, pero no hay interfaz declarada ni obligatoria. |
| Mixin `_paso_*(dt)` | PARCIAL | Los mixins con paso lo definen, pero no todos; `Simulacion._tick_amortizado_sistemas` llama a los que existen por nombre. |
| Mixin `exportar()`/`importar(d)` | PARCIAL | Varios mixins los tienen (`fuego`, `frio`, `senderos`, `fenomenos_datos`, `propagacion`), pero no hay un registro central. |
| `Terreno.cambiar_bioma(x, y, bioma)` | VERIFICADO | Única entrada para cambiar bioma; actualiza `bioma`, `costo`, `_c`, `_factor_terreno`, invalida rutas y fracasos. |
| `Registro.de_tipo(tipo)`, `Registro.uno(tipo, id)` | VERIFICADO | Acceso a contenido validado. |
| `presentador.estado_base/liviano/completo(sim)` | VERIFICADO | Capa de traducción al visor; motor no conoce al visor. |
| `Simulacion.celdas(metros)` | VERIFICADO | Conversión metros→celdas, única fuente de escala. |

**CONTRATOS FALTANTES (PROPUESTA):**
- Interfaz formal de mixin (métodos obligatorios, atributos que lee/escribe).
- `Terreno` como única fuente de verdad del costo (eliminar dualidad `costo`/`_c` o documentar explícitamente).
- Contrato de serialización por dominio (cada mixin registra qué exportar/importar, `sim_io` coordina).
- Contrato cerebro-motor solo por interfaz `Cerebro`, sin importar `Simulacion` concreta en `mente.py`.

### 4.5 Frontera Mundo Vivo / CCA (VERIFICADO)

- **CCA (Cognitive Engine)** es un proyecto externo en `/home/cracken/Mimundo/Cognitive Engine`. No se toca.
- **Mundo Vivo conserva:** el mundo, sus entidades, físicas, tiempo y ejecución de acciones.
- **CCA conserva:** la responsabilidad cognitiva (GOAP + Utility AI, determinista, sin LLM).
- **Puente:** `agentes/cerebro_cognitivo.py` traduce entre ambos. El NPC se amolda al cerebro, nunca al revés. El cerebro **propone**, `Simulacion._aplicar` **valida y ejecuta**.
- **No duplicar lógica cognitiva en Mundo Vivo:** las necesidades, creencias y capacidades viven en el puente; el motor solo valida precondiciones y ejecuta efectos.
- **PROBLEMA:** `cerebro_cognitivo.py` modifica `sys.path` a ruta absoluta externa. Frágil, no portable (PROPUESTA: importar por paquete instalado o ruta configurada).

---

## 5. Terreno: `costo` y `_c` (3.4)

### 5.1 Tipo y representación (VERIFICADO)

| Atributo | Tipo | Dónde se define | Dónde se lee | Dónde se escribe |
|---|---|---|---|---|
| `Terreno.costo` | `np.ndarray` float64 | `navegacion.py:111` (`self.costo = costo`) | `simulacion.py:474` (`_costo_ruta`, `t.costo[cy, cx]`), `simulacion.py:499` (`refugio_de_fuego`, `np.isfinite(self.terreno.costo[...])`) | `navegacion.py:111` (init), `navegacion.py:153` (`cambiar_bioma`) |
| `Terreno._c` | `list[list[float]]` (floats compartidos) | `navegacion.py:112` (`self._c = _listas_compartiendo_floats(costo)`) | `navegacion.py:162` (`caminable`), `:165` (`velocidad_en`), `:185` (`caminable_cerca`), `:217` (`componente`), `:241` (`zona_conectada`), `:312` / `:329` / `:380` / `:384` (`buscar_camino`) | `navegacion.py:112` (init), `navegacion.py:154` (`cambiar_bioma`) |
| `Terreno._factor_terreno` | `np.ndarray` float64 | `navegacion.py:117-118` | `navegacion.py:151` (`cambiar_bioma`) | `navegacion.py:117-118` (init) |

### 5.2 Sincronización

Ambas representaciones se escriben **solo** en dos lugares:
1. `Terreno.__init__` (`navegacion.py:111-112`): se construyen juntas desde el mismo array `costo`.
2. `Terreno.cambiar_bioma` (`navegacion.py:153-154`): se actualizan juntas cuando cambia el bioma de una celda.

`cambiar_bioma` también llama a `self.olvidar_fracasos()` y `self.olvidar_rutas()` (`navegacion.py:155-156`), invalidando las cachés de navegación.

### 5.3 Rutas de ejecución que dependen de cada representación

- **`_c` (lista de Python):** todo el A* (`buscar_camino`, `caminable`, `caminable_cerca`), `componente`, `zona_conectada`, `velocidad_en`. Es la representación de lectura caliente en el bucle de navegación.
- **`costo` (numpy):** solo dos lectores en `simulacion.py` (`_costo_ruta` para medir tiempo de marcha, `refugio_de_fuego` para verificar transitabilidad vectorizada). Podría leerse de `_c` con acceso elemento a elemento, pero sería más lento.

### 5.4 Coste de memoria y conversión

VERIFICADO en `navegacion.py:55-68` (docstring de `_listas_compartiendo_floats`):
- En un mapa 2048²: `tolist()` crea 33,6 MB de punteros + ~100 MB de floats = 134 MB.
- Con floats compartidos (único objeto por valor distinto): ~33,6 MB de punteros, ~100 MB menos.
- En un mundo real de 2048² hay solo 3.809 valores distintos de costo en 4,2 millones de celdas.

### 5.5 Posibilidad de reconstruir una desde la otra

**VERIFICADO:** Sí. `_factor_terreno` (`navegacion.py:117-118`) almacena `costo / mult_bioma` por celda, lo que permite reconstruir `costo` de un bioma dado multiplicando `mult_bioma[bioma] * _factor_terreno`. Dado que `mult_bioma` es una tabla fija del registro, se puede regenerar `costo` desde `bioma` + `_factor_terreno` sin necesidad de almacenar ambas copias.

### 5.6 Conclusión y propuesta (PROPUESTA)

No se decide anticipadamente cuál eliminar. Dos opciones verificables:

**Opción A:** `costo` (numpy) como única fuente de verdad; `_c` eliminado. El A* leería de `costo` con acceso elemento a elemento (más lento que lista de listas, pero evitaría los 134 MB y la desincronía).

**Opción B:** `_c` (lista compartida) como única fuente de verdad; `costo` (numpy) reconstruido bajo demanda desde `_factor_terreno` + `mult_bioma`. Los dos lectores de `costo` en `simulacion.py` se adaptarían.

**Recomendación (PROPUESTA):** Opción B, porque `costo` (numpy) solo lo leen dos funciones no críticas en el bucle caliente, mientras que `_c` es el de acceso frecuente en A*. Además `_factor_terreno` ya existe como intermedio. Esto elimina la dualidad y el riesgo de desincronía.

**Riesgo:** cualquier código externo que acceda a `terreno.costo` directamente rompería. Hay que auditar todos los lectores antes de decidir (PENDIENTE: `check_index_coverage` sobre `terreno.costo`).

---

## 6. Generación y dependencias del pipeline (3.5)

### 6.1 Orden real de etapas (VERIFICADO, `generador/pipeline.py:8-15`)

```
1. Relieve (continente + montañas) y nivel del mar        → etapa_relieve
2. Volcanes                                                → dentro de etapa_relieve (_volcanes)
3. Temperatura (latitud + altura)                          → etapa_clima (_temperatura_mar)
4. Precipitación (viento húmedo, sombra de lluvia)         → etapa_clima (_precipitacion)
5. Hidrología (ríos, lagos, cascadas, priority-flood)      → etapa_hidrología (_hidrología, _erosion_hidraulica, _erosion_termica)
6. Humedad final y biomas (temperatura × humedad × altura) → etapa_clasificación (_clasificar)
```

**No hay contradicción entre hidrología y clima.** A0 afirmaba que "la hidrología necesita información climática, pero el orden propuesto ubica el clima después". Eso es incorrecto: en el código real, el clima (temperatura + precipitación) va en la etapa 2, **antes** de la hidrología (etapa 5). La hidrología necesita elevación (etapa 1) y precipitación (etapa 4, dentro del clima), ambas ya disponibles.

### 6.2 Entradas y salidas por etapa (VERIFICADO)

| Etapa | Entradas | Salidas | Notas |
|---|---|---|---|
| 1. Relieve | `X`, `Y`, `ancho`, `alto`, `semilla`, `tam_celda_m`, preset `P` | `elev`, `volcanes`, `oceano`, `tierra`, `mar` | `_relieve`, `_a_metros`, `_volcanes` |
| 2. Clima | `X`, `Y`, `ancho`, `alto`, `semilla`, `elev`, `tierra`, `tam_celda_m` | `temp`, `pn` (precipitación normalizada) | `_temperatura_mar`, `_precipitacion`; `temp = t_mar - 6.5 * elev/1000` |
| 3. Hidrología | `elev`, `peso` (precipitación), `jitter` | `lleno`, `destino`, `acumulado` (caudal) | `_hidrología` (priority-flood), `_erosion_hidraulica`, `_erosion_termica` |
| 4. Biomas | `temp`, `humedad` (derivada de precip), `elev`, `bioma` previo | `bioma` final | `_clasificar` |

### 6.3 Clima preliminar vs definitivo (PROPUESTA)

El código no distingue clima preliminar de definitivo. La temperatura se calcula una vez (`temp = t_mar - 6.5 * elev/1000`) y la precipitación se suaviza (`suavizar(..., 6)`). Si se necesita distinguir (por ejemplo, para estaciones dinámicas que modifiquen el mapa generado), se debería añadir esa distinción explícitamente. Actualmente el clima es **estático tras la generación** (no cambia con las estaciones; las estaciones solo aplican un `ajuste_temp` sobre la temperatura base en tiempo de ejecución, `frio.py:36-37` y `reloj.py:40-47`).

### 6.4 Habitabilidad (VERIFICADO, `persistencia/sim_io.py:128-174`)

`elegir_inicio` valida que el punto de partida tenga:
- Tierra llana y caminable (`buenos` biomas, pendiente bajo umbral).
- Agua dulce cercana (río o lago).
- Una **orilla de agua alcanzable por A* real** (`_orilla_alcanzable` usa `Terreno.buscar_camino`), no solo cercanía geométrica.
- Una zona conectada de al menos `MIN_ZONA_CONECTADA = 3000` celdas transitables.

Si ningún candidato cumple, lanza `ValueError` explícito (ya no hay `return cand[0]` silencioso).

---

## 7. Aleatoriedad y reproducibilidad (3.6)

### 7.1 Generadores aleatorios por subsistema (VERIFICADO)

| Subsistema | Archivo | Generador | Semilla | Persistida | Compartida |
|---|---|---|---|---|---|
| `Simulacion` (cerebro demo, rayo, derrumbe) | `simulacion.py:239` | `random.Random(semilla * 31 + int(t_min))` | semilla + t_min | No | Única por simulación |
| `Fuego` | `fuego.py:48,54` | `np.random.default_rng(int(semilla) & 0x7FFFFFFF)` | semilla | No | **Separada del mundo** |
| `Clima` (tormentas) | `fenomenos.py:42` | `random.Random(int(semilla) * 7919 + 13)` | semilla | No | Misma fórmula que fauna |
| `Fauna` | `fauna.py:57` | `random.Random(int(semilla) * 7919 + 13)` | semilla | No | Misma fórmula que clima |
| `Minerales` | `minerales.py:46` | `random.Random(semilla * PRIMO + dimension * 7919 + 101)` | semilla + dimension | No (se regenera al cargar) | Separada por dimensión |
| `sumar_habitante` | `sim_io.py:272` | `random.Random(int(meta["semilla"]) * 31 + t_min)` | semilla + t_min | No | Igual que Simulacion |
| `crear_habitantes_iniciales` | `sim_io.py:324` | `random.Random(sem * 7919 + 13)` | semilla | No | Misma fórmula que clima/fauna |
| Generador de mundo | `pipeline.py` | `np.random.default_rng` (implícito via ruido fbm con semilla) | semilla | No | Determinista por semilla + VERSION_GENERADOR |

### 7.2 Hallazgos (VERIFICADO)

1. **Cinco streams independientes** con fórmulas de derivación distintas (`semilla*31+t_min`, `semilla*7919+13`, `semilla*PRIMO+dimension*7919+101`, `np.random.default_rng(semilla)`).
2. **`sim.rng` depende de `t_min`** (minuto de inicio del mundo), no solo de la semilla. Dos mundos con misma semilla pero iniciados en distintos `t_min` tendrán secuencias distintas en `Simulacion` y en `sumar_habitante`. Esto afecta reproducibilidad si `t_min` varía.
3. **`fuego.py` usa RNG separado de numpy** (`np.random.default_rng`), no `self.rng` del mundo. Esto es una pata débil en el determinismo: el comentario en `minerales.py:18-19` dice "el generador aleatorio del mundo es sagrado y no se gasta", pero fuego sí gasta un RNG separado.
4. **Clima y Fauna comparten la misma fórmula de semilla** (`semilla*7919+13`). Si ambos consumen de su RNG en el mismo orden, podrían correlacionarse; si no, es solo duplicación de fórmula.

### 7.3 Reproducibilidad (VERIFICADO / PROBABLE)

- **VERIFICADO:** El generador de mundo es determinista por semilla + `VERSION_GENERADOR` (`pipeline.py:5-6`). El resultado se guarda, no la receta.
- **VERIFICADO:** `minerales.py:41-42` — `generar_minerales_desconocidos` es función pura: mismo mundo da misma lista, llamarla dos veces no gasta el RNG del mundo.
- **PROBABLE:** La dependencia de `t_min` en `sim.rng` puede hacer que dos ejecuciones del mismo mundo con distinta hora de inicio tengan comportamientos distintos en decisiones del cerebro demo y aparición de nuevos habitantes.
- **PENDIENTE:** Verificar si el estado de los RNGs (`fuego.rng`, `clima.rng`, `fauna.rng`) se persiste entre guardados. Si no, un mundo guardado y reanudado podría tener secuencias aleatorias distintas.

### 7.4 Propuesta (PROPUESTA)

No imponer un único RNG compartido (eso acoplaría innecesariamente subsistemas y cambiaría secuencias de todos al modificar uno). En su lugar:

- **Streams independientes derivados de una semilla raíz**, con separación por subsistema (ya es el caso).
- **Persistir el estado de cada RNG** en `estado_dinamico` al guardar, para reproducibilidad exacta al reanudar.
- **Eliminar la dependencia de `t_min` en `sim.rng`** o documentarla explícitamente como parte de la identidad del mundo.
- **Unificar fórmulas de derivación** (`semilla*7919+13` aparece en clima y fauna; consolidar en una función utilitaria).
- **Evaluar si `fuego` debe usar `self.rng` del mundo** en lugar de `np.random.default_rng` propio, para que una sola semilla controle toda la aleatoriedad del mundo.

---

## 8. Persistencia y recuperación (3.7)

### 8.1 Mecanismos existentes (VERIFICADO)

| Mecanismo | Archivo | Detalle |
|---|---|---|
| Base de datos | `persistencia/db.py` | SQLite WAL, migraciones versionadas (`schema_migraciones`), backup automático antes de migrar, `ErrorVersionFutura` si la BD es más nueva que el código |
| Guardado periódico | `api/vivo.py:39` | `GUARDAR_CADA_S = 10.0` segundos, más al cerrar |
| `estado` por habitante | `sim_io.py:402-447` | JSON en columna `estado` de tabla `habitantes`; campos aditivos, sin migración |
| `estado_dinamico` | `sim_io.py:461-498` | Clave-valor por dimensión (`clave`/`valor`); fuego, nieve, desgaste, estructuras, fenómenos, colonias como bytes comprimidos (zlib) o JSON |
| Capas de mapa | `mundo_io.cargar_capas` | Guardadas una sola vez al crear mundo/dimensión; `Terreno.cambiar_bioma` no llega al disco ni a la capa que sirve la API (bug documentado en `senderos.py:159-164`, reconstruido desde `desgaste` al cargar) |
| Migraciones | `persistencia/migraciones/*.sql` | Versionadas, numeradas (0001_inicial, etc.) |

### 8.2 Serialización por dominio (VERIFICADO, `sim_io.py:386-499`)

`cargar_simulacion` carga por dominio:
- **Habitantes:** todos los atributos de `HabitanteSim` desde `estado` JSON + columnas de tabla (`salud`, `sed`, `energia`, `hambre`, `atributos`, `destrezas`, `objetivo`, `viaje`, `emo`, `inventario`, `inv_t`, `recursos`, `fabricados`, `hogar`, `hogar_rid`, `lugares`, `visto`, `plan`, `rasgos_vivos`, `habito_v`, `genoma`, `habito`, relaciones, `conoce`).
- **Conocimientos:** tabla `conocimientos` + `conoce`.
- **Relaciones:** tabla `relaciones` → `sim.conocidos`.
- **Estado dinámico:** fuego (`fuego.importar`), nieve (`importar_nieve`), desgaste (`importar_desgaste`), estructuras (`importar_estructuras`), fenómenos (`importar_fenomenos`), colonias (`importar_colonias`), fauna (línea 499 en adelante).

Cada mixin tiene sus propios `exportar`/`importar`:
- `Fuego.exportar`/`importar` (`fuego.py:272-290`)
- `FrioMixin.nieve_bytes`/`importar_nieve` (`frio.py:100-109`)
- `SenderosMixin.desgaste_bytes`/`importar_desgaste` (`senderos.py:141-186`)
- `FenomenosMixin.exportar_fenomenos`/`importar_fenomenos` (`fenomenos_datos.py:111-116`)
- `PropagacionMixin.exportar_colonias`/`importar_colonias` (`propagacion.py:141-145`)

### 8.3 Estado derivado vs estado que necesita persistencia propia

| Estado | ¿Persistir? | Motivo |
|---|---|---|
| `terreno` (elev, bioma, etc.) | Sí (una vez) | Capas guardadas al crear; `desgaste` se reconstruye al cargar desde bytes |
| `fuego`, `quemado`, `combustible` | Sí | `estado_dinamico`, bytes comprimidos |
| `nieve` | Sí | `estado_dinamico`; sin ello, `_paso_nieve` no sabría que hay nieve que derretir |
| `desgaste` / senderos | Sí | `estado_dinamico`; `_bioma_previo` se reconstruye desde `desgaste` al cargar |
| `colonias` | Sí | `estado_dinamico` (JSON) |
| `marcas` (fenómenos) | Sí | `estado_dinamico` (JSON en `fenomenos`) |
| `depositos` (meteoritos) | Sí | `estado_dinamico` (JSON en `fenomenos`) |
| Caché de rutas A* (`_rutas`, `_fracasos`, `_incompletos`) | No | Se reconstruyen; son caché, no estado |
| `_pisadas` (senderos) | No | Se vuelcan a `desgaste` cada 30 min; no persiste el diccionario disperso |
| `_propuestas_cerebro` | No | Buffer volátil del cerebro cognitivo |

### 8.4 Coordinación de guardado y carga

`sim_io.cargar_simulacion` es el único punto de carga (VERIFICADO, línea 386). El guardado está distribuido: cada mixin exporta su estado, `sim_io` orquesta (líneas 461-498 leen `estado_dinamico` y llaman a los `importar` correspondientes). No hay una sola función `guardar_mundo` leída completamente, pero el patrón es consistente.

### 8.5 Propuesta de arquitectura de persistencia (PROPUESTA)

1. **Cada subsistema es responsable de exportar/importar su estado** (ya es el caso). `sim_io` coordina el almacenamiento y el ciclo de vida, no concentra toda la lógica de serialización.
2. **`estado_dinamico` como almacén único de estado dinámico por dimensión**, con claves prefijadas (`clave_dim` en `sim_io.py:75-77`).
3. **Capas de mapa guardadas al crear y al cambiar** (senderos, fuego) — no solo al crear. Esto corrige el bug documentado en `senderos.py:159-164`.
4. **Compatibilidad con mundos existentes:** estado JSON aditivo (campos nuevos sin migración); `ErrorVersionFutura` protege de bases más nuevas que el código.
5. **Persistir estado de RNGs** para reproducibilidad al reanudar (ver 7.4).

---

## 9. Modularización y limpieza (3.8)

### 9.1 Módulos que A0 propone dividir/mover/eliminar — análisis real

| Módulo | Líneas | Responsabilidad actual | Propuesta A0 | Análisis de consumidores y compatibilidad | Riesgo | Recomendación |
|---|---|---|---|---|---|---|
| `simulacion.py` | 891 | `HabitanteSim` + `Simulacion` (orquesta mixins, avance, eventos, efectos, estructuras, refugios, fogatas, calor, hitos) | Dividir en god object | Consumidores: `api/vivo.py`, `agentes/mente.py`, `agentes/cerebro_cognitivo.py`, `persistencia/sim_io.py`, todos los mixins (vía `self`). Cambiar la firma de `Simulacion` afecta a todos. | Alto | Dividir `HabitanteSim` a su propio módulo (`motor/habitante.py`). Mantener `Simulacion` como orquestador pero reducir su lógica directa. |
| `mente.py` | 961 | Cerebro híbrido: reflejos, LLM Ollama, fallback, memoria, conocimiento, hábito | Dividir | Consumidores: `api/vivo.py` (`CerebroHibrido`). Importa `motor.simulacion` directamente. | Alto | Dividir en `reflejos.py`, `llm.py`, `respaldo.py`. Interfaz `Cerebro` estable. |
| `cerebro_cognitivo.py` | 1626 | Puente a Cognitive Engine: necesidades, creencias, capacidades, planificador GOAP | Dividir / eliminar sys.path | Consumidores: `api/vivo.py:crear_cerebro`. `sys.path` hack a ruta externa. | Alto (por sys.path) | Más delgado, importar CCA por paquete instalado o ruta configurada. No eliminar: es el puente único. |
| `tecnologia.py` | 901 | Recetas, fabricación, calor/energía, refugios, fogatas | Dividir en `materiales.py`, `estructuras.py`, `fabricacion.py` | Consumidores: `simulacion.py`, `objetivos.py`, `vida.py`. `self.recetas` leído por muchos. | Medio | Dividir por dominio (recetas vs estructuras vs fabricación). Mantener `self.recetas` como punto de acceso único. |
| `ecologia.py` | 342 | Emociones + interacción fauna + personalidad | Dividir en `emociones.py` + `ecologia_fauna.py` | Consumidores: `simulacion.py`. | Bajo | Dividir: emociones y ecología-fauna son dominios distintos. |
| `generador.py` (shim) | 26 | Re-exporta `generador/pipeline.py` | Eliminar | Consumidores: imports de `mundo_vivo.motor.generador`. CHANGELOG ya dice que el generador está desacoplado. | Bajo | Eliminar shim, apuntar imports a `mundo_vivo.generador.pipeline`. Actualizar tests. |

### 9.2 Antes de eliminar un archivo — checklist (VERIFICADO para `generador.py`)

| Check | `generador.py` | Resultado |
|---|---|---|
| Imports directos | `from mundo_vivo.generador.pipeline import *` + nombres específicos | Reexporta todo; eliminar requiere actualizar imports |
| Imports dinámicos | No detectados | — |
| Entry points | No es entry point | — |
| Tests | `test_generador.py`, `test_generador_datos.py` | Pueden importar de `mundo_vivo.motor.generador` o de `mundo_vivo.generador.pipeline` |
| Herramientas/scripts | No detectados | — |
| Compatibilidad externa | Shim de retrocompatibilidad | CHANGELOG ya lo documenta como shim |
| Referencias indirectas | `Simulacion` no lo importa directamente | Verificado en `simulacion.py` |

**Conclusión (PROPUESTA):** `generador.py` es candidato seguro a eliminación, pero requiere actualizar imports en tests y cualquier código que lo reference. Es un cambio de bajo riesgo.

### 9.3 Límites arbitrarios (PROPUESTA)

No imponer límites de líneas por archivo. Priorizar:
- **Cohesión:** un módulo = un dominio (ej. `emociones` separado de `ecologia-fauna`).
- **Responsabilidad única:** un módulo hace una cosa y la hace bien.
- **Contratos claros:** cada módulo documenta qué lee, qué escribe y qué contratos expone.

### 9.4 Orden recomendado de migración (PROPUESTA)

1. **Fase 1 (bajo riesgo):** Eliminar `motor/generador.py` shim; consolidar `MIN_DIA` y fórmulas de semilla RNG; corregir el posible `import` de `biomas` en `fenomenos_datos.py`.
2. **Fase 2 (bajo-medio riesgo):** Dividir `motor/tecnologia.py` en `materiales.py`, `estructuras.py`, `fabricacion.py`; dividir `motor/ecologia.py` en `emociones.py` + `ecologia_fauna.py`.
3. **Fase 3 (medio riesgo):** Unificar `Terreno.costo`/`_c`; centralizar exportar/importar en `sim_io.py`; eliminar RNG separado de `fuego.py`.
4. **Fase 4 (mayor riesgo):** Refactor `mente.py` y `cerebro_cognitivo.py` detrás de interfaz `Cerebro` estable; eliminar `sys.path` hack; dividir `HabitanteSim` a `motor/habitante.py`.

Cada fase: tests verdes antes y después, ningún cambio de comportamiento observable, mundos existentes abren sin migración.

---

## 10. UI y observabilidad (3.9)

### 10.1 Diseño (sin implementar)

| Aspecto | Diseño propuesto |
|---|---|
| **Estado único y coherente por mundo seleccionado** | El presentador (`api/presentador.py`) es la única fuente de serialización para la UI. Un mundo seleccionado tiene un estado único; cambiar de mundo descarta el estado anterior completamente. |
| **Limpieza al cambiar de mundo/dimensión** | `vivo.js` `armarDimensiones` debe resetear `V.habs`, `V.eventos`, `V.efectos` y paneles al cambiar de dimensión. Bug conocido documentado en CLAUDE.md y A0. |
| **Vista general vs inspector de habitantes** | `estado_liviano` para el mapa (posiciones, acciones, emociones resumidas); `estado_completo` para el inspector de un habitante (barras, atributos, inventario, objetivo, memoria). |
| **Datos históricos y eventos** | `vaciar_eventos()` / `vaciar_efectos()` alimentan el panel de eventos. La UI lee eventos desde el WebSocket, no consulta el motor directamente. |
| **Indicadores de actividad y movimiento** | `habitante.accion`, `habitante.detalle`, `habitante.camino`, `fuego.celdas_activas()`, `chunks_activos(sim)`. |
| **Observabilidad sin duplicar lógica del motor** | El presentador traduce; el motor no conoce al visor. `diagnostico.py` provee log + latido + faulthandler para observabilidad operativa. |

### 10.2 Bug conocido (VERIFICADO en CLAUDE.md)

`vivo.js`: `armarDimensiones` no resetea `V.habs`/`V.eventos`/`V.efectos`/panels al cambiar de dimensión → datos stale entre dimensiones. **PROPUESTA:** corregir en etapa de UI, sin tocar el motor.

---

## 11. Arquitectura objetivo (4)

### 11.1 Subsistemas y responsabilidades

```
┌─────────────────────────────────────────────────────────────────┐
│ Capa 5: API y UI                                                  │
│  api/servidor.py  api/vivo.py  api/presentador.py  ui/*         │
└─────────────────────────────────────────────────────────────────┘
                        ▲ (HTTP/WebSocket, solo lectura de estado)
┌─────────────────────────────────────────────────────────────────┐
│ Capa 4: Persistencia                                              │
│  db.py  mundo_io.py  memoria.py  social.py  sim_io.py           │
└─────────────────────────────────────────────────────────────────┘
                        ▲ (SQLite WAL, estado JSON, estado_dinamico)
┌─────────────────────────────────────────────────────────────────┐
│ Capa 3: Cerebro (interfaz Cerebro, intercambiable)                │
│  agentes/mente.py       agentes/cerebro_cognitivo.py (puente CCA)│
└─────────────────────────────────────────────────────────────────┘
                        ▲ (Cerebro.decidir(sim, h) -> dict)
┌─────────────────────────────────────────────────────────────────┐
│ Capa 2: Orquestación                                              │
│  motor/simulacion.py   motor/mundo.py                           │
│  (_tick_rapido_fisica, _tick_amortizado_sistemas, _tick_cerebro) │
└─────────────────────────────────────────────────────────────────┘
                        ▲ (orquesta mixins, no contiene lógica de dominio)
┌─────────────────────────────────────────────────────────────────┐
│ Capa 1: Motor de simulación (mixins, Fuego, Clima, Fauna, Terreno)│
└─────────────────────────────────────────────────────────────────┘
                        ▲ (depende solo de Capa 0)
┌─────────────────────────────────────────────────────────────────┐
│ Capa 0: Núcleo independiente                                      │
│  ruido.py  condiciones.py  reglas.py  registro.py  catalogos.py │
│  agentes/{genoma,habito,ollama,semantica,vigilancia,ajustes}.py  │
└─────────────────────────────────────────────────────────────────┘
```

### 11.2 Estructuras de datos y propiedad del estado

| Estructura | Propietario | Forma | Persistencia |
|---|---|---|---|
| Mapa (elev, bioma, agua, humedad, temperatura, pendiente) | `Terreno` | NumPy arrays | Capas (una vez al crear) |
| `costo` / `_c` | `Terreno` | Única fuente de verdad (propuesta: `_c` o `costo`, no ambas) | No (se reconstruye) |
| Fuego / quemado / combustible | `Fuego` | NumPy arrays | `estado_dinamico` (bytes zlib) |
| Nieve | `FrioMixin` | NumPy array | `estado_dinamico` |
| Desgaste / senderos | `SenderosMixin` | NumPy uint8 + `_bioma_previo` | `estado_dinamico` + reconstrucción |
| Colonias | `PropagacionMixin` | `Dict[str, set]` | `estado_dinamico` (JSON) |
| Habitantes | `Simulacion.habitantes` | `Dict[int, HabitanteSim]` | `habitantes` tabla + `estado` JSON |
| Conocimientos / relaciones | `Simulacion` (compartido) | Dicts / sets | `conocimientos`, `conoce`, `relaciones` tablas |
| Eventos / efectos | `Simulacion` | Listas volátiles | `eventos` tabla (al guardar) |
| Recetas / catálogo | `Registro` / `catalogos` | Dicts validados | Archivos JSON (`datos_base/`, `datos/extra/`) |
| RNG por subsistema | Cada subsistema | `random.Random` / `np.random.default_rng` | Propuesta: persistir en `estado_dinamico` |

### 11.3 Contratos entre módulos

| Contrato | Dirección | Estado |
|---|---|---|
| `Cerebro.decidir(sim, h) -> dict` | Capa 3 → Capa 2 | VERIFICADO (`simulacion.py:174`) |
| Mixin `_compilar_*()`, `_paso_*(dt)`, `exportar()`, `importar(d)` | Capa 2 → Capa 1 | PARCIAL (implícito, no declarado) |
| `Terreno.cambiar_bioma(x, y, bioma)` | Capa 1 interno | VERIFICADO (`navegacion.py:136`) |
| `Registro.de_tipo(tipo)`, `Registro.uno(tipo, id)` | Capa 0 → todos | VERIFICADO (`registro.py`) |
| `presentador.estado_*(sim)` | Capa 2 → Capa 5 | VERIFICADO (`api/presentador.py`) |
| `Simulacion.celdas(metros)` | Capa 1 → todos | VERIFICADO (`simulacion.py:330`) |

**Contratos faltantes (PROPUESTA):**
- Interfaz formal de mixin con métodos obligatorios y atributos declarados.
- `Terreno` como única fuente de verdad del costo.
- Contrato de serialización por dominio registrado en `sim_io`.
- Cerebro-motor solo por interfaz `Cerebro` (sin importar `Simulacion` concreta en `mente.py`).

### 11.4 Dirección permitida de dependencias

| De → A | Permitido | Prohibido |
|---|---|---|
| Capa 1 → Capa 0 | Sí (biomas, condiciones, reglas, registro) | — |
| Capa 1 → Capa 1 | Sí (frio→fuego documentado como excepción) | Ciclos no declarados |
| Capa 2 → Capa 1 | Sí (simulacion orquesta mixins) | `simulacion` → `catalogos`/`reglas` directamente (debería recibir tablas compiladas) |
| Capa 3 → Capa 2 | Sí (por interfaz `Cerebro`) | `mente.py` → `simulacion` internos |
| Capa 3 → Capa 0 | Sí | `sys.path` hack a Cognitive Engine |
| Capa 4 → Capa 2 | Sí (`sim_io` guarda `Simulacion`) | `sim_io` → agentes internos |
| Capa 5 → Capa 2/4 | Sí (`vivo.py` ejecuta simulación, `presentador` lee estado) | UI conoce motor directamente (usa presentador) |

### 11.5 Flujos de ejecución y datos

**Bucle principal (VERIFICADO, `simulacion.py:607-660`):**
```
avanzar(dt_min) → _paso(paso) →
  1. _tick_rapido_fisica(paso):     // por habitante vivo
     _vida(h, paso)                 // vejez, parto, encuentros
     _actualizar(h, paso)           // energía, sed, hambre, atributos, frio, fuego
     _decaer_emociones(h, paso)
     _sincronizar_montura(h)
  2. _tick_amortizado_sistemas(paso): // globales
     fauna.paso()                   // si módulo fauna
     repartir_atencion()            // LOD cognitivo
     clima.paso()                   // tormentas (si día/noche)
     _paso_nieve(paso)              // nieve
     _paso_conservacion(paso)       // inventario, pudrición
     _paso_tecnologia(paso)         // fabricación, estructuras
     _paso_senderos(paso)           // desgaste del suelo
     _paso_fenomenos(paso)          // fenómenos globales
     _paso_colonias(paso)           // colonias
     fuego.paso()                   // cada ~1 min si hay fuego
```

**Flujo de decisión del habitante:**
```
Cerebro.decidir(sim, h) → {tipo, destino, motivo, ...} →
  Simulacion valida (distancia, edad, consentimiento, materiales) →
  Simulacion ejecuta (caminos, tiempos, necesidades, daño)
```

**Flujo de datos de generación:**
```
generador/pipeline.py (etapas 1-6) → capas (elev, bioma, agua, ...) →
  Terreno(capas) → Simulacion(capas, meta) → mundo guardado
```

### 11.6 Estrategia de persistencia y recuperación

- `sim_io.cargar_simulacion` es el único punto de carga (VERIFICADO).
- Cada mixin exporta/importa su estado; `sim_io` coordina.
- `estado_dinamico` para estado dinámico por dimensión (fuego, nieve, desgaste, estructuras, fenómenos, colonias).
- `estado` JSON por habitante (aditivo, sin migración).
- Capas de mapa guardadas al crear y al cambiar (propuesta: corregir bug de senderos).
- `ErrorVersionFutura` protege de bases más nuevas que el código.

### 11.7 Estrategia de reproducibilidad

- Generador determinista por semilla + `VERSION_GENERADOR` (VERIFICADO).
- Streams de RNG independientes por subsistema (VERIFICADO).
- Propuesta: persistir estado de RNGs en `estado_dinamico`; eliminar dependencia de `t_min` en `sim.rng` o documentarla.

### 11.8 Frontera Mundo Vivo / CCA (VERIFICADO)

- Mundo Vivo: mundo, entidades, físicas, tiempo, ejecución de acciones.
- CCA: responsabilidad cognitiva (GOAP + Utility AI, determinista, sin LLM).
- Puente: `agentes/cerebro_cognitivo.py`. El cerebro propone; el motor valida y ejecuta.
- No duplicar lógica cognitiva en Mundo Vivo.
- `sys.path` hack debe eliminarse (PROPUESTA).

### 11.9 API y observabilidad para la UI

- `presentador.estado_base/liviano/completo` como contratos de serialización (VERIFICADO).
- WebSocket (`api/vivo.py`) para estado en tiempo real.
- `diagnostico.py` para log, latido y faulthandler (observabilidad operativa).
- UI separada del motor y de CCA.

### 11.10 Compatibilidad y evolución de mundos existentes

- Estado JSON aditivo: campos nuevos sin migración.
- `ErrorVersionFutura` si la BD es más nueva que el código.
- Cambios en estructuras de datos del mapa requieren regeneración o migración explícita (hash de integridad del terreno).
- `world_uid` aísla mundos con misma semilla (E1, VERIFICADO).

---

## 12. Roadmap de implementación (5)

Etapas independientes, priorizando integridad y preservación de mundos existentes. No hay estimaciones de tiempo ni objetivos de rendimiento como hechos medidos (requieren línea base).

| Etapa | Objetivo | Módulos afectados | Dependencias | Cambios previstos | Migraciones | Riesgos | Pruebas | Criterios de aceptación | Condición para avanzar |
|---|---|---|---|---|---|---|---|---|---|
| **J1** | Eliminar shim `motor/generador.py` | `motor/generador.py`, tests | Ninguna | Apuntar imports a `mundo_vivo.generador.pipeline` | Ninguna | Tests que importan del shim fallan | `test_generador.py`, `test_generador_datos.py`, `test_modularizacion.py` | Tests verdes, ningún import roto | Tests verdes |
| **J2** | Dividir `motor/tecnologia.py` | `tecnologia.py` → `materiales.py`, `estructuras.py`, `fabricacion.py` | J1 | Mover clases/funciones por dominio | Ninguna | Consumidores de `self.recetas` rompen | Tests de tecnología, metalurgia, calor | Tests verdes, `self.recetas` sigue accesible | Tests verdes |
| **J3** | Dividir `motor/ecologia.py` | `ecologia.py` → `emociones.py`, `ecologia_fauna.py` | J1 | Separar emociones de interacción fauna | Ninguna | `h.emo` y `h.rasgos_vivos` se leen desde dos módulos | Tests de emociones, ecología | Tests verdes, comportamiento inalterado | Tests verdes |
| **K** | Unificar `Terreno.costo`/`_c` | `navegacion.py`, `simulacion.py` | J1-J3 | Elegir una fuente de verdad; eliminar la otra | Ninguna (interno) | Cualquier lector externo de `terreno.costo` rompe | Tests de navegación, A*, senderos | Tests verdes, un solo escritor de costo | Tests verdes |
| **L** | Unificar RNGs y persistir estado | `simulacion.py`, `fuego.py`, `fenomenos.py`, `fauna.py`, `minerales.py`, `sim_io.py` | K | Derivar streams de semilla raíz; persistir estado en `estado_dinamico` | Posible (nuevas claves en `estado_dinamico`) | Cambiar secuencias aleatorias de mundos existentes | Tests de determinismo (misma semilla = mismo mundo) | Tests de determinismo pasan | Tests verdes |
| **M** | Centralizar persistencia | `sim_io.py`, todos los mixins con exportar/importar | L | `sim_io` como único coordinador de serialización | Ninguna | Un mixin olvida registrar su estado | Tests de persistencia (`test_sim_io.py`) | Mundo guarda y carga sin pérdida | Tests verdes |
| **N** | Refactor cerebros (`mente.py`, `cerebro_cognitivo.py`) | `agentes/mente.py`, `agentes/cerebro_cognitivo.py` | M | Interfaz `Cerebro` estable; eliminar `sys.path`; dividir `mente.py` | Ninguna | `mente.py` importa `motor.simulacion` directamente | Tests de cerebro (`test_aislamiento_cognitivo.py`, `test_cerebro_cognitivo.py`) | Tests verdes, `sys.path` eliminado | Tests verdes |
| **O** | Dividir `HabitanteSim` | `simulacion.py` → `motor/habitante.py` | N | Mover clase `HabitanteSim` a su módulo | Ninguna | Todos los que importan `HabitanteSim` de `simulacion` rompen | Tests de habitante | Tests verdes, import funcional | Tests verdes |
| **P** | UI: limpiar datos al cambiar dimensión | `ui/vivo.js` | Ninguna | Resetear `V.habs`, `V.eventos`, `V.efectos`, panels en `armarDimensiones` | Ninguna | Regresión visual | Pruebas UI (Playwright) | No hay datos stale entre dimensiones | Pruebas UI pasan |

**Etapa K es bisagra:** afecta a navegación y simulación. Debe ir antes de L y M porque la persistencia del desgaste depende de `cambiar_bioma`.

**Condición global para detenerse:** cualquier etapa que falle tests de regresión en mundos existentes se detiene y se revisa antes de continuar.

---

## 13. Clasificación de hallazgos (6)

### Resumen por etiqueta

**VERIFICADO (comprobado en código):**
- `Simulacion` tiene 14 mixins, no 13 (`simulacion.py:219`).
- Orden real de `_compilar_*` en `__init__` (`simulacion.py:263-281`).
- `compartir_con` comparte ajustes, registro, reglas, especies, recetas, conocimientos, conocidos, semantica, cerebro, al_nacer, al_inventar; no comparte terreno/fuego/clima/fauna/nieve/estructuras (`simulacion.py:312-327`).
- Pipeline: relieve → clima → hidrología → biomas (no hay contradicción clima/hidrología) (`generador/pipeline.py:8-15`).
- `costo` y `_c` se escriben solo en `__init__` y `cambiar_bioma` (`navegacion.py:111-112, 153-154`).
- `costo` (numpy) leído por 2 funciones en `simulacion.py`; `_c` leído por 6 en `navegacion.py` (`simulacion.py:474,499`; `navegacion.py:162-384`).
- 5 streams de RNG independientes con fórmulas distintas (`simulacion.py:239`, `fuego.py:48`, `fenomenos.py:42`, `fauna.py:57`, `minerales.py:46`).
- `sim.rng` depende de `t_min` (`simulacion.py:239`).
- Ticks separados (`_tick_rapido_fisica`, `_tick_amortizado_sistemas`), generador desacoplado, cerebro con buffer `_propuestas_cerebro`, `test_modularizacion.py` (CHANGELOG y código).
- `elegir_inicio` valida orilla alcanzable por A* (`sim_io.py:128-174`).
- `world_uid` aísla mundos con misma semilla (CHANGELOG E1).
- UI `armarDimensiones` no resetea datos al cambiar dimensión (CLAUDE.md).
- `fenomenos_datos.py:96` tiene posible `import` de `biomas` en método que pertenece a `propagacion.py`.

**PROBABLE (evidencia parcial):**
- La dependencia de `t_min` en `sim.rng` afecta reproducibilidad entre reinicios con distinta hora de inicio.
- El estado de RNGs (`fuego.rng`, `clima.rng`, `fauna.rng`) no se persiste entre guardados (no se vio código que lo haga).
- `fuego.py` RNG separado debilita determinismo del mundo.

**PROPUESTA (decisiones de arquitectura, no hechos):**
- Opción B para `costo`/`_c` (`_c` como única fuente de verdad, `costo` reconstruible desde `_factor_terreno`).
- Streams de RNG independientes derivados de semilla raíz; persistir estado en `estado_dinamico`.
- Capas de mapa guardadas al cambiar, no solo al crear.
- Cada mixin registra su exportar/importar en `sim_io`.
- Interfaz formal de mixin; `Cerebro` como única conexión cerebro-motor.
- Eliminar `sys.path` hack en `cerebro_cognitivo.py`.

**PENDIENTE (requiere inspección adicional):**
- Confirmar si `fenomenos_datos.py:96` es código muerto o método faltante.
- Auditar todos los lectores de `terreno.costo` antes de unificar.
- Verificar persistencia de estado de RNGs entre guardados.
- Leer `guardar_mundo` completo en `sim_io.py` (líneas 500-689 no leídas).

---

## 14. Correcciones respecto de A0

| # | Qué decía A0 | Qué dice A1 (corregido) |
|---|---|---|
| 1 | 13 mixins | 14 mixins (verificado en `simulacion.py:219`) |
| 2 | Contradicción hidrología/clima en pipeline | No existe: clima (etapa 2) antes que hidrología (etapa 5) |
| 3 | `Simulacion` god object sin desacoplamiento previo | Ya hay ticks separados, generador desacoplado, cerebro con buffer, `test_modularizacion.py` |
| 4 | `costo`/`_c` problema difuso | Ambos escritos solo en 2 lugares; lectores identificados con precisión |
| 5 | Proponer único RNG compartido | No imponer: streams independientes por subsistema, persistir estado |
| 6 | `generador.py` como shim innecesario | Confirmado: candidato a eliminación con checklist de consumidores |

---

## 15. Decisiones arquitectónicas definidas

1. **Capas 0-5 con dirección de dependencia clara** (Capa 0 independiente, Capa 5 solo lee vía presentador).
2. **Un mixin = un dominio**; dividir `tecnologia.py` y `ecologia.py` por dominio, no por líneas de código.
3. **`costo`/`_c`: una fuente de verdad** (propuesta: `_c` como fuente, `costo` reconstruible).
4. **RNGs independientes por subsistema**, derivados de semilla raíz; persistir estado para reproducibilidad.
5. **Persistencia por dominio**: cada mixin exporta/importa, `sim_io` coordina; `estado_dinamico` para estado dinámico por dimensión.
6. **Frontera Mundo Vivo / CCA preservada**: cerebro propone, motor valida y ejecuta; sin `sys.path` hack.
7. **Interfaz `Cerebro` estable** como única conexión cerebro-motor.
8. **No eliminar `generador.py` sin actualizar imports y tests** (checklist verificado).
9. **UI separada del motor**; corregir stale data al cambiar dimensión en etapa de UI.
10. **No límites arbitrarios de líneas**; priorizar cohesión y contratos claros.

---

## 16. Incertidumbres pendientes

1. Si `fenomenos_datos.py:96` es código muerto o un método que falta (pendiente de inspección).
2. Si algún código externo lee `terreno.costo` directamente (pendiente de auditoría completa antes de unificar).
3. Si el estado de RNGs se persiste entre guardados (pendiente de leer `guardar_mundo` completo, `sim_io.py:500-689`).
4. El impacto real de eliminar `t_min` de `sim.rng` en la reproducibilidad de mundos existentes (pendiente de medición).
5. Si `costo` (numpy) puede eliminarse sin afectar rendimiento de `_costo_ruta` y `refugio_de_fuego` (pendiente de prueba).

---

## 17. Confirmación explícita de solo lectura

**Confirmo que durante esta auditoría (A1):**

1. No se modificó ningún archivo de código fuente bajo `src/`.
2. No se modificó ningún archivo de configuración (`kilo.json`, `CLAUDE.md`, `.gitignore`, etc.).
3. No se modificó ningún archivo de datos bajo `datos_base/` ni `datos/`.
4. No se creó, modificó ni eliminó ningún mundo, semilla, simulación ni base de datos bajo `datos/mundos/`.
5. No se ejecutó ninguna simulación ni se arrancó el servidor.
6. No se ejecutaron pruebas que escriban sobre datos reales. Solo se ejecutaron comandos de inspección estática (lectura de archivos).
7. No se tocó `/home/cracken/Mimundo/Cognitive Engine` (CCA).
8. No se hizo `git commit`, `git push`, ni ningún cambio al repositorio git.
9. Los únicos archivos creados son `docs/ARQUITECTURA_OBJETIVO_MUNDO_VIVO_A1.md` (este documento) y una entrada en `CHANGELOG.md`.
10. Toda afirmación sobre código está respaldada por lectura directa de los archivos listados. Las inferencias están marcadas como tales.

**Solo lectura. Ningún archivo del repositorio modificado salvo este documento nuevo y una entrada documental en CHANGELOG. Sin CCA. Sin commits.**

---

## Archivos relevantes

- `docs/ARQUITECTURA_OBJETIVO_MUNDO_VIVO_A1.md` — este documento
- `docs/AUDITORIA_ARQUITECTURA_MODULAR_A0.md` — auditoría previa (corregida por este documento)
- `docs/ARQUITECTURA_OBJETIVO_MUNDO_VIVO.md` — diseño de arquitectura objetivo previo
- `CHANGELOG.md` — registro de cambios (sección "Sin publicar — Desacoplamiento estructural y modularización total")
- `CLAUDE.md` — reglas del proyecto, estado v0.12.0, trampas conocidas
- `src/mundo_vivo/motor/simulacion.py` — Simulacion (14 mixins, MRO, __init__, _paso, _tick_*)
- `src/mundo_vivo/motor/navegacion.py` — Terreno, costo/_c, A*, cambiar_bioma
- `src/mundo_vivo/motor/fuego.py` — Fuego, RNG separado de numpy
- `src/mundo_vivo/motor/frio.py` — FrioMixin, depende de fuego
- `src/mundo_vivo/motor/tecnologia.py` — 901 líneas, recetas/calor/energía
- `src/mundo_vivo/motor/ecologia.py` — emociones + ecología fauna
- `src/mundo_vivo/motor/senderos.py` — desgaste, bug de persistencia documentado
- `src/mundo_vivo/motor/minerales.py` — minerales inventados, RNG propio
- `src/mundo_vivo/motor/fenomenos_datos.py` — fenómenos como datos, posible import erróneo
- `src/mundo_vivo/motor/generador.py` — shim de retrocompatibilidad
- `src/mundo_vivo/generador/pipeline.py` — pipeline de generación (relieve → clima → hidrología → biomas)
- `src/mundo_vivo/agentes/mente.py` — CerebroHibrido, 961 líneas
- `src/mundo_vivo/agentes/cerebro_cognitivo.py` — puente a CCA, 1626 líneas
- `src/mundo_vivo/persistencia/sim_io.py` — cargar_simulacion, elegir_inicio, persistencia por dominio
- `src/mundo_vivo/persistencia/db.py` — migraciones, backups
- `src/mundo_vivo/registro.py` — registro de contenido JSON
- `src/mundo_vivo/reglas.py` — motor de reglas declarativas
- `src/mundo_vivo/condiciones.py` — evaluador de condiciones
- `api/presentador.py` — capa de traducción al visor
- `api/vivo.py` — ejecutor en vivo (20 Hz)
- `api/servidor.py` — FastAPI REST
- `ui/vivo.js` — frontend, bug stale data al cambiar dimensión
- `tests/test_modularizacion.py` — tests de fronteras modulares
- `tests/` — 48 archivos de prueba

**Fin del documento A1.** Solo lectura. Ningún código funcional modificado. Sin commits.

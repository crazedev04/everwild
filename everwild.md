EVERWILD
Arquitectura integral de generación procedural, mundo, recursos, ecosistemas, sociedades e invenciones
Propuesta ampliada — Versión 2.0
1. Primero: cómo se organiza el sistema
Hay cuatro tipos de información que no debemos mezclar.
Tipo	Qué contiene	Formato recomendado
Definiciones	Materiales, especies, minerales, objetos, biomas, procesos.	JSON
Reglas	Generación, distribución, clima, comportamiento, transformaciones.	JSON
Lógica	Algoritmos de generación, simulación, validación y comportamiento.	Código del motor
Estado del mundo	Organismos, depósitos, inventos, ciudades, eventos, comercio.	SQLite

Por ejemplo, JSON puede definir que existen volcanes y sus características. Pero el algoritmo que calcula una erupción, modifica el terreno y genera lava pertenece al código del motor.

No vamos a convertir todo en JSON. Vamos a utilizar JSON para que el motor pueda leer, validar y modificar sus definiciones sin tener que reprogramar cada elemento.

2. Estructura completa de datos
Esta sería la organización propuesta para data/.
data/
│
├── manifest.json
│
├── schemas/
│   ├── material.schema.json
│   ├── mineral.schema.json
│   ├── object.schema.json
│   ├── species.schema.json
│   ├── biome.schema.json
│   ├── process.schema.json
│   ├── technology.schema.json
│   ├── generation.schema.json
│   └── event.schema.json
│
├── world/
│   ├── world_profiles.json
│   ├── planet_parameters.json
│   ├── generation_parameters.json
│   └── natural_laws.json
│
├── geography/
│   ├── continents.json
│   ├── oceans.json
│   ├── elevation.json
│   ├── terrain_types.json
│   ├── mountains.json
│   ├── valleys.json
│   ├── plateaus.json
│   ├── plains.json
│   ├── islands.json
│   ├── caves.json
│   ├── canyons.json
│   └── coastlines.json
│
├── tectonics/
│   ├── plates.json
│   ├── boundaries.json
│   ├── earthquakes.json
│   ├── volcanism.json
│   ├── volcanic_types.json
│   ├── magma.json
│   └── geological_activity.json
│
├── hydrology/
│   ├── rivers.json
│   ├── lakes.json
│   ├── waterfalls.json
│   ├── watersheds.json
│   ├── groundwater.json
│   ├── aquifers.json
│   ├── wetlands.json
│   ├── glaciers.json
│   ├── oceans.json
│   ├── tides.json
│   ├── currents.json
│   ├── waves.json
│   └── erosion.json
│
├── climate/
│   ├── temperature.json
│   ├── humidity.json
│   ├── precipitation.json
│   ├── seasons.json
│   ├── wind.json
│   ├── atmospheric_pressure.json
│   ├── storms.json
│   ├── droughts.json
│   ├── snow.json
│   └── climate_change.json
│
├── geology/
│   ├── rock_types.json
│   ├── geological_layers.json
│   ├── soil_types.json
│   ├── sedimentation.json
│   ├── erosion.json
│   ├── fossil_deposits.json
│   └── geological_formation.json
│
├── minerals/
│   ├── native_elements.json
│   ├── oxides.json
│   ├── sulfides.json
│   ├── sulfates.json
│   ├── carbonates.json
│   ├── silicates.json
│   ├── phosphates.json
│   ├── halides.json
│   ├── gemstones.json
│   ├── industrial_minerals.json
│   ├── ores.json
│   ├── rocks.json
│   └── deposits.json
│
├── materials/
│   ├── organic.json
│   ├── wood.json
│   ├── fibers.json
│   ├── bones.json
│   ├── hides.json
│   ├── stone.json
│   ├── clay.json
│   ├── metals.json
│   ├── alloys.json
│   ├── liquids.json
│   ├── gases.json
│   ├── food.json
│   └── synthetic.json
│
├── objects/
│   ├── natural.json
│   ├── tools.json
│   ├── weapons.json
│   ├── containers.json
│   ├── furniture.json
│   ├── clothing.json
│   ├── components.json
│   ├── vehicles.json
│   └── structures.json
│
├── biology/
│   ├── plants/
│   ├── animals/
│   ├── fungi/
│   ├── microorganisms/
│   ├── insects/
│   ├── aquatic_life/
│   ├── ecosystems/
│   ├── reproduction/
│   ├── evolution/
│   ├── diseases/
│   └── domestication/
│
├── biomes/
│   ├── forests.json
│   ├── grasslands.json
│   ├── deserts.json
│   ├── tundras.json
│   ├── taigas.json
│   ├── wetlands.json
│   ├── mountains.json
│   ├── tropical.json
│   ├── aquatic.json
│   ├── coastal.json
│   └── transitions.json
│
├── distribution/
│   ├── vegetation.json
│   ├── animals.json
│   ├── minerals.json
│   ├── resources.json
│   ├── objects.json
│   ├── structures.json
│   └── constraints.json
│
├── processes/
│   ├── mechanical.json
│   ├── thermal.json
│   ├── chemical.json
│   ├── biological.json
│   ├── geological.json
│   ├── hydrological.json
│   ├── food_processing.json
│   └── environmental.json
│
├── technologies/
│   ├── firemaking.json
│   ├── stoneworking.json
│   ├── woodworking.json
│   ├── textiles.json
│   ├── ceramics.json
│   ├── agriculture.json
│   ├── animal_husbandry.json
│   ├── construction.json
│   ├── metallurgy.json
│   ├── chemistry.json
│   ├── mechanics.json
│   ├── navigation.json
│   ├── electricity.json
│   └── medicine.json
│
├── society/
│   ├── settlements.json
│   ├── social_organization.json
│   ├── roles.json
│   ├── laws.json
│   ├── customs.json
│   ├── languages.json
│   ├── cultures.json
│   ├── conflicts.json
│   ├── cooperation.json
│   └── migration.json
│
├── economy/
│   ├── goods.json
│   ├── trade.json
│   ├── currencies.json
│   ├── markets.json
│   ├── trade_routes.json
│   ├── production.json
│   ├── supply_and_demand.json
│   └── transportation.json
│
├── domestication/
│   ├── animal_taming.json
│   ├── animal_breeding.json
│   ├── plant_cultivation.json
│   ├── selective_breeding.json
│   ├── agricultural_methods.json
│   └── domestication_conditions.json
│
├── events/
│   ├── geological.json
│   ├── climatic.json
│   ├── ecological.json
│   ├── biological.json
│   ├── social.json
│   └── economic.json
│
├── actions/
│   ├── manipulation.json
│   ├── construction.json
│   ├── harvesting.json
│   ├── mining.json
│   ├── hunting.json
│   ├── agriculture.json
│   ├── social.json
│   └── exploration.json
│
└── generation/
    ├── geography_rules.json
    ├── geology_rules.json
    ├── hydrology_rules.json
    ├── climate_rules.json
    ├── biome_rules.json
    ├── distribution_rules.json
    ├── ecology_rules.json
    └── population_rules.json


Esta es una organización por dominios. No significa que haya que crear cientos de archivos vacíos. Se puede comenzar con archivos agrupados y separarlos cuando el volumen lo justifique.

3. Ejemplos reales de cómo deberían ser los JSON
Ahora viene lo importante: cómo se representarían las cosas.
3.1 Minerales
No alcanza con tener una lista que diga hierro, cobre y oro.

Hay que diferenciar minerales, elementos nativos, menas, rocas y depósitos.

Ejemplo de un mineral:

minerals/native_elements.json
{
  "schema_version": 1,
  "minerals": [
    {
      "id": "mineral.gold.native",
      "name": "Oro nativo",
      "chemical_formula": "Au",
      "category": "native_element",
      "properties": {
        "density_kg_m3": 19300,
        "hardness_mohs": 2.5,
        "melting_point_c": 1064,
        "conductivity": "high"
      },
      "uses": [
        "jewelry",
        "decoration",
        "currency",
        "electronics"
      ],
      "tags": [
        "metallic",
        "precious",
        "conductive"
      ]
    }
  ]
}


3.2 Catálogo mineralógico amplio
Como punto de partida, conviene contemplar estas familias:
Familia	Ejemplos
Elementos nativos	Oro, plata, cobre, azufre, grafito, diamante.
Óxidos	Hematita, magnetita, casiterita, corindón.
Sulfuros	Pirita, galena, calcopirita, esfalerita, cinabrio.
Carbonatos	Calcita, dolomita, malaquita, azurita.
Silicatos	Cuarzo, feldespato, mica, olivino, granate, talco.
Sulfatos	Yeso, barita, anhidrita.
Fosfatos	Apatita, monacita.
Halogenuros	Halita, fluorita, silvita.
Gemas	Rubí, zafiro, esmeralda, amatista, topacio, ópalo.
Minerales industriales	Caolín, talco, grafito, yeso, fluorita.

No todos son recursos explotables ni todos tienen que aparecer en cualquier mundo.
3.3 Menas
Una mena es un material geológico que contiene minerales aprovechables.

Ejemplo:
{
  "schema_version": 1,
  "id": "ore.iron.hematite",
  "name": "Mena de hierro hematítica",
  "category": "ore",
  "composition": [
    {
      "mineral": "mineral.hematite",
      "percentage": 65
    },
    {
      "mineral": "mineral.quartz",
      "percentage": 25
    },
    {
      "mineral": "mineral.other",
      "percentage": 10
    }
  ],
  "processing": [
    "crushing",
    "beneficiation",
    "smelting"
  ]
}


3.4 Depósitos minerales
Un depósito no es una definición global. Es una entidad generada en un mundo.

Por ejemplo:
{
  "id": "deposit_000182",
  "world_id": "mundo_872674866",
  "type": "ore.iron.hematite",
  "location": {
    "x": 420,
    "y": 780,
    "depth": 35
  },
  "estimated_quantity_kg": 850000,
  "concentration": 0.65,
  "accessibility": 0.45,
  "remaining_quantity_kg": 850000,
  "formation": "sedimentary"
}


Esto representa una instancia del mundo. Su estado debe persistirse en SQLite, no agregarse al JSON global.

4. Geología, tectónica y volcanes
Hay que incorporar un sistema geológico que permita que la superficie se modifique.

No solamente generar montañas al principio.

Debe contemplar:
- Placas tectónicas.
- Bordes convergentes.
- Bordes divergentes.
- Fallas.
- Terremotos.
- Actividad volcánica.
- Cámaras magmáticas.
- Flujos de lava.
- Cenizas.
- Erupciones.
- Formación de islas volcánicas.
- Calderas.
- Géiseres.
- Aguas termales.
- Erosión volcánica.
- Formación de nuevos depósitos minerales.
- Levantamiento y hundimiento del terreno.
Ejemplo de definición:

geology/volcano_types.json
{
  "schema_version": 1,
  "volcano_types": [
    {
      "id": "volcano.stratovolcano",
      "name": "Estratovolcán",
      "formation": "convergent_plate_boundary",
      "properties": {
        "eruption_style": [
          "explosive",
          "effusive"
        ],
        "lava_viscosity": "high",
        "ash_production": "high"
      },
      "possible_events": [
        "ash_fall",
        "lava_flow",
        "pyroclastic_flow",
        "gas_release"
      ]
    },
    {
      "id": "volcano.shield",
      "name": "Volcán en escudo",
      "formation": "hotspot_or_divergent_boundary",
      "properties": {
        "eruption_style": [
          "effusive"
        ],
        "lava_viscosity": "low",
        "ash_production": "low"
      },
      "possible_events": [
        "lava_flow",
        "land_expansion"
      ]
    }
  ]
}


El motor debe calcular cuándo y cómo ocurren estos eventos según su modelo geológico.

Una erupción puede cambiar el mundo: destruir vegetación, modificar cauces, cubrir suelos, generar nuevas tierras y modificar la disponibilidad de minerales.

5. Hidrología: ríos, océanos, mareas y cambios del agua
Este dominio debe tener mucha más profundidad que un simple generador de ríos.

Incluir:
- Ríos principales.
- Afluentes.
- Arroyos.
- Cuencas.
- Lagos.
- Lagunas.
- Cascadas.
- Deltas.
- Estuarios.
- Pantanos.
- Humedales.
- Acuíferos.
- Aguas subterráneas.
- Glaciares.
- Deshielo.
- Corrientes oceánicas.
- Mareas.
- Oleaje.
- Erosión fluvial.
- Inundaciones.
- Sequías.
- Cambios de cauce.
- Formación de nuevos ríos.
- Sedimentación.
5.1 Mareas
Las mareas no deberían ser simplemente una animación del nivel del mar.

Su modelo puede contemplar:
- Posición relativa de la Luna.
- Influencia solar.
- Período de marea.
- Amplitud.
- Geometría costera.
- Profundidad del agua.
- Estuarios y bahías.
Ejemplo de configuración:
{
  "schema_version": 1,
  "id": "hydrology.tides.default",
  "enabled": true,
  "drivers": {
    "lunar_influence": 0.70,
    "solar_influence": 0.30
  },
  "simulation": {
    "period_hours": 12.4,
    "calculate_local_amplitude": true,
    "consider_coast_geometry": true
  },
  "effects": [
    "shoreline_water_level",
    "coastal_habitat",
    "estuary_flow",
    "intertidal_resources"
  ]
}


Los valores son parámetros de ejemplo; la amplitud real debe depender de la geografía y del modelo astronómico.
5.2 Formación de nuevos ríos
Esto es especialmente importante.

Un río no debe quedar congelado en su forma inicial.

El sistema hidrológico puede permitir:
1. Lluvias intensas.
2. Escorrentía.
3. Formación de canales.
4. Erosión.
5. Unión de pequeños cauces.
6. Formación de nuevos afluentes.
7. Desbordamientos.
8. Cambios en el recorrido.
9. Formación de meandros.
10. Creación de lagos y deltas.
El algoritmo debe trabajar con elevación, drenaje, precipitación, permeabilidad y sedimentación.

No hace falta recalcular todo el mapa cada tick. Se pueden evaluar cambios locales y regionales.

6. Clima y fenómenos naturales
Además de temperatura y humedad, agregaría un catálogo de eventos climáticos:
- Tormentas.
- Tormentas eléctricas.
- Huracanes o ciclones.
- Tornados.
- Granizo.
- Nevadas.
- Heladas.
- Olas de calor.
- Olas de frío.
- Sequías.
- Inundaciones.
- Incendios naturales.
- Vientos extremos.
- Cambios estacionales.
- Variaciones climáticas prolongadas.
También agregaría ciclos de largo plazo:
- Avance y retroceso de glaciares.
- Cambios en precipitaciones.
- Desertificación.
- Cambios de vegetación.
- Variaciones de temperatura regional.
La simulación debe decidir qué procesos se ejecutan a escala local y cuáles se representan mediante estadísticas regionales.

7. Biología, ecosistemas y domesticación
Acá agregaría bastante más que plantas y animales.
7.1 Dominios biológicos
biology/
├── plants/
├── trees/
├── shrubs/
├── grasses/
├── crops/
├── fungi/
├── insects/
├── mammals/
├── birds/
├── reptiles/
├── amphibians/
├── fish/
├── aquatic_life/
├── microorganisms/
├── parasites/
├── diseases/
├── reproduction/
├── evolution/
└── ecosystems/


Cada especie debe poder definir:
- Hábitat.
- Biomas compatibles.
- Temperatura.
- Humedad.
- Alimentación.
- Reproducción.
- Ciclo de vida.
- Crecimiento.
- Longevidad.
- Depredadores.
- Competidores.
- Enfermedades.
- Comportamiento.
- Movilidad.
- Relación con otras especies.
7.2 Domesticación
Hay que diferenciar tres cosas:
1. Amansamiento: un individuo pierde parte de su temor o agresividad frente a los humanos.
2. Domesticación: una población cambia a lo largo de generaciones por selección y convivencia con humanos.
3. Mejoramiento selectivo: se favorecen características específicas mediante reproducción dirigida.
Ejemplo de definición:
{
  "schema_version": 1,
  "id": "domestication.animal.general",
  "process": "multi_generational_selection",
  "requirements": {
    "repeated_human_interaction": true,
    "controlled_reproduction": true,
    "population_stability": true
  },
  "selectable_traits": [
    "temperament",
    "size",
    "strength",
    "milk_production",
    "wool_production",
    "fertility",
    "disease_resistance"
  ],
  "outcomes": [
    "behavioral_adaptation",
    "population_trait_changes",
    "domesticated_population"
  ]
}


No significa que cualquier especie pueda domesticarse. La viabilidad debe depender de características biológicas y ecológicas.
7.3 Agricultura y cultivos
Agregar:
- Recolección de semillas.
- Germinación.
- Siembra.
- Cultivo.
- Riego.
- Fertilización.
- Rotación de cultivos.
- Plagas.
- Enfermedades vegetales.
- Cosecha.
- Almacenamiento.
- Selección de semillas.
- Hibridación.
- Domesticación vegetal.
Los habitantes podrían descubrir agricultura de forma emergente, no simplemente desbloquearla.

8. Sociedad, comercio y economía
Esto debe ser un dominio separado de la generación procedural.

La generación puede crear recursos y condiciones para que aparezcan asentamientos. Pero el comercio, la organización social y la economía deben evolucionar durante la simulación.
8.1 Sociedad
Contemplar:
- Grupos.
- Familias.
- Comunidades.
- Asentamientos.
- Aldeas.
- Ciudades.
- Roles sociales.
- División del trabajo.
- Cooperación.
- Conflictos.
- Liderazgo.
- Normas.
- Costumbres.
- Cultura.
- Lenguaje.
- Tradiciones.
- Migración.
- Alianzas.
- Relaciones entre comunidades.
8.2 Comercio
Contemplar:
- Intercambio directo.
- Trueque.
- Valor percibido.
- Oferta.
- Demanda.
- Escasez.
- Excedentes.
- Especialización productiva.
- Mercados.
- Rutas comerciales.
- Transporte.
- Almacenamiento.
- Comercio entre asentamientos.
- Comercio entre regiones.
- Monedas, si emergen.
- Conflictos por recursos.
- Interrupción de rutas.
- Impuestos o tributos, si aparecen formas de organización que los establezcan.
Ejemplo de configuración:

economy/trade.json
{
  "schema_version": 1,
  "id": "economy.trade.default",
  "exchange_methods": [
    "barter",
    "negotiated_exchange",
    "currency"
  ],
  "value_factors": [
    "scarcity",
    "production_cost",
    "demand",
    "utility",
    "transport_cost",
    "risk"
  ],
  "trade_conditions": {
    "require_available_goods": true,
    "consider_travel_distance": true,
    "consider_relationships": true,
    "consider_route_safety": true
  },
  "possible_outcomes": [
    "trade_agreement",
    "resource_exchange",
    "market_creation",
    "trade_route",
    "economic_dependency"
  ]
}


La configuración describe los mecanismos disponibles. No obliga a que todas las comunidades tengan mercados o monedas.

9. Tecnologías, metalurgia e invenciones
Mantendría estos dominios separados:
- Materiales.
- Acciones.
- Procesos.
- Tecnologías.
- Invenciones.
Una tecnología representa un cuerpo de conocimiento. Una invención es un descubrimiento concreto. Un proceso es algo que el motor puede simular.

Por ejemplo, un habitante puede descubrir una forma de producir una aleación. El motor comprueba los materiales, las proporciones y las condiciones. Si funciona, se registra el conocimiento en ese mundo.

Dominios tecnológicos que agregaría:
Dominio	Ejemplos
Metalurgia	Fundición, forja, aleaciones, temple.
Cerámica	Arcilla, hornos, cocción, vidriado.
Textiles	Hilado, tejido, teñido, fibras.
Agricultura	Cultivos, riego, selección de semillas.
Ganadería	Crianza, domesticación, reproducción.
Construcción	Adobe, piedra, madera, mampostería.
Mecánica	Palancas, poleas, engranajes.
Navegación	Embarcaciones, orientación, navegación costera.
Química	Mezclas, extracción, fermentación, reacciones.
Electricidad	Generación, conducción, almacenamiento.
Medicina	Plantas medicinales, heridas, tratamientos.
Transporte	Ruedas, carros, caminos, barcos.
Comunicación	Escritura, señales, sistemas de registro.

No deberían ser árboles de desbloqueo rígidos. La progresión debe depender del conocimiento, la disponibilidad de recursos y la capacidad de los habitantes.

10. Eventos dinámicos del mundo
Este sistema merece su propio dominio.

Un evento no es una decoración. Es algo que produce consecuencias.

Ejemplos:
Categoría	Eventos
Geológicos	Terremotos, erupciones, deslizamientos.
Hidrológicos	Inundaciones, sequías, cambios de cauce.
Climáticos	Tormentas, heladas, olas de calor.
Biológicos	Epidemias, plagas, extinciones locales.
Ecológicos	Incendios, expansión de especies, pérdida de hábitat.
Sociales	Guerras, migraciones, alianzas, fundación de asentamientos.
Económicos	Escasez, rutas comerciales, crisis productivas.

Cada evento debe tener:
- Causa.
- Condiciones.
- Probabilidad o criterio de activación.
- Alcance espacial.
- Duración.
- Intensidad.
- Efectos.
- Consecuencias secundarias.
- Registro histórico.
Ejemplo:
{
  "schema_version": 1,
  "id": "event.volcanic_eruption",
  "category": "geological",
  "trigger": {
    "source": "volcanic_activity",
    "conditions": [
      "pressure_threshold",
      "magma_availability"
    ]
  },
  "effects": [
    "terrain_modification",
    "lava_generation",
    "ash_deposition",
    "vegetation_damage",
    "air_quality_change"
  ],
  "secondary_effects": [
    "soil_fertility_change",
    "river_obstruction",
    "new_mineral_deposits"
  ]
}


Los efectos reales deben calcularse mediante los sistemas correspondientes, no ejecutarse como una lista ciega de cambios.

11. Ejemplo del manifest.json
Este archivo permite que el motor sepa qué dominios debe cargar.
{
  "engine_data_version": "2.0.0",
  "schema_version": 1,
  "domains": [
    "world",
    "geography",
    "tectonics",
    "hydrology",
    "climate",
    "geology",
    "minerals",
    "materials",
    "objects",
    "biology",
    "biomes",
    "distribution",
    "processes",
    "technologies",
    "society",
    "economy",
    "domestication",
    "events",
    "actions",
    "generation"
  ],
  "loading": {
    "validate_schemas": true,
    "validate_references": true,
    "build_memory_indexes": true
  }
}


Este es un ejemplo de organización, no un contrato definitivo. El agente debe diseñar el esquema real y sus dependencias.

12. Qué debe ocurrir durante la generación de un mundo
Este sería el flujo general:
1. Generación planetaria

Continentes, océanos y parámetros globales


2. Geografía y geología

Montañas, valles, placas, volcanes, rocas y depósitos


3. Hidrología y clima

Ríos, lagos, mareas, corrientes, temperaturas y estaciones


4. Biomas y suelos

Clasificación ambiental y condiciones ecológicas


5. Distribución de recursos y organismos

Minerales, plantas, animales y recursos naturales


6. Ecosistemas y poblaciones

Relaciones ecológicas, reproducción y cadenas alimentarias


7. Mundo persistente

Inicialización de regiones, organismos y estado guardado


Después de la generación comienza la evolución del mundo:

Clima dinámico, cambios geológicos, evolución biológica, domesticación, sociedades, comercio, tecnologías e invenciones.

La distinción es fundamental: algunos sistemas generan el estado inicial; otros permiten que ese estado evolucione.

13. Qué debe guardar SQLite
No todo debe vivir en los JSON.

Cada mundo tiene información que cambia continuamente.

Por ejemplo:
Tabla conceptual	Contenido
world_chunks	Regiones generadas y modificadas.
terrain_changes	Alteraciones del terreno.
mineral_deposits	Depósitos y cantidades restantes.
organisms	Individuos vivos.
populations	Poblaciones regionales.
domestication	Poblaciones domesticadas y progreso.
settlements	Asentamientos y comunidades.
trade_routes	Rutas comerciales existentes.
trade_transactions	Intercambios realizados.
inventions	Inventos descubiertos.
experiments	Experimentos realizados.
knowledge	Conocimiento de los habitantes.
world_events	Historia de eventos.
structures	Construcciones existentes.

Son entidades conceptuales; el agente debe diseñar las tablas y relaciones reales.

14. Instrucciones para el agente de desarrollo
Esta parte es la que le tenés que pasar al agente junto con todo el documento.
Primera tarea: auditoría y planificación, no reescritura
OBJETIVO:

Analizar la arquitectura actual de Everwild y elaborar un plan
de reestructuración tomando como referencia el documento
de arquitectura proporcionado.

No comenzar una reescritura general.

TAREAS:

1. Auditar la estructura actual del proyecto.

2. Identificar todos los sistemas existentes de:
   - Generación geográfica.
   - Clima.
   - Biomas.
   - Distribución de objetos.
   - Materiales.
   - Minerales.
   - Menas y depósitos.
   - Objetos y estructuras.
   - Recetas.
   - Metalurgia.
   - Electricidad.
   - Tecnologías.
   - Ecosistemas.
   - CCA.
   - Persistencia.

3. Inspeccionar los archivos JSON existentes.
   Identificar campos, inconsistencias, duplicaciones y referencias.

4. Determinar qué sistemas están mezclados y cuáles están
   correctamente separados.

5. Comparar la arquitectura actual con la arquitectura objetivo.

6. Proponer la estructura definitiva de carpetas y archivos.

7. Definir qué datos deben ser JSON y cuáles deben
   permanecer en código.

8. Definir schemas de validación y un cargador central.

9. Definir la persistencia de datos dinámicos por mundo.

10. Proponer una migración progresiva.

11. Definir pruebas de rendimiento y compatibilidad.

12. Identificar los riesgos de modificar sistemas existentes.

RESTRICCIONES:

- No borrar archivos existentes.
- No eliminar recetas o materiales.
- No regenerar mundos.
- No cambiar IDs sin compatibilidad.
- No modificar el mundo mundo_872674866.
- No reemplazar el generador actual sin auditoría.
- No implementar todos los sistemas de una vez.
- No introducir dependencias innecesarias.
- No duplicar sistemas que ya existen.

RESULTADO ESPERADO:

Entregar un documento de auditoría que incluya:

A. Arquitectura actual.
B. Árbol de carpetas actual.
C. Inventario de datos JSON.
D. Sistemas existentes y faltantes.
E. Problemas arquitectónicos.
F. Árbol de carpetas objetivo adaptado al repositorio.
G. Propuesta de schemas JSON.
H. Diseño del cargador y registry.
I. Diseño de persistencia.
J. Plan de migración por fases.
K. Riesgos y compatibilidad.
L. Pruebas y métricas.

Esperar aprobación antes de comenzar cambios estructurales.



15. Mi recomendación: qué es importante no perder de vista
Hay una diferencia entre tener un mundo enorme y tener un mundo vivo.

No quiero que Everwild solamente genere un continente con 200 tipos de árboles, 50 minerales y 100 animales.

Quiero que sus sistemas estén relacionados.

Por ejemplo:
1. Un volcán entra en erupción.
2. La lava modifica la geografía.
3. Las cenizas alteran el suelo.
4. Aparecen nuevas condiciones para la vegetación.
5. Se modifica el hábitat de los animales.
6. Algunas poblaciones migran.
7. Los habitantes encuentran nuevos minerales.
8. Experimentan con ellos.
9. Descubren una nueva técnica metalúrgica.
10. Esa técnica se transmite a otra comunidad.
11. Aparece el comercio de ese material.
12. Se desarrolla una ruta comercial.
13. Las comunidades empiezan a especializarse.

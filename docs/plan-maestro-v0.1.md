# Proyecto: Mundo Vivo
## Plan maestro de implementación — versión 0.1

**Estado:** documento base de planificación.  
**Objetivo:** construir un mundo 2D procedural, persistente y autónomo donde habitantes controlados por agentes de IA sobrevivan, aprendan, inventen, formen sociedades y evolucionen durante generaciones.

---

## 1. Visión del proyecto

No es un juego tradicional con personajes que ejecutan rutinas prefijadas. Es un experimento de vida artificial: nosotros definimos las leyes del mundo, los recursos, las capacidades posibles y las consecuencias; los habitantes deciden qué intentar hacer dentro de esas reglas.

El mundo debe poder continuar durante mucho tiempo, guardar su historia y conservar la identidad y los recuerdos de sus habitantes aunque se actualice o reemplace el código.

### Principios no negociables

1. **Autonomía:** los habitantes generan sus propios objetivos y pueden cambiar de opinión.
2. **Consecuencias:** las acciones consumen tiempo y recursos y pueden salir bien o mal.
3. **Persistencia:** actualizar el programa no debe borrar el mundo ni las memorias.
4. **Identidad individual:** cada habitante tiene personalidad, experiencias, conocimientos y memoria privada.
5. **Aprendizaje:** pueden aprender por experiencia, observación, ensayo y error y enseñanza social.
6. **Emergencia con límites verificables:** pueden proponer ideas y técnicas nuevas, pero el motor valida materiales, energía, herramientas, tiempo y reglas físicas.
7. **Observabilidad:** el usuario puede mirar el mundo y consultar qué ocurrió y por qué, sin tener que dirigir a los habitantes.
8. **Escalabilidad:** empezar pequeño y ampliar población, territorio y complejidad sin rehacer la arquitectura.

## 2. Decisiones acordadas

| Tema | Decisión |
|---|---|
| Presentación inicial | 2D, vista superior |
| Mundo | Un continente procedural, con semilla reproducible |
| Inicio | Cuatro habitantes en naturaleza salvaje, sin aldea ni edificios |
| Entorno | Biomas, costas, ríos, lagos, montañas, cuevas y subsuelo |
| Vida | Plantas, animales, depredadores, amenazas y ciclos naturales |
| IA | Local mediante Ollama |
| Modelo inicial | Qwen 3.5 4B, sujeto a pruebas de calidad y rendimiento |
| Persistencia | SQLite al principio, con exportación JSON y backups |
| Calendario | Día/noche, estaciones, años y control de velocidad |
| Velocidades | Normal, rápida, muy rápida y máxima configurable |
| Población | Empieza con cuatro; reproducción y generaciones en una fase posterior |
| Evolución | Aprendizaje individual/social y herencia generacional diferenciados |

La elección 2D es para concentrar recursos en simulación e inteligencia. El motor del mundo debe estar desacoplado de la representación para poder incorporar una vista 3D en el futuro.

## 3. Experiencia inicial

Al generar un mundo se crea un continente con una semilla aleatoria. Los cuatro habitantes aparecen en una zona inicial sin refugios, herramientas ni ciudad. No se les asigna una secuencia obligatoria de tareas.

El mundo ya existe y sigue sus propias reglas: hay recursos, animales, clima, peligros y zonas desconocidas. Los habitantes necesitan descubrir cómo sobrevivir.

No se debe garantizar que todos sobrevivan. Pueden cooperar, separarse, competir, enfermar, sufrir accidentes o morir. La simulación debe registrar sus historias sin convertir los resultados en guiones predeterminados.

## 4. Generación procedural del mundo

### 4.1 Enfoque

Usar un mapa de celdas/t tiles en capas, no simular cada píxel. La generación debe ser determinista a partir de una semilla: la misma semilla y versión del generador producen el mismo mapa.

Generar primero la geografía a gran escala y después poblarla con biomas, recursos, flora, fauna y puntos de interés.

### 4.2 Capas geográficas

- **Superficie:** terreno, agua, vegetación, estructuras, animales y habitantes.
- **Subsuelo:** suelo excavable, cavernas, túneles, depósitos minerales, agua subterránea y peligros.
- **Altura y relieve:** llanuras, colinas, montañas, acantilados y valles.
- **Hidrología:** océano, costas, ríos conectados, lagos, pantanos y fuentes de agua.
- **Clima:** temperatura, humedad, lluvia, nieve, viento y tormentas.

### 4.3 Biomas iniciales propuestos

- Bosque templado.
- Pradera.
- Montaña.
- Pantano.
- Costa y playa.
- Bosque frío o zona nevada.
- Región árida.

No hace falta que todos aparezcan en cada continente. Su distribución depende de latitud, altura, humedad y temperatura simuladas.

### 4.4 Cuevas y subsuelo

Las cuevas deben formar redes conectadas, no simples decoraciones. Pueden contener minerales, agua, fauna propia, oscuridad, derrumbes y otros riesgos. La exploración requiere luz, herramientas o preparación adecuada.

### 4.5 Recursos y ecología

Los recursos no deben ser infinitos ni aparecer mágicamente en el inventario. Deben tener ubicación, cantidad, regeneración y condiciones ambientales.

Ejemplos: madera, ramas, piedra, arcilla, fibras, frutos, semillas, agua, minerales, carbón y alimentos animales. Las plantas crecen y se reproducen según estación, suelo y clima. Los animales comen, se desplazan, huyen, cazan y se reproducen según reglas ecológicas.

### 4.6 Fauna y amenazas

La fauna debe tener necesidades y comportamientos propios: herbívoros, omnívoros, depredadores, animales nocturnos y especies de zonas concretas. Las amenazas pueden incluir depredadores, clima extremo, enfermedades, accidentes, incendios y escasez.

No implementar decenas de especies al comienzo. Empezar con unas pocas especies que permitan probar una cadena alimentaria y relaciones depredador-presa.

## 5. Habitantes y arquitectura de agentes

Cada habitante tiene un identificador permanente y un estado independiente.

### 5.1 Componentes individuales

- Identidad y nombre.
- Personalidad y predisposiciones.
- Necesidades físicas: hambre, sed, energía, salud, temperatura y seguridad.
- Estado emocional simulado.
- Memoria episódica: eventos vividos.
- Memoria semántica: conocimientos y conclusiones.
- Habilidades y nivel de práctica.
- Relaciones y confianza hacia otros.
- Objetivos actuales y objetivos de largo plazo.
- Creencias y opiniones, con evidencia y grado de confianza.
- Inventario y pertenencias.
- Historial de decisiones, éxitos y fracasos.

### 5.2 Privacidad de memoria

Cada agente recibe únicamente sus recuerdos privados y la información pública que puede percibir o conocer. No se debe incluir la memoria privada de otros en su contexto.

La interacción social transmite información mediante conversación, observación y enseñanza; no mediante lectura directa de otra base de memoria.

El motor y la base de datos aplican el aislamiento. No se debe confiar solamente en una instrucción al modelo diciendo que no lea recuerdos ajenos.

### 5.3 Decisión autónoma

El motor mantiene el mundo y sus reglas. El agente recibe una percepción limitada de su entorno, sus necesidades, objetivos y recuerdos relevantes. Propone una intención o plan estructurado. El motor comprueba si es posible, ejecuta o rechaza la acción y registra el resultado.

El agente puede:
- Mantener objetivos propios.
- Crear subobjetivos.
- Cambiar prioridades.
- Elegir cooperar o no.
- Formar opiniones y revisarlas.
- Intentar acciones nuevas dentro de las capacidades disponibles.
- Abandonar planes cuando cambian las circunstancias.

El modelo no debe decidir directamente posiciones, inventarios o resultados físicos: eso corresponde al motor determinista.

### 5.4 Aprendizaje

Separar:
- Aprendizaje individual por ensayo y error.
- Aprendizaje por observación.
- Enseñanza y transmisión cultural.
- Aprendizaje de habilidades mediante práctica.
- Revisión de creencias por evidencia nueva.

No afirmar que el modelo se reentrena solo. En la primera etapa el aprendizaje se implementa mediante memoria, habilidades, reglas descubiertas, preferencias y cambios de estrategia guardados. El fine-tuning o entrenamiento de modelos queda fuera del MVP.

## 6. Sueño, reflexión y emociones

Dormir tiene consecuencias físicas: recupera energía y reduce riesgos. Durante el descanso se ejecuta una tarea de consolidación:

1. Seleccionar eventos recientes relevantes.
2. Resumir experiencias sin borrar los eventos originales.
3. Relacionar experiencias y conocimientos.
4. Registrar aprendizajes, cambios de opinión y preguntas pendientes.
5. Revisar objetivos para el siguiente período.

Los “sueños” se representan como asociaciones o simulaciones internas generadas durante la reflexión; no se presentan como prueba de conciencia.

El estado emocional es una variable simulada que influye en decisiones y expresiones. Puede reflejar bienestar, miedo, frustración, curiosidad, soledad, confianza o entusiasmo. No se debe tratar como diagnóstico humano.

## 7. Invención, tecnología y experimentación

La creatividad debe estar conectada con el mundo físico.

### 7.1 Sistema de fabricación

Las recetas conocidas se almacenan como conocimiento. Los habitantes pueden combinar materiales y proponer recetas nuevas. El motor valida:
- Materiales y cantidades.
- Herramientas necesarias.
- Conocimientos o habilidades.
- Tiempo y energía.
- Condiciones del entorno.
- Resultado físico permitido.

Un intento inválido puede fallar y generar aprendizaje. Una receta nueva solo se incorpora al catálogo del mundo cuando supera las reglas de validación.

### 7.2 Progresión tecnológica

No imponer un árbol tecnológico rígido. Puede existir un catálogo de posibilidades físicas, pero el orden de descubrimiento depende de los habitantes y los recursos.

Áreas posibles: fuego, refugio, herramientas, recipientes, agricultura, pesca, caza, tejido, minería, metalurgia, transporte, construcción y medicina básica.

### 7.3 Construcción

Los edificios se construyen por partes y requieren materiales, tiempo y trabajo. Pueden deteriorarse por clima, uso, incendios o ataques. La construcción puede tener diseños y funciones emergentes, siempre dentro de reglas de estabilidad y materiales.

## 8. Sociedad y generaciones

Las relaciones se desarrollan a partir de interacciones y eventos. Deben existir cooperación, amistad, rivalidad, confianza, intercambio, acuerdos, conflictos y reconciliaciones.

La reproducción se implementará después de que supervivencia y relaciones sean estables. La descendencia puede heredar predisposiciones limitadas y algunos rasgos, pero comienza con identidad, experiencias y personalidad propias. No hereda automáticamente los recuerdos de sus padres.

La evolución biológica y el aprendizaje cultural deben ser sistemas separados. Las mutaciones y la herencia necesitan reglas explícitas y medibles.

## 9. Tiempo y simulación

El mundo tiene reloj propio: minutos, horas, días, estaciones y años. El día/noche y las estaciones afectan clima, plantas, animales, necesidades y decisiones.

Controles previstos:
- Pausa.
- 1× tiempo normal.
- 5×.
- 20×.
- 100× o máximo configurable.

La velocidad del mundo no puede superar la capacidad de cómputo de forma gratuita. Separar el tiempo simulado del tiempo real y administrar las consultas al modelo con una cola y límites de concurrencia. Los procesos físicos simples pueden avanzar muchos ticks sin llamar al LLM. Los agentes piensan cuando hay motivos, cambios relevantes o vencimiento de su intervalo de decisión.

## 10. Arquitectura técnica propuesta

| Capa | Tecnología inicial | Responsabilidad |
|---|---|---|
| Interfaz 2D | JavaScript + Canvas (o PixiJS) | Renderizar mapa, habitantes, paneles y controles |
| API y servidor | Python + FastAPI | Coordinar simulación, guardado y clientes |
| Motor de mundo | Python | Tiempo, física simplificada, recursos, ecología y validación |
| Agentes | Adaptador de modelos + Ollama | Decisiones, reflexión y comunicación |
| Persistencia | SQLite | Mundo, habitantes, eventos, memorias y versiones |
| Tiempo real | WebSocket | Actualizar la interfaz |
| Exportación | JSON + SQLite | Copias portables y análisis externo |

El motor, los agentes, la persistencia y la interfaz deben ser módulos separados. La vista 2D no debe contener reglas de supervivencia. Esto permitirá una vista 3D futura sin reescribir la simulación.

### Rendimiento

La RTX 4060 se comparte entre el modelo local y el resto del sistema. No llamar al modelo en cada tick. Usar:
- Cola de solicitudes.
- Límite de concurrencia.
- Intervalos de decisión.
- Contextos breves y memoria recuperada por relevancia.
- Tareas de reflexión en momentos de descanso.
- Simulación física por lotes cuando sea seguro.

Probar primero con cuatro agentes y medir latencia, uso de VRAM/RAM y velocidad simulada antes de aumentar población.

## 11. Persistencia, migraciones y copias de seguridad

La base de datos es independiente del código fuente y debe vivir en un directorio de datos persistente.

Separar:
- Estado actual del mundo.
- Semilla y versión del generador.
- Habitantes e identidades.
- Memorias y conocimientos.
- Eventos históricos.
- Inventarios y estructuras.
- Calendario y clima.
- Definiciones de especies, recetas y reglas.

Cada cambio de esquema debe usar migraciones versionadas. Nunca borrar ni recrear la base automáticamente al iniciar una versión nueva.

Política inicial:
- Guardado automático periódico y después de eventos importantes.
- Backup rotativo antes de migraciones.
- Exportación completa a un paquete con base de datos, semilla, versión del mundo y metadatos.
- Exportación de habitantes por separado, conservando IDs y relaciones.
- Prueba periódica de restauración.

La memoria no debe depender de archivos temporales, del prompt del modelo ni de la versión de Ollama.

## 12. Panel de observación

La interfaz debe permitir observar sin controlar obligatoriamente.

### Vista del mundo
- Mapa desplazable y zoom.
- Biomas, agua, relieve, cuevas descubiertas y estructuras.
- Habitantes y animales.
- Día, hora, estación y año.
- Velocidad y pausa.
- Eventos recientes.

### Ficha de habitante
- Personalidad y estado actual.
- Necesidades y salud.
- Inventario y habilidades.
- Objetivos y planes.
- Relaciones.
- Recuerdos relevantes e historial.
- Conocimientos y cambios de opinión.

### Herramientas de observación
- Línea de tiempo histórica.
- Registro de eventos.
- Estadísticas de población, muertes, nacimientos y recursos.
- Registro explicable de decisiones: qué percibió, qué recordó, qué intentó y qué resultado obtuvo.

El usuario podrá inspeccionar, pero las intervenciones directas deben ser opcionales y quedar registradas para distinguirlas de las decisiones autónomas.

## 13. Fases de implementación

### Fase 0 — Diseño y cimientos
- Definir reglas y formatos de datos.
- Separar motor, agentes, base de datos e interfaz.
- Implementar semillas y versiones.
- Definir guardado, backups y migraciones.
- Crear pruebas automatizadas básicas.

**Salida:** proyecto organizado y persistencia confiable.

### Fase 1 — Continente procedural
- Generar un continente reproducible.
- Crear relieve, costas, ríos, lagos y biomas.
- Crear capas de superficie y subsuelo.
- Generar algunas cuevas y depósitos.
- Renderizar mapa 2D y permitir explorarlo.

**Salida:** un mundo que se puede generar, guardar y volver a cargar.

### Fase 2 — Ecología y supervivencia
- Plantas y recursos renovables.
- Agua, clima y ciclos día/noche.
- Un pequeño conjunto de especies animales.
- Alimentación, huida, depredación y reproducción animal básica.
- Necesidades de los habitantes y consecuencias de hambre, sed, clima y lesiones.

**Salida:** mundo que funciona aunque no haya intervención del usuario.

### Fase 3 — Cuatro agentes autónomos
- Identidad, personalidad y necesidades.
- Percepción limitada.
- Decisiones estructuradas y validadas.
- Movimiento, exploración, recolección, descanso y refugio básico.
- Memoria privada persistente.
- Registro de decisiones y resultados.

**Salida:** cuatro habitantes que intentan sobrevivir de manera independiente.

### Fase 4 — Memoria, reflexión y relaciones
- Memoria episódica y semántica.
- Consolidación durante el sueño.
- Estados emocionales simulados.
- Relaciones, confianza, conflictos y cooperación.
- Comunicación y enseñanza.

**Salida:** individuos con historias y relaciones que cambian.

### Fase 5 — Fabricación, construcción e invención
- Inventarios y recetas.
- Ensayo y error.
- Herramientas y materiales.
- Construcciones por etapas.
- Descubrimiento y validación de técnicas nuevas.

**Salida:** habitantes capaces de transformar el entorno.

### Fase 6 — Sociedad y generaciones
- Reproducción de habitantes.
- Herencia de predisposiciones.
- Infancia, aprendizaje y transmisión cultural.
- Grupos, acuerdos, propiedad y conflictos.
- Estadísticas multigeneracionales.

**Salida:** una sociedad que puede crecer y cambiar durante generaciones.

### Fase 7 — Mundo avanzado y escalabilidad
- Más biomas y especies.
- Enfermedades, eventos naturales y amenazas adicionales.
- Comercio, especialización y asentamientos.
- Optimización de población y simulación por regiones.
- Herramientas de análisis y experimentos comparativos.
- Evaluar una representación 3D opcional.

**Salida:** experimento de vida artificial de larga duración.

## 14. Criterios de éxito

No medir el éxito por lo bonito del mapa o por lo convincente que suena una respuesta del modelo.

Medir:
- ¿Sobreviven sin instrucciones directas?
- ¿Descubren estrategias diferentes?
- ¿Recuerdan experiencias y actúan en consecuencia?
- ¿Cambian opiniones ante acontecimientos?
- ¿Enseñan conocimientos a otros?
- ¿Inventan soluciones que pasan la validación física?
- ¿Se forman relaciones y conflictos con causas rastreables?
- ¿Las comunidades desarrollan diferencias culturales?
- ¿El mundo puede avanzar meses/años sin intervención?
- ¿Una actualización conserva mundo, habitantes e historial?
- ¿Se puede exportar y restaurar una partida completa?

## 15. Riesgos y límites que debemos controlar

1. **El modelo no es consciente por el hecho de tener memoria o hablar de emociones.** Es un experimento de agentes y comportamientos emergentes.
2. **La autonomía no es ilimitada.** Los agentes solo pueden actuar sobre las capacidades que el motor ofrece; nuevas capacidades requieren mecanismos de composición y validación.
3. **El modelo puede inventar hechos.** Solo el motor confirma recursos, posiciones, resultados y reglas.
4. **La memoria puede crecer demasiado.** Usar eventos originales, resúmenes versionados y recuperación selectiva; no borrar la historia fuente.
5. **El rendimiento puede limitar la población.** Medir antes de escalar y no invocar al LLM por cada acción.
6. **Los cambios de código pueden romper partidas.** Migraciones, backups y pruebas de restauración son obligatorios.
7. **La privacidad entre agentes requiere aislamiento en el servidor.** No alcanza con pedirle al modelo que no revele recuerdos ajenos.
8. **Las invenciones deben ser comprobables.** Una idea narrada no equivale a un objeto construido o una técnica funcional.

## 16. Próximo paso concreto

Antes de ampliar el prototipo existente, hacer una revisión técnica del MVP y decidir qué se conserva y qué se reemplaza. El primer hito no es “hacer que hablen”: es generar un continente reproducible y guardarlo correctamente.

Orden inmediato:
1. Revisar el código del MVP existente.
2. Definir el formato de mundo, coordenadas, capas y semilla.
3. Diseñar esquema SQLite versionado.
4. Implementar generador procedural de continente y biomas.
5. Renderizar y guardar/cargar el mismo mundo.
6. Recién después sumar ecología y agentes.

---

## 17. Registro de decisiones y cambios

Este documento es la fuente principal de planificación. Cada cambio importante debe anotarse con:
- Fecha.
- Decisión.
- Motivo.
- Alternativas consideradas.
- Impacto en datos guardados y compatibilidad.
- Fase afectada.

**Regla de trabajo:** no cambiar silenciosamente una decisión acordada ni eliminar datos de una partida. Si una modificación requiere migrar o reiniciar el mundo, explicarlo y crear primero una copia de seguridad.

**Estado actual:** visión y dirección general acordadas; arquitectura propuesta; detalles de implementación pendientes de validación. No se considera implementado ningún sistema por el solo hecho de estar descrito en este documento.

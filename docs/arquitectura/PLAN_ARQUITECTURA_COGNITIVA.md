# Plan de Arquitectura Cognitiva de los Habitantes
## Proyecto Mundo Vivo

**Estado:** Propuesta de arquitectura para análisis y planificación  
**Objetivo:** Diseñar e implementar un sistema cognitivo individual para cada habitante del mundo simulado.

---

# 1. Visión general

El objetivo es que cada habitante de Mundo Vivo tenga una mente propia, capaz de interpretar su entorno, recordar experiencias, adquirir conocimientos, aprender habilidades, desarrollar una personalidad, establecer objetivos, tomar decisiones y modificar su comportamiento a lo largo de su existencia.

No se busca crear personajes que simplemente ejecuten comportamientos predefinidos ni que reaccionen únicamente a necesidades básicas.

Se busca construir habitantes autónomos cuyas decisiones estén influenciadas por:

- Su personalidad y temperamento.
- Sus necesidades y motivaciones.
- Sus experiencias anteriores.
- Sus conocimientos y creencias.
- Sus habilidades adquiridas.
- Sus relaciones con otros habitantes.
- Su interpretación de los acontecimientos.
- Sus objetivos y planes.
- Su evolución individual a lo largo del tiempo.

Dos habitantes pueden experimentar exactamente el mismo acontecimiento y llegar a conclusiones diferentes. Sus historias personales deben influir en cómo interpretan el mundo.

La arquitectura debe permitir que cada habitante desarrolle una trayectoria individual, sin depender de una secuencia de comportamientos escritos de antemano.

# 2. Principios de diseño

La implementación deberá respetar los siguientes principios:

1. **Individualidad:** cada habitante debe poseer un estado mental propio y persistente.
2. **Continuidad:** las experiencias anteriores deben influir en las decisiones futuras.
3. **Aprendizaje:** los habitantes deben poder adquirir conocimientos y habilidades mediante experiencias.
4. **Evolución:** las personalidades, creencias, preferencias y relaciones pueden cambiar.
5. **Autonomía:** los habitantes deben poder generar objetivos propios.
6. **Coherencia:** las decisiones deben considerar los conocimientos, recursos, capacidades y circunstancias reales del individuo.
7. **Memoria selectiva:** no todos los acontecimientos tienen la misma importancia ni deben conservarse de la misma manera.
8. **Adaptabilidad:** los habitantes deben poder modificar sus planes cuando cambian las circunstancias.
9. **Persistencia:** la identidad, memoria y evolución deben sobrevivir a la interrupción y reinicio de la simulación.
10. **Eficiencia:** la actividad cognitiva debe organizarse por prioridades y no bloquear la evolución del mundo.

# 3. Arquitectura general del cerebro

El cerebro debe estar compuesto por módulos especializados que compartan información y trabajen como un sistema integrado.

## 3.1. Percepción

Responsable de interpretar los estímulos provenientes del mundo.

Debe procesar:

- Percepción visual del entorno.
- Sonidos y acontecimientos auditivos.
- Presencia y comportamiento de otros habitantes.
- Objetos, recursos y estructuras.
- Cambios ambientales y climáticos.
- Amenazas y situaciones peligrosas.
- Acontecimientos relevantes.
- Información recibida mediante comunicación.

La percepción no debe guardar indiscriminadamente cada estímulo. Debe identificar acontecimientos significativos, detectar cambios y evitar duplicaciones.

Debe diferenciar entre:

- Información observada directamente.
- Información escuchada de otro individuo.
- Información inferida.
- Información desconocida.

Esta distinción es importante para evitar que un habitante trate una suposición o un rumor como un hecho comprobado.

## 3.2. Sistema 1: pensamiento rápido

Sistema de procesamiento reactivo y automático.

Responsable de resolver situaciones que no requieren una deliberación profunda.

Ejemplos:

- Apartarse de un peligro inmediato.
- Reaccionar ante un ataque.
- Buscar refugio ante condiciones ambientales adversas.
- Responder a necesidades urgentes.
- Reconocer situaciones familiares.
- Ejecutar habilidades conocidas.
- Activar respuestas emocionales.

Debe funcionar mediante sistemas deterministas de bajo costo, como Utility AI, máquinas de estados o árboles de comportamiento.

No debe depender de procesos deliberativos para responder a situaciones urgentes.

## 3.3. Sistema 2: pensamiento deliberativo

Responsable del razonamiento complejo y la planificación.

Debe permitir:

- Evaluar diferentes alternativas.
- Analizar consecuencias.
- Relacionar acontecimientos anteriores.
- Formular hipótesis.
- Resolver problemas nuevos.
- Elaborar estrategias.
- Planificar acciones a corto y largo plazo.
- Revisar decisiones anteriores.
- Cambiar de opinión ante nueva evidencia.
- Evaluar riesgos y oportunidades.

Debe activarse según la relevancia de las situaciones, la incertidumbre, los objetivos y la necesidad de deliberación.

No debe ejecutarse continuamente ni ser necesario para cada movimiento.

## 3.4. Sistema de memoria

La memoria será uno de los componentes centrales de la identidad de cada habitante.

No debe limitarse a una lista de mensajes o a una base de datos de texto.

Debe organizarse en distintos tipos de memoria.

### A. Memoria episódica

Registra acontecimientos experimentados por el individuo.

Ejemplos:

- Encontró una fuente de alimento.
- Fue atacado por un animal.
- Descubrió una cueva.
- Perdió un objeto.
- Presenció una discusión.
- Recibió ayuda de otro habitante.

Cada recuerdo debe incluir, cuando corresponda:

- Momento del acontecimiento.
- Lugar.
- Participantes.
- Descripción.
- Importancia.
- Impacto emocional.
- Origen de la información.
- Grado de certeza.
- Relación con otros recuerdos.

### B. Memoria semántica

Almacena conocimientos y conclusiones generales.

Ejemplos:

- Determinadas plantas son comestibles.
- Una zona presenta peligros frecuentes.
- Ciertos materiales pueden combinarse.
- Un recurso puede encontrarse en determinado bioma.
- Un individuo posee conocimientos sobre construcción.

Los conocimientos deben poder adquirirse, actualizarse y corregirse.

Es importante conservar la diferencia entre hechos comprobados, creencias e hipótesis.

### C. Memoria procedimental

Almacena habilidades y procedimientos aprendidos.

Ejemplos:

- Fabricar una herramienta.
- Construir un refugio.
- Obtener alimento.
- Encender fuego.
- Preparar determinados materiales.
- Utilizar herramientas.
- Ejecutar procedimientos complejos.

Cada habilidad debe registrar:

- Requisitos.
- Recursos necesarios.
- Secuencia de pasos.
- Capacidades requeridas.
- Condiciones de utilización.
- Riesgos conocidos.
- Resultados anteriores.
- Nivel de dominio.
- Posibles limitaciones.

Las habilidades deben poder reutilizarse y combinarse.

### D. Memoria social

Almacena información individual sobre otros habitantes.

Ejemplos:

- Identidad de otros individuos.
- Experiencias compartidas.
- Comportamientos observados.
- Interacciones anteriores.
- Confianza.
- Desconfianza.
- Cooperación.
- Conflictos.
- Opiniones y expectativas.
- Información conocida sobre sus habilidades y conocimientos.

La percepción de otro individuo debe poder cambiar con el tiempo.

### E. Memoria autobiográfica

Representa la historia personal del habitante.

Debe permitir reconstruir aspectos como:

- Acontecimientos importantes de su vida.
- Experiencias que marcaron su comportamiento.
- Descubrimientos.
- Pérdidas.
- Relaciones significativas.
- Objetivos alcanzados o abandonados.
- Cambios personales.

No debe ser simplemente un resumen de todos los recuerdos: debe conservar una representación coherente de la trayectoria individual.

## 3.5. Recuperación de recuerdos

Inspirado en Generative Agents.

Cuando un habitante necesita tomar una decisión, debe recuperar información relevante sin consultar toda su memoria.

La recuperación puede considerar:

- Recencia: cuándo ocurrió.
- Importancia: cuánto impacto tuvo.
- Relevancia: relación con la situación actual.
- Frecuencia: cuántas veces ocurrió.
- Carga emocional: qué impacto tuvo en el individuo.
- Confianza: qué tan fiable es la información.
- Relaciones causales: qué acontecimientos están vinculados.

La recuperación debe poder encontrar tanto recuerdos recientes como experiencias antiguas importantes.

No debe limitarse a los últimos cinco acontecimientos.

## 3.6. Reflexión y formación de conocimientos

Inspirado en el mecanismo de Reflection de Generative Agents.

El habitante debe poder analizar sus experiencias y producir conclusiones de nivel superior.

Ejemplo:

Experiencias:
- Encontró restos de animales en una zona.
- Vio un depredador cerca del lugar.
- Fue atacado al regresar.

Posible conclusión:
- La zona podría ser territorio de un depredador.

Esta conclusión debe almacenarse como una creencia o hipótesis, no como un hecho confirmado.

La reflexión debe permitir:

- Detectar patrones.
- Relacionar experiencias.
- Formular hipótesis.
- Generar conclusiones.
- Identificar contradicciones.
- Revisar creencias.
- Aprender de errores.
- Reconocer situaciones recurrentes.

Las conclusiones deben poder ser contrastadas con experiencias posteriores.

## 3.7. Identidad y personalidad

Cada habitante debe poseer una identidad individual y persistente.

Debe contemplar:

### Rasgos relativamente estables

- Temperamento.
- Nivel de curiosidad.
- Prudencia.
- Agresividad.
- Sociabilidad.
- Cooperación.
- Competitividad.
- Tolerancia al riesgo.
- Perseverancia.
- Tendencia a explorar.

### Estados variables

- Estado emocional.
- Estrés.
- Confianza.
- Miedo.
- Frustración.
- Motivación.
- Satisfacción.
- Cansancio.

### Valores y preferencias

- Preferencias alimentarias.
- Lugares preferidos.
- Actividades favoritas.
- Objetivos personales.
- Valores individuales.
- Aversión a determinadas situaciones.
- Preferencias sociales.

La personalidad no debe ser una colección de etiquetas estáticas.

Debe influir en la percepción, interpretación, decisiones, comunicación y comportamiento.

Algunos rasgos pueden evolucionar mediante experiencias, pero no deberían cambiar arbitrariamente de un momento a otro.

## 3.8. Motivaciones y generación de objetivos

El habitante debe ser capaz de generar objetivos propios.

Los objetivos pueden surgir de:

- Necesidades biológicas.
- Curiosidad.
- Experiencias anteriores.
- Intereses personales.
- Relaciones.
- Descubrimientos.
- Problemas pendientes.
- Aspiraciones.
- Valores.
- Oportunidades detectadas.

Deben existir diferentes escalas:

- Objetivos inmediatos.
- Objetivos de corto plazo.
- Objetivos de largo plazo.
- Objetivos recurrentes.
- Objetivos sociales.
- Objetivos de supervivencia.
- Objetivos exploratorios.

Los objetivos deben tener prioridad, motivación, condiciones de cumplimiento y posibilidad de abandono o modificación.

Un habitante también debe poder mantener objetivos que no respondan a una necesidad inmediata.

## 3.9. Planificación y ejecución

Se propone utilizar una combinación de:

- Utility AI para evaluar prioridades.
- GOAP para construir planes orientados a objetivos.
- Behavior Trees o máquinas de estados para controlar la ejecución.

El proceso debería ser:

1. El individuo identifica una necesidad, oportunidad o intención.
2. Evalúa su importancia.
3. Selecciona un objetivo.
4. Recupera conocimientos y habilidades relevantes.
5. Construye un plan.
6. Comprueba recursos y condiciones.
7. Ejecuta las acciones.
8. Evalúa los resultados.
9. Modifica o abandona el plan cuando sea necesario.

Un plan fallido debe producir información útil para decisiones futuras.

No se debe asumir que un habitante puede ejecutar acciones para las que no tiene capacidad o recursos.

## 3.10. Aprendizaje y adquisición de habilidades

Inspirado en Voyager.

Los habitantes deben poder aprender procedimientos mediante experimentación, observación y experiencia.

El aprendizaje puede surgir de:

- Intentos propios.
- Prueba y error.
- Observación de otros individuos.
- Enseñanza.
- Descubrimientos.
- Combinación de conocimientos existentes.

Una habilidad nueva no debe considerarse válida solamente porque fue propuesta.

Debe pasar por un proceso de validación contra las reglas del mundo.

Debe distinguirse entre:

- Habilidad propuesta.
- Habilidad en experimentación.
- Habilidad validada.
- Habilidad dominada.
- Habilidad olvidada o deteriorada.

La biblioteca de habilidades debe permitir reutilizar procedimientos y combinarlos para resolver problemas más complejos.

## 3.11. Comunicación y comportamiento social

La comunicación debe ser una expresión de la mente y no un sistema independiente que produzca diálogos aleatorios.

La forma de hablar debe depender de:

- Personalidad.
- Estado emocional.
- Conocimientos.
- Relación con el interlocutor.
- Confianza.
- Contexto.
- Objetivos.
- Experiencias compartidas.

Los habitantes deben poder:

- Informar.
- Preguntar.
- Compartir conocimientos.
- Enseñar habilidades.
- Advertir sobre peligros.
- Negociar.
- Persuadir.
- Cooperar.
- Mentir o esconder información, cuando su personalidad y objetivos lo justifiquen.
- Expresar desacuerdo.
- Resolver conflictos.

La comunicación debe generar consecuencias cognitivas.

Lo que un habitante escucha puede convertirse en un recuerdo, una creencia, una sospecha o una nueva hipótesis.

Debe mantenerse la procedencia de la información: escuchar algo no significa que sea verdadero.

# 4. Evolución cognitiva

El cerebro no debe limitarse a almacenar información. Debe cambiar a partir de ella.

Se deberán contemplar mecanismos para:

- Revisar creencias.
- Corregir conocimientos erróneos.
- Modificar preferencias.
- Desarrollar habilidades.
- Cambiar relaciones.
- Adaptar estrategias.
- Aprender de fracasos.
- Desarrollar nuevos objetivos.
- Consolidar experiencias importantes.

Ejemplo:

Dos habitantes observan el mismo robo.

El primero interpreta que los desconocidos son peligrosos y comienza a desconfiar de ellos.

El segundo interpreta que la escasez puede llevar a comportamientos extremos.

El tercero considera que el ladrón tenía una razón justificada.

Las diferencias deben surgir de sus experiencias, personalidad, valores, conocimientos y relaciones.

# 5. Consolidación y mantenimiento de la memoria

Inspirado en los ciclos de consolidación de memoria.

Se propone que los habitantes puedan realizar procesos periódicos de revisión y organización de recuerdos.

Estos procesos pueden:

- Agrupar acontecimientos similares.
- Generar resúmenes de experiencias.
- Extraer conocimientos.
- Identificar patrones.
- Actualizar creencias.
- Consolidar aprendizajes.
- Reducir redundancias.

La compresión de memoria no debe implicar la eliminación indiscriminada de información.

Deben conservarse especialmente:

- Descubrimientos importantes.
- Acontecimientos traumáticos.
- Experiencias excepcionales.
- Relaciones significativas.
- Conocimientos adquiridos.
- Errores relevantes.
- Evidencias necesarias para revisar conclusiones.

La información original importante debe poder recuperarse.

# 6. Actividad cognitiva y niveles de simulación

Se propone implementar un sistema de LOD cognitivo.

No todos los habitantes necesitan el mismo nivel de procesamiento en todo momento.

### Nivel 1: habitantes en foco

Individuos cercanos o relevantes para la actividad principal de la simulación.

Mantienen:

- Percepción activa.
- Reacciones inmediatas.
- Objetivos y planes.
- Interacciones sociales.
- Actualización de memoria.
- Procesos deliberativos cuando corresponda.

### Nivel 2: habitantes en segundo plano

Mantienen su autonomía, pero con una frecuencia de actualización reducida.

Pueden:

- Ejecutar actividades.
- Mantener necesidades y objetivos.
- Actualizar relaciones.
- Registrar acontecimientos importantes.
- Consolidar experiencias.
- Realizar reflexiones periódicas.

### Nivel 3: habitantes distantes

Utilizan una simulación más abstracta.

Se mantienen:

- Necesidades.
- Estado general.
- Objetivos.
- Recursos.
- Relaciones relevantes.
- Acontecimientos importantes.
- Evolución temporal.

Al recuperar relevancia, deben poder reanudar un estado coherente con lo ocurrido durante su ausencia del foco.

La reducción de actividad cognitiva no debe significar que los habitantes dejan de existir o de evolucionar.

# 7. Flujo general de funcionamiento

El funcionamiento integrado del cerebro debería seguir este proceso:

1. El mundo produce acontecimientos.
2. La percepción identifica los estímulos relevantes.
3. Se actualiza el estado interno del habitante.
4. El Sistema 1 resuelve situaciones inmediatas.
5. Si corresponde, se activa el Sistema 2.
6. Se recuperan recuerdos y conocimientos pertinentes.
7. Se evalúan objetivos, alternativas y consecuencias.
8. Se selecciona o modifica un objetivo.
9. El planificador construye una secuencia de acciones.
10. El sistema de ejecución valida las acciones contra las reglas del mundo.
11. El habitante actúa.
12. Se registran los resultados.
13. Las experiencias pueden modificar conocimientos, emociones, habilidades y relaciones.
14. Los procesos de reflexión y consolidación actualizan la memoria a largo plazo.

Este ciclo debe ser continuo a escala de la simulación, pero no implica que todos los módulos deban ejecutarse en cada actualización.

# 8. Integración con el mundo existente

Esta propuesta no implica reemplazar el motor de simulación.

La arquitectura cognitiva debe integrarse con los sistemas existentes y utilizar sus capacidades.

Se debe conservar el funcionamiento actual de:

- Generación procedural del continente.
- Biomas.
- Geografía.
- Ríos y montañas.
- Cuevas y subsuelo.
- Flora y fauna.
- Recursos.
- Clima y condiciones ambientales.
- Supervivencia.
- Construcción y fabricación.
- Recetas y materiales.
- Movimiento y navegación.
- Interacciones físicas.
- Visualización.
- Paneles y herramientas de administración.
- Persistencia del mundo.

La arquitectura cognitiva debe consultar las reglas y posibilidades reales del mundo.

No debe inventar recursos, acciones, recetas, capacidades o acontecimientos inexistentes.

Tampoco debe modificar sistemas ajenos al cerebro sin justificar previamente la necesidad y el impacto del cambio.

# 9. Propuesta de implementación por etapas

La implementación debe realizarse progresivamente. Antes de modificar código, se debe analizar la arquitectura actual y determinar qué componentes ya existen.

## Etapa 0 — Auditoría y diseño técnico

- Analizar la estructura actual del proyecto.
- Identificar los sistemas existentes de personalidad, memoria, necesidades, decisiones y comportamiento.
- Identificar duplicaciones y dependencias.
- Comparar la implementación actual con esta propuesta.
- Definir qué se conserva, qué se adapta y qué falta.
- Diseñar interfaces entre módulos.
- Identificar riesgos de rendimiento y persistencia.

**Resultado:** diagnóstico técnico y plan de integración.

## Etapa 1 — Estado mental individual

- Definir el estado cognitivo persistente de cada habitante.
- Separar rasgos estables y estados variables.
- Definir identidad, personalidad, motivaciones y emociones.
- Establecer el almacenamiento y recuperación del estado.

**Resultado:** cada habitante dispone de una identidad cognitiva propia.

## Etapa 2 — Memoria integral

- Implementar memoria episódica.
- Implementar memoria semántica.
- Implementar memoria procedimental.
- Implementar memoria social.
- Implementar memoria autobiográfica.
- Incorporar relevancia, importancia, procedencia y recuperación.

**Resultado:** cada habitante conserva y recupera sus propias experiencias y conocimientos.

## Etapa 3 — Reflexión y aprendizaje

- Implementar formación de conclusiones.
- Incorporar hipótesis y creencias.
- Detectar patrones y contradicciones.
- Permitir revisar conocimientos.
- Incorporar consolidación de memoria.

**Resultado:** los habitantes pueden extraer conocimientos de sus experiencias.

## Etapa 4 — Objetivos y planificación

- Implementar generación de objetivos.
- Incorporar prioridades y motivaciones.
- Integrar Utility AI.
- Integrar GOAP.
- Incorporar modificación y abandono de planes.
- Validar las acciones contra las reglas del mundo.

**Resultado:** los habitantes pueden perseguir objetivos propios y adaptar sus planes.

## Etapa 5 — Habilidades y descubrimientos

- Implementar biblioteca de habilidades.
- Incorporar experimentación.
- Validar procedimientos.
- Permitir aprendizaje por observación.
- Permitir reutilización y combinación de habilidades.

**Resultado:** los habitantes pueden desarrollar capacidades nuevas y aprovecharlas posteriormente.

## Etapa 6 — Comunicación y evolución social

- Integrar personalidad y contexto en la comunicación.
- Incorporar intercambio de conocimientos.
- Desarrollar confianza, cooperación y conflicto.
- Registrar experiencias sociales.
- Permitir evolución de opiniones y relaciones.

**Resultado:** las interacciones sociales tienen continuidad y consecuencias.

## Etapa 7 — LOD cognitivo y optimización

- Implementar niveles de actividad cognitiva.
- Priorizar acontecimientos relevantes.
- Programar procesos de reflexión y consolidación.
- Evitar trabajo duplicado.
- Mantener coherencia entre habitantes activos y distantes.
- Medir rendimiento y consumo de recursos.

**Resultado:** el sistema puede escalar sin exigir el mismo procesamiento a todos los habitantes.

# 10. Criterios de aceptación

La arquitectura no debe considerarse terminada únicamente porque los módulos existan.

Debe comprobarse su comportamiento mediante escenarios reproducibles.

### Memoria

- Un habitante recuerda acontecimientos importantes.
- Puede recuperar recuerdos antiguos relevantes.
- Distingue entre experiencias propias e información recibida.
- Mantiene memoria después de reiniciar la simulación.

### Razonamiento y reflexión

- Puede formular hipótesis a partir de experiencias.
- Distingue hipótesis de hechos comprobados.
- Puede cambiar una conclusión cuando aparece evidencia contraria.
- Sus decisiones tienen en cuenta experiencias anteriores.

### Personalidad

- Dos habitantes interpretan de manera diferente una situación.
- Sus rasgos influyen consistentemente en sus decisiones.
- Sus estados emocionales pueden modificar temporalmente su comportamiento.
- Su personalidad puede evolucionar sin perder continuidad.

### Objetivos y planificación

- Genera objetivos a partir de necesidades, intereses y oportunidades.
- Construye planes realizables.
- Detecta cuando un plan deja de ser viable.
- Modifica sus planes cuando las circunstancias cambian.

### Aprendizaje

- Puede adquirir una habilidad mediante una experiencia válida.
- Puede reutilizar una habilidad aprendida.
- No considera válida una habilidad que no ha sido comprobada.
- Puede mejorar mediante práctica y experiencia.

### Sociedad

- Recuerda interacciones anteriores.
- Diferencia individuos y relaciones.
- Puede modificar su confianza y opinión sobre otros.
- Puede compartir y adquirir conocimientos.

### Rendimiento

- El procesamiento cognitivo no bloquea el avance del mundo.
- Los habitantes en segundo plano siguen evolucionando.
- La actividad cognitiva se distribuye según prioridades.
- El sistema no ejecuta procesos costosos innecesariamente.
- Los estados pueden guardarse y recuperarse sin inconsistencias.

# 11. Restricciones y decisiones de arquitectura

La implementación debe respetar estas condiciones:

- No reemplazar el proyecto existente por una demostración simplificada.
- No eliminar funcionalidades actuales para facilitar la implementación.
- No duplicar sistemas que ya resuelven correctamente una responsabilidad.
- No mezclar la lógica cognitiva con la representación visual.
- No permitir que las decisiones eludan las reglas físicas y económicas del mundo.
- No depender de procesos deliberativos para acciones urgentes.
- No eliminar recuerdos importantes durante la consolidación.
- No asumir que todos los habitantes tienen los mismos conocimientos.
- No compartir automáticamente recuerdos privados entre individuos.
- No confundir información observada con información inferida.
- Mantener persistencia y compatibilidad de los datos existentes.
- Incorporar pruebas para cada módulo y para las interacciones entre módulos.

# 12. Entregables esperados del análisis técnico

Antes de implementar, el equipo o agente que analice este documento deberá entregar:

1. **Auditoría del proyecto actual:** sistemas cognitivos existentes, capacidades y limitaciones.
2. **Matriz de correspondencia:** qué componentes de esta arquitectura ya están implementados y cuáles faltan.
3. **Arquitectura técnica propuesta:** módulos, responsabilidades, interfaces y flujo de información.
4. **Modelo de datos:** estructuras necesarias para identidad, memoria, conocimientos, habilidades, objetivos y relaciones.
5. **Plan de integración:** archivos y componentes que habría que modificar o crear.
6. **Plan de migración:** cómo preservar los datos y comportamientos actuales.
7. **Plan de pruebas:** escenarios que demuestren el funcionamiento de cada capacidad.
8. **Evaluación de rendimiento:** frecuencia de actualización, costos de procesamiento y escalabilidad.
9. **Implementación por etapas:** orden de desarrollo, dependencias y criterios para dar cada etapa por terminada.

No se debe comenzar una reestructuración completa antes de presentar y revisar este diagnóstico.

---

# Objetivo final

Construir habitantes que no sean simples entidades que reaccionan a estímulos, sino individuos con una historia, una identidad, conocimientos, habilidades, motivaciones, relaciones y capacidad de evolución.

Cada habitante debe poder experimentar el mundo, interpretar lo sucedido, aprender de sus experiencias, desarrollar sus propias conclusiones y actuar de acuerdo con la persona en la que se ha convertido.

**El objetivo no es programar todas las historias que vivirán los habitantes. Es construir las condiciones cognitivas para que sus historias puedan surgir de sus propias experiencias y decisiones.**

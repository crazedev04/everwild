# ANEXO A — Fundamentos científicos y técnicos de la arquitectura cognitiva

Este anexo complementa el Plan de Arquitectura Cognitiva de los Habitantes.

Su finalidad es documentar las investigaciones, arquitecturas y conceptos que fundamentan el diseño propuesto para Mundo Vivo.

Las implementaciones originales deben utilizarse como referencias de diseño, no copiarse literalmente. Cada técnica debe adaptarse a las características del mundo, las reglas de simulación y las necesidades de autonomía de sus habitantes.

## A.1. Generative Agents: Interactive Simulacra of Human Behavior

**Autores:** Joon Sung Park y colaboradores.  
**Instituciones:** Stanford University y Google Research.  
**Publicación:** UIST 2023.  
**Enlace:** https://arxiv.org/abs/2304.03442  
**Código:** https://github.com/joonspk-research/generative_agents

### Arquitectura original

El sistema utiliza tres componentes principales:

**Memory Stream**

Almacena registros de experiencias, observaciones, reflexiones y planes.

Cada registro puede incluir:
- Descripción.
- Momento de creación.
- Importancia.
- Tipo de recuerdo.
- Relaciones con otros recuerdos.

**Retrieval**

Recupera recuerdos relevantes utilizando tres criterios:

- Recency: proximidad temporal.
- Importance: importancia del acontecimiento.
- Relevance: similitud con la situación actual.

**Reflection**

Permite generar conclusiones de nivel superior mediante el análisis de recuerdos anteriores.

Las reflexiones pueden generar preguntas, recuperar evidencia relacionada y producir nuevas observaciones de carácter abstracto.

**Planning**

Construye planes generales y los descompone en acciones más pequeñas. Los planes pueden modificarse cuando aparecen nuevos acontecimientos.

### Resultados experimentales

Los autores implementaron 25 agentes en un entorno virtual inspirado en The Sims.

Los agentes generaron comportamientos individuales y sociales emergentes, incluyendo conversaciones, relaciones, organización de acontecimientos y coordinación de actividades.

Las pruebas de ablación mostraron que observación, planificación y reflexión contribuían a la credibilidad del comportamiento.

### Aplicación a Mundo Vivo

Adoptar como referencia:
- Memoria autobiográfica.
- Recuperación contextual.
- Reflexión sobre experiencias.
- Generación de conclusiones.
- Planificación basada en recuerdos.
- Evolución de opiniones y relaciones.

Ampliar respecto al trabajo original:
- Memoria episódica, semántica, procedimental y social diferenciadas.
- Procedencia y grado de certeza de la información.
- Creencias que puedan revisarse mediante evidencia.
- Persistencia a largo plazo.
- Memoria individual aislada por habitante.

## A.2. Voyager: An Open-Ended Embodied Agent with Large Language Models

**Autores:** Guanzhi Wang y colaboradores.  
**Publicación:** 2023; publicado posteriormente en Transactions on Machine Learning Research.  
**Enlace:** https://arxiv.org/abs/2305.16291  
**Sitio oficial:** https://voyager.minedojo.org/  
**Código:** https://github.com/MineDojo/Voyager

### Arquitectura original

**Automatic Curriculum**

Genera objetivos y desafíos según el estado del agente y su progreso.

**Skill Library**

Conserva habilidades ejecutables, indexadas mediante descripciones y recuperables en situaciones similares.

Las habilidades pueden combinarse para desarrollar comportamientos más complejos.

**Iterative Prompting**

Utiliza resultados de ejecución, errores y mecanismos de autoverificación para mejorar procedimientos.

### Resultados experimentales

En Minecraft, Voyager obtuvo:
- 3,3 veces más objetos únicos.
- 2,3 veces más distancia recorrida.
- Progreso hasta 15,3 veces más rápido en determinados hitos tecnológicos.

También demostró reutilización de habilidades en mundos nuevos.

### Aplicación a Mundo Vivo

Adoptar como referencia:
- Aprendizaje autónomo.
- Descubrimiento progresivo.
- Experimentación.
- Biblioteca de habilidades.
- Recuperación de procedimientos.
- Composición de habilidades.
- Verificación de resultados.

Ampliar respecto al trabajo original:
- Aprendizaje mediante observación y enseñanza.
- Habilidades con requisitos y limitaciones explícitos.
- Validación contra las reglas físicas y económicas del mundo.
- Evaluación de riesgos y consecuencias.
- Dominio progresivo de habilidades.

## A.3. Goal-Oriented Action Planning — GOAP

**Autor de referencia:** Jeff Orkin.  
**Aplicaciones destacadas:** F.E.A.R. y Condemned.  
**Material original:** https://static.hlt.bme.hu/semantics/external/pages/GOAP/alumni.media.mit.edu/_jorkin/GOAP_draft_AIWisdom2_2003.pdf  
**Recursos:** https://static.hlt.bme.hu/semantics/external/pages/GOAP/alumni.media.mit.edu/_jorkin/goap.html

### Arquitectura

GOAP permite que un agente formule una secuencia de acciones para satisfacer un objetivo.

Cada acción define:
- Precondiciones.
- Efectos.
- Costos.
- Condiciones de ejecución.

El planificador busca una secuencia válida que permita alcanzar el estado deseado.

### Aplicación a Mundo Vivo

Adoptar como referencia:
- Generación de planes.
- Evaluación de alternativas.
- Comprobación de requisitos.
- Costos y riesgos.
- Replanificación.
- Adaptación a cambios ambientales.

El sistema debe separar la selección de objetivos de la ejecución de las acciones.

## A.4. Behavior Trees

**Autores de referencia:** Michele Colledanchise y Petter Ögren.  
**Publicación de referencia:** 2017.  
**Enlace:** https://arxiv.org/abs/1709.00084

### Arquitectura

Los Behavior Trees organizan las tareas de un agente mediante estructuras jerárquicas y modulares.

Permiten:
- Secuencias de tareas.
- Selección entre alternativas.
- Condiciones.
- Reacciones.
- Reutilización de comportamientos.
- Control de ejecución.

### Aplicación a Mundo Vivo

Utilizarlos como referencia para:
- Ejecución de planes.
- Comportamientos físicos.
- Reacciones inmediatas.
- Interrupción y reanudación de tareas.
- Organización modular de acciones.

No deben utilizarse como sustituto de la planificación deliberativa ni de la memoria.

## A.5. Sistema 1 y Sistema 2

**Autor de referencia:** Daniel Kahneman.  
**Obra:** Thinking, Fast and Slow.  
**Enlace:** https://us.macmillan.com/books/9780374533557/thinkingfastandslow/

### Concepto

Sistema 1:
- Rápido.
- Automático.
- Intuitivo.
- Reactivo.

Sistema 2:
- Deliberativo.
- Analítico.
- Reflexivo.
- Requiere mayor esfuerzo.

### Aplicación a Mundo Vivo

Utilizar esta distinción como principio de diseño para separar:
- Procesamiento reactivo y necesidades inmediatas.
- Razonamiento complejo y planificación.
- Respuestas automáticas y decisiones deliberadas.

No debe interpretarse como una reproducción literal del cerebro humano.

## A.6. LOD cognitivo

**Tipo:** estrategia de arquitectura y optimización para simulaciones.

No se atribuye a un único estudio fundacional.

Consiste en adaptar la profundidad y frecuencia de procesamiento de cada habitante según su relevancia para la simulación.

Niveles propuestos:
- Foco: actividad cognitiva detallada.
- Segundo plano: actividad reducida, conservando autonomía.
- Distante: evolución abstracta mediante reglas y procesos estadísticos.

La reducción de procesamiento no debe eliminar la continuidad de identidad, memoria, objetivos ni acontecimientos importantes.

## A.7. Consolidación de memoria

**Tipo:** principio inspirado en procesos de consolidación de memoria y sistemas de memoria artificial.

Aplicación:
- Agrupar experiencias redundantes.
- Extraer patrones.
- Generar resúmenes.
- Consolidar conocimientos.
- Mantener recuerdos importantes.
- Preservar evidencias que permitan revisar conclusiones.

La consolidación no debe equivaler a eliminar indiscriminadamente los recuerdos originales.

## A.8. Matriz de trazabilidad

| Capacidad de Mundo Vivo | Fundamento |
|---|---|
| Memoria autobiográfica | Generative Agents |
| Recuperación de recuerdos | Generative Agents |
| Reflexión y conclusiones | Generative Agents |
| Planificación de actividades | Generative Agents + GOAP |
| Aprendizaje de habilidades | Voyager |
| Exploración autónoma | Voyager |
| Composición de habilidades | Voyager |
| Ejecución reactiva | Behavior Trees |
| Planificación de acciones | GOAP |
| Pensamiento rápido y deliberativo | Sistema 1 y Sistema 2 |
| Actividad cognitiva escalable | LOD cognitivo |
| Consolidación de recuerdos | Diseño propio inspirado en memoria cognitiva |

## A.9. Criterio de utilización de las investigaciones

El equipo debe estudiar las publicaciones originales y, cuando estén disponibles, sus implementaciones y materiales suplementarios.

Para cada componente debe documentar:

1. Qué problema resolvía la investigación.
2. Cómo estaba construido el sistema original.
3. Qué resultados fueron demostrados experimentalmente.
4. Qué limitaciones tenía.
5. Qué partes pueden reutilizarse.
6. Qué partes requieren adaptación.
7. Qué componentes adicionales necesita Mundo Vivo.

No deben presentarse hipótesis de diseño como resultados científicos demostrados.

La arquitectura final deberá integrar los aportes en un único sistema cognitivo coherente, evitando módulos aislados o duplicados.

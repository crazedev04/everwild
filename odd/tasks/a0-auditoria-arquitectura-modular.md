# odd/tasks/a0-auditoria-arquitectura-modular.md

Objective: Read-only deep technical audit of Mundo Vivo current state + design of target modular architecture. Produce docs/AUDITORIA_ARQUITECTURA_MODULAR_A0.md. No code changes, no commits, no simulation runs, no CCA modifications.

Branch: a0-auditoria-arquitectura-modular
Delivery strategy: ask-on-risk (default). No commits unless explicitly requested.
Test runner: PYTHONPATH=src:. python3 -m pytest -q tests (~140 s; background)

## Specs

S1: Resumen ejecutivo del estado real verificado del repositorio (hechos vs inferencias).
S2: Auditoría de modularización: por módulo (responsabilidad declarada vs real, acoplamiento, cohesión, duplicación, testeabilidad aislada).
S3: Mapa de dependencias (capas, importaciones cruzadas, dependencias circulares, estado global compartido).
S4: Análisis obligatorio de Simulacion y mixins (responsabilidades por mixin, estado compartido, orden de inicialización, riesgos).
S5: Auditoría de estructuras de datos (arrays NumPy, diccionarios, grillas espaciales, caché, persistencia; criterios de selección).
S6: Auditoría por subsistema (generación, geografía/navegación, ecosistema, habitantes/CCA, persistencia, API/UI).
S7: Inventario de código duplicado y obsoleto (clasificado: confirmado / posiblemente / necesario / duplicación).
S8: Problemas y riesgos clasificados por prioridad (hecho verificado / medido / inferencia / problema potencial).
S9: Arquitectura objetivo propuesta (capas, directorios, interfaces, dependencias permitidas/prohibidas, estructuras de datos, propiedad del estado, contratos, persistencia, pruebas, limpieza, compatibilidad).
S10: Estándares obligatorios de implementación para etapas futuras.
S11: Estrategia de limpieza progresiva.
S12: Línea base y plan de rendimiento.
S13: Roadmap corregido (etapas A–F revisadas contra el código real).
S14: Criterios de aceptación por etapa.
S15: Decisiones que requieren aprobación del usuario.
S16: Diagrama Mermaid de capas y dependencias.
S17: Confirmación explícita de solo lectura (ningún archivo modificado salvo el nuevo documento; sin CCA; sin commits).

## Tasks

T1: Exploración dirigida de motor/ (módulos clave no leídos aún) — S2,S4,S5,S6 — inline — pending
T2: Exploración de agentes/, api/, persistencia/, catalogos/, registro/, reglas/ — S2,S3,S4,S6 — inline — pending
T3: Exploración de ui/, datos_base/, tests clave — S2,S6,S7 — inline — pending
T4: Construir mapa de dependencias y clasificar problemas — S3,S7,S8 — inline — pending
T5: Redactar docs/AUDITORIA_ARQUITECTURA_MODULAR_A0.md (S1–S17) — S1–S17 — inline — pending
T6: Verificación final del documento (solo lectura, rutas, referencias) — S17 — inline — pending

## Log

L1: /caveman — A0: Auditoría arquitectónica integral y diseño de modularización objetivo de Mundo Vivo. SOLO LECTURA E INVESTIGACIÓN. No implementar cambios. Repositorio ~/Mimundo/mundo-vivo.

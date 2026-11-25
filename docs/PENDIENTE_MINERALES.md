# Pendiente: minerales (nota histórica)

**Este documento quedó unificado dentro de `docs/PLAN_MEJORAS_MOTOR.md`.** Lo que había acá es ahora
la fase 2 (minerales, menas y metalurgia) y la fase 7 (electricidad) de ese plan, con el diseño
corregido y ampliado:

- se encontró un bloqueante que este diseño no veía: **el horno y la fragua no se pueden construir**,
  así que el techo real de calor del mundo es 600 °C y la fundición era inalcanzable (fase 0);
- la lista de menas pasó de 9 a 19, con caliza y caolín agregados porque sin ellos no hay cemento ni
  fragua que cueste más que una choza;
- la recolección con herramienta resultó ser código y no JSON, como se suponía acá;
- se sumó el vocabulario de propiedades que faltaba (`funde`, `golpea`, `clava`, `mezcla`, `muele`,
  `afila`, `imanta`, `aisla`) como fase propia;
- se sumó una fase nueva: **minerales desconocidos generados por el mundo**, con propiedades
  sorteadas dentro de rangos declarados en datos, para que las invenciones no las anticipe ni el
  autor.

Se conserva el archivo sólo para no perder el rastro del diseño acordado con Nicolás el 2026-11-23.
Para trabajar, mirar el plan unificado.

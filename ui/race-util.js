// Utilidades puras de la UI para descartar respuestas atrasadas al cambiar de
// mundo o dimensión (Etapa 0: estabilización funcional). Sin DOM ni dependencias.
// La regla es siempre la misma: una carga async captura un token (o un contexto
// mundo+dimensión) al pedir, y solo se aplica si sigue vigente al resolverse.
(function (root) {
  "use strict";

  // Secuencia monótona: cada carga nueva obtiene un token mayor que el anterior.
  function creador() {
    let n = 0;
    return function siguiente() {
      n += 1;
      return n;
    };
  }

  // ¿La respuesta con este token sigue siendo la más reciente?
  function vigente(token, actual) {
    return token === actual;
  }

  // ¿El contexto pedido (mundo/dimensión) sigue siendo el actual?
  // Conservador: ante datos faltantes de cualquiera de los dos lados, no aplica.
  function mismoContexto(ctx, actual) {
    if (!ctx || !actual) return false;
    const dimA = ctx.dimension == null ? 0 : ctx.dimension;
    const dimB = actual.dimension == null ? 0 : actual.dimension;
    return ctx.nombre === actual.nombre && dimA === dimB;
  }

  var api = { creador: creador, vigente: vigente, mismoContexto: mismoContexto };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.RaceUtil = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
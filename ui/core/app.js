// Núcleo de integración de la UI (Etapa 2). Contrato explícito entre módulos que
// reemplaza las variables globales cruzadas (window.MV / window.MVBase / MV_abrirMapa).
// Cada módulo se registra con un nombre y el resto lo obtiene por `App.parte(nombre)`,
// invirtiendo la dependencia: ya nadie se referencia directamente (no hay ciclo).
(function (root) {
  "use strict";
  var partes = {};
  var App = {
    registrar: function (nombre, api) { partes[nombre] = api; return api; },
    parte: function (nombre) { return partes[nombre]; },
    _partes: partes,   // inspección (pruebas / depuración)
  };
  if (typeof module !== "undefined" && module.exports) module.exports = App;
  root.App = App;
})(typeof globalThis !== "undefined" ? globalThis : this);
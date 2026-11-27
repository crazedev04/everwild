// Utilidades puras del renderizado bajo demanda (Etapa 1). Sin DOM ni dependencias.
// Dos piezas:
//  - necesitaAnimacion(...): decide si hace falta encadenar frames (animación continua).
//  - crearPlanificador(...): un único rAF que se agenda solo cuando se pide, evita
//    solicitudes redundantes y suspende cuando no hay cambios ni animación.
(function (root) {
  "use strict";

  // ¿Hay algo que se anime frame a frame? Fuego, fogatas, antorchas, efectos
  // (rayo/derrumbe/diálogo), movimiento suavizado sin asentar, o cámara siguiendo.
  function necesitaAnimacion(estado, habs, efectos, seguirActivo) {
    if (!estado) return false;
    if ((estado.fuego && estado.fuego.length) || (estado.fogatas && estado.fogatas.length)) return true;
    if (efectos && efectos.length) return true;
    if (seguirActivo) return true;
    for (var k in habs) {
      var o = habs[k];
      if (!o || !o.d) continue;
      if (o.d.vivo && o.d.antorcha) return true;            // llama de la antorcha titila
      if (Math.abs(o.x - o.d.x) > 1e-2 || Math.abs(o.y - o.d.y) > 1e-2) return true; // aún moviéndose
    }
    return false;
  }

  // Planificador de un solo hilo de rAF.
  //  requestFrame: fn(cb) -> id   (en navegador, requestAnimationFrame)
  //  draw: fn()                   (dibuja un cuadro)
  //  necesitaMas: fn() -> bool    (¿encadenar otro frame?)
  function crearPlanificador(requestFrame, draw, necesitaMas) {
    var raf = 0;
    var visible = true;
    function paso() {
      raf = 0;
      if (!visible) return;
      draw();
      if (necesitaMas()) pedir();
    }
    function pedir() {
      if (raf || !visible) return;   // ya hay uno agendado, o la pestaña está oculta
      raf = requestFrame(paso);
    }
    function setVisible(v) {
      visible = !!v;
      if (visible) pedir();          // al reactivar, retoma el dibujo
    }
    // Cancela un frame agendado y suspende (usado por destroy del renderer).
    function cancelar() {
      raf = 0;
      visible = false;
    }
    return {
      pedir: pedir,
      setVisible: setVisible,
      cancelar: cancelar,
      _paso: paso,                   // expuesto para pruebas deterministas
      get pending() { return !!raf; },
    };
  }

  var api = { necesitaAnimacion: necesitaAnimacion, crearPlanificador: crearPlanificador };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.RaceRender = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
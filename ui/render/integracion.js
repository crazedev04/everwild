// Puente de integración opt-in del renderer definitivo (E1). NO modifica la app por
// defecto: sólo se activa con `?renderer=nuevo` (o localStorage `mv_renderer=nuevo`).
// Reutiliza datos ya cargados por `terreno` (capas/meta) y el estado de `vivo`; arma una
// WorldView provisional por reemplazo completo y la entrega al renderer. El renderer viejo
// sigue intacto: quitar el flag vuelve a `escena.js`.
(function (root) {
  "use strict";
  var WV = (typeof require !== "undefined") ? require("./worldview.js") : root.WorldView;
  var Ad = (typeof require !== "undefined") ? require("./adaptador.js") : root.AdaptadorRenderer;
  var Rn = (typeof require !== "undefined") ? require("./renderer.js") : root.Renderer;

  function activoFlag() {
    try {
      if (typeof location !== "undefined" && new URLSearchParams(location.search).get("renderer") === "nuevo") return true;
      return typeof localStorage !== "undefined" && localStorage.getItem("mv_renderer") === "nuevo";
    } catch (e) { return false; }
  }

  // Crea el adaptador + renderer y los registra como "renderer" en App.
  // `opts`: { App, canvas, requestFrame }. Devuelve el api del puente.
  function crearPuente(opts) {
    var App = opts.App, canvas = opts.canvas, requestFrame = opts.requestFrame;
    var adaptador = Ad.crearAdaptador();
    var renderer = Rn.crear(canvas, { requestFrame: requestFrame });
    var estadoVivo = null;

    function reconstruir() {
      var t = App.parte("terreno");
      if (!t || !t.estado || !t.estado.meta || !t.estado.capas) return;
      var est = t.estado;
      var gen = adaptador.ciclo();
      var ctx = { worldId: est.nombre, dimension: est.dimension || 0 };
      // cámara/viewport: la UI es dueña; el renderer sólo recibe su estado (§6.1)
      var v = est.vista || { x: 0, y: 0, z: 1 };
      var dpr = (typeof devicePixelRatio !== "undefined" && devicePixelRatio) || 1;
      renderer.setViewport((canvas && canvas.clientWidth || 0), (canvas && canvas.clientHeight || 0), dpr);
      renderer.setCam(v.x, v.y, v.z);
      adaptador.construir(gen, ctx, { meta: est.meta, capas: est.capas, estado: estadoVivo })
        .then(function (res) {
          var e = adaptador.entregar(res);
          if (e.aplicada) { renderer.setWorldView(e.wv); renderer.pedirRender(); }
        });
    }

    var api = {
      alAbrir: function () { estadoVivo = null; reconstruir(); },
      alEstado: function (estado) { estadoVivo = estado; reconstruir(); },
      pedirRender: function () { renderer.pedirRender(); },
      renderer: renderer,
      adaptador: adaptador,
    };
    App.registrar("renderer", api);
    return api;
  }

  var api = { crearPuente: crearPuente, activoFlag: activoFlag };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.RenderIntegracion = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
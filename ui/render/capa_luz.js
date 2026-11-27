// Capa de iluminación ambiental del renderer definitivo (E6). Aplica un velo de oscuridad
// según `WorldView.clima.luz` (0..1, 1 = pleno día). Es un overlay de pantalla completa en
// coords de mundo (respeta cámara/clipping por frame.vis); no calcula nada por entidad.
// Si no hay dato de luz, no dibuja (no inventa iluminación). No muta la vista.
(function (root) {
  "use strict";

  function crearCapaLuz(opts) {
    var op = opts || {};
    var maxAlpha = op.maxAlpha != null ? op.maxAlpha : 0.72;   // oscuridad máx. de noche
    var wv = null, luz = null, _ref = null;

    function setWorldView(w) {
      wv = w;
      var l = w && w.clima ? w.clima.luz : null;
      if (l === _ref) return;
      _ref = l;
      luz = (typeof l === "number" && isFinite(l)) ? l : null;
    }

    function draw(ctx, frame) {
      if (luz == null || !frame || !frame.vis) return;
      var a = Math.max(0, Math.min(1, 1 - luz)) * maxAlpha;
      if (a <= 0.003) return;                          // día pleno: sin velo
      var v = frame.vis;
      ctx.fillStyle = "rgba(8,10,20," + a.toFixed(3) + ")";
      ctx.fillRect(v.x0, v.y0, v.x1 - v.x0, v.y1 - v.y0);
    }

    return { setWorldView: setWorldView, draw: draw, get luz() { return luz; } };
  }

  var api = { crearCapaLuz: crearCapaLuz };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.CapaLuz = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
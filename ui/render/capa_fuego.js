// Capa de fuego activo del renderer definitivo (E6). Dibuja las celdas en combustión desde
// `WorldView.fuego` (lista real [[x,y,intensidad],...], ver motor/fuego.celdas_activas).
// Es un efecto TRANSITORIO (no persistente): el terreno quemado/ceniza va en capa_ambiente.
// No inventa focos ni intensidades; culling por frame.vis; caché por identidad del arreglo.
(function (root) {
  "use strict";

  function crearCapaFuego(opts) {
    var op = opts || {};
    var wv = null, celdas = null, _ref = null;

    function setWorldView(w) {
      wv = w;
      var f = w && w.fuego;
      if (f === _ref) return;
      _ref = f;
      celdas = Array.isArray(f) ? f : null;
    }

    function color(intensidad) {
      // int alto => amarillo; bajo => rojo (mapeo visual, no dato nuevo)
      var t = Math.max(0, Math.min(1, (intensidad || 0) / 255));
      return "rgb(255," + Math.round(90 + 120 * t) + ",42)";
    }

    function draw(ctx, frame) {
      if (!celdas || !frame || !frame.vis) return;
      var v = frame.vis, lod = frame.lod || 1;
      var r = Math.max(0.3, 5 / lod);
      for (var i = 0; i < celdas.length; i++) {
        var c = celdas[i];
        if (c[0] < v.x0 - 1 || c[0] > v.x1 + 1 || c[1] < v.y0 - 1 || c[1] > v.y1 + 1) continue;
        ctx.fillStyle = color(c[2]);
        ctx.fillRect(c[0] - r, c[1] - r, 2 * r, 2 * r);
      }
    }

    return { setWorldView: setWorldView, draw: draw, get celdas() { return celdas; } };
  }

  var api = { crearCapaFuego: crearCapaFuego };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.CapaFuego = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
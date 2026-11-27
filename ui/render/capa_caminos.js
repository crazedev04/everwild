// Capa de caminos del renderer definitivo (E5). Dibuja las celdas abiertas como sendero
// a partir de `WorldView.senderos` (lista real [[x,y],...], ver motor/senderos.publico_senderos).
// NO implementa desgaste: sólo representa las celdas que el dato publica; no inventa caminos.
// Cachea la lista por identidad del arreglo; `draw` pinta sólo lo visible (culling). No muta la vista.
(function (root) {
  "use strict";

  function crearCapaCaminos(opts) {
    var op = opts || {};
    var color = op.color || "#8a6d3b";   // tierra apisonada (marcador provisional, sin sprites)
    var wv = null, celdas = null, _ref = null;

    function setWorldView(w) {
      wv = w;
      var s = w && w.senderos;
      if (s === _ref) return;            // misma referencia => misma lista (contrato §4.4)
      _ref = s;
      celdas = Array.isArray(s) ? s : null;
    }

    function draw(ctx, frame) {
      if (!celdas || !frame || !frame.vis) return;
      var v = frame.vis, lod = frame.lod || 1;
      var r = Math.max(0.3, 4 / lod);    // tamaño en celdas (mín. visible al alejar)
      ctx.fillStyle = color;
      for (var i = 0; i < celdas.length; i++) {
        var c = celdas[i];
        if (c[0] < v.x0 - 1 || c[0] > v.x1 + 1 || c[1] < v.y0 - 1 || c[1] > v.y1 + 1) continue; // culling
        ctx.fillRect(c[0] - r, c[1] - r, 2 * r, 2 * r);
      }
    }

    return { setWorldView: setWorldView, draw: draw, get celdas() { return celdas; } };
  }

  var api = { crearCapaCaminos: crearCapaCaminos };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.CapaCaminos = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
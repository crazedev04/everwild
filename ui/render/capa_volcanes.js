// Capa de volcanes/lava del renderer definitivo (E7). Dibuja las celdas de lava persistente
// a partir de `WorldView.terreno.rasgos` (bit RASGO_LAVA = 2, ver motor/biomas). Es un rasgo
// GEOLÓGICO ESTÁTICO (lava solidificada en el terreno): NO hay dato de volcán puntual, erupción
// ni lava dinámica publicado, así que no se representan (no se inventan). Bitmap 1 px/celda,
// caché por identidad; `draw` pinta sólo lo visible. No muta la WorldView.
(function (root) {
  "use strict";

  var RASGO_LAVA = 2;

  function crearCapaVolcanes(opts) {
    var op = opts || {};
    var crearCanvas = op.crearCanvas || function (w, h) {
      var c = document.createElement("canvas"); c.width = w; c.height = h; return c;
    };
    var lavaRgb = op.lavaRgb || [74, 59, 51];   // basalto (lava solidificada), marcador provisional
    var wv = null, meta = null, bitmap = null, _last = null;

    function construir() {
      var t = wv && wv.terreno;
      var rasgos = t && t.rasgos;
      var w = meta && meta.ancho, h = meta && meta.alto;
      if (!rasgos || !w || !h || rasgos.length !== w * h) { bitmap = null; _last = null; return; }
      if (bitmap && _last && _last.rasgos === rasgos && _last.w === w && _last.h === h) return;
      var cv = crearCanvas(w, h), octx = cv.getContext("2d");
      var img = octx.createImageData(w, h), d32 = new Uint32Array(img.data.buffer);
      var col = (255 << 24) | (lavaRgb[2] << 16) | (lavaRgb[1] << 8) | lavaRgb[0];
      for (var i = 0; i < w * h; i++) d32[i] = (rasgos[i] & RASGO_LAVA) ? col : 0; // bit 2 => lava; resto transparente
      octx.putImageData(img, 0, 0);
      bitmap = cv; _last = { rasgos: rasgos, w: w, h: h };
    }

    function setWorldView(w) { wv = w; meta = w && w.meta; construir(); }

    function draw(ctx, frame) {
      if (!bitmap || !frame || !frame.vis) return;
      var v = frame.vis, x0 = v.x0, y0 = v.y0, x1 = v.x1, y1 = v.y1;
      if (x1 <= x0 || y1 <= y0) return;
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(bitmap, x0, y0, x1 - x0, y1 - y0, x0, y0, x1 - x0, y1 - y0);
    }

    return { setWorldView: setWorldView, draw: draw, get bitmap() { return bitmap; }, get meta() { return meta; } };
  }

  var api = { crearCapaVolcanes: crearCapaVolcanes, RASGO_LAVA: RASGO_LAVA };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.CapaVolcanes = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
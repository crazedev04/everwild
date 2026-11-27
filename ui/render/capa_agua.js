// Capa de agua del renderer definitivo (E4). Bitmap 1 px/celda a partir de
// `WorldView.terreno.agua` (0 ninguna, 1 océano, 2 lago, 3 río — ver generador/pipeline)
// y `WorldView.terreno.caudal` (0..255, sólo ríos). El renderer NO conoce REST: sólo
// consume la WorldView. Datos ausentes/inválidos => no dibuja (no inventa representación).
// Caché por identidad de buffers (agua, caudal, dims) bajo el contrato de no mutación (§4.4).
(function (root) {
  "use strict";

  // Colores de presentación por código de agua real (no son datos: sólo mapeo visual).
  var AGUA_RGB = { 1: [27, 79, 138], 2: [47, 111, 176], 3: [74, 144, 217] };

  function crearCapaAgua(opts) {
    var op = opts || {};
    var crearCanvas = op.crearCanvas || function (w, h) {
      var c = document.createElement("canvas"); c.width = w; c.height = h; return c;
    };
    var wv = null, meta = null, bitmap = null, _last = null;

    function construir() {
      var t = wv && wv.terreno;
      var agua = t && t.agua, caudal = t && t.caudal;
      var w = meta && meta.ancho, h = meta && meta.alto;
      if (!agua || !w || !h || agua.length !== w * h) { bitmap = null; _last = null; return; }
      if (bitmap && _last && _last.agua === agua && _last.caudal === caudal && _last.w === w && _last.h === h) return;
      var cv = crearCanvas(w, h), octx = cv.getContext("2d");
      var img = octx.createImageData(w, h), d32 = new Uint32Array(img.data.buffer);
      for (var i = 0; i < w * h; i++) {
        var code = agua[i], rgb = AGUA_RGB[code];
        if (!rgb) { d32[i] = 0; continue; }            // 0 o código inválido: transparente (no engaña)
        var f = 1;
        if (code === 3 && caudal) f = 0.6 + 0.4 * (caudal[i] / 255); // río: más caudal, más opaco/profundo
        var r = Math.round(rgb[0] * f), g = Math.round(rgb[1] * f), b = Math.round(rgb[2] * f);
        d32[i] = (255 << 24) | (b << 16) | (g << 8) | r;              // little-endian RGBA
      }
      octx.putImageData(img, 0, 0);
      bitmap = cv; _last = { agua: agua, caudal: caudal, w: w, h: h };
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

  var api = { crearCapaAgua: crearCapaAgua };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.CapaAgua = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
// Capa de terreno del renderer definitivo (E2). Dibuja un bitmap 1 px/celda a partir de
// `WorldView.terreno.bioma` y una paleta inyectada (el renderer NO conoce REST: la paleta
// la entrega el adaptador). El bitmap se reutiliza; `draw` sólo pinta la porción visible.
// Datos ausentes/incompletos => no dibuja (no inventa representación).
(function (root) {
  "use strict";

  function crearCapaTerreno(opts) {
    var op = opts || {};
    // fábrica de superficies inyectable (en navegador: document.createElement('canvas'))
    var crearCanvas = op.crearCanvas || function (w, h) {
      var c = document.createElement("canvas"); c.width = w; c.height = h; return c;
    };
    var pal = null, wv = null, meta = null, bitmap = null;
    var _last = null;   // { bioma, pal, w, h } de la última construcción (caché por identidad)

    function construir() {
      if (!wv || !meta || !wv.terreno || !wv.terreno.bioma) { bitmap = null; _last = null; return; }
      var w = meta.ancho, h = meta.alto, bioma = wv.terreno.bioma;
      if (!w || !h || !bioma || bioma.length !== w * h) { bitmap = null; _last = null; return; }   // capa inválida: no dibuja
      // Caché por identidad: si bioma, paleta y dimensiones no cambiaron, reutiliza el bitmap.
      // Válido bajo el contrato de no mutación externa de los buffers entregados (§4.4): el
      // adaptador no modifica el buffer tras entregarlo, así que la identidad implica contenido.
      if (bitmap && _last && _last.bioma === bioma && _last.pal === pal && _last.w === w && _last.h === h) return;
      var cv = crearCanvas(w, h), octx = cv.getContext("2d");
      var img = octx.createImageData(w, h);
      var d32 = new Uint32Array(img.data.buffer);
      // paleta a 32-bit little-endian (igual convención que mapa.js)
      var p32 = new Uint32Array(256);
      for (var b = 0; b < 256; b++) {
        var rgb = (pal && pal[b]) || [255, 0, 255];   // magenta = bioma sin color (no engaña)
        p32[b] = (255 << 24) | (rgb[2] << 16) | (rgb[1] << 8) | rgb[0];
      }
      for (var i = 0; i < w * h; i++) d32[i] = p32[bioma[i]];
      octx.putImageData(img, 0, 0);
      bitmap = cv;
      _last = { bioma: bioma, pal: pal, w: w, h: h };
    }

    function setWorldView(w) { wv = w; meta = w && w.meta; construir(); }
    function setPaleta(p) { pal = p; if (wv) construir(); }

    function draw(ctx, frame) {
      if (!bitmap || !frame || !frame.vis) return;
      var v = frame.vis, x0 = v.x0, y0 = v.y0, x1 = v.x1, y1 = v.y1;
      if (x1 <= x0 || y1 <= y0) return;
      ctx.imageSmoothingEnabled = false;
      // el ctx ya viene transformado a coords de mundo (cámara); pinta sólo lo visible
      ctx.drawImage(bitmap, x0, y0, x1 - x0, y1 - y0, x0, y0, x1 - x0, y1 - y0);
    }

    return {
      setWorldView: setWorldView,
      setPaleta: setPaleta,
      draw: draw,
      get bitmap() { return bitmap; },
      get meta() { return meta; },
    };
  }

  var api = { crearCapaTerreno: crearCapaTerreno };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.CapaTerreno = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
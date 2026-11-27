// Capa de ambiente del renderer definitivo (E4): nieve acumulada y ceniza/quemado.
// Dibuja mapas dinámicos 1 px/celda (0..255) desde `WorldView.mapas_dinamicos.nieve/quemado`.
// Sólo pinta lo que el dato trae: 0 => transparente; ausente/inválido => no dibuja.
// Caché por identidad de cada buffer (no reconstruye si no cambió). No muta la WorldView.
(function (root) {
  "use strict";

  function crearCapaAmbiente(opts) {
    var op = opts || {};
    var crearCanvas = op.crearCanvas || function (w, h) {
      var c = document.createElement("canvas"); c.width = w; c.height = h; return c;
    };
    var wv = null, meta = null;
    var nieveBmp = null, quemBmp = null;
    var _nieveRef = null, _quemRef = null, _w = 0, _h = 0;

    // Construye un bitmap alfa desde un mapa 0..255 con color base (r,g,b) y alpha máx.
    function mapaBitmap(mapa, w, h, rgb, alphaMax) {
      var cv = crearCanvas(w, h), octx = cv.getContext("2d");
      var img = octx.createImageData(w, h), d32 = new Uint32Array(img.data.buffer);
      for (var i = 0; i < w * h; i++) {
        var v = mapa[i];
        if (!v) { d32[i] = 0; continue; }                 // 0 => transparente
        var a = Math.round(alphaMax * (v / 255));
        d32[i] = (a << 24) | (rgb[2] << 16) | (rgb[1] << 8) | rgb[0];
      }
      octx.putImageData(img, 0, 0);
      return cv;
    }

    function construir() {
      var md = wv && wv.mapas_dinamicos;
      var w = meta && meta.ancho, h = meta && meta.alto;
      var nieve = md && md.nieve, quem = md && md.quemado;
      var dimsOk = w && h;
      var nieveOk = dimsOk && nieve && nieve.length === w * h;
      var quemOk = dimsOk && quem && quem.length === w * h;
      if (!nieveOk && !quemOk) { nieveBmp = null; quemBmp = null; _nieveRef = null; _quemRef = null; return; }
      if (w !== _w || h !== _h) { _w = w; _h = h; _nieveRef = null; _quemRef = null; nieveBmp = null; quemBmp = null; }
      if (nieveOk && nieve !== _nieveRef) { nieveBmp = mapaBitmap(nieve, w, h, [235, 240, 248], 230); _nieveRef = nieve; }
      if (!nieveOk) { nieveBmp = null; _nieveRef = null; }
      if (quemOk && quem !== _quemRef) { quemBmp = mapaBitmap(quem, w, h, [40, 38, 36], 200); _quemRef = quem; }
      if (!quemOk) { quemBmp = null; _quemRef = null; }
    }

    function setWorldView(w) { wv = w; meta = w && w.meta; construir(); }

    function pintar(ctx, bmp, frame) {
      if (!bmp || !frame || !frame.vis) return;
      var v = frame.vis, x0 = v.x0, y0 = v.y0, x1 = v.x1, y1 = v.y1;
      if (x1 <= x0 || y1 <= y0) return;
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(bmp, x0, y0, x1 - x0, y1 - y0, x0, y0, x1 - x0, y1 - y0);
    }

    function draw(ctx, frame) { pintar(ctx, quemBmp, frame); pintar(ctx, nieveBmp, frame); }

    return { setWorldView: setWorldView, draw: draw, get nieveBitmap() { return nieveBmp; }, get quemadoBitmap() { return quemBmp; } };
  }

  var api = { crearCapaAmbiente: crearCapaAmbiente };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.CapaAmbiente = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
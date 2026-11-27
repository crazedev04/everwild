// Capa de entidades del renderer definitivo (E3). Dibuja estructuras, habitantes y fauna
// en un único sistema de profundidad (Y-sort, §5.3) a partir de `WorldView`. Sólo usa
// datos reales; no inventa posiciones ni atributos. La estética es provisional (marcadores
// simples), no un estilo definitivo. No muta la WorldView; cachea la lista por identidad.
(function (root) {
  "use strict";

  var COLORES_DEF = ["#ff7a59", "#5ac8fa", "#ffd166", "#b794f6", "#6ee7a8", "#f472b6", "#f59e0b", "#94a3b8"];
  var ORDEN = { estructura: 0, fauna: 1, habitante: 2 };   // desempate a igual Y (§5.3)

  function crearCapaEntidades(opts) {
    var op = opts || {};
    var COL = op.COLORES || COLORES_DEF;
    var wv = null, items = null, _ref = null;

    function idDe(it) {
      if (it.tipo === "habitante") return it.e.id;
      if (it.tipo === "fauna") return it.e.inst;
      return it.idx;
    }

    function construir() {
      items = [];
      if (wv) {
        var est = wv.estructuras || [], hab = wv.habitantes || [], fau = wv.fauna || [];
        for (var i = 0; i < est.length; i++) items.push({ y: est[i].y, tipo: "estructura", e: est[i], idx: i });
        for (var j = 0; j < hab.length; j++) items.push({ y: hab[j].y, tipo: "habitante", e: hab[j] });
        for (var k = 0; k < fau.length; k++) items.push({ y: fau[k].y, tipo: "fauna", e: fau[k] });
        items.sort(function (a, b) {
          if (a.y !== b.y) return a.y - b.y;                 // Y ascendente: más Y = al frente
          var oa = ORDEN[a.tipo], ob = ORDEN[b.tipo];
          if (oa !== ob) return oa - ob;                     // desempate por tipo
          return idDe(a) - idDe(b);                          // luego por id/inst estable
        });
      }
      _ref = wv;
    }

    function setWorldView(w) { wv = w; construir(); }

    function draw(ctx, frame) {
      if (!items || !frame || !frame.vis) return;
      var v = frame.vis, lod = frame.lod || 1;
      var r = Math.max(0.35, 5 / lod);   // radio en celdas (mín. visible al alejar)
      for (var n = 0; n < items.length; n++) {
        var it = items[n], e = it.e;
        if (e.x < v.x0 - 1 || e.x > v.x1 + 1 || e.y < v.y0 - 1 || e.y > v.y1 + 1) continue; // culling
        if (it.tipo === "habitante") {
          ctx.beginPath(); ctx.arc(e.x, e.y, r, 0, 6.2832);
          ctx.fillStyle = e.vivo === false ? "#555b66" : COL[(e.color || 0) % COL.length];
          ctx.fill();
          if (e.en_fuego) { ctx.beginPath(); ctx.arc(e.x, e.y, r * 1.4, 0, 6.2832); ctx.strokeStyle = "#ff5a2a"; ctx.stroke(); }
        } else if (it.tipo === "estructura") {
          ctx.fillStyle = e.ruina ? "#6b5b4a" : "#8a6d3b";
          ctx.fillRect(e.x - r, e.y - r, 2 * r, 2 * r);
        } else { // fauna
          ctx.beginPath(); ctx.arc(e.x, e.y, r * 0.6, 0, 6.2832);
          ctx.fillStyle = "#c9a227"; ctx.fill();
        }
      }
    }

    return { setWorldView: setWorldView, draw: draw, get items() { return items; } };
  }

  var api = { crearCapaEntidades: crearCapaEntidades };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.CapaEntidades = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
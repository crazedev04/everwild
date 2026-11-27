// Adaptador provisional de datos (E1). PURO: sin DOM, sin REST, sin WS.
// Transforma fuentes actuales (capas raster + secciones del estado) en una `WorldView`
// provisional y la entrega al renderer por REEMPLAZO COMPLETO (modo provisional, §4.1).
//
// Garantías:
//  - Cada ciclo de construcción tiene una generación local (`buildGen`); las respuestas
//    de ciclos anteriores se DESCARTAN (no contaminan la vista nueva).
//  - La vista se arma como unidad y sólo al completarse reemplaza a la anterior.
//  - Un fallo parcial NO se presenta como actualización exitosa: el ciclo queda fallido
//    y la vista anterior se conserva.
//  - No simula revisiones autoritativas: `localSequence` numera, no acredita orden.
//  - La cola autoritativa (WorldDelta/snapshot) y `applyDelta` quedan deshabilitadas.
(function (root) {
  "use strict";
  var WV = (typeof require !== "undefined") ? require("./worldview.js") : root.WorldView;

  function crearAdaptador(opciones) {
    var op = opciones || {};
    var secuenciador = op.secuenciador || (function () { var n = 0; return function () { n += 1; return n; }; })();
    var _genBuild = 0;       // última generación de ciclo iniciada
    var _genActual = 0;      // generación "en vuelo" que puede reemplazar la vista
    var vistaActual = null;  // WorldView vigente (null hasta el primer ciclo completo)
    var contexto = null;     // { worldId, dimension } vigente
    var _ctxGen = {};        // contexto intencional por generación (gen -> ctx)

    // Inicia un ciclo de construcción y devuelve su generación (buildGen).
    function ciclo() {
      _genBuild += 1;
      _genActual = _genBuild;
      return _genBuild;
    }

    // Construye la vista como unidad a partir de fuentes dadas (valores o promesas).
    // `fuentes` = { meta, capas, estado, efectos }. `ctx` = { worldId, dimension }.
    // Resuelve a { ok, gen, wv } o { ok:false, gen, error } ante fallo parcial.
    // No toca `vistaActual` (eso lo hace `entregar`).
    function construir(gen, ctx, fuentes) {
      var f = fuentes || {};
      _ctxGen[gen] = ctx; // el ciclo fija su contexto intencional (cambio de mundo = ciclo nuevo)
      var sec = WV.seccionesDesdeEstado(f.estado);
      var ter = WV.terrenoDesdeCapas(f.capas, f.meta);
      var wv = WV.crearWorldView(
        {
          worldId: ctx.worldId,
          dimension: ctx.dimension,
          localSequence: secuenciador(),
          t: f.estado && f.estado.t_min != null ? f.estado.t_min : null,
          meta: f.meta,
        },
        Object.assign(sec, ter),
        { efectos: f.efectos || null }
      );
      return Promise.resolve().then(function () {
        return { ok: true, gen: gen, wv: wv };
      });
    }

    // Entrega una vista construida: reemplaza la anterior SÓLO si el ciclo sigue vigente
    // y el contexto coincide. Devuelve { aplicada, motivo, wv }.
    function entregar(resultado) {
      var gen = resultado && resultado.gen;
      if (!resultado || !resultado.ok) {
        return { aplicada: false, motivo: "fallo", wv: vistaActual };
      }
      if (gen !== _genActual) {
        return { aplicada: false, motivo: "obsoleto", wv: vistaActual }; // ciclo anterior
      }
      var wv = resultado.wv;
      var ctxGen = _ctxGen[gen];
      if (ctxGen && (wv.worldId !== ctxGen.worldId || wv.dimension !== ctxGen.dimension)) {
        return { aplicada: false, motivo: "contexto", wv: vistaActual };
      }
      contexto = { worldId: wv.worldId, dimension: wv.dimension };
      vistaActual = wv; // reemplazo COMPLETO (nunca mezcla secciones de ciclos distintos)
      return { aplicada: true, motivo: "ok", wv: vistaActual };
    }

    // Marca un ciclo como fallido (p. ej. error de red en una fuente): no reemplaza la
    // vista y el ciclo no podrá entregar aunque llegue tarde.
    function descartar(gen) {
      if (gen === _genActual) _genActual = 0; // invalida la entrega de ese ciclo
      return { descartado: true, wv: vistaActual };
    }

    return {
      ciclo: ciclo,
      construir: construir,
      entregar: entregar,
      descartar: descartar,
      get vista() { return vistaActual; },
      get contexto() { return contexto; },
      get genActual() { return _genActual; },
    };
  }

  var api = { crearAdaptador: crearAdaptador };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.AdaptadorRenderer = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
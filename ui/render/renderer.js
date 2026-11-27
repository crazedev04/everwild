// Núcleo del renderer Canvas 2D definitivo (E1). Desacoplado de DOM, REST y WS:
// recibe el `canvas` por parámetro y dependencias puras inyectadas. Implementa la API
// pública de RENDERER_ARCHITECTURE §6.1 y el ciclo on-demand de §7/§8.3.
//
// En E1 NO se completa la representación visual: `draw` sólo limpia el lienzo. El
// terreno, sprites y capas llegan en E2+. `applyDelta` queda RESERVADA (futura, sólo
// con contrato autoritativo §4.8): no se implementa ni se invoca en modo provisional.
(function (root) {
  "use strict";
  var RaceRender = (typeof require !== "undefined") ? require("../render-util.js") : root.RaceRender;

  function crear(canvas, opciones) {
    var op = opciones || {};
    var ctx = canvas && canvas.getContext ? canvas.getContext("2d") : null;
    var requestFrame = op.requestFrame || (typeof requestAnimationFrame === "function"
      ? requestAnimationFrame
      : function (cb) { return setTimeout(function () { cb(0); }, 0); });

    var wv = null;
    var cam = { x: 0, y: 0, z: 1 };
    var viewport = { w: 0, h: 0, dpr: 1 };
    var capas = { vegetacion: true, estructuras: true, entidades: true, sombras: true, efectos: true, overlay: true };
    var seleccion = null;
    var activo = true;
    var destroyed = false;
    var dirty = true;
    var presupuesto = op.presupuesto || 4;   // BATCH_POR_PASO (experimental, §8.3)
    var cola = [];                            // cola de procesamiento diferible (§8.3)
    var interpol = {};                        // estado visual transitorio (se descarta al cambiar de mundo)

    // --- ciclo on-demand (§7): un único planificador, sin rAF permanente ---
    var plan = RaceRender.crearPlanificador(requestFrame, function () { frame(); }, function () { return necesitaMas(); });

    function contextoCambia(w) {
      return wv && (w.worldId !== wv.worldId || w.dimension !== wv.dimension);
    }

    function frame() {
      if (destroyed) return;
      dirty = false;
      // procesamiento diferible con presupuesto: el resto queda encolado (§8.3)
      var n = 0;
      while (cola.length && n < presupuesto) { var t = cola.shift(); try { t(); } catch (e) { /* tarea diferible fallida: no rompe el frame */ } n += 1; }
      dibujar();
    }

    function necesitaMas() {
      if (destroyed) return false;
      if (cola.length > 0) return true;            // trabajo visual pendiente: encadena frame
      if (!wv) return false;
      return RaceRender.necesitaAnimacion(
        { fuego: wv.fuego, fogatas: wv.fogatas },
        comoHabs(wv.habitantes), wv.efectos || [], false);
    }

    // habitantes WorldView (array) -> forma que espera necesitaAnimacion (mapa id->{x,y,d})
    function comoHabs(habitantes) {
      var m = {};
      if (habitantes) for (var i = 0; i < habitantes.length; i++) { var h = habitantes[i]; m[h.id] = { x: h.x, y: h.y, d: h }; }
      return m;
    }

    function dibujar() {
      if (!ctx) return;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = "#0a0d12";
      ctx.fillRect(0, 0, viewport.w || (canvas ? canvas.width : 0), viewport.h || (canvas ? canvas.height : 0));
      // E1: sin capas visuales todavía (terreno/sprites en E2+). El loop y la invalidación
      // quedan verificados; la representación visual definitiva no es alcance de E1.
    }

    // --- API pública (§6.1) ---
    function setWorldView(w) {
      if (destroyed || !w) return;
      if (contextoCambia(w)) { interpol = {}; }   // no se interpola entre mundos/dimensiones (§4.6)
      wv = w; dirty = true; plan.pedir();
    }

    function applyDelta() {
      // RESERVADA: sólo con contrato autoritativo (§4.2/§4.8). No se usa en provisional.
      throw new Error("applyDelta no disponible en modo provisional (requiere contrato authoritativeRev)");
    }

    function setCam(x, y, z) {
      if (destroyed) return;
      cam.x = x; cam.y = y; cam.z = z; dirty = true; plan.pedir();
    }

    function setViewport(w, h, dpr) {
      if (destroyed) return;
      viewport.w = w; viewport.h = h; viewport.dpr = dpr || 1; dirty = true; plan.pedir();
    }

    function setCapas(c) {
      if (destroyed || !c) return;
      for (var k in c) if (k in capas) capas[k] = !!c[k];
      dirty = true; plan.pedir();
    }

    function setSeleccion(id) {
      if (destroyed) return;
      seleccion = id; dirty = true; plan.pedir();
    }

    function pedirRender() { if (!destroyed) plan.pedir(); }

    function setActivo(b) { if (destroyed) return; activo = !!b; plan.setVisible(activo); }

    // Consulta de SÓLO LECTURA sobre la cámara y representación vigentes (§6.1).
    // NO solicita frame. Devuelve { x, y, id } (entidad más cercana) o null.
    function hitTest(px, py) {
      if (destroyed || !wv) return null;
      var wx = cam.x + (px - viewport.w / 2) / cam.z;
      var wy = cam.y + (py - viewport.h / 2) / cam.z;
      var mejor = null, md = Math.max(1.5, 12 / cam.z);
      var habs = wv.habitantes || [];
      for (var i = 0; i < habs.length; i++) {
        var h = habs[i];
        if (h.vivo === false) continue;
        var d = Math.hypot(h.x - wx, h.y - wy);
        if (d < md) { md = d; mejor = h.id; }
      }
      return { x: wx, y: wy, id: mejor };
    }

    // Encola trabajo visual diferible (§8.3) y garantiza que el loop lo retome.
    function encolar(tarea) {
      if (destroyed || typeof tarea !== "function") return;
      cola.push(tarea); plan.pedir();
    }

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      plan.cancelar();          // cancela el rAF pendiente y suspende
      cola = [];
      interpol = {};
      wv = null;
      ctx = null;
    }

    return {
      setWorldView: setWorldView,
      applyDelta: applyDelta,
      setCam: setCam,
      setViewport: setViewport,
      setCapas: setCapas,
      setSeleccion: setSeleccion,
      pedirRender: pedirRender,
      setActivo: setActivo,
      hitTest: hitTest,
      destroy: destroy,
      encolar: encolar,            // interno para pruebas de la cola de procesamiento
      // acceso de sólo lectura / pruebas deterministas:
      _frame: frame,
      _plan: plan,
      get worldView() { return wv; },
      get cam() { return cam; },
      get viewport() { return viewport; },
      get capas() { return capas; },
      get seleccion() { return seleccion; },
      get activo() { return activo; },
      get destroyed() { return destroyed; },
      get cola() { return cola.length; },
      get dirty() { return dirty; },
    };
  }

  var api = { crear: crear };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.Renderer = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
// Puente de integración opt-in del renderer definitivo (E1). NO modifica la app por
// defecto: sólo se activa con `?renderer=nuevo` (o localStorage `mv_renderer=nuevo`).
// Reutiliza datos ya cargados por `terreno` (capas/meta) y el estado de `vivo`; arma una
// WorldView provisional por reemplazo completo y la entrega al renderer.
//
// El renderer experimental dibuja en su PROPIO canvas superpuesto (transparente,
// `pointer-events:none`), NO sobre #lienzo: así el renderer anterior sigue visible e
// intacto y no hay doble escritura sobre el mismo canvas. Quitar el flag (o destroy)
// vuelve al renderer anterior.
(function (root) {
  "use strict";
  var Ad = (typeof require !== "undefined") ? require("./adaptador.js") : root.AdaptadorRenderer;
  var Rn = (typeof require !== "undefined") ? require("./renderer.js") : root.Renderer;
  var CT = (typeof require !== "undefined") ? require("./capa_terreno.js") : root.CapaTerreno;
  var CA = (typeof require !== "undefined") ? require("./capa_agua.js") : root.CapaAgua;
  var CC = (typeof require !== "undefined") ? require("./capa_caminos.js") : root.CapaCaminos;
  var CB = (typeof require !== "undefined") ? require("./capa_ambiente.js") : root.CapaAmbiente;
  var CE = (typeof require !== "undefined") ? require("./capa_entidades.js") : root.CapaEntidades;
  var COLORES = ["#ff7a59", "#5ac8fa", "#ffd166", "#b794f6", "#6ee7a8", "#f472b6", "#f59e0b", "#94a3b8"];
  var puenteActual = null;   // evita canvases duplicados si se inicializa varias veces

  function hexRgb(h) { return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)]; }

  function activoFlag() {
    try {
      if (typeof location !== "undefined" && new URLSearchParams(location.search).get("renderer") === "nuevo") return true;
      return typeof localStorage !== "undefined" && localStorage.getItem("mv_renderer") === "nuevo";
    } catch (e) { return false; }
  }

  // Hook seguro: llama api[evento](arg) del puente registrado; no-op si no existe.
  // Permite que mapa.js/vivo.js invoquen el puente sin depender de él (carga diferida).
  function despachar(App, evento, arg) {
    var p = App && App.parte && App.parte("renderer");
    if (p && typeof p[evento] === "function") p[evento](arg);
  }

  // Crea el adaptador + renderer (canvas propio) y los registra como "renderer" en App.
  // `opts`: { App, parent, requestFrame }. Devuelve el api del puente (con destroy()).
  function crearPuente(opts) {
    if (puenteActual && puenteActual.destroy) puenteActual.destroy(); // no duplicar canvas
    var App = opts.App;
    var parent = opts.parent || (typeof document !== "undefined" && document.body);
    var dprOf = function () { return (typeof devicePixelRatio !== "undefined" && devicePixelRatio) || 1; };

    // canvas experimental superpuesto: transparente, no captura puntero, mismo tamaño que el viewport
    var exp = (typeof document !== "undefined" && document.createElement)
      ? document.createElement("canvas") : { width: 0, height: 0, style: {}, getContext: function () { return null; } };
    exp.id = "lienzo-exp";
    exp.style.position = "absolute";
    exp.style.inset = "0";
    exp.style.width = "100%";
    exp.style.height = "100%";
    exp.style.pointerEvents = "none";      // no interfiere con zoom/arrastre/selección del canvas anterior
    exp.style.background = "transparent";
    if (parent && parent.appendChild) parent.appendChild(exp);

    var adaptador = Ad.crearAdaptador();
    var capaTerreno = CT.crearCapaTerreno({});                       // bitmap 1 px/celda (E2)
    var capaAgua = CA.crearCapaAgua({});                             // océano/lago/río + caudal (E4)
    var capaCaminos = CC.crearCapaCaminos({});                       // celdas de sendero (E5)
    var capaAmbiente = CB.crearCapaAmbiente({});                     // nieve + quemado dinámicos (E4)
    var capaEntidades = CE.crearCapaEntidades({ COLORES: COLORES }); // estructuras/habitantes/fauna (E3)
    var renderer = Rn.crear(exp, { requestFrame: opts.requestFrame, transparent: true, capas: [capaTerreno, capaAgua, capaCaminos, capaAmbiente, capaEntidades] });
    var estadoVivo = null;
    var dinamico = { nieve: null, quemado: null };   // mapas dinámicos (1 vez por mundo)
    var _dinKey = null;

    // Descarga + infla un mapa dinámico (deflate, 1 byte/celda) una vez por mundo/dimensión.
    // Opt-in: no toca el loop por defecto. Si no hay fetch/DecompressionStream, queda null (no engaña).
    function cargarDinamico(nombre, dim) {
      var key = nombre + "#" + (dim || 0);
      if (key === _dinKey) return;
      _dinKey = key; dinamico = { nieve: null, quemado: null };
      if (typeof fetch !== "function" || typeof DecompressionStream === "undefined") return;
      function bajar(capa) {
        return fetch("/api/mundos/" + encodeURIComponent(nombre) + "/dinamico/" + capa)
          .then(function (r) { return r.arrayBuffer(); })
          .then(function (buf) {
            var ds = new DecompressionStream("deflate");
            var st = new Blob([buf]).stream().pipeThrough(ds);
            return new Response(st).arrayBuffer();
          })
          .then(function (ab) { dinamico[capa] = new Uint8Array(ab); reconstruir(); })
          .catch(function () { /* sin mapa dinámico: la capa no dibuja eso */ });
      }
      bajar("nieve"); bajar("quemado");
    }

    // Paleta de biomas: el adaptador (no el renderer) conoce REST y la inyecta.
    function cargarPaleta() {
      if (typeof fetch !== "function") return;
      fetch("/api/biomas").then(function (r) { return r.json(); }).then(function (lista) {
        var pal = {};
        for (var i = 0; i < lista.length; i++) {
          var b = lista[i], rgb = hexRgb(b.color);
          pal[b.id] = rgb;
          if (b.id_numerico != null) pal[b.id_numerico] = rgb;
        }
        renderer.setPaleta(pal);
      }).catch(function () { /* sin paleta: la capa usa magenta por bioma (no engaña) */ });
    }
    cargarPaleta();

    function reconstruir() {
      var t = App.parte("terreno");
      if (!t || !t.estado || !t.estado.meta || !t.estado.capas) return;
      var est = t.estado;
      cargarDinamico(est.nombre, est.dimension || 0);
      var gen = adaptador.ciclo();
      var ctx = { worldId: est.nombre, dimension: est.dimension || 0 };
      var v = est.vista || { x: 0, y: 0, z: 1 };
      var cw = (parent && parent.clientWidth) || 0, ch = (parent && parent.clientHeight) || 0;
      renderer.setViewport(cw, ch, dprOf());   // CSS * dpr en el backing store (§3 fix HiDPI)
      renderer.setCam(v.x, v.y, v.z);          // la UI es dueña de la cámara; el renderer sólo la recibe
      // inyecta los dinámicos (si llegaron) sin mutar el objeto de capas del terreno
      var capas = (dinamico.nieve || dinamico.quemado)
        ? Object.assign({}, est.capas, { nieve: dinamico.nieve, quemado: dinamico.quemado })
        : est.capas;
      adaptador.construir(gen, ctx, { meta: est.meta, capas: capas, estado: estadoVivo })
        .then(function (res) {
          var e = adaptador.entregar(res);
          if (e.aplicada) { renderer.setWorldView(e.wv); renderer.pedirRender(); }
        });
    }

    var onResize = function () { reconstruir(); };
    if (typeof window !== "undefined" && window.addEventListener) window.addEventListener("resize", onResize);

    var api = {
      alAbrir: function () { estadoVivo = null; reconstruir(); },
      alEstado: function (estado) { estadoVivo = estado; reconstruir(); },
      pedirRender: function () { renderer.pedirRender(); },
      renderer: renderer,
      adaptador: adaptador,
      canvas: exp,
      destroy: function () {
        if (typeof window !== "undefined" && window.removeEventListener) window.removeEventListener("resize", onResize);
        renderer.destroy();
        if (exp && exp.parentNode) exp.parentNode.removeChild(exp);
        if (puenteActual === api) puenteActual = null;
      },
    };
    App.registrar("renderer", api);
    puenteActual = api;
    return api;
  }

  var api = { crearPuente: crearPuente, activoFlag: activoFlag, despachar: despachar };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.RenderIntegracion = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
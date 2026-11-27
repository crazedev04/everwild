"use strict";
// Regresión de integración E1 (puente opt-in): hooks no-op sin puente, canvas experimental
// propio (no comparte #lienzo), sin duplicados, destroy libera, cambio de mundo y HiDPI.
// Usa un DOM mínimo simulado (sin navegador): comportamiento observable, no internos.
const test = require("node:test");
const assert = require("node:assert");
const Integracion = require("../../ui/render/integracion.js");

function makeApp() {
  const partes = {};
  return { registrar(n, a) { partes[n] = a; }, parte(n) { return partes[n]; }, _p: partes };
}

// DOM simulado: parent con append/remove, createElement devuelve canvas con ctx que registra.
function makeDom(dpr) {
  const children = [];
  const parent = {
    clientWidth: 800, clientHeight: 600,
    appendChild(c) { c.parentNode = parent; children.push(c); },
    removeChild(c) { const i = children.indexOf(c); if (i >= 0) children.splice(i, 1); c.parentNode = null; },
    _children: children,
  };
  const created = [];
  global.document = {
    body: parent,
    createElement() {
      const ctx = { setTransform() {}, clearRect() {}, fillRect() {}, fillStyle: "" };
      const c = { id: "", style: {}, width: 0, height: 0, getContext: () => ctx, parentNode: null,
        remove() { if (c.parentNode) c.parentNode.removeChild(c); } };
      created.push(c); return c;
    },
  };
  global.window = { addEventListener() {}, removeEventListener() {} };
  global.devicePixelRatio = dpr;
  global.location = { search: "?renderer=nuevo" };
  global.localStorage = { getItem() { return null; } };
  return { parent, created };
}

function limpiar() { delete global.document; delete global.window; delete global.devicePixelRatio; delete global.location; delete global.localStorage; }

test("despachar es no-op sin puente registrado", () => {
  const app = makeApp();
  assert.doesNotThrow(() => Integracion.despachar(app, "alEstado", { t_min: 1 }));
});

test("despachar reenvía al puente registrado", () => {
  const app = makeApp();
  let recibido = null;
  app.registrar("renderer", { alEstado: (e) => { recibido = e; } });
  const arg = { t_min: 9 };
  Integracion.despachar(app, "alEstado", arg);
  assert.strictEqual(recibido, arg);
});

test("crearPuente usa canvas propio (no #lienzo) y lo agrega al parent", () => {
  const dom = makeDom(1); const app = makeApp();
  const p = Integracion.crearPuente({ App: app, parent: dom.parent, requestFrame: () => 1 });
  try {
    assert.ok(app.parte("renderer") === p, "registrado como renderer");
    assert.strictEqual(dom.parent._children.length, 1, "un canvas en el parent");
    const exp = dom.parent._children[0];
    assert.strictEqual(exp.id, "lienzo-exp");
    assert.strictEqual(exp.style.pointerEvents, "none", "no captura puntero");
    assert.strictEqual(exp.style.background, "transparent", "transparente");
    assert.ok(exp !== global.document.body, "no es el body");
  } finally { p.destroy(); }
});

test("inicializar dos veces no duplica canvas (destruye el anterior)", () => {
  const dom = makeDom(1); const app = makeApp();
  const p1 = Integracion.crearPuente({ App: app, parent: dom.parent, requestFrame: () => 1 });
  const p2 = Integracion.crearPuente({ App: app, parent: dom.parent, requestFrame: () => 1 });
  try {
    assert.strictEqual(dom.parent._children.length, 1, "sigue habiendo un solo canvas");
    assert.strictEqual(p1.renderer.destroyed, true, "el puente anterior se destruyó");
    assert.ok(p2.renderer.destroyed === false);
  } finally { p2.destroy(); }
});

test("destroy libera el canvas experimental y el renderer", () => {
  const dom = makeDom(1); const app = makeApp();
  const p = Integracion.crearPuente({ App: app, parent: dom.parent, requestFrame: () => 1 });
  p.destroy();
  assert.strictEqual(dom.parent._children.length, 0, "canvas removido del DOM");
  assert.strictEqual(p.renderer.destroyed, true);
  assert.strictEqual(p.canvas.parentNode, null);
});

test("cambio de mundo: viewport HiDPI y reemplazo de WorldView por el puente", async () => {
  const dom = makeDom(2); const app = makeApp();   // dpr 2
  app.registrar("terreno", { estado: { nombre: "M", dimension: 0, meta: { ancho: 2, alto: 2 }, capas: { bioma: new Uint8Array(4) }, vista: { x: 0, y: 0, z: 1 } } });
  const p = Integracion.crearPuente({ App: app, parent: dom.parent, requestFrame: () => 1 });
  try {
    p.alEstado({ t_min: 3, habitantes: [{ id: 1, x: 1, y: 1, vivo: true }] });
    await Promise.resolve(); await Promise.resolve(); // deja correr construir (microtarea)
    const exp = dom.parent._children[0];
    assert.strictEqual(exp.width, 1600, "backing store = 800*dpr2");
    assert.ok(p.renderer.worldView, "WorldView entregada al renderer");
    assert.strictEqual(p.renderer.worldView.autoritativo, false);
  } finally { p.destroy(); limpiar(); }
});
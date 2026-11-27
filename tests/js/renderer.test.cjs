"use strict";
// Regresión del núcleo del renderer (E1): API §6.1, loop on-demand (dedup, continuación
// con trabajo pendiente, suspensión), hitTest sin render, destroy que limpia todo.
const test = require("node:test");
const assert = require("node:assert");
const { crear } = require("../../ui/render/renderer.js");

function arnul(wvExtra) {
  const ctx = { setTransform() {}, fillRect() {}, fillStyle: "" };
  const canvas = { width: 800, height: 600, getContext: () => ctx };
  let pedidos = 0, cb = null;
  const requestFrame = (fn) => { pedidos += 1; cb = fn; return pedidos; };
  const r = crear(canvas, { requestFrame });
  return { r, get pedidos() { return pedidos; }, get cb() { return cb; } };
}

const wv = (over) => Object.assign({ worldId: "M", dimension: 0, localSequence: 1, autoritativo: false, habitantes: [{ id: 1, x: 5, y: 5, vivo: true }], fuego: null, fogatas: null, efectos: null }, over || {});

test("API pública §6.1 expuesta; applyDelta reservada (lanza)", () => {
  const { r } = arnul();
  for (const m of ["setWorldView", "setCam", "setViewport", "setCapas", "setSeleccion", "pedirRender", "setActivo", "destroy", "hitTest"]) {
    assert.strictEqual(typeof r[m], "function", m);
  }
  assert.throws(() => r.applyDelta({}), /reservada|provisional/i);
});

test("setWorldView pide un frame; invalidaciones múltiples se deduplican en uno", () => {
  const h = arnul();
  h.r.setWorldView(wv());
  h.r.setCam(1, 2, 3);
  h.r.setCapas({ entidades: false });
  h.r.setSeleccion(1);
  assert.strictEqual(h.pedidos, 1); // un solo rAF agendado pese a 4 invalidaciones
});

test("loop continúa mientras quede trabajo pendiente y suspende al vaciarse", () => {
  const h = arnul();
  h.r.setWorldView(wv({ fuego: null, habitantes: [{ id: 1, x: 5, y: 5, vivo: true }] }));
  const base = h.pedidos; // 1 (por setWorldView)
  // encola más tareas que el presupuesto (4): deben quedar pendientes tras un frame
  for (let i = 0; i < 10; i++) h.r.encolar(() => {});
  h.r._plan._paso(); // ejecuta un frame: drena 4, quedan 6
  assert.ok(h.r.cola > 0, "queda trabajo encolado");
  assert.ok(h.pedidos > base, "encadenó otro frame por trabajo pendiente");
  // vacía la cola y sin animación: el siguiente frame no re-agenda
  h.r._plan._paso();
  while (h.r.cola > 0) h.r._plan._paso();
  const p = h.pedidos;
  h.r._plan._paso();
  assert.strictEqual(h.pedidos, p, "suspende sin trabajo ni animación");
});

test("animación (fuego) mantiene el loop activo", () => {
  const h = arnul();
  h.r.setWorldView(wv({ fuego: [{ x: 1, y: 1, intensidad: 10 }] }));
  h.r._plan._paso();
  const p = h.pedidos;
  h.r._plan._paso();
  assert.ok(h.pedidos > p, "con fuego encadena frames");
});

test("hitTest es consulta de sólo lectura: no solicita frame", () => {
  const h = arnul();
  h.r.setViewport(800, 600, 1);
  h.r.setCam(5, 5, 1);        // centro de pantalla -> mundo (5,5)
  h.r.setWorldView(wv());
  h.r._plan._paso();          // consume el frame de las invalidaciones
  const p = h.pedidos;
  const res = h.r.hitTest(400, 300); // centro exacto
  assert.strictEqual(h.pedidos, p, "hitTest no pide render");
  assert.ok(res && res.id === 1, "detecta el habitante más cercano");
});

test("setActivo(false) suspende; setActivo(true) reactiva", () => {
  const h = arnul();
  h.r.setActivo(false);
  h.r.setWorldView(wv());
  assert.strictEqual(h.pedidos, 0, "oculto: no agenda");
  h.r.setActivo(true);
  assert.ok(h.pedidos >= 1, "reactiva y agenda");
});

test("cambio de mundo/dimensión: reemplaza vista sin error", () => {
  const h = arnul();
  h.r.setWorldView(wv());
  h.r.setWorldView(wv({ worldId: "Otro", dimension: 1, habitantes: [{ id: 2, x: 1, y: 1, vivo: true }] }));
  assert.strictEqual(h.r.worldView.worldId, "Otro");
  assert.strictEqual(h.r.worldView.dimension, 1);
});

test("destroy cancela rAF, limpia y evita actividad posterior", () => {
  const h = arnul();
  h.r.setWorldView(wv());
  h.r.destroy();
  assert.strictEqual(h.r.destroyed, true);
  assert.strictEqual(h.r._plan.pending, false, "sin frame pendiente");
  const p = h.pedidos;
  h.r.setWorldView(wv({ worldId: "X" })); // no-op tras destroy
  h.r.pedirRender();
  assert.strictEqual(h.pedidos, p, "no agenda más frames");
  assert.strictEqual(h.r.worldView, null);
  assert.strictEqual(h.r.cola, 0);
});
test("clear HiDPI: backing store = CSS*dpr y limpieza cubre todo el área física", () => {
  const llamadas = { clear: [], fill: [] };
  const ctx = { setTransform() {}, clearRect(x, y, w, h) { llamadas.clear.push([x, y, w, h]); }, fillRect(x, y, w, h) { llamadas.fill.push([x, y, w, h]); }, fillStyle: "" };
  const canvas = { width: 0, height: 0, getContext: () => ctx };
  let cb = null;
  const r = crear(canvas, { requestFrame: (fn) => { cb = fn; return 1; }, transparent: true });
  r.setViewport(800, 600, 2);            // CSS 800x600, dpr 2
  assert.strictEqual(canvas.width, 1600); // backing store físico
  assert.strictEqual(canvas.height, 1200);
  r._plan._paso();                        // ejecuta el frame (clear)
  assert.deepStrictEqual(llamadas.clear[0], [0, 0, 1600, 1200]); // cubre todo el backing store
});

test("cambio de mundo limpia la selección (estado transitorio incompatible)", () => {
  const h = arnul();
  h.r.setWorldView(wv());
  h.r.setSeleccion(1);
  assert.strictEqual(h.r.seleccion, 1);
  h.r.setWorldView(wv({ worldId: "Otro", dimension: 1 })); // cambio de contexto
  assert.strictEqual(h.r.seleccion, null);
});

test("draw aplica cámara/viewport y pasa frame con vis a las capas", () => {
  const rec = { transforms: [], frames: [] };
  const ctx = { setTransform(...a) { rec.transforms.push(a); }, clearRect() {}, fillRect() {}, fillStyle: "", drawImage() {} };
  const canvas = { width: 0, height: 0, getContext: () => ctx };
  const layer = { setWorldView() {}, draw(c, f) { rec.frames.push(f); } };
  const r = crear(canvas, { requestFrame: () => 1, capas: [layer] });
  r.setViewport(800, 600, 1);
  r.setCam(10, 20, 2);
  r.setWorldView({ worldId: "M", dimension: 0, localSequence: 1, meta: { ancho: 100, alto: 100 }, terreno: { bioma: new Uint8Array(10000) } });
  r._plan._paso();
  assert.deepStrictEqual(rec.transforms.find((t) => t[0] === 2), [2, 0, 0, 2, -20, -40]); // s=z*dpr, tx=-x*s
  const f = rec.frames[0];
  assert.ok(f && f.vis, "capa recibió frame");
  assert.strictEqual(f.vis.x0, 10); assert.strictEqual(f.vis.y0, 20);
  assert.strictEqual(f.vis.x1, 100); assert.strictEqual(f.vis.y1, 100); // acotado a 100x100
  assert.strictEqual(f.dpr, 1);
  assert.strictEqual(f.cam.z, 2);
});

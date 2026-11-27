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
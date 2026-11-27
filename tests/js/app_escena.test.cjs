"use strict";
// Regresión de la modularización (Etapa 2): contrato App (sin ciclos) e instalación
// de la capa de render extraída. No ejecuta el dibujo completo (eso va en el smoke).
const test = require("node:test");
const assert = require("node:assert");

const App = require("../../ui/core/app.js");
require("../../ui/render/escena.js"); // instala globalThis.Escena

test("App: registrar y parte resuelven por nombre", () => {
  const api = { hola: 1 };
  App.registrar("demo", api);
  assert.strictEqual(App.parte("demo"), api);
  assert.strictEqual(App.parte("no-existe"), undefined);
});

test("App: dos módulos se obtienen sin referenciarse entre sí (sin ciclo)", () => {
  App.registrar("a", { f: () => "A" });
  App.registrar("b", { g: () => "B" });
  // cada uno llega a la otra parte solo por App, no por una global del otro
  const a = App.parte("a"), b = App.parte("b");
  assert.strictEqual(App.parte("b").g(), "B");
  assert.strictEqual(typeof a.f, "function");
  assert.strictEqual(typeof b.g, "function");
});

test("Escena.instalar define V.sobreMapa y deja el contrato listo", () => {
  const V = {};
  const base = () => ({ estado: { vista: { z: 1 }, vis: {}, capas: {} } });
  globalThis.Escena.instalar(V, base, {}, [], () => null, { parentElement: {} });
  assert.strictEqual(typeof V.sobreMapa, "function");
  assert.strictEqual(typeof V.pedirNieve, "function");
  assert.strictEqual(typeof V.pedirCeniza, "function");
});
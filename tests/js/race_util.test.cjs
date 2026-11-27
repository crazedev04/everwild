"use strict";
// Pruebas de regresión del criterio anti-carrera de la UI (Etapa 0).
// Cubren la lógica pura de tokens/contexto sin DOM, que es la que decide si una
// respuesta atrasada (capas, ficha, paneles) debe aplicarse o descartarse.
const test = require("node:test");
const assert = require("node:assert");
const { creador, vigente, mismoContexto } = require("../../ui/race-util.js");

test("creador emite tokens monótonos y distinguibles", () => {
  const next = creador();
  const a = next();
  const b = next();
  assert.ok(b > a);
  assert.notStrictEqual(a, b);
});

test("solo el token vigente se aplica (el último gana)", () => {
  const next = creador();
  const t1 = next(); // carga A
  const t2 = next(); // carga B (más nueva)
  assert.strictEqual(vigente(t2, t2), true);
  assert.strictEqual(vigente(t1, t2), false); // A llega tarde: se descarta
});

test("carga A resuelta después de B no sobrescribe (orden invertido)", () => {
  const next = creador();
  const tA = next();
  const tB = next();
  // Simula resolución fuera de orden: la vigente es la última pedida (tB).
  const actual = tB;
  const aplicaA = vigente(tA, actual);
  const aplicaB = vigente(tB, actual);
  assert.strictEqual(aplicaA, false);
  assert.strictEqual(aplicaB, true);
});

test("mismoContexto exige igual mundo y dimensión", () => {
  assert.strictEqual(mismoContexto({ nombre: "m", dimension: 0 }, { nombre: "m", dimension: 0 }), true);
  assert.strictEqual(mismoContexto({ nombre: "m", dimension: 1 }, { nombre: "m", dimension: 0 }), false);
  assert.strictEqual(mismoContexto({ nombre: "m", dimension: 0 }, { nombre: "otro", dimension: 0 }), false);
});

test("mismoContexto es conservador ante datos faltantes", () => {
  assert.strictEqual(mismoContexto(null, { nombre: "m" }), false);
  assert.strictEqual(mismoContexto({ nombre: "m" }, null), false);
  // dimensión ausente se trata como 0 en ambos lados
  assert.strictEqual(mismoContexto({ nombre: "m" }, { nombre: "m", dimension: 0 }), true);
});
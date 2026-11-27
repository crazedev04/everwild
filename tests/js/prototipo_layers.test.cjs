"use strict";
// Regresión de los helpers puros del prototipo de renderer (Etapa 3A):
// LOD por zoom, culling, orden por Y, pool de sprites y ruido determinista.
const test = require("node:test");
const assert = require("node:assert");
const L = require("../../ui/prototipo/layers.js");

test("rng determinista por semilla", () => {
  const a = L.rng(123), b = L.rng(123);
  const sa = Array.from({ length: 5 }, a);
  const sb = Array.from({ length: 5 }, b);
  assert.deepEqual(sa, sb);
  assert.notDeepEqual(sa, Array.from({ length: 5 }, L.rng(999)));
});

test("fbm determinista y en [0,1]", () => {
  const v1 = L.fbm(3.5, 7.25, 42, 4);
  const v2 = L.fbm(3.5, 7.25, 42, 4);
  assert.strictEqual(v1, v2);
  assert.ok(v1 >= 0 && v1 <= 1);
});

test("seleccionarLOD: puntos / híbrido / sprites según zoom", () => {
  assert.strictEqual(L.seleccionarLOD(0.6).modo, "puntos");
  assert.strictEqual(L.seleccionarLOD(3).modo, "hibrido");
  assert.strictEqual(L.seleccionarLOD(8).modo, "sprites");
  const near = L.seleccionarLOD(12);
  assert.strictEqual(near.sprites, true);
  assert.strictEqual(near.sombras, true);
  assert.strictEqual(near.detalle, true);   // detalle por celda sólo de cerca
  assert.strictEqual(L.seleccionarLOD(0.6).sprites, false);
});

test("esVisible respeta el margen (culling)", () => {
  const vis = { x0: 10, y0: 10, x1: 20, y1: 20 };
  assert.strictEqual(L.esVisible(15, 15, 0, vis), true);
  assert.strictEqual(L.esVisible(5, 15, 0, vis), false);
  assert.strictEqual(L.esVisible(5, 15, 6, vis), true);  // con margen entra
});

test("ordenarPorY ascendente y estable", () => {
  const a = [{ id: "a", y: 5 }, { id: "b", y: 1 }, { id: "c", y: 5 }, { id: "d", y: 3 }];
  const r = L.ordenarPorY(a);
  assert.deepEqual(r.map((o) => o.id), ["b", "d", "a", "c"]); // a antes que c (estable)
});

test("crearPool reutiliza y resetea", () => {
  let creados = 0, resets = 0;
  const pool = L.crearPool(() => ({ v: ++creados }), (o) => { resets++; o.v = 0; });
  const o1 = pool.obtener();
  pool.devolver(o1);
  const o2 = pool.obtener();
  assert.strictEqual(o1, o2);     // reutilizado, no se creó otro
  assert.strictEqual(creados, 1);
  assert.ok(resets >= 1);
});
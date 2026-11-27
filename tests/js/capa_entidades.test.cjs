"use strict";
const test = require("node:test");
const assert = require("node:assert");
const WV = require("../../ui/render/worldview.js");
const CE = require("../../ui/render/capa_entidades.js");

function ctxFalso() {
  const llamadas = [];
  const ctx = {
    fillStyle: "", strokeStyle: "", _last: null,
    beginPath() {}, arc(x, y, r) { ctx._last = { x, y, r }; },
    fill() { if (ctx._last) llamadas.push({ op: "arc", x: ctx._last.x, y: ctx._last.y, r: ctx._last.r, fill: ctx.fillStyle }); },
    stroke() {}, fillRect(x, y, w, h) { llamadas.push({ op: "rect", x, y, fill: ctx.fillStyle }); },
  };
  return { ctx, llamadas };
}

test("Y-sort ascendente: habitante(y5) < fauna(y7) < estructura(y10)", () => {
  const wv = WV.seccionesDesdeEstado({
    refugios: [[5, 10, "casa"]],
    habitantes: [{ id: 1, x: 1, y: 5, color: 0, vivo: true }],
    fauna: [[9, 2, 7]],
  });
  const capa = CE.crearCapaEntidades({ COLORES: ["#111"] });
  capa.setWorldView(wv);
  const tipos = capa.items.map((it) => it.tipo);
  assert.deepStrictEqual(tipos, ["habitante", "fauna", "estructura"]);
});

test("color de habitante sale de COLORES y muerto en gris", () => {
  const wv = WV.seccionesDesdeEstado({
    habitantes: [{ id: 1, x: 1, y: 1, color: 0, vivo: true }, { id: 2, x: 2, y: 2, color: 1, vivo: false }],
  });
  const { ctx, llamadas } = ctxFalso();
  const capa = CE.crearCapaEntidades({ COLORES: ["#aaa", "#bbb"] });
  capa.setWorldView(wv);
  capa.draw(ctx, { vis: { x0: 0, y0: 0, x1: 10, y1: 10 }, lod: 1 });
  const vivos = llamadas.filter((l) => l.fill === "#aaa");
  const muertos = llamadas.filter((l) => l.fill === "#555b66");
  assert.ok(vivos.length >= 1, "el vivo usa COLORES[0]");
  assert.ok(muertos.length >= 1, "el muerto va en gris");
});

test("culling: lo que cae fuera de vis no se dibuja", () => {
  const wv = WV.seccionesDesdeEstado({ habitantes: [{ id: 1, x: 100, y: 100, color: 0, vivo: true }] });
  const { ctx, llamadas } = ctxFalso();
  const capa = CE.crearCapaEntidades({});
  capa.setWorldView(wv);
  capa.draw(ctx, { vis: { x0: 0, y0: 0, x1: 4, y1: 4 }, lod: 1 });
  assert.strictEqual(llamadas.length, 0);
});

test("sin datos: capas ausentes no rompen y items queda vacío", () => {
  const capa = CE.crearCapaEntidades({});
  capa.setWorldView(WV.seccionesDesdeEstado({}));
  assert.deepStrictEqual(capa.items, []);
});

test("no muta la WorldView", () => {
  const estado = { habitantes: [{ id: 1, x: 1, y: 1, color: 0, vivo: true }] };
  const wv = WV.seccionesDesdeEstado(estado);
  const copia = JSON.parse(JSON.stringify(wv));
  const capa = CE.crearCapaEntidades({});
  capa.setWorldView(wv);
  capa.draw(ctxFalso().ctx, { vis: { x0: 0, y0: 0, x1: 9, y1: 9 }, lod: 2 });
  assert.deepStrictEqual(wv, copia);
});

test("cambio de mundo reconstruye la lista (items cambia de identidad)", () => {
  const capa = CE.crearCapaEntidades({});
  capa.setWorldView(WV.seccionesDesdeEstado({ habitantes: [{ id: 1, x: 1, y: 1, color: 0, vivo: true }] }));
  const a = capa.items;
  capa.setWorldView(WV.seccionesDesdeEstado({ habitantes: [{ id: 2, x: 3, y: 3, color: 0, vivo: true }] }));
  assert.notStrictEqual(capa.items, a);
  assert.strictEqual(capa.items[0].e.id, 2);
});
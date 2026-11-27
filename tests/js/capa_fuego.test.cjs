"use strict";
const test = require("node:test");
const assert = require("node:assert");
const WV = require("../../ui/render/worldview.js");
const CF = require("../../ui/render/capa_fuego.js");
const CL = require("../../ui/render/capa_luz.js");
const CE = require("../../ui/render/capa_entidades.js");

function wvFuego(fuego) {
  return WV.crearWorldView({ worldId: "w", meta: { ancho: 4, alto: 4 } }, { fuego });
}
function wvLuz(luz) {
  const sec = WV.seccionesDesdeEstado({ luz });
  return WV.crearWorldView({ worldId: "w", meta: { ancho: 4, alto: 4 } }, sec);
}

test("fuego válido: un triple => un fillRect con color según intensidad", () => {
  const capa = CF.crearCapaFuego({});
  capa.setWorldView(wvFuego([[1, 1, 255], [2, 2, 10]]));
  const ops = [];
  capa.draw({ fillStyle: "", fillRect(x, y, w, h) { ops.push({ x, y, c: this.fillStyle }); } },
    { vis: { x0: 0, y0: 0, x1: 4, y1: 4 }, lod: 1 });
  assert.strictEqual(ops.length, 2);
  assert.notStrictEqual(ops[0].c, ops[1].c, "intensidad alta vs baja colorean distinto");
});

test("fuego ausente (null) => no dibuja", () => {
  const capa = CF.crearCapaFuego({});
  capa.setWorldView(wvFuego(null));
  let n = 0;
  capa.draw({ fillStyle: "", fillRect() { n++; } }, { vis: { x0: 0, y0: 0, x1: 4, y1: 4 }, lod: 1 });
  assert.strictEqual(n, 0);
});

test("fuego culling: foco fuera de vis no se dibuja", () => {
  const capa = CF.crearCapaFuego({});
  capa.setWorldView(wvFuego([[50, 50, 200]]));
  let n = 0;
  capa.draw({ fillStyle: "", fillRect() { n++; } }, { vis: { x0: 0, y0: 0, x1: 4, y1: 4 }, lod: 1 });
  assert.strictEqual(n, 0);
});

test("fuego caché por identidad y reconstrucción por cambio de mundo", () => {
  const f = [[1, 1, 100]];
  const wv = wvFuego(f);
  const capa = CF.crearCapaFuego({});
  capa.setWorldView(wv);
  const a = capa.celdas;
  capa.setWorldView(wv);
  assert.strictEqual(capa.celdas, a);
  capa.setWorldView(wvFuego([[3, 3, 5]]));
  assert.notStrictEqual(capa.celdas, a);
});

test("luz: noche (luz baja) => velo con alfa; día pleno => sin velo", () => {
  const capaN = CL.crearCapaLuz({});
  capaN.setWorldView(wvLuz(0.2));
  let alphaN = null;
  capaN.draw({ fillStyle: "", fillRect() { alphaN = this.fillStyle; } }, { vis: { x0: 0, y0: 0, x1: 4, y1: 4 } });
  assert.ok(alphaN && alphaN.indexOf("rgba") === 0, "noche dibuja velo rgba");

  const capaD = CL.crearCapaLuz({});
  capaD.setWorldView(wvLuz(1));
  let n = 0;
  capaD.draw({ fillStyle: "", fillRect() { n++; } }, { vis: { x0: 0, y0: 0, x1: 4, y1: 4 } });
  assert.strictEqual(n, 0, "día pleno no dibuja velo");
});

test("luz ausente (sin clima) => no dibuja", () => {
  const capa = CL.crearCapaLuz({});
  capa.setWorldView(WV.crearWorldView({ worldId: "w", meta: {} }, {}));
  let n = 0;
  capa.draw({ fillStyle: "", fillRect() { n++; } }, { vis: { x0: 0, y0: 0, x1: 4, y1: 4 } });
  assert.strictEqual(n, 0);
});

test("no muta la WorldView (fuego y luz)", () => {
  const wv = wvFuego([[1, 1, 9]]);
  const copia = JSON.stringify(wv.fuego);
  const c = CF.crearCapaFuego({});
  c.setWorldView(wv);
  c.draw({ fillStyle: "", fillRect() {} }, { vis: { x0: 0, y0: 0, x1: 4, y1: 4 } });
  assert.strictEqual(JSON.stringify(wv.fuego), copia);
});

test("composición: entidades (arc) < luz (fillRect rgba) < fuego (fillRect rojo) al final", () => {
  const sec = WV.seccionesDesdeEstado({ luz: 0.2, habitantes: [{ id: 1, x: 1, y: 1, color: 0, vivo: true }], fuego: [[1, 1, 200]] });
  const wv = WV.crearWorldView({ worldId: "w", meta: { ancho: 4, alto: 4 } }, sec);
  const seq = [];
  const ctx = {
    fillStyle: "", strokeStyle: "", _last: null,
    beginPath() {}, arc() { seq.push("arc"); }, fill() {}, stroke() {},
    fillRect(x, y, w, h) { seq.push("rect:" + this.fillStyle); },
  };
  const frame = { vis: { x0: 0, y0: 0, x1: 4, y1: 4 }, lod: 1 };
  // orden definitivo: iluminación (6) antes que fuego (7)
  const capas = [CE.crearCapaEntidades({ COLORES: ["#111"] }), CL.crearCapaLuz({}), CF.crearCapaFuego({})];
  for (const c of capas) c.setWorldView(wv);
  for (const c of capas) c.draw(ctx, frame);

  const iArc = seq.indexOf("arc");
  const iFuego = seq.findIndex((s) => s.startsWith("rect:rgb("));
  const iLuz = seq.findIndex((s) => s.startsWith("rect:rgba("));
  assert.ok(iArc >= 0 && iFuego >= 0 && iLuz >= 0, "las tres dibujan");
  assert.ok(iArc < iLuz, "entidades antes que iluminación");
  assert.ok(iLuz < iFuego, "iluminación antes que fuego (el fuego queda visible)");
});
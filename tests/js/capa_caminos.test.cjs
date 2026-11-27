"use strict";
const test = require("node:test");
const assert = require("node:assert");
const WV = require("../../ui/render/worldview.js");
const CT = require("../../ui/render/capa_terreno.js");
const CA = require("../../ui/render/capa_agua.js");
const CC = require("../../ui/render/capa_caminos.js");
const CB = require("../../ui/render/capa_ambiente.js");
const CE = require("../../ui/render/capa_entidades.js");

function crearCanvasFalso() {
  return function (w, h) {
    let last = null;
    const ctx = {
      createImageData: (ww, hh) => ({ width: ww, height: hh, data: new Uint8ClampedArray(ww * hh * 4) }),
      putImageData: (img) => { last = img; },
    };
    return { width: w, height: h, getContext: () => ctx, _last: () => last };
  };
}

function wvCaminos(senderos) {
  const meta = { ancho: 4, alto: 4 };
  return WV.crearWorldView({ worldId: "w", meta }, { senderos });
}

test("caminos válidos: una celda => un fillRect", () => {
  const wv = wvCaminos([[1, 1], [2, 2]]);
  const ops = [];
  const ctx = { fillStyle: "", fillRect(x, y, w, h) { ops.push({ x, y }); } };
  const capa = CC.crearCapaCaminos({});
  capa.setWorldView(wv);
  capa.draw(ctx, { vis: { x0: 0, y0: 0, x1: 4, y1: 4 }, lod: 1 });
  assert.strictEqual(ops.length, 2);
});

test("caminos ausentes (senderos null) => no dibuja", () => {
  const capa = CC.crearCapaCaminos({});
  capa.setWorldView(wvCaminos(null));
  const ops = [];
  capa.draw({ fillStyle: "", fillRect() { ops.push(1); } }, { vis: { x0: 0, y0: 0, x1: 4, y1: 4 }, lod: 1 });
  assert.strictEqual(ops.length, 0);
});

test("culling: celda fuera de vis no se dibuja", () => {
  const capa = CC.crearCapaCaminos({});
  capa.setWorldView(wvCaminos([[100, 100]]));
  const ops = [];
  capa.draw({ fillStyle: "", fillRect() { ops.push(1); } }, { vis: { x0: 0, y0: 0, x1: 4, y1: 4 }, lod: 1 });
  assert.strictEqual(ops.length, 0);
});

test("caché por identidad: mismo arreglo => misma lista", () => {
  const s = [[1, 1]];
  const wv = wvCaminos(s);
  const capa = CC.crearCapaCaminos({});
  capa.setWorldView(wv);
  const a = capa.celdas;
  capa.setWorldView(wv);
  assert.strictEqual(capa.celdas, a);
});

test("cambio de mundo (nuevo arreglo) reconstruye", () => {
  const capa = CC.crearCapaCaminos({});
  capa.setWorldView(wvCaminos([[1, 1]]));
  const a = capa.celdas;
  capa.setWorldView(wvCaminos([[3, 3]]));
  assert.notStrictEqual(capa.celdas, a);
  assert.deepStrictEqual(capa.celdas, [[3, 3]]);
});

test("no muta la WorldView", () => {
  const wv = wvCaminos([[1, 1], [2, 2]]);
  const copia = JSON.stringify(wv.senderos);
  const capa = CC.crearCapaCaminos({});
  capa.setWorldView(wv);
  capa.draw({ fillStyle: "", fillRect() {} }, { vis: { x0: 0, y0: 0, x1: 4, y1: 4 }, lod: 2 });
  assert.strictEqual(JSON.stringify(wv.senderos), copia);
});

test("composición: terreno/agua (drawImage) < caminos (fillRect) < ambiente (drawImage) < entidades (arc)", () => {
  const meta = { ancho: 2, alto: 2 };
  const ter = WV.terrenoDesdeCapas({ bioma: new Uint8Array([1, 1, 1, 1]), agua: new Uint8Array([0, 1, 0, 0]) }, meta);
  const md = WV.terrenoDesdeCapas({ nieve: new Uint8Array([0, 2, 0, 0]) }, meta);
  const wv = WV.crearWorldView({ worldId: "w", meta },
    { terreno: ter.terreno, mapas_dinamicos: md.mapas_dinamicos, senderos: [[1, 1]], habitantes: [{ id: 1, x: 1, y: 1, color: 0, vivo: true }] });

  const seq = [];
  const ctx = {
    fillStyle: "", strokeStyle: "", imageSmoothingEnabled: false, _last: null,
    beginPath() {}, arc() { seq.push("arc"); }, fill() {}, stroke() {},
    drawImage() { seq.push("drawImage"); },
    fillRect() { seq.push("fillRect"); },
  };
  const frame = { vis: { x0: 0, y0: 0, x1: 2, y1: 2 }, lod: 1 };
  const cf = crearCanvasFalso();
  const capas = [CT.crearCapaTerreno({ crearCanvas: cf }), CA.crearCapaAgua({ crearCanvas: cf }),
    CC.crearCapaCaminos({}), CB.crearCapaAmbiente({ crearCanvas: cf }), CE.crearCapaEntidades({ COLORES: ["#111"] })];
  for (const c of capas) c.setWorldView(wv);
  for (const c of capas) c.draw(ctx, frame);

  const iCam = seq.indexOf("fillRect");
  const iArc = seq.indexOf("arc");
  assert.ok(iCam >= 0 && iArc >= 0, "caminos y entidades dibujan");
  assert.ok(iCam < iArc, "caminos antes que entidades");
  assert.ok(seq.lastIndexOf("drawImage", iCam) >= 0, "hay drawImage (terreno/agua) antes de caminos");
  assert.ok(seq.indexOf("drawImage", iCam) >= 0 && seq.indexOf("drawImage", iCam) < iArc, "ambiente (drawImage) entre caminos y entidades");
});
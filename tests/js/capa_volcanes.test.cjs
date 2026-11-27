"use strict";
const test = require("node:test");
const assert = require("node:assert");
const WV = require("../../ui/render/worldview.js");
const CV = require("../../ui/render/capa_volcanes.js");

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

function wvRasgos(rasgos) {
  const meta = { ancho: 2, alto: 2 };
  const ter = WV.terrenoDesdeCapas({ rasgos }, meta);
  return WV.crearWorldView({ worldId: "w", meta }, { terreno: ter.terreno });
}

test("lava válida: bit 2 => celda opaca; otros bits (cascada) no son lava", () => {
  const wv = wvRasgos(new Uint8Array([0, 2, 1, 3])); // 0 nada, 2 lava, 1 cascada, 3 lava+cascada
  const capa = CV.crearCapaVolcanes({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wv);
  const px = new Uint32Array(capa.bitmap._last().data.buffer);
  assert.strictEqual(px[0] >>> 24, 0, "sin rasgo => transparente");
  assert.strictEqual(px[1] >>> 24, 255, "lava (bit 2) opaca");
  assert.strictEqual(px[2] >>> 24, 0, "cascada (bit 1) no es lava");
  assert.strictEqual(px[3] >>> 24, 255, "lava+cascada => lava opaca");
});

test("rasgos ausentes => no dibuja", () => {
  const capa = CV.crearCapaVolcanes({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wvRasgos(null));
  assert.strictEqual(capa.bitmap, null);
});

test("rasgos con longitud inválida => no dibuja", () => {
  const capa = CV.crearCapaVolcanes({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wvRasgos(new Uint8Array([2, 2, 2]))); // 3 != 2*2
  assert.strictEqual(capa.bitmap, null);
});

test("caché por identidad: mismos rasgos => mismo bitmap", () => {
  const r = new Uint8Array([0, 2, 0, 0]);
  const wv = wvRasgos(r);
  const capa = CV.crearCapaVolcanes({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wv);
  const a = capa.bitmap;
  capa.setWorldView(wv);
  assert.strictEqual(capa.bitmap, a);
});

test("cambio de mundo (nuevo buffer) reconstruye", () => {
  const capa = CV.crearCapaVolcanes({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wvRasgos(new Uint8Array([0, 2, 0, 0])));
  const a = capa.bitmap;
  capa.setWorldView(wvRasgos(new Uint8Array([0, 0, 0, 2])));
  assert.notStrictEqual(capa.bitmap, a);
});

test("draw pinta sólo la región visible (clipping por frame.vis)", () => {
  const wv = wvRasgos(new Uint8Array([2, 2, 2, 2]));
  const capa = CV.crearCapaVolcanes({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wv);
  let args = null;
  const ctx = { imageSmoothingEnabled: false, drawImage(...a) { args = a; } };
  capa.draw(ctx, { vis: { x0: 1, y0: 1, x1: 2, y1: 2 } });
  assert.deepStrictEqual(args.slice(1, 5), [1, 1, 1, 1], "dibuja el sub-rectángulo visible");
});

test("no muta la WorldView", () => {
  const wv = wvRasgos(new Uint8Array([0, 2, 0, 1]));
  const copia = JSON.stringify(Array.from(wv.terreno.rasgos));
  const capa = CV.crearCapaVolcanes({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wv);
  assert.strictEqual(JSON.stringify(Array.from(wv.terreno.rasgos)), copia);
});
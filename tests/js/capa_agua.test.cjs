"use strict";
const test = require("node:test");
const assert = require("node:assert");
const WV = require("../../ui/render/worldview.js");
const CA = require("../../ui/render/capa_agua.js");

// Canvas falso: registra el último ImageData para inspeccionar píxeles (RGBA little-endian).
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

function wvAgua(agua, caudal) {
  const meta = { ancho: 2, alto: 2 };
  const ter = WV.terrenoDesdeCapas({ agua, caudal }, meta);
  return WV.crearWorldView({ worldId: "w", meta }, { terreno: ter.terreno, mapas_dinamicos: ter.mapas_dinamicos });
}

test("agua válida: 0 transparente, 1/2/3 con color, río modulada por caudal", () => {
  const wv = wvAgua(new Uint8Array([0, 1, 2, 3]), new Uint8Array([0, 0, 0, 128]));
  const capa = CA.crearCapaAgua({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wv);
  const px = new Uint32Array(capa.bitmap._last().data.buffer);
  assert.strictEqual(px[0] >>> 24, 0, "agua 0 => transparente");
  assert.strictEqual(px[1] >>> 24, 255, "océano opaco");
  assert.notStrictEqual(px[1], px[2], "océano y lago colorean distinto");
  assert.strictEqual(px[3] >>> 24, 255, "río opaco");
});

test("agua ausente => no dibuja (bitmap null)", () => {
  const capa = CA.crearCapaAgua({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wvAgua(null, null));
  assert.strictEqual(capa.bitmap, null);
});

test("agua con longitud inválida => no dibuja", () => {
  const capa = CA.crearCapaAgua({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wvAgua(new Uint8Array([1, 2, 3]), null)); // 3 != 2*2
  assert.strictEqual(capa.bitmap, null);
});

test("caché por identidad: mismos buffers => mismo bitmap", () => {
  const agua = new Uint8Array([0, 1, 2, 3]);
  const wv = wvAgua(agua, new Uint8Array([0, 0, 0, 0]));
  const capa = CA.crearCapaAgua({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wv);
  const a = capa.bitmap;
  capa.setWorldView(wv); // misma vista
  assert.strictEqual(capa.bitmap, a, "reutiliza el bitmap");
});

test("cambio de mundo (nuevo buffer) reconstruye el bitmap", () => {
  const capa = CA.crearCapaAgua({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wvAgua(new Uint8Array([0, 1, 2, 3]), null));
  const a = capa.bitmap;
  capa.setWorldView(wvAgua(new Uint8Array([3, 3, 3, 3]), null));
  assert.notStrictEqual(capa.bitmap, a);
});

test("no muta la WorldView", () => {
  const wv = wvAgua(new Uint8Array([0, 1, 2, 3]), new Uint8Array([0, 0, 0, 9]));
  const copia = JSON.stringify({ a: Array.from(wv.terreno.agua), c: Array.from(wv.terreno.caudal) });
  const capa = CA.crearCapaAgua({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wv);
  assert.strictEqual(JSON.stringify({ a: Array.from(wv.terreno.agua), c: Array.from(wv.terreno.caudal) }), copia);
});
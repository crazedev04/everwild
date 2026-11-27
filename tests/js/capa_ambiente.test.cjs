"use strict";
const test = require("node:test");
const assert = require("node:assert");
const WV = require("../../ui/render/worldview.js");
const CB = require("../../ui/render/capa_ambiente.js");

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

function wvAmbiente(nieve, quemado) {
  const meta = { ancho: 2, alto: 2 };
  const ter = WV.terrenoDesdeCapas({ nieve, quemado }, meta);
  return WV.crearWorldView({ worldId: "w", meta }, { terreno: ter.terreno, mapas_dinamicos: ter.mapas_dinamicos });
}

test("nieve y quemado válidos: 0 transparente, >0 con alfa", () => {
  const wv = wvAmbiente(new Uint8Array([0, 255, 0, 0]), new Uint8Array([0, 0, 128, 0]));
  const capa = CB.crearCapaAmbiente({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wv);
  const nieve = new Uint32Array(capa.nieveBitmap._last().data.buffer);
  const quem = new Uint32Array(capa.quemadoBitmap._last().data.buffer);
  assert.strictEqual(nieve[0] >>> 24, 0, "nieve 0 => transparente");
  assert.ok((nieve[1] >>> 24) > 0, "nieve 255 => opaca");
  assert.strictEqual(quem[0] >>> 24, 0, "quemado 0 => transparente");
  assert.ok((quem[2] >>> 24) > 0, "quemado 128 => alfa intermedio");
});

test("ambiente ausente => no dibuja", () => {
  const capa = CB.crearCapaAmbiente({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wvAmbiente(null, null));
  assert.strictEqual(capa.nieveBitmap, null);
  assert.strictEqual(capa.quemadoBitmap, null);
});

test("longitud inválida => ese mapa no dibuja", () => {
  const capa = CB.crearCapaAmbiente({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wvAmbiente(new Uint8Array([1, 2, 3]), new Uint8Array([0, 0, 0, 0])));
  assert.strictEqual(capa.nieveBitmap, null, "nieve inválida no dibuja");
  assert.ok(capa.quemadoBitmap, "quemado válido sí dibuja");
});

test("caché por identidad: mismos buffers => mismo bitmap", () => {
  const nieve = new Uint8Array([0, 1, 0, 0]);
  const wv = wvAmbiente(nieve, new Uint8Array([0, 0, 0, 0]));
  const capa = CB.crearCapaAmbiente({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wv);
  const a = capa.nieveBitmap;
  capa.setWorldView(wv);
  assert.strictEqual(capa.nieveBitmap, a);
});

test("cambio de mundo (nuevo buffer) reconstruye", () => {
  const capa = CB.crearCapaAmbiente({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wvAmbiente(new Uint8Array([0, 1, 0, 0]), null));
  const a = capa.nieveBitmap;
  capa.setWorldView(wvAmbiente(new Uint8Array([0, 9, 0, 0]), null));
  assert.notStrictEqual(capa.nieveBitmap, a);
});

test("no muta la WorldView", () => {
  const wv = wvAmbiente(new Uint8Array([0, 5, 0, 0]), new Uint8Array([0, 0, 7, 0]));
  const copia = JSON.stringify({ n: Array.from(wv.mapas_dinamicos.nieve), q: Array.from(wv.mapas_dinamicos.quemado) });
  const capa = CB.crearCapaAmbiente({ crearCanvas: crearCanvasFalso() });
  capa.setWorldView(wv);
  assert.strictEqual(JSON.stringify({ n: Array.from(wv.mapas_dinamicos.nieve), q: Array.from(wv.mapas_dinamicos.quemado) }), copia);
});
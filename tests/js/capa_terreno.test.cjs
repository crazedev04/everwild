"use strict";
// Regresión de la capa de terreno (E2): bitmap 1 px/celda desde bioma+paleta, sólo visible,
// y ausencia/invalidéz => no dibuja. Usa superficies simuladas (sin DOM real).
const test = require("node:test");
const assert = require("node:assert");
const { crearCapaTerreno } = require("../../ui/render/capa_terreno.js");

function entorno() {
  const pintadas = [];
  function crearCanvas(w, h) {
    const octx = {
      createImageData(ww, hh) { return { data: new Uint8ClampedArray(ww * hh * 4), width: ww, height: hh }; },
      putImageData(img) { pintadas.push(img); },
    };
    return { width: w, height: h, getContext: () => octx };
  }
  return { crearCanvas, pintadas };
}

const wvBioma = (bioma, w, h) => ({ meta: { ancho: w, alto: h }, terreno: { bioma }, t: 1 });

test("construye bitmap 1 px/celda con la paleta (little-endian)", () => {
  const e = entorno();
  const capa = crearCapaTerreno({ crearCanvas: e.crearCanvas });
  capa.setPaleta({ 0: [255, 0, 0], 1: [0, 255, 0] });
  capa.setWorldView(wvBioma(new Uint8Array([0, 1, 1, 0]), 2, 2));
  assert.ok(capa.bitmap, "bitmap construido");
  assert.strictEqual(e.pintadas.length, 1, "putImageData una vez");
  const d32 = new Uint32Array(e.pintadas[0].data.buffer);
  assert.strictEqual(d32[0], ((255 << 24) | (0 << 16) | (0 << 8) | 255) >>> 0); // rojo
  assert.strictEqual(d32[1], ((255 << 24) | (0 << 16) | (255 << 8) | 0) >>> 0); // verde
});

test("draw pinta sólo la porción visible", () => {
  const e = entorno();
  const capa = crearCapaTerreno({ crearCanvas: e.crearCanvas });
  capa.setWorldView(wvBioma(new Uint8Array(4), 2, 2));
  let llamado = null;
  const ctx = { imageSmoothingEnabled: true, drawImage(...a) { llamado = a; } };
  capa.draw(ctx, { vis: { x0: 0, y0: 0, x1: 2, y1: 2 } });
  assert.ok(llamado, "drawImage invocado");
  assert.deepStrictEqual(llamado.slice(1), [0, 0, 2, 2, 0, 0, 2, 2]);
  assert.strictEqual(ctx.imageSmoothingEnabled, false);
});

test("datos ausentes o inválidos => no dibuja (no engaña)", () => {
  const e = entorno();
  const capa = crearCapaTerreno({ crearCanvas: e.crearCanvas });
  capa.setWorldView({ meta: { ancho: 2, alto: 2 }, terreno: {} }); // sin bioma
  assert.strictEqual(capa.bitmap, null);
  capa.setWorldView(wvBioma(new Uint8Array(3), 2, 2)); // longitud != ancho*alto
  assert.strictEqual(capa.bitmap, null);
  let dibujo = false;
  capa.draw({ drawImage() { dibujo = true; } }, { vis: { x0: 0, y0: 0, x1: 2, y1: 2 } });
  assert.strictEqual(dibujo, false);
});

test("bioma sin color en paleta => magenta (no inventa color real)", () => {
  const e = entorno();
  const capa = crearCapaTerreno({ crearCanvas: e.crearCanvas });
  capa.setPaleta({}); // sin entradas
  capa.setWorldView(wvBioma(new Uint8Array([7]), 1, 1));
  const d32 = new Uint32Array(e.pintadas[0].data.buffer);
  assert.strictEqual(d32[0], ((255 << 24) | (255 << 16) | (0 << 8) | 255) >>> 0); // magenta
});
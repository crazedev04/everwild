"use strict";
// Regresión del modelo/normalización de WorldView (E1): identidad real, capas válidas,
// ausencia => null y vista provisional sin authoritativeRev. PURO (sin DOM/REST).
const test = require("node:test");
const assert = require("node:assert");
const WV = require("../../ui/render/worldview.js");

const meta = { ancho: 2, alto: 2, tam_celda_m: 50 }; // esperado = 4

test("capaValida: exige longitud == ancho*alto", () => {
  assert.strictEqual(WV.capaValida(new Uint8Array(4), meta), true);
  assert.strictEqual(WV.capaValida(new Uint8Array(3), meta), false);
  assert.strictEqual(WV.capaValida(null, meta), false);
});

test("terrenoDesdeCapas: capa inválida/ausente queda null, válida se conserva", () => {
  const capas = { bioma: new Uint8Array(4), agua: new Uint8Array(2), caudal: new Uint8Array(4) };
  const { terreno, mapas_dinamicos } = WV.terrenoDesdeCapas(capas, meta);
  assert.ok(terreno.bioma instanceof Uint8Array);
  assert.strictEqual(terreno.agua, null);        // longitud 2 != 4
  assert.ok(terreno.caudal instanceof Uint8Array);
  assert.strictEqual(terreno.elev, null);        // ausente
  assert.strictEqual(mapas_dinamicos.nieve, null);
});

test("habitantes: identidad por id, vitales mergeadas, sin inventar campos", () => {
  const habs = [{ id: 7, x: 1, y: 2, vivo: true, color: 3, accion: "libre" }];
  const vitales = [[7, 80, 30, 70, 20, 12, 0]];
  const out = WV.habitantesDesdeEstado(habs, vitales);
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0].id, 7);
  assert.deepStrictEqual(out[0].vitales, { salud: 80, sed: 30, energia: 70, hambre: 20, temp: 12, frio: 0 });
  assert.strictEqual(out[0].inst, undefined);    // no se inventa inst en habitantes
  assert.strictEqual(out[0].nombre, undefined);  // no se inventan atributos
});

test("fauna: identidad compuesta inst tal cual", () => {
  const out = WV.faunaDesdeEstado([{ inst: 12, x: 5, y: 6, clase: "conejo", peligro: 0 }]);
  assert.strictEqual(out[0].inst, 12);
  assert.strictEqual(out[0].clase, "conejo");
});

test("secciones ausentes => null (no arrays vacíos inventados)", () => {
  const s = WV.seccionesDesdeEstado({});
  assert.strictEqual(s.habitantes, null);
  assert.strictEqual(s.fauna, null);
  assert.strictEqual(s.estructuras, null);
  assert.strictEqual(s.senderos, null);
  assert.strictEqual(s.clima, null);
});

test("estructuras = refugios + ruinas con marca de ruina", () => {
  const s = WV.seccionesDesdeEstado({ refugios: [{ id: "r1", x: 1, y: 2 }], ruinas: [{ id: "u1", x: 3, y: 4 }] });
  assert.strictEqual(s.estructuras.length, 2);
  assert.strictEqual(s.estructuras[0].ruina, false);
  assert.strictEqual(s.estructuras[1].ruina, true);
});

test("crearWorldView provisional: autoritativo=false y sin authoritativeRev", () => {
  const wv = WV.crearWorldView(
    { worldId: "M", dimension: 0, localSequence: 5, t: 100, meta },
    { habitantes: [], terreno: { bioma: new Uint8Array(4) } }
  );
  assert.strictEqual(wv.autoritativo, false);
  assert.strictEqual(wv.authoritativeRev, null);
  assert.strictEqual(wv.localSequence, 5);
  assert.strictEqual(wv.worldId, "M");
  assert.ok(Object.isFrozen(wv));                 // sólo lectura (nivel superior)
});

test("crearWorldView con authoritativeRev => autoritativo=true (contrato backend)", () => {
  const wv = WV.crearWorldView(
    { worldId: "M", dimension: 0, localSequence: 5, authoritativeRev: 184, meta }, {}
  );
  assert.strictEqual(wv.autoritativo, true);
  assert.strictEqual(wv.authoritativeRev, 184);
});
test("estructuras reales (triples [x,y,tipo]) con ruina por subconjunto", () => {
  const s = WV.seccionesDesdeEstado({ refugios: [[1, 2, "casa"], [3, 4, "choza"]], ruinas: [[3, 4, "choza"]] });
  assert.strictEqual(s.estructuras.length, 2);
  assert.strictEqual(s.estructuras[0].tipo, "casa");
  assert.strictEqual(s.estructuras[0].ruina, false);
  assert.strictEqual(s.estructuras[1].ruina, true);
});

test("fauna real (triples [inst,x,y]) sin inventar atributos", () => {
  const s = WV.seccionesDesdeEstado({ fauna: [[12, 5, 6]] });
  assert.strictEqual(s.fauna.length, 1);
  assert.strictEqual(s.fauna[0].inst, 12);
  assert.strictEqual(s.fauna[0].x, 5);
  assert.strictEqual(s.fauna[0].clase, undefined);
});

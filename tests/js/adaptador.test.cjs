"use strict";
// Regresión del adaptador provisional (E1): buildGen descarta ciclos viejos, reemplazo
// COMPLETO de WorldView, fallo parcial no entrega, cambio de mundo/dimensión.
const test = require("node:test");
const assert = require("node:assert");
const { crearAdaptador } = require("../../ui/render/adaptador.js");

const meta = { ancho: 2, alto: 2, tam_celda_m: 50 };
const capas = () => ({ bioma: new Uint8Array([1, 2, 3, 4]), agua: new Uint8Array(4) });
const ctx0 = { worldId: "M", dimension: 0 };

test("construir+entregar: reemplazo completo de la vista provisional", async () => {
  const a = crearAdaptador();
  const gen = a.ciclo();
  const r = await a.construir(gen, ctx0, { meta, capas: capas(), estado: { t_min: 10, habitantes: [{ id: 1, x: 0, y: 0, vivo: true }] } });
  const e = a.entregar(r);
  assert.strictEqual(e.aplicada, true);
  assert.strictEqual(a.vista.worldId, "M");
  assert.strictEqual(a.vista.autoritativo, false);
  assert.strictEqual(a.vista.habitantes.length, 1);
});

test("respuesta de ciclo anterior se descarta (no contamina la vista)", async () => {
  const a = crearAdaptador();
  const g1 = a.ciclo();
  const r1 = await a.construir(g1, ctx0, { meta, capas: capas(), estado: { t_min: 1, habitantes: [{ id: 1, x: 0, y: 0 }] } });
  const g2 = a.ciclo(); // arranca uno nuevo antes de entregar el primero
  const e1 = a.entregar(r1); // obsoleto
  assert.strictEqual(e1.aplicada, false);
  assert.strictEqual(e1.motivo, "obsoleto");
  assert.strictEqual(a.vista, null); // nada se aplicó
  const r2 = await a.construir(g2, ctx0, { meta, capas: capas(), estado: { t_min: 2, habitantes: [{ id: 2, x: 1, y: 1 }] } });
  assert.strictEqual(a.entregar(r2).aplicada, true);
  assert.strictEqual(a.vista.habitantes[0].id, 2);
});

test("reemplazo completo: la vista nueva no mezcla secciones del ciclo viejo", async () => {
  const a = crearAdaptador();
  const g1 = a.ciclo();
  await a.entregar(await a.construir(g1, ctx0, { meta, capas: capas(), estado: { t_min: 1, habitantes: [{ id: 1, x: 0, y: 0 }], fauna: [{ inst: 9, x: 0, y: 0 }] } }));
  const g2 = a.ciclo();
  // el nuevo estado NO trae fauna: la vista nueva debe tener fauna=null, no la vieja
  await a.entregar(await a.construir(g2, ctx0, { meta, capas: capas(), estado: { t_min: 2, habitantes: [{ id: 2, x: 1, y: 1 }] } }));
  assert.strictEqual(a.vista.fauna, null);
  assert.strictEqual(a.vista.habitantes[0].id, 2);
});

test("fallo parcial del adaptador: no entrega y conserva la vista anterior", async () => {
  const a = crearAdaptador();
  const g1 = a.ciclo();
  await a.entregar(await a.construir(g1, ctx0, { meta, capas: capas(), estado: { t_min: 1, habitantes: [{ id: 1, x: 0, y: 0 }] } }));
  const g2 = a.ciclo();
  const mal = await a.construir(g2, ctx0, { meta, capas: { bioma: new Uint8Array(2) }, estado: { t_min: 9, habitantes: [{ id: 9, x: 0, y: 0 }] } });
  a.descartar(g2); // fallo parcial declarado por el adaptador
  const e = a.entregar(mal);
  assert.strictEqual(e.aplicada, false);
  assert.strictEqual(a.vista.habitantes[0].id, 1); // sigue la vieja
});

test("cambio de mundo/dimensión: ciclo nuevo adopta contexto; respuesta vieja se descarta", async () => {
  const a = crearAdaptador();
  const g1 = a.ciclo();
  const r1 = await a.construir(g1, ctx0, { meta, capas: capas(), estado: { t_min: 1 } });
  // llega un ciclo nuevo (cambio de mundo) antes de entregar el viejo
  const g2 = a.ciclo();
  await a.entregar(await a.construir(g2, { worldId: "Otro", dimension: 0 }, { meta, capas: capas(), estado: { t_min: 2 } }));
  assert.strictEqual(a.vista.worldId, "Otro");
  // la respuesta del mundo viejo (gen antigua) llega tarde: se descarta por obsoleta
  const e1 = a.entregar(r1);
  assert.strictEqual(e1.aplicada, false);
  assert.strictEqual(e1.motivo, "obsoleto");
  assert.strictEqual(a.vista.worldId, "Otro");
});

test("sin authoritativeRev la vista nunca es autoritativa (no simula revisiones)", async () => {
  const a = crearAdaptador();
  const g = a.ciclo();
  await a.entregar(await a.construir(g, ctx0, { meta, capas: capas(), estado: { t_min: 5 } }));
  assert.strictEqual(a.vista.autoritativo, false);
  assert.strictEqual(a.vista.authoritativeRev, null);
});
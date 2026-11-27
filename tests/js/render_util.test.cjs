"use strict";
// Regresión del renderizado bajo demanda (Etapa 1): criterio de "hace falta animar"
// y el planificador que evita bucles rAF duplicados y suspende cuando no hay cambios.
const test = require("node:test");
const assert = require("node:assert");
const { necesitaAnimacion, crearPlanificador } = require("../../ui/render-util.js");

const quieto = (x, y) => ({ x, y, d: { x, y, vivo: true } });

test("escena inactiva no necesita animación continua", () => {
  const habs = { 1: quieto(5, 5), 2: quieto(8, 9) };
  assert.strictEqual(necesitaAnimacion({ fuego: [], fogatas: [] }, habs, [], false), false);
});

test("fuego, fogatas, antorchas, efectos y movimiento fuerzan animación", () => {
  assert.strictEqual(necesitaAnimacion({ fuego: [[1, 2, 3]] }, {}, [], false), true);
  assert.strictEqual(necesitaAnimacion({ fogatas: [[1, 2, 1]] }, {}, [], false), true);
  assert.strictEqual(necesitaAnimacion({}, { 1: { x: 0, y: 0, d: { x: 0, y: 0, vivo: true, antorcha: true } } }, [], false), true);
  assert.strictEqual(necesitaAnimacion({}, {}, [{ tipo: "rayo" }], false), true);
  // habitante en movimiento (suavizado sin asentar)
  assert.strictEqual(necesitaAnimacion({}, { 1: quieto(0, 0) , 2: { x: 0, y: 0, d: { x: 3, y: 0, vivo: true } } }, [], false), true);
});

test("seguir activo fuerza animación (cámara en movimiento)", () => {
  assert.strictEqual(necesitaAnimacion({}, {}, [], true), true);
});

test("necesitaAnimacion es conservador ante estado ausente", () => {
  assert.strictEqual(necesitaAnimacion(null, {}, [], false), false);
});

test("planificador: no agenda dos frames por pedido (sin bucles duplicados)", () => {
  let raf = 0, pedido = 0;
  const plan = crearPlanificador((cb) => { pedido++; raf = cb; return pedido; }, () => {}, () => false);
  plan.pedir();
  plan.pedir();
  plan.pedir();
  assert.strictEqual(pedido, 1);
});

test("planificador: suspende cuando no hay más animación", () => {
  let pedido = 0;
  const plan = crearPlanificador((cb) => { pedido++; return pedido; }, () => {}, () => false);
  plan.pedir();
  plan._paso(); // ejecuta el frame: draw + decide
  assert.strictEqual(pedido, 1); // no re-agenda
});

test("planificador: continúa mientras haya animación", () => {
  let pedido = 0, animar = true;
  const plan = crearPlanificador((cb) => { pedido++; return pedido; }, () => {}, () => animar);
  plan.pedir();
  plan._paso();
  assert.strictEqual(pedido, 2); // re-agendó
  animar = false;
  plan._paso();
  assert.strictEqual(pedido, 2); // ya no
});

test("planificador: suspende con la pestaña oculta y reactiva al volver", () => {
  let pedido = 0;
  const plan = crearPlanificador((cb) => { pedido++; return pedido; }, () => {}, () => false);
  plan.setVisible(false);
  plan.pedir();
  assert.strictEqual(pedido, 0); // oculto: no agenda
  plan.setVisible(true);
  assert.strictEqual(pedido, 1); // reactiva
});

test("planificador: pending refleja si hay un frame agendado", () => {
  const plan = crearPlanificador((cb) => 1, () => {}, () => false);
  assert.strictEqual(plan.pending, false);
  plan.pedir();
  assert.strictEqual(plan.pending, true);
  plan._paso();
  assert.strictEqual(plan.pending, false);
});
test("planificador: cancelar limpia el frame pendiente y suspende", () => {
  let pedido = 0;
  const plan = crearPlanificador((cb) => { pedido++; return pedido; }, () => {}, () => false);
  plan.pedir();
  assert.strictEqual(plan.pending, true);
  plan.cancelar();
  assert.strictEqual(plan.pending, false);
  plan.pedir();
  assert.strictEqual(pedido, 1); // suspendido: no vuelve a agendar
});

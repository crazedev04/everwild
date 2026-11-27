// Helpers puros del prototipo de renderer 2D (Etapa 3A). Sin DOM ni dependencias.
// Se inspiran en técnicas de BiomeSimulator (LOD por zoom, culling, orden por Y,
// pooling) adaptadas a Canvas 2D. Todo determinista por semilla.
(function (root) {
  "use strict";

  // PRNG mulberry32: determinista por semilla.
  function rng(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Ruido de valor 2D con hash determinista (no consume el PRNG global).
  function _hash(x, y, seed) {
    let h = (x | 0) * 374761393 + (y | 0) * 668265263 + (seed | 0) * 2147483647;
    h = (h ^ (h >>> 13)) * 1274126177;
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }
  function _suave(t) { return t * t * (3 - 2 * t); }
  function ruido2(x, y, seed) {
    const xi = Math.floor(x), yi = Math.floor(y);
    const xf = _suave(x - xi), yf = _suave(y - yi);
    const a = _hash(xi, yi, seed), b = _hash(xi + 1, yi, seed);
    const c = _hash(xi, yi + 1, seed), d = _hash(xi + 1, yi + 1, seed);
    return (a * (1 - xf) + b * xf) * (1 - yf) + (c * (1 - xf) + d * xf) * yf;
  }
  // FBM: suma de octavas, resultado normalizado a [0,1].
  function fbm(x, y, seed, oct) {
    let v = 0, amp = 0.5, f = 1, norm = 0;
    for (let i = 0; i < (oct || 4); i++) {
      v += amp * ruido2(x * f, y * f, seed + i * 101);
      norm += amp; amp *= 0.5; f *= 2;
    }
    return v / norm;
  }

  // Nivel de detalle según zoom (umbrales tipo BiomeSimulator: sprites a z>=6,
  // detalle por celda a z>=10; de lejos puntos / híbrido).
  function seleccionarLOD(z) {
    if (z < 1) return { modo: "puntos", sprites: false, detalle: false, sombras: false };
    if (z < 6) return { modo: "hibrido", sprites: false, detalle: false, sombras: false };
    return { modo: "sprites", sprites: true, detalle: z >= 10, sombras: true };
  }

  // Culling: ¿la celda (x,y) con margen m cae en el rectángulo visible?
  function esVisible(x, y, m, vis) {
    return x >= vis.x0 - m && x <= vis.x1 + m && y >= vis.y0 - m && y <= vis.y1 + m;
  }

  // Orden por Y ascendente (más Y = más abajo = al frente). Estable.
  function ordenarPorY(lista) {
    return lista.slice().sort((a, b) => a.y - b.y);
  }

  // Pool de sprites: reutiliza objetos en vez de recrearlos (reduce GC).
  function crearPool(factory, reset) {
    const libres = [];
    return {
      obtener() {
        const o = libres.length ? libres.pop() : factory();
        if (reset) reset(o);
        return o;
      },
      devolver(o) { if (o) libres.push(o); },
      tam() { return libres.length; },
    };
  }

  const api = { rng, ruido2, fbm, seleccionarLOD, esVisible, ordenarPorY, crearPool };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.Layers = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
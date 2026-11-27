// Modelo y normalización de `WorldView` (E1). PURO: sin DOM, sin REST, sin WS.
// Toma datos ya normalizados (capas raster + secciones del estado) y arma una vista
// provisional de sólo lectura. No inventa entidades, atributos ni identificadores:
// sólo reordena lo que la fuente realmente publica (ver RENDERER_ARCHITECTURE §4).
(function (root) {
  "use strict";

  // Longitud esperada de una capa raster a 1 px/celda.
  function esperado(meta) {
    if (!meta || meta.ancho == null || meta.alto == null) return null;
    return meta.ancho * meta.alto;
  }

  // Una capa raster es válida sólo si existe y su longitud == ancho*alto (§4.5).
  function capaValida(capa, meta) {
    const n = esperado(meta);
    if (n == null || capa == null) return false;
    return capa.length === n;
  }

  // Terreno normalizado: cada capa válida se conserva; la inválida/ausente queda null.
  // No copia los buffers (garantía de no mutación externa del adaptador, §4.4).
  function terrenoDesdeCapas(capas, meta) {
    const c = capas || {};
    const t = {
      bioma: capaValida(c.bioma, meta) ? c.bioma : null,
      agua: capaValida(c.agua, meta) ? c.agua : null,
      caudal: capaValida(c.caudal, meta) ? c.caudal : null,
      rasgos: capaValida(c.rasgos, meta) ? c.rasgos : null,
      elev: capaValida(c.elev, meta) ? c.elev : null,
      temp: capaValida(c.temp, meta) ? c.temp : null,
      hum: capaValida(c.hum, meta) ? c.hum : null,
    };
    const dinamicos = {
      nieve: capaValida(c.nieve, meta) ? c.nieve : null,
      quemado: capaValida(c.quemado, meta) ? c.quemado : null,
    };
    return { terreno: t, mapas_dinamicos: dinamicos };
  }

  // Identidad y mapeo de habitantes: sólo campos presentes; `id` simple (feed vivo).
  function habitantesDesdeEstado(habitantes, vitales) {
    if (!Array.isArray(habitantes)) return null;
    const porId = {};
    if (Array.isArray(vitales)) {
      for (const v of vitales) {
        if (!v || v[0] == null) continue;
        porId[v[0]] = { salud: v[1], sed: v[2], energia: v[3], hambre: v[4], temp: v[5], frio: v[6] };
      }
    }
    return habitantes.map((h) => {
      const o = { id: h.id, x: h.x, y: h.y };
      if (h.vivo != null) o.vivo = h.vivo;
      if (h.color != null) o.color = h.color;
      if (h.sexo != null) o.sexo = h.sexo;
      if (h.nac != null) o.nac = h.nac;
      if (h.accion != null) o.accion = h.accion;
      if (h.detalle != null) o.detalle = h.detalle;
      if (h.en_fuego != null) o.en_fuego = h.en_fuego;
      if (h.antorcha != null) o.antorcha = h.antorcha;
      if (h.emo != null) o.emo = h.emo;
      const vi = porId[h.id];
      if (vi) o.vitales = vi;
      return o;
    });
  }

  // Fauna: identidad compuesta `inst` (única fuente que hoy la publica, §4.3).
  function faunaDesdeEstado(fauna) {
    if (!Array.isArray(fauna)) return null;
    return fauna.map((a) => {
      const o = { inst: a.inst, x: a.x, y: a.y };
      if (a.clase != null) o.clase = a.clase;
      if (a.medio != null) o.medio = a.medio;
      if (a.peso_kg != null) o.peso_kg = a.peso_kg;
      if (a.peligro != null) o.peligro = a.peligro;
      return o;
    });
  }

  // Estructuras = refugios + ruinas (sólo si la fuente los trae). No inventa ids.
  function estructurasDesdeEstado(estado) {
    const partes = [];
    if (Array.isArray(estado.refugios)) for (const r of estado.refugios) partes.push(Object.assign({ ruina: false }, r));
    if (Array.isArray(estado.ruinas)) for (const r of estado.ruinas) partes.push(Object.assign({ ruina: true }, r));
    return partes.length ? partes : null;
  }

  // Secciones del estado (presentador.estado) → secciones WorldView. Ausente => null.
  function seccionesDesdeEstado(estado) {
    const e = estado || {};
    const clima = (e.luz != null || e.tormentas != null || e.viento != null)
      ? { luz: e.luz != null ? e.luz : null, tormentas: e.tormentas != null ? e.tormentas : null, viento: e.viento != null ? e.viento : null }
      : null;
    return {
      estructuras: estructurasDesdeEstado(e),
      senderos: Array.isArray(e.senderos) ? e.senderos : null,
      aldeas: Array.isArray(e.aldeas) ? e.aldeas : null,
      fogatas: Array.isArray(e.fogatas) ? e.fogatas : null,
      fuego: Array.isArray(e.fuego) ? e.fuego : null,
      clima: clima,
      habitantes: habitantesDesdeEstado(e.habitantes, e.vitales),
      fauna: faunaDesdeEstado(e.fauna),
    };
  }

  // Arma la WorldView completa. `autoritativo` es true SÓLO si hay authoritativeRev
  // (contrato backend, §4.8); en modo provisional es false y no hay authoritativeRev.
  // Congela el nivel superior para señalar "de sólo lectura" (los TypedArray siguen
  // mutables por dentro: la garantía es de no mutación externa, §4.4).
  function crearWorldView(cabecera, secciones, opciones) {
    const op = opciones || {};
    const conRev = cabecera.authoritativeRev != null;
    const wv = {
      worldId: cabecera.worldId,
      dimension: cabecera.dimension == null ? 0 : cabecera.dimension,
      localSequence: cabecera.localSequence,
      authoritativeRev: conRev ? cabecera.authoritativeRev : null,
      autoritativo: conRev,
      t: cabecera.t != null ? cabecera.t : null,
      meta: cabecera.meta,
      terreno: (secciones && secciones.terreno) || null,
      mapas_dinamicos: (secciones && secciones.mapas_dinamicos) || null,
      estructuras: (secciones && secciones.estructuras) || null,
      senderos: (secciones && secciones.senderos) || null,
      aldeas: (secciones && secciones.aldeas) || null,
      fogatas: (secciones && secciones.fogatas) || null,
      fuego: (secciones && secciones.fuego) || null,
      clima: (secciones && secciones.clima) || null,
      habitantes: (secciones && secciones.habitantes) || null,
      fauna: (secciones && secciones.fauna) || null,
      efectos: op.efectos || null,
    };
    return Object.freeze(wv);
  }

  var api = {
    esperado: esperado,
    capaValida: capaValida,
    terrenoDesdeCapas: terrenoDesdeCapas,
    seccionesDesdeEstado: seccionesDesdeEstado,
    habitantesDesdeEstado: habitantesDesdeEstado,
    faunaDesdeEstado: faunaDesdeEstado,
    crearWorldView: crearWorldView,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.WorldView = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
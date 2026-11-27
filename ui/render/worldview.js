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

  // Fauna: identidad compuesta `inst`. El feed vivo real publica triples [inst,x,y];
  // también se aceptan objetos {inst,x,y,clase,...} (compatibilidad). No inventa atributos.
  function faunaDesdeEstado(fauna) {
    if (!Array.isArray(fauna)) return null;
    return fauna.map((a) => {
      var o = Array.isArray(a) ? { inst: a[0], x: a[1], y: a[2] } : { inst: a.inst, x: a.x, y: a.y };
      if (!Array.isArray(a)) {
        if (a.clase != null) o.clase = a.clase;
        if (a.medio != null) o.medio = a.medio;
        if (a.peso_kg != null) o.peso_kg = a.peso_kg;
        if (a.peligro != null) o.peligro = a.peligro;
      }
      return o;
    });
  }

  // Normaliza una estructura (objeto {x,y,tipo,...} o triple [x,y,tipo]) a objeto.
  function _estructura(r) {
    if (Array.isArray(r)) return { x: r[0], y: r[1], tipo: r[2] };
    return Object.assign({}, r);
  }
  function _claveEstructura(r) {
    if (Array.isArray(r)) return r[0] + "," + r[1] + "," + r[2];
    return r.x + "," + r.y + "," + r.tipo;
  }

  // Estructuras = refugios + ruinas. El backend real publica refugios como triples
  // [x,y,tipo] y ruinas como subconjunto de refugios (mismo formato). Se marcan `ruina`
  // por pertenencia; una ruina que no esté en refugios se agrega aparte (compatibilidad).
  function estructurasDesdeEstado(estado) {
    var refugios = Array.isArray(estado.refugios) ? estado.refugios : [];
    var ruinas = Array.isArray(estado.ruinas) ? estado.ruinas : [];
    var clavesRuina = {}, clavesRefugio = {};
    for (var i = 0; i < ruinas.length; i++) clavesRuina[_claveEstructura(ruinas[i])] = true;
    for (var j = 0; j < refugios.length; j++) clavesRefugio[_claveEstructura(refugios[j])] = true;
    var out = [];
    for (var k = 0; k < refugios.length; k++) {
      var o = _estructura(refugios[k]);
      o.ruina = !!clavesRuina[_claveEstructura(refugios[k])];
      out.push(o);
    }
    for (var m = 0; m < ruinas.length; m++) {
      if (!clavesRefugio[_claveEstructura(ruinas[m])]) { var q = _estructura(ruinas[m]); q.ruina = true; out.push(q); }
    }
    return out.length ? out : null;
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
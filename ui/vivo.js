// Capa en vivo del visor: se conecta por WebSocket y dibuja habitantes, día/noche, fuego, ceniza, tormentas y efectos.
// Solo muestra lo que manda el servidor (no tiene reglas del mundo). Se apoya en mapa.js (window.MVBase).
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const COLORES = ["#ff7a59", "#5ac8fa", "#ffd166", "#b794f6", "#6ee7a8", "#f472b6", "#f59e0b", "#94a3b8"];
  const V = {
    nombre: null, ws: null, meta: null, conectado: false, reintento: null,
    estado: null, luz: 1, habs: {}, velocidades: [], velocidad: 1, velocidadReal: 0,
    efectos: [], eventos: [], sel: null, seguir: false, herramientaFuego: false,
    herramientaPoder: null, spawnPendiente: null,
    oscuro: null, ceniza: { canvas: null, v: -1, pedido: 0 }, nieve: { canvas: null, v: -1, pedido: 0 }, ultimoFrame: 0, fichaT: 0,
  };
  window.App.registrar("vivo", V);   // contrato explícito (antes window.MV)

  const base = () => window.App.parte("terreno");   // acceso al terreno/cámara (antes window.MVBase)
  const dosDig = (n) => (n < 10 ? "0" : "") + n;
  function textoHora(t) {
    const dia = Math.floor(t / 1440) + 1, m = Math.floor(t % 1440);
    return "Día " + dia + " " + dosDig(Math.floor(m / 60)) + ":" + dosDig(m % 60);
  }
  // Estado de las secciones <details>: se recuerda por clave para que un refresco no las cierre.
  const ABIERTAS = (() => { try { return JSON.parse(localStorage.getItem("mv_abiertas") || "{}"); } catch (e) { return {}; } })();
  const abre = (clave, pordefecto) => (clave in ABIERTAS ? ABIERTAS[clave] : !!pordefecto);
  document.addEventListener("toggle", (ev) => {
    const d = ev.target;
    if (!d || d.tagName !== "DETAILS" || !d.dataset.k) return;
    ABIERTAS[d.dataset.k] = d.open;
    try { localStorage.setItem("mv_abiertas", JSON.stringify(ABIERTAS)); } catch (e) {}
  }, true);
  const seccion = (clave, titulo, n, cuerpo, pordefecto) =>
    "<details data-k='" + clave + "'" + (abre(clave, pordefecto) ? " open" : "") + "><summary><span>" + titulo +
    (n != null ? "<span class='n'>" + n + "</span>" : "") + "</span></summary>" + cuerpo + "</details>";
  // Cambia el contenido solo si cambió de verdad, y no mueve el scroll del panel.
  function poner(el, html) {
    if (el._html === html) return;
    const sc = $("paneles"), y = sc ? sc.scrollTop : 0;
    el.innerHTML = html; el._html = html;
    if (sc) sc.scrollTop = y;
  }
  const ESTACION_ICONO = { primavera: "🌱", verano: "☀️", otoño: "🍂", invierno: "❄️" };
  // Qué se ve en el suelo de cada bioma con zoom alto (ids de motor/biomas.py).

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // Edad en años del mundo (1 año = 120 días). Antes se mostraban los días pelados y a los 3000 días no se entendía nada.
  const DIAS_ANIO = 120;
  function edadTexto(dias, corto) {
    const d = Math.max(0, Math.floor(dias || 0));
    const a = Math.floor(d / DIAS_ANIO), r = d % DIAS_ANIO;
    if (corto) return a >= 1 ? a + "a" + (r ? " " + r + "d" : "") : d + "d";
    if (a < 1) return d + (d === 1 ? " día" : " días");
    const sa = a + (a === 1 ? " año" : " años");
    return r ? sa + " y " + r + (r === 1 ? " día" : " días") : sa;
  }

  // ------------------------------------------------------------ conexión
  V.alAbrir = function (nombre, meta, dimension) {
    const mismaConexion = V.nombre === nombre && V.ws && V.ws.readyState === 1;
    V.dimension = dimension || 0;
    if (mismaConexion) { V.meta = meta; return; }   // sólo cambió el mapa que se mira: no se reconecta
    desconectar();
    V.nombre = nombre; V.meta = meta; V.habs = {}; V.efectos = []; V.eventos = []; V.sel = null; V.estado = null;
    V.oscuro = null; V.ceniza = { canvas: null, v: -1, pedido: 0 }; V.nieve = { canvas: null, v: -1, pedido: 0 };
    $("feed").innerHTML = ""; $("ficha")._html = null; $("ficha").innerHTML = "<p class='nota'>Elegí a alguien de la lista o en el mapa para ver qué piensa, a quién quiere y qué recuerda.</p>";
    $("ficha-cab").classList.remove("visible"); $("habitantes")._ids = null; $("habitantes").innerHTML = ""; $("recetas")._html = null; $("fauna-lista")._html = null;
    conectar();
  };

  function desconectar() {
    if (V.reintento) { clearTimeout(V.reintento); V.reintento = null; }
    if (V.ws) { const w = V.ws; V.ws = null; w.onclose = null; try { w.close(); } catch (e) {} }
    V.conectado = false;
  }

  V.desconectar = function () { desconectar(); V.nombre = null; };

  function conectar() {
    if (!V.nombre) return;
    const nombre = V.nombre, proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(proto + "//" + location.host + "/ws/" + encodeURIComponent(nombre));
    V.ws = ws;
    ws.onopen = () => { V.conectado = true; marcarConexion(); };
    ws.onmessage = (ev) => { if (ws !== V.ws) return; let m; try { m = JSON.parse(ev.data); } catch (e) { return; } recibir(m); };
    ws.onclose = () => {
      V.conectado = false; marcarConexion();
      if (V.ws === ws && V.nombre === nombre) V.reintento = setTimeout(conectar, 2000);
    };
  }

  function armarDimensiones(dims, actual) {
    // Mientras el mundo tiene un solo mapa esto no se muestra: nadie tiene por qué saber que existe la idea.
    const sel = $("sel-dimension");
    if (!dims || dims.length < 2) { sel.style.display = "none"; return; }
    const firma = dims.map((d) => d.id + ":" + d.nombre).join("|");
    if (sel._firma !== firma) {
      sel._firma = firma;
      sel.innerHTML = dims.map((d) => "<option value='" + d.id + "'>" + esc(d.nombre) + " (" + d.habitantes + ")</option>").join("");
    }
    sel.value = String(actual == null ? V.dimension || 0 : actual);
    sel.style.display = "";
    if (V.dimension !== +sel.value) {      // el servidor cambió de mapa: hay que traer las capas nuevas
      V.dimension = +sel.value;
      const t = window.App.parte("terreno"); if (t && t.abrirMapa) t.abrirMapa(V.nombre, V.dimension);
    }
  }
  $("sel-dimension").addEventListener("change", (e) => enviar({ cmd: "dimension", d: +e.target.value }));

  function marcarConexion() {
    $("conexion").textContent = V.conectado ? "● en vivo" : "○ sin conexión";
    $("conexion").style.color = V.conectado ? "var(--ok)" : "var(--mal)";
  }

  function recibir(m) {
    switch (m.tipo) {
      case "hola":
        V.velocidades = m.velocidades; V.velocidad = m.velocidad;
        $("cerebro-txt").textContent = "Cerebro: " + m.cerebro;
        V.ajustes = m.ajustes; V.modulosDesc = m.modulos_desc; V.faunaCat = m.fauna_cat || []; armarModulos();
        armarVelocidades(); armarDimensiones(m.dimensiones, m.dimension); aplicarEstado(m.estado); break;
      case "estado":
        if (m.dimensiones && m.dimensiones.length > 1) armarDimensiones(m.dimensiones, m.dimension);
        V.velocidad = m.velocidad; V.velocidadReal = m.velocidad_real; aplicarEstado(m); marcarVelocidad(); estadoCerebro(m.cerebro); break;
      case "velocidad": V.velocidad = m.velocidad; marcarVelocidad(); break;
      case "rayo": V.efectos.push({ tipo: "rayo", x: m.x, y: m.y, t0: performance.now() }); break;
      case "derrumbe": V.efectos.push({ tipo: "derrumbe", camino: m.camino, t0: performance.now() }); break;
      case "habla": V.efectos.push({ tipo: "habla", id: m.id, texto: m.texto, t0: performance.now() }); break;
      case "ajustes": V.ajustes = m.ajustes; armarModulos(); break;
      case "spawn":
        V.efectos.push({ tipo: "rayo", x: m.x, y: m.y, t0: performance.now() });
        elegir(m.id);
        break;
      case "eventos": for (const e of m.eventos) agregarEvento(e); break;
      case "error": $("estado").textContent = m.texto || "Error"; setTimeout(() => ($("estado").textContent = ""), 3000); break;
    }
    if (V.pedirRender) V.pedirRender();   // el mundo cambió: redibujar bajo demanda
  }

  function aplicarEstado(e) {
    // El mensaje de cada 100 ms es liviano; el bloque pesado (fuego, estructuras, colonias,
    // barras finas) llega una vez por segundo. Se MERGEA, nunca se reemplaza: lo que no vino
    // en este mensaje sigue siendo válido.
    const est = V.estado || (V.estado = {});
    Object.assign(est, e);
    V.luz = e.luz;
    pintarReloj(e);
    const vistos = new Set();
    for (const h of e.habitantes) {
      vistos.add(h.id);
      const o = V.habs[h.id];
      if (!o) V.habs[h.id] = { x: h.x, y: h.y, d: { ...h } };
      else { o.d = Object.assign(o.d, h); if (Math.hypot(o.x - h.x, o.y - h.y) > 30) { o.x = h.x; o.y = h.y; } }
    }
    for (const id of Object.keys(V.habs)) if (!vistos.has(+id)) delete V.habs[id];
    if (e.vitales) for (const [id, salud, sed, energia, hambre, temp, frio] of e.vitales) {
      const o = V.habs[id];
      if (o) Object.assign(o.d, { salud, sed, energia, hambre, temp, frio });
    }
    if (Date.now() - V.fichaT > 2000) { V.fichaT = Date.now(); listaHabitantes(); }
    // Nieve y ceniza continuas desactivadas del loop activo para eliminar tirones de 4 MB en hilo principal
  }

  function pintarReloj(e) {
    const f = e.fecha || {}, h = f.hora || 0, m = f.minuto || 0;
    $("r-dia").textContent = "Día " + (f.dia || 1);
    $("r-hora").textContent = dosDig(h) + ":" + dosDig(m);
    $("r-sub").textContent = (ESTACION_ICONO[f.estacion] || "") + " " + (f.estacion ? f.estacion[0].toUpperCase() + f.estacion.slice(1) : "") + " · Año " + (f.anio || 1) +
      (f.dia_del_anio ? " · día " + f.dia_del_anio + " de 120" : "") + (e.temp_media != null ? " · " + Math.round(e.temp_media) + " °C" : "");
    // el sol recorre un semicírculo entre las 6 y las 20; de noche aparece la luna abajo
    const sol = $("dial-sol"), hh = h + m / 60, dia = hh >= 6 && hh <= 20;
    const ang = dia ? Math.PI * (1 - (hh - 6) / 14) : -Math.PI * (((hh + 24 - 20) % 24) / 10);
    sol.setAttribute("cx", (32 + 22 * Math.cos(ang)).toFixed(1));
    sol.setAttribute("cy", (32 - 22 * Math.sin(ang)).toFixed(1));
    sol.setAttribute("fill", dia ? "#f0b35a" : "#cfd8e6");
    sol.setAttribute("r", dia ? "5" : "4");
    $("dial-cielo").setAttribute("fill-opacity", (0.08 + 0.4 * e.luz).toFixed(2));
  }

  function armarModulos() {
    const cont = $("modulos"); if (!V.ajustes || !V.modulosDesc) return;
    if (cont.dataset.listo !== "1") {
      cont.innerHTML = Object.entries(V.modulosDesc).map(([k, d]) =>
        "<label class='modulo'><input type='checkbox' data-m='" + k + "'><span>" + esc(d) + "</span></label>").join("");
      cont.querySelectorAll("input").forEach((i) => i.addEventListener("change", () =>
        enviar({ cmd: "ajustes", cambios: { modulos: { [i.dataset.m]: i.checked } } })));
      cont.dataset.listo = "1";
    }
    cont.querySelectorAll("input").forEach((i) => { i.checked = !!V.ajustes.modulos[i.dataset.m]; });
    if (document.activeElement !== $("in-modelo")) $("in-modelo").value = V.ajustes.modelo || "";
    if (document.activeElement !== $("in-modelo-emb")) $("in-modelo-emb").value = V.ajustes.modelo_embeddings || "";
    const tope = String(Math.round(V.ajustes.velocidad_max_pensando || 0)), st = $("sel-tope");
    if (![...st.options].some((o) => o.value === tope)) st.add(new Option(tope + "×", tope));
    st.value = tope; $("sel-paralelo").value = String(V.ajustes.paralelo || 1);
  }
  function estadoCerebro(c) {
    if (!c) return;
    V.pensando = c.llm_activo ? c.pensando : 0;
    $("cerebro-estado").textContent = !c.llm_activo ? "Modelo de lenguaje apagado: caminan con reglas simples."
      : !c.llm_disponible ? "⚠ No se pudo usar el modelo (" + (c.ultimo_error || "sin respuesta") + "). Siguen con reglas simples y reintenta solo."
      : "Modelo " + c.modelo + " · pensando: " + c.pensando + (c.tope != null ? " · tope " + Math.round(c.tope) + "×" : "") + (c.latencia_s != null ? " · última respuesta " + c.latencia_s + " s" : "") + " · decisiones: " + c.decisiones_llm + " (rechazadas: " + c.rechazos_llm + ")" + significado(c.semantica);
  }
  function significado(s) {
    if (!s || !s.activa) return "";
    if (s.error) return " · significado: ⚠ " + s.error;
    return " · significado: " + s.guardados + " recuerdos (" + s.por_significado + " usados contra " + s.por_palabras + " por palabras)";
  }
  $("sel-tope").addEventListener("change", (e) => enviar({ cmd: "ajustes", cambios: { velocidad_max_pensando: +e.target.value } }));
  $("sel-paralelo").addEventListener("change", (e) => enviar({ cmd: "ajustes", cambios: { paralelo: +e.target.value } }));
  $("btn-modelo").addEventListener("click", () => { const v = $("in-modelo").value.trim(); if (v) enviar({ cmd: "ajustes", cambios: { modelo: v } }); });
  $("btn-modelo-emb").addEventListener("click", () => { const v = $("in-modelo-emb").value.trim(); if (v) enviar({ cmd: "ajustes", cambios: { modelo_embeddings: v } }); });

  function enviar(o) { if (V.ws && V.ws.readyState === 1) V.ws.send(JSON.stringify(o)); }

  // ------------------------------------------------------------ interfaz
  function armarVelocidades() {
    const cont = $("velocidades"); cont.innerHTML = "";
    for (const v of V.velocidades) {
      const b = document.createElement("button");
      b.dataset.v = v; b.textContent = v === 0 ? "⏸" : v === 1 ? "1×" : v + "×";
      b.title = v === 0 ? "Pausa" : v + " minutos del mundo por segundo real";
      b.addEventListener("click", () => enviar({ cmd: "velocidad", v: v }));
      cont.appendChild(b);
    }
    marcarVelocidad();
  }
  function marcarVelocidad() {
    document.querySelectorAll("#velocidades button").forEach((b) => b.classList.toggle("primario", +b.dataset.v === V.velocidad));
    const lento = V.velocidad > 0 && V.velocidadReal < V.velocidad * 0.8;
    $("vel-real").textContent = V.velocidad === 0 ? "en pausa" : lento
      ? (V.pensando > 0 ? "esperando al modelo (va a ~" + Math.round(V.velocidadReal) + "×)" : "el motor llega a ~" + Math.round(V.velocidadReal) + "×") : "";
  }

  function listaHabitantes() {
    const e = V.estado; if (!e) return;
    const cont = $("habitantes");
    if (!cont._ids) { cont.innerHTML = ""; cont._ids = {}; }
    const vivos = e.habitantes.filter((h) => h.vivo).length;
    $("tab-n-gente").textContent = vivos + "/" + e.habitantes.length;
    // contadores en las otras pestañas: sin esto hay que entrar a cada una para saber si pasó algo
    const nAl = (e.aldeas || []).length;
    $("tab-n-familias").textContent = nAl ? String(nAl) : "";
    const nFa = (e.fauna || []).length;
    $("tab-n-animales").textContent = nFa ? String(nFa) : "";
    const barra = (v, c) => "<div class='barra-mini'><i style='width:" + Math.max(0, Math.min(100, v)) + "%;background:" + c + "'></i></div>";
    const orden = e.habitantes.slice().sort((a, b) => (b.vivo - a.vivo) || (a.id - b.id));
    const ids = new Set();
    orden.forEach((h, idx) => {
      ids.add(h.id);
      let d = cont._ids[h.id];
      if (!d) {
        d = document.createElement("div"); d.dataset.id = h.id;
        d.innerHTML = "<span class='punto'></span><div class='hab-txt'><b></b><span></span></div><div class='mini'></div>";
        d.addEventListener("click", () => elegir(h.id));
        cont._ids[h.id] = d;
      }
      d.className = "hab" + (V.sel === h.id ? " sel" : "") + (h.vivo ? "" : " muerto");
      d.children[0].style.background = COLORES[h.color % COLORES.length];
      d.children[1].children[0].textContent = h.nombre;
      d.children[1].children[1].textContent = h.vivo ? accionTxt(h) + (h.nac != null && e.t_min != null ? " · " + edadTexto((e.t_min - h.nac) / 1440, true) : "") : "murió";
      const vd = (V.habs[h.id] && V.habs[h.id].d) || h;   // las barras viven en el bloque mergeado, no en el mensaje liviano
      const mini = h.vivo ? barra(vd.salud ?? 0, "var(--ok)") + barra(100 - (vd.sed ?? 0), "var(--agua)") + barra(vd.energia ?? 0, "var(--acento)") : "";
      if (d.children[2]._h !== mini) { d.children[2].innerHTML = mini; d.children[2]._h = mini; }
      if (cont.children[idx] !== d) cont.insertBefore(d, cont.children[idx] || null);
    });
    for (const k of Object.keys(cont._ids)) if (!ids.has(+k)) { cont._ids[k].remove(); delete cont._ids[k]; }
  }
  function nombreDe(id) { const h = V.habs[id]; return h ? h.d.nombre : "#" + id; }
  function accionTxt(h) {
    if (h.en_fuego) return "¡se quema!";
    if (h.detalle) return h.detalle;
    return { libre: "libre", caminando: "camina", durmiendo: "duerme", bebiendo: "bebe", esperando: "espera" }[h.accion] || h.accion;
  }

  function aviso(e) {
    const caja = $("avisos"); if (!caja) return;
    const hito = e.tipo === "hito", d = document.createElement("div");
    d.className = "aviso" + (hito ? " hito" : "");
    d.innerHTML = "<b>" + (hito ? "Nueva etapa" : e.tipo === "muerte" ? "Murió alguien" : "Importante") + "</b><span>" + esc(String(e.texto).replace(/^🌅 Nueva etapa: /, "")) + "</span>";
    d.addEventListener("click", () => { if (e.habitante_id != null) centrarEn(e.habitante_id); d.remove(); });
    caja.appendChild(d);
    while (caja.children.length > 4) caja.removeChild(caja.firstChild);
    setTimeout(() => d.classList.add("sale"), hito ? 9000 : 6000);
    setTimeout(() => d.remove(), hito ? 9600 : 6600);
  }
  function centrarEn(id) {
    const o = V.habs[id], b = base(); if (!o || !b) return;
    const v = b.estado.vista, caja = $("lienzo").parentElement;
    v.x = o.x - caja.clientWidth / v.z / 2; v.y = o.y - caja.clientHeight / v.z / 2;
    elegir(id);
  }
  function agregarEvento(e) {
    if ((e.importancia || 1) >= 4 || e.tipo === "hito") aviso(e);

    // Feed flotante sobre el mapa
    const ff = $("feed-flotante");
    if (ff && (e.importancia || 1) >= 3) {
      const item = document.createElement("div");
      item.className = "feed-item imp-" + (e.importancia || 1);
      const t = e.t_min, m = Math.floor(t % 1440);
      item.innerHTML = "<span class='h'>D" + (Math.floor(t / 1440) + 1) + " " + dosDig(Math.floor(m / 60)) + ":" + dosDig(m % 60) + "</span><span>" + esc(e.texto) + "</span>";
      item.addEventListener("click", () => { if (e.habitante_id != null) centrarEn(e.habitante_id); });
      ff.insertBefore(item, ff.firstChild);
      while (ff.children.length > 5) ff.removeChild(ff.lastChild);
      setTimeout(() => item.remove(), 12000);
    }

    if ((e.importancia || 1) < 2) return;   // lo trivial queda en la página de Eventos
    const d = document.createElement("div");
    d.className = "ev imp-" + (e.importancia || 1);
    const t = e.t_min, m = Math.floor(t % 1440);
    d.innerHTML = "<span class='h'>D" + (Math.floor(t / 1440) + 1) + " " + dosDig(Math.floor(m / 60)) + ":" + dosDig(m % 60) + "</span><span>" + esc(e.texto) + "</span>";
    const f = $("feed"); f.insertBefore(d, f.firstChild);
    while (f.children.length > 40) f.removeChild(f.lastChild);
  }

  async function elegir(id) {
    V.sel = id; listaHabitantes();
    $("ficha-cab").classList.add("visible");
    if (V.pedirRender) V.pedirRender();   // anillo de selección en el lienzo
    await refrescarFicha();
  }
  async function refrescarFicha() {
    if (V.sel == null || !V.nombre || document.hidden) return;
    // Se captura el pedido: si al volver cambió el habitante, el mundo o la dimensión,
    // esta respuesta es vieja y no debe tocar la ficha. El token además deja que una
    // selección nueva no quede bloqueada por una petición anterior en vuelo.
    const nombre = V.nombre, id = V.sel, dim = V.dimension || 0;
    const seq = (V.fichaSeq = (V.fichaSeq || 0) + 1);
    try {
      const r = await fetch("/api/mundos/" + nombre + "/habitantes/" + id);
      if (!r.ok) return;
      const f = await r.json();
      if (seq !== V.fichaSeq || nombre !== V.nombre || id !== V.sel || dim !== (V.dimension || 0)) return;
      const vivo = !!f.vivo, hb = V.habs[id];
      // cabecera fija: se actualiza en el lugar, no se reconstruye
      $("fc-punto").style.background = hb ? COLORES[hb.d.color % COLORES.length] : "var(--suave)";
      $("fc-nombre").textContent = f.nombre + (vivo ? "" : " ✝");
      $("fc-emo").textContent = vivo && f.emocion ? f.emocion : "";
      $("fc-sub").textContent = [edadTexto(f.edad_dias), f.sexo === "F" ? "Mujer" : f.sexo === "M" ? "Hombre" : "",
        f.madre_id ? "hij" + (f.sexo === "F" ? "a" : "o") + " de " + nombreDe(f.madre_id) + (f.padre_id ? " y " + nombreDe(f.padre_id) : "") : "fundador",
        f.temperamento || ""].filter(Boolean).join(" · ");
      $("fc-acc").textContent = f.causa_muerte ? "Murió por: " + f.causa_muerte : hb ? accionTxt(hb.d) + (hb.d.temp != null ? " · " + Math.round(hb.d.temp) + " °C" + (hb.d.frio > 0.3 ? " · pasando frío" : "") : "") : "";
      const set = (id, v) => { $(id).style.width = Math.max(0, Math.min(100, v)) + "%"; };
      if (hb && hb.d.vivo) { set("fc-b-salud", hb.d.salud); set("fc-b-agua", 100 - hb.d.sed); set("fc-b-energia", hb.d.energia);
        set("fc-b-comida", hb.d.hambre == null ? 100 : 100 - hb.d.hambre); }

      const vivos = f.rasgos_vivos || {};
      const rasgos = Object.entries(f.rasgos || {}).map(([k, v]) => {
        const a = vivos[k] != null ? vivos[k] : v, cambio = Math.round((a - v) * 100);
        return "<div class='rasgo'><span>" + esc(k) + "</span><div class='afb'><i style='left:0;width:" + Math.round(a * 100) + "%;background:var(--agua)'></i></div></div>" +
          (cambio ? "<div class='nota' style='margin:-2px 0 4px 106px'>heredó " + Math.round(v * 100) + " · hoy " + Math.round(a * 100) + " (" + (cambio > 0 ? "+" : "") + cambio + ")</div>" : "");
      }).join("");
      const hv = (f.habito && f.habito.v) || {}, NOM_H = { explorar: "explorar", acercarse: "buscar compañía", conversar: "conversar", cazar: "cazar", inventar: "probar ideas", agua: "ir al agua", esperar: "quedarse quieto", dormir: "dormir" };
      const habito = Object.keys(hv).length ? "<p class='nota'>Lo que esta persona aprendió por experiencia (" + (f.habito.n || 0) + " experiencias). Verde: le fue bien. Rojo: le fue mal.</p>" +
        Object.entries(hv).sort((a, b) => b[1] - a[1]).map(([k, v]) => "<div class='rasgo'><span>" + esc(NOM_H[k] || k) + "</span><div class='afb centro'><i style='background:" + (v >= 0 ? "var(--ok)" : "var(--mal)") +
          ";left:" + (v >= 0 ? 50 : 50 + v * 50) + "%;width:" + Math.min(50, Math.abs(v) * 50) + "%'></i></div></div>").join("") : "<p class='nota'>Todavía no tuvo experiencias para aprender.</p>";
      const afecto = (v) => { const c = v >= 0 ? "var(--ok)" : "var(--mal)", w = Math.min(50, Math.abs(v) * 50);
        return "<div class='afb centro'><i style='background:" + c + ";left:" + (v >= 0 ? 50 : 50 - w) + "%;width:" + w + "%'></i></div>"; };
      const rel = (f.relaciones || []).map((r) => "<div class='rel'><b>" + esc(r.otro) + "</b>" +
        "<div class='fila'><span>afecto</span>" + afecto(r.afecto) + "</div>" +
        "<div class='fila'><span>confianza</span><div class='afb'><i style='left:0;width:" + Math.round(Math.max(0, Math.min(1, r.confianza)) * 100) + "%;background:var(--agua)'></i></div></div>" +
        (r.resumen ? "<span class='suave'>" + esc(r.resumen) + "</span>" : "") + "</div>").join("");
      const li = (arr, f2, vacio) => "<ul class='lista'>" + (arr.map(f2).join("") || "<li class='vacia'>" + vacio + "</li>") + "</ul>";
      const hora = (t) => "<span class='t'>" + textoHora(t) + "</span>";
      const inv = Object.entries(f.inventario || {}).filter(([, n]) => n > 0).map(([k, n]) => n + " de " + esc(k) + (f.inv_t && f.inv_t[k] != null && /^(carne|pescado|huevo)$/.test(k) ? " <span class='suave'>(" + (f.inv_t[k] / 1440).toFixed(1) + " d)</span>" : "")).join(", ");
      const datos = (inv ? "<div>Lleva: " + inv + "</div>" : "") + ((f.conocimientos || []).length ? "<div>Sabe: <b>" + f.conocimientos.map(esc).join(", ") + "</b></div>" : "");
      const pens = f.pensamientos || [], mem = (f.memorias || []).filter((m) => m.tipo !== "creencia"), evs = (f.eventos || []).slice(0, 8);
      const apr = f.aprendizajes || [], plan = f.plan || [];
      const NOM_LUG = { agua: "💧 Agua", peligro: "⚠ Peligro", comida: "🍖 Buena caza", refugio: "🏕 Refugio", hogar: "🏠 Hogar" };
      const lug = Object.entries(f.lugares || {}).filter(([, l]) => l.length).map(([k, l]) => "<div class='rel'><b>" + (NOM_LUG[k] || esc(k)) + "</b>" +
        l.map((p) => "<span class='suave'>(" + Math.round(p[0]) + ", " + Math.round(p[1]) + ")" + (p[3] && k !== "agua" ? " · " + esc(p[3]) : "") + (p[4] > 1 ? " · " + p[4] + " veces" : "") + "</span>").join("") + "</div>").join("");
      poner($("ficha"),
        (datos ? "<div class='ficha-datos'>" + datos + "</div>" : "") +
        (plan.length ? "<div class='ficha-datos'><div>Se propone: <b>" + plan.map(esc).join(" · ") + "</b></div></div>" : "") +
        (vivo ? "<div class='acciones-ficha'>" +
          "<button id='fc-btn-curar' title='Restablecer salud, energía y saciar sed'>✨ Curar milagrosamente</button>" +
          "<button id='fc-btn-romper' title='Desvincular de su familia para destrabar reproducción sin consanguinidad'>💔 Destrabar linaje</button>" +
          "</div>" : "") +
        seccion("f-apr", "Lo que aprendió", apr.length, li(apr, (a) => "<li>" + hora(a.t_min) + esc(a.contenido) + "</li>", "Todavía no reflexionó (lo hace una vez por día)."), true) +
        seccion("f-lug", "Lugares que recuerda", null, lug || "<p class='nota'>Ninguno todavía.</p>", false) +
        seccion("f-pens", "Lo que pensó", pens.length, li(pens, (p) => "<li>" + hora(p.t_min) + esc(p.texto) + "</li>", "Todavía nada (modelo apagado o sin respuestas)."), true) +
        seccion("f-rel", "Relaciones", (f.relaciones || []).length, rel || "<p class='nota'>Todavía ninguna.</p>", false) +
        seccion("f-mem", "Recuerdos", mem.length, li(mem, (m) => "<li>" + hora(m.t_min) + esc(m.contenido) + (m.veces > 1 ? " <span class='suave'>(×" + m.veces + ")</span>" : "") + "</li>", "Todavía ninguno."), false) +
        seccion("f-evs", "Últimos sucesos", evs.length, li(evs, (e) => "<li>" + hora(e.t_min) + esc(e.texto) + "</li>", "Nada aún."), false) +
        seccion("f-hab", "Lo que aprendió por experiencia", null, habito, false) +
        seccion("f-car", "Carácter (heredado y actual)", null, rasgos || "<p class='nota'>Sin datos.</p>", false));

      const bCurar = $("fc-btn-curar");
      if (bCurar) bCurar.onclick = () => enviar({ cmd: "curar", id: id });
      const bRomper = $("fc-btn-romper");
      if (bRomper) bRomper.onclick = () => {
        if (confirm("¿Desvincular a " + f.nombre + " de sus padres biológicos para habilitar descendencia sin consanguinidad?")) {
          enviar({ cmd: "romper_lazo", id: id });
          setTimeout(refrescarFicha, 600);
        }
      };
    } catch (e) { /* sin red: se reintenta en el próximo ciclo */ }
  }
  // setInterval(refrescarFicha, 5000);  // Solo se consulta cuando el usuario hace clic o interactua

  // recetas (existentes e inventadas) y animales: se leen de la base cada tanto
  const NOM_PROP = {};  // se muestran tal cual vienen (flota, corta, enciende, teje, construye...)
  let _recetasOcupado = false;
  async function refrescarRecetas() {
    const n = V.nombre;
    if (!n || _recetasOcupado || document.hidden) return;
    _recetasOcupado = true;
    try {
      const [r, fa] = await Promise.all([fetch("/api/mundos/" + n + "/recetas").then((x) => x.json()), fetch("/api/mundos/" + n + "/fauna").then((x) => x.json())]);
      if (n !== V.nombre) return;   // cambió el mundo: esta respuesta es vieja
      const sab = r.existentes.filter((e) => e.descubierta), nuevas = r.existentes.filter((e) => !e.descubierta);
      const nSabe = r.inventadas.length + sab.length;        // lo que esta gente sabe hacer, en la pestaña
      $("tab-n-recetas").textContent = nSabe ? String(nSabe) : "";
      const formula = (e) => "<div class='formula'>" + e.ingredientes.map((i) => "<span class='chip'>" + esc(i) + "</span>").join("+") + "→<span class='chip prop'>" + esc(NOM_PROP[e.propiedad] || e.propiedad) + "</span></div>";
      const quien = (e) => e.por ? "<div class='quien'>" + esc(e.por) + " · " + textoHora(e.t_min) + " · la saben " + e.saben + "</div>" : "";
      const tarj = (e, cls) => "<div class='receta" + (cls ? " " + cls : "") + "'><b>" + esc(e.nombre) + "</b>" + formula(e) + quien(e) + "</div>";
      poner($("recetas"),
        "<p class='nota'>Las <b>inventadas</b> son ideas propias que el mundo validó. Las <b>existentes</b> son las del catálogo: si las descubren, se anotan con su nombre.</p>" +
        seccion("r-inv", "Inventadas por ellos", r.inventadas.length, r.inventadas.map((e) => tarj(e)).join("") || "<p class='nota'>Todavía ninguna.</p>", true) +
        seccion("r-sab", "Existentes descubiertas", sab.length + "/" + r.existentes.length, sab.map((e) => tarj(e)).join("") || "<p class='nota'>Todavía ninguna.</p>", true) +
        seccion("r-pend", "Existentes sin descubrir", nuevas.length, nuevas.map((e) => tarj(e, "pendiente")).join(""), false) +
        "<p class='nota'>Se pueden agregar más en <code>datos/extra/recetas/*.json</code>.</p>");
      const por = {};
      for (const e of fa.especies) (por[e.medio] = por[e.medio] || []).push(e);
      const tit = { tierra: "Tierra", agua: "Agua", aire: "Aire" };
      const muertes = Object.entries(fa.muertes || {});
      poner($("fauna-lista"),
        "<div class='resumen-fauna'><div><strong>" + fa.total + "</strong>animales vivos</div>" +
        (muertes.length ? "<div><strong>" + muertes.reduce((a, [, v]) => a + v, 0) + "</strong>muertes (" + muertes.map(([k, v]) => esc(k) + " " + v).join(", ") + ")</div>" : "") + "</div>" +
        Object.entries(por).map(([m, l]) => seccion("a-" + m, tit[m] || m, l.reduce((a, e) => a + e.n, 0),
          "<div>" + (l.filter((e) => e.n > 0).map((e) => "<span class='bicho" + (e.peligro >= 5 ? " peligro" : "") + "' title='" + esc(e.clase + ", " + e.dieta + (e.edad_media != null ? " · edad media " + e.edad_media + " d de ~" + e.vida_dias : "")) + "'>" + e.emoji + " " + esc(e.nombre) + " <b>" + e.n + "</b></span>").join("") || "<span class='nota'>Ninguno por ahora.</span>") + "</div>", true)).join(""));
    } catch (e) { /* sin red */ }
    finally { _recetasOcupado = false; }
  }
  // Refrescar recetas solo al cargar y cada 45s si la pestaña está activa
  setInterval(() => {
    if (document.querySelector("#p-recetas.visible")) refrescarRecetas();
  }, 30000);
  setTimeout(refrescarRecetas, 2000);

  async function actualizarEra() {
    const n = V.nombre;
    if (!n) return;
    try {
      const r = await (await fetch("/api/mundos/" + n + "/era")).json();
      if (n !== V.nombre) return;   // cambió el mundo: no actualizar la era vieja
      $("era-barra").style.display = "block";
      $("era-nombre").textContent = "Era: " + r.era;
      $("era-fill").style.width = Math.round(r.progreso * 100) + "%";
      $("era-detalle").textContent = r.propiedades_descubiertas + " de " + r.propiedades_total + " propiedades descubiertas";
    } catch (e) {}
  }
  setInterval(actualizarEra, 60000);
  setTimeout(actualizarEra, 3000);

  function desactivarPoderes() {
    V.herramientaPoder = null;
    V.herramientaFuego = false;
    V.spawnPendiente = null;
    document.querySelectorAll(".btn-poder").forEach((b) => b.classList.remove("activo"));
    const bf = $("btn-fuego"); if (bf) bf.classList.remove("primario");
    $("lienzo").style.cursor = "";
  }

  function activarPoder(nombre) {
    if (V.herramientaPoder === nombre) {
      desactivarPoderes();
      return;
    }
    desactivarPoderes();
    V.herramientaPoder = nombre;
    if (nombre === "fuego") V.herramientaFuego = true;
    const btn = $(
      nombre === "spawn" ? "btn-dock-spawn" :
      nombre === "fuego" ? "btn-dock-fuego" :
      nombre === "curar" ? "btn-dock-curar" :
      nombre === "infectar" ? "btn-dock-infectar" : null
    );
    if (btn) btn.classList.add("activo");
    const bf = $("btn-fuego");
    if (bf && nombre === "fuego") bf.classList.add("primario");
    $("lienzo").style.cursor = "crosshair";
  }

  // Eventos de dock de observador
  const bDSpawn = $("btn-dock-spawn");
  if (bDSpawn) bDSpawn.onclick = () => {
    $("modal-spawn").classList.add("visible");
  };
  const bDFuego = $("btn-dock-fuego");
  if (bDFuego) bDFuego.onclick = () => activarPoder("fuego");
  const bDCurar = $("btn-dock-curar");
  if (bDCurar) bDCurar.onclick = () => activarPoder("curar");
  const bDInfectar = $("btn-dock-infectar");
  if (bDInfectar) bDInfectar.onclick = () => activarPoder("infectar");

  // Modal spawn
  const bSpCancelar = $("sp-cancelar");
  if (bSpCancelar) bSpCancelar.onclick = () => {
    $("modal-spawn").classList.remove("visible");
  };
  const bSpConfirmar = $("sp-confirmar");
  if (bSpConfirmar) bSpConfirmar.onclick = () => {
    const nom = $("sp-nombre").value.trim();
    const sex = $("sp-sexo").value;
    $("modal-spawn").classList.remove("visible");
    activarPoder("spawn");
    V.spawnPendiente = { nombre: nom, sexo: sex === "azar" ? null : sex };
  };

  const btnFuegoLegacy = $("btn-fuego");
  if (btnFuegoLegacy) {
    btnFuegoLegacy.addEventListener("click", () => {
      activarPoder("fuego");
    });
  }
  // pestañas: se recuerda la elegida
  // ---- familias y aldeas
  async function pintarFamilias() {
    const n = V.nombre;
    if (!n) return;
    let f; try { const r = await fetch("/api/mundos/" + n + "/familias"); if (!r.ok) return; f = await r.json(); } catch (e) { return; }
    if (n !== V.nombre) return;   // cambió el mundo: no pintar el árbol viejo
    const P = {}; f.personas.forEach((p) => { P[p.id] = p; p.hijos = []; p.pareja = []; });
    f.personas.forEach((p) => { for (const q of [p.madre_id, p.padre_id]) if (q && P[q] && !P[q].hijos.includes(p)) P[q].hijos.push(p); });
    f.uniones.forEach(([a, b]) => { if (P[a] && P[b]) { P[a].pareja.push(P[b]); P[b].pareja.push(P[a]); } });
    const hecho = new Set();
    const tarj = (p) => "<span class='pers" + (p.vivo ? "" : " muerto") + "' data-id='" + p.id + "'><i class='punto' style='background:" + (V.habs[p.id] ? COLORES[V.habs[p.id].d.color % COLORES.length] : "var(--suave)") + "'></i>" +
      esc(p.nombre) + " <small>" + (p.sexo === "F" ? "♀" : p.sexo === "M" ? "♂" : "") + " " + edadTexto(p.edad_dias, true) + "</small></span>";
    function nodo(p) {
      hecho.add(p.id);
      const par = p.pareja.find((q) => !hecho.has(q.id)); if (par) hecho.add(par.id);
      const hijos = [...new Set([...p.hijos, ...(par ? par.hijos : [])])].filter((h) => !hecho.has(h.id));
      hijos.forEach((h) => hecho.add(h.id));   // reserva para no repetir
      hijos.forEach((h) => hecho.delete(h.id));
      let html = "<li><div class='pareja'>" + tarj(p) + (par ? "<span class='union'>♥</span>" + tarj(par) : "") + "</div>";
      const sub = hijos.filter((h) => !hecho.has(h.id)).map(nodo).join("");
      return html + (sub ? "<ul>" + sub + "</ul>" : "") + "</li>";
    }
    const raices = f.personas.filter((p) => !(p.madre_id && P[p.madre_id]) && !(p.padre_id && P[p.padre_id]));
    let html = ""; for (const p of raices) if (!hecho.has(p.id)) html += nodo(p);
    for (const p of f.personas) if (!hecho.has(p.id)) html += nodo(p);
    const ar = $("arbol"); ar.innerHTML = html ? "<ul>" + html + "</ul>" : "<p class='nota'>Todavía no hay familias.</p>";
    ar.querySelectorAll(".pers").forEach((el) => el.addEventListener("click", () => { if (V.habs[+el.dataset.id]) centrarEn(+el.dataset.id); else elegir(+el.dataset.id); }));
    // aldeas: las que calcula el motor. Una aldea necesita CASAS (2 refugios o más), no gente parada junta.
    const e = V.estado || {};
    const aldeas = e.aldeas || [];
    const enAldea = new Set();
    let al = aldeas.map((a) => {
      a.gente.forEach((p) => enAldea.add(p.id));
      const fog = (e.fogatas || []).filter((q) => Math.hypot(q[0] - a.x, q[1] - a.y) <= a.r).length;
      return "<div class='aldea' data-x='" + a.x + "' data-y='" + a.y + "'><b>" + esc(a.nombre) + "</b>" +
        "<span class='cifras'>🏠 " + a.casas + (fog ? " · 🔥 " + fog : "") + "</span>" +
        "<span class='sub'>" + (a.gente.length ? esc(a.gente.map((p) => p.nombre).join(", ")) : "nadie ahora") + "</span>" +
        "<span class='sub pie'>" + a.familias + " familia" + (a.familias === 1 ? "" : "s") + " · " +
        a.gente.length + " persona" + (a.gente.length === 1 ? "" : "s") + "</span></div>";
    }).join("");
    if (!al) al = "<p class='nota'>Todavía no hay aldeas. Hace falta que construyan dos chozas cerca una de la otra.</p>";
    // los que andan juntos pero sin casas todavía no son una aldea: van aparte, para no perder la información
    const sueltos = Object.values(V.habs).filter((o) => o.d.vivo && !enAldea.has(o.d.id));
    if (sueltos.length) {
      const g = sueltos.map((o) => o.d.nombre).join(", ");
      const cx = sueltos.reduce((s, o) => s + o.x, 0) / sueltos.length;
      const cy = sueltos.reduce((s, o) => s + o.y, 0) / sueltos.length;
      al += "<div class='aldea' data-x='" + cx + "' data-y='" + cy + "'><b>Sin aldea</b><span>" + sueltos.length +
        " pers.</span><span class='sub'>" + esc(g) + " · duermen a la intemperie</span></div>";
    }
    const ad = $("aldeas"); ad.innerHTML = al;
    ad.querySelectorAll(".aldea").forEach((el) => el.addEventListener("click", () => {
      const b = base(), v = b.estado.vista, caja = $("lienzo").parentElement;
      v.x = +el.dataset.x - caja.clientWidth / v.z / 2; v.y = +el.dataset.y - caja.clientHeight / v.z / 2;
    }));
  }
  setInterval(() => { if (document.querySelector("#p-familias.visible")) pintarFamilias(); }, 4000);
  function pestana(t) {
    document.querySelectorAll("#tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === t ? "true" : "false"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("visible", p.id === "p-" + t));
    try { localStorage.setItem("mv_tab", t); } catch (e) {}
    if (t === "familias") pintarFamilias();
    if (t === "recetas") refrescarRecetas();
  }
  document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => pestana(b.dataset.tab)));
  let tab0 = "gente"; try { tab0 = localStorage.getItem("mv_tab") || "gente"; } catch (e) {}
  pestana(document.querySelector("#tabs [data-tab='" + tab0 + "']") ? tab0 : "gente");
  $("chk-seguir").addEventListener("change", (e) => { V.seguir = e.target.checked; if (V.pedirRender) V.pedirRender(); });
  // Capas que se leen al dibujar la escena (en vivo.js): al alternarlas hay que redibujar.
  ["chk-fauna", "chk-senderos", "chk-chunks"].forEach((id) => {
    const el = $(id); if (el) el.addEventListener("change", () => { if (V.pedirRender) V.pedirRender(); });
  });

  // clic (sin arrastre) sobre el mapa: elegir habitante o prender fuego
  let down = null;
  const lienzo = $("lienzo");
  window.Escena.instalar(V, base, window.Sprites, COLORES, $, lienzo);
  lienzo.addEventListener("pointerdown", (ev) => { down = [ev.clientX, ev.clientY]; });
  lienzo.addEventListener("pointerup", (ev) => {
    if (!down || Math.hypot(ev.clientX - down[0], ev.clientY - down[1]) > 4 || !V.estado) { down = null; return; }
    down = null;
    const r = lienzo.getBoundingClientRect(), v = base().estado.vista;
    const cx = v.x + (ev.clientX - r.left) / v.z, cy = v.y + (ev.clientY - r.top) / v.z;
    const gx = Math.floor(cx), gy = Math.floor(cy);

    if (V.herramientaPoder === "spawn") {
      const datos = V.spawnPendiente || {};
      enviar({ cmd: "spawn", x: gx, y: gy, sexo: datos.sexo, nombre: datos.nombre });
      V.spawnPendiente = null;
      desactivarPoderes();
      return;
    }
    if (V.herramientaPoder === "fuego" || V.herramientaFuego) {
      enviar({ cmd: "fuego", x: gx, y: gy });
      return;
    }
    if (V.herramientaPoder === "infectar") {
      enviar({ cmd: "infectar", x: gx, y: gy, radio: 8 });
      desactivarPoderes();
      return;
    }
    if (V.herramientaPoder === "curar") {
      // Buscar habitante más cercano para sanar
      let curado = null, mdC = Math.max(2.5, 20 / v.z);
      for (const o of Object.values(V.habs)) {
        const d = Math.hypot(o.x - cx, o.y - cy);
        if (d < mdC) { mdC = d; curado = o.d.id; }
      }
      if (curado != null) {
        enviar({ cmd: "curar", id: curado });
        desactivarPoderes();
      }
      return;
    }

    let mejor = null, md = Math.max(1.5, 12 / v.z);
    for (const o of Object.values(V.habs)) { const d = Math.hypot(o.x - cx, o.y - cy); if (d < md) { md = d; mejor = o.d.id; } }
    if (mejor != null) elegir(mejor);
  });

  // ------------------------------------------------------------- nieve

  // Renderizado bajo demanda: se dibuja cuando hay cambios y se encadena animación
  // continua SOLO mientras haya elementos que la necesiten (fuego, antorchas, efectos,
  // movimiento suavizado, seguir). Un único planificador evita bucles rAF duplicados y
  // suspende cuando la escena está inactiva o la pestaña oculta.
  function dibujarSi() {
    if (V.conectado && base() && base().estado.capas) base().dibujar();
  }
  function seguirActivo() {
    if (!V.seguir || V.sel == null) return false;
    const o = V.habs[V.sel], b = base();
    if (!o || !b) return false;
    const v = b.estado.vista, caja = $("lienzo").parentElement;
    const tx = o.x - caja.clientWidth / v.z / 2, ty = o.y - caja.clientHeight / v.z / 2;
    return Math.abs(v.x - tx) > 0.5 || Math.abs(v.y - ty) > 0.5;
  }
  const plan = window.RaceRender.crearPlanificador(
    (cb) => requestAnimationFrame(cb), dibujarSi,
    () => window.RaceRender.necesitaAnimacion(V.estado, V.habs, V.efectos, seguirActivo()));
  V.pedirRender = () => plan.pedir();
  document.addEventListener("visibilitychange", () => plan.setVisible(!document.hidden));
  plan.pedir();                                            // primer dibujo
  window.addEventListener("beforeunload", desconectar);
})();

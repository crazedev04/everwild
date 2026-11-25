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
  window.MV = V;

  const base = () => window.MVBase;
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
  const DETALLE = {
    4:  { forma: "mata",   color: "rgba(176,166,96,0.40)",  densidad: 0.34, tam: 0.26 },  // sabana
    5:  { forma: "mata",   color: "rgba(120,160,86,0.40)",  densidad: 0.38, tam: 0.24 },  // pradera
    6:  { forma: "arbol",  color: "rgba(64,112,62,0.8)",    densidad: 0.20, tam: 0.5 },   // bosque templado
    7:  { forma: "arbol",  color: "rgba(46,104,52,0.85)",   densidad: 0.28, tam: 0.58 },  // selva
    8:  { forma: "mata",   color: "rgba(104,128,88,0.38)",  densidad: 0.26, tam: 0.26 },  // pantano
    9:  { forma: "arbol",  color: "rgba(58,92,74,0.8)",     densidad: 0.20, tam: 0.48 },  // bosque frío
    10: { forma: "mata",   color: "rgba(140,146,120,0.34)", densidad: 0.16, tam: 0.2 },   // tundra
    12: { forma: "piedra", color: "rgba(146,146,152,0.5)",  densidad: 0.20, tam: 0.3 },   // montaña
    13: { forma: "piedra", color: "rgba(92,78,74,0.55)",    densidad: 0.22, tam: 0.3 },   // volcán
    2:  { forma: "piedra", color: "rgba(214,198,156,0.35)", densidad: 0.10, tam: 0.18 },  // playa
    3:  { forma: "piedra", color: "rgba(206,182,132,0.3)",  densidad: 0.08, tam: 0.18 },  // desierto
  };

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
    ws.onmessage = (ev) => { let m; try { m = JSON.parse(ev.data); } catch (e) { return; } recibir(m); };
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
      if (window.MV_abrirMapa) window.MV_abrirMapa(V.nombre, V.dimension);
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
    if (e.ceniza_v !== V.ceniza.v) pedirCeniza(e.ceniza_v);
    if (e.nieve_v !== V.nieve.v) pedirNieve(e.nieve_v);
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
    await refrescarFicha();
  }
  async function refrescarFicha() {
    if (V.sel == null || !V.nombre) return;
    try {
      const r = await fetch("/api/mundos/" + V.nombre + "/habitantes/" + V.sel);
      if (!r.ok) return;
      const f = await r.json(), vivo = !!f.vivo, hb = V.habs[V.sel];
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
      if (bCurar) bCurar.onclick = () => enviar({ cmd: "curar", id: V.sel });
      const bRomper = $("fc-btn-romper");
      if (bRomper) bRomper.onclick = () => {
        if (confirm("¿Desvincular a " + f.nombre + " de sus padres biológicos para habilitar descendencia sin consanguinidad?")) {
          enviar({ cmd: "romper_lazo", id: V.sel });
          setTimeout(refrescarFicha, 600);
        }
      };
    } catch (e) { /* sin red: se reintenta en el próximo ciclo */ }
  }
  setInterval(refrescarFicha, 5000);

  // recetas (existentes e inventadas) y animales: se leen de la base cada tanto
  const NOM_PROP = {};  // se muestran tal cual vienen (flota, corta, enciende, teje, construye...)
  async function refrescarRecetas() {
    const n = V.nombre;
    if (!n) return;
    try {
      const [r, fa] = await Promise.all([fetch("/api/mundos/" + n + "/recetas").then((x) => x.json()), fetch("/api/mundos/" + n + "/fauna").then((x) => x.json())]);
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
  }
  setInterval(refrescarRecetas, 12000);
  setTimeout(refrescarRecetas, 1500);

  async function actualizarEra() {
    if (!V.nombre) return;
    try {
      const r = await (await fetch("/api/mundos/" + V.nombre + "/era")).json();
      $("era-barra").style.display = "block";
      $("era-nombre").textContent = "Era: " + r.era;
      $("era-fill").style.width = Math.round(r.progreso * 100) + "%";
      $("era-detalle").textContent = r.propiedades_descubiertas + " de " + r.propiedades_total + " propiedades descubiertas";
    } catch (e) {}
  }
  setInterval(actualizarEra, 15000);
  setTimeout(actualizarEra, 2000);

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
    if (!V.nombre) return;
    let f; try { const r = await fetch("/api/mundos/" + V.nombre + "/familias"); if (!r.ok) return; f = await r.json(); } catch (e) { return; }
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
  }
  document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => pestana(b.dataset.tab)));
  let tab0 = "gente"; try { tab0 = localStorage.getItem("mv_tab") || "gente"; } catch (e) {}
  pestana(document.querySelector("#tabs [data-tab='" + tab0 + "']") ? tab0 : "gente");
  $("chk-seguir").addEventListener("change", (e) => { V.seguir = e.target.checked; });

  // clic (sin arrastre) sobre el mapa: elegir habitante o prender fuego
  let down = null;
  const lienzo = $("lienzo");
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
  async function pedirNieve(v) {
    if (document.hidden) return;
    const ahora = Date.now();
    if (ahora - V.nieve.pedido < 15000 || !V.nombre) return;
    V.nieve.pedido = ahora;
    try {
      const r = await fetch("/api/mundos/" + V.nombre + "/dinamico/nieve");
      const ds = new DecompressionStream("deflate");
      const piped = r.body.pipeThrough(ds);
      const datos = new Uint8Array(await new Response(piped).arrayBuffer());
      const { ancho: w, alto: h } = V.meta;
      if (datos.length !== w * h) return;
      const c = V.nieve.canvas || (V.nieve.canvas = document.createElement("canvas"));
      c.width = w; c.height = h;
      const cx = c.getContext("2d"), img = cx.createImageData(w, h);
      const data32 = new Uint32Array(img.data.buffer);
      for (let i = 0; i < datos.length; i++) {
        const q = datos[i];
        if (q > 12) {
          const a = Math.min(215, Math.floor(q * 0.85));
          // Formato Little Endian en typed array 32-bit: (alpha << 24) | (B << 16) | (G << 8) | R
          data32[i] = (a << 24) | (252 << 16) | (246 << 8) | 240;
        }
      }
      cx.putImageData(img, 0, 0);
      V.nieve.v = v;
    } catch (e) {}
  }

  // ------------------------------------------------------------- ceniza
  async function pedirCeniza(v) {
    if (document.hidden) return;
    const ahora = Date.now();
    if (ahora - V.ceniza.pedido < 10000 || !V.nombre) return;
    V.ceniza.pedido = ahora;
    try {
      const r = await fetch("/api/mundos/" + V.nombre + "/dinamico/quemado");
      const ds = new DecompressionStream("deflate");
      const piped = r.body.pipeThrough(ds);
      const datos = new Uint8Array(await new Response(piped).arrayBuffer());
      const { ancho: w, alto: h } = V.meta;
      if (datos.length !== w * h) return;
      const c = V.ceniza.canvas || (V.ceniza.canvas = document.createElement("canvas"));
      c.width = w; c.height = h;
      const cx = c.getContext("2d"), img = cx.createImageData(w, h);
      const data32 = new Uint32Array(img.data.buffer);
      for (let i = 0; i < datos.length; i++) {
        const q = datos[i];
        if (q > 6) {
          const a = Math.min(190, Math.floor(q * 0.75));
          data32[i] = (a << 24) | (24 << 16) | (24 << 8) | 28;
        }
      }
      cx.putImageData(img, 0, 0);
      V.ceniza.v = v;
    } catch (e) {}
  }

  // ------------------------------------------------------------- dibujo
  function ruido(x, y, t) { const n = Math.sin(x * 12.9898 + y * 78.233 + t * 0.9) * 43758.5453; return n - Math.floor(n); }

  V.sobreMapa = function (ctx, s, dpr) {
    if (!V.estado || !V.meta) return;
    const { ancho: w, alto: h } = V.meta, vista = base().estado.vista, z = vista.z;
    const ahora = performance.now();
    // ceniza
    const vis = base().estado.vis || { x0: 0, y0: 0, x1: w, y1: h };     // solo se dibuja lo que está a la vista
    const vw = vis.x1 - vis.x0, vh = vis.y1 - vis.y0;
    if (vw <= 0 || vh <= 0) return;
    const visible = (x, y, m) => x >= vis.x0 - m && x <= vis.x1 + m && y >= vis.y0 - m && y <= vis.y1 + m;
    for (const cv of [V.ceniza.canvas, V.nieve.canvas]) {
      if (cv) { ctx.imageSmoothingEnabled = false; ctx.drawImage(cv, vis.x0, vis.y0, vw, vh, vis.x0, vis.y0, vw, vh); }
    }
    // fuego (llamas que titilan)
    const fuego = V.estado.fuego || [];
    const f4 = Math.floor(ahora / 120);
    // detalle del suelo con zoom alto: matitas, árboles y piedras según el bioma. Solo lo visible, y solo de cerca,
    // así el terreno deja de ser un manchón plano sin costar nada cuando se mira el mundo entero.
    const _cap = base().estado.capas;
    if (z >= 10 && _cap && _cap.bioma) {  // only at close zoom to avoid per-cell draw overhead
      const cb = _cap.bioma, ca = _cap.agua, anchoM = V.meta.ancho;
      const paso = z >= 16 ? 1 : 2;                       // de muy cerca, detalle en cada celda
      for (let cy = vis.y0; cy < vis.y1; cy += paso) {
        for (let cx = vis.x0; cx < vis.x1; cx += paso) {
          const idx = cy * anchoM + cx;
          if (ca[idx]) continue;                          // en el agua no se dibuja nada
          const bio = cb[idx];
          const D = DETALLE[bio];
          if (!D) continue;
          let n = (cx * 1597334677 + cy * 3812015801) | 0;
          n = (n ^ (n >>> 15)) * 2246822519 | 0;
          const u = ((n ^ (n >>> 13)) >>> 0) / 4294967296;
          if (u > D.densidad) continue;
          const px = cx + 0.15 + (((n >>> 7) & 255) / 255) * 0.7;
          const py = cy + 0.15 + (((n >>> 17) & 255) / 255) * 0.7;
          const esc = D.tam * (0.75 + (((n >>> 3) & 15) / 15) * 0.5);
          ctx.fillStyle = D.color;
          if (D.forma === "mata") {                       // tres pastitos
            ctx.strokeStyle = D.color; ctx.lineWidth = esc * 0.22; ctx.lineCap = "round";
            ctx.beginPath();
            ctx.moveTo(px, py); ctx.lineTo(px - esc * 0.3, py - esc);
            ctx.moveTo(px, py); ctx.lineTo(px, py - esc * 1.15);
            ctx.moveTo(px, py); ctx.lineTo(px + esc * 0.3, py - esc);
            ctx.stroke();
          } else if (D.forma === "arbol") {
            ctx.strokeStyle = "rgba(60,42,28,0.85)"; ctx.lineWidth = esc * 0.22; ctx.lineCap = "round";
            ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px, py - esc * 0.8); ctx.stroke();
            ctx.fillStyle = "rgba(0,0,0,0.25)";
            ctx.beginPath(); ctx.ellipse(px, py, esc * 0.5, esc * 0.2, 0, 0, 6.2832); ctx.fill();
            ctx.fillStyle = D.color;
            ctx.beginPath(); ctx.arc(px, py - esc * 1.25, esc * 0.72, 0, 6.2832); ctx.fill();
          } else {                                        // piedra
            ctx.fillStyle = "rgba(0,0,0,0.22)";
            ctx.beginPath(); ctx.ellipse(px, py + esc * 0.18, esc * 0.52, esc * 0.22, 0, 0, 6.2832); ctx.fill();
            ctx.fillStyle = D.color;
            ctx.beginPath(); ctx.ellipse(px, py, esc * 0.48, esc * 0.36, 0, 0, 6.2832); ctx.fill();
          }
        }
      }
    }
    // senderos: huellas de tierra pisada que abren los habitantes
    const chkSenderos = $("chk-senderos");
    if ((!chkSenderos || chkSenderos.checked) && V.estado.senderos && V.estado.senderos.length) {
      ctx.fillStyle = "rgba(182, 148, 102, 0.55)";
      for (const [sx, sy] of V.estado.senderos) {
        if (!visible(sx, sy, 1)) continue;
        ctx.fillRect(sx, sy, 1, 1);
      }
    }
    // chunks activos (debug LOD espacial)
    const chkChunks = $("chk-chunks");
    if (chkChunks && chkChunks.checked && V.estado.chunks_activos) {
      const CHUNK = 64;
      ctx.strokeStyle = "rgba(0, 220, 255, 0.4)";
      ctx.lineWidth = Math.max(0.08, 1.5 / s);
      ctx.fillStyle = "rgba(0, 220, 255, 0.08)";
      for (const [cx, cy] of V.estado.chunks_activos) {
        const x = cx * CHUNK, y = cy * CHUNK;
        if (!visible(x + CHUNK/2, y + CHUNK/2, CHUNK)) continue;
        ctx.fillRect(x, y, CHUNK, CHUNK);
        ctx.strokeRect(x, y, CHUNK, CHUNK);
      }
    }
    // aldeas: el claro de tierra pisada y el nombre, debajo de todo lo demás
    for (const al of V.estado.aldeas || []) {
      if (!visible(al.x, al.y, al.r)) continue;
      const g = ctx.createRadialGradient(al.x, al.y, al.r * 0.25, al.x, al.y, al.r);
      g.addColorStop(0, "rgba(196,164,112,0.26)"); g.addColorStop(1, "rgba(196,164,112,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(al.x, al.y, al.r, 0, 6.2832); ctx.fill();
      ctx.strokeStyle = "rgba(232,206,150,0.34)"; ctx.lineWidth = Math.max(0.04, 1.2 / s);
      ctx.setLineDash([1.6 / 1, 1.2 / 1]); ctx.beginPath(); ctx.arc(al.x, al.y, al.r, 0, 6.2832); ctx.stroke();
      ctx.setLineDash([]);
      if (z >= 2) {
        ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
        const yN = al.y - al.r - 0.5;
        ctx.font = Math.max(0.9, 13 * dpr / s) + "px system-ui, sans-serif";
        ctx.fillStyle = "rgba(0,0,0,0.55)"; ctx.fillText(al.nombre, al.x, yN + 0.12);
        ctx.fillStyle = "rgba(255,232,180,0.92)"; ctx.fillText(al.nombre, al.x, yN);
        if (z >= 4 && al.gente.length) {              // de cerca, quiénes viven ahí
          const q = al.gente.map((p) => p.nombre).join(", ");
          ctx.font = Math.max(0.7, 10 * dpr / s) + "px system-ui, sans-serif";
          ctx.fillStyle = "rgba(0,0,0,0.5)"; ctx.fillText(q, al.x, yN - 1.0 + 0.1);
          ctx.fillStyle = "rgba(226,214,186,0.85)"; ctx.fillText(q, al.x, yN - 1.0);
        }
        ctx.textAlign = "start";
      }
    }
    // refugios y ruinas: chozas, casas de piedra, hornos, fraguas, pilas, dinamos y ruinas
    const esRuina = new Set((V.estado.ruinas || []).map(([rx, ry]) => rx + "," + ry));
    for (const [x, y, tipo] of V.estado.refugios || []) {
      if (!visible(x, y, 2)) continue;
      // los pasos (bocas de caverna, pozos) no son casas: son un agujero oscuro en el suelo
      const paso = tipo.indexOf("boca_") === 0 || tipo.indexOf("pozo_") === 0;
      if (z < 2) {
        ctx.fillStyle = paso ? "#15121a" : (esRuina.has(x + "," + y) ? "#4a453f" : "#c9a36b");
        ctx.fillRect(x - 0.6, y - 0.6, 1.2, 1.2);
        continue;
      }
      if (paso) {
        const up = Math.max(13 / s, 4.0 / ((V.meta && V.meta.tam_celda_m) || 50));
        ctx.fillStyle = "#6b6257";
        ctx.beginPath(); ctx.ellipse(x, y, up * 1.15, up * 0.8, 0, 0, 6.2832); ctx.fill();
        ctx.fillStyle = "#0b0910";
        ctx.beginPath(); ctx.ellipse(x, y, up * 0.85, up * 0.55, 0, 0, 6.2832); ctx.fill();
        continue;
      }
      const u = Math.max(14 / s, 3.0 / ((V.meta && V.meta.tam_celda_m) || 50));
      if (window.Sprites && window.Sprites.estructura) {
        window.Sprites.estructura(ctx, tipo, x, y, u, z, esRuina.has(x + "," + y), ahora);
      }
    }
    // fogatas: leños, brasas, llama que titila y un hilo de humo.
    // El tamaño es FÍSICO (una fogata mide ~1,2 m), con un mínimo en píxeles para que se vea de lejos.
    // Antes era fijo en celdas y a 5 m por celda quedaba una fogata de 13 metros, más grande que una persona.
    const tamCeldaF = (V.meta && V.meta.tam_celda_m) || 50;
    const uF = Math.max(10 / s, 1.2 / tamCeldaF);                                     // "unidad fogata" en celdas
    for (const [x, y, vida] of V.estado.fogatas || []) {
      if (!visible(x, y, 3)) continue;
      const r = ruido(x, y, f4), r2 = ruido(x + 7, y - 3, f4);
      const fuerza = (vida === undefined ? 1 : 0.45 + 0.55 * vida) * uF;              // una fogata que se apaga es más chica
      ctx.lineCap = "round"; ctx.strokeStyle = "rgba(60,40,28,0.95)"; ctx.lineWidth = 0.22 * fuerza;
      ctx.beginPath();                                                                 // leños cruzados
      ctx.moveTo(x - 0.7 * fuerza, y + 0.38 * fuerza); ctx.lineTo(x + 0.7 * fuerza, y + 0.08 * fuerza);
      ctx.moveTo(x - 0.7 * fuerza, y + 0.08 * fuerza); ctx.lineTo(x + 0.7 * fuerza, y + 0.38 * fuerza);
      ctx.stroke();
      const g = ctx.createRadialGradient(x, y, 0, x, y, 2.2 * fuerza);                 // brasas
      g.addColorStop(0, "rgba(255,170,60,0.5)"); g.addColorStop(1, "rgba(255,120,20,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 2.2 * fuerza, 0, 6.2832); ctx.fill();
      const alto = (0.9 + 0.5 * r) * fuerza;                                           // llama
      ctx.beginPath();
      ctx.moveTo(x - 0.4 * fuerza, y + 0.25 * fuerza);
      ctx.quadraticCurveTo(x - 0.48 * fuerza, y - alto * 0.5, x + (r2 - 0.5) * 0.3 * fuerza, y - alto);
      ctx.quadraticCurveTo(x + 0.48 * fuerza, y - alto * 0.5, x + 0.4 * fuerza, y + 0.25 * fuerza);
      ctx.closePath();
      ctx.fillStyle = "rgba(255," + (120 + Math.floor(r * 100)) + ",40,0.95)"; ctx.fill();
      ctx.beginPath(); ctx.arc(x, y - alto * 0.25, 0.24 * fuerza, 0, 6.2832);
      ctx.fillStyle = "rgba(255,246,200,0.9)"; ctx.fill();                              // corazón blanco
      if (z >= 2) {                                                                     // humo
        ctx.strokeStyle = "rgba(190,190,190,0.2)"; ctx.lineWidth = Math.max(0.05, 1.4 / s);
        ctx.beginPath(); ctx.moveTo(x, y - alto);
        for (let i = 1; i <= 4; i++) {
          const t = i / 4;
          ctx.lineTo(x + Math.sin((ahora / 700) + i + x) * (0.5 + t) * fuerza, y - alto - t * 4.0 * fuerza);
        }
        ctx.stroke();
      }
    }
    for (const [x, y, inten] of fuego) {
      if (!visible(x, y, 1)) continue;
      const r = ruido(x, y, f4);
      const g = 60 + Math.floor(r * 140 * (inten / 255 + 0.3));
      ctx.fillStyle = "rgba(255," + g + ",20," + (0.55 + 0.4 * (inten / 255)) + ")";
      ctx.fillRect(x, y, 1, 1);
    }
    // lluvia y tormentas
    for (const t of V.estado.tormentas || []) {
      const [tx, ty, tr, ti, esNieve] = t;
      if (!visible(tx, ty, tr)) continue;
      const g = ctx.createRadialGradient(tx, ty, tr * 0.1, tx, ty, tr);
      g.addColorStop(0, "rgba(40,50,70," + (0.38 * ti) + ")"); g.addColorStop(1, "rgba(40,50,70,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(tx, ty, tr, 0, 6.2832); ctx.fill();
      ctx.strokeStyle = esNieve ? "rgba(255,255,255,0.8)" : "rgba(170,200,255,0.55)"; ctx.lineWidth = Math.max(0.05, 1 / s);
      ctx.beginPath();
      const n = Math.floor(tr * 4 * ti);
      for (let i = 0; i < n; i++) {
        const a = Math.random() * 6.2832, d = tr * Math.sqrt(Math.random()) * 0.95;
        const px = tx + Math.cos(a) * d, py = ty + Math.sin(a) * d;
        ctx.moveTo(px, py); ctx.lineTo(px - 0.25, py + 0.7);
      }
      ctx.stroke();
    }
    // habitantes (suavizados entre mensajes)
    const dtF = Math.min(0.1, (ahora - V.ultimoFrame) / 1000 || 0.016); V.ultimoFrame = ahora;
    const k = 1 - Math.exp(-dtF * 12);
    const tmin = (V.estado && V.estado.t_min) || 0;
    for (const o of Object.values(V.habs)) {
      const px = o.x, py = o.y;
      o.x += (o.d.x - o.x) * k; o.y += (o.d.y - o.y) * k;
      const mdx = o.x - px, mdy = o.y - py, paso = Math.hypot(mdx, mdy);
      o.dir = Sprites.direccion(mdx, mdy, o.dir);
      // el ciclo de caminata avanza con lo que caminó, no con el reloj: así no patina al ir lento
      o.ciclo = ((o.ciclo || 0) + paso / Math.max(0.05, 1.7 / ((V.meta && V.meta.tam_celda_m) || 50))) % 4;
      o.paso = paso < 1e-4 ? 0 : [1, 0, 2, 0][Math.floor(o.ciclo)];
      o.edadDias = o.d.nac != null && tmin ? (tmin - o.d.nac) / 1440 : 0;
    }
    // antorchas: la llamita que lleva en la mano quien se llevó el fuego (después de suavizar, así no queda atrás)
    for (const hb of Object.values(V.habs)) {
      if (!hb.d.vivo || !hb.d.antorcha || !visible(hb.x, hb.y, 2) || z < 2) continue;
      const uA = Math.max(10 / s, 1.7 / ((V.meta && V.meta.tam_celda_m) || 50));   // a la altura de la mano
      const r = ruido(hb.x, hb.y, f4), tx = hb.x + 0.38 * uA, ty = hb.y - 0.62 * uA;
      ctx.strokeStyle = "rgba(90,60,35,0.95)"; ctx.lineWidth = 0.13 * uA; ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(tx - 0.1 * uA, ty + 0.55 * uA); ctx.lineTo(tx, ty + 0.1 * uA); ctx.stroke();
      const g = ctx.createRadialGradient(tx, ty, 0, tx, ty, 1.1 * uA);
      g.addColorStop(0, "rgba(255,180,70,0.55)"); g.addColorStop(1, "rgba(255,140,30,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(tx, ty, 1.1 * uA, 0, 6.2832); ctx.fill();
      ctx.fillStyle = "rgba(255," + (170 + Math.floor(r * 70)) + ",80,0.95)";
      ctx.beginPath(); ctx.ellipse(tx, ty, 0.13 * uA, (0.22 + 0.08 * r) * uA, 0, 0, 6.2832); ctx.fill();
    }
    // noche: capa oscura con "agujeros" de luz en fuegos y personas
    const a = Math.max(0, Math.min(0.8, (1 - V.luz) * 0.85));
    if (a > 0.03) {
      // la capa oscura tiene el tamaño de lo visible, no el del mundo
      if (!V.oscuro) V.oscuro = document.createElement("canvas");
      // nunca 0×0: si el lienzo se está re-acomodando, drawImage con un canvas vacío tira InvalidStateError
      const ow = Math.max(1, Math.floor(vw)), oh = Math.max(1, Math.floor(vh));
      if (V.oscuro.width !== ow || V.oscuro.height !== oh) { V.oscuro.width = ow; V.oscuro.height = oh; }
      const o = V.oscuro.getContext("2d");
      o.globalCompositeOperation = "source-over"; o.clearRect(0, 0, vw, vh);
      o.fillStyle = "rgba(6,10,38," + a + ")"; o.fillRect(0, 0, vw, vh);
      o.globalCompositeOperation = "destination-out";
      const hueco = (x, y, rad, fza) => {      // "agujero" de luz en la capa de noche
        const g2 = o.createRadialGradient(x - vis.x0, y - vis.y0, 0, x - vis.x0, y - vis.y0, rad);
        g2.addColorStop(0, "rgba(0,0,0," + fza + ")"); g2.addColorStop(1, "rgba(0,0,0,0)");
        o.fillStyle = g2; o.fillRect(x - vis.x0 - rad, y - vis.y0 - rad, rad * 2, rad * 2);
      };
      // los radios de luz también en metros, si no a 5 m por celda una fogata alumbraba 45 metros
      const mLuz = (m) => Math.max(5 / s, m / ((V.meta && V.meta.tam_celda_m) || 50));
      const rFog = mLuz(14), rAnt = mLuz(8), rRef = mLuz(5);
      for (const [x, y, vida] of V.estado.fogatas || []) {
        if (!visible(x, y, rFog)) continue;
        const fza = vida === undefined ? 1 : 0.5 + 0.5 * vida;
        hueco(x, y, rFog * fza, 0.85 * fza);   // la fogata es el centro de la noche
      }
      for (const hb of Object.values(V.habs)) {
        if (hb.d.vivo && hb.d.antorcha && visible(hb.x, hb.y, rAnt)) hueco(hb.x, hb.y, rAnt, 0.75);
      }
      for (const [x, y] of V.estado.refugios || []) {
        if (visible(x, y, rRef)) hueco(x, y, rRef, 0.3);   // la puerta tira un poco de luz
      }
      for (const [x, y, inten] of fuego) { if (!visible(x, y, 2)) continue; o.fillStyle = "rgba(0,0,0," + (0.35 + 0.5 * inten / 255) + ")"; o.fillRect(x - 1 - vis.x0, y - 1 - vis.y0, 3, 3); }
      for (const hb of Object.values(V.habs)) {
        if (!hb.d.vivo || !visible(hb.x, hb.y, 5)) continue;
        const hx = hb.x - vis.x0, hy = hb.y - vis.y0;
        const g = o.createRadialGradient(hx, hy, 0, hx, hy, 4);
        g.addColorStop(0, "rgba(0,0,0,0.55)"); g.addColorStop(1, "rgba(0,0,0,0)");
        o.fillStyle = g; o.fillRect(hx - 4, hy - 4, 8, 8);
      }
      ctx.imageSmoothingEnabled = true; ctx.drawImage(V.oscuro, vis.x0, vis.y0, ow, oh);
      // brillo cálido alrededor del fuego
      ctx.globalCompositeOperation = "lighter";
      for (const [x, y, inten] of fuego) { if (!visible(x, y, 2)) continue; ctx.fillStyle = "rgba(255,120,30," + (0.05 * inten / 255) + ")"; ctx.fillRect(x - 1, y - 1, 3, 3); }
      ctx.globalCompositeOperation = "source-over";
    }
    // efectos: rayos y derrumbes
    V.efectos = V.efectos.filter((e) => ahora - e.t0 < (e.tipo === "rayo" ? 500 : e.tipo === "habla" ? Math.min(14000, 6000 + 60 * String(e.texto || "").length) : 1500));
    for (const e of V.efectos) {
      if (e.tipo === "habla") continue;
      const p = (ahora - e.t0) / (e.tipo === "rayo" ? 500 : 1500);
      if (e.tipo === "rayo") {
        ctx.strokeStyle = "rgba(255,255,255," + (1 - p) + ")"; ctx.lineWidth = Math.max(0.12, 2 / s);
        ctx.beginPath(); let px = e.x, py = e.y - 9; ctx.moveTo(px, py);
        for (let i = 1; i <= 6; i++) { px = e.x + (ruido(i, e.x, e.t0) - 0.5) * 1.5 * (6 - i) / 6; py = e.y - 9 + i * 1.5; ctx.lineTo(px, py); }
        ctx.stroke();
        ctx.fillStyle = "rgba(255,255,230," + (0.7 * (1 - p)) + ")"; ctx.beginPath(); ctx.arc(e.x, e.y, 1.6 * (0.5 + p), 0, 6.2832); ctx.fill();
      } else {
        const n = e.camino.length, idx = Math.min(n - 1, Math.floor(p * n));
        ctx.fillStyle = "rgba(120,100,80,0.9)";
        for (let i = Math.max(0, idx - 2); i <= idx; i++) { ctx.beginPath(); ctx.arc(e.camino[i][0], e.camino[i][1], 0.35, 0, 6.2832); ctx.fill(); }
        ctx.fillStyle = "rgba(160,140,120," + (0.5 * (1 - p)) + ")";
        for (const c of e.camino.slice(0, idx + 1)) ctx.fillRect(c[0] - 0.3, c[1] - 0.3, 0.6, 0.6);
      }
    }
    // animales: cada uno con la forma de su clase y el largo que le da su peso real
    if ($("chk-fauna").checked && V.estado && V.estado.fauna && V.faunaCat) {
      const col = { tierra: "#c98b4e", agua: "#4fd1e8", aire: "#f5f5f5" };
      const tamC = (V.meta && V.meta.tam_celda_m) || 50;
      if (!V.animPrev) V.animPrev = {};
      const prev = V.animPrev, ahoraA = {};
      for (const g of V.estado.fauna) {
        const [i, x, y] = g;
        const c = V.faunaCat[i];
        if (!c) continue;
        const clave = i + ":" + Math.round(x * 4) + ":" + Math.round(y * 4);
        ahoraA[clave] = [x, y];
        if (!visible(x, y, 2)) continue;
        if (z < 4) {   // de lejos, un puntito por medio: dibujar formas no se vería y cuesta
          ctx.fillStyle = col[c.medio] || "#ccc"; ctx.globalAlpha = 0.85;
          ctx.fillRect(x - 0.4, y - 0.4, 0.8, 0.8); ctx.globalAlpha = 1;
          continue;
        }
        const largo = Math.max(9 / s, Sprites.largoM(c.peso_kg) / tamC);
        const img = Sprites.animal(c.clase, (c.peligro || 0) >= 4);
        const p = prev[i];
        const ang = p ? Math.atan2(y - p[1], x - p[0]) : 0;      // mira hacia donde se mueve
        ctx.save();
        ctx.translate(x, y);
        if (p && (Math.abs(x - p[0]) > 1e-4 || Math.abs(y - p[1]) > 1e-4)) ctx.rotate(ang);
        ctx.fillStyle = "rgba(0,0,0,0.3)";
        ctx.beginPath(); ctx.ellipse(0, largo * 0.18, largo * 0.34, largo * 0.14, 0, 0, 6.2832); ctx.fill();
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(img, -largo / 2, -largo / 2, largo, largo);
        ctx.restore();
      }
      // posición anterior de cada especie-instancia, para saber hacia dónde apunta
      for (const g of V.estado.fauna) prev[g[0]] = [g[1], g[2]];
      if (z >= 9) {   // de muy cerca, además el emoji chiquito para reconocerlo
        ctx.font = Math.max(0.6, 9 * dpr / s) + "px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
        for (const [i, x, y] of V.estado.fauna) {
          const c = V.faunaCat[i];
          if (!c || !visible(x, y, 2)) continue;
          const largo = Math.max(9 / s, Sprites.largoM(c.peso_kg) / tamC);
          ctx.fillText(c.emoji, x, y - largo * 0.75);
        }
        ctx.textAlign = "start"; ctx.textBaseline = "alphabetic";
      }
    }
    // personas (encima de todo para que se vean de noche)
    // Tamaño: el real de una persona (~1,7 m) pero nunca menos de 18 px en pantalla, así se la ve igual de lejos.
    const tamCelda = (V.meta && V.meta.tam_celda_m) || 50;
    const altoP = Math.max(18 / s, 1.7 / tamCelda);
    const r = Math.max(0.45, altoP * 0.42), tam = (12 * dpr) / s;
    for (const o of Object.values(V.habs)) {
      const d = o.d, col = COLORES[d.color % COLORES.length];
      if (!visible(o.x, o.y, 8) && V.sel !== d.id) continue;
      const hh = altoP * (Sprites.EDADES[Sprites.edadDe(o.edadDias || 0)].alto);
      const hw = hh * (Sprites.ANCHO_PX / Sprites.ALTO_PX);
      ctx.fillStyle = "rgba(0,0,0,0.35)"; ctx.beginPath(); ctx.ellipse(o.x, o.y, hw * 0.34, hw * 0.15, 0, 0, 6.2832); ctx.fill();
      if (!d.vivo) {   // lápida en vez de cruz: piedra redondeada con una pequeña cruz
        const piedraW = r * 1.4, piedraH = r * 1.9, radio = r * 0.35;
        ctx.fillStyle = "#9aa0a6"; ctx.strokeStyle = "#5a5f66"; ctx.lineWidth = r * 0.15;
        ctx.beginPath();
        ctx.moveTo(o.x - piedraW/2 + radio, o.y);
        ctx.lineTo(o.x - piedraW/2, o.y - piedraH + radio);
        ctx.quadraticCurveTo(o.x - piedraW/2, o.y - piedraH, o.x - piedraW/2 + radio, o.y - piedraH);
        ctx.lineTo(o.x + piedraW/2 - radio, o.y - piedraH);
        ctx.quadraticCurveTo(o.x + piedraW/2, o.y - piedraH, o.x + piedraW/2, o.y - piedraH + radio);
        ctx.lineTo(o.x + piedraW/2, o.y);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
        // cruz pequeña arriba
        ctx.strokeStyle = "#d8d8d8"; ctx.lineWidth = r * 0.18;
        ctx.beginPath();
        ctx.moveTo(o.x, o.y - piedraH + r * 0.35); ctx.lineTo(o.x, o.y - piedraH - r * 0.5);
        ctx.moveTo(o.x - r * 0.35, o.y - piedraH); ctx.lineTo(o.x + r * 0.35, o.y - piedraH);
        ctx.stroke();
      } else {
        // el sprite se apoya en los pies, que es donde está la persona en el mundo
        const img = Sprites.persona(o.edadDias || 0, d.sexo, col, o.dir || 0, o.paso || 0);
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(img, o.x - hw / 2, o.y - hh, hw, hh);
        if (d.en_fuego) { ctx.strokeStyle = "#ff3b30"; ctx.lineWidth = Math.max(0.06, 1.5 / s);
          ctx.beginPath(); ctx.ellipse(o.x, o.y - hh * 0.45, hw * 0.5, hh * 0.55, 0, 0, 6.2832); ctx.stroke(); }
        if (d.accion === "durmiendo") { ctx.fillStyle = "#fff"; ctx.strokeStyle = "#000"; ctx.lineWidth = tam * 0.16;
          ctx.font = "bold " + tam + "px sans-serif";
          ctx.strokeText("z", o.x + hw * 0.5, o.y - hh); ctx.fillText("z", o.x + hw * 0.5, o.y - hh); }
      }
      // Barras y nombre van en PÍXELES de pantalla (dividido por la escala), no en celdas: con un tope en celdas,
      // al acercarse el zoom las barras crecían hasta tapar a la persona de al lado.
      if (d.vivo && z >= 2) {   // barras de vida, sed y energía debajo de cada persona
        const bw = Math.max(hw * 1.3, 14 / s), bh = 3 / s, sep = 1.4 / s, bx0 = o.x - bw / 2;
        [[d.salud, "#4caf6a"], [100 - d.sed, "#4aa8e0"], [d.energia, "#e0a040"],
         ...(d.hambre == null ? [] : [[100 - d.hambre, "#c98b4e"]])].forEach(([v, c], i) => {
          const by0 = o.y + 3 / s + i * (bh + sep);
          ctx.fillStyle = "rgba(0,0,0,0.65)"; ctx.fillRect(bx0 - 1 / s, by0 - 1 / s, bw + 2 / s, bh + 2 / s);
          ctx.fillStyle = c; ctx.fillRect(bx0, by0, bw * Math.max(0, Math.min(100, v)) / 100, bh);
        });
      }
      if (V.sel === d.id) {   // anillo en el piso, que no tapa el cuerpo
        ctx.strokeStyle = "#fff"; ctx.lineWidth = 2 / s;
        ctx.beginPath(); ctx.ellipse(o.x, o.y, hw * 0.62, hw * 0.28, 0, 0, 6.2832); ctx.stroke();
      }
      if (z >= 2.5 || V.sel === d.id) { ctx.fillStyle = "#fff"; ctx.strokeStyle = "#000"; ctx.lineWidth = tam * 0.18;
        ctx.font = tam + "px sans-serif"; ctx.textAlign = "center";
        ctx.strokeText(d.nombre, o.x, o.y - hh - 2 / s); ctx.fillText(d.nombre, o.x, o.y - hh - 2 / s); ctx.textAlign = "start"; }
    }
    // burbujas de diálogo
    const vistos = {};
    const IMPORTANTE = /\b(peligro|cuidado|ayuda|muerte|murió|descubrí|inventé|encontré|amenaza|fuego|agua|comida|enfermo|herido|traicion|traicionó|mentira|mentiste|amor|odio|enojado|triste|feliz|celos|propuesta|familia)\b/i;
    for (const e of V.efectos) {
      if (e.tipo !== "habla") continue;
      const o = V.habs[e.id]; if (!o || z < 1.2) continue;
      const textoRaw = String(e.texto || "");
      const nombresOtros = Object.values(V.habs).filter((h) => h.id !== e.id).map((h) => h.d && h.d.nombre).filter(Boolean);
      const mencionaNombre = nombresOtros.some((n) => textoRaw.toLowerCase().includes(String(n).toLowerCase()));
      if (!mencionaNombre && !IMPORTANTE.test(textoRaw)) continue;
      const emo = o.d.emo || {};
      const moodEmoji = emo.miedo >= 0.4 ? "😨" : emo.tristeza >= 0.4 ? "😢" : emo.enojo >= 0.4 ? "😠" : emo.alegria >= 0.4 ? "😊" : "";
      const texto = (moodEmoji ? moodEmoji + " " : "") + textoRaw;
      const lineas = ajustarTexto(ctx, texto, tam, 28);
      const ancho = Math.max(...lineas.map((l) => ctx.measureText(l).width)) + tam * 0.8;
      const alto = lineas.length * tam * 1.15 + tam * 0.6, off = (vistos[e.id] = (vistos[e.id] || 0) + 1) - 1;
      const hhB = Math.max(18 / s, 1.7 / ((V.meta && V.meta.tam_celda_m) || 50));
      const bx = o.x - ancho / 2, by = o.y - hhB - alto - 4 / s - off * (alto + 0.2);
      ctx.globalAlpha = Math.min(1, (Math.min(14000, 6000 + 60 * String(e.texto || '').length) - (ahora - e.t0)) / 1500);
      ctx.fillStyle = "rgba(255,255,255,0.95)"; ctx.strokeStyle = "#222"; ctx.lineWidth = Math.max(0.05, 1 / s);
      ctx.beginPath(); ctx.roundRect(bx, by, ancho, alto, tam * 0.4); ctx.fill(); ctx.stroke();
      let yCursor = by + tam * 0.9;
      const nombresSorted = nombresOtros.slice().sort((a, b) => String(b).length - String(a).length);
      const regex = nombresSorted.length ? new RegExp("(" + nombresSorted.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "gi") : null;
      for (const l of lineas) {
        let segs = [];
        if (regex) {
          const parts = l.split(regex);
          for (const p of parts) {
            if (!p) continue;
            const esNombre = nombresSorted.some((n) => p.toLowerCase() === String(n).toLowerCase());
            segs.push({ t: p, bold: esNombre });
          }
        } else {
          segs.push({ t: l, bold: false });
        }
        let xCursor = bx + tam * 0.4;
        for (const seg of segs) {
          ctx.font = (seg.bold ? "bold " : "") + tam + "px sans-serif";
          ctx.fillStyle = seg.bold ? "#1a5fb4" : "#111";
          ctx.fillText(seg.t, xCursor, yCursor);
          xCursor += ctx.measureText(seg.t).width;
        }
        yCursor += tam * 1.15;
      }
      ctx.globalAlpha = 1;
    }
    // seguir a la persona elegida
    if (V.seguir && V.sel != null && V.habs[V.sel]) {
      const o = V.habs[V.sel], caja = lienzo.parentElement;
      vista.x += (o.x - caja.clientWidth / z / 2 - vista.x) * 0.15;
      vista.y += (o.y - caja.clientHeight / z / 2 - vista.y) * 0.15;
    }
  };

  function ajustarTexto(ctx, texto, tam, max) {
    ctx.font = tam + "px sans-serif";
    const out = []; let linea = "";
    for (const p of String(texto).split(" ")) {
      if ((linea + " " + p).trim().length > max) { out.push(linea); linea = p; } else linea = (linea + " " + p).trim();
    }
    if (linea) out.push(linea);
    return out.slice(0, 6);
  }

  // bucle de dibujo: redibuja mientras haya conexión
  let ultimoCuadro = 0;
  function cuadro(ts) {
    // de lejos (se ve poco detalle) alcanza con ~8 cuadros por segundo; de cerca ~30
    const z = base() && base().estado.vista.z;
    if (V.conectado && base() && base().estado.capas && ts - ultimoCuadro >= (z < 1.5 ? 120 : 33)) {
      ultimoCuadro = ts; base().dibujar();
    }
    requestAnimationFrame(cuadro);
  }
  requestAnimationFrame(cuadro);
  window.addEventListener("beforeunload", desconectar);
})();

// Visor 2D de Mundo Vivo. Solo LEE datos del servidor y los dibuja; no tiene reglas del mundo.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const lienzo = $("lienzo"), ctx = lienzo.getContext("2d");
  const estado = { nombre: null, meta: null, capas: null, biomas: {}, pal: null, img: null, offscreen: null,
                   vista: { x: 0, y: 0, z: 4 }, modo: "bioma" };

  const hexRgb = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const lerp = (a, b, t) => a + (b - a) * t;
  function rampa(paradas, t) {
    t = Math.max(0, Math.min(1, t));
    for (let i = 1; i < paradas.length; i++) {
      if (t <= paradas[i][0]) {
        const [t0, c0] = paradas[i - 1], [t1, c1] = paradas[i], k = (t - t0) / (t1 - t0 || 1);
        return [lerp(c0[0], c1[0], k), lerp(c0[1], c1[1], k), lerp(c0[2], c1[2], k)];
      }
    }
    return paradas[paradas.length - 1][1];
  }
  const RAMPA_ALTURA = [[0, [20, 48, 90]], [0.5, [29, 79, 143]], [0.5001, [80, 150, 80]], [0.7, [190, 180, 90]], [0.85, [140, 120, 100]], [1, [250, 250, 250]]];
  const RAMPA_TEMP = [[0, [60, 80, 200]], [0.35, [120, 190, 230]], [0.55, [240, 240, 140]], [0.8, [240, 150, 60]], [1, [200, 40, 40]]];
  const RAMPA_HUM = [[0, [200, 170, 100]], [0.5, [110, 180, 110]], [1, [30, 90, 180]]];

  // ---------------------------------------------------------------- datos
  async function json(url, opciones) {
    const r = await fetch(url, opciones);
    if (!r.ok) throw new Error((await r.text()) || r.status);
    return r.json();
  }
  async function bin(url, Tipo) {
    const r = await fetch(url);
    if (!r.ok) throw new Error((await r.text()) || r.status);
    return new Tipo(await r.arrayBuffer());
  }

  window.MV_abrirMapa = (nombre, dim) => abrirMundo(nombre, dim);

  async function cargarListaMundos(elegir) {
    const lista = await json("/api/mundos");
    const sel = $("sel-mundo");
    sel.innerHTML = "";
    for (const m of lista) {
      const o = document.createElement("option");
      o.value = m.nombre; o.textContent = m.nombre + " (semilla " + m.semilla + ")";
      sel.appendChild(o);
    }
    $("vacio").classList.toggle("visible", lista.length === 0);
    if (lista.length) {
      const guardado = elegir || localStorage.getItem("mv_mundo");
      sel.value = lista.some((m) => m.nombre === guardado) ? guardado : lista[0].nombre;
      await abrirMundo(sel.value);
    } else {
      estado.nombre = null; estado.capas = null; dibujar();
    }
  }

  async function abrirMundo(nombre, dimension) {
    $("estado").textContent = "Cargando…";
    const d = "?dim=" + (dimension || 0);
    const [meta, elev, temp, hum, bioma, agua, caudal, rasgos] = await Promise.all([
      json("/api/mundos/" + nombre + "/meta" + d),
      bin("/api/mundos/" + nombre + "/capa/elevacion" + d, Int16Array),
      bin("/api/mundos/" + nombre + "/capa/temperatura" + d, Int8Array),
      bin("/api/mundos/" + nombre + "/capa/humedad" + d, Uint8Array),
      bin("/api/mundos/" + nombre + "/capa/bioma" + d, Uint8Array),
      bin("/api/mundos/" + nombre + "/capa/agua" + d, Uint8Array),
      bin("/api/mundos/" + nombre + "/capa/caudal" + d, Uint8Array),
      bin("/api/mundos/" + nombre + "/capa/rasgos" + d, Uint8Array),
    ]);
    estado.nombre = nombre; estado.meta = meta; estado.dimension = dimension || 0;
    estado.capas = { elev, temp, hum, bioma, agua, caudal, rasgos };
    try { localStorage.setItem("mv_mundo", nombre); } catch (e) {}
    $("meta-txt").textContent = "semilla " + meta.semilla + " · " + meta.ancho + "×" + meta.alto + " · celdas de " + meta.tam_celda_m + " m · generador " + meta.version_generador;
    $("link-eventos").href = "/eventos?mundo=" + encodeURIComponent(nombre);
    prepararImagen();
    centrar();
    dibujar();
    $("estado").textContent = "";
    if (window.MV && window.MV.alAbrir) window.MV.alAbrir(nombre, meta, estado.dimension);
  }

  // ------------------------------------------------------------ pintado
  function prepararImagen() {
    const { ancho: w, alto: h } = estado.meta, c = estado.capas;
    if (!estado.offscreen) estado.offscreen = document.createElement("canvas");
    estado.offscreen.width = w; estado.offscreen.height = h; estado.mini = null;
    const octx = estado.offscreen.getContext("2d");
    const img = octx.createImageData(w, h);
    const data32 = new Uint32Array(img.data.buffer);
    const relieve = $("chk-relieve").checked, rios = $("chk-rios").checked, rasgos = $("chk-rasgos").checked;
    const modo = estado.modo;
    const pal = estado.pal || {};
    const bioma = c.bioma, agua = c.agua, elev = c.elev, rasg = c.rasgos, temp = c.temp, hum = c.hum;

    // Cache pre-calculado de paleta a 32-bit little-endian
    const pal32 = new Uint32Array(256);
    for (let b = 0; b < 256; b++) {
      const rgb = pal[b] || [255, 0, 255];
      pal32[b] = (255 << 24) | (rgb[2] << 16) | (rgb[1] << 8) | rgb[0];
    }

    let i = 0;
    if (modo === "bioma" && !relieve && !rasgos && !rios) {
      // Camino hiper-rápido: copia directa de memoria en un solo pase
      for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++, i++) {
          data32[i] = pal32[bioma[i]];
        }
      }
    } else {
      for (let y = 0; y < h; y++) {
        const yTop = Math.max(0, y - 1) * w, yBot = Math.min(h - 1, y + 1) * w, yRow = y * w;
        for (let x = 0; x < w; x++, i++) {
          let rgb;
          if (modo === "bioma") rgb = pal[bioma[i]] || [255, 0, 255];
          else if (modo === "altura") rgb = rampa(RAMPA_ALTURA, (elev[i] + 3000) / 6000 >= 0.5 ? 0.5 + (elev[i] / 3000) * 0.5 : (elev[i] + 3000) / 6000);
          else if (modo === "temperatura") rgb = rampa(RAMPA_TEMP, (temp[i] + 20) / 55);
          else rgb = rampa(RAMPA_HUM, hum[i] / 255);
          let r = rgb[0], g = rgb[1], b = rgb[2];

          if (modo === "bioma") {
            let n = (x * 374761393 + y * 668265263) | 0;
            n = (n ^ (n >> 13)) * 1274126177 | 0;
            const v = ((n ^ (n >> 16)) & 1023) * 0.0009775 - 0.5;
            const k = 1 + v * (agua[i] ? 0.05 : 0.16);
            r *= k; g *= k; b *= k;
          }
          if (relieve && elev[i] >= 0) {
            const xL = Math.max(0, x - 1), xR = Math.min(w - 1, x + 1);
            const dx = (elev[yRow + xR] - elev[yRow + xL]) * 0.5;
            const dy = (elev[yBot + x] - elev[yTop + x]) * 0.5;
            let s = 1 - (dx + dy) * 0.0166667;
            if (s < 0.6) s = 0.6; else if (s > 1.4) s = 1.4;
            r *= s; g *= s; b *= s;
          }
          if (rios && agua[i] === 3) { r = 74; g = 144; b = 217; }
          if (rasgos) {
            const rg = rasg[i];
            if (rg & 1) { r = 255; g = 255; b = 255; }
            if (rg & 2) { r = 255; g = 90; b = 31; }
          }
          const cr = r < 0 ? 0 : r > 255 ? 255 : (r | 0);
          const cg = g < 0 ? 0 : g > 255 ? 255 : (g | 0);
          const cb = b < 0 ? 0 : b > 255 ? 255 : (b | 0);
          data32[i] = (255 << 24) | (cb << 16) | (cg << 8) | cr;
        }
      }
    }
    octx.putImageData(img, 0, 0);
  }

  function ajustarLienzo() {
    const caja = lienzo.parentElement, dpr = window.devicePixelRatio || 1;
    const w = Math.round(caja.clientWidth * dpr), h = Math.round(caja.clientHeight * dpr);
    if (lienzo.width !== w) lienzo.width = w;   // cambiar el tamaño borra el lienzo: solo si hace falta
    if (lienzo.height !== h) lienzo.height = h;
  }

  function dibujar() {
    ajustarLienzo();
    const dpr = window.devicePixelRatio || 1, W = lienzo.width, H = lienzo.height;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = "#0a0d12"; ctx.fillRect(0, 0, W, H);
    if (!estado.capas) return;
    const { x, y, z } = estado.vista, s = z * dpr;
    ctx.setTransform(s, 0, 0, s, -x * s, -y * s);
    // solo se redibuja lo que se ve: la porción visible del mapa, y de lejos una versión chica (baja calidad)
    const { ancho: w, alto: h } = estado.meta;
    const x0 = Math.max(0, Math.floor(x)), y0 = Math.max(0, Math.floor(y));
    const x1 = Math.min(w, Math.ceil(x + W / s)), y1 = Math.min(h, Math.ceil(y + H / s));
    estado.vis = { x0, y0, x1, y1 };
    if (x1 > x0 && y1 > y0) {
      if (z < 1) {                                   // mundo entero a la vista: miniatura a media resolución
        if (!estado.mini) {
          estado.mini = document.createElement("canvas"); estado.mini.width = Math.ceil(w / 2); estado.mini.height = Math.ceil(h / 2);
          const mc = estado.mini.getContext("2d"); mc.imageSmoothingEnabled = true; mc.drawImage(estado.offscreen, 0, 0, estado.mini.width, estado.mini.height);
        }
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(estado.mini, x0 / 2, y0 / 2, (x1 - x0) / 2, (y1 - y0) / 2, x0, y0, x1 - x0, y1 - y0);
      } else {
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(estado.offscreen, x0, y0, x1 - x0, y1 - y0, x0, y0, x1 - x0, y1 - y0);
      }
    }
    if ($("chk-grilla").checked && z >= 8) {
      ctx.lineWidth = 1 / s; ctx.strokeStyle = "rgba(0,0,0,.25)"; ctx.beginPath();
      for (let i = x0; i <= x1; i++) { ctx.moveTo(i, y0); ctx.lineTo(i, y1); }
      for (let j = y0; j <= y1; j++) { ctx.moveTo(x0, j); ctx.lineTo(x1, j); }
      ctx.stroke();
    }
    if (window.MV && window.MV.sobreMapa) window.MV.sobreMapa(ctx, s, dpr);   // capa en vivo (vivo.js)
  }

  function centrar() {
    const caja = lienzo.parentElement, { ancho: w, alto: h } = estado.meta;
    const z = Math.max(1, Math.floor(Math.min(caja.clientWidth / w, caja.clientHeight / h) * 10) / 10);
    estado.vista.z = z;
    estado.vista.x = w / 2 - caja.clientWidth / z / 2;
    estado.vista.y = h / 2 - caja.clientHeight / z / 2;
  }

  // --------------------------------------------------------- interacción
  function celdaEn(ev) {
    const r = lienzo.getBoundingClientRect(), { x, y, z } = estado.vista;
    return [Math.floor(x + (ev.clientX - r.left) / z), Math.floor(y + (ev.clientY - r.top) / z)];
  }

  lienzo.addEventListener("wheel", (ev) => {
    if (!estado.capas) return;
    ev.preventDefault();
    const r = lienzo.getBoundingClientRect(), v = estado.vista;
    const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    const wx = v.x + mx / v.z, wy = v.y + my / v.z;
    // con celdas de 5 m hace falta acercarse mucho más para separar a dos personas que están a un par de metros
    v.z = Math.max(0.25, Math.min(260, v.z * (ev.deltaY < 0 ? 1.15 : 1 / 1.15)));
    v.x = wx - mx / v.z; v.y = wy - my / v.z;
    dibujar();
  }, { passive: false });

  const btnZIn = $("btn-zoom-in"), btnZOut = $("btn-zoom-out");
  if (btnZIn) btnZIn.addEventListener("click", () => {
    if (!estado.capas) return;
    const v = estado.vista, caja = lienzo.parentElement;
    const mx = caja.clientWidth / 2, my = caja.clientHeight / 2;
    const wx = v.x + mx / v.z, wy = v.y + my / v.z;
    v.z = Math.max(0.25, Math.min(260, v.z * 1.25));
    v.x = wx - mx / v.z; v.y = wy - my / v.z;
    dibujar();
  });
  if (btnZOut) btnZOut.addEventListener("click", () => {
    if (!estado.capas) return;
    const v = estado.vista, caja = lienzo.parentElement;
    const mx = caja.clientWidth / 2, my = caja.clientHeight / 2;
    const wx = v.x + mx / v.z, wy = v.y + my / v.z;
    v.z = Math.max(0.25, Math.min(260, v.z / 1.25));
    v.x = wx - mx / v.z; v.y = wy - my / v.z;
    dibujar();
  });
  let arrastre = null;
  lienzo.addEventListener("pointerdown", (ev) => {
    arrastre = { px: ev.clientX, py: ev.clientY, vx: estado.vista.x, vy: estado.vista.y };
    lienzo.setPointerCapture(ev.pointerId); lienzo.classList.add("arrastrando");
  });
  lienzo.addEventListener("pointermove", (ev) => {
    if (arrastre) {
      estado.vista.x = arrastre.vx - (ev.clientX - arrastre.px) / estado.vista.z;
      estado.vista.y = arrastre.vy - (ev.clientY - arrastre.py) / estado.vista.z;
      dibujar();
    }
    mostrarInfo(ev);
  });
  lienzo.addEventListener("pointerup", () => { arrastre = null; lienzo.classList.remove("arrastrando"); });
  lienzo.addEventListener("dblclick", () => { if (estado.capas) { centrar(); dibujar(); } });
  lienzo.addEventListener("pointerleave", () => { $("info").innerHTML = "Pasá el mouse por el mapa."; });

  // Navegación por teclado (flechas, para TV/remoto/móvil sin mouse)
  window.addEventListener("keydown", (ev) => {
    if (!estado.capas) return;
    const paso = 60 / estado.vista.z;   // 60 px de pantalla por tecla
    if (ev.key === "ArrowLeft") { estado.vista.x -= paso; ev.preventDefault(); }
    else if (ev.key === "ArrowRight") { estado.vista.x += paso; ev.preventDefault(); }
    else if (ev.key === "ArrowUp") { estado.vista.y -= paso; ev.preventDefault(); }
    else if (ev.key === "ArrowDown") { estado.vista.y += paso; ev.preventDefault(); }
    else if (ev.key === "+" || ev.key === "=") { estado.vista.z = Math.max(0.25, Math.min(260, estado.vista.z * 1.25)); ev.preventDefault(); }
    else if (ev.key === "-" || ev.key === "_") { estado.vista.z = Math.max(0.25, Math.min(260, estado.vista.z / 1.25)); ev.preventDefault(); }
    else return;
    dibujar();
  });

  function mostrarInfo(ev) {
    if (!estado.capas) return;
    const [cx, cy] = celdaEn(ev), { ancho: w, alto: h, tam_celda_m: m } = estado.meta;
    if (cx < 0 || cy < 0 || cx >= w || cy >= h) { $("info").textContent = "Fuera del mapa."; return; }
    const i = cy * w + cx, c = estado.capas, b = estado.biomas[c.bioma[i]];
    const agua = ["", "océano", "lago", "río"][c.agua[i]];
    const extra = [];
    if (c.rasgos[i] & 1) extra.push("cascada");
    if (c.rasgos[i] & 2) extra.push("lava");
    $("info").innerHTML =
      "<div><b>" + (b ? b.nombre : "?") + "</b></div>" +
      "<div>Celda " + cx + ", " + cy + " <span class='suave'>(" + (cx * m) + " m, " + (cy * m) + " m)</span></div>" +
      "<div>Altura: <b>" + c.elev[i] + " m</b></div>" +
      "<div>Temperatura: <b>" + c.temp[i] + " °C</b></div>" +
      "<div>Humedad: <b>" + Math.round(c.hum[i] / 2.55) + " %</b></div>" +
      (agua ? "<div>Agua: <b>" + agua + "</b>" + (c.agua[i] === 3 ? " (caudal " + c.caudal[i] + ")" : "") + "</div>" : "") +
      (extra.length ? "<div>Rasgos: <b>" + extra.join(", ") + "</b></div>" : "");
  }

  function armarLeyenda() {
    const cont = $("leyenda"); cont.innerHTML = "";
    for (const id of Object.keys(estado.biomas)) {
      const b = estado.biomas[id], f = document.createElement("div");
      f.innerHTML = "<i style='background:" + b.color + "'></i>" + b.nombre;
      cont.appendChild(f);
    }
  }

  // ---------------------------------------------------------- controles
  document.querySelectorAll("input[name=modo]").forEach((r) => r.addEventListener("change", () => {
    estado.modo = r.value; if (estado.capas) { prepararImagen(); dibujar(); }
  }));
  ["chk-relieve", "chk-rios", "chk-rasgos"].forEach((id) => $(id).addEventListener("change", () => {
    if (estado.capas) { prepararImagen(); dibujar(); }
  }));
  $("chk-grilla").addEventListener("change", dibujar);
  $("sel-mundo").addEventListener("change", (e) => abrirMundo(e.target.value));
  $("btn-nuevo").addEventListener("click", async () => {
    $("nuevo-panel").classList.add("visible");
    try {
      const m = await json("/api/modelos");
      $("lista-modelos").innerHTML = m.modelos.map((x) => "<option value='" + x + "'>").join("");
      if (!$("in-modelo-nuevo").value) { try { $("in-modelo-nuevo").value = localStorage.getItem("mv_modelo") || m.predeterminado; } catch (e) { $("in-modelo-nuevo").value = m.predeterminado; } }
      if (!m.ok) $("in-modelo-nuevo").title = "No pude consultar Ollama: " + m.error;
    } catch (e) {}
  });

  const bCancNuevo = $("btn-cancelar-nuevo");
  if (bCancNuevo) bCancNuevo.addEventListener("click", () => $("nuevo-panel").classList.remove("visible"));
  // Consejos que van rotando mientras se genera, como las pantallas de carga de los juegos.
  // Son cosas ciertas del mundo: sirven para entender qué están viendo.
  const TIPS = [
    "Nadie sabe nada de entrada: cada receta la descubre alguien probando materiales de verdad.",
    "Una celda son 5 metros. El mundo entero mide unos 10 kilómetros de lado.",
    "Los habitantes no saben que los estás mirando, y nunca se van a enterar.",
    "El fuego se propaga de verdad: el viento, la lluvia y lo que ya se quemó deciden hasta dónde llega.",
    "Cada persona hereda un genoma que le marca el carácter, y ese carácter cambia con lo que vive.",
    "Una aldea necesita casas: dos chozas cerca una de la otra. Gente parada junta no alcanza.",
    "Los materiales de cada zona se agotan al juntarlos y vuelven a crecer en unos ocho días.",
    "Doce años del mundo son 1440 días. Recién ahí un chico puede formar su propia familia.",
    "Si nadie descubre cómo hacer fuego, no hay comida cocida, ni cerámica, ni noches tibias.",
  ];

  function pantallaCarga(mostrar) {
    $("carga").classList.toggle("visible", !!mostrar);
    if (!mostrar) { $("carga-error").textContent = ""; $("carga-barra").style.width = "0"; }
  }

  async function seguirGeneracion(tid, km) {
    pantallaCarga(true);
    $("carga-sub").textContent = "Generando un mundo de " + km + " km: relieve, clima, ríos y biomas. "
      + "Tardá lo que tarde, no cierres esta pestaña.";
    let i = Math.floor(Math.random() * TIPS.length);
    $("carga-tip").textContent = TIPS[i % TIPS.length];
    const rot = setInterval(() => { $("carga-tip").textContent = TIPS[++i % TIPS.length]; }, 6000);
    try {
      for (;;) {
        const t = await json("/api/mundos/generando/" + tid);
        $("carga-etapa").textContent = t.texto || "";
        $("carga-barra").style.width = Math.round((t.frac || 0) * 100) + "%";
        $("carga-pct").textContent = Math.round((t.frac || 0) * 100) + "%";
        if (t.error) { $("carga-error").textContent = "No se pudo crear: " + t.error; return null; }
        if (t.hecho) return t.nombre;
        await new Promise((r) => setTimeout(r, 600));
      }
    } finally {
      clearInterval(rot);
    }
  }

  $("btn-crear").addEventListener("click", async () => {
    const nom = $("in-nombre-nuevo") ? $("in-nombre-nuevo").value.trim() : null;
    const semilla = $("in-semilla").value.trim(), tam = parseInt($("in-tam").value, 10);
    const TAM_CELDA = 5;                               // metros por celda de los mundos nuevos
    const km = (tam * TAM_CELDA / 1000).toFixed(1);
    $("btn-crear").disabled = true;
    // generar 2048×2048 lleva ~90 s: sin este aviso parece que se colgó
    $("estado").textContent = "Generando un mundo de " + km + " km… puede tardar un par de minutos, no lo cierres.";
    try {
      const r = await json("/api/mundos", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre: nom || null, semilla: semilla ? parseInt(semilla, 10) : null, ancho: tam, alto: tam,
                               tam_celda_m: TAM_CELDA, modelo: $("in-modelo-nuevo").value.trim() || null,
                               poblacion: parseInt($("in-poblacion").value, 10) || 4 }) });
      try { localStorage.setItem("mv_modelo", $("in-modelo-nuevo").value.trim()); } catch (e) {}
      $("nuevo-panel").classList.remove("visible"); $("in-semilla").value = "";
      if ($("in-nombre-nuevo")) $("in-nombre-nuevo").value = "";
      $("estado").textContent = "";
      const nombre = await seguirGeneracion(r.trabajo, km);
      if (nombre) { pantallaCarga(false); await cargarListaMundos(nombre); }
      else { setTimeout(() => pantallaCarga(false), 6000); }   // dejar leer el error
    } catch (e) { pantallaCarga(false); $("estado").textContent = "Error: " + e.message; }
    $("btn-crear").disabled = false;
  });
  $("btn-borrar").addEventListener("click", async () => {
    if (!estado.nombre) return;
    const n = estado.nombre;
    if (!window.confirm("¿Eliminar el mundo «" + n + "»?\nSe pierde todo (personas, recuerdos, historia) y no se puede deshacer.\nSi querés guardarlo, exportalo antes.")) return;
    $("estado").textContent = "Eliminando…";
    try {
      if (window.MV && window.MV.desconectar) window.MV.desconectar();
      const r = await fetch("/api/mundos/" + encodeURIComponent(n), { method: "DELETE" });
      if (!r.ok) throw new Error((await r.text()) || r.status);
      try { if (localStorage.getItem("mv_mundo") === n) localStorage.removeItem("mv_mundo"); } catch (e) {}
      estado.capas = null; estado.nombre = null;
      await cargarListaMundos();
      $("estado").textContent = "";
    } catch (e) { $("estado").textContent = "Error: " + e.message; }
  });
  $("btn-exportar").addEventListener("click", async () => {
    if (!estado.nombre) return;
    $("estado").textContent = "Exportando…";
    const r = await fetch("/api/mundos/" + estado.nombre + "/exportar", { method: "POST" });
    const blob = await r.blob(), a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = estado.nombre + ".zip"; a.click();
    $("estado").textContent = "";
  });
  window.addEventListener("resize", () => { if (estado.capas) dibujar(); });
  window.MVBase = { estado, dibujar, centrar };

  // -------------------------------------------------------------- inicio
  (async function iniciar() {
    const lista = await json("/api/biomas");
    estado.pal = {};
    for (const b of lista) {
      estado.biomas[b.id] = b;
      if (b.id_numerico != null) estado.biomas[b.id_numerico] = b;
      const rgb = hexRgb(b.color);
      estado.pal[b.id] = rgb;
      if (b.id_numerico != null) estado.pal[b.id_numerico] = rgb;
    }
    armarLeyenda();
    await cargarListaMundos(new URLSearchParams(location.search).get("mundo"));
  })().catch((e) => { $("estado").textContent = "Error: " + e.message; });
})();

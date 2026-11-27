// Prototipo AISLADO de renderer 2D por capas para Everwild (Etapa 3A).
// No usa el motor ni la app: genera un mundo ficticio determinista y lo dibuja con
// Canvas 2D en capas (terreno, vegetación, estructuras, entidades, efectos, overlay),
// con LOD por zoom, orden por Y, sombras, culling, caché/pool de sprites y
// actualización parcial del terreno. Sirve para decidir la representación visual.
(function () {
  "use strict";
  const L = window.Layers;
  const canvas = document.getElementById("lienzo");
  const ctx = canvas.getContext("2d", { alpha: false });
  const hud = document.getElementById("hud");

  const W = 180, H = 140;            // celdas del mundo ficticio
  const PAL = {                       // paleta por bioma (id -> color)
    0: "#1d3557", 1: "#2a9d8f", 2: "#e9c46a", 3: "#8ab17d", 4: "#606c38",
    5: "#355070", 6: "#6a994e", 7: "#386641", 8: "#4a4e69", 9: "#9aa0a6",
    10: "#ced4da", 11: "#b5651d", 12: "#7d8597",
  };
  const AGUA = "#1b3a5c";

  const estado = {
    seed: 1337, t: 0, pausa: false, sel: null,
    capas: { vegetacion: true, estructuras: true, entidades: true, sombras: true, efectos: true, overlay: true },
    cam: { x: W / 2, y: H / 2, z: 2 },
  };
  let elev, temp, hum, bioma, agua, plantas = [], animales = [], estructuras = [], senderos;
  let terrainCv, terrainCtx, terrainImg, vegCv, vegCtx, vegImg;
  let drawCount = 0, fps = 0, _lastT = performance.now(), _acc = 0, _frames = 0;

  // ---- generación determinista del mundo ficticio -----------------------------
  function generar(seed) {
    estado.seed = seed; estado.sel = null;
    elev = new Float32Array(W * H); temp = new Float32Array(W * H); hum = new Float32Array(W * H);
    bioma = new Uint8Array(W * H); agua = new Uint8Array(W * H); senderos = new Float32Array(W * H);
    const r = L.rng(seed);
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const i = y * W + x;
        const e = L.fbm(x / 26, y / 26, seed, 5);
        elev[i] = e;
        temp[i] = Math.max(0, Math.min(1, 1 - y / H + (L.fbm(x / 40, y / 40, seed + 7, 3) - 0.5) * 0.4));
        hum[i] = L.fbm(x / 22 + 5, y / 22, seed + 13, 4);
      }
    }
    // ríos: dos curvas senoidales que tallan agua
    for (let x = 0; x < W; x++) {
      const r1 = Math.floor(H * 0.35 + Math.sin(x / 18) * 10);
      const r2 = Math.floor(H * 0.7 + Math.sin(x / 25 + 2) * 8);
      for (let t = -1; t <= 1; t++) { const a = (r1 + t) * W + x, b = (r2 + t) * W + x; if (a >= 0 && a < W * H) agua[a] = 1; if (b >= 0 && b < W * H) agua[b] = 1; }
    }
    for (let i = 0; i < W * H; i++) {
      if (elev[i] < 0.32) agua[i] = 1;                  // mar / lagos
      if (agua[i]) { bioma[i] = 0; continue; }
      const e = elev[i], tp = temp[i], hm = hum[i];
      let b;
      if (e > 0.82) b = tp < 0.4 ? 10 : 12;             // montaña / roca
      else if (e > 0.72) b = 11;                        // tierra
      else if (tp < 0.3) b = 9;                         // nieve/tundra
      else if (hm > 0.66) b = e > 0.6 ? 7 : 6;          // bosque / selva
      else if (hm > 0.5) b = 3;                         // pradera
      else if (hm > 0.38) b = 4;                        // sabana
      else b = tp > 0.6 ? 2 : 5;                        // desierto / costa
      bioma[i] = b;
    }
    // senderos con desgaste entre dos aldeas
    const ax = Math.floor(W * 0.3), ay = Math.floor(H * 0.5), bx = Math.floor(W * 0.7), by = Math.floor(H * 0.45);
    for (let s = 0; s <= 1; s += 0.002) {
      const x = Math.floor(ax + (bx - ax) * s), y = Math.floor(ay + (by - ay) * s + Math.sin(s * 9) * 3);
      for (let d = -1; d <= 1; d++) { const i = (y + d) * W + x; if (i >= 0 && i < W * H && !agua[i]) senderos[i] = Math.min(1, senderos[i] + 0.5); }
    }
    estructuras = [
      { x: ax, y: ay, tipo: "casa" }, { x: ax + 3, y: ay + 1, tipo: "horno" },
      { x: bx, y: by, tipo: "casa" }, { x: bx - 2, y: by + 2, tipo: "fragua" },
    ];
    // plantas por etapa (0 semilla .. 3 adulto) en tierra no sendero
    plantas = [];
    for (let k = 0; k < 520; k++) {
      const x = Math.floor(r() * W), y = Math.floor(r() * H), i = y * W + x;
      if (agua[i] || senderos[i] > 0.2) continue;
      const cat = bioma[i] === 6 || bioma[i] === 7 ? "arbol" : "mata";
      plantas.push({ x: x + 0.2 + r() * 0.6, y: y + 0.2 + r() * 0.6, cat, etapa: Math.floor(r() * 4), v: Math.floor(r() * 3) });
    }
    // animales
    animales = [];
    for (let k = 0; k < 40; k++) {
      let x, y, i;
      do { x = r() * W; y = r() * H; i = (y | 0) * W + (x | 0); } while (agua[i]);
      animales.push({ x, y, vx: (r() - 0.5) * 0.6, vy: (r() - 0.5) * 0.6, especie: ["conejo", "zorro", "ciervo"][k % 3], dir: 1 });
    }
    rasterTerrain(); rasterVeg();
    estado.cam.x = W / 2; estado.cam.y = H / 2;
    pedirRender();
  }

  // ---- capas rasterizadas (1 px / celda) -------------------------------------
  function rasterTerrain() {
    terrainCv = terrainCv || document.createElement("canvas");
    terrainCv.width = W; terrainCv.height = H; terrainCtx = terrainCv.getContext("2d");
    terrainImg = terrainCtx.createImageData(W, H);
    pintarTerrainTodo();
    terrainCtx.putImageData(terrainImg, 0, 0);
  }
  function pintarTerrainTodo() {
    const d = terrainImg.data;
    for (let i = 0; i < W * H; i++) {
      const col = agua[i] ? AGUA : PAL[bioma[i]] || "#444";
      const n = parseInt(col.slice(1), 16);
      d[i * 4] = (n >> 16) & 255; d[i * 4 + 1] = (n >> 8) & 255; d[i * 4 + 2] = n & 255; d[i * 4 + 3] = 255;
    }
  }
  // actualización parcial: redibuja sólo un conjunto de celdas y sube la zona sucia
  function updateTiles(cells) {
    const d = terrainImg.data;
    for (const i of cells) {
      const col = agua[i] ? AGUA : PAL[bioma[i]] || "#444";
      const n = parseInt(col.slice(1), 16);
      d[i * 4] = (n >> 16) & 255; d[i * 4 + 1] = (n >> 8) & 255; d[i * 4 + 2] = n & 255; d[i * 4 + 3] = 255;
    }
    terrainCtx.putImageData(terrainImg, 0, 0, 0, 0, W, H);
  }
  function rasterVeg() {
    vegCv = vegCv || document.createElement("canvas");
    vegCv.width = W; vegCv.height = H; vegCtx = vegCv.getContext("2d");
    vegImg = vegCtx.createImageData(W, H);
    const d = vegImg.data;
    const COL = { 0: [180, 200, 120], 1: [120, 200, 110], 2: [70, 160, 80], 3: [40, 120, 60] };
    for (const p of plantas) {
      const i = (p.y | 0) * W + (p.x | 0); if (agua[i]) continue;
      const c = COL[p.etapa]; d[i * 4] = c[0]; d[i * 4 + 1] = c[1]; d[i * 4 + 2] = c[2]; d[i * 4 + 3] = 200;
    }
    vegCtx.putImageData(vegImg, 0, 0);
  }

  // ---- caché de sprites (reuse) ----------------------------------------------
  const _sprites = new Map();
  function sprite(clave, px, fn) {
    let c = _sprites.get(clave);
    if (c) return c;
    c = document.createElement("canvas"); c.width = px; c.height = px;
    fn(c.getContext("2d"), px); _sprites.set(clave, c); return c;
  }
  function spritePlanta(cat, etapa, v) {
    const px = 48;
    return sprite("pl:" + cat + etapa + v, px, (g) => {
      const cx = px / 2, base = px - 4, h = (etapa + 1) * 8;
      g.strokeStyle = "#5a3d28"; g.lineWidth = 3; g.beginPath(); g.moveTo(cx, base); g.lineTo(cx, base - h); g.stroke();
      if (cat === "arbol" || etapa >= 2) {
        g.fillStyle = ["#7bbf5a", "#5a9e46", "#3f7d34"][v];
        g.beginPath(); g.arc(cx, base - h, 6 + etapa * 2, 0, 6.2832); g.fill();
      } else { g.fillStyle = "#8ab17d"; g.fillRect(cx - 3, base - h, 6, 4); }
    });
  }
  function spriteAnimal(esp) {
    const px = 40;
    return sprite("an:" + esp, px, (g) => {
      const col = { conejo: "#c9b79c", zorro: "#d2691e", ciervo: "#a9744f" }[esp] || "#ccc";
      g.fillStyle = col; g.beginPath(); g.ellipse(px / 2, px * 0.6, px * 0.28, px * 0.18, 0, 0, 6.2832); g.fill();
      g.beginPath(); g.arc(px * 0.72, px * 0.42, px * 0.12, 0, 6.2832); g.fill();
      g.fillStyle = "#000"; g.fillRect(px * 0.74, px * 0.4, 2, 2);
    });
  }
  function spriteEstructura(tipo) {
    const px = 64;
    return sprite("es:" + tipo, px, (g) => {
      if (tipo === "casa") {
        g.fillStyle = "#c9a36b"; g.fillRect(10, 28, 44, 30);
        g.fillStyle = "#7a4b2a"; g.beginPath(); g.moveTo(6, 30); g.lineTo(32, 10); g.lineTo(58, 30); g.closePath(); g.fill();
        g.fillStyle = "#3a2a1a"; g.fillRect(26, 40, 12, 18);
      } else {
        g.fillStyle = "#6b6257"; g.fillRect(14, 30, 36, 28);
        g.fillStyle = tipo === "horno" ? "#ff7a2a" : "#ffce54"; g.beginPath(); g.arc(32, 40, 7, 0, 6.2832); g.fill();
      }
    });
  }

  // ---- dibujo por capas -------------------------------------------------------
  function worldTransform() {
    const z = estado.cam.z;
    ctx.setTransform(z, 0, 0, z, -estado.cam.x * z + canvas.width / 2, -estado.cam.y * z + canvas.height / 2);
  }
  function visRect() {
    const z = estado.cam.z, hw = canvas.width / z / 2, hh = canvas.height / z / 2;
    return { x0: Math.floor(estado.cam.x - hw) - 2, y0: Math.floor(estado.cam.y - hh) - 2, x1: Math.ceil(estado.cam.x + hw) + 2, y1: Math.ceil(estado.cam.y + hh) + 2 };
  }

  function dibujar() {
    drawCount++;
    const z = estado.cam.z, lod = L.seleccionarLOD(z), vis = visRect();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = "#0b0f14"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    worldTransform();
    ctx.imageSmoothingEnabled = false;
    // TerrainLayer
    ctx.drawImage(terrainCv, 0, 0);
    // VegetationLayer (overlay pixel); sprites de cerca van a la capa de profundidad
    if (estado.capas.vegetacion) { ctx.imageSmoothingEnabled = false; ctx.globalAlpha = lod.sprites ? 0.0 : 1.0; ctx.drawImage(vegCv, 0, 0); ctx.globalAlpha = 1; }
    // senderos (desgaste) sobre el terreno
    ctx.fillStyle = "rgba(150,120,80,0.5)";
    for (let i = 0; i < W * H; i++) if (senderos[i] > 0.2 && L.esVisible(i % W, (i / W) | 0, 0, vis)) ctx.fillRect(i % W, (i / W) | 0, 1, 1);

    // lista de profundidad (Y): estructuras + plantas(sprites) + animales
    const prof = [];
    if (estado.capas.estructuras) for (const e of estructuras) if (L.esVisible(e.x, e.y, 3, vis)) prof.push({ y: e.y, pos: e, d: () => dibujarEstructura(e, z) });
    if (estado.capas.vegetacion && lod.sprites) for (const p of plantas) if (L.esVisible(p.x, p.y, 2, vis)) prof.push({ y: p.y, pos: p, d: () => dibujarPlanta(p, z) });
    if (estado.capas.entidades) for (const a of animales) if (L.esVisible(a.x, a.y, 2, vis)) prof.push({ y: a.y, pos: a, d: () => dibujarAnimal(a, z, lod) });

    const orden = L.ordenarPorY(prof);
    // Sombras (plano del suelo, debajo de todos los sprites)
    if (estado.capas.sombras && lod.sombras) {
      ctx.fillStyle = "rgba(0,0,0,0.30)";
      for (const it of orden) { const p = it.pos; ctx.beginPath(); ctx.ellipse(p.x, p.y, 0.5, 0.16, 0, 0, 6.2832); ctx.fill(); }
    }
    // sprites ordenados por Y (más Y = al frente)
    ctx.imageSmoothingEnabled = true;
    for (const it of orden) it.d();

    // EffectsLayer: día/noche + partículas
    if (estado.capas.efectos) dibujarEfectos(vis);
    // OverlayLayer: selección + HUD
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    if (estado.capas.overlay) dibujarOverlay(lod);
  }

  function dibujarPlanta(p, z) {
    const s = (0.5 + p.etapa * 0.35) * (p.cat === "arbol" ? 1.4 : 1.0);
    const img = spritePlanta(p.cat, p.etapa, p.v);
    ctx.drawImage(img, p.x - s / 2, p.y - s, s, s);
  }
  function dibujarAnimal(a, z, lod) {
    if (!lod.sprites) { ctx.fillStyle = { conejo: "#c9b79c", zorro: "#d2691e", ciervo: "#a9744f" }[a.especie]; ctx.fillRect(a.x - 0.3, a.y - 0.3, 0.6, 0.6); return; }
    const s = 0.9, img = spriteAnimal(a.especie);
    ctx.save(); ctx.translate(a.x, a.y); if (a.vx < 0) ctx.scale(-1, 1);
    ctx.drawImage(img, -s / 2, -s, s, s); ctx.restore();
  }
  function dibujarEstructura(e, z) {
    const s = 1.6, img = spriteEstructura(e.tipo);
    ctx.drawImage(img, e.x - s / 2, e.y - s, s, s);
  }
  function dibujarEfectos(vis) {
    const t = (estado.t / 60) % 1;                       // ciclo día/noche de demo
    const a = Math.max(0, Math.sin(t * 6.2832)) * 0.45;
    if (a > 0.02) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = "rgba(8,12,40," + a + ")"; ctx.fillRect(0, 0, canvas.width, canvas.height);
      worldTransform();
    }
  }
  function dibujarOverlay(lod) {
    ctx.font = "12px ui-monospace, monospace"; ctx.textAlign = "left"; ctx.textBaseline = "top";
    const vis = visRect();
    let visPlantas = 0, visAnim = 0;
    for (const p of plantas) if (L.esVisible(p.x, p.y, 0, vis)) visPlantas++;
    for (const a of animales) if (L.esVisible(a.x, a.y, 0, vis)) visAnim++;
    hud.textContent =
      "LOD: " + lod.modo + "  (zoom " + estado.cam.z.toFixed(1) + "×)\n" +
      "sprites: " + lod.sprites + "  detalle: " + lod.detalle + "  sombras: " + lod.sombras + "\n" +
      "visibles → plantas " + visPlantas + "  animales " + visAnim + "\n" +
      "sprites en caché: " + _sprites.size + "   draws: " + drawCount + "\n" +
      "fps: " + fps.toFixed(0) + "   semilla: " + estado.seed;
    // anillo de selección
    if (estado.sel) {
      worldTransform();
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 2 / estado.cam.z;
      ctx.beginPath(); ctx.ellipse(estado.sel.x, estado.sel.y, 0.7, 0.3, 0, 0, 6.2832); ctx.stroke();
    }
  }

  // ---- bucle bajo demanda (un solo rAF; continúa si hay animación) -----------
  let raf = 0;
  function pedirRender() { if (!raf) raf = requestAnimationFrame(cuadro); }
  function cuadro() {
    raf = 0;
    const now = performance.now(); _acc += now - _lastT; _lastT = now; _frames++;
    if (_acc >= 500) { fps = _frames * 1000 / _acc; _frames = 0; _acc = 0; }
    if (!estado.pausa) { estado.t++; for (const a of animales) mover(a); }
    dibujar();
    if (!estado.pausa) pedirRender();          // animación continua mientras no esté en pausa
  }
  function mover(a) {
    a.x += a.vx * 0.05; a.y += a.vy * 0.05;
    if (a.x < 1 || a.x > W - 2) a.vx *= -1; if (a.y < 1 || a.y > H - 2) a.vy *= -1;
    a.dir = a.vx < 0 ? -1 : 1;
  }

  // ---- interacción -----------------------------------------------------------
  function resize() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; pedirRender(); }
  window.addEventListener("resize", resize);
  document.getElementById("zoom").addEventListener("input", (e) => { estado.cam.z = +e.target.value; document.getElementById("zoomv").textContent = estado.cam.z.toFixed(1) + "×"; pedirRender(); });
  document.getElementById("regenerar").addEventListener("click", () => generar((Math.random() * 1e9) | 0));
  document.getElementById("pausa").addEventListener("click", (e) => { estado.pausa = !estado.pausa; e.target.textContent = estado.pausa ? "Reanudar" : "Pausar"; pedirRender(); });
  document.getElementById("mutar").addEventListener("click", () => {
    const r = L.rng(estado.seed + estado.t + 1), cells = [];
    for (let k = 0; k < 400; k++) { const i = (r() * W * H) | 0; if (!agua[i]) { bioma[i] = 1 + ((r() * 12) | 0); cells.push(i); } }
    updateTiles(cells); pedirRender();          // actualización parcial (no re-rasteriza todo)
  });
  document.querySelectorAll('[data-capa]').forEach((el) => el.addEventListener("change", () => { estado.capas[el.dataset.capa] = el.checked; pedirRender(); }));
  let drag = null;
  canvas.addEventListener("pointerdown", (e) => { drag = [e.clientX, e.clientY, estado.cam.x, estado.cam.y]; });
  canvas.addEventListener("pointerup", (e) => {
    if (drag && Math.hypot(e.clientX - drag[0], e.clientY - drag[1]) < 4) {
      const z = estado.cam.z, wx = (e.clientX - canvas.width / 2) / z + estado.cam.x, wy = (e.clientY - canvas.height / 2) / z + estado.cam.y;
      let best = null, bd = 1e9; for (const a of animales) { const d = Math.hypot(a.x - wx, a.y - wy); if (d < bd) { bd = d; best = a; } }
      estado.sel = bd < 2 ? best : null;
    }
    drag = null; pedirRender();
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const z = estado.cam.z; estado.cam.x = drag[2] - (e.clientX - drag[0]) / z; estado.cam.y = drag[3] - (e.clientY - drag[1]) / z; pedirRender();
  });

  resize();
  const zp = new URLSearchParams(location.search).get("z");
  if (zp) { estado.cam.z = Math.max(0.5, Math.min(16, +zp)); const sl = document.getElementById("zoom"); if (sl) sl.value = estado.cam.z; const zv = document.getElementById("zoomv"); if (zv) zv.textContent = estado.cam.z.toFixed(1) + "×"; }
  generar(estado.seed);
})();
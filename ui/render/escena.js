// Capa de render dinámico (Etapa 2): dibujo de la escena en vivo sobre el terreno.
// Extraído de vivo.js sin cambios de comportamiento. Recibe sus dependencias por
// parámetro (estado V, acceso al terreno, Sprites, colores, $, lienzo) y define
// V.sobreMapa. No conoce reglas del mundo: solo pinta lo que el estado publica.
(function (root) {
  "use strict";

  function instalar(V, base, Sprites, COLORES, $, lienzo) {
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

    async function pedirNieve(v) {
      if (document.hidden) return;
      const ahora = Date.now();
      if (ahora - V.nieve.pedido < 15000 || !V.nombre) return;
      const n = V.nombre;
      V.nieve.pedido = ahora;
      try {
        const r = await fetch("/api/mundos/" + n + "/dinamico/nieve");
        const ds = new DecompressionStream("deflate");
        const piped = r.body.pipeThrough(ds);
        const datos = new Uint8Array(await new Response(piped).arrayBuffer());
        if (n !== V.nombre) return;   // cambió el mundo: descartar este mapa de nieve
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
      const n = V.nombre;
      V.ceniza.pedido = ahora;
      try {
        const r = await fetch("/api/mundos/" + n + "/dinamico/quemado");
        const ds = new DecompressionStream("deflate");
        const piped = r.body.pipeThrough(ds);
        const datos = new Uint8Array(await new Response(piped).arrayBuffer());
        if (n !== V.nombre) return;   // cambió el mundo: descartar este mapa de ceniza
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
      if (V.ceniza && V.ceniza.canvas && V.ceniza.v > 0) {
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(V.ceniza.canvas, vis.x0, vis.y0, vw, vh, vis.x0, vis.y0, vw, vh);
      }
      if (V.nieve && V.nieve.canvas && V.nieve.v > 0) {
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(V.nieve.canvas, vis.x0, vis.y0, vw, vh, vis.x0, vis.y0, vw, vh);
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
        if (Sprites && Sprites.estructura) {
          Sprites.estructura(ctx, tipo, x, y, u, z, esRuina.has(x + "," + y), ahora);
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
        if (!V._luzSprite) {
          const cL = document.createElement("canvas");
          cL.width = 64; cL.height = 64;
          const ctxL = cL.getContext("2d");
          const gL = ctxL.createRadialGradient(32, 32, 0, 32, 32, 32);
          gL.addColorStop(0, "rgba(0,0,0,1)");
          gL.addColorStop(1, "rgba(0,0,0,0)");
          ctxL.fillStyle = gL; ctxL.fillRect(0, 0, 64, 64);
          V._luzSprite = cL;
        }
        const hueco = (x, y, rad, fza) => {      // "agujero" de luz en la capa de noche con sprite pre-renderizado
          o.globalAlpha = fza;
          o.drawImage(V._luzSprite, x - vis.x0 - rad, y - vis.y0 - rad, rad * 2, rad * 2);
          o.globalAlpha = 1.0;
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
        if (!V._sombraHab) {
          const cS = document.createElement("canvas");
          cS.width = 16; cS.height = 16;
          const ctxS = cS.getContext("2d");
          const gS = ctxS.createRadialGradient(8, 8, 0, 8, 8, 8);
          gS.addColorStop(0, "rgba(0,0,0,0.55)"); gS.addColorStop(1, "rgba(0,0,0,0)");
          ctxS.fillStyle = gS; ctxS.fillRect(0, 0, 16, 16);
          V._sombraHab = cS;
        }
        for (const hb of Object.values(V.habs)) {
          if (!hb.d.vivo || !visible(hb.x, hb.y, 5)) continue;
          o.drawImage(V._sombraHab, hb.x - vis.x0 - 4, hb.y - vis.y0 - 4, 8, 8);
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

    // Referencias por si el caparazón (vivo.js) quiere exponerlas: no se invocan hoy.
    V.pedirNieve = pedirNieve;
    V.pedirCeniza = pedirCeniza;
  }

  root.Escena = { instalar: instalar };
})(typeof globalThis !== "undefined" ? globalThis : this);
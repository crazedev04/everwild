/* Mundo Vivo — sprites dibujados en código, sin archivos que bajar.
   Cada persona se dibuja una sola vez por combinación (edad, sexo, color, dirección, paso) y queda en caché:
   son canvas chiquitos, así que mover 60 personas es copiar 60 imágenes ya hechas.

   Vista de 3/4 desde arriba, como el resto del mapa. Cuatro edades, que es lo que pidió el usuario:
     cria   (niño, hasta los 12 años del mundo)   cabeza grande, cuerpo chico
     joven  (12 a 24)                             flaco, espigado
     adulto (24 a 45)                             hombros anchos
     viejo  (45 y más)                            encorvado, pelo blanco, bastón
*/
(function () {
  "use strict";

  const ALTO_PX = 64;                  // alto del sprite en píxeles de dibujo (mayor resolución para zoom cercano)
  const ANCHO_PX = 48;
  const DIAS_ANIO = 120;
  const cache = new Map();

  // Proporciones por edad: alto relativo, radio de cabeza, ancho de hombros, inclinación.
  const EDADES = {
    cria:   { alto: 0.58, cabeza: 0.180, hombros: 0.110, pelo: "#5a3d28", encorva: 0.00, baston: false },
    joven:  { alto: 0.84, cabeza: 0.135, hombros: 0.130, pelo: "#3d2a1d", encorva: 0.00, baston: false },
    adulto: { alto: 1.00, cabeza: 0.125, hombros: 0.160, pelo: "#2a1c12", encorva: 0.02, baston: false },
    viejo:  { alto: 0.92, cabeza: 0.125, hombros: 0.145, pelo: "#d8d3ca", encorva: 0.09, baston: true },
  };

  function edadDe(dias) {
    const a = (dias || 0) / DIAS_ANIO;
    return a < 12 ? "cria" : a < 24 ? "joven" : a < 45 ? "adulto" : "viejo";
  }

  // Aclara u oscurece un color #rrggbb. Sirve para sacar sombra y luz del mismo color de la persona.
  function tinte(hex, k) {
    if (!hex || hex[0] !== "#" || (hex.length !== 7 && hex.length !== 4)) return hex;
    const full = hex.length === 4 ? "#" + hex[1] + hex[1] + hex[2] + hex[2] + hex[3] + hex[3] : hex;
    const n = parseInt(full.slice(1), 16);
    const f = (c) => Math.max(0, Math.min(255, Math.round(c + (k > 0 ? (255 - c) * k : c * k))));
    return "rgb(" + f((n >> 16) & 255) + "," + f((n >> 8) & 255) + "," + f(n & 255) + ")";
  }

  const PIELES = ["#e8be96", "#d9a57c", "#c68a63", "#a9734f", "#8a5a3c"];

  /* Dibuja una persona con detalle y proporciones definidas.
     dir: 0 = hacia el observador, 1 = de espaldas, 2 = perfil derecho, 3 = perfil izquierdo.
     paso: 0, 1 o 2 (quieto, pierna adelante, pierna atrás). */
  function dibujar(ctx, edad, sexo, color, dir, paso, piel) {
    const E = EDADES[edad];
    const W = ANCHO_PX, H = ALTO_PX;
    const cx = W / 2;
    const pies = H - 2;
    const alto = H * E.alto;
    const rc = H * E.cabeza;                       // radio de la cabeza
    const hom = H * E.hombros;                     // medio ancho de hombros
    const yCabeza = pies - alto + rc;
    const yCuello = yCabeza + rc * 0.85;
    const yHombro = yCabeza + rc * 1.15;
    const yCintura = pies - alto * 0.44;
    const yFalda = edad === "cria" ? pies - alto * 0.25 : pies - alto * 0.32;
    const lean = alto * E.encorva;                 // los viejos van encorvados hacia adelante
    const perfil = dir >= 2;
    const lado = dir === 2 ? 1 : -1;
    const colorOscuro = tinte(color, -0.45);
    const colorClaro = tinte(color, 0.25);
    const colorSombra = tinte(color, -0.65);
    const cuero = "#422817";
    const cueroLuz = "#694228";
    const peloColor = E.pelo;

    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    // 1. PIES Y PIERNAS
    // Cálculo de zancada y flexión
    const zancada = paso === 0 ? 0.2 : paso === 1 ? 0.75 : -0.75;
    const piernaLargo = pies - yCintura;
    const piernaGrosor = Math.max(2.2, hom * 0.38);

    if (perfil) {
      // Perfil: dos piernas en tijera con botas de cuero
      const pAtr = cx + lean - lado * hom * (0.15 + zancada * 0.45);
      const pAde = cx + lean + lado * hom * (0.15 + zancada * 0.45);

      // Pierna trasera
      ctx.strokeStyle = colorSombra;
      ctx.lineWidth = piernaGrosor * 0.9;
      ctx.beginPath();
      ctx.moveTo(cx + lean, yCintura + 2);
      ctx.lineTo(pAtr, pies);
      ctx.stroke();

      // Bota trasera
      ctx.fillStyle = cuero;
      ctx.beginPath();
      ctx.ellipse(pAtr + lado * 1.5, pies - 1, piernaGrosor * 0.8, piernaGrosor * 0.5, 0, 0, 6.2832);
      ctx.fill();

      // Pierna delantera
      ctx.strokeStyle = colorOscuro;
      ctx.lineWidth = piernaGrosor;
      ctx.beginPath();
      ctx.moveTo(cx + lean, yCintura + 2);
      ctx.lineTo(pAde, pies);
      ctx.stroke();

      // Bota delantera
      ctx.fillStyle = cueroLuz;
      ctx.beginPath();
      ctx.ellipse(pAde + lado * 2, pies - 1, piernaGrosor * 0.9, piernaGrosor * 0.55, 0, 0, 6.2832);
      ctx.fill();
    } else {
      // Frente o Espalda
      const dxIzq = paso === 1 ? -hom * 0.65 : paso === 2 ? -hom * 0.35 : -hom * 0.45;
      const dxDer = paso === 1 ? hom * 0.35 : paso === 2 ? hom * 0.65 : hom * 0.45;
      const yPiesIzq = paso === 1 ? pies - 1.5 : pies;
      const yPiesDer = paso === 2 ? pies - 1.5 : pies;

      // Pantalón / calzas
      ctx.strokeStyle = colorOscuro;
      ctx.lineWidth = piernaGrosor;
      ctx.beginPath();
      ctx.moveTo(cx - hom * 0.35, yCintura + 2); ctx.lineTo(cx + dxIzq, yPiesIzq);
      ctx.moveTo(cx + hom * 0.35, yCintura + 2); ctx.lineTo(cx + dxDer, yPiesDer);
      ctx.stroke();

      // Botas
      ctx.fillStyle = cuero;
      ctx.beginPath();
      ctx.ellipse(cx + dxIzq, yPiesIzq, piernaGrosor * 0.8, piernaGrosor * 0.5, 0, 0, 6.2832);
      ctx.ellipse(cx + dxDer, yPiesDer, piernaGrosor * 0.8, piernaGrosor * 0.5, 0, 0, 6.2832);
      ctx.fill();
    }

    // 2. TÚNICA / ROPA DEL TORSO
    const homX = perfil ? hom * 0.65 : hom;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(cx - homX + lean, yHombro);
    ctx.lineTo(cx + homX + lean, yHombro);
    ctx.lineTo(cx + homX * 0.85 + (perfil ? lean * 0.5 : 0), yFalda);
    ctx.lineTo(cx - homX * 0.85 + (perfil ? lean * 0.5 : 0), yFalda);
    ctx.closePath();
    ctx.fill();

    // Sombreado y pliegues de la túnica
    ctx.fillStyle = colorClaro;
    ctx.beginPath();
    ctx.moveTo(cx - homX + lean, yHombro);
    ctx.lineTo(cx + homX + lean, yHombro);
    ctx.lineTo(cx + homX * 0.95 + lean, yHombro + 4);
    ctx.lineTo(cx - homX * 0.95 + lean, yHombro + 4);
    ctx.closePath();
    ctx.fill();

    // Cinturón de cuero con hebilla metálica
    ctx.fillStyle = cuero;
    const beltY = yCintura - 1;
    const bW = homX * (perfil ? 1.6 : 1.7);
    ctx.fillRect(cx - bW / 2 + (perfil ? lean * 0.6 : 0), beltY, bW, 2.8);
    if (dir !== 1) { // Hebilla visible al frente y perfil
      ctx.fillStyle = "#d4af37"; // oro/bronce
      const hbX = perfil ? cx + lado * homX * 0.45 + lean * 0.6 : cx;
      ctx.fillRect(hbX - 1.5, beltY - 0.5, 3, 3.8);
      ctx.fillStyle = "#222";
      ctx.fillRect(hbX - 0.7, beltY + 0.5, 1.4, 1.8);
    }

    // Cuello de la camisa / manto
    if (dir === 0) { // Frente: cuello en V con túnica interior
      ctx.fillStyle = piel;
      ctx.beginPath();
      ctx.moveTo(cx - homX * 0.28, yHombro);
      ctx.lineTo(cx, yHombro + rc * 0.65);
      ctx.lineTo(cx + homX * 0.28, yHombro);
      ctx.closePath();
      ctx.fill();
    }

    // 3. BRAZOS Y MANOS
    const brazoAng = paso === 0 ? 0.1 : paso === 1 ? -0.55 : 0.55;
    const brazoGrosor = Math.max(2.0, hom * 0.32);

    if (perfil) {
      // Perfil: brazo oscilante con mano
      const bX = cx + lean + lado * hom * (0.2 + brazoAng * 0.5);
      const bY = yCintura + 3;
      ctx.strokeStyle = colorClaro;
      ctx.lineWidth = brazoGrosor;
      ctx.beginPath();
      ctx.moveTo(cx + lean, yHombro + 2);
      ctx.lineTo(bX, bY);
      ctx.stroke();

      // Mano
      ctx.fillStyle = piel;
      ctx.beginPath();
      ctx.arc(bX + lado * 1.0, bY + 1.0, brazoGrosor * 0.65, 0, 6.2832);
      ctx.fill();
    } else {
      // Frente y Espalda: dos brazos
      const bIzqX = cx - homX * (1.0 + brazoAng * 0.35);
      const bDerX = cx + homX * (1.0 - brazoAng * 0.35);
      const bY = yCintura + 2;

      ctx.strokeStyle = colorOscuro;
      ctx.lineWidth = brazoGrosor;
      ctx.beginPath();
      ctx.moveTo(cx - homX * 0.9, yHombro + 2); ctx.lineTo(bIzqX, bY);
      ctx.moveTo(cx + homX * 0.9, yHombro + 2); ctx.lineTo(bDerX, bY);
      ctx.stroke();

      // Manos
      ctx.fillStyle = piel;
      ctx.beginPath();
      ctx.arc(bIzqX - 0.5, bY + 1.5, brazoGrosor * 0.65, 0, 6.2832);
      ctx.arc(bDerX + 0.5, bY + 1.5, brazoGrosor * 0.65, 0, 6.2832);
      ctx.fill();
    }

    // 4. BASTÓN DE MADERA DEL VIEJO
    if (E.baston) {
      ctx.strokeStyle = "#5a3a1f";
      ctx.lineWidth = 2.0;
      const bx = cx + (perfil ? lado * hom * 1.25 + lean : homX * 1.35);
      ctx.beginPath();
      ctx.moveTo(bx - (perfil ? lado * 1.5 : 1), yHombro);
      // Empuñadura curvada
      ctx.quadraticCurveTo(bx + (perfil ? lado * 2 : 2), yHombro - 3, bx + (perfil ? lado * 1 : 1), yHombro + 2);
      ctx.lineTo(bx + hom * 0.1, pies);
      ctx.stroke();
    }

    // 5. CABEZA, CARA Y RASGOS FACIALES
    const xCabeza = cx + lean * 1.3 + (perfil ? lado * rc * 0.18 : 0);

    // Cuello
    ctx.fillStyle = tinte(piel, -0.15);
    ctx.fillRect(xCabeza - rc * 0.25, yCuello - 1, rc * 0.5, rc * 0.45);

    // Cabeza base
    ctx.fillStyle = piel;
    ctx.beginPath();
    ctx.arc(xCabeza, yCabeza, rc, 0, 6.2832);
    ctx.fill();

    // Rasgos de cara (ojos, cejas, mejillas, barba)
    if (dir !== 1) { // Si no está de espaldas
      if (perfil) {
        const eyeX = xCabeza + lado * rc * 0.48;
        const eyeY = yCabeza - rc * 0.08;

        // Nariz perfil
        ctx.fillStyle = tinte(piel, -0.12);
        ctx.beginPath();
        ctx.moveTo(xCabeza + lado * rc * 0.8, eyeY - 1);
        ctx.lineTo(xCabeza + lado * (rc * 1.15), eyeY + 2);
        ctx.lineTo(xCabeza + lado * rc * 0.75, eyeY + 3.5);
        ctx.closePath();
        ctx.fill();

        // Ojo
        ctx.fillStyle = "#1e1510";
        ctx.beginPath();
        ctx.arc(eyeX, eyeY, Math.max(1.1, rc * 0.14), 0, 6.2832);
        ctx.fill();

        // Ceja
        ctx.strokeStyle = peloColor;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(eyeX - lado * 1.5, eyeY - 2.2);
        ctx.lineTo(eyeX + lado * 1.5, eyeY - 2.0);
        ctx.stroke();

        // Barba para viejo o adulto macho
        if (edad === "viejo" || (edad === "adulto" && sexo === "M")) {
          ctx.fillStyle = edad === "viejo" ? peloColor : tinte(peloColor, -0.15);
          ctx.beginPath();
          ctx.moveTo(xCabeza + lado * rc * 0.3, yCabeza + rc * 0.4);
          ctx.lineTo(xCabeza + lado * rc * 1.05, yCabeza + rc * 0.5);
          ctx.lineTo(xCabeza + lado * (rc * (edad === "viejo" ? 0.9 : 0.6)), yCabeza + rc * (edad === "viejo" ? 1.45 : 1.1));
          ctx.lineTo(xCabeza, yCabeza + rc * 0.85);
          ctx.closePath();
          ctx.fill();
        }
      } else {
        // Frente
        const eyeSep = rc * 0.42;
        const eyeY = yCabeza - rc * 0.05;

        // Ojos
        ctx.fillStyle = "#1a130e";
        ctx.beginPath();
        ctx.arc(xCabeza - eyeSep, eyeY, Math.max(1.2, rc * 0.13), 0, 6.2832);
        ctx.arc(xCabeza + eyeSep, eyeY, Math.max(1.2, rc * 0.13), 0, 6.2832);
        ctx.fill();

        // Brillo en los ojos
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(xCabeza - eyeSep - 0.4, eyeY - 0.7, 0.9, 0.9);
        ctx.fillRect(xCabeza + eyeSep - 0.4, eyeY - 0.7, 0.9, 0.9);

        // Cejas
        ctx.strokeStyle = peloColor;
        ctx.lineWidth = 1.3;
        ctx.beginPath();
        ctx.moveTo(xCabeza - eyeSep - 2.0, eyeY - 2.4); ctx.lineTo(xCabeza - eyeSep + 1.8, eyeY - 2.2);
        ctx.moveTo(xCabeza + eyeSep - 1.8, eyeY - 2.2); ctx.lineTo(xCabeza + eyeSep + 2.0, eyeY - 2.4);
        ctx.stroke();

        // Boca / bigote
        if (edad === "viejo" || (edad === "adulto" && sexo === "M")) {
          // Barba completa y bigote
          ctx.fillStyle = edad === "viejo" ? peloColor : tinte(peloColor, -0.15);
          ctx.beginPath();
          ctx.ellipse(xCabeza, yCabeza + rc * 0.75, rc * 0.65, rc * (edad === "viejo" ? 0.65 : 0.4), 0, 0, 6.2832);
          ctx.fill();
        } else {
          // Labios sutiles
          ctx.fillStyle = tinte(piel, -0.25);
          ctx.fillRect(xCabeza - 1.5, yCabeza + rc * 0.45, 3.0, 1.2);
        }

        // Mejillas rosadas en niños (cría)
        if (edad === "cria") {
          ctx.fillStyle = "rgba(235, 120, 110, 0.35)";
          ctx.beginPath();
          ctx.arc(xCabeza - eyeSep - 1.0, eyeY + 2.8, 2.2, 0, 6.2832);
          ctx.arc(xCabeza + eyeSep + 1.0, eyeY + 2.8, 2.2, 0, 6.2832);
          ctx.fill();
        }
      }
    }

    // 6. CABELLO Y PEINADO
    ctx.fillStyle = peloColor;
    if (dir === 1) {
      // De espaldas: cabello cubre casi toda la cabeza
      ctx.beginPath();
      ctx.arc(xCabeza, yCabeza, rc * 1.04, 0, 6.2832);
      ctx.fill();
      if (sexo === "F") { // Trenza o melena larga en la espalda
        ctx.beginPath();
        ctx.rect(xCabeza - rc * 0.45, yCabeza + rc * 0.3, rc * 0.9, rc * 1.1);
        ctx.fill();
      }
    } else {
      // Vista frontal o lateral
      ctx.beginPath();
      ctx.arc(xCabeza, yCabeza, rc * 1.04, Math.PI * (perfil ? 0.72 : 0.88), Math.PI * (perfil ? 2.18 : 2.12));
      ctx.fill();

      // Flequillo / mechones
      ctx.beginPath();
      if (perfil) {
        ctx.ellipse(xCabeza - lado * rc * 0.25, yCabeza - rc * 0.75, rc * 0.85, rc * 0.5, 0, 0, 6.2832);
      } else {
        ctx.ellipse(xCabeza, yCabeza - rc * 0.75, rc * 0.92, rc * 0.45, 0, 0, 6.2832);
      }
      ctx.fill();

      // Cabello largo en mujeres (melena a los costados)
      if (sexo === "F") {
        ctx.beginPath();
        if (perfil) {
          ctx.ellipse(xCabeza - lado * rc * 0.5, yCabeza + rc * 0.45, rc * 0.55, rc * 0.95, 0, 0, 6.2832);
        } else {
          ctx.ellipse(xCabeza - rc * 0.85, yCabeza + rc * 0.4, rc * 0.38, rc * 0.85, 0, 0, 6.2832);
          ctx.ellipse(xCabeza + rc * 0.85, yCabeza + rc * 0.4, rc * 0.38, rc * 0.85, 0, 0, 6.2832);
        }
        ctx.fill();
      }
    }
  }

  function persona(edadDias, sexo, color, dir, paso) {
    const edad = edadDe(edadDias);
    const piel = PIELES[Math.abs(hash(color + sexo)) % PIELES.length];
    const clave = edad + "|" + sexo + "|" + color + "|" + dir + "|" + paso;
    let cv = cache.get(clave);
    if (cv) return cv;
    cv = document.createElement("canvas");
    cv.width = ANCHO_PX; cv.height = ALTO_PX;
    const c = cv.getContext("2d");
    dibujar(c, edad, sexo, color, dir, paso, piel);
    cache.set(clave, cv);
    return cv;
  }

  function hash(s) {
    let h = 2166136261;
    s = String(s);
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = (h * 16777619) | 0; }
    return h;
  }

  /* Dirección a partir de cuánto se movió desde el frame anterior. Si está quieto, mantiene la última. */
  function direccion(dx, dy, previa) {
    if (Math.abs(dx) < 1e-4 && Math.abs(dy) < 1e-4) return previa || 0;
    if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? 2 : 3;
    return dy > 0 ? 0 : 1;
  }

  /* ----------------------------------------------------------------- animales
     Una forma por clase, vista de 3/4 desde arriba. El largo sale del peso real de la especie
     (ver datos_base/fauna/especies.json), así un ratón de 50 g y un mamut de 30 t no se dibujan igual. */
  const A_PX = 32;                       // lienzo del sprite de animal (cuadrado)

  // clase -> (color de lomo, color de panza)
  const PELAJE = {
    mamifero:  ["#8a6a46", "#b79470"], ave: ["#6f7f9a", "#c9d3e0"], reptil: ["#5f7a4a", "#8aa06a"],
    pez:       ["#4b7f9b", "#a9ccd9"], anfibio: ["#5d8a55", "#9cc08a"], insecto: ["#4a4238", "#6b5f4e"],
    aracnido:  ["#3b332c", "#5a4f44"], molusco: ["#7a6a7f", "#a596a8"], crustaceo: ["#9b5a46", "#c08a72"],
    cnidario:  ["#9a7fb0", "#cdb8dd"],
  };

  /* Largo del bicho en metros, a partir del peso. Crece con la raíz cúbica (el volumen va al cubo del largo):
     0,05 kg -> 0,17 m (ratón)   120 kg -> 2,2 m (ciervo)   30000 kg -> 14 m (ballena). */
  function largoM(peso) {
    return 0.45 * Math.cbrt(Math.max(0.001, peso || 1));
  }

  function dibujarAnimal(ctx, clase, peligroso) {
    const [lomo, panza] = PELAJE[clase] || PELAJE.mamifero;
    const C = A_PX / 2;
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    const L = A_PX * 0.80, An = A_PX * 0.34;     // el bicho mira al este; el dibujo lo rota quien lo pinta

    if (clase === "ave") {
      ctx.fillStyle = lomo;                       // cuerpo en gota
      ctx.beginPath(); ctx.ellipse(C, C, L * 0.30, An * 0.52, 0, 0, 6.2832); ctx.fill();
      ctx.fillStyle = panza;                      // alas abiertas
      ctx.beginPath(); ctx.ellipse(C - L * 0.05, C - An * 0.55, L * 0.26, An * 0.3, -0.45, 0, 6.2832); ctx.fill();
      ctx.beginPath(); ctx.ellipse(C - L * 0.05, C + An * 0.55, L * 0.26, An * 0.3, 0.45, 0, 6.2832); ctx.fill();
      ctx.fillStyle = lomo;                       // cabeza y pico
      ctx.beginPath(); ctx.arc(C + L * 0.30, C, An * 0.26, 0, 6.2832); ctx.fill();
      ctx.fillStyle = "#d8a24a";
      ctx.beginPath(); ctx.moveTo(C + L * 0.40, C - An * 0.1); ctx.lineTo(C + L * 0.52, C);
      ctx.lineTo(C + L * 0.40, C + An * 0.1); ctx.closePath(); ctx.fill();
    } else if (clase === "pez" || clase === "cnidario") {
      ctx.fillStyle = lomo;                       // cuerpo fusiforme
      ctx.beginPath(); ctx.ellipse(C, C, L * 0.36, An * 0.44, 0, 0, 6.2832); ctx.fill();
      ctx.fillStyle = panza;
      ctx.beginPath(); ctx.ellipse(C, C + An * 0.16, L * 0.30, An * 0.26, 0, 0, 6.2832); ctx.fill();
      ctx.fillStyle = lomo;                       // cola
      ctx.beginPath(); ctx.moveTo(C - L * 0.34, C); ctx.lineTo(C - L * 0.52, C - An * 0.38);
      ctx.lineTo(C - L * 0.52, C + An * 0.38); ctx.closePath(); ctx.fill();
    } else if (clase === "insecto" || clase === "aracnido") {
      const patas = clase === "aracnido" ? 4 : 3;
      ctx.strokeStyle = lomo; ctx.lineWidth = An * 0.1;
      ctx.beginPath();
      for (let i = 0; i < patas; i++) {
        const px = C - L * 0.14 + (i / Math.max(1, patas - 1)) * L * 0.3;
        ctx.moveTo(px, C - An * 0.15); ctx.lineTo(px - An * 0.1, C - An * 0.6);
        ctx.moveTo(px, C + An * 0.15); ctx.lineTo(px - An * 0.1, C + An * 0.6);
      }
      ctx.stroke();
      ctx.fillStyle = lomo;
      ctx.beginPath(); ctx.ellipse(C - L * 0.1, C, L * 0.2, An * 0.3, 0, 0, 6.2832); ctx.fill();
      ctx.beginPath(); ctx.arc(C + L * 0.18, C, An * 0.24, 0, 6.2832); ctx.fill();
    } else {
      // cuadrúpedo: mamífero, reptil, anfibio y el resto
      const bajo = clase === "reptil" || clase === "anfibio";
      const alto = bajo ? An * 0.34 : An * 0.46;
      ctx.strokeStyle = "#4a3a2a"; ctx.lineWidth = An * 0.13;   // patas
      ctx.beginPath();
      for (const px of [-L * 0.24, L * 0.22]) {
        ctx.moveTo(C + px, C - alto * 0.5); ctx.lineTo(C + px - L * 0.04, C - An * 0.72);
        ctx.moveTo(C + px, C + alto * 0.5); ctx.lineTo(C + px - L * 0.04, C + An * 0.72);
      }
      ctx.stroke();
      ctx.fillStyle = lomo;                                      // tronco
      ctx.beginPath(); ctx.ellipse(C - L * 0.03, C, L * 0.35, alto, 0, 0, 6.2832); ctx.fill();
      ctx.fillStyle = panza;
      ctx.beginPath(); ctx.ellipse(C - L * 0.03, C + alto * 0.3, L * 0.3, alto * 0.45, 0, 0, 6.2832); ctx.fill();
      ctx.strokeStyle = lomo; ctx.lineWidth = An * 0.12;         // cola
      ctx.beginPath(); ctx.moveTo(C - L * 0.36, C); ctx.lineTo(C - L * 0.52, C - An * (bajo ? 0.05 : 0.25)); ctx.stroke();
      ctx.fillStyle = lomo;                                      // cabeza
      ctx.beginPath(); ctx.ellipse(C + L * 0.36, C, An * 0.3, An * 0.26, 0, 0, 6.2832); ctx.fill();
      if (peligroso) {                                           // los que muerden muestran el ojo
        ctx.fillStyle = "#e8513a";
        ctx.beginPath(); ctx.arc(C + L * 0.40, C - An * 0.08, An * 0.08, 0, 6.2832); ctx.fill();
      }
    }
  }

  function animal(clase, peligroso) {
    const clave = "A|" + clase + "|" + (peligroso ? 1 : 0);
    let cv = cache.get(clave);
    if (cv) return cv;
    cv = document.createElement("canvas");
    cv.width = A_PX; cv.height = A_PX;
    dibujarAnimal(cv.getContext("2d"), clase, peligroso);
    cache.set(clave, cv);
    return cv;
  }

  /* Dibuja estructuras y construcciones: casas de piedra, hornos, fraguas, pilas, dinamos, ruinas, etc. */
  function estructura(ctx, tipo, x, y, u, z, esRuina, ahora) {
    ahora = ahora || 0;
    // Sombra en el suelo
    ctx.fillStyle = "rgba(0,0,0,0.32)";
    ctx.beginPath();
    ctx.ellipse(x, y + 0.45 * u, u * 1.05, 0.35 * u, 0, 0, 6.2832);
    ctx.fill();

    // 1. RUINA: muro roto, vigas cruzadas, escombros, maleza
    if (esRuina) {
      ctx.fillStyle = "#4a453f";
      ctx.fillRect(x - 0.7 * u, y - 0.1 * u, 1.4 * u, 0.45 * u);
      ctx.fillStyle = "#38332d";
      ctx.fillRect(x - 0.6 * u, y - 0.25 * u, 0.4 * u, 0.3 * u);
      ctx.fillRect(x + 0.2 * u, y - 0.2 * u, 0.35 * u, 0.25 * u);
      ctx.strokeStyle = "#2b2015";
      ctx.lineWidth = 0.12 * u;
      ctx.beginPath();
      ctx.moveTo(x - 0.65 * u, y - 0.3 * u); ctx.lineTo(x + 0.3 * u, y + 0.2 * u);
      ctx.moveTo(x + 0.5 * u, y - 0.25 * u); ctx.lineTo(x - 0.2 * u, y + 0.25 * u);
      ctx.stroke();
      ctx.fillStyle = "#4d6b38";
      ctx.beginPath();
      ctx.arc(x - 0.3 * u, y + 0.1 * u, 0.18 * u, 0, 6.2832);
      ctx.arc(x + 0.4 * u, y + 0.05 * u, 0.15 * u, 0, 6.2832);
      ctx.fill();
      return;
    }

    // 2. HORNO DE BARRO: cúpula de arcilla cocida, boca en arco con fuego titilante
    if (tipo.indexOf("horno") >= 0) {
      ctx.fillStyle = "#9c4a2f";
      ctx.beginPath();
      ctx.ellipse(x, y - 0.1 * u, 0.75 * u, 0.75 * u, 0, 0, 6.2832);
      ctx.fill();
      ctx.fillStyle = "#b85c3b";
      ctx.beginPath();
      ctx.ellipse(x, y - 0.25 * u, 0.55 * u, 0.45 * u, 0, 0, 6.2832);
      ctx.fill();
      ctx.fillStyle = "#260e05";
      ctx.beginPath();
      ctx.ellipse(x, y + 0.12 * u, 0.32 * u, 0.38 * u, 0, 0, 6.2832);
      ctx.fill();
      const rF = 0.08 + 0.04 * Math.sin(ahora * 0.01 + x);
      const gF = ctx.createRadialGradient(x, y + 0.18 * u, 0, x, y + 0.18 * u, 0.28 * u);
      gF.addColorStop(0, "#fff5aa");
      gF.addColorStop(0.4, "#f59e0b");
      gF.addColorStop(1, "rgba(220, 38, 38, 0)");
      ctx.fillStyle = gF;
      ctx.beginPath();
      ctx.arc(x, y + 0.18 * u, 0.22 * u + rF, 0, 6.2832);
      ctx.fill();
      ctx.fillStyle = "rgba(180, 175, 170, 0.4)";
      ctx.beginPath();
      ctx.arc(x, y - 0.9 * u, 0.15 * u, 0, 6.2832);
      ctx.fill();
      return;
    }

    // 3. FRAGUA: base de piedra, carbones al rojo vivo y yunque oscuro
    if (tipo.indexOf("fragua") >= 0) {
      ctx.fillStyle = "#474d57";
      ctx.fillRect(x - 0.85 * u, y - 0.2 * u, 1.7 * u, 0.65 * u);
      ctx.fillStyle = "#dc2626";
      ctx.fillRect(x - 0.7 * u, y - 0.15 * u, 0.65 * u, 0.3 * u);
      ctx.fillStyle = "#f59e0b";
      ctx.fillRect(x - 0.6 * u, y - 0.1 * u, 0.45 * u, 0.18 * u);
      ctx.fillStyle = "#1e242d";
      ctx.fillRect(x + 0.1 * u, y - 0.15 * u, 0.55 * u, 0.45 * u);
      ctx.fillStyle = "#333d4b";
      ctx.fillRect(x + 0.02 * u, y - 0.35 * u, 0.72 * u, 0.22 * u);
      if (Math.sin(ahora * 0.015 + y) > 0.3) {
        ctx.fillStyle = "#fef08a";
        ctx.fillRect(x + 0.25 * u, y - 0.55 * u, 0.08 * u, 0.08 * u);
      }
      return;
    }

    // 4. CASA DE PIEDRA: sillares de cantería, tejado de pizarra, chimenea
    if (tipo.indexOf("casa_de_piedra") >= 0 || (tipo.indexOf("piedra") >= 0 && tipo.indexOf("muro") < 0)) {
      ctx.fillStyle = "#5d6775";
      ctx.fillRect(x - 0.85 * u, y - 0.25 * u, 1.7 * u, 0.75 * u);
      ctx.strokeStyle = "#404752";
      ctx.lineWidth = Math.max(0.04, 0.8 / (ctx.canvas.width / 100 || 50));
      ctx.beginPath();
      ctx.moveTo(x - 0.85 * u, y); ctx.lineTo(x + 0.85 * u, y);
      ctx.moveTo(x - 0.85 * u, y + 0.25 * u); ctx.lineTo(x + 0.85 * u, y + 0.25 * u);
      ctx.stroke();
      ctx.fillStyle = "#273140";
      ctx.beginPath();
      ctx.moveTo(x - 1.1 * u, y - 0.22 * u);
      ctx.lineTo(x, y - 1.15 * u);
      ctx.lineTo(x + 1.1 * u, y - 0.22 * u);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = "#331f12";
      ctx.fillRect(x - 0.22 * u, y + 0.08 * u, 0.44 * u, 0.42 * u);
      ctx.fillStyle = "#4a5360";
      ctx.fillRect(x + 0.5 * u, y - 1.05 * u, 0.24 * u, 0.55 * u);
      return;
    }

    // 5. PILA (Batería): celda galvánica con electrodos de cobre y zinc
    if (tipo.indexOf("pila") >= 0) {
      ctx.fillStyle = "#2a4358";
      ctx.fillRect(x - 0.45 * u, y - 0.1 * u, 0.9 * u, 0.65 * u);
      ctx.fillStyle = "#d97706";
      ctx.fillRect(x - 0.32 * u, y - 0.45 * u, 0.18 * u, 0.55 * u);
      ctx.fillStyle = "#94a3b8";
      ctx.fillRect(x + 0.14 * u, y - 0.45 * u, 0.18 * u, 0.55 * u);
      ctx.fillStyle = "rgba(91, 170, 240, 0.25)";
      ctx.beginPath();
      ctx.arc(x, y - 0.1 * u, 0.7 * u, 0, 6.2832);
      ctx.fill();
      return;
    }

    // 6. DINAMO: generador eléctrico, bobina de cobre, eje y descarga
    if (tipo.indexOf("dinamo") >= 0) {
      ctx.fillStyle = "#1e293b";
      ctx.fillRect(x - 0.75 * u, y - 0.15 * u, 1.5 * u, 0.65 * u);
      ctx.fillStyle = "#b45309";
      ctx.beginPath();
      ctx.ellipse(x, y - 0.15 * u, 0.55 * u, 0.4 * u, 0, 0, 6.2832);
      ctx.fill();
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth = 0.06 * u;
      ctx.beginPath();
      ctx.moveTo(x - 0.35 * u, y - 0.45 * u); ctx.lineTo(x - 0.35 * u, y + 0.15 * u);
      ctx.moveTo(x, y - 0.52 * u); ctx.lineTo(x, y + 0.22 * u);
      ctx.moveTo(x + 0.35 * u, y - 0.45 * u); ctx.lineTo(x + 0.35 * u, y + 0.15 * u);
      ctx.stroke();
      ctx.fillStyle = "#cbd5e1";
      ctx.beginPath();
      ctx.arc(x, y - 0.15 * u, 0.15 * u, 0, 6.2832);
      ctx.fill();
      if (Math.sin(ahora * 0.02 + x) > 0.4) {
        ctx.strokeStyle = "#60a5fa";
        ctx.lineWidth = 0.08 * u;
        ctx.beginPath();
        ctx.moveTo(x - 0.6 * u, y - 0.4 * u);
        ctx.lineTo(x - 0.4 * u, y - 0.7 * u);
        ctx.lineTo(x - 0.1 * u, y - 0.5 * u);
        ctx.stroke();
      }
      return;
    }

    // 7. CALLE EMPEDRADA
    if (tipo.indexOf("calle") >= 0 || tipo.indexOf("empedrad") >= 0) {
      ctx.fillStyle = "#64635e";
      ctx.fillRect(x - u, y - 0.5 * u, 2 * u, u);
      ctx.strokeStyle = "#44433f";
      ctx.lineWidth = 0.06 * u;
      ctx.strokeRect(x - u, y - 0.5 * u, 2 * u, u);
      return;
    }

    // 8. MURO DE PIEDRA (con almenas)
    if (tipo.indexOf("muro") === 0) {
      ctx.fillStyle = "#717985";
      ctx.fillRect(x - 1.05 * u, y - 0.25 * u, 2.1 * u, 0.65 * u);
      ctx.fillStyle = "#828b97";
      for (let mx = -0.9 * u; mx <= 0.8 * u; mx += 0.5 * u) {
        ctx.fillRect(x + mx, y - 0.45 * u, 0.25 * u, 0.22 * u);
      }
      return;
    }

    // 9. CABAÑA DE TRONCOS
    if (tipo.indexOf("troncos") >= 0 || tipo.indexOf("cabana") >= 0) {
      ctx.fillStyle = "#6b3f1f";
      ctx.fillRect(x - 0.8 * u, y - 0.2 * u, 1.6 * u, 0.7 * u);
      ctx.strokeStyle = "#4d2b14";
      ctx.lineWidth = 0.06 * u;
      ctx.beginPath();
      ctx.moveTo(x - 0.8 * u, y); ctx.lineTo(x + 0.8 * u, y);
      ctx.moveTo(x - 0.8 * u, y + 0.25 * u); ctx.lineTo(x + 0.8 * u, y + 0.25 * u);
      ctx.stroke();
      ctx.fillStyle = "#523018";
      ctx.beginPath();
      ctx.moveTo(x - 1.05 * u, y - 0.18 * u); ctx.lineTo(x, y - 0.95 * u); ctx.lineTo(x + 1.05 * u, y - 0.18 * u);
      ctx.closePath(); ctx.fill();
      ctx.fillStyle = "#2d190b";
      ctx.fillRect(x - 0.2 * u, y + 0.08 * u, 0.4 * u, 0.42 * u);
      return;
    }

    // 10. CHOZA DE BARRO / ADOBE
    if (tipo.indexOf("barro") >= 0) {
      ctx.fillStyle = "#a87144";
      ctx.fillRect(x - 0.75 * u, y - 0.2 * u, 1.5 * u, 0.7 * u);
      ctx.fillStyle = "#d4a843";
      ctx.beginPath();
      ctx.moveTo(x - 1.0 * u, y - 0.18 * u); ctx.lineTo(x, y - 0.9 * u); ctx.lineTo(x + 1.0 * u, y - 0.18 * u);
      ctx.closePath(); ctx.fill();
      ctx.fillStyle = "#3a1e0c";
      ctx.fillRect(x - 0.2 * u, y + 0.08 * u, 0.4 * u, 0.42 * u);
      return;
    }

    // 11. TIENDA DE PIEL / CUERO (Teepee)
    if (tipo.indexOf("tienda") === 0) {
      ctx.strokeStyle = "#5a3a1e";
      ctx.lineWidth = 0.08 * u;
      ctx.beginPath();
      ctx.moveTo(x - 0.25 * u, y - 1.35 * u); ctx.lineTo(x + 0.25 * u, y - 0.9 * u);
      ctx.moveTo(x + 0.25 * u, y - 1.35 * u); ctx.lineTo(x - 0.25 * u, y - 0.9 * u);
      ctx.stroke();
      ctx.fillStyle = tipo.indexOf("cuero") >= 0 ? "#784b2c" : "#8a5d3c";
      ctx.beginPath();
      ctx.moveTo(x - 0.85 * u, y + 0.45 * u);
      ctx.lineTo(x, y - 1.15 * u);
      ctx.lineTo(x + 0.85 * u, y + 0.45 * u);
      ctx.closePath(); ctx.fill();
      ctx.fillStyle = "#2d1607";
      ctx.beginPath();
      ctx.moveTo(x - 0.18 * u, y + 0.45 * u);
      ctx.lineTo(x, y + 0.05 * u);
      ctx.lineTo(x + 0.18 * u, y + 0.45 * u);
      ctx.closePath(); ctx.fill();
      return;
    }

    // 12. CHOZA DE RAMAS / REFUGIO DE PAJA (por defecto)
    ctx.fillStyle = "#b89058";
    ctx.fillRect(x - 0.7 * u, y - 0.2 * u, 1.4 * u, 0.65 * u);
    ctx.fillStyle = "#d4b359";
    ctx.beginPath();
    ctx.moveTo(x - 0.95 * u, y - 0.18 * u); ctx.lineTo(x, y - 0.88 * u); ctx.lineTo(x + 0.95 * u, y - 0.18 * u);
    ctx.closePath(); ctx.fill();
    ctx.fillStyle = "#3d2a13";
    ctx.fillRect(x - 0.18 * u, y + 0.08 * u, 0.36 * u, 0.37 * u);
  }

  window.Sprites = { persona: persona, edadDe: edadDe, direccion: direccion, animal: animal, largoM: largoM,
                     estructura: estructura, ANCHO_PX: ANCHO_PX, ALTO_PX: ALTO_PX, A_PX: A_PX, EDADES: EDADES };
})();

"""
Generador procedural de continentes (Fase 1).

Misma semilla + misma VERSION_GENERADOR  =>  mismo mapa.
Si se cambia el algoritmo hay que subir VERSION_GENERADOR; los mundos ya
guardados conservan su mapa porque se guarda el resultado, no la receta.

Orden de generación:
  1. Relieve (continente + montañas) y nivel del mar
  2. Volcanes
  3. Temperatura (latitud + altura)
  4. Precipitación (viento húmedo que descarga lluvia contra las montañas)
  5. Hidrología (ríos, lagos, cascadas) con "priority-flood"
  6. Humedad final y biomas (temperatura x humedad x altura)
"""
from __future__ import annotations

import heapq
from typing import Dict, List, Tuple

import numpy as np

from . import biomas as B
from .ruido import fbm, suavizar

VERSION_GENERADOR = "1.0.0"
ALTURA_MAX_M = 3000.0
PROFUNDIDAD_MAX_M = 3000.0

# tipos de dato con que se guarda cada capa
DTYPES = {
    "elevacion": np.int16,    # metros sobre el nivel del mar (negativo = fondo marino)
    "temperatura": np.int8,   # grados C
    "humedad": np.uint8,      # 0..255
    "bioma": np.uint8,        # ver biomas.py
    "agua": np.uint8,         # 0 ninguna, 1 oceano, 2 lago, 3 rio
    "caudal": np.uint8,       # 0..255 (solo rios)
    "rasgos": np.uint8,       # bits: 1 cascada, 2 lava
}


# ---------------------------------------------------------------- utilidades

def _dilatar(m: np.ndarray, ocho: bool = True) -> np.ndarray:
    h, w = m.shape
    p = np.pad(m, 1, mode="constant")
    out = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            if not ocho and dy != 0 and dx != 0:
                continue
            out |= p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
    return out


def _dist_agua(agua: np.ndarray, maxd: int = 6) -> np.ndarray:
    dist = np.full(agua.shape, maxd + 1, dtype=np.int16)
    dist[agua] = 0
    frente = agua.copy()
    visto = agua.copy()
    for k in range(1, maxd + 1):
        nuevo = _dilatar(frente, ocho=False) & ~visto
        dist[nuevo] = k
        visto |= nuevo
        frente = nuevo
    return dist


def _seleccionar_lagos(mask: np.ndarray, prof: np.ndarray, minimo: int, maximo: int) -> np.ndarray:
    """Conserva como lago las depresiones de tamaño razonable. Si una depresión es enorme,
    solo queda como lago su parte más profunda (el resto pasa a ser llanura)."""
    h, w = mask.shape
    visto = np.zeros_like(mask)
    out = mask.copy()
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if visto[y0, x0]:
            continue
        comp = [(y0, x0)]
        visto[y0, x0] = True
        k = 0
        while k < len(comp):
            y, x = comp[k]
            k += 1
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not visto[yy, xx]:
                    visto[yy, xx] = True
                    comp.append((yy, xx))
        if len(comp) < minimo:
            for y, x in comp:
                out[y, x] = False
        elif len(comp) > maximo:
            orden = sorted(comp, key=lambda c: (-prof[c[0], c[1]], c[0], c[1]))
            for y, x in orden[maximo:]:
                out[y, x] = False
    return out


# ------------------------------------------------------------------- relieve

def _relieve(X, Y, w, h, s) -> np.ndarray:
    wx = X + (fbm(X, Y, w / 4, 3, s + 1) - 0.5) * w * 0.30
    wy = Y + (fbm(X, Y, w / 4, 3, s + 2) - 0.5) * h * 0.30
    nx = wx / w * 2 - 1
    ny = wy / h * 2 - 1
    d = np.sqrt(nx ** 2 + ny ** 2)
    continente = np.clip(1.0 - d ** 1.8, -0.4, 1.0)
    base = fbm(X, Y, w / 5, 5, s + 3)
    cresta = 1.0 - np.abs(2 * fbm(X, Y, w / 6, 4, s + 4) - 1)
    interior = np.clip((continente - 0.15) / 0.45, 0, 1)
    interior = interior * interior * (3 - 2 * interior)
    montanas = cresta ** 2 * interior
    # el océano siempre rodea al continente: la tierra cae hacia los bordes del mapa
    borde = np.minimum(np.minimum(X, w - 1 - X), np.minimum(Y, h - 1 - Y)) / (0.10 * min(w, h))
    borde = np.clip(borde, 0.0, 1.0)
    borde = borde * borde * (3 - 2 * borde)
    return 0.50 * continente + 0.22 * base + 0.45 * montanas - (1.0 - borde) * 0.8


def _a_metros(e: np.ndarray, mar: float) -> np.ndarray:
    emax, emin = float(e.max()), float(e.min())
    tierra = e >= mar
    out = np.empty_like(e)
    out[tierra] = ((e[tierra] - mar) / (emax - mar)) ** 1.6 * ALTURA_MAX_M
    out[~tierra] = -((mar - e[~tierra]) / (mar - emin)) * PROFUNDIDAD_MAX_M
    return out


def _volcanes(elev: np.ndarray, s: int, cfg: Optional[dict] = None) -> List[Tuple[int, int]]:
    """Coloca 1 o 2 volcanes sobre las cumbres más altas. Modifica elev. Los umbrales vienen del preset."""
    cfg = cfg or {}
    alt_min = float(cfg.get("altura_min_m", 1200))
    realce = float(cfg.get("realce_m", 450.0))
    crater = float(cfg.get("crater_m", -250.0))
    h, w = elev.shape
    yy, xx = np.ogrid[:h, :w]
    cand = elev.copy()
    n = 1 + ((s * 2654435761 >> 7) & 1)
    puntos: List[Tuple[int, int]] = []
    for _ in range(n):
        idx = int(np.argmax(cand))
        cy, cx = divmod(idx, w)
        if elev[cy, cx] < alt_min:
            break
        puntos.append((cy, cx))
        cand[(yy - cy) ** 2 + (xx - cx) ** 2 < (w / 4) ** 2] = -1e9
    for cy, cx in puntos:
        r2 = (yy - cy) ** 2 + (xx - cx) ** 2
        elev += realce * np.exp(-r2 / (2 * 5.0 ** 2))
        elev[r2 <= 2.25] += crater  # cráter
    return puntos


# --------------------------------------------------------------------- clima

def _temperatura_mar(X, Y, w, h, s) -> np.ndarray:
    lat = np.abs(Y / (h - 1) * 2 - 1)  # 0 en el ecuador (centro), 1 en los polos
    return 29.0 - 34.0 * lat ** 1.4 + (fbm(X, Y, w / 3, 3, s + 5) - 0.5) * 6.0


def _precipitacion(elev: np.ndarray, t_mar: np.ndarray, s: int) -> np.ndarray:
    """Viento húmedo cruzando el mapa: se recarga sobre el mar y llueve sobre la tierra,
    más al subir montañas (sombra de lluvia al otro lado)."""
    invertir = bool(s % 2)  # viento del este o del oeste según la semilla
    if invertir:
        elev, t_mar = elev[:, ::-1], t_mar[:, ::-1]
    h, w = elev.shape
    m = np.zeros(h)
    precip = np.zeros((h, w))
    prev = elev[:, 0].copy()
    for x in range(w):
        e = elev[:, x]
        oceano = e < 0
        capacidad = np.clip((t_mar[:, x] + 10.0) / 45.0, 0.25, 1.0)
        m = np.where(oceano, m + (capacidad - m) * 0.35, m)
        dz = np.maximum(0.0, e - prev)
        frac = np.where(oceano, 0.0, 0.025 + np.clip(dz / 120.0, 0, 1) * 0.30)
        p = m * frac
        precip[:, x] = p
        m = m - p
        prev = e
    return precip[:, ::-1] if invertir else precip


# ---------------------------------------------------------------- hidrología

def _hidrologia(elev: np.ndarray, peso: np.ndarray, jitter: np.ndarray):
    """Priority-flood: rellena depresiones, da dirección de flujo a cada celda y
    acumula caudal. Devuelve (lleno, destino, acumulado)."""
    h, w = elev.shape
    n = h * w
    ev = elev.ravel().tolist()
    oceano = [e < 0 for e in ev]
    cerrado = list(oceano)
    lleno = list(ev)
    destino = [-1] * n
    heap: List[Tuple[float, int]] = []
    oc2d = elev < 0
    toca_tierra = _dilatar(~oc2d) & oc2d
    borde = np.zeros((h, w), dtype=bool)
    borde[0, :] = borde[-1, :] = borde[:, 0] = borde[:, -1] = True
    for i in np.flatnonzero((toca_tierra | borde).ravel()).tolist():
        if not cerrado[i]:
            cerrado[i] = True
        heapq.heappush(heap, (ev[i], i))
    eps = 1e-3
    jit = jitter.ravel().tolist()
    while heap:
        f, i = heapq.heappop(heap)
        y, x = divmod(i, w)
        for dy in (-1, 0, 1):
            yy = y + dy
            if yy < 0 or yy >= h:
                continue
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                xx = x + dx
                if xx < 0 or xx >= w:
                    continue
                j = yy * w + xx
                if cerrado[j]:
                    continue
                cerrado[j] = True
                paso = f + eps * (1.0 + 20.0 * jit[j])
                nf = ev[j] if ev[j] > paso else paso
                lleno[j] = nf
                destino[j] = i
                heapq.heappush(heap, (nf, j))
    lleno_a = np.array(lleno)
    acc = peso.ravel().astype(np.float64).copy()
    orden = np.argsort(-lleno_a, kind="stable").tolist()
    for i in orden:
        d = destino[i]
        if d >= 0:
            acc[d] += acc[i]
    return lleno_a.reshape(h, w), np.array(destino).reshape(h, w), acc.reshape(h, w)


# -------------------------------------------------------------------- principal

def generar_mundo(semilla: int, ancho: int = 256, alto: int = 256, tam_celda_m: int = 50, progreso=None,
                  dimension: str = "mundo") -> Dict:
    """`progreso(fraccion_0_a_1, texto)` se llama al empezar cada etapa, para la pantalla de carga."""
    paso = progreso if progreso is not None else (lambda f, t: None)
    s = int(semilla)
    P = preset(dimension)
    if algoritmo(dimension) == "cavernas":
        return _generar_cavernas(s, ancho, alto, tam_celda_m, P, paso)
    paso(0.02, "Levantando el relieve")
    X, Y = np.meshgrid(np.arange(ancho, dtype=np.float64), np.arange(alto, dtype=np.float64))

    # 1-2. relieve y volcanes
    bruto = _relieve(X, Y, ancho, alto, s)
    mar = float(np.quantile(bruto, P["quantil_mar"]))
    elev = _a_metros(bruto, mar)
    volcanes = _volcanes(elev, s, P["volcanes"])
    oceano = elev < 0
    tierra = ~oceano

    paso(0.30, "Repartiendo el calor y la lluvia")
    # 3-4. clima
    t_mar = _temperatura_mar(X, Y, ancho, alto, s)
    temp = t_mar - 6.5 * np.maximum(elev, 0.0) / 1000.0
    precip = suavizar(_precipitacion(elev, t_mar, s), 6)
    ref = max(float(np.quantile(precip[tierra], 0.85)), 1e-9)
    pn = np.clip(precip / ref, 0.0, 1.0)

    paso(0.42, "Haciendo correr los ríos")
    # 5. hidrología (un micro-relieve evita ríos rectos sobre llanuras planas)
    elev = np.where(tierra, elev + (fbm(X, Y, 3.0, 3, s + 9) - 0.5) * 6.0 + 3.0, elev)
    elev = np.where(tierra, np.maximum(elev, 0.0), elev)
    lleno, destino, acc = _hidrologia(elev, pn + 0.02, fbm(X, Y, 2.5, 2, s + 11))
    prof = lleno - elev
    lago = (prof > P["umbral_lago_m"]) & tierra
    lago = _seleccionar_lagos(lago, prof, 4, max(40, ancho * alto // 400))
    # las depresiones que no son lago se rellenan: pasan a ser llanuras con drenaje
    elev = np.where(tierra, lleno, elev)
    umbral_rio = float(np.quantile(acc[tierra & ~lago], P["quantil_rio"]))
    rio = (acc > umbral_rio) & tierra & ~lago
    # cascadas: río que cae más de 100 m hacia su celda de destino
    cascada = np.zeros_like(rio)
    ys, xs = np.nonzero(rio)
    flat_e = elev.ravel()
    for y, x in zip(ys.tolist(), xs.tolist()):
        d = int(destino[y, x])
        if d >= 0 and elev[y, x] - flat_e[d] > P["umbral_cascada_m"]:
            cascada[y, x] = True

    paso(0.68, "Sembrando los biomas")
    # 6. humedad final y biomas
    agua_mask = oceano | lago | rio
    d_agua = _dist_agua(agua_mask, 6)
    ruido_h = fbm(X, Y, ancho / 6, 4, s + 7)
    hum = np.clip(0.65 * pn + 0.35 * ruido_h, 0.0, 1.0)
    hum = np.clip(hum + 0.22 * np.clip(1.0 - d_agua / 6.0, 0.0, 1.0), 0.0, 1.0)
    hum[oceano] = 1.0

    bioma = _clasificar(elev, temp, hum, oceano, lago, d_agua, volcanes)

    agua = np.zeros(elev.shape, dtype=np.uint8)
    agua[oceano] = B.AGUA_OCEANO
    agua[lago] = B.AGUA_LAGO
    agua[rio] = B.AGUA_RIO

    caudal = np.zeros(elev.shape, dtype=np.uint8)
    if rio.any():
        k = np.log(np.maximum(acc[rio] / umbral_rio, 1.0))
        kmax = max(float(k.max()), 1e-9)
        caudal[rio] = np.clip(40 + (k / kmax) * 215, 0, 255).astype(np.uint8)

    rasgos = np.zeros(elev.shape, dtype=np.uint8)
    rasgos[cascada] |= B.RASGO_CASCADA
    yy, xx = np.ogrid[:alto, :ancho]
    for cy, cx in volcanes:
        rasgos[((yy - cy) ** 2 + (xx - cx) ** 2) <= 2.25] |= B.RASGO_LAVA

    capas = {
        "elevacion": np.clip(np.round(elev), -32000, 32000).astype(np.int16),
        "temperatura": np.clip(np.round(temp), -60, 60).astype(np.int8),
        "humedad": np.clip(np.round(hum * 255), 0, 255).astype(np.uint8),
        "bioma": bioma,
        "agua": agua,
        "caudal": caudal,
        "rasgos": rasgos,
    }
    meta = {
        "semilla": s,
        "version_generador": VERSION_GENERADOR,
        "ancho": ancho,
        "alto": alto,
        "tam_celda_m": tam_celda_m,
        "nivel_mar_bruto": round(mar, 6),
        "volcanes": [[int(cx), int(cy)] for cy, cx in volcanes],
    }
    return {"capas": capas, "meta": meta}


_CLIMA_CACHE = None


def algoritmo(id_dimension: str = "mundo") -> str:
    """Qué generador pide esa dimensión. El algoritmo es CÓDIGO (un algoritmo no es contenido); cuál se usa
    y con qué números, dato."""
    from ..registro import Registro
    return str((Registro.cargar().uno("dimension", id_dimension) or {}).get("generador") or "continental")


def _generar_cavernas(s: int, ancho: int, alto: int, tam_celda_m: float, P: dict, paso) -> Dict:
    """Cavernas: autómata celular de roca y hueco, el mismo molde que el fuego y las colonias.

    No hay sol, ni estaciones, ni mar: hay roca, huecos conectados, agua estancada en lo más hondo y
    hongales donde hay humedad. Los umbrales son todos del preset, así que otra caverna (más cerrada, más
    húmeda, más honda) es sólo JSON."""
    rng = np.random.default_rng(s)
    paso(0.05, "Cavando la roca")
    roca = rng.random((alto, ancho)) < float(P.get("densidad_roca", 0.46))
    roca[0, :] = roca[-1, :] = roca[:, 0] = roca[:, -1] = True
    for _ in range(int(P.get("pasadas", 5))):
        vecinos = np.zeros((alto, ancho), dtype=np.int16)
        p = np.pad(roca, 1, mode="constant", constant_values=True).astype(np.int16)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                vecinos += p[1 + dy:1 + dy + alto, 1 + dx:1 + dx + ancho]   # la celda cuenta como una más
        roca = vecinos >= int(P.get("vecinos_roca", 5))
        roca[0, :] = roca[-1, :] = roca[:, 0] = roca[:, -1] = True

    paso(0.35, "Conectando las galerías")
    # Quedarse con la cueva más grande: un portal no puede dejar a nadie encerrado en una burbuja de roca.
    hueco = ~roca
    alcanzable = _mayor_hueco(hueco)
    roca = ~alcanzable

    paso(0.60, "Midiendo la hondura")
    X, Y = np.meshgrid(np.arange(ancho, dtype=np.float64), np.arange(alto, dtype=np.float64))
    relieve = fbm(X, Y, 48.0, 4, s ^ 0x5EEDCA7E)
    elev = float(P.get("profundidad_m", -400.0)) + float(P.get("relieve_m", 70.0)) * (relieve - 0.5) * 2.0

    agua = np.zeros((alto, ancho), dtype=np.uint8)
    if alcanzable.any():
        corte = float(np.quantile(elev[alcanzable], float(P.get("quantil_agua", 0.08))))
        agua[alcanzable & (elev <= corte)] = B.AGUA_LAGO      # agua estancada en lo más hondo

    bioma = np.full((alto, ancho), B.ROCA_VIVA, dtype=np.uint8)
    bioma[alcanzable] = B.CAVERNA
    bioma[agua == B.AGUA_LAGO] = B.LAGO
    hum_base = float(P.get("humedad", 0.78))
    hum = np.clip(hum_base + 0.18 * (relieve - 0.5), 0.0, 1.0)
    if alcanzable.any():                                      # donde más húmedo, hongal
        corte_h = float(np.quantile(hum[alcanzable], 1.0 - float(P.get("quantil_hongal", 0.30))))
        bioma[alcanzable & (hum >= corte_h) & (agua == 0)] = B.HONGAL

    paso(0.85, "Guardando la caverna")
    temp = np.full((alto, ancho), float(P.get("temperatura_C", 12.0)))
    capas = {
        "elevacion": np.clip(np.round(elev), -32000, 32000).astype(np.int16),
        "temperatura": np.clip(np.round(temp), -60, 60).astype(np.int8),
        "humedad": np.clip(np.round(hum * 255), 0, 255).astype(np.uint8),
        "bioma": bioma,
        "agua": agua,
        "caudal": np.zeros((alto, ancho), dtype=np.uint8),
        "rasgos": np.zeros((alto, ancho), dtype=np.uint8),
    }
    meta = {"semilla": s, "version_generador": VERSION_GENERADOR, "ancho": ancho, "alto": alto,
            "tam_celda_m": tam_celda_m, "generador": "cavernas",
            "huecos": int(alcanzable.sum()), "volcanes": []}
    return {"capas": capas, "meta": meta}


def _mayor_hueco(hueco: np.ndarray) -> np.ndarray:
    """La región hueca más grande, por dilatación sucesiva desde la semilla mejor ubicada.

    Se hace con numpy y no con una BFS en Python: en 512×512 una BFS por celda tarda segundos y acá se
    resuelve con unas pocas decenas de pasadas sobre el mapa entero."""
    if not hueco.any():
        return hueco
    alto, ancho = hueco.shape
    ys, xs = np.nonzero(hueco)
    cy, cx = alto // 2, ancho // 2
    i = int(np.argmin((ys - cy) ** 2 + (xs - cx) ** 2))       # el hueco más cercano al centro
    actual = np.zeros_like(hueco)
    actual[ys[i], xs[i]] = True
    while True:
        p = np.pad(actual, 1, mode="constant", constant_values=False)
        crecido = actual.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                crecido |= p[1 + dy:1 + dy + alto, 1 + dx:1 + dx + ancho]
        crecido &= hueco
        if crecido.sum() == actual.sum():
            return actual
        actual = crecido


def preset(id_dimension: str = "mundo") -> dict:
    """Los umbrales de generación de una dimensión, desde los datos (datos_base/dimensiones/).
    El ALGORITMO sigue siendo código (un generador nuevo es un algoritmo, no contenido), pero todos sus
    números son dato: una dimensión con el mismo generador y otros umbrales es sólo JSON."""
    from ..registro import Registro
    d = Registro.cargar().uno("dimension", id_dimension) or {}
    base = {"altura_max_m": ALTURA_MAX_M, "profundidad_max_m": PROFUNDIDAD_MAX_M,
            "quantil_mar": 0.55, "quantil_rio": 0.95, "umbral_lago_m": 8.0, "umbral_cascada_m": 100.0,
            "volcanes": {"altura_min_m": 1200, "crater_m": -250.0, "radio_celdas": 6}}
    base.update(d.get("preset") or {})
    return base


def tabla_clima(reg=None):
    """[(prioridad, id_numerico, rangos)] ordenada. Los rangos de cada bioma salen de los DATOS
    (`clasificacion` y `clasificacion_extra` en datos_base/biomas/). Se arma una vez por proceso.

    OJO: esto se APLICA con máscaras de numpy, no con el evaluador de condiciones. Clasificar 4 millones
    de celdas pasando por un intérprete de JSON no termina nunca (ver docs/OPTIMIZACION.md)."""
    global _CLIMA_CACHE
    if _CLIMA_CACHE is None or reg is not None:
        from ..registro import Registro
        reg = reg or Registro.cargar()
        filas = []
        for bid, d in reg.de_tipo("bioma").items():
            num = d.get("id_numerico")
            if num is None:
                continue
            c = d.get("clasificacion")
            if c:
                filas.append((int(c["prioridad"]), int(num), c["rangos"]))
            for extra in d.get("clasificacion_extra") or []:
                filas.append((int(extra["prioridad"]), int(num), extra["rangos"]))
        filas.sort(key=lambda f: f[0])
        _CLIMA_CACHE = filas
    return _CLIMA_CACHE


# Qué columna del mundo mira cada rango. Agregar una es código (una primitiva más); usarla es dato.
_CAMPOS = ("temperatura_C", "humedad", "elevacion_m", "dist_agua", "pendiente")


def _mascara(rangos: dict, campos: dict):
    """Máscara booleana de numpy para un conjunto de rangos.

    El formato es `[mínimo, máximo]`, con el mínimo incluido y el máximo excluido. Un tercer elemento
    `"abierto"` deja el mínimo afuera (`> mínimo` en vez de `>= mínimo`): hace falta porque la elevación y la
    temperatura son FLOAT acá dentro (se redondean recién al guardar), así que `> 2000` y `>= 2001` no son
    lo mismo y la diferencia se ve en el mapa.
    """
    m = None
    for nombre, rango in rangos.items():
        col = campos.get(nombre)
        if col is None:
            continue
        lo, hi = rango[0], rango[1]
        abierto = len(rango) > 2 and rango[2] == "abierto"
        parcial = ((col > lo) if abierto else (col >= lo)) & (col < hi)
        m = parcial if m is None else (m & parcial)
    return m


def _clasificar(elev, temp, hum, oceano, lago, d_agua, volcanes) -> np.ndarray:
    h, w = elev.shape
    b = np.full((h, w), B.PRADERA, dtype=np.uint8)
    T, H = temp, hum

    # Clima, pantano y altura salen de los DATOS: cada bioma declara en qué rangos aparece y con qué
    # prioridad (el número más alto pisa al más bajo, igual que el orden de las líneas de antes).
    gy, gx = np.gradient(elev)
    campos = {"temperatura_C": T, "humedad": H, "elevacion_m": elev,
              "dist_agua": d_agua, "pendiente": np.hypot(gx, gy)}
    for _prio, num, rangos in tabla_clima():
        m = _mascara(rangos, campos)
        if m is not None:
            b[m] = num

    # costas
    costa = _dilatar(oceano) & ~oceano
    b[costa & (elev < 20) & (T > -5)] = B.PLAYA

    # volcanes
    yy, xx = np.ogrid[:h, :w]
    for cy, cx in volcanes:
        b[((yy - cy) ** 2 + (xx - cx) ** 2) <= 36] = B.VOLCAN

    # agua
    b[lago] = B.LAGO
    b[oceano] = B.OCEANO
    b[elev < -1000] = B.OCEANO_PROFUNDO
    return b

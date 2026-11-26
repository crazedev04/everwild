"""
Guardar y cargar la simulación viva en la base del mundo.

Qué se guarda:
- habitantes (tabla `habitantes`): posición en metros, estado (salud, sed, energía, acción) e identidad.
- reloj (`estado_mundo.t_min`).
- fuego, ceniza, combustible y tormentas (`estado_dinamico`).
Los eventos nuevos se vuelcan a la tabla `eventos`. Nada de esto toca el mapa ni la memoria de los habitantes.
"""
from __future__ import annotations

import json
import zlib
import math
import random
import uuid
from collections import deque
from typing import List, Optional, Tuple

import numpy as np

from ..agentes import ajustes as _ajustes
from ..agentes.genoma import Genoma, genoma_fundador
from ..motor import biomas as B
from ..motor.navegacion import Terreno
from ..motor.vida import ADULTO_MIN, ANIO_MIN, NOMBRES_F, NOMBRES_M  # noqa: F401  (ADULTO_MIN se usa en los tests)
from ..motor.simulacion import HabitanteSim, Simulacion
from . import mundo_io, social
from .memoria import MemoriaPrivada
from ..agentes.habito import Habito

MIN_ZONA_CONECTADA = 3000  # celdas transitables conectadas mínimas para el punto de inicio
# Cuántas trayectorias se guardan por habitante para entrenar futuros cerebros. Son seis JSON por
# fila: con 2.000 por persona y 20 habitantes quedan ~6 MB, que es de sobra para entrenar y no crece
# para siempre (sin tope eran 60.989 filas en un solo mundo).
TOPE_ENTRENAMIENTO = 2000
# P2 — Habitabilidad del inicio. El punto de partida sólo se acepta si desde él hay una orilla de
# agua alcanzable por la navegación REAL (A* `buscar_camino`), no basta con que el agua esté cerca
# geométricamente ni con que una BFS la "vea". Ver docs/IMPLEMENTACION_P2_HABITABILIDAD.md.
TOPE_ORILLAS = 8          # cuántas orillas candidatas se enrutan por inicio (acotado)
TOPE_BFS_ORILLA = 4000    # tope de nodos del BFS que busca orillas caminables alrededor del inicio
RADIO_ORILLA_MIN = 12     # radio mínimo de búsqueda de orilla, en celdas
RADIO_ORILLA_M = 2000.0   # radio de búsqueda de orilla en metros (acotado además al tamaño del mundo)
MAX_CANDIDATOS_INICIO = 40  # cuántos candidatos al inicio se validan (acotado; determinista por orden)
# Vecindad de 8 para el BFS de orillas. El A* (`buscar_camino`) es el que valida de verdad; acá sólo
# se encuentran orillas caminables cercanas. Se define local para no tocar el módulo de navegación.
_OFFS8 = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
# Agua dulce: río y lago. El océano no sirve para beber.
_AGUA_DULCE = {B.AGUA_RIO, B.AGUA_LAGO}


def _agua_adyacente_dulce(t: Terreno, x: int, y: int) -> bool:
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if t.dentro(x + dx, y + dy) and t.agua[y + dy, x + dx] in _AGUA_DULCE:
                return True
    return False


def _podar_por_habitante(con, tabla: str, tope: int) -> None:
    """Deja las últimas `tope` filas de cada habitante y borra el resto.

    Se hace en dos pasos y por persona a propósito: busca el `id` de corte con un LIMIT/OFFSET sobre
    el índice y después borra por rango. Es lo que puede usar el índice. La forma de una sola
    sentencia («borrá las filas que tengan 400 filas más nuevas de la misma persona») obliga a contar
    filas por cada fila, o sea cuadrática, y encima corría en cada guardado.
    """
    import sqlite3

    try:
        habitantes = [f[0] for f in con.execute('SELECT DISTINCT habitante_id FROM "%s"' % tabla)]
        for hid in habitantes:
            fila = con.execute(
                'SELECT id FROM "%s" WHERE habitante_id = ? ORDER BY id DESC LIMIT 1 OFFSET ?'
                % tabla, (hid, tope)).fetchone()
            if fila is not None:
                con.execute('DELETE FROM "%s" WHERE habitante_id = ? AND id <= ?' % tabla,
                            (hid, fila[0]))
    except sqlite3.Error:
        # `entrenamiento_cerebro` la crea el puente cognitivo la primera vez que anota algo: con el
        # cerebro híbrido puede no existir, y eso no es motivo para no guardar el mundo.
        pass


def clave_dim(clave: str, dimension: int = 0) -> str:
    """Clave de `estado_dinamico` para una dimensión. La 0 usa las de siempre, así un mundo viejo abre igual."""
    return clave if not dimension else "d%d:%s" % (int(dimension), clave)


def _presupuesto_camino(tam_celda_m: float) -> int:
    """Presupuesto de expansiones del A* para validar habitabilidad.

    Es el MISMO `nodos_camino` que usa el motor a esta resolución (ver `Simulacion._calcular_escala`):
    así "habitable en la generación" significa "enrutable dentro del presupuesto de producción", no
    con un presupuesto distinto que después el motor no tendría.
    """
    k = (50.0 / float(tam_celda_m)) ** 2
    return int(min(120_000, 12_000 * k))


def _orilla_alcanzable(t: Terreno, x: int, y: int, presupuesto: int) -> Optional[Tuple[int, int]]:
    """Celda de orilla caminable alcanzable por A* desde `(x, y)`, o `None`.

    Reutiliza la navegación real (`Terreno.buscar_camino`): no alcanza con que haya agua cerca
    geométricamente ni con que una BFS la "vea"; la orilla tiene que ser enrutable dentro del
    presupuesto de producción. Acotado a propósito: el BFS que reúne orillas tiene tope de nodos y
    radio, y se enrutan como mucho `TOPE_ORILLAS` orillas por inicio.
    """
    if not t.caminable(x, y):
        return None
    if _agua_adyacente_dulce(t, x, y):
        return (x, y)  # ya está en la orilla: puede beber sin caminar
    ancho, alto = t.ancho, t.alto
    radio = max(RADIO_ORILLA_MIN, int(RADIO_ORILLA_M / t.tam_celda_m))
    vistos = {(x, y)}
    cola = deque([(x, y, 0)])
    orillas: List[Tuple[int, int]] = []
    while cola and len(vistos) <= TOPE_BFS_ORILLA:
        cx, cy, d = cola.popleft()
        if d >= radio:
            continue
        for ax, ay in _OFFS8:
            nx, ny = cx + ax, cy + ay
            if 0 <= nx < ancho and 0 <= ny < alto and (nx, ny) not in vistos and t.caminable(nx, ny):
                vistos.add((nx, ny))
                if _agua_adyacente_dulce(t, nx, ny):
                    orillas.append((nx, ny))
                else:
                    cola.append((nx, ny, d + 1))
    # Orden determinista: orillas más cercanas primero; desempate por coordenada.
    orillas.sort(key=lambda p: (abs(p[0] - x) + abs(p[1] - y), p[0], p[1]))
    for o in orillas[:TOPE_ORILLAS]:
        if t.buscar_camino((x, y), o, presupuesto) is not None:
            return o
    return None


def elegir_inicio(capas: dict, tam_celda_m: float = 50.0) -> Tuple[int, int]:
    """Punto de inicio: tierra llana y habitable, junto a agua dulce, en una zona grande y conectada."""
    t = Terreno(capas, tam_celda_m)
    dulce = (t.agua == B.AGUA_RIO) | (t.agua == B.AGUA_LAGO)
    ys, xs = np.nonzero(dulce)
    if len(xs) == 0:
        raise ValueError("El mundo no tiene agua dulce: no hay dónde empezar.")
    buenos = np.isin(t.bioma, [B.PRADERA, B.BOSQUE_TEMPLADO, B.SABANA, B.BOSQUE_FRIO])
    for umbral in (0.15, 0.35, 0.8, 2.0):
        cand = []
        for wy, wx in zip(ys[::3], xs[::3]):  # muestreo para ir rápido
            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    x, y = int(wx) + dx, int(wy) + dy
                    if t.dentro(x, y) and buenos[y, x] and t.pendiente[y, x] < umbral and t.caminable(x, y) \
                            and t.agua[y, x] == 0:
                        cand.append((x, y))
        if cand:
            break
    if not cand:
        # último recurso: cualquier tierra caminable junto al agua
        for wy, wx in zip(ys[::3], xs[::3]):
            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    x, y = int(wx) + dx, int(wy) + dy
                    if t.dentro(x, y) and t.caminable(x, y) and t.agua[y, x] == 0:
                        cand.append((x, y))
        if not cand:
            raise ValueError("No se encontró un lugar habitable junto al agua.")
    cx, cy = t.ancho / 2, t.alto / 2
    cand = sorted(set(cand), key=lambda p: math.hypot(p[0] - cx, p[1] - cy))
    presupuesto = _presupuesto_camino(tam_celda_m)
    for x, y in cand[:MAX_CANDIDATOS_INICIO]:
        if t.componente(x, y) < MIN_ZONA_CONECTADA:
            continue
        if _orilla_alcanzable(t, x, y, presupuesto) is None:
            continue  # no hay agua realmente alcanzable por A*: no es habitable
        return x, y
    return cand[0]


def composicion_inicial(rng) -> List[dict]:
    """Quiénes empiezan el mundo. Cambia en cada mundo, pero SIEMPRE hay al menos un hombre y una mujer adultos:
    sin eso no hay descendencia y el mundo se muere sin empezar.

    Devuelve una lista de grupos; cada grupo arranca junto y en un lugar distinto del mapa, así se tienen que
    encontrar caminando. Un grupo es [{"sexo": "F"|"M", "nino": bool}, ...].
    """
    forma = rng.choices(["pareja", "familia", "dos_solos", "grupo", "disperso"],
                        weights=[18, 18, 22, 22, 20])[0]
    if forma == "pareja":                       # una pareja sola, juntos
        return [[{"sexo": "F", "nino": False}, {"sexo": "M", "nino": False}]]
    if forma == "familia":                      # una pareja y un hijo chico
        return [[{"sexo": "F", "nino": False}, {"sexo": "M", "nino": False},
                 {"sexo": rng.choice("FM"), "nino": True}]]
    if forma == "dos_solos":                    # dos desconocidos en puntas distintas
        return [[{"sexo": "F", "nino": False}], [{"sexo": "M", "nino": False}]]
    if forma == "grupo":                        # una banda de 3 a 5 que ya anda junta
        n = rng.randint(3, 5)
        gente = [{"sexo": "F", "nino": False}, {"sexo": "M", "nino": False}]
        gente += [{"sexo": rng.choice("FM"), "nino": False} for _ in range(n - 2)]
        rng.shuffle(gente)
        return [gente]
    # disperso: dos o tres grupitos chicos repartidos
    grupos = [[{"sexo": "F", "nino": False}], [{"sexo": "M", "nino": False}]]
    for _ in range(rng.randint(0, 1)):
        grupos.append([{"sexo": rng.choice("FM"), "nino": False}])
    for g in grupos:                            # alguno puede ser una parejita
        if rng.random() < 0.3:
            g.append({"sexo": "M" if g[0]["sexo"] == "F" else "F", "nino": False})
    rng.shuffle(grupos)
    return grupos


def _puntos_de_partida(t: Terreno, x0: int, y0: int, n: int, tam: float, rng) -> List[Tuple[int, int]]:
    """`n` lugares de arranque, todos en la MISMA masa de tierra que (x0, y0) y a una distancia que se pueda
    caminar. Si cayeran en islas distintas no se encontrarían nunca y el mundo se extinguiría."""
    if n <= 1:
        return [(x0, y0)]
    zona = t.zona_conectada(x0, y0, tope=120000)
    if len(zona) < 50:
        return [(x0, y0)] * n
    # Ni pegados ni imposibles: entre 600 m y 4 km, pero acotado al tamaño del mundo, porque en un mapa chico
    # esas distancias caen fuera y los grupos terminaban todos en el mismo lugar.
    lado = min(t.ancho, t.alto)
    # Tope de 2 km a propósito: la vista llega a 1,5 km, así que más lejos pueden no cruzarse NUNCA
    # y el mundo se extingue sin que se note. Conviene subirlo recién cuando se los vea encontrarse solos.
    lejos_max = min(2000.0 / tam, lado * 0.33)
    lejos_min = min(600.0 / tam, lejos_max * 0.45)
    cerca = [c for c in zona if lejos_min <= math.hypot(c[0] - x0, c[1] - y0) <= lejos_max]
    rng.shuffle(cerca)
    puntos = [(x0, y0)]
    sep_min = max(4.0, min(400.0 / tam, lejos_max * 0.5))   # entre grupo y grupo
    for c in cerca:
        if len(puntos) >= n:
            break
        if all(math.hypot(c[0] - p[0], c[1] - p[1]) >= sep_min for p in puntos):
            puntos.append(c)
    for c in cerca:                             # segunda vuelta más permisiva antes de rendirse
        if len(puntos) >= n:
            break
        if all(math.hypot(c[0] - p[0], c[1] - p[1]) >= sep_min * 0.4 for p in puntos):
            puntos.append(c)
    while len(puntos) < n:                      # mundo apretadísimo: mejor juntos que en islas separadas
        puntos.append(puntos[len(puntos) % max(1, len(puntos))])
    return puntos


def sumar_habitante(con, sexo: Optional[str] = None, cerca_de: Optional[Tuple[int, int]] = None,
                    nombre: Optional[str] = None, dimension: int = 0) -> dict:
    """Mete una persona nueva en un mundo que ya está andando. Devuelve su ficha corta.

    Para qué existe (fase 6 del plan, y fase 8): el cuello de botella de sangre. Cuando uno solo engendra
    con todas, la generación siguiente son medio hermanos entre sí y `parentesco_cercano` les prohíbe
    procrear: la colonia se extingue por diseño. Sangre nueva lo destraba sin tocar esa regla.

    Llega sin padres (`madre_id`/`padre_id` en nulo), así que no es pariente de nadie, y con un genoma
    de fundador: ni mejor ni peor que los que empezaron. Si no se dice el sexo, se elige el que esté en
    minoría entre los adultos vivos, que es lo que de verdad desempata una población.
    """
    meta = mundo_io.cargar_meta(con)
    capas = mundo_io.cargar_capas(con, dimension=dimension)
    tam = float(meta["tam_celda_m"])
    if dimension:
        d = mundo_io.dimension_por_id(con, dimension) or {}
        tam = float(d.get("tam_celda_m") or tam)
    t = Terreno(capas, tam)
    fila = con.execute("SELECT t_min FROM estado_mundo WHERE id = 1").fetchone()
    t_min = int(fila["t_min"] if fila else 0)

    vivos = [r for r in con.execute("SELECT identidad, nacimiento_min, x, y FROM habitantes WHERE muerte_min IS NULL")]
    if sexo not in ("F", "M"):
        adultos = [r for r in vivos if t_min - int(r["nacimiento_min"] or 0) >= ADULTO_MIN]
        f = sum(1 for r in adultos if (json.loads(r["identidad"] or "{}").get("sexo") or "F") == "F")
        sexo = "F" if f <= len(adultos) - f else "M"      # el que está en minoría

    rng = random.Random(int(meta["semilla"]) * 31 + t_min)
    if cerca_de is None:
        # cerca de la gente si hay gente (que se encuentren), y si no, donde empezaría un mundo nuevo
        if vivos:
            r = vivos[rng.randrange(len(vivos))]
            cerca_de = (int(float(r["x"]) / tam), int(float(r["y"]) / tam))
        else:
            cerca_de = elegir_inicio(capas, tam)
    lejos = max(2, int(round(300.0 / tam)))              # a unos 300 m: a la vista, pero no encima
    c = None
    for intento in range(20):
        ang = rng.random() * 2 * math.pi
        d = lejos * (0.5 + rng.random())
        c = t.caminable_cerca(int(cerca_de[0] + math.cos(ang) * d), int(cerca_de[1] + math.sin(ang) * d), 4)
        if c:
            break
    c = c or t.caminable_cerca(int(cerca_de[0]), int(cerca_de[1]), 6) or elegir_inicio(capas, tam)

    usados = {r[0] for r in con.execute("SELECT nombre FROM habitantes")}
    pool = [x for x in (NOMBRES_F if sexo == "F" else NOMBRES_M) if x not in usados]
    nombre = nombre or (rng.choice(pool) if pool else "Nuevo%d" % (len(usados) + 1))
    n_hab = con.execute("SELECT COUNT(*) FROM habitantes").fetchone()[0]
    g = genoma_fundador(int(meta["semilla"]) * 1000 + 9000 + n_hab)
    estado = {"salud": 100.0, "sed": 30.0, "energia": 90.0, "accion": "libre", "detalle": "",
              "color": n_hab % 12}
    px, py = (c[0] + 0.5) * tam, (c[1] + 0.5) * tam
    with con:
        cur = con.execute(
            """INSERT INTO habitantes (uuid, nombre, nacimiento_min, x, y, z, estado, identidad, genoma,
                                       madre_id, padre_id, dimension, creado_en)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))""",
            (str(uuid.uuid4()), nombre, t_min - 25 * ANIO_MIN, px, py,
             float(capas["elevacion"][c[1], c[0]]), json.dumps(estado),
             json.dumps({"generacion": 0, "sexo": sexo}), json.dumps(g.a_dict()), None, None, dimension))
    hid = cur.lastrowid
    mundo_io.registrar_evento(con, t_min, "llegada", "%s llegó de algún lugar lejano." % nombre,
                              actor_id=hid, x=px, y=py, importancia=4, origen="sistema")
    return {"id": hid, "nombre": nombre, "sexo": sexo, "x": px, "y": py, "dimension": dimension}


def crear_habitantes_iniciales(con, n: Optional[int] = None, semilla: Optional[int] = None) -> List[int]:
    """Crea a los fundadores (si todavía no hay habitantes). Devuelve sus ids.

    La composición, los nombres y los lugares salen de la semilla del mundo: el mismo mundo da siempre la misma
    gente, pero dos mundos distintos arrancan distinto. Con `n` se fuerza una cantidad (lo usan los tests).
    """
    if con.execute("SELECT COUNT(*) FROM habitantes").fetchone()[0] > 0:
        return [r[0] for r in con.execute("SELECT id FROM habitantes ORDER BY id")]
    meta = mundo_io.cargar_meta(con)
    capas = mundo_io.cargar_capas(con)
    tam = float(meta["tam_celda_m"])
    sem = int(meta["semilla"] if semilla is None else semilla)
    rng = random.Random(sem * 7919 + 13)
    t = Terreno(capas, tam)
    x0, y0 = elegir_inicio(capas, tam)

    grupos = composicion_inicial(rng)
    if n is not None:                            # cantidad forzada: una sola tanda junta, mitad y mitad
        grupos = [[{"sexo": "F" if k % 2 == 0 else "M", "nino": False} for k in range(max(2, n))]]
    puntos = _puntos_de_partida(t, x0, y0, len(grupos), tam, rng)

    libres_f = [x for x in NOMBRES_F]
    libres_m = [x for x in NOMBRES_M]
    rng.shuffle(libres_f)
    rng.shuffle(libres_m)
    ids: List[int] = []
    usadas: set = set()
    sep = max(1, int(round(25.0 / tam)))          # ~25 m entre uno y otro dentro del mismo grupo
    k = 0
    for gi, (grupo, (gx, gy)) in enumerate(zip(grupos, puntos)):
        ids_grupo: List[int] = []
        for j, quien in enumerate(grupo):
            c = None
            for intento in range(14):             # anillo creciente hasta encontrar celda libre y transitable
                ang = 2.39996323 * (k + intento * 7)
                d = sep * (1 + intento * 0.5)
                cand = t.caminable_cerca(int(gx + math.cos(ang) * d), int(gy + math.sin(ang) * d), 3)
                if cand and cand not in usadas:
                    c = cand
                    break
            c = c or t.caminable_cerca(int(gx), int(gy), 4) or (x0, y0)
            usadas.add(c)
            # dentro de la celda, su propio punto (el mismo sesgo que usa el motor al caminar)
            a_ = 2.39996323 * (k + 1)
            r_ = 0.32 * math.sqrt((((k + 1) * 0.6180339887) % 1.0) * 0.75 + 0.25)
            ox, oy = r_ * math.cos(a_), r_ * math.sin(a_)
            sexo = quien["sexo"]
            pool = libres_f if sexo == "F" else libres_m
            nombre = pool.pop() if pool else "Nuevo%d" % (k + 1)
            g = genoma_fundador(sem * 1000 + k)
            estado = {"salud": 100.0, "sed": 30.0, "energia": 90.0, "accion": "libre", "detalle": "", "color": k}
            # `nacimiento_min` va NEGATIVO: es cuánto hace que nacieron respecto del minuto 0 del mundo.
            # Los adultos tienen 25 años; un chico entre 3 y 8, siempre menos de los 12 que lo harían adulto.
            nac = -int(ANIO_MIN * rng.uniform(3.0, 8.0)) if quien["nino"] else -25 * ANIO_MIN
            madre = padre = None
            if quien["nino"] and len(ids_grupo) >= 2:
                madre, padre = ids_grupo[0], ids_grupo[1]
            px, py = (c[0] + 0.5 + ox) * tam, (c[1] + 0.5 + oy) * tam
            with con:
                cur = con.execute(
                    """INSERT INTO habitantes (uuid, nombre, nacimiento_min, x, y, z, estado, identidad, genoma,
                                               madre_id, padre_id, creado_en)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?, datetime('now'))""",
                    (str(uuid.uuid4()), nombre, nac, px, py, float(capas["elevacion"][c[1], c[0]]),
                     json.dumps(estado), json.dumps({"generacion": 0, "sexo": sexo}), json.dumps(g.a_dict()),
                     madre, padre))
            ids.append(cur.lastrowid)
            ids_grupo.append(cur.lastrowid)
            mundo_io.registrar_evento(con, 0, "llegada", "%s llegó al mundo." % nombre,
                                      actor_id=ids[-1], x=px, y=py, importancia=4, origen="sistema")
            k += 1
    return ids


def cargar_simulacion(con, cerebro=None, dimension: int = 0, base: Optional[Simulacion] = None) -> Simulacion:
    """Una dimensión del mundo (0 = el de siempre), con su gente, su fuego y su fauna.

    El reloj es del mundo, no del mapa: todas las dimensiones arrancan en el mismo minuto."""
    meta = mundo_io.cargar_meta(con)
    d = mundo_io.dimension_por_id(con, dimension) or {}
    capas = mundo_io.cargar_capas(con, dimension=dimension)
    if dimension:
        meta = dict(meta, ancho=d["ancho"], alto=d["alto"], tam_celda_m=d["tam_celda_m"], semilla=d["semilla"])
    t_min = float(con.execute("SELECT t_min FROM estado_mundo WHERE id = 1").fetchone()[0])
    sim = Simulacion(capas, meta, t_min=t_min, cerebro=cerebro, dimension=dimension,
                     ident=d.get("ident") or "mundo", base=base)
    sim.ajustes = base.ajustes if base is not None else _ajustes.obtener(con)
    tam = sim.tam_celda_m
    for r in con.execute("SELECT * FROM habitantes WHERE dimension = ? ORDER BY id", (int(dimension),)):
        est = json.loads(r["estado"] or "{}")
        ident = json.loads(r["identidad"] or "{}")
        h = HabitanteSim(r["id"], r["nombre"], (r["x"] or 0) / tam, (r["y"] or 0) / tam,
                         salud=est.get("salud", 100.0), sed=est.get("sed", 30.0), energia=est.get("energia", 90.0),
                         color=int(est.get("color", 0)), vivo=r["muerte_min"] is None)
        h.hambre = float(est.get("hambre", 0.0))
        h.atributos = {k: float(v) for k, v in (est.get("atributos") or {}).items()}
        h.destrezas = {k: float(v) for k, v in (est.get("destrezas") or {}).items()}
        h.objetivo = est.get("objetivo") or None
        h.viaje = est.get("viaje") or None
        h.causa_muerte, h.t_muerte = r["causa_muerte"], r["muerte_min"]
        h.hasta = float(est.get("hasta", 0.0))
        if est.get("accion") == "durmiendo":
            h.accion = "durmiendo"
        h.sexo = ident.get("sexo") or ("F" if r["id"] % 2 == 1 else "M")
        h.nacimiento_min = r["nacimiento_min"] if r["nacimiento_min"] else h.nacimiento_min
        h.madre_id, h.padre_id = r["madre_id"], r["padre_id"]
        h.embarazo = est.get("embarazo")
        h.sin_concebir_hasta = float(est.get("sin_concebir_hasta", 0.0))
        h.emo.update({k: float(v) for k, v in (est.get("emo") or {}).items() if k in h.emo})
        h.inventario = {k: int(v) for k, v in (est.get("inventario") or {}).items()}
        h.inv_t = {k: float(v) for k, v in (est.get("inv_t") or {}).items() if k in h.inventario}
        h.rotos = int(est.get("rotos", 0))
        h.recursos = set(est.get("recursos", []))
        h.fabricados = set(est.get("fabricados", []))
        h.hogar = tuple(est["hogar"]) if est.get("hogar") else None
        h.hogar_rid = est.get("hogar_rid")
        h.montura = est.get("montura")
        h.novedad_t = float(est.get("novedad_t", 0.0))
        h.zonas = {tuple(z) for z in est.get("zonas", [])}
        h.visto = {int(k): list(v) for k, v in (est.get("visto") or {}).items()}
        h.ultima_idea_t = float(est.get("ultima_idea_t", 0.0))
        h.ataque_t = float(est.get("ataque_t", -1e9))
        h.lugares = {k: [list(p) for p in v] for k, v in (est.get("lugares") or {}).items()}
        h.plan = [str(p) for p in (est.get("plan") or [])]
        h.ultima_reflexion_t = float(est.get("ultima_reflexion_t", 0.0))
        h.rasgos_vivos = {k: float(v) for k, v in (est.get("rasgos_vivos") or {}).items()}
        h.habito_v = {k: float(v) for k, v in (est.get("habito_v") or {}).items()}
        try:
            g = json.loads(r["genoma"] or "{}")
            h.genoma = Genoma.de_dict(g) if g else None
        except (ValueError, KeyError):
            h.genoma = None
        if est.get("habito"):
            h.habito = Habito.de_dict(est["habito"], h.genoma.pesos if h.genoma else None)
        sim.habitantes[h.id] = h
    for r in con.execute("SELECT id, nombre, descripcion, materiales, propiedad, creador_id, origen, receta_id, t_min FROM conocimientos"):
        sim.conocimientos[r["id"]] = {"nombre": r["nombre"], "descripcion": r["descripcion"],
                                      "materiales": json.loads(r["materiales"]), "propiedad": r["propiedad"],
                                      "creador_id": r["creador_id"], "origen": r["origen"], "receta_id": r["receta_id"],
                                      "t_min": r["t_min"]}
    sim.rearmar_recetas_inventadas()
    for r in con.execute("SELECT habitante_id, conocimiento_id FROM conoce"):
        if r["habitante_id"] in sim.habitantes:
            sim.habitantes[r["habitante_id"]].conoce.add(r["conocimiento_id"])
    for r in con.execute("SELECT habitante_id, otro_id FROM relaciones"):
        sim.conocidos.add((min(r[0], r[1]), max(r[0], r[1])))
    # El estado dinámico de la dimensión 0 sigue con las claves de siempre (un mundo viejo abre igual);
    # las demás llevan el prefijo 'd<N>:'.
    pref = clave_dim("", dimension)
    din = {r["clave"][len(pref):]: r["valor"] for r in con.execute("SELECT clave, valor FROM estado_dinamico")
           if r["clave"].startswith(pref) and (dimension or ":" not in r["clave"])}
    if all(k in din for k in ("fuego", "quemado", "combustible")):
        try:
            def _d(v):
                b = bytes(v)
                return zlib.decompress(b) if b[:2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda") else b
            sim.fuego.importar(_d(din["fuego"]), _d(din["quemado"]), _d(din["combustible"]), din.get("edad_min"))
        except ValueError:
            pass  # tamaño distinto (mundo cambiado): se parte de cero
    def _decomp(raw: bytes) -> bytes:
        try:
            return zlib.decompress(raw) if raw[:2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda") else raw
        except zlib.error:
            return raw
    if "nieve" in din:
        sim.importar_nieve(_decomp(bytes(din["nieve"])))
    if "desgaste" in din:
        sim.importar_desgaste(_decomp(bytes(din["desgaste"])))
    vivos = [h for h in sim.habitantes.values() if h.vivo]
    if vivos:
        sim.centro_seguro = (sum(h.x for h in vivos) / len(vivos), sum(h.y for h in vivos) / len(vivos))
    if "estructuras" in din:
        try:
            sim.importar_estructuras(json.loads(bytes(din["estructuras"]).decode("utf-8")))
        except ValueError:
            pass
    if "fenomenos" in din:
        try:
            sim.importar_fenomenos(json.loads(bytes(din["fenomenos"]).decode("utf-8")))
        except ValueError:
            pass
    if "colonias" in din:
        try:
            sim.importar_colonias(json.loads(bytes(din["colonias"]).decode("utf-8")))
        except ValueError:
            pass
    if "fauna" in din:
        try:
            sim.fauna.importar(json.loads(bytes(din["fauna"]).decode("utf-8")))
            sim._fauna_lista = True
            for h in sim.habitantes.values():          # coherencia: quien monta, monta algo que existe
                a = sim.fauna.animales.get(h.montura) if h.montura is not None else None
                if a is None:
                    h.montura = None
                else:
                    a.jinete = h.id
        except (ValueError, KeyError):
            pass
    if "tormentas" in din:
        sim.clima.importar(json.loads(bytes(din["tormentas"]).decode("utf-8")))

    def al_nacer(sim_, madre, padre, g, sexo, nombre):
        with con:
            cur = con.execute(
                """INSERT INTO habitantes (uuid, nombre, nacimiento_min, x, y, estado, identidad, genoma, madre_id, padre_id, dimension, creado_en)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?, datetime('now'))""",
                (str(uuid.uuid4()), nombre, int(sim_.t), madre.x * tam, madre.y * tam,
                 json.dumps({"salud": 100.0, "sed": 20.0, "energia": 90.0}),
                 json.dumps({"generacion": g.generacion, "sexo": sexo}), json.dumps(g.a_dict()),
                 madre.id, padre.id if padre else None, sim_.dimension))
        nuevo = HabitanteSim(cur.lastrowid, nombre, madre.x, madre.y, sed=20.0, color=(cur.lastrowid - 1) % 8)
        nuevo.sexo, nuevo.genoma, nuevo.madre_id = sexo, g, madre.id
        nuevo.padre_id = padre.id if padre else None
        nuevo.nacimiento_min = int(sim_.t)
        sim_.habitantes[nuevo.id] = nuevo
        return nuevo

    def al_inventar(sim_, h, nombre, materiales, propiedad, descripcion, origen="inventada", receta_id=None):
        with con:
            cur = con.execute("INSERT INTO conocimientos (nombre, descripcion, materiales, propiedad, creador_id, t_min, origen, receta_id) "
                              "VALUES (?,?,?,?,?,?,?,?)", (nombre, descripcion, json.dumps(materiales), propiedad, h.id, int(sim_.t),
                                                           origen, receta_id))
            con.execute("INSERT OR IGNORE INTO conoce (habitante_id, conocimiento_id, aprendido_de, t_min) VALUES (?,?,NULL,?)",
                        (h.id, cur.lastrowid, int(sim_.t)))
        return cur.lastrowid

    sim.al_nacer, sim.al_inventar = al_nacer, al_inventar
    # Las bocas de caverna y demás pasos que están desde siempre. Es idempotente: se hace una sola vez
    # por dimensión y queda guardado con el resto de las estructuras.
    sim.sembrar_estructuras_naturales()
    return sim


def cargar_mundo(con, cerebro=None) -> "Mundo":
    """El mundo entero: la dimensión de siempre y las que se le hayan abierto.

    Un mundo que nunca vio un portal tiene una sola dimensión y esto es exactamente lo de antes."""
    from ..motor.mundo import Mundo
    principal = cargar_simulacion(con, cerebro=cerebro, dimension=0)
    mundo = Mundo(principal)
    for d in mundo_io.listar_dimensiones(con):
        if d["id"]:
            mundo.agregar(cargar_simulacion(con, cerebro=cerebro, dimension=d["id"], base=principal))

    def al_crear_dimension(ident: str):
        """La primera vez que alguien abre un paso, se genera el mapa del otro lado y queda guardado."""
        d = mundo_io.crear_dimension(con, ident)
        if d is None:
            return None
        ya = mundo.sims.get(d["id"])
        if ya is not None:
            return ya
        return mundo.agregar(cargar_simulacion(con, cerebro=cerebro, dimension=d["id"], base=principal))

    mundo.al_crear_dimension = al_crear_dimension
    return mundo


def guardar_mundo_vivo(con, mundo) -> None:
    for sim in mundo.sims.values():
        guardar_simulacion(con, sim)


def volcar_eventos_mundo(con, mundo) -> int:
    return sum(volcar_eventos(con, sim) for sim in sorted(mundo.sims.values(), key=lambda s: s.dimension))


def guardar_simulacion(con, sim: Simulacion) -> None:
    tam = sim.tam_celda_m
    with con:
        con.execute("UPDATE estado_mundo SET t_min = ?, actualizado_en = datetime('now') WHERE id = 1", (int(sim.t),))
        for h in sim.habitantes.values():
            estado = {"salud": round(h.salud, 2), "sed": round(h.sed, 2), "energia": round(h.energia, 2),
                      "hambre": round(h.hambre, 2),
                      "atributos": {k: round(v, 4) for k, v in h.atributos.items()},
                      "destrezas": {k: round(v, 4) for k, v in h.destrezas.items()},
                      "objetivo": h.objetivo, "viaje": h.viaje,
                      "accion": h.accion, "detalle": h.detalle, "color": h.color,
                      "hasta": round(h.hasta, 1) if h.accion == "durmiendo" else 0.0,
                      "embarazo": h.embarazo, "sin_concebir_hasta": h.sin_concebir_hasta,
                      "emo": {k: round(v, 3) for k, v in h.emo.items()}, "inventario": h.inventario, "rotos": h.rotos, "recursos": sorted(h.recursos), "fabricados": sorted(h.fabricados), "hogar": list(h.hogar) if h.hogar else None, "hogar_rid": h.hogar_rid, "inv_t": {k: round(v, 1) for k, v in h.inv_t.items()}, "montura": h.montura,
                      "novedad_t": round(h.novedad_t, 1), "zonas": [list(z) for z in sorted(h.zonas)][:600],
                      "visto": {str(k): v for k, v in h.visto.items()}, "ultima_idea_t": round(h.ultima_idea_t, 1),
                      "ataque_t": round(h.ataque_t, 1), "lugares": h.lugares, "plan": h.plan,
                      "ultima_reflexion_t": round(h.ultima_reflexion_t, 1),
                      "rasgos_vivos": {k: round(v, 4) for k, v in h.rasgos_vivos.items()},
                      "habito": h.habito.a_dict() if h.habito is not None else None,
                      "habito_v": {k: round(v, 3) for k, v in h.habito_v.items()}}
            con.execute("UPDATE habitantes SET x=?, y=?, estado=?, muerte_min=?, causa_muerte=?, dimension=? WHERE id=?",
                        (h.x * tam, h.y * tam, json.dumps(estado), h.t_muerte if not h.vivo else None,
                         h.causa_muerte if not h.vivo else None, sim.dimension, h.id))
        dia = int(sim.t // 1440)
        if getattr(sim, "_dia_olvido", None) != dia:         # una vez por día del mundo: cada uno olvida lo que ya no importa
            sim._dia_olvido = dia
            for h in sim.habitantes.values():
                if h.vivo:
                    MemoriaPrivada(con, h.id).olvidar(sim.t)
        if getattr(sim, "_dia_poda", None) != dia:           # poda diaria de eventos menores viejos (los importantes se quedan)
            sim._dia_poda = dia
            con.execute("DELETE FROM eventos WHERE importancia <= 2 AND t_min < ? AND tipo NOT IN ('muerte','nacimiento')",
                        (int(sim.t) - 150 * 1440,))
            # Las dos tablas que crecen con cada decisión de cada habitante. `decisiones` ya se
            # podaba, pero en CADA guardado (o sea cada 10 segundos reales) y con una subconsulta
            # correlacionada que cuenta filas por fila: cuadrática. Ahora va una vez por día del
            # mundo, con el resto de las podas. `entrenamiento_cerebro` no se podaba nunca: eran
            # 60.989 filas y ~10 MB de JSON en el mundo `gaia`, creciendo para siempre.
            _podar_por_habitante(con, "decisiones", 400)
            _podar_por_habitante(con, "entrenamiento_cerebro", TOPE_ENTRENAMIENTO)
        exp_raw = sim.fuego.exportar()
        exp = {k: (zlib.compress(v, level=1) if isinstance(v, (bytes, bytearray)) else v)
               for k, v in exp_raw.items()}
        exp["tormentas"] = json.dumps(sim.clima.exportar()).encode("utf-8")
        exp["nieve"] = zlib.compress(sim.nieve_bytes(), level=1)
        exp["desgaste"] = zlib.compress(sim.desgaste_bytes(), level=1)
        exp["estructuras"] = json.dumps(sim.exportar_estructuras(), separators=(",", ":")).encode("utf-8")
        exp["fenomenos"] = json.dumps(sim.exportar_fenomenos(), separators=(",", ":")).encode("utf-8")
        exp["colonias"] = json.dumps(sim.exportar_colonias(), separators=(",", ":")).encode("utf-8")
        if sim._fauna_lista:
            exp["fauna"] = json.dumps(sim.fauna.exportar(), separators=(",", ":")).encode("utf-8")
        for clave, valor in exp.items():
            con.execute("INSERT OR REPLACE INTO estado_dinamico (clave, valor, actualizado_min) VALUES (?,?,?)",
                        (clave_dim(clave, sim.dimension), valor, sim.t))


def _procesar_interno(con, sim: Simulacion, e: dict) -> None:
    """Eventos internos del motor (empiezan con "_"): se convierten en diálogos, recuerdos y relaciones."""
    t, d, tam = e["t_min"], e["datos"], sim.tam_celda_m
    x = None if e["x"] is None else e["x"] * tam
    y = None if e["y"] is None else e["y"] * tam
    tipo = e["tipo"]
    if tipo == "_memoria" and e["habitante_id"] is not None:
        MemoriaPrivada(con, e["habitante_id"]).agregar(t, d.get("tipo", "episodica"), e["texto"], float(d.get("importancia", 0.5)),
                                                       x=e["x"], y=e["y"], origen=d.get("origen", "vivido"),
                                                       de_quien=d.get("de_quien"), certeza=float(d.get("certeza", 1.0)))
    elif tipo == "_dialogo":
        social.registrar_dialogo(con, t, d["emisor"], d["receptores"], d["mensaje"], x, y,
                                 certeza=float(d.get("certeza", 1.0)))
        for r in d["receptores"]:
            social.ajustar_relacion(con, t, d["emisor"], r, d_afecto=0.05 * d.get("impresion", 0), d_confianza=0.01,
                                    motivo="conversaron")
            social.ajustar_relacion(con, t, r, d["emisor"], d_afecto=0.0, d_confianza=0.01, motivo="conversaron")
    elif tipo == "_encuentro":
        a, b = d["a"], d["b"]
        na, nb = social._nombre(con, a), social._nombre(con, b)
        MemoriaPrivada(con, a).agregar(t, "episodica", "Conociste a %s." % nb, 0.7)
        MemoriaPrivada(con, b).agregar(t, "episodica", "Conociste a %s." % na, 0.7)
        social.ajustar_relacion(con, t, a, b, motivo="se conocieron")
        social.ajustar_relacion(con, t, b, a, motivo="se conocieron")
        mundo_io.registrar_evento(con, t, "encuentro", e["texto"], actor_id=a, objetivo_id=b, x=x, y=y,
                                  importancia=2, origen="autonomo")
    elif tipo == "_relacion":
        if d.get("d_afecto") or d.get("d_confianza"):
            social.ajustar_relacion(con, t, d["hab"], d["otro"], d.get("d_afecto", 0.0), d.get("d_confianza", 0.0),
                                    d.get("motivo", ""))
    elif tipo == "_aprende":
        con.execute("INSERT OR IGNORE INTO conoce (habitante_id, conocimiento_id, aprendido_de, t_min) VALUES (?,?,?,?)",
                    (d["hab"], d["conocimiento"], d.get("de"), t))
        con.commit()


def volcar_eventos(con, sim: Simulacion) -> int:
    """Pasa a la base los eventos acumulados. Devuelve cuántos (los internos se procesan aparte)."""
    evs = sim.vaciar_eventos()
    for e in evs:
        if e["tipo"].startswith("_"):
            _procesar_interno(con, sim, e)
            continue
        mundo_io.registrar_evento(
            con, e["t_min"], e["tipo"], e["texto"], actor_id=e["habitante_id"],
            x=None if e["x"] is None else e["x"] * sim.tam_celda_m,
            y=None if e["y"] is None else e["y"] * sim.tam_celda_m,
            causa=e["causa"], resultado=e["resultado"], importancia=e["importancia"],
            origen=e["origen"], datos=e["datos"], dimension=sim.dimension)
    # Trabajo de fondo de los vectores de significado: guarda lo que llegó y pide lo que falta. No espera a nadie.
    sim.semantica.configurar(sim.ajustes)
    sim.semantica.paso(con)
    return sum(1 for e in evs if not e["tipo"].startswith("_"))

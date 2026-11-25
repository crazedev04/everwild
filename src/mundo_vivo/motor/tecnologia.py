"""Tecnología de verdad: juntar materiales del mundo, fabricar objetos con las recetas que conocen, encender fogatas,
llevar fuego de un incendio, construir refugios y usar lo fabricado (abrigo, armas, curación).

Nada de esto es automático: hay que saber la receta (la descubren con `inventar`), tener los materiales (los juntan según
el bioma donde están) y dedicarle el tiempo que dice la receta (`tiempo_min`). Los datos están en datos_base/recetas."""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import biomas as B
from .conservacion import TOPE_LOTE

DURA_ANTORCHA_MIN = 0.2 * 1440.0
MIN_LENA = 2
FOGATA_MIN_POR_LENA = 150.0
# En METROS (ver vida.py): a 50 m por celda dan los mismos números de siempre para las zonas de recursos,
# y los radios de calor dejan de ser absurdos (una fogata calentaba a 250 m a la redonda).
METROS_CALOR_FOGATA = 20.0      # lo que abriga una fogata alrededor
METROS_CALOR_REFUGIO = 12.0     # adentro de la choza y su alero
MAX_REFUGIOS_POR_PERSONA = 3
METROS_ALDEA = 150.0            # casas a esta distancia o menos son la misma aldea
TIEMPO_JUNTAR_MIN = 20.0
METROS_ZONA = 800.0             # los recursos se agotan por zona y vuelven a crecer (a 50 m/celda: zonas de 16×16)
DIAS_REGENERAR = 8.0
MIN_DIA = 1440.0
# Deterioro: una casa por la que no pasa nadie se cae sola. Tarda estaciones a propósito: 20 días de
# gracia y después medio año largo hasta quedar en ruinas.
DIAS_SIN_USO = 20.0
DESGASTE_POR_DIA = 0.004
MIN_ABRIGO = 0.05
# Las magnitudes físicas que una estructura puede PROVEER y una receta puede PEDIR. Agregar una (presión,
# vacío, lo que sea) es sumar una línea acá y escribir el JSON: `_provisto_en` ya es genérico.
PROVISIONES = {
    "calor_C": ("hace falta fuego al lado.", "hace falta más calor del que da esto."),
    "energia_W": ("hace falta corriente al lado.", "hace falta más corriente de la que da esto."),
}
# Grupos de biomas que el motor usa para reglas propias (no son contenido: son atajos de lectura).
_BOSQUES = (B.BOSQUE_TEMPLADO, B.SELVA, B.BOSQUE_FRIO)
_PASTOS = (B.PRADERA, B.SABANA)

# Qué se junta, dónde, con qué suerte, cuánto rinde y cuánto aguanta la zona: ahora vive en los DATOS
# (`recoleccion` y `lena` de cada material, ver datos_base/reglas/materiales.json). El motor no conoce
# ningún material por su nombre: se compilan a tablas planas en `_compilar_materiales()`.
# ARMAS, ANTORCHAS y OBJETIVOS ahora son datos: ver datos_base/items/ y datos_base/cultura/.


class TecnologiaMixin:
    # ------------------------------------------------------- datos de materiales
    def _compilar_materiales(self) -> None:
        """Del registro a tablas planas. Se hace UNA vez al crear el mundo: el bucle de 20 Hz nunca toca el
        registro ni el evaluador de condiciones (ver docs/OPTIMIZACION.md)."""
        from ..motor import biomas as _B
        por_clave = {v[0]: k for k, v in _B.BIOMAS.items()}
        self.recoleccion: Dict[str, tuple] = {}     # material -> (biomas,)
        self.prob_rec: Dict[str, float] = {}
        self.cant_rec: Dict[str, tuple] = {}
        self.capacidad: Dict[str, int] = {}
        self.herramienta_rec: Dict[str, str] = {}   # material -> propiedad que hace falta llevar para juntarlo
        self.lena: tuple = ()
        lena = []
        for mid, d in self.registro.de_tipo("material").items():
            r = d.get("recoleccion") or {}
            prop = (r.get("requiere") or {}).get("propiedad")
            if prop:
                self.herramienta_rec[mid] = str(prop)
            if r.get("biomas"):
                self.recoleccion[mid] = tuple(por_clave[b] if isinstance(b, str) else b for b in r["biomas"])
            if r.get("prob") is not None:
                self.prob_rec[mid] = float(r["prob"])
            if r.get("cantidad"):
                self.cant_rec[mid] = tuple(r["cantidad"])
            if r.get("capacidad_zona") is not None:
                self.capacidad[mid] = int(r["capacidad_zona"])
            if d.get("lena"):
                lena.append(mid)
        self.lena = tuple(sorted(lena))
        # Armas, antorchas y objetivos: también datos. El alcance va en METROS en el JSON y se pasa a celdas
        # acá, una sola vez: en celdas, a 5 m por celda las armas tenían 10 veces menos alcance.
        self.armas: Dict[str, tuple] = {}
        antorchas = []
        for iid, d in self.registro.de_tipo("item").items():
            arma = d.get("arma")
            if arma:
                self.armas[iid] = (float(arma["bono_caza"]), self.celdas(float(arma["alcance_m"]), minimo=0.0))
            if d.get("antorcha"):
                antorchas.append(iid)
        # el palo pelado va último: es el último recurso para llevarse una llama
        # se respeta el ORDEN del archivo de datos: se prueba la primera que uno tenga encima
        self.antorchas = tuple(a for a in antorchas if a != "palo") + ("palo",)
        # Estructuras que dan calor: de acá sale la progresión (fogata 600 °C, horno 1000, fragua 1500).
        self.estructuras: Dict[str, dict] = dict(self.registro.de_tipo("estructura"))
        obj = self.registro.uno("objetivos", "respaldo") or {}
        self.objetivos = tuple(obj.get("recetas") or ())

    # ------------------------------------------------------------ consultas
    def tiene(self, h, item: str) -> bool:
        return h.inventario.get(item, 0) > 0

    def _receta_de(self, texto: str) -> Optional[dict]:
        t = str(texto or "").strip().lower()
        if not t:
            return None
        if t in self.recetas:
            return self.recetas[t]
        for r in self.recetas.values():
            if r["nombre"].lower() == t:
                return r
        for r in self.recetas.values():
            if t in r["nombre"].lower():
                return r
        return None

    def receta_de_invento(self, nombre: str, materiales: List[str], propiedad: str, descripcion: str = "") -> str:
        """Un invento que no está en el catálogo igual tiene que PODERSE hacer: se le arma una receta de verdad y se
        suma al catálogo de este mundo. Sin esto el conocimiento queda sin receta y nunca aparece en «fabricar»."""
        from ..catalogos import TIEMPO_CATEGORIA
        base = "".join(ch if ch.isalnum() else "_" for ch in nombre.lower().strip())[:40].strip("_") or "invento"
        rid = base
        n = 2
        while rid in self.recetas:
            rid = "%s_%d" % (base, n)
            n += 1
        cat = {"corta": "herramienta", "perfora": "herramienta", "golpea": "herramienta", "ata": "herramienta",
               "abriga": "ropa", "protege": "ropa", "arde": "fuego", "enciende": "fuego", "cura": "salud",
               "contiene": "recipiente", "flota": "transporte"}.get(propiedad, "otros")
        self.recetas[rid] = {
            "type": "receta", "id": rid, "nombre": nombre, "ingredientes": list(materiales), "propiedad": propiedad,
            "categoria": cat, "descripcion": descripcion, "tiempo_min": TIEMPO_CATEGORIA.get(cat, 20),
            "resultado": {"item": rid, "cantidad": 1}, "herramienta": [], "requiere_fuego": False,
            "_archivo": "inventado", "_inventada": True}
        return rid

    def rearmar_recetas_inventadas(self) -> None:
        """Al cargar el mundo, el catálogo vuelve del JSON: hay que devolverle las recetas que inventaron acá."""
        for c in self.conocimientos.values():
            rid = c.get("receta_id")
            if c.get("origen") == "inventada" and rid and rid not in self.recetas:
                self.recetas[rid] = {
                    "type": "receta", "id": rid, "nombre": c["nombre"], "ingredientes": list(c["materiales"]),
                    "propiedad": c["propiedad"], "categoria": "otros", "descripcion": c.get("descripcion", ""),
                    "tiempo_min": 20, "resultado": {"item": rid, "cantidad": 1}, "herramienta": [],
                    "requiere_fuego": False, "_archivo": "inventado", "_inventada": True}

    def recetas_con_propiedad(self, *props) -> List[str]:
        """Ids de receta por propiedad. Se cachea por propiedad: `disponibles()` lo consulta varias veces
        por llamada y el catálogo pasó de 127 a 151 recetas con la metalurgia (ver docs/OPTIMIZACION.md).
        El índice se rehace solo cuando aparece una receta inventada."""
        cache = getattr(self, "_idx_prop", None)
        if cache is None or self._idx_prop_n != len(self.recetas):
            cache = {}
            for i, r in self.recetas.items():
                cache.setdefault(r["propiedad"], []).append(i)
            self._idx_prop, self._idx_prop_n = cache, len(self.recetas)
        if len(props) == 1:
            return cache.get(props[0], [])
        return [i for p in props for i in cache.get(p, [])]

    def fuente_de_chispa(self, h) -> Optional[str]:
        for i in self.recetas_con_propiedad("enciende"):
            if self.tiene(h, i):
                return i
        return "antorcha_encendida" if self.tiene(h, "antorcha_encendida") else None

    def lena_que_lleva(self, h) -> int:
        return sum(h.inventario.get(m, 0) for m in self.lena)

    def fogata_cerca(self, h, radio: float) -> Optional[dict]:
        for f in self.fogatas:
            if math.hypot(f["x"] - h.x, f["y"] - h.y) <= radio:
                return f
        return None

    def refugio_cerca(self, h, radio: Optional[float] = None) -> Optional[dict]:
        """El mejor techo al alcance. «Mejor» es por abrigo EFECTIVO (el de la choza más lo que le suma la
        fogata de al lado), y a igual abrigo gana el propio: la cama de uno antes que la del vecino."""
        radio = self.r_refugio if radio is None else radio
        mejor, mejor_a = None, 0.0
        for r in self.refugios:
            # un pozo o una boca de caverna están en la misma lista pero NO son un techo: no abrigan a nadie
            if float(r.get("abrigo", 0.0)) <= 0:
                continue
            if math.hypot(r["x"] - h.x, r["y"] - h.y) > radio:
                continue
            a = self.abrigo_efectivo(r)
            propio = r.get("dueno") == h.id
            if mejor is None or a > mejor_a or (a == mejor_a and propio and mejor.get("dueno") != h.id):
                mejor, mejor_a = r, a
        return mejor

    # ------------------------------------------------- el calor cae con la distancia
    @staticmethod
    def _caida(d: float, nucleo: float, radio: float, curva: str) -> float:
        """Factor 0..1 del calor a distancia `d`. Pleno en el núcleo, nada pasado el radio, y en el medio
        según la curva que diga el DATO. Agregar una estructura que caliente distinto no toca Python."""
        if d <= nucleo:
            return 1.0
        if d >= radio or curva == "escalon":
            return 0.0
        f = (radio - d) / max(1e-9, radio - nucleo)
        return f * f if curva == "cuadratica" else f

    def _alcance(self, e: dict) -> Tuple[float, float, str]:
        """(núcleo, radio, curva) de una estructura, en CELDAS. Los dos van en metros en el JSON: a 5 m por
        celda un núcleo de 3×3 celdas serían 15 metros, y a 50 m serían 150."""
        p = e.get("provee") or {}
        radio = self.celdas(float(e.get("radio_m", 6.0)), minimo=1.5)
        nucleo = self.celdas(float(p.get("nucleo_m", e.get("radio_m", 6.0))), minimo=1.0)
        return min(nucleo, radio), radio, str(p.get("caida", "escalon"))

    def _provisto_en(self, x: float, y: float, campo: str, trabajo: bool = True) -> float:
        """Cuánto de `campo` (grados, vatios) hay en un punto. Es el MÁXIMO, no la suma: dos fogatas no son
        un horno, y dos pilas no son una dinamo.

        Dos curvas distintas a propósito. Para **trabajar** (fabricar, fundir) cuenta sólo el núcleo: no se
        funde metal «casi al lado» de la fragua. Para **abrigarse** vale toda la caída, porque estar cerca
        del fuego ayuda un poco aunque no se esté encima.

        El campo es un parámetro y no hay un solo `if` de contenido: de acá salen `calor_disponible` y
        `energia_disponible` con el mismo código, y la próxima magnitud física también.
        """
        mejor = 0.0
        fog = self.estructuras.get("fogata") or {}
        nuc, rad, curva = self._alcance(fog)
        provee = float((fog.get("provee") or {}).get(campo, 0))
        if provee:
            for f in self.fogatas:
                d = math.hypot(f["x"] - x, f["y"] - y)
                k = 1.0 if d <= nuc else (0.0 if trabajo else self._caida(d, nuc, rad, curva))
                if k:
                    mejor = max(mejor, provee * k)
        inc = self.estructuras.get("incendio") or {}
        provee = float((inc.get("provee") or {}).get(campo, 0))
        if provee:
            nuc, rad, curva = self._alcance(inc)
            if self.fuego_cerca_de(x, y, rad):
                mejor = max(mejor, provee)      # del incendio sólo se sabe si está en el radio: adentro, pleno
        for r in self.refugios:                      # lo construido: hornos, fraguas, dinamos
            e = self.estructuras.get(r.get("tipo")) or {}
            provee = float((e.get("provee") or {}).get(campo, 0))
            if not provee:
                continue
            nuc, rad, curva = self._alcance(e)
            d = math.hypot(r["x"] - x, r["y"] - y)
            k = 1.0 if d <= nuc else (0.0 if trabajo else self._caida(d, nuc, rad, curva))
            if k:
                mejor = max(mejor, provee * k)
        return mejor

    def _grados_en(self, x: float, y: float, trabajo: bool = True) -> float:
        return self._provisto_en(x, y, "calor_C", trabajo)

    def calor_disponible(self, h) -> float:
        """Los grados que tiene al alcance de la MANO: con esto se decide si una receta se puede hacer."""
        return self._provisto_en(h.x, h.y, "calor_C", trabajo=True)

    def energia_disponible(self, h) -> float:
        """Los vatios que tiene al alcance de la mano. Calcado del calor, y a propósito: la luz es el mismo
        escalón físico que la fundición, con otra magnitud (ver fase 7 de docs/PLAN_MEJORAS_MOTOR.md)."""
        return self._provisto_en(h.x, h.y, "energia_W", trabajo=True)

    def atractor_fogata(self, h) -> float:
        """0..1: cuánto tira la fogata de la aldea a quedarse. Vale sólo en las horas de poca luz, que es
        cuando juntarse alrededor del fuego tiene sentido. Lo usan las utilidades (`motor/objetivos.py`)
        para abaratar quedarse con los demás y encarecer irse lejos."""
        from . import reloj
        if not self.fogatas or not reloj.es_noche(self.t):
            return 0.0
        tope = float(self.estructuras.get("fogata", {}).get("provee", {}).get("calor_C", 600)) or 600.0
        return min(1.0, self._grados_en(h.x, h.y, trabajo=False) / tope)

    def abrigo_efectivo(self, r: dict) -> float:
        """El abrigo de una casa contando el fuego que tenga alrededor.

        Es el incentivo físico que convierte un montón de chozas en una aldea: la misma choza abriga más si
        está dentro del alcance de una fogata encendida. El motor no tiene que saber qué es una aldea.
        """
        a = float(r.get("abrigo", 0.0))
        if a <= 0:
            return 0.0
        tope = float(self.estructuras.get("fogata", {}).get("provee", {}).get("calor_C", 600)) or 600.0
        k = min(1.0, self._grados_en(r["x"], r["y"], trabajo=False) / tope)
        return min(0.95, a + (1.0 - a) * 0.5 * k)

    def sembrar_estructuras_naturales(self) -> int:
        """Lo que no construyó nadie y está desde siempre: las bocas de caverna de la montaña, por ejemplo.

        Son estructuras y no terreno (el generador dibuja el suelo, no los agujeros), pero dependen del mapa
        y de la semilla: el mismo mundo tiene siempre las mismas bocas, en los mismos lugares. Una boca nueva
        es JSON: `natural: {biomas, cada_km2, maximo, separacion_m}` en una estructura.
        Se corre una sola vez por dimensión; después queda guardado con el resto de las estructuras."""
        hechas = set(getattr(self, "naturales_sembradas", []))
        ids_bioma = {d["id"]: int(d["id_numerico"]) for d in self.registro.de_tipo("bioma").values()}
        puestas = 0
        for eid, e in self.estructuras.items():
            nat = e.get("natural")
            if not nat or eid in hechas:
                continue
            hechas.add(eid)
            quiere = [ids_bioma[b] for b in (nat.get("biomas") or []) if b in ids_bioma]
            if not quiere:
                continue
            ok = np.isin(self.terreno.bioma, quiere) & np.isfinite(self.terreno.costo)
            ys, xs = np.nonzero(ok)
            if not len(xs):
                continue
            km2 = len(xs) * (self.tam_celda_m ** 2) / 1e6
            cuantas = int(round(km2 * float(nat.get("cada_km2", 0.5))))
            cuantas = max(int(nat.get("minimo", 1)), min(int(nat.get("maximo", 40)), cuantas))
            # RNG propio: el del mundo es sagrado y no se gasta acá (rompería el determinismo de la semilla)
            rng = random.Random(self.semilla * 2246822519 + self.dimension * 97 + sum(eid.encode()))
            orden = list(range(len(xs)))
            rng.shuffle(orden)
            sep = self.celdas(float(nat.get("separacion_m", 1500.0)))
            elegidas: List[tuple] = []
            for i in orden:
                if len(elegidas) >= cuantas:
                    break
                px, py = float(xs[i]) + 0.5, float(ys[i]) + 0.5
                if all(math.hypot(px - ax, py - ay) >= sep for ax, ay in elegidas):
                    elegidas.append((px, py))
            for px, py in elegidas:
                self.refugios.append({"rid": self._nuevo_refugio(), "x": round(px, 2), "y": round(py, 2),
                                      "dueno": None, "tipo": eid, "nombre": e.get("nombre", eid),
                                      "abrigo": float((e.get("estructura") or {}).get("abrigo", 0.0)),
                                      "t": int(self.t), "natural": True})
            puestas += len(elegidas)
        self.naturales_sembradas = sorted(hechas)
        return puestas

    def _accion_atravesar(self, h, it: dict) -> Tuple[bool, str]:
        """Cruzar a otra dimensión por una estructura que lleve ahí (`provee.lleva_a` en los datos).

        El motor no sabe qué es un portal ni qué es una caverna: lee el dato, igual que con `calor_C`."""
        if self.mundo is None:
            return False, "Acá no hay a dónde cruzar."
        p = self.mundo.pasaje_cerca(self, h)
        if p is None:
            return False, "No tenés nada al lado que lleve a ninguna parte."
        destino = self.mundo.dimension_para(p["a"])
        if destino is None:
            return False, "Mirás el paso y no se ve nada del otro lado todavía."
        nombre = self.estructuras.get(p["tipo"], {}).get("nombre", p["tipo"])
        r = p["r"]
        llegada = self.mundo.otra_punta(self, r, destino)      # a dónde da este paso, siempre al mismo lugar
        if llegada is None or not self.mundo.mover(h, destino, llegada[0], llegada[1]):
            return False, "No se puede pasar."
        self._evento("paso_dimension", "%s cruzó por %s." % (h.nombre, nombre), h, importancia=4,
                     datos={"a": destino.ident, "desde": self.ident})
        destino._recuerdo(h, "Cruzaste por %s y apareciste del otro lado, en (%d, %d)."
                          % (nombre, int(h.x), int(h.y)), 0.9)
        h.marcar_lugar("refugio", h.x, h.y, "la salida por donde viniste", destino.t,
                       radio=destino.celdas(300.0))
        return True, "Cruzaste por %s." % nombre

    def requisitos_ok(self, h, r: dict, usar: Optional[List[str]] = None) -> Tuple[bool, str]:
        """¿Puede hacer esta receta acá y ahora? Un solo lugar para todos los requisitos.

        `requiere: {calor_C: "@mena"}` significa «lo que pida el material que se esté usando»: es lo que
        deja que UNA receta de fundición sirva para cualquier mena, incluida una que este mundo inventó
        esta mañana y que no está en ningún catálogo (ver motor/minerales.py).
        """
        req = r.get("requiere") or ({"calor_C": 400} if r.get("requiere_fuego") else {})
        for campo, (falta, poco) in PROVISIONES.items():
            pedido = req.get(campo, 0)
            if isinstance(pedido, str) and pedido.startswith("@"):
                if usar is None:
                    usar, _ = self._ingredientes_ok(h, r)
                pide = max([0.0] + [float((self.reglas.materiales.get(m) or {}).get("punto_fusion_C", 0) or 0)
                                    for m in (usar or [])])
            else:
                pide = float(pedido)
            if not pide:
                continue
            hay = self._provisto_en(h.x, h.y, campo, trabajo=True)
            if hay < pide:
                return False, ("Para hacer %s " % r["nombre"]) + (falta if hay <= 0 else poco)
        return True, ""

    def calor_de_estructuras(self, h) -> float:
        """Factor (0..1] que multiplica la severidad del frío: junto a una fogata o dentro de un refugio se
        pasa menos frío.

        El calor del fuego ya no es binario. Antes eran 20 metros planos y un paso más afuera cero: daba lo
        mismo estar encima de las brasas que a 20 metros. Ahora el núcleo abriga pleno (el 0,25 de siempre) y
        de ahí para afuera la caída la dice el dato (`provee.nucleo_m` y `caida` de la estructura).
        """
        k = 1.0
        tope = float(self.estructuras.get("fogata", {}).get("provee", {}).get("calor_C", 600)) or 600.0
        f = min(1.0, self._grados_en(h.x, h.y, trabajo=False) / tope)
        if f > 0:
            k *= 1.0 - 0.75 * f
        r = self.refugio_cerca(h)
        if r:
            k *= 1.0 - self.abrigo_efectivo(r)
        return k

    def restante(self, x: float, y: float, mat: str) -> float:
        cap = self.capacidad.get(mat)
        if cap is None:
            return 99.0
        usado, t0 = self.agotamiento.get("%d,%d,%s" % (int(x) // self.zona, int(y) // self.zona, mat), (0.0, self.t))
        usado = max(0.0, usado - cap / DIAS_REGENERAR * (self.t - t0) / 1440.0)
        # lo que dejó un fenómeno (un meteorito, por ejemplo) se suma a lo que da la zona
        extra = self.depositos.get("%d,%d,%s" % (int(x) // self.zona, int(y) // self.zona, mat), 0.0)
        return cap + extra - usado

    def _gastar_recurso(self, x: float, y: float, mat: str, n: int) -> None:
        if mat not in self.capacidad:
            return
        k = "%d,%d,%s" % (int(x) // self.zona, int(y) // self.zona, mat)
        usado, t0 = self.agotamiento.get(k, (0.0, self.t))
        usado = max(0.0, usado - self.capacidad[mat] / DIAS_REGENERAR * (self.t - t0) / 1440.0) + n
        self.agotamiento[k] = (usado, self.t)
        if len(self.agotamiento) > 600:                          # poda las zonas ya regeneradas
            for kk in [kk for kk, (u, tt) in self.agotamiento.items() if u - self.capacidad.get(kk.split(",", 2)[2], 10) / DIAS_REGENERAR * (self.t - tt) / 1440.0 <= 0]:
                self.agotamiento.pop(kk, None)

    def agotados(self, h) -> List[str]:
        """Materiales que el bioma da pero que acá ya se juntaron todos (vuelven a crecer con los días)."""
        return sorted(m for m in self.disponibles(h, con_agotados=True) if self.restante(h.x, h.y, m) < 1.0)

    def disponibles(self, h, con_agotados: bool = False) -> Dict[str, float]:
        """Qué se puede juntar acá, con su probabilidad."""
        t = self.terreno
        x, y = int(h.x), int(h.y)
        if not t.dentro(x, y):
            return {}
        b = int(t.bioma[y, x])
        out: Dict[str, float] = {}
        for m, v in self.recoleccion.items():
            if b in v:
                out[m] = self.prob_rec.get(m, 0.5)
        zx, zy = int(x) // self.zona, int(y) // self.zona
        for k, n in self.depositos.items():          # lo que dejó caer un fenómeno
            if n > 0 and k.startswith("%d,%d," % (zx, zy)):
                out[k.split(",", 2)[2]] = 0.6
        cerca_agua = t.agua_adyacente(x, y)
        if cerca_agua or b == B.PANTANO:
            out["arcilla"] = self.prob_rec.get("arcilla", 0.5)
        if cerca_agua:
            out["pescado"] = 0.6 if any(self.tiene(h, i) for i in ("red_de_pesca", "arpon", "red_de_fibra")) else self.prob_rec.get("pescado", 0.5)
        if b in _BOSQUES and any(self.tiene(h, i) for i in self.recetas_con_propiedad("corta")):
            out["madera"] = self.prob_rec.get("madera", 0.5)
        if self.fogata_cerca(h, self.r_mano):
            out["ceniza"] = self.prob_rec.get("ceniza", 0.5); out["carbon"] = self.prob_rec.get("carbon", 0.5)
        # La roca dura no se junta con la mano: pide algo que golpee. Es el mismo trato que la madera y el
        # hacha de dos líneas más arriba, pero sacado de los DATOS (`recoleccion.requiere.propiedad`), así
        # que una mena nueva declara su herramienta sin tocar Python.
        if self.herramienta_rec:
            for m in [m for m in out if m in self.herramienta_rec]:
                if not any(self.tiene(h, i) for i in self.recetas_con_propiedad(self.herramienta_rec[m])):
                    out.pop(m)
        if not con_agotados:
            out = {m: p for m, p in out.items() if self.restante(x, y, m) >= 1.0}
        return out

    # -------------------------------------------------------------- juntar
    def _accion_juntar(self, h, it: dict) -> Tuple[bool, str]:
        mat = str(it.get("material", "")).strip().lower()
        col = self.cosechar_colonia(h) if self.modulo("colonias") else None
        if col and (not mat or mat == col[0]):          # está parado sobre una colonia que da algo
            self._ganar_item(h, col[0], col[1])
            h.accion, h.detalle, h.hasta = "juntando", col[0], self.t + TIEMPO_JUNTAR_MIN
            h.camino = []
            return True, "Juntaste %d de %s de lo que crece acá." % (col[1], col[0])
        disp = self.disponibles(h)
        if mat not in disp:
            prop = self.herramienta_rec.get(mat)
            if prop and int(self.terreno.bioma[int(h.y), int(h.x)]) in self.recoleccion.get(mat, ()):
                return False, "Hay %s acá, pero está metido en la roca: con las manos no sale." % mat
            if mat in self.agotados(h):
                return False, "Acá ya juntaste todo el %s; vuelve a crecer con los días. Habría que buscar en otro lado." % mat
            return False, "Acá no encontrás eso. Lo que hay: %s." % (", ".join(sorted(disp)) or "nada útil")
        h.accion, h.detalle, h.hasta = "juntando", mat, self.t + TIEMPO_JUNTAR_MIN
        h.camino = []
        if self.rng.random() > disp[mat]:
            return True, "Buscaste %s un rato pero no encontraste." % mat
        lo, hi = self.cant_rec.get(mat, (1, 2))
        n = self.rng.randint(lo, hi)
        if self.modulo("atributos") and self.atributo(h, "fuerza") > 0.5:   # brazos fuertes rinden más
            n += int(self.rng.random() < (self.atributo(h, "fuerza") - 0.5) * 1.2)
        n = min(n, max(1, int(self.restante(h.x, h.y, mat))))
        self._gastar_recurso(h.x, h.y, mat, n)
        self._ganar_item(h, mat, n)
        primera = mat not in h.recursos
        if primera:
            h.recursos.add(mat)
            self._recuerdo(h, "En este lugar se consigue %s (cerca de (%d, %d))." % (mat, int(h.x), int(h.y)), 0.5, "semantica")
        return True, "Juntaste %d de %s." % (n, mat)

    # ------------------------------------------------------------ fabricar
    def _ingredientes_ok(self, h, r: dict) -> Tuple[Optional[List[str]], str]:
        """(lista de ítems concretos a consumir, motivo si falta algo)."""
        usar, pedido = [], dict()
        for ing in r["ingredientes"]:
            if ing.startswith("#"):
                # `self.etiquetas` se compila una vez por mundo: antes esto releía el JSON de disco en
                # CADA fabricación, y además las etiquetas de un mundo incluyen las menas que ese mundo
                # inventó (ver motor/minerales.py), que en el archivo no están.
                opts = sorted(self.etiquetas.get(ing[1:], ()), key=lambda m: -h.inventario.get(m, 0))
                elegido = next((m for m in opts if h.inventario.get(m, 0) - pedido.get(m, 0) > 0), None)
                if elegido is None:
                    return None, "te falta algo de «%s»" % ing[1:]
            else:
                elegido = ing
                if h.inventario.get(ing, 0) - pedido.get(ing, 0) <= 0:
                    return None, "te falta %s" % ing
            pedido[elegido] = pedido.get(elegido, 0) + 1
            usar.append(elegido)
        for herr in r.get("herramienta", []):
            if not self.tiene(h, herr):
                return None, "te falta la herramienta %s" % herr
        return usar, ""

    def puede_fabricar(self, h, r: dict) -> bool:
        if not self.sabe(h, r["id"]):
            return False
        usar, _ = self._ingredientes_ok(h, r)
        return usar is not None and self.requisitos_ok(h, r)[0]

    def _accion_fabricar(self, h, it: dict) -> Tuple[bool, str]:
        r = self._receta_de(it.get("objeto") or it.get("receta"))
        if r is None:
            return False, "No sabés qué es eso."
        if not self.sabe(h, r["id"]):
            return False, "Todavía no descubriste cómo hacer eso."
        usar, falta = self._ingredientes_ok(h, r)
        if usar is None:
            return False, "No podés hacer %s: %s." % (r["nombre"], falta)
        ok_req, por_que = self.requisitos_ok(h, r, usar)
        if not ok_req:
            return False, por_que
        est = r.get("estructura")
        # el tope es de CASAS: un horno, una fragua o un pozo no son el techo de nadie (abrigo 0) y no
        # tienen que gastar el cupo, o levantar un horno deja a la persona sin poder construirse la casa
        if est and float(est.get("abrigo", 0.0)) > 0 and \
                sum(1 for x in self.refugios if x["dueno"] == h.id and float(x.get("abrigo", 0.0)) > 0) >= MAX_REFUGIOS_POR_PERSONA:
            return False, "Ya tenés suficientes refugios."
        if est and not self.terreno.caminable(int(h.x), int(h.y)):
            return False, "Acá no se puede construir."
        for m in usar:
            h.inventario[m] -= 1
            if h.inventario[m] <= 0:
                h.inventario.pop(m, None); h.inv_t.pop(m, None)
        h.camino = []
        # el tiempo es de ESTA persona: con pulso y práctica tarda menos (ver motor/atributos.py)
        h.accion, h.detalle, h.hasta = ("construyendo" if est else "fabricando"), r["nombre"], self.t + self.tiempo_de_receta(h, r)
        self.practicar(h, r["id"])
        if est:
            nuevo = {"rid": self._nuevo_refugio(), "x": round(h.x, 2), "y": round(h.y, 2), "dueno": h.id,
                     "tipo": r["id"], "nombre": r["nombre"], "abrigo": float(est.get("abrigo", 0.0)),
                     "abrigo0": float(est.get("abrigo", 0.0)),   # lo que abrigaba nueva: el deterioro parte de acá
                     "visto": int(self.t), "t": int(self.t + r["tiempo_min"])}
            self.refugios.append(nuevo)
            techo = float(est.get("abrigo", 0.0)) > 0
            if techo:                                # un pozo, un horno o una fragua no son la casa de nadie
                h.hogar = (round(h.x, 1), round(h.y, 1))
                h.hogar_rid = nuevo["rid"]           # la cama PROPIA, no «el mejor techo de por acá»
            h.marcar_lugar("refugio", h.x, h.y, r["nombre"], self.t, radio=self.celdas(300.0))
            self._evento("construccion", "%s construyó %s." % (h.nombre, r["nombre"]), h, importancia=4, datos={"receta": r["id"]})
            self._recuerdo(h, ("Construiste %s. Es tu refugio: cerca de (%d, %d)." if techo else
                               "Construiste %s: quedó cerca de (%d, %d).") % (r["nombre"], int(h.x), int(h.y)), 0.85)
            self.sentir(h, "alegria", 0.3)
            if techo:
                self._hito("vivienda", h, "primera vivienda. %s construyó %s." % (h.nombre, r["nombre"]))
                if any(o["dueno"] != h.id and float(o.get("abrigo", 0.0)) > 0
                       and math.hypot(o["x"] - h.x, o["y"] - h.y) <= self.r_aldea for o in self.refugios):
                    self._hito("aldea", h, "primera aldea: varias viviendas de familias distintas, una junto a la otra.")
            # Un escalón de calor nuevo es un avance de la sociedad. La clave sale del DATO (los grados que
            # provee), así que agregar una estructura más caliente no pide tocar nada de esto.
            provee = self.estructuras.get(r["id"], {}).get("provee") or {}
            grados = float(provee.get("calor_C", 0))
            if grados > 0:
                self._hito("calor_%d" % int(grados), h,
                           "el calor de %d grados: %s levantó %s." % (int(grados), h.nombre, r["nombre"]))
            if float(provee.get("energia_W", 0)) > 0:
                self._hito("luz", h, "la corriente eléctrica. %s levantó %s." % (h.nombre, r["nombre"]))
            return True, "Construiste %s (te llevó un buen rato)." % r["nombre"]
        res = r["resultado"]
        n = int(res.get("cantidad", 1))
        if res.get("desde_mena"):
            # El resultado lo dice el MATERIAL, no la receta: fundir una mena da el metal que esa mena
            # declara. Con esto una sola receta funde las 19 menas del catálogo y las que el mundo invente.
            res = dict(res, item=next((self.metal_de(m) for m in usar if self.metal_de(m) != m), usar[0]))
        self._ganar_item(h, res["item"], n)
        h.inv_t[res["item"]] = 0.0
        primera = res["item"] not in h.fabricados
        h.fabricados.add(res["item"])
        self._evento("fabricacion", "%s hizo %s." % (h.nombre, r["nombre"]), h, importancia=3 if primera else 1,
                     datos={"receta": r["id"], "item": res["item"], "n": n})
        self._recuerdo(h, "Hiciste %s con tus manos." % r["nombre"], 0.6 if primera else 0.3)
        if primera:
            self.experiencia(h, "fabricar")
        item = res["item"]
        if item in self.armas:
            self._hito("armas", h, "herramientas y armas. %s hizo %s." % (h.nombre, r["nombre"]))
        if r["propiedad"] == "funde":
            self._hito("metalurgia", h, "el primer metal. %s fundió %s." % (h.nombre, r["nombre"]))
        if r["propiedad"] == "abriga":
            self._hito("ropa", h, "primera ropa. %s hizo %s." % (h.nombre, r["nombre"]))
        if item == "tela":
            self._hito("telar", h, "el tejido: %s hizo la primera tela." % h.nombre)
        if item == "ceramica":
            self._hito("ceramica", h, "la cerámica: %s coció arcilla." % h.nombre)
        if r["propiedad"] == "contiene":
            self._hito("recipientes", h, "recipientes para guardar y cargar. %s hizo %s." % (h.nombre, r["nombre"]))
        return True, "Hiciste %s." % r["nombre"]

    # -------------------------------------------------------------- fuego
    def _accion_tomar_fuego(self, h, it: dict) -> Tuple[bool, str]:
        if not (self.fogata_cerca(h, self.r_mano) or self.fuego_cerca(h, self.r_mano)):
            return False, "No hay fuego al alcance para prender una rama."
        base = next((a for a in self.antorchas if self.tiene(h, a)), None) or ("palo" if self.tiene(h, "palo") else None)
        if base is None:
            return False, "Necesitás un palo o una antorcha para llevarte el fuego."
        h.inventario[base] -= 1
        if h.inventario[base] <= 0:
            h.inventario.pop(base, None); h.inv_t.pop(base, None)
        self._ganar_item(h, "antorcha_encendida", 1)
        h.inv_t["antorcha_encendida"] = 0.0 if base != "palo" else 0.5 * DURA_ANTORCHA_MIN
        h.accion, h.detalle, h.hasta = "esperando", "prende una rama", self.t + 3.0
        self._evento("fuego_llevado", "%s prendió una rama en el fuego y se la llevó." % h.nombre, h, importancia=3)
        self._recuerdo(h, "Prendiste una rama en el fuego: se puede llevar la llama a otro lado.", 0.8, "semantica")
        return True, "Prendiste una antorcha."

    def _accion_encender(self, h, it: dict) -> Tuple[bool, str]:
        f0 = self.fogata_cerca(h, self.r_mano)
        fuente = self.fuente_de_chispa(h)
        if fuente is None:
            return False, "No tenés con qué sacar fuego (chispa, frotar palos o una antorcha prendida)."
        if self.lena_que_lleva(h) < MIN_LENA:
            return False, "Te falta leña: juntá palos, paja o carbón."
        if self.nieve_en(h.x, h.y) > 0.6 and fuente != "antorcha_encendida":
            return False, "Con tanta nieve no prende."
        gastar = MIN_LENA
        for m in self.lena:
            while gastar > 0 and h.inventario.get(m, 0) > 0:
                h.inventario[m] -= 1
                gastar -= 1
            if h.inventario.get(m, 0) <= 0:
                h.inventario.pop(m, None); h.inv_t.pop(m, None)
            if gastar == 0:
                break
        mas = MIN_LENA * FOGATA_MIN_POR_LENA
        h.accion, h.detalle, h.hasta = "esperando", "prende el fuego", self.t + 10.0
        h.camino = []
        if f0:
            f0["hasta"] = max(f0["hasta"], self.t) + mas
            return True, "Le agregaste leña a la fogata."
        self.fogatas.append({"x": round(h.x, 2), "y": round(h.y, 2), "hasta": self.t + mas, "dueno": h.id})
        self._evento("fogata", "%s encendió una fogata." % h.nombre, h, importancia=3, datos={"con": fuente})
        self._hito("fuego", h, "dominio del fuego. %s encendió la primera fogata." % h.nombre)
        self._recuerdo(h, "Encendiste una fogata (con %s). Da calor, luz y sirve para cocinar." % fuente.replace("_", " "), 0.8, "semantica")
        h.marcar_lugar("refugio", h.x, h.y, "fogata", self.t, radio=self.celdas(300.0))
        self.sentir(h, "alegria", 0.3)
        self.experiencia(h, "hacer_fuego")
        return True, "Encendiste una fogata."

    def _paso_tecnologia(self, paso: float) -> None:
        self._acum_tec = getattr(self, "_acum_tec", 0.0) + paso
        if self._acum_tec < 10.0:
            return
        dt, self._acum_tec = self._acum_tec, 0.0
        if self.fogatas:
            vivas = []
            for f in self.fogatas:
                if self.nieve_en(f["x"], f["y"]) > 0.7:
                    f["hasta"] -= dt * 2.0                # la nieve la apaga antes
                if f["hasta"] > self.t:
                    vivas.append(f)
            self.fogatas = vivas
        self._paso_ruinas()

    def _paso_ruinas(self) -> None:
        """Lo que nadie usa se cae. Una vez por día simulado, no por tick: son 400 refugios contra 25
        personas y no hace falta más resolución que ésa para algo que tarda estaciones.

        «Usado» es tránsito: alguien parado dentro del radio del techo. Si no pasa nadie durante
        `DIAS_SIN_USO`, el abrigo empieza a caer, y abajo de un umbral la casa queda como RUINA: sigue en
        el mapa (la ruina es historia del mundo) pero ya no abriga ni es el hogar de nadie.
        """
        ultimo = getattr(self, "_ruinas_t", None)
        if ultimo is not None and self.t - ultimo < MIN_DIA:
            return
        dias = 1.0 if ultimo is None else (self.t - ultimo) / MIN_DIA
        self._ruinas_t = self.t
        if ultimo is None:
            return
        vivos = [h for h in self.habitantes.values() if h.vivo]
        for r in self.refugios:
            if r.get("natural") or float(r.get("abrigo", 0.0)) <= 0:
                continue                             # las bocas de caverna y los pozos no se arruinan
            if any(math.hypot(h.x - r["x"], h.y - r["y"]) <= self.r_refugio for h in vivos):
                r["visto"] = int(self.t)
                continue
            if self.t - float(r.get("visto", self.t)) < DIAS_SIN_USO * MIN_DIA:
                continue
            r["abrigo"] = round(max(0.0, float(r["abrigo"]) - DESGASTE_POR_DIA * dias), 3)
            if r["abrigo"] <= MIN_ABRIGO:
                r["abrigo"], r["ruina"] = 0.0, True
                for h in self.habitantes.values():
                    if h.hogar_rid == r.get("rid"):
                        h.hogar, h.hogar_rid = None, None
                self._evento("ruina", "%s quedó en ruinas: no pasó nadie en mucho tiempo." % r.get("nombre", "Un refugio"),
                             x=r["x"], y=r["y"], importancia=2, origen="sistema", datos={"rid": r.get("rid")})

    # ----------------------------------------------------------- usar cosas
    def curativo(self, h) -> Optional[str]:
        for i in self.recetas_con_propiedad("cura"):
            if self.tiene(h, i):
                return i
        return None

    def _accion_usar(self, h, it: dict) -> Tuple[bool, str]:
        item = str(it.get("objeto") or it.get("item") or "").strip().lower()
        r = self._receta_de(item)
        i = r["id"] if r else item
        if r is None or r["propiedad"] != "cura" or not self.tiene(h, r["resultado"]["item"]):
            return False, "No tenés nada así para curarte."
        it_id = r["resultado"]["item"]
        h.inventario[it_id] -= 1
        if h.inventario[it_id] <= 0:
            h.inventario.pop(it_id, None); h.inv_t.pop(it_id, None)
        h.salud = min(100.0, h.salud + 25.0)
        h.accion, h.detalle, h.hasta = "esperando", "se cura", self.t + 15.0
        self._recuerdo(h, "Te curaste con %s." % r["nombre"], 0.6)
        return True, "Usaste %s y te sentís mejor." % r["nombre"]

    def bono_arma(self, h) -> Tuple[float, float]:
        bono, alcance = 0.0, 0.0
        for item, (b, al) in self.armas.items():
            if self.tiene(h, item) and b > bono:
                bono, alcance = b, al
        if self.modulo("atributos"):            # la fuerza también cuenta, con arma o sin ella
            bono += 0.25 * (self.atributo(h, "fuerza") - 0.3)
        return max(0.0, bono), alcance

    def proteccion_de(self, h) -> float:
        """0..0.5 menos daño por ataques si lleva algo que proteja."""
        n = sum(1 for i in self.recetas_con_propiedad("protege") if self.tiene(h, i))
        return min(0.5, 0.25 * n)

    def abrigo_objetos(self, h) -> float:
        n = sum(1 for i in self.recetas_con_propiedad("abriga") if self.tiene(h, i))
        return min(0.6, 0.22 * n)

    # ------------------------------------------------------------- hitos
    def _hito(self, clave: str, h, texto: str) -> None:
        """Un avance de la sociedad (primera vez en este mundo). Sale como alerta en el visor."""
        if clave in self.hitos:
            return
        self.hitos.add(clave)
        self._evento("hito", "🌅 Nueva etapa: %s" % texto, h, importancia=5, datos={"hito": clave})

    # --------------------------------------------------------- persistencia
    def exportar_estructuras(self) -> dict:
        return {"fogatas": self.fogatas, "refugios": self.refugios, "hitos": sorted(self.hitos),
                # los minerales que sorteó este mundo: se guardan para que editar el espacio de lo posible
                # no le cambie la geología a una partida ya empezada (ver motor/minerales.py)
                "minerales": getattr(self, "minerales_mundo", []),
                "naturales_sembradas": sorted(getattr(self, "naturales_sembradas", [])),
                "prox_refugio": self.prox_refugio, "prox_aldea": self.prox_aldea,
                "aldea_num": {str(k): v for k, v in self.aldea_num.items()},
                "agotamiento": {k: [round(u, 2), round(tt, 1)] for k, (u, tt) in self.agotamiento.items()}}

    def importar_estructuras(self, d: dict) -> None:
        if d.get("minerales"):              # lo guardado manda sobre lo que se vuelva a sortear
            self.inyectar_minerales(d["minerales"])
        self.fogatas = [f for f in d.get("fogatas", []) if f.get("hasta", 0) > self.t]
        self.refugios = list(d.get("refugios", []))[-400:]
        self.hitos = set(d.get("hitos", []))
        self.naturales_sembradas = list(d.get("naturales_sembradas", []))
        self.prox_refugio = int(d.get("prox_refugio", 1))
        self.prox_aldea = int(d.get("prox_aldea", 1))
        self.aldea_num = {int(k): int(v) for k, v in (d.get("aldea_num") or {}).items()}
        for r in self.refugios:                      # mundos de antes: sus casas no tenían identidad propia
            if r.get("rid") is None:
                r["rid"] = self.prox_refugio
                self.prox_refugio += 1
            r.setdefault("abrigo0", float(r.get("abrigo", 0.0)))     # ni cuánto abrigaban nuevas
            r.setdefault("visto", int(r.get("t", self.t)))           # ni cuándo pasó alguien por última vez
        self.agotamiento = {k: (float(v[0]), float(v[1])) for k, v in (d.get("agotamiento") or {}).items()}

    def aldeas(self) -> List[dict]:
        """Grupos de refugios pegados (≤ METROS_ALDEA entre vecinos). Una aldea necesita CASAS: con menos de 2 refugios
        no hay aldea, por más gente que haya parada ahí. El número es estable: una aldea se sigue llamando «Aldea 3»
        aunque le agreguen chozas o aparezca otra más grande al lado."""
        # Una aldea son CASAS. Las bocas de caverna y los pozos están en la misma lista y no cuentan.
        sin_ver = [r for r in self.refugios if r.get("rid") is not None and float(r.get("abrigo", 0.0)) > 0]
        out = []
        while sin_ver:
            grupo = [sin_ver.pop()]
            i = 0
            while i < len(grupo):                      # crece el grupo por vecindad, no por distancia al centro
                a = grupo[i]
                i += 1
                for r in list(sin_ver):
                    if math.hypot(r["x"] - a["x"], r["y"] - a["y"]) <= self.r_aldea:
                        sin_ver.remove(r)
                        grupo.append(r)
            if len(grupo) < 2:
                continue
            cx = sum(r["x"] for r in grupo) / len(grupo)
            cy = sum(r["y"] for r in grupo) / len(grupo)
            radio = max(6.0, max(math.hypot(r["x"] - cx, r["y"] - cy) for r in grupo) + 4.0)
            # el número ya asignado a cualquiera de sus casas; si dos aldeas se juntan, se queda con el más viejo
            viejos = sorted(n for n in (self.aldea_num.get(r["rid"]) for r in grupo) if n is not None)
            num = viejos[0] if viejos else self._nuevo_numero_aldea()
            for r in grupo:
                self.aldea_num[r["rid"]] = num
            duenos = [d for d in dict.fromkeys(r["dueno"] for r in grupo)]
            vecinos = [h for h in self.habitantes.values()
                       if h.vivo and (h.id in duenos or math.hypot(h.x - cx, h.y - cy) <= radio)]
            out.append({"num": num, "nombre": "Aldea %d" % num, "x": round(cx, 1), "y": round(cy, 1),
                        "r": round(radio, 1), "casas": len(grupo), "familias": len(duenos),
                        "gente": [{"id": h.id, "nombre": h.nombre} for h in sorted(vecinos, key=lambda h: h.id)]})
        out.sort(key=lambda a: a["num"])
        return out

    def _nuevo_refugio(self) -> int:
        self.prox_refugio = max(1, int(getattr(self, "prox_refugio", 1)))
        n, self.prox_refugio = self.prox_refugio, self.prox_refugio + 1
        return n

    def _nuevo_numero_aldea(self) -> int:
        self.prox_aldea = max(1, int(getattr(self, "prox_aldea", 1)))
        n, self.prox_aldea = self.prox_aldea, self.prox_aldea + 1
        return n

    def publico_estructuras(self) -> dict:
        return {"fogatas": [[f["x"], f["y"], round(max(0.0, min(1.0, (f["hasta"] - self.t) / (MIN_LENA * FOGATA_MIN_POR_LENA))), 2)]
                            for f in self.fogatas],
                "refugios": [[r["x"], r["y"], r["tipo"]] for r in self.refugios],
                # lista aparte y no un campo más en `refugios`, para no cambiarle la forma a lo que ya dibuja la UI
                "ruinas": [[r["x"], r["y"], r["tipo"]] for r in self.refugios if r.get("ruina")],
                # Los senderos van publicados aunque sean un BIOMA. La idea era que la UI los
                # dibujara gratis con la paleta, pero la capa de biomas que recibe el visor se
                # escribe UNA vez, al generar el mundo (`mundo_io.guardar_capas`), así que
                # `Terreno.cambiar_bioma` no llega nunca hasta allá: medido, 0 celdas de sendero en
                # la capa servida por la API. Van por el estado, que ya viaja 10 veces por segundo,
                # y son pocas: sólo las celdas que de verdad se abrieron.
                "senderos": self.publico_senderos(),
                "aldeas": self.aldeas()}


# Lo que se les ocurre hacer, en orden de necesidad, cuando el modelo no decide (respaldo) o como pista. Son ids de recetas.
# (la lista de objetivos del respaldo vive en datos_base/cultura/objetivos.json)


def _plan(self, h):
    """Una acción concreta para avanzar en la tecnología (o None). Es el 'sentido común' del respaldo y de los reflejos."""
    frio = self.modulo("frio") and self.severidad_frio(h) > 0.2
    if h.salud < 50 and self.curativo(h):
        return {"tipo": "usar", "objeto": self.curativo(h)}
    if (frio or self.t % 1440 > 1080 or self.t % 1440 < 300) and not self.fogata_cerca(h, self.r_fogata):
        if self.fuente_de_chispa(h) and self.lena_que_lleva(h) >= MIN_LENA:
            return {"tipo": "encender"}
        if self.fuente_de_chispa(h) and "palo" in self.disponibles(h):
            return {"tipo": "juntar", "material": "palo"}
        if not self.fuente_de_chispa(h) and (self.fogata_cerca(h, self.r_mano) or self.fuego_cerca(h, self.r_mano)) and (self.tiene(h, "palo") or any(self.tiene(h, a) for a in self.antorchas)):
            return {"tipo": "tomar_fuego"}
    for rid in self.objetivos:
        r = self.recetas.get(rid)
        if r is None:
            continue
        res = r["resultado"]["item"]
        if r.get("estructura"):
            if any(x["dueno"] == h.id for x in self.refugios):
                continue
        elif self.tiene(h, res):
            continue
        if not self.sabe(h, rid):
            if self.t - h.ultima_idea_t > 300 and self.modulo("conocimientos"):
                ing = []
                for m in r["ingredientes"]:
                    if m.startswith("#"):
                        m = sorted(self.etiquetas.get(m[1:], ("palo",)))[0]
                    ing.append(m)
                return {"tipo": "inventar", "receta": {"nombre": r["nombre"], "materiales": ing, "propiedad": r["propiedad"],
                                                        "descripcion": r.get("descripcion", "")}}
            return None
        usar, falta = self._ingredientes_ok(h, r)
        if usar is not None:
            if not self.requisitos_ok(h, r)[0]:
                continue
            return {"tipo": "fabricar", "objeto": rid}
        disp = self.disponibles(h)
        for ing in r["ingredientes"]:
            if not ing.startswith("#") and h.inventario.get(ing, 0) <= 0:
                if ing in disp:
                    return {"tipo": "juntar", "material": ing}
                break
        return None
    return None


TecnologiaMixin.plan_tecnologico = _plan

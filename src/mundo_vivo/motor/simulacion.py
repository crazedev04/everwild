"""
Simulación viva del mundo: reloj, habitantes que se mueven, fuego, clima y gravedad.

El motor NO decide qué quiere hacer cada habitante: eso lo decide un `Cerebro` (intercambiable).
Hoy hay un cerebro de DEMOSTRACIÓN con reglas simples para poder ver el mundo en movimiento;
el cerebro real (modelo de lenguaje + genoma) se conecta en la Fase 3 usando la misma interfaz:

    cerebro.decidir(sim, habitante) -> {"tipo": "ir" | "dormir" | "esperar" | "beber", ...}

El motor valida y ejecuta (caminos, tiempos, necesidades, daño); el cerebro solo propone.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import reloj
from .fenomenos import Clima, camino_de_caida
from .fuego import Fuego
from .navegacion import Terreno
from .ecologia import CANALES, EcologiaMixin
from .frio import FrioMixin
from .alimentacion import HAMBRE_DESPIERTA, AlimentacionMixin
from .atencion import AtencionMixin
from .atributos import BASE as ATRIB_BASE, AtributosMixin
from .conservacion import ConservacionMixin
from .fenomenos_datos import FenomenosMixin
from .objetivos import ObjetivosMixin
from .minerales import MineralesMixin
from .propagacion import PropagacionMixin
from .psique import PsiqueMixin
from .senderos import SenderosMixin
from .tecnologia import TecnologiaMixin
from .fauna import CLAVES_HABITAT, Fauna
from .vida import ANIO_MIN, VidaMixin
from .. import catalogos
from ..agentes import conocimiento as _conocimiento
from ..reglas import Reglas

PASO_MAX = 1.0  # minutos simulados por sub-paso
# Con esta sed uno se despierta aunque esté durmiendo. El cerebro usa el MISMO número para no volver a dormirse:
# si se separan, el que duerme se despierta por sed, se vuelve a dormir, y se muere al lado del agua.
SED_DESPIERTA = 80.0


class HabitanteSim:
    def __init__(self, id: int, nombre: str, x: float, y: float, salud: float = 100.0, sed: float = 30.0,
                 energia: float = 90.0, color: int = 0, vivo: bool = True):
        self.id, self.nombre, self.color = id, nombre, color
        self.x, self.y = float(x), float(y)
        self.salud, self.sed, self.energia = float(salud), float(sed), float(energia)
        self.hambre = 0.0          # cuarta barra: independiente de las otras tres
        # Lo que se construye viviendo (no se hereda: eso es el genoma)
        self.atributos: Dict[str, float] = {}      # fuerza, resistencia, pulso
        self.destrezas: Dict[str, float] = {}      # receta -> 0..1 de práctica
        self.objetivo: Optional[dict] = None       # qué quiere ahora y desde cuándo
        self.viaje: Optional[dict] = None          # efecto de una planta psicoactiva, si tiene uno encima
        self.vivo = vivo
        self.causa_muerte: Optional[str] = None
        self.t_muerte: Optional[int] = None
        self.accion = "libre"      # libre | caminando | durmiendo | bebiendo | esperando
        self.detalle = ""
        self.camino: List[Tuple[int, int]] = []
        self.hasta = 0.0           # ocupado hasta este minuto
        self.al_llegar: Optional[str] = None
        self.en_fuego = False
        self.herido_fuego = False
        # su lugarcito dentro de la celda: sin esto todos caminan al centro exacto y quedan uno encima del otro.
        # Ángulo dorado para que queden bien repartidos, y radio variado para que no formen un anillo.
        _a = 2.39996323 * id
        _r = 0.32 * math.sqrt(((id * 0.6180339887) % 1.0) * 0.75 + 0.25)
        self.sesgo = (_r * math.cos(_a), _r * math.sin(_a))
        # vida social y familia
        self.sexo = "F"
        self.nacimiento_min = -25 * ANIO_MIN      # los fundadores ya son adultos
        self.genoma = None                         # agentes.genoma.Genoma (o None)
        self.madre_id: Optional[int] = None
        self.padre_id: Optional[int] = None
        self.pareja_id: Optional[int] = None       # Fase 8: compromiso formal
        self.embarazo: Optional[dict] = None
        self.sin_concebir_hasta = 0.0
        self.propuesta: Optional[dict] = None
        self.mensajes: List[tuple] = []           # lo que le dijeron y todavía no respondió
        self.ultimo_dicho: Dict[int, str] = {}
        self.conoce: set = set()                  # ids de conocimientos
        self.prox_vista = 0.0
        self.ultimo_resultado = ""                # resultado de lo último que intentó (para el cerebro)
        self.lugares_agua: set = set()
        # ecología y emociones
        self.emo: Dict[str, float] = {c: 0.0 for c in CANALES}
        self.inventario: Dict[str, int] = {}
        self.recursos: set = set()                    # materiales que sabe dónde se consiguen
        self.fabricados: set = set()
        self.hogar = None                             # (x, y) de su refugio
        self.hogar_rid: Optional[int] = None          # y qué refugio es: la cama propia, no «la mejor de acá»
        self.cama = 0.0                               # abrigo efectivo de donde se acostó (se mide al dormir)
        self.rotos = 0                                # lotes que se le pudrieron (aprendió a conservar)
        self.inv_t: Dict[str, float] = {}             # edad media (min) de cada lote del inventario
        self.montura: Optional[int] = None
        # inquietud: cuándo fue la última vez que vivió algo nuevo (lugar, idea, caza, persona)
        self.novedad_t = 0.0
        self.zonas: set = set()
        self.ultima_charla: Dict[int, float] = {}      # a quién le habló y cuándo
        self.oido_de: Dict[int, float] = {}            # quién le habló a él y cuándo
        self.historial_dicho: List[str] = []
        self.visto: Dict[int, list] = {}              # id -> [x, y, t] de la última vez que lo vio
        self.ultima_idea_t = 0.0                      # cuándo probó una idea por última vez
        self.ataque_t = -1e9                          # último ataque de un animal sufrido
        self.frio = 0.0                               # severidad actual del frío (0 = nada)
        self.sin_regenerar = False
        self.avisado_frio = False
        self.lugares: Dict[str, list] = {}            # tipo -> [[x, y, t, nota, veces]]: agua, peligro, comida, refugio...
        self.plan: List[str] = []                     # intenciones que se propuso en su última reflexión
        self.rasgos_vivos: Dict[str, float] = {}      # carácter actual: parte del genoma y cambia con lo que vive
        self.habito = None                            # agentes.habito.Habito: red propia que aprende de sus resultados
        self.snap = None                              # foto al elegir una actividad, para calcular cómo le fue
        self.habito_v: Dict[str, float] = {}          # últimas inclinaciones calculadas (para mostrar)
        self.ultima_reflexion_t = 0.0

    def rasgo(self, k: str) -> float:
        if k in self.rasgos_vivos:
            return self.rasgos_vivos[k]
        return self.genoma.rasgos.get(k, 0.5) if self.genoma is not None else 0.5

    def marcar_lugar(self, tipo: str, x: float, y: float, nota: str, t: float, radio: float = 6.0, max_por_tipo: int = 8) -> None:
        """Recuerda un sitio (agua, peligro, comida...). Si ya tenía uno a menos de `radio` celdas, lo refuerza en vez de duplicar."""
        lst = self.lugares.setdefault(tipo, [])
        for p in lst:
            if math.hypot(p[0] - x, p[1] - y) <= radio:
                p[2], p[4] = t, p[4] + 1
                if nota:
                    p[3] = nota
                return
        lst.append([round(x, 1), round(y, 1), t, nota, 1])
        if len(lst) > max_por_tipo:      # se olvida lo más viejo y menos repetido
            lst.sort(key=lambda p: (p[4], p[2]))
            lst.pop(0)

    def a_publico_mapa(self) -> dict:
        """Lo mínimo para dibujar el mapa. Las barras finas y los atributos van por `vitales`/ficha:
        el mapa se redibuja 10 veces por segundo y no necesita lo que no cambia."""
        return {"id": self.id, "nombre": self.nombre, "color": self.color, "x": round(self.x, 3), "y": round(self.y, 3),
                "vivo": self.vivo, "accion": self.accion, "detalle": self.detalle, "sexo": self.sexo,
                "nac": int(self.nacimiento_min), "en_fuego": self.en_fuego,
                "antorcha": bool(self.inventario.get("antorcha_encendida", 0)),
                "emo": {k: round(v, 2) for k, v in self.emo.items() if v > 0.1}}

    def a_publico(self) -> dict:
        return {"id": self.id, "nombre": self.nombre, "color": self.color, "x": round(self.x, 3), "y": round(self.y, 3),
                "salud": round(self.salud, 1), "sed": round(self.sed, 1), "energia": round(self.energia, 1),
                "hambre": round(self.hambre, 1),
                "atributos": {k: round(v, 3) for k, v in self.atributos.items()},
                "objetivo": self.objetivo,
                "accion": self.accion, "detalle": self.detalle, "vivo": self.vivo, "en_fuego": self.en_fuego,
                "sexo": self.sexo, "embarazada": bool(self.embarazo), "montado": self.montura is not None,
                "emo": {k: round(v, 2) for k, v in self.emo.items() if v > 0.1},
                "nac": int(self.nacimiento_min),
                # lleva fuego en la mano: en el mapa se le ve la llama y le ilumina alrededor de noche
                "antorcha": bool(self.inventario.get("antorcha_encendida", 0))}


class Cerebro:
    nombre = "base"
    # Cliente del modelo de lenguaje, si el cerebro usa uno. `None` significa que no hay modelo, y
    # entonces no hay latencia que limite la velocidad del mundo (ver `Ejecutor.tope_pensando`).
    cliente = None

    def decidir(self, sim: "Simulacion", h: HabitanteSim) -> dict:
        return {"tipo": "esperar", "min": 15}


class CerebroDemo(Cerebro):
    """Reglas simples SOLO para demostrar el mundo en movimiento. No es inteligencia."""
    nombre = "demostración (reglas simples)"

    def decidir(self, sim: "Simulacion", h: HabitanteSim) -> dict:
        rng = sim.rng
        # Si se está muriendo de sed, el agua primero: la sed mata en horas y un fuego lejano no.
        f = None if h.sed >= SED_DESPIERTA else sim.fuego_cerca(h, sim.r_huir_fuego)
        if f:
            fx, fy, d = f
            ref = sim.refugio_de_fuego(h)
            if ref:
                return {"tipo": "ir", "destino": ref, "motivo": "huye del fuego"}
            vx, vy = h.x - fx, h.y - fy
            n = math.hypot(vx, vy) or 1.0
            for dist in (28, 18, 10):
                c = sim.terreno.caminable_cerca(int(h.x + vx / n * dist), int(h.y + vy / n * dist), 4)
                if c and sim.fuego.fuego[c[1], c[0]] == 0:
                    return {"tipo": "ir", "destino": c, "motivo": "huye del fuego"}
        if h.sed >= 55:
            if sim.terreno.agua_adyacente(int(h.x), int(h.y)):
                return {"tipo": "beber"}
            c = sim.agua_cercana(h, sim.r_agua_cerca) or sim.agua_cercana(h, sim.r_agua_lejos)
            if c:
                return {"tipo": "ir", "destino": c, "luego": "beber", "motivo": "tiene sed"}
            b = sim.buscar_agua_lejos(h)
            if b:
                return b
        if h.energia <= 25 or (reloj.es_noche(sim.t) and h.energia < 70):
            return {"tipo": "dormir", "min": rng.randint(240, 420)}
        if rng.random() < 0.3:
            return {"tipo": "esperar", "min": rng.randint(10, 40)}
        for _ in range(8):
            d = rng.uniform(sim.celdas(300.0), sim.celdas(900.0))     # en metros: en celdas quedaba en 90 m
            a = rng.random() * 2 * math.pi
            c = sim.terreno.caminable_cerca(int(h.x + math.cos(a) * d), int(h.y + math.sin(a) * d), 3)
            if c:
                return {"tipo": "ir", "destino": c, "motivo": "explora"}
        return {"tipo": "esperar", "min": 15}


class Simulacion(VidaMixin, EcologiaMixin, FrioMixin, ConservacionMixin, AlimentacionMixin, AtributosMixin, AtencionMixin, FenomenosMixin, ObjetivosMixin, PsiqueMixin, PropagacionMixin, MineralesMixin, SenderosMixin, TecnologiaMixin):
    def __init__(self, capas: dict, meta: dict, t_min: float = 480, semilla: Optional[int] = None,
                 cerebro: Optional[Cerebro] = None, dimension: int = 0, ident: str = "mundo",
                 base: Optional["Simulacion"] = None):
        """`dimension` es dónde transcurre esto: 0 es el mundo de siempre. Cada dimensión tiene su propio
        terreno, fuego, clima, fauna y nieve, porque son mapas distintos. Lo que es del MUNDO y no del mapa
        (ajustes, conocimientos, quién conoce a quién) se comparte pasando `base`: así inventar algo en una
        caverna lo sabe también el de arriba."""
        self.dimension = int(dimension)
        self.ident = ident
        self.meta = meta
        self.semilla = int(meta["semilla"] if semilla is None else semilla)
        self.tam_celda_m = float(meta["tam_celda_m"])
        self._calcular_escala()
        self.terreno = Terreno(capas, self.tam_celda_m)
        self.fuego = Fuego(capas["bioma"], capas["agua"], self.semilla, capas.get("humedad"))
        self.clima = Clima(self.terreno.ancho, self.terreno.alto, self.semilla, self.fuego.viento)
        self.t = float(t_min)
        self.cerebro = cerebro or CerebroDemo()
        self.rng = random.Random(self.semilla * 31 + int(t_min))
        self.habitantes: Dict[int, HabitanteSim] = {}
        self._eventos: List[dict] = []
        self._efectos: List[dict] = []
        self._acum_fuego = 0.0
        self._acum_nieve = 0.0
        self.fogatas: List[dict] = []
        self.hitos: set = set()
        self.agotamiento: dict = {}
        self.refugios: List[dict] = []
        self.prox_refugio = 1          # identidad de cada casa, para que el número de aldea no se mueva
        self.prox_aldea = 1
        self.aldea_num: dict = {}      # rid de la casa -> número de la aldea a la que pertenece
        # vida social / conocimientos
        # Los módulos salen de UNA sola lista (agentes/ajustes.py). Antes había acá un diccionario aparte que no
        # incluía `personalidad`, `atributos` ni `objetivos`: un módulo nuevo quedaba sin efecto en silencio.
        from ..agentes.ajustes import PREDETERMINADOS as _PRE
        self.ajustes: dict = {"modulos": dict(_PRE["modulos"])}
        from ..agentes.semantica import Semantica
        # Vectores de significado de los recuerdos. Inerte hasta que haya cliente y el módulo esté encendido.
        self.semantica = Semantica(getattr(self.cerebro, "cliente", None))
        self.ajustes["modulos"]["fauna"] = False      # una simulación pelada no puebla fauna hasta que se pide
        from ..registro import Registro
        self.registro = Registro.cargar()      # todo el contenido del mundo sale de acá
        self._compilar_materiales()            # materiales, armas, antorchas, leña
        self._compilar_estructures()           # estructuras que proveen calor/energía
        self._compilar_objetives()             # objetivos de respaldo
        self._compilar_conservacion()
        self._compilar_alimentos()
        self._compilar_fenomenos()
        self._compilar_psicoactivos()
        self._compilar_colonias()
        self._compilar_atencion()
        self.reglas = Reglas.cargar()
        self.especies = catalogos.cargar_especies(CLAVES_HABITAT)
        # las estructuras ya están compiladas (`_compilar_materiales` las leyó del registro): con ellas se
        # valida que toda estructura declarada se pueda construir de verdad (catalogos._validar_estructuras)
        self.recetas = catalogos.cargar_recetas(self.reglas.materiales, _conocimiento.PROPIEDADES, self.estructuras)
        # Etiquetas (#lena, #mena_de_hierro) compiladas una vez: antes se releía el JSON de disco en cada
        # fabricación, y además las de un mundo incluyen las menas que ESE mundo inventó.
        self.etiquetas = catalogos.cargar_etiquetas()
        # Los minerales que no están en ningún catálogo: los sortea este mundo de su semilla.
        self.minerales_mundo: List[dict] = []
        self.inyectar_minerales(self.generar_minerales_desconocidos())
        self._compilar_senderos()           # el desgaste del suelo (motor/senderos.py)
        # Qué hay sobre la cabeza. Bajo tierra no hay sol, ni estaciones, ni nieve, ni tormentas: el motor
        # no sabe qué es una caverna, sólo lee estos dos interruptores de los datos de la dimensión.
        self.cielo = dict((self.registro.uno("dimension", self.ident) or {}).get("cielo")
                          or {"dia_noche": True, "estaciones": True})
        self.fauna = Fauna(self.terreno, self.fuego, self.semilla, self.especies)
        self.nieve = np.zeros((self.terreno.alto, self.terreno.ancho), dtype=np.float32)     # 0..1 por celda
        self._suelo_nevable = self.terreno.agua == 0
        self._temp_media_base = float(self.terreno.temperatura[self._suelo_nevable].mean()) if self._suelo_nevable.any() else 15.0
        # La humedad del mapa no cambia nunca, así que el factor de acumulación de nieve se arma una
        # sola vez. `_paso_nieve` lo rearmaba entero cada vez que corría: un array de 4,2 millones
        # de celdas de puro gasto. La TEMPERATURA no se cachea a propósito: es un array público y
        # cachear sus valores dejaría que escribirle no tuviera efecto, que es exactamente la
        # trampa de `Terreno.costo` y `Terreno._c` (ver «Trampas ya vistas» en CLAUDE.md).
        self._hum_nieve = 0.4 + self.terreno.humedad.astype(np.float32) / 255.0
        self._hay_nieve = False     # lo prende el primer copo y lo apaga el último deshielo
        self.fauna.temp_fn = self.temp_en                                                   # los animales también sienten el frío
        self._fauna_lista = False          # True cuando la fauna ya se pobló o se cargó de la base
        self.centro_seguro = None          # (x, y): sin grandes depredadores al empezar cerca de ahí
        # Buffer de propuestas del Cerebro Cognitivo — desacopla el hilo cognitivo del tick crítico.
        # Clave: id del habitante. El motor reutiliza la última propuesta si el cerebro aún no resolvió
        # la siguiente (relevante cuando el CE real tarda; el CerebroDemo resuelve en microsegundos).
        self._propuestas_cerebro: Dict[int, dict] = {}
        self.conocimientos: Dict[int, dict] = {}
        self.conocidos: set = set()
        self.al_nacer = None       # callback(sim, madre, padre, genoma, sexo, nombre) -> HabitanteSim (lo pone sim_io)
        self.al_inventar = None    # callback(sim, h, nombre, materiales, propiedad, descripcion) -> id
        self.mundo = None          # motor.mundo.Mundo, si este mapa es parte de un mundo con varias dimensiones
        if base is not None:
            self.compartir_con(base)

    def compartir_con(self, base: "Simulacion") -> None:
        """Lo que es del mundo entero y no de este mapa pasa a ser EL MISMO objeto que el de `base`.

        Es a propósito que sean referencias y no copias: si alguien inventa algo en la caverna, el de arriba
        tiene que saberlo; si se apaga un módulo en el panel, se apaga en todas partes. Lo que NO se comparte
        es lo que depende del mapa (terreno, fuego, clima, fauna, nieve, estructuras)."""
        self.ajustes = base.ajustes
        self.registro = base.registro
        self.reglas = base.reglas
        self.especies = base.especies
        self.recetas = base.recetas
        self.conocimientos = base.conocimientos
        self.conocidos = base.conocidos
        self.semantica = base.semantica
        self.cerebro = base.cerebro
        self.al_nacer, self.al_inventar = base.al_nacer, base.al_inventar

    # ------------------------------------------------------------------ escala
    def celdas(self, metros: float, minimo: float = 1.0) -> float:
        """Pasa metros a celdas de este mundo. El mínimo de 1 celda evita que un radio real chico (lo que abriga una
        fogata, por ejemplo) quede en cero en un mundo de celdas grandes."""
        return max(minimo, metros / self.tam_celda_m)

    def _calcular_escala(self) -> None:
        """Las distancias del motor están en metros; acá se convierten una sola vez. Así el mismo comportamiento vale
        para celdas de 50 m y de 5 m, y los mundos viejos no cambian (a 50 m/celda dan los números de siempre)."""
        from . import tecnologia as T
        from . import vida as V
        self.r_habla = self.celdas(V.METROS_HABLA)
        self.r_vista = self.celdas(V.METROS_VISTA)
        self.r_encuentro = self.celdas(V.METROS_ENCUENTRO)
        self.r_fogata = self.celdas(T.METROS_CALOR_FOGATA)
        self.r_refugio = self.celdas(T.METROS_CALOR_REFUGIO)
        self.r_aldea = self.celdas(T.METROS_ALDEA)
        self.zona = max(1, int(round(self.celdas(T.METROS_ZONA))))
        # radios de trabajo: al lado de algo (juntar del fuego, fabricar), y lo que se busca caminando
        # "al lado": al alcance del brazo. El mínimo de 1,5 celdas cubre la celda vecina incluso en diagonal
        # (√2 ≈ 1,41); con 1,0 justo, estar en la celda de al lado ya no contaba.
        self.r_mano = self.celdas(8.0, minimo=1.5)
        # Ver humo a lo lejos NO es lo mismo que tener el fuego encima. Separarlos es clave: con un solo radio
        # de 1,1 km, un incendio lejano los hacía huir sin parar y se morían de sed sin llegar nunca al agua.
        self.r_ver_fuego = self.celdas(1100.0)      # lo ve y le da miedo (va al prompt)
        self.r_huir_fuego = self.celdas(220.0)      # está lo bastante cerca como para dejar todo y correr
        self.r_lejos_fuego = self.celdas(320.0)     # a esta distancia del frente ya se considera a salvo
        self.r_agua_cerca = self.celdas(3000.0)
        self.r_agua_lejos = self.celdas(7000.0)
        # el A* y la BFS cuestan ~(escala)² por viaje físico: el presupuesto de nodos acompaña, con tope
        k = (50.0 / self.tam_celda_m) ** 2
        self.nodos_bfs = int(min(300_000, 30_000 * k))
        self.nodos_camino = int(min(120_000, 12_000 * k))

    # ------------------------------------------------------------------ eventos
    def _evento(self, tipo: str, texto: str, h: Optional[HabitanteSim] = None, x: Optional[float] = None,
                y: Optional[float] = None, causa: Optional[str] = None, resultado: Optional[str] = None,
                importancia: int = 1, origen: str = "autonomo", datos: Optional[dict] = None) -> None:
        if h is not None and x is None:
            x, y = h.x, h.y
        self._eventos.append({"t_min": int(self.t), "tipo": tipo, "texto": texto,
                              "habitante_id": h.id if h else None, "x": x, "y": y, "causa": causa,
                              "resultado": resultado, "importancia": importancia, "origen": origen,
                              "datos": datos or {}})

    def vaciar_eventos(self) -> List[dict]:
        out, self._eventos = self._eventos, []
        return out

    def _tope_efectos(self) -> None:
        """Si nadie mira (sin observador) los efectos visuales no se acumulan sin límite."""
        if len(self._efectos) > 400:
            del self._efectos[:-200]

    def vaciar_efectos(self) -> List[dict]:
        out, self._efectos = self._efectos, []
        return out

    # ---------------------------------------------------------------- consultas
    def fuego_cerca(self, h: HabitanteSim, radio: float) -> Optional[Tuple[float, float, float]]:
        return self.fuego_cerca_de(h.x, h.y, radio)

    def fuego_cerca_de(self, px: float, py: float, radio: float) -> Optional[Tuple[float, float, float]]:
        """Lo mismo que `fuego_cerca` pero desde un punto cualquiera: hace falta para preguntar por el
        calor que recibe una CASA, no sólo una persona (ver `abrigo_efectivo`)."""
        if not self.fuego._hubo_fuego:
            return None
        r = int(radio) + 1
        x0, y0 = int(px), int(py)
        ys0, ys1 = max(0, y0 - r), min(self.terreno.alto, y0 + r + 1)
        xs0, xs1 = max(0, x0 - r), min(self.terreno.ancho, x0 + r + 1)
        ys, xs = np.nonzero(self.fuego.fuego[ys0:ys1, xs0:xs1])
        if len(xs) == 0:
            return None
        d = np.hypot(xs + xs0 + 0.5 - px, ys + ys0 + 0.5 - py)
        i = int(np.argmin(d))
        return (float(xs[i] + xs0 + 0.5), float(ys[i] + ys0 + 0.5), float(d[i])) if d[i] <= radio else None

    def agua_cercana(self, h: HabitanteSim, radio: int = 60) -> Optional[Tuple[int, int]]:
        """Celda transitable junto al agua más cercana *alcanzable* (BFS desde donde está, sin A* por candidato).
        Funciona aunque esté parado en una celda empinada o el agua más próxima en línea recta esté aislada."""
        from collections import deque
        t = self.terreno
        x0, y0 = int(h.x), int(h.y)
        if t.dentro(x0, y0) and t.agua_adyacente(x0, y0):
            return (x0, y0)
        vis = {(x0, y0)}
        q = deque([(x0, y0)])
        n = 0
        while q and n < self.nodos_bfs:
            x, y = q.popleft()
            n += 1
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                c = (x + dx, y + dy)
                if c in vis or abs(c[0] - x0) > radio or abs(c[1] - y0) > radio:
                    continue
                vis.add(c)
                if not t.dentro(*c) or not t.caminable(*c):
                    continue
                if dx and dy and (not t.caminable(x + dx, y) or not t.caminable(x, y + dy)):
                    continue                              # igual que el A*: no se cortan esquinas
                if t.agua_adyacente(*c):
                    return c
                q.append(c)
        if h.sed >= 55:
            import sys
            print("AGUA-CERCANA-NONE: h=%d sed=%.1f pos=(%d,%d) radio=%d" % (h.id, h.sed, x0, y0, radio), file=sys.stderr, flush=True)
        return None

    def buscar_agua_lejos(self, h: HabitanteSim) -> Optional[dict]:
        """Si no se conoce agua alcanzable, sale a buscarla lejos (por donde se pueda ir). El motivo NO es «explora»,
        así la sed no corta el viaje en cada paso."""
        for _ in range(10):
            d = self.rng.uniform(self.celdas(1000.0), self.celdas(2500.0))   # también en metros
            a = self.rng.random() * 2 * math.pi
            c = self.terreno.caminable_cerca(int(h.x + math.cos(a) * d), int(h.y + math.sin(a) * d), 3)
            if c and self.terreno.buscar_camino((int(h.x), int(h.y)), c, self.nodos_camino):
                return {"tipo": "ir", "destino": c, "motivo": "busca agua"}
        return None

    def refugio_de_fuego(self, h: HabitanteSim) -> Optional[Tuple[int, int]]:
        """Celda sin combustible (agua cercana, playa, ceniza) alejada del fuego, para esperar a que pase."""
        f = self.fuego_cerca(h, self.r_huir_fuego * 1.2)
        if not f:
            return None
        fx, fy, _ = f
        r = int(self.celdas(1600.0))      # hasta dónde buscar un lugar a salvo
        x0, y0 = int(h.x), int(h.y)
        ys0, ys1 = max(0, y0 - r), min(self.terreno.alto, y0 + r + 1)
        xs0, xs1 = max(0, x0 - r), min(self.terreno.ancho, x0 + r + 1)
        sin_comb = (self.fuego.comb[ys0:ys1, xs0:xs1] < 0.1) & (self.fuego.fuego[ys0:ys1, xs0:xs1] == 0) \
            & np.isfinite(self.terreno.costo[ys0:ys1, xs0:xs1])
        ys, xs = np.nonzero(sin_comb)
        if len(xs) == 0:
            return None
        gx, gy = xs + xs0 + 0.5, ys + ys0 + 0.5
        dfuego = np.hypot(gx - fx, gy - fy)
        dme = np.hypot(gx - h.x, gy - h.y)
        puntaje = np.where(dfuego >= self.r_lejos_fuego, dme, 1e9)   # el más cercano que quede lejos del fuego
        # solo refugios a los que se puede llegar, y cuyo camino no cruce el fuego
        probados = 0
        for i in np.argsort(puntaje):
            if puntaje[i] >= 1e9 or probados >= 6:
                break
            dest = (int(xs[i] + xs0), int(ys[i] + ys0))
            cam = self.terreno.buscar_camino((x0, y0), dest, self.nodos_camino)
            probados += 1
            if cam and not any(self.fuego.fuego[cy, cx] for cx, cy in cam):
                return dest
        # sin salida limpia: cruzar el frente de fuego hacia lo ya quemado (la ceniza ya no arde)
        mejor, mejor_p = None, 1e9
        quem = self.fuego.quemado[ys0:ys1, xs0:xs1]
        for i in np.argsort(dme)[:400]:
            if quem[ys[i], xs[i]] < 0.5:
                continue
            dest = (int(xs[i] + xs0), int(ys[i] + ys0))
            cam = self.terreno.buscar_camino((x0, y0), dest, self.nodos_camino)
            if not cam:
                continue
            en_fuego = sum(1 for cx, cy in cam if self.fuego.fuego[cy, cx])
            if en_fuego <= 2 and len(cam) + 6 * en_fuego < mejor_p:
                mejor, mejor_p = dest, len(cam) + 6 * en_fuego
            probados += 1
            if probados >= 14:
                break
        return mejor

    # -------------------------------------------------------------- intervención
    def encender(self, x: int, y: int, origen: str = "usuario") -> bool:
        ok = self.fuego.encender(x, y)
        if ok:
            quien = "El observador" if origen == "usuario" else "Un rayo" if origen == "rayo" else "Algo"
            self._evento("incendio", "%s prendió un fuego en la celda (%d, %d)." % (quien, x, y), x=x + 0.5, y=y + 0.5,
                         importancia=3, origen=origen if origen == "usuario" else "sistema",
                         causa="intervención del observador" if origen == "usuario" else "rayo")
        return ok

    def rayo(self, x: int, y: int) -> None:
        if not self.terreno.dentro(x, y):
            return
        self._efectos.append({"tipo": "rayo", "x": x + 0.5, "y": y + 0.5})
        for h in self.habitantes.values():
            if h.vivo and math.hypot(h.x - x - 0.5, h.y - y - 0.5) < 0.9:
                self._dano(h, 70.0, "un rayo", "herida", "Un rayo alcanzó a %s." % h.nombre)
        lluvia = self.clima.lluvia_en(x + 0.5, y + 0.5)
        if self.terreno.agua[y, x] == 0 and self.rng.random() < 0.35 * self.fuego.comb[y, x] * reloj.sequedad(self.t) * (1 - 0.9 * lluvia) * (1 - 0.95 * float(self.nieve[y, x])):
            self.encender(x, y, origen="rayo")

    def derrumbe(self, x: int, y: int) -> None:
        camino = camino_de_caida(self.terreno, x, y)
        if len(camino) < 2:
            return
        golpeados = []
        for h in self.habitantes.values():
            if h.vivo and any(math.hypot(h.x - cx - 0.5, h.y - cy - 0.5) < 1.1 for cx, cy in camino):
                golpeados.append(h)
        self._efectos.append({"tipo": "derrumbe", "camino": [[cx + 0.5, cy + 0.5] for cx, cy in camino]})
        cerca = any(h.vivo and math.hypot(h.x - x, h.y - y) < 40 for h in self.habitantes.values())
        if golpeados or cerca:       # un derrumbe que nadie vio ni sufrió no es un suceso: queda solo el efecto en el mapa
            self._evento("derrumbe", "Se desprendieron rocas en la celda (%d, %d) y rodaron %d celdas cuesta abajo." % (x, y, len(camino) - 1),
                         x=x + 0.5, y=y + 0.5, causa="gravedad y lluvia sobre una pendiente",
                         importancia=3 if golpeados else 2, datos={"camino": camino})
        for h in golpeados:
            self._dano(h, self.rng.uniform(25, 60), "un derrumbe", "herida", "%s fue golpeado por rocas de un derrumbe." % h.nombre, mio="Unas rocas de un derrumbe te golpearon.")

    def _dano(self, h: HabitanteSim, cantidad: float, causa: str, tipo: str, texto: str, mio: Optional[str] = None) -> None:
        h.salud -= cantidad
        self._evento(tipo, texto, h, causa=causa, importancia=3, datos={"dano": round(cantidad, 1)})
        self._recuerdo(h, mio or (texto.replace(h.nombre, "Te", 1) if texto.startswith(h.nombre) else texto), 0.7)
        h.camino, h.hasta = [], 0.0
        if causa in ("fuego", "quemaduras") or "incendio" in causa:
            self.sentir(h, "miedo", 0.5)
        if h.salud <= 0:
            self._morir(h, causa)

    def _morir(self, h: HabitanteSim, causa: str) -> None:
        if not h.vivo:
            return
        h.vivo, h.causa_muerte, h.t_muerte = False, causa, int(self.t)
        # Fase 8: liberar la pareja
        if getattr(h, "pareja_id", None) is not None:
            pareja = self.habitantes.get(h.pareja_id) if hasattr(self, "habitantes") else None
            if pareja is not None and pareja.vivo:
                pareja.pareja_id = None
                self._evento("_relacion", "", pareja, datos={"hab": pareja.id, "otro": h.id,
                                                              "d_afecto": -0.3, "d_confianza": -0.3,
                                                              "motivo": "murió la pareja"})
        h.accion, h.detalle, h.camino = "muerto", "", []
        self._evento("muerte", "%s murió (%s)." % (h.nombre, causa), h, causa=causa, importancia=5)
        for o in self.habitantes.values():
            if o.vivo and o.id != h.id and math.hypot(o.x - h.x, o.y - h.y) <= 30:
                self.sentir(o, "tristeza", 0.6)
                self.sentir(o, "miedo", 0.2)
                self.experiencia(o, "muerte_cercana")
                self._recuerdo(o, "%s murió (%s) cerca tuyo." % (h.nombre, causa), 0.9)
                self._evento("_relacion", "", o, datos={"hab": o.id, "otro": h.id, "d_afecto": 0.0, "d_confianza": 0.0,
                                                        "motivo": "murió"})

    # ----------------------------------------------------------------- avance
    def avanzar(self, dt_min: float) -> None:
        while dt_min > 1e-9:
            paso = min(PASO_MAX, dt_min)
            dt_min -= paso
            self._paso(paso)

    def _tick_rapido_fisica(self, paso: float) -> None:
        """Ticks rápidos: movimiento, navegación, cinemática y necesidades vitales directas."""
        for h in list(self.habitantes.values()):
            if h.vivo:
                self._vida(h, paso)
            if h.vivo:
                self._actualizar(h, paso)
                self._decaer_emociones(h, paso)
                if h.montura is not None:
                    self._sincronizar_montura(h)

    def _tick_amortizado_sistemas(self, paso: float) -> None:
        """Ticks amortizados: clima, nieve, fuego, fauna, senderos, colonias y fenómenos globales."""
        if self.modulo("fauna"):
            if not self._fauna_lista:
                self._fauna_lista = True
                self.fauna.poblar_inicial(self.centro_seguro)
            vivos = [h for h in self.habitantes.values() if h.vivo]
            if self.fauna.paso(paso, self.t, vivos):
                self._ataques_animales()
            if self.fauna.mutaciones:
                self._avisar_mutaciones()
        self.repartir_atencion()
        if self.cielo.get("dia_noche", True):     # bajo tierra no hay tormentas ni nieve: no hay cielo
            self.clima.paso(self, paso)
            self._paso_nieve(paso)
        self._paso_conservacion(paso)
        self._paso_tecnologia(paso)
        self._paso_senderos(paso)
        self._paso_fenomenos(paso)
        self._paso_colonias(paso)
        self._tope_efectos()
        self._acum_fuego += paso
        if self._acum_fuego >= 1.0 or (self._acum_fuego > 0 and not self.fuego._hubo_fuego):
            dt, self._acum_fuego = self._acum_fuego, 0.0
            lluvia = self.clima.mascara_lluvia(self.fuego.fuego.shape) if self.fuego._hubo_fuego else None
            r = self.fuego.paso(dt, reloj.sequedad(self.t) * (0.45 if reloj.es_noche(self.t) else 1.0), lluvia)
            if r["termino"]:
                ha = r["celdas_episodio"] * (self.tam_celda_m ** 2) / 10000.0
                self._evento("incendio_extinguido", "El incendio se extinguió. Se quemaron unas %.1f hectáreas." % ha,
                             importancia=3, origen="sistema", datos={"celdas": r["celdas_episodio"], "hectareas": round(ha, 1)})

    def _paso(self, paso: float) -> None:
        self.t += paso
        # 1. Ticks rápidos: física, desplazamiento, vitales
        self._tick_rapido_fisica(paso)
        # 2. Ticks amortizados: macro-sistemas globales
        self._tick_amortizado_sistemas(paso)

    def _actualizar(self, h: HabitanteSim, paso: float) -> None:
        dormido = h.accion == "durmiendo" and self.t < h.hasta
        if dormido:
            # DÓNDE se duerme importa: antes se descansaba igual en el barro que en la choza, así que tener
            # casa no servía para nada. Bajo techo se recupera más (hasta el doble con el mejor refugio), y
            # el abrigo es el EFECTIVO, o sea que la fogata de la aldea también se nota. El factor se mide
            # UNA vez, al acostarse (`h.cama`): durmiendo nadie se mueve, y esto corre a 20 Hz por persona.
            h.energia = min(100.0, h.energia + 0.15 * paso * (1.0 + float(getattr(h, "cama", 0.0))))
            h.sed = min(100.0, h.sed + 0.07 * paso)
        else:
            h.energia = max(0.0, h.energia - 0.05 * paso)
            h.sed = min(100.0, h.sed + 0.11 * paso)
        # La sed despierta siempre (mata en horas). El hambre sólo si le queda energía para hacer algo:
        # si no, se despierta, no puede ni levantarse, se vuelve a dormir y muere de agotamiento.
        if dormido and (h.sed >= SED_DESPIERTA or (h.hambre >= HAMBRE_DESPIERTA and h.energia > 35.0)):
            h.hasta = 0.0
        elif h.accion in ("juntando", "fabricando", "construyendo", "curando", "cocinando") and h.sed >= 65 and h.hasta > self.t:
            h.hasta = 0.0   # una tarea larga no puede dejar morir de sed
        h.sin_regenerar = False
        self._paso_hambre(h, paso, dormido)
        self._paso_atributos(h, paso)
        self._paso_psique(h, paso)
        if self.modulo("frio"):
            self._aplicar_frio(h, paso, dormido)
        if h.sed >= 90:
            h.salud -= 0.3 * paso
        if h.energia <= 5:
            h.salud -= 0.1 * paso
        if h.sed < 60 and h.energia > 30 and h.salud < 100 and not h.sin_regenerar:
            h.salud = min(100.0, h.salud + 0.05 * paso)
        cx, cy = int(h.x), int(h.y)
        # fuego: quema a quien esté sobre una celda en llamas
        inten = int(self.fuego.fuego[cy, cx]) if self.fuego._hubo_fuego else 0
        h.en_fuego = inten > 0
        if inten > 0:
            h.salud -= paso * (inten / 255.0) * 15.0
            if not h.herido_fuego:
                h.herido_fuego = True
                self._evento("herida", "%s se quemó con un incendio." % h.nombre, h, causa="fuego", importancia=3)
                self._recuerdo(h, "Te quemaste con un incendio.", 0.8)
                h.marcar_lugar("peligro", h.x, h.y, "fuego", self.t, radio=self.celdas(500.0))
                self.experiencia(h, "quemarse")
            h.hasta = 0.0
            if h.detalle != "huye del fuego":
                h.camino = []
            if h.accion in ("durmiendo", "bebiendo", "esperando"):
                h.accion = "libre"
        elif h.herido_fuego and not self.fuego._hubo_fuego:
            h.herido_fuego = False
        # reflejo: si el fuego está encima, para y despierta (el cerebro decide hacia dónde ir)
        elif self.fuego._hubo_fuego and (h.accion in ("durmiendo", "caminando") or h.accion == "libre"):
            f = self.fuego_cerca(h, self.celdas(800.0) if h.accion == "durmiendo" else self.celdas(500.0))
            if f and (h.accion == "durmiendo" or h.detalle != "huye del fuego"):
                h.camino, h.hasta, h.accion = [], 0.0, "libre"
        if h.salud <= 0:
            self._morir(h, "fuego" if inten > 0 else "sed" if h.sed >= 90 else "hambre" if h.hambre >= 95
                        else "agotamiento" if h.energia <= 5 else "frío" if h.frio > 0.4 else "heridas")
            return
        # caídas: caminar por pendientes muy empinadas puede salir mal (gravedad)
        if h.accion == "caminando":
            p = float(self.terreno.pendiente[cy, cx])
            if p > 0.8 and self.rng.random() < 0.0003 * paso * min(2.0, p):
                self._dano(h, min(25.0, 2.0 + p * 10.0), "una caída por la pendiente", "herida",
                           "%s resbaló y cayó por una pendiente empinada." % h.nombre, mio="Resbalaste y caíste por una pendiente empinada.")
                if not h.vivo:
                    return
        if self.t < h.hasta:
            return
        if h.accion in ("durmiendo", "bebiendo", "esperando"):
            h.accion, h.detalle = "libre", ""
        if h.camino and h.detalle == "huye del fuego" and self.fuego._hubo_fuego:
            fz = self.fuego.fuego
            for px, py in h.camino[:3]:   # el fuego tapó la ruta: replanear
                if fz[py, px]:
                    h.camino = []
                    break
        if (h.camino and h.detalle != "huye del fuego" and self.fuego._hubo_fuego
                and h.sed < SED_DESPIERTA and self.fuego_cerca(h, self.r_huir_fuego)):
            h.camino = []   # el fuego lo alcanza: deja lo que hacía. Con sed mortal NO: iba al agua y moría a mitad
        if h.camino and h.detalle == "explora" and (h.sed >= 55 or h.energia <= 25):
            h.camino = []   # una necesidad urgente interrumpe el paseo
        if h.camino:
            self._mover(h, paso)
            return
        if h.al_llegar == "beber":
            h.al_llegar = None
            self._aplicar(h, {"tipo": "beber"})
            return
        propuesta = self._tick_cerebro(h)
        ok, texto = self._aplicar(h, propuesta)
        reg = getattr(self.cerebro, "registrar_resultado", None)
        if reg is not None and texto:
            reg(self, h, ok, texto)

    def _tick_cerebro(self, h: HabitanteSim) -> dict:
        """Consulta al cerebro de forma desacoplada o consume propuesta encolada/cacheada."""
        propuesta = self._propuestas_cerebro.pop(h.id, None)
        if propuesta is None:
            propuesta = self.cerebro.decidir(self, h)
        return propuesta

    def _mover(self, h: HabitanteSim, paso: float) -> None:
        h.accion = "caminando"
        dist = paso * self.terreno.velocidad_en(h.x, h.y) * (1.6 if h.detalle.startswith("huye") else 1.0) * (1.8 if h.montura is not None else 1.0) * (1.0 - 0.4 * self.nieve_en(h.x, h.y))  # el miedo da alas; la nieve frena
        paso_z = max(1, int(self.celdas(600.0)))        # "lugar nuevo" en metros, no en celdas
        z = (int(h.x) // paso_z, int(h.y) // paso_z)
        if z not in h.zonas:
            h.zonas.add(z)
            if len(h.zonas) > 1:
                h.novedad_t = self.t
                self.experiencia(h, "lugar_nuevo")
        while dist > 1e-9 and h.camino:
            tx, ty = h.camino[0]
            px, py = tx + 0.5 + h.sesgo[0], ty + 0.5 + h.sesgo[1]   # su punto propio, nunca el centro exacto
            d = math.hypot(px - h.x, py - h.y)
            if d <= dist:
                h.x, h.y = px, py
                dist -= d
                self.pisar(tx, ty)          # el paso deja huella (motor/senderos.py)
                h.camino.pop(0)
            else:
                h.x += (px - h.x) / d * dist
                h.y += (py - h.y) / d * dist
                dist = 0.0
        if not h.camino:
            h.accion = "libre"

    def _aplicar(self, h: HabitanteSim, it: dict) -> Tuple[bool, str]:
        """Ejecuta lo que el cerebro propuso. Devuelve (ok, texto) y deja el texto en h.ultimo_resultado."""
        tipo = it.get("tipo")
        ok, texto = True, ""
        if tipo == "esperar" and it.get("motivo") == "pensando":   # no ensucia "lo último que intentaste"
            h.accion, h.detalle, h.hasta = "esperando", "pensando", self.t + float(it.get("min", 1))
            return True, ""
        if tipo == "ir":
            dest = tuple(it["destino"])
            # con el presupuesto de nodos de ESTE mundo: a 5 m por celda un viaje de 1,8 km son 360 celdas
            # y el default de 40.000 no alcanza. Sin esto, explorar fallaba siempre y no se movían del lugar.
            camino = self.terreno.buscar_camino((int(h.x), int(h.y)), dest, self.nodos_camino)
            if camino is not None and not camino:                        # ya está en el lugar (antes: "No encontraste camino")
                if it.get("luego") == "beber" or (h.sed >= 55 and self.terreno.agua_adyacente(int(h.x), int(h.y))):
                    return self._aplicar(h, {"tipo": "beber"})
                h.accion, h.detalle, h.hasta = "esperando", "ya está ahí", self.t + 10
                return True, "Ya estás ahí."
            if camino:
                h.camino, h.accion, h.detalle, h.al_llegar = camino, "caminando", it.get("motivo", ""), it.get("luego")
                texto = {"explora": "Saliste a explorar.", "va al agua": "Fuiste hacia el agua.", "tiene sed": "Fuiste a buscar agua."}.get(it.get("motivo"), "Fuiste hacia %s." % (it.get("motivo") or "otro lado"))
            else:
                h.accion, h.detalle, h.hasta = "esperando", "no encuentra camino", self.t + 10
                ok, texto = False, "No encontraste camino."
                if h.sed >= 55:
                    import sys
                    print("SED-SIN-CAMINO: h=%d sed=%.1f pos=(%d,%d) destino=%s" % (h.id, h.sed, int(h.x), int(h.y), dest), file=sys.stderr, flush=True)
        elif tipo == "buscar":
            ok, texto = self._accion_buscar(h, it)
        elif tipo == "juntar":
            ok, texto = self._accion_juntar(h, it)
        elif tipo == "fabricar":
            ok, texto = self._accion_fabricar(h, it)
        elif tipo == "encender":
            ok, texto = self._accion_encender(h, it)
        elif tipo == "tomar_fuego":
            ok, texto = self._accion_tomar_fuego(h, it)
        elif tipo == "usar":
            ok, texto = self._accion_usar(h, it)
        elif tipo == "cocinar":
            ok, texto = self._accion_cocinar(h, it)
        elif tipo == "curar":
            ok, texto = self._accion_curar(h, it)
        elif tipo == "comer":
            ok, texto = self._accion_comer(h, it)
        elif tipo == "dormir":
            cama = self.refugio_cerca(h)
            h.cama = self.abrigo_efectivo(cama) if cama else 0.0
            h.accion, h.detalle, h.hasta = "durmiendo", "", self.t + float(it.get("min", 240))
            if cama is None:
                texto = "Te pusiste a dormir a la intemperie."
            else:
                texto = ("Te pusiste a dormir en %s." % cama.get("nombre", "tu refugio")) if cama.get("dueno") == h.id \
                    else "Te pusiste a dormir bajo %s." % cama.get("nombre", "un techo ajeno")
        elif tipo == "beber":
            if self.terreno.agua_adyacente(int(h.x), int(h.y)):
                h.accion, h.detalle, h.hasta = "bebiendo", "", self.t + 5
                h.sed = max(0.0, h.sed - 60.0)
                texto = "Bebiste agua."
                h.marcar_lugar("agua", h.x, h.y, "agua para beber", self.t)
                pz = max(1, int(self.celdas(600.0)))
                zona = (int(h.x) // pz, int(h.y) // pz)
                if zona not in h.lugares_agua:
                    h.lugares_agua.add(zona)
                    self._recuerdo(h, "En (%d, %d) hay agua para beber." % (int(h.x), int(h.y)), 0.6, "semantica")
            else:
                h.accion, h.detalle, h.hasta = "esperando", "no hay agua aquí", self.t + 5
                ok, texto = False, "Aquí no hay agua."
        elif tipo == "hablar":
            ok, texto = self._accion_hablar(h, it)
        elif tipo == "ir_hacia":
            ok, texto = self._accion_ir_hacia(h, it)
        elif tipo == "proponer_hijo":
            ok, texto = self._accion_proponer_hijo(h, it)
        elif tipo == "responder_propuesta":
            ok, texto = self._accion_responder(h, it)
        elif tipo == "ensenar":
            ok, texto = self._accion_ensenar(h, it)
        elif tipo == "inventar":
            ok, texto = self._accion_inventar(h, it)
        elif tipo == "cazar":
            ok, texto = self._accion_cazar(h, it)
        elif tipo == "montar":
            ok, texto = self._accion_montar(h, it)
        elif tipo == "desmontar":
            ok, texto = self._accion_desmontar(h, it)
        elif tipo == "atravesar":
            ok, texto = self._accion_atravesar(h, it)
        else:
            h.accion, h.detalle, h.hasta = "esperando", it.get("motivo", ""), self.t + float(it.get("min", 15))
            texto = "Esperaste un rato."
        if not ok and h.hasta <= self.t:
            h.accion, h.detalle, h.hasta = "esperando", "", self.t + 3.0   # equivocarse cuesta un poco de tiempo
        h.ultimo_resultado = texto
        return ok, texto

    # ------------------------------------------------------------------ estado

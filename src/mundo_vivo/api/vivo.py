"""
Ejecutor en vivo: mantiene una simulación corriendo mientras haya alguien mirando.

- El mundo avanza a la velocidad pedida (minutos simulados por segundo real). Si la computadora no llega,
  se recorta el avance (presupuesto de tiempo por vuelta) en lugar de congelar la pantalla.
- Cuando nadie está conectado el mundo se guarda y se detiene (no gasta CPU).
- Guarda cada ~10 segundos reales y al cerrar. Los eventos se vuelcan a la base al guardar.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from .. import diagnostico
from ..agentes import ajustes as _aj
from ..agentes.genoma import genoma_fundador
from ..agentes.mente import CerebroHibrido
from ..motor.simulacion import Cerebro, Simulacion, HabitanteSim
from ..persistencia import db, mundo_io, sim_io
from ..persistencia.sim_io import NOMBRES_F, NOMBRES_M, ANIO_MIN
import math
import random
import uuid

VELOCIDADES = (0, 1, 5, 20, 100, 500, 2000)   # minutos simulados por segundo real
# El 2000 sólo tiene sentido con un cerebro sin modelo, y aun así es un techo, no una promesa.
# Medido (0.10.0, cerebro cognitivo): mapa de 256² con 25 habitantes, ~960 minutos de mundo por
# segundo de CPU; mapa de 2048² con 4 habitantes, ~99. En el mapa grande el costo es del MOTOR
# (A* largo, fuego, nieve, clima sobre 4 millones de celdas), no del cerebro, así que pedir 500×
# no rompe nada: el bucle recorta el avance y el mundo corre a lo que puede.
# Con el cerebro híbrido la latencia del modelo frena mucho antes (ver `tope_pensando`).
HZ_BUCLE = 20
HZ_ESTADO = 10
PRESUPUESTO_S = 0.035                    # tiempo máximo de cálculo por vuelta
GUARDAR_CADA_S = 10.0
PASO_AVANCE = 2.0                        # minutos simulados por tanda de cálculo

# Qué cerebro maneja a los habitantes. Se elige con la variable de entorno MUNDO_VIVO_CEREBRO:
#   hibrido    (default) modelo de lenguaje + reflejos + respaldo, el de siempre
#   cognitivo  Cognitive Engine, el proyecto aparte: GOAP y Utility AI, sin modelo y determinista
VAR_CEREBRO = "MUNDO_VIVO_CEREBRO"


def crear_cerebro(con) -> Cerebro:
    """Instancia el cerebro pedido. Por defecto usa Cognitive Engine (GOAP + Utility AI sin LLM)."""
    elegido = (os.environ.get(VAR_CEREBRO) or "cognitivo").strip().lower()
    if elegido in ("cognitivo", "cognitive", "cognitive_engine", ""):
        from ..agentes.cerebro_cognitivo import CerebroCognitivo

        # La base va para que cada decisión quede anotada en `decisiones`: es de ahí que el visor
        # saca «Lo que pensó».
        return CerebroCognitivo(con)
    if elegido in ("hibrido", "híbrido", "llm"):
        return CerebroHibrido(con)
    raise ValueError(
        f"{VAR_CEREBRO}='{elegido}' no existe. Valores válidos: cognitivo, hibrido."
    )


class Ejecutor:
    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.con = db.abrir(ruta)
        sim_io.crear_habitantes_iniciales(self.con, 4)
        self.cerebro = crear_cerebro(self.con)
        self.mundo = sim_io.cargar_mundo(self.con, cerebro=self.cerebro)
        # `sim` es la dimensión que se está MIRANDO. El mundo entero corre siempre, se mire lo que se mire.
        self.sim: Simulacion = self.mundo.principal
        fila = self.con.execute("SELECT velocidad FROM estado_mundo WHERE id = 1").fetchone()
        self.velocidad = float(fila[0]) if fila and float(fila[0]) in VELOCIDADES else 1.0
        self.clientes: Set[asyncio.Queue] = set()
        self.tarea: Optional[asyncio.Task] = None
        self._ultimo_guardado = time.monotonic()
        self._ultimo_volcado = time.monotonic()
        self.velocidad_real = 0.0   # minutos simulados por segundo real efectivos
        self._vitales_prev: dict = {}   # último bloque de barras enviado, para mandar solo lo que cambió
        self._latido = diagnostico.Latido()
        diagnostico.log().info("mundo abierto: %s", json.dumps(
            {"mundo": ruta.stem, "cerebro": self.cerebro.nombre, "velocidad": self.velocidad,
             "dimensiones": len(self.mundo.sims), "semilla": self.sim.semilla,
             "terreno": [self.sim.terreno.ancho, self.sim.terreno.alto],
             "tam_celda_m": self.sim.tam_celda_m,
             "habitantes": len(self.sim.habitantes)}, default=str, ensure_ascii=False))

    # ----------------------------------------------------------------- clientes
    def hola(self) -> dict:
        s = self.sim
        return {"tipo": "hola", "ancho": s.terreno.ancho, "alto": s.terreno.alto, "tam_celda_m": s.tam_celda_m,
                "velocidades": list(VELOCIDADES), "velocidad": self.velocidad,
                "cerebro": getattr(s.cerebro, "nombre", "desconocido"), "estado": self._estado(),
                "ajustes": s.ajustes, "modulos_desc": _aj.MODULOS, "fauna_cat": s.fauna.catalogo_publico(),
                "dimension": s.dimension, "dimensiones": self.mundo.dimensiones()}

    def _estado(self) -> dict:
        from .presentador import estado_completo
        e = estado_completo(self.sim)
        e["dimension"] = self.sim.dimension
        e["dimensiones"] = self.mundo.dimensiones()
        e["cielo"] = self.sim.cielo
        return e

    def _estado_liviano(self, pesado: bool) -> dict:
        """El mensaje de cada 100 ms. `pesado` suma fuego, estructuras, colonias y barras finas,
        que se mandan una vez por segundo: dibujar no necesita recalcularlos diez veces."""
        from .presentador import estado_liviano
        e = estado_liviano(self.sim, bloques=pesado)
        e["dimension"] = self.sim.dimension
        e["dimensiones"] = self.mundo.dimensiones()
        e["cielo"] = self.sim.cielo
        if pesado:
            e["vitales"] = self._vitales_sucios()
        return e

    def _vitales_sucios(self) -> list:
        """[[id, salud, sed, energia, hambre, temp, frio], ...] solo de los vivos que cambiaron
        desde el último bloque. Los muertos no llevan barras."""
        out = []
        prev = self._vitales_prev
        ahora: dict = {}
        for h in self.sim.habitantes.values():
            if not h.vivo:
                continue
            t = (round(h.salud, 1), round(h.sed, 1), round(h.energia, 1), round(h.hambre, 1),
                 round(self.sim.temp_en(h.x, h.y), 1), round(h.frio, 2))
            ahora[h.id] = t
            if prev.get(h.id) != t:
                out.append([h.id, *t])
        self._vitales_prev = ahora
        return out

    def suscribir(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self.clientes.add(q)
        if self.tarea is None or self.tarea.done():
            self._ultimo_guardado = time.monotonic()
            bucle = asyncio.get_running_loop()
            diagnostico.enganchar_asyncio(bucle)   # asyncio se come las excepciones de las tareas
            self.tarea = bucle.create_task(self._bucle())
        return q

    async def desuscribir(self, q: asyncio.Queue) -> None:
        self.clientes.discard(q)
        if not self.clientes and self.tarea:
            self.tarea.cancel()
            try:
                await self.tarea
            except (asyncio.CancelledError, Exception):
                pass
            self.tarea = None
            self.guardar()

    def _difundir(self, msg: dict) -> None:
        texto = json.dumps(msg, separators=(",", ":"))
        for q in list(self.clientes):
            if q.full():
                try:
                    q.get_nowait()   # cliente lento: se descarta lo viejo
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(texto)

    # ----------------------------------------------------------------- comandos
    def comando(self, c: dict) -> Optional[dict]:
        cmd = c.get("cmd")
        if cmd == "velocidad":
            v = float(c.get("v", 1))
            if v not in VELOCIDADES:
                return {"tipo": "error", "texto": "Velocidad no permitida."}
            self.velocidad = v
            with self.con:
                self.con.execute("UPDATE estado_mundo SET velocidad = ? WHERE id = 1", (v,))
            return {"tipo": "velocidad", "velocidad": v}
        if cmd == "fuego":
            x, y = int(c.get("x", -1)), int(c.get("y", -1))
            ok = self.sim.encender(x, y, origen="usuario")
            self._volcar()
            return {"tipo": "fuego", "ok": ok}
        if cmd == "spawn":
            x, y = int(c.get("x", -1)), int(c.get("y", -1))
            sexo = str(c.get("sexo", "")).upper()
            if sexo not in ("F", "M"):
                sexo = "F" if random.random() < 0.5 else "M"
            nombre = str(c.get("nombre", "")).strip()
            if not nombre:
                usados = {h.nombre for h in self.sim.habitantes.values()}
                pool = [n for n in (NOMBRES_F if sexo == "F" else NOMBRES_M) if n not in usados]
                nombre = random.choice(pool) if pool else f"Inmigrante{len(self.sim.habitantes) + 1}"
            
            # Buscar celda transitable si cae en agua o roca no transitable
            if not self.sim.terreno.caminable(x, y):
                cercana = self.sim.terreno.caminable_cerca(x, y, 10)
                if cercana:
                    x, y = cercana
                else:
                    return {"tipo": "error", "texto": "Lugar no transitable."}

            tam = float(self.sim.tam_celda_m)
            g = genoma_fundador(int(self.sim.semilla * 7919 + len(self.sim.habitantes) * 13 + int(self.sim.t)))
            color = len(self.sim.habitantes) % 8
            
            # Persistir en la base de datos
            with self.con:
                cur = self.con.execute(
                    """INSERT INTO habitantes (uuid, nombre, nacimiento_min, x, y, estado, identidad, genoma, madre_id, padre_id, dimension, creado_en)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?, datetime('now'))""",
                    (str(uuid.uuid4()), nombre, int(self.sim.t - 20 * ANIO_MIN), x * tam, y * tam,
                     json.dumps({"salud": 100.0, "sed": 20.0, "energia": 100.0}),
                     json.dumps({"generacion": 0, "sexo": sexo, "origen": "inmigrante"}), json.dumps(g.a_dict()),
                     None, None, self.sim.dimension))
                hid = cur.lastrowid
            
            nuevo = HabitanteSim(hid, nombre, float(x), float(y), sed=20.0, color=color)
            nuevo.sexo = sexo
            nuevo.genoma = g
            nuevo.madre_id = None
            nuevo.padre_id = None
            nuevo.nacimiento_min = int(self.sim.t - 20 * ANIO_MIN) # Adulto de 20 años
            self.sim.habitantes[nuevo.id] = nuevo

            self.sim._evento("inmigrante", f"Un nuevo habitante nómada llegó al mundo: {nombre}.", nuevo,
                             importancia=4, datos={"origen": "usuario", "id": nuevo.id})
            self._volcar()
            self._difundir({"tipo": "spawn", "id": nuevo.id, "nombre": nuevo.nombre, "x": x, "y": y})
            return {"tipo": "spawn", "ok": True, "id": nuevo.id, "nombre": nuevo.nombre}

        if cmd == "curar":
            hid = int(c.get("id", -1))
            h = self.sim.habitantes.get(hid)
            if not h or not h.vivo:
                return {"tipo": "error", "texto": "Habitante no encontrado o fallecido."}
            h.salud = 100.0
            h.sed = 0.0
            h.energia = 100.0
            h.en_fuego = False
            self.sim.sentir(h, "alegria", 1.0)
            self.sim._evento("milagro", f"El observador bendijo y sanó a {h.nombre}.", h, importancia=3)
            self._volcar()
            return {"tipo": "curar", "ok": True, "id": hid}

        if cmd == "infectar":
            # Inocular una epidemia / intoxicación en un área o persona
            x, y = int(c.get("x", -1)), int(c.get("y", -1))
            radio = float(c.get("radio", 8.0))
            afectados = []
            for h in self.sim.habitantes.values():
                if h.vivo and math.hypot(h.x - x, h.y - y) <= radio:
                    h.salud = max(15.0, h.salud - 45.0)
                    self.sim.sentir(h, "miedo", 0.8)
                    afectados.append(h.nombre)
            if afectados:
                nombres_txt = ", ".join(afectados[:3]) + (f" y {len(afectados)-3} más" if len(afectados) > 3 else "")
                self.sim._evento("epidemia", f"Una extraña plaga afectó a {nombres_txt}.",
                                 importancia=4, datos={"x": x, "y": y, "afectados": len(afectados)})
                self._volcar()
                return {"tipo": "infectar", "ok": True, "afectados": len(afectados)}
            return {"tipo": "error", "texto": "No había habitantes en la zona afectada."}

        if cmd == "romper_lazo":
            # Desvincular parentesco para destrabar cuellos de botella genéticos
            hid = int(c.get("id", -1))
            h = self.sim.habitantes.get(hid)
            if not h:
                return {"tipo": "error", "texto": "Habitante no encontrado."}
            h.madre_id = None
            h.padre_id = None
            with self.con:
                self.con.execute("UPDATE habitantes SET madre_id = NULL, padre_id = NULL WHERE id = ?", (hid,))
            self.sim._evento("liberacion_linaje", f"{h.nombre} fue liberado/a de sus lazos de consanguinidad.", h, importancia=3)
            self._volcar()
            return {"tipo": "romper_lazo", "ok": True, "id": hid}
        if cmd == "dimension":
            s = self.mundo.sims.get(int(c.get("d", 0)))
            if s is None:
                return {"tipo": "error", "texto": "Ese lugar todavía no existe en este mundo."}
            self.sim = s
            return dict(self.hola(), tipo="hola")
        if cmd == "ajustes":
            try:
                self.sim.ajustes = _aj.guardar(self.con, c.get("cambios") or {})
            except (ValueError, TypeError) as e:
                return {"tipo": "error", "texto": str(e)}
            return {"tipo": "ajustes", "ajustes": self.sim.ajustes}
        return {"tipo": "error", "texto": "Comando desconocido."}

    # Cuántos minutos del mundo pueden pasarle a una persona entre que pide pensar y le llega la respuesta.
    # Los reflejos (sed, hambre, fuego, dormir) siguen corriendo cada minuto simulado: esto es solo cada cuánto
    # toma una decisión deliberada. 90 min es como una persona que replanifica una vez y media por hora.
    MIN_POR_PENSADA = 90.0

    def tope_pensando(self) -> float:
        """Velocidad máxima mientras alguien piensa.
        En los ajustes: 0 = automático (según lo que tarda el modelo); >0 = techo fijo, nunca por encima del
        automático; <0 = SIN TOPE (el mundo corre a fondo y cada uno decide cada varios días: no hacen nada)."""
        fijo = float(self.sim.ajustes.get("velocidad_max_pensando", 0.0))
        if fijo < 0:
            return 1e9                                    # el usuario pidió explícitamente no frenar
        if self.cerebro.cliente is None:
            # Un cerebro sin modelo decide en microsegundos: no hay latencia que limite el mundo.
            return 1e9 if fijo == 0 else fijo
        lat = self.cerebro.cliente.estado().get("latencia_s")
        auto = max(2.0, min(500.0, self.MIN_POR_PENSADA / float(lat))) if lat else 10.0
        return min(fijo, auto) if fijo > 0 else auto      # el valor fijo es un techo, nunca una excusa para atropellarlos

    # -------------------------------------------------------------------- bucle
    async def _bucle(self) -> None:
        dt_vuelta = 1.0 / HZ_BUCLE
        cada_estado = 1.0 / HZ_ESTADO
        cada_pesado = 1.0        # fuego, estructuras, colonias y barras finas: una vez por segundo
        ult_estado = 0.0
        ult_pesado = 0.0
        pendiente = 0.0
        cerebro_estado = {}
        t_prev = time.monotonic()
        try:
            while True:
                await asyncio.sleep(dt_vuelta)
                ahora = time.monotonic()
                real = min(0.5, ahora - t_prev)
                t_prev = ahora
                v = self.velocidad
                pendiente += v * real
                inicio, avanzado = time.perf_counter(), 0.0
                # A velocidades altas (>20x), aumentar el paso de avance por tanda para amortizar
                # el overhead del bucle y llamadas entre subsistemas.
                paso_tanda = max(PASO_AVANCE, min(10.0, v / HZ_BUCLE)) if v > 20 else PASO_AVANCE
                presupuesto = 0.045 if v >= 500 else PRESUPUESTO_S
                while pendiente > 1e-6:
                    paso = min(paso_tanda, pendiente)
                    self.mundo.avanzar(paso)
                    pendiente -= paso
                    avanzado += paso
                    if time.perf_counter() - inicio > presupuesto:
                        pendiente = 0.0   # no llega: se recorta en vez de acumular atraso
                        break
                if real > 0:
                    self.velocidad_real = 0.8 * self.velocidad_real + 0.2 * (avanzado / real)
                for e in self.mundo.vaciar_efectos():
                    if e.get("dimension", 0) == self.sim.dimension:   # no se ven los rayos del otro mapa
                        self._difundir(e)
                if ahora - ult_estado >= cada_estado or self.velocidad == 0 and ahora - ult_estado >= 0.5:
                    ult_estado = ahora
                    pesado = ahora - ult_pesado >= cada_pesado
                    if pesado:
                        ult_pesado = ahora
                    est = self._estado_liviano(pesado)
                    est["tipo"] = "estado"
                    est["velocidad"] = self.velocidad
                    est["velocidad_real"] = round(self.velocidad_real, 1)
                    if pesado:
                        cerebro_estado = dict(self.cerebro.estado(self.sim))
                        cerebro_estado["tope"] = round(self.tope_pensando(), 1)
                        cerebro_estado["atencion"] = self.sim.resumen_atencion()
                    est["cerebro"] = cerebro_estado
                    self._difundir(est)
                if ahora - self._ultimo_guardado >= GUARDAR_CADA_S:
                    self.guardar()
                elif ahora - self._ultimo_volcado >= 2.0:     # los sucesos llegan al panel casi en vivo
                    self._volcar()
                    self._ultimo_volcado = ahora
                # Latido del registro. En el caso normal es una comparación de reloj y sigue de largo
                # (ver `diagnostico.Latido`): no cuesta nada a 20 Hz.
                self._latido.quizas(self.sim, con=self.con, extra={
                    "velocidad": self.velocidad,
                    "velocidad_real": round(self.velocidad_real, 1),
                    "clientes": len(self.clientes),
                    **diagnostico.metricas_cerebro(self.cerebro, self.sim)})
        except asyncio.CancelledError:
            raise
        except BaseException:
            # Sin esto el bucle muere en silencio: la tarea nadie la espera y el mundo se queda
            # quieto sin que aparezca nada en ninguna parte.
            diagnostico.log().critical("el bucle del mundo se murió", exc_info=True)
            raise

    def _volcar(self) -> None:
        """Pasa los eventos nuevos a la base y los avisa a los que miran."""
        pend = [dict(e, dimension=s.dimension) for s in self.mundo.sims.values() for e in s._eventos]
        n = sim_io.volcar_eventos_mundo(self.con, self.mundo)
        if n:
            self._difundir({"tipo": "eventos", "eventos": [
                {"t_min": e["t_min"], "tipo": e["tipo"], "texto": e["texto"], "importancia": e["importancia"],
                 "habitante_id": e["habitante_id"], "dimension": e.get("dimension", 0)} for e in pend]})

    def guardar(self) -> None:
        self._volcar()
        sim_io.guardar_mundo_vivo(self.con, self.mundo)
        if hasattr(self.cerebro, "guardar_cerebros"):
            self.cerebro.guardar_cerebros()
        self._ultimo_guardado = time.monotonic()

    def cerrar(self) -> None:
        try:
            self.guardar()
            if self.cerebro.cliente is not None:
                self.cerebro.cliente.apagar()
        finally:
            self.con.close()


    def descartar(self) -> None:
        """Cierra SIN guardar (para borrar el mundo)."""
        try:
            if self.tarea and not self.tarea.done():
                self.tarea.cancel()
            if self.cerebro.cliente is not None:
                self.cerebro.cliente.apagar()
        finally:
            try:
                self.con.close()
            except Exception:
                pass


class Gestor:
    """Un ejecutor por mundo, creado cuando alguien lo abre."""

    def __init__(self, dir_mundos: Path):
        self.dir_mundos = dir_mundos
        self.ejecutores: Dict[str, Ejecutor] = {}

    def de(self, nombre: str) -> Ejecutor:
        if nombre not in self.ejecutores:
            self.ejecutores[nombre] = Ejecutor(self.dir_mundos / (nombre + ".db"))
        return self.ejecutores[nombre]

    def eliminar(self, nombre: str) -> None:
        e = self.ejecutores.pop(nombre, None)
        if e is not None:
            e.descartar()

    def cerrar_todo(self) -> None:
        for e in self.ejecutores.values():
            if e.tarea and not e.tarea.done():
                e.tarea.cancel()
            e.cerrar()
        self.ejecutores.clear()

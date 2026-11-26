"""Registro permanente y autopsia: lo que queda para mirar cuando el mundo se murió de madrugada.

Por qué existe
--------------
Un mundo que corre toda la noche se cae y, hasta ahora, no dejaba nada. Redirigir la salida a un
archivo no alcanza: Python guarda la salida en un buffer y ese buffer se pierde cuando el proceso
muere de golpe (una violación de segmento no ejecuta nada del lado de Python). Este módulo arma tres
cosas que sí sobreviven:

1. Un registro con rotación en ``<datos>/logs/mundo.log``. Cada línea se escribe y se vacía en el
   acto (``logging`` ya hace flush por registro), así que lo último que se anotó está en el disco
   cuando el proceso cae.
2. ``faulthandler`` prendido siempre, volcando a ``<datos>/logs/caida.log``. Es lo único que deja
   rastro de una violación de segmento: lo escribe el propio manejador de la señal, en C, sin pasar
   por el intérprete. También queda registrado en ``SIGUSR1``, así que a un mundo colgado se le puede
   pedir la foto de sus hilos sin matarlo (``kill -USR1 <pid>``).
3. Un latido periódico con las métricas que importan, para poder reconstruir después cómo venía el
   mundo antes de caerse: minuto simulado, velocidad real, habitantes vivos, memoria del proceso,
   tamaño de las estructuras que crecen y la latencia del modelo.

Costo en el bucle de 20 Hz
--------------------------
Ninguno medible. El latido se cierra con una comparación de ``time.monotonic()`` y vuelve enseguida
si todavía no es la hora; la cuenta de métricas sólo corre cuando de verdad toca escribir (por
omisión, cada 60 segundos reales). Las sondas son todas ``len()``, que es O(1): acá no se recorre
ningún array del mapa. Lo que sí cuesta (contar filas en la base) va en una cadencia aparte, mucho
más lenta.
"""
from __future__ import annotations

import faulthandler
import json
import logging
import logging.handlers
import os
import platform
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

NOMBRE = "mundo_vivo"
ARCHIVO_LOG = "mundo.log"
ARCHIVO_CAIDA = "caida.log"
BYTES_POR_ARCHIVO = 8 * 1024 * 1024
ARCHIVOS_VIEJOS = 6

# Cadencias por omisión del latido, en segundos reales.
CADA_LATIDO_S = 60.0
CADA_BASE_S = 600.0        # contar filas pega en la base: va mucho más espaciado

_arrancado = False
_carpeta: Optional[Path] = None
_archivo_caida = None      # se guarda la referencia a propósito: si se cierra, faulthandler pierde el fd


def log() -> logging.Logger:
    return logging.getLogger(NOMBRE)


def carpeta_logs() -> Optional[Path]:
    return _carpeta


# --------------------------------------------------------------------------- arranque
def arrancar(datos: Path | str, contexto: Optional[Dict[str, Any]] = None,
             nivel: int = logging.INFO) -> logging.Logger:
    """Prepara el registro y el manejador de caídas. Se puede llamar más de una vez sin efecto.

    `datos` es la carpeta de datos del proyecto; los registros van a `<datos>/logs/`.
    `contexto` es lo que se quiera dejar anotado del arranque (mundo, semilla, cerebro…).
    """
    global _arrancado, _carpeta, _archivo_caida
    registro = logging.getLogger(NOMBRE)
    if _arrancado:
        if contexto:
            registro.info("contexto: %s", json.dumps(contexto, default=str, ensure_ascii=False))
        return registro

    _carpeta = Path(datos) / "logs"
    _carpeta.mkdir(parents=True, exist_ok=True)

    registro.setLevel(nivel)
    registro.propagate = False
    formato = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    archivo = logging.handlers.RotatingFileHandler(
        _carpeta / ARCHIVO_LOG, maxBytes=BYTES_POR_ARCHIVO, backupCount=ARCHIVOS_VIEJOS,
        encoding="utf-8", delay=False)
    archivo.setFormatter(formato)
    registro.addHandler(archivo)

    # faulthandler escribe desde el manejador de la señal, en C: es lo único que sobrevive a un
    # segfault. El archivo se abre con buffering de línea y NO se cierra nunca.
    _archivo_caida = open(_carpeta / ARCHIVO_CAIDA, "a", buffering=1, encoding="utf-8")
    _archivo_caida.write("\n===== arranque %s pid %d =====\n"
                         % (time.strftime("%Y-%m-%d %H:%M:%S"), os.getpid()))
    faulthandler.enable(file=_archivo_caida, all_threads=True)
    for sig in ("SIGUSR1", "SIGABRT"):
        s = getattr(signal, sig, None)
        if s is not None:
            try:
                faulthandler.register(s, file=_archivo_caida, all_threads=True, chain=True)
            except (RuntimeError, ValueError, OSError):
                pass   # en un hilo que no es el principal no se puede: no es motivo para no arrancar

    _enganchar_excepciones(registro)
    _arrancado = True

    registro.info("--- arranque ---")
    registro.info("entorno: %s", json.dumps(entorno(), default=str, ensure_ascii=False))
    if contexto:
        registro.info("contexto: %s", json.dumps(contexto, default=str, ensure_ascii=False))
    return registro


def entorno() -> Dict[str, Any]:
    """Qué versión de todo está corriendo. Es la primera pregunta de cualquier autopsia."""
    from . import __version__ as version
    datos: Dict[str, Any] = {
        "version": version,
        "pid": os.getpid(),
        "python": sys.version.split()[0],
        "python_exe": sys.executable,
        "implementacion": platform.python_implementation(),
        "gil": getattr(sys, "_is_gil_enabled", lambda: True)(),
        "plataforma": platform.platform(),
        # Ojo: esto es el cerebro que ESTE proceso pidió por entorno, no el que corrió un mundo
        # que se cayó. Para eso está `_cerebro_de_la_corrida()`, que lo lee de `decisiones.modelo`.
        "cerebro_este_proceso": os.environ.get("MUNDO_VIVO_CEREBRO", "hibrido"),
    }
    try:
        import numpy
        datos["numpy"] = numpy.__version__
    except Exception as e:                          # pragma: no cover - sólo si falta numpy
        datos["numpy"] = "ERROR: %s" % e
    try:
        import websockets
        datos["websockets"] = websockets.__version__
        try:
            from websockets import speedups        # noqa: F401  (sólo para saber si está)
            datos["websockets_speedups"] = True
        except Exception:
            datos["websockets_speedups"] = False
    except Exception:
        pass
    return datos


def _enganchar_excepciones(registro: logging.Logger) -> None:
    """Toda excepción que llegue arriba sin que nadie la agarre queda escrita con su traza entera."""
    anterior = sys.excepthook

    def gancho(tipo, valor, traza):
        registro.critical("excepción sin atender", exc_info=(tipo, valor, traza))
        anterior(tipo, valor, traza)

    sys.excepthook = gancho

    anterior_hilo = threading.excepthook

    def gancho_hilo(args):
        registro.critical("excepción sin atender en el hilo %s",
                          getattr(args.thread, "name", "?"),
                          exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        anterior_hilo(args)

    threading.excepthook = gancho_hilo


def enganchar_asyncio(loop) -> None:
    """El bucle de asyncio se come las excepciones de las tareas: acá quedan escritas."""
    def manejador(_loop, contexto):
        exc = contexto.get("exception")
        log().error("asyncio: %s", contexto.get("message"), exc_info=exc)

    loop.set_exception_handler(manejador)


# --------------------------------------------------------------------------- métricas
def memoria_kb() -> int:
    """Memoria residente del proceso, leída de /proc (una línea: no cuesta nada)."""
    try:
        with open("/proc/self/statm", "rb") as f:
            paginas = int(f.read().split()[1])
        return paginas * (os.sysconf("SC_PAGE_SIZE") // 1024)
    except Exception:
        return -1


def sondas(sim) -> Dict[str, Any]:
    """Tamaño de las estructuras que crecen. Todo `len()`: no se recorre ningún array del mapa."""
    s: Dict[str, Any] = {}

    def n(nombre: str, obj) -> None:
        try:
            s[nombre] = len(obj)
        except Exception:
            pass

    n("habitantes", sim.habitantes)
    s["vivos"] = sum(1 for h in sim.habitantes.values() if h.vivo)
    n("refugios", getattr(sim, "refugios", None))
    n("ruinas", getattr(sim, "ruinas", None))
    n("fogatas", getattr(sim, "fogatas", None))
    n("agotamiento", getattr(sim, "agotamiento", None))
    n("colonias", getattr(sim, "colonias", None))
    n("eventos_sin_volcar", getattr(sim, "_eventos", None))
    n("efectos_sin_volcar", getattr(sim, "_efectos", None))
    n("pisadas", getattr(sim, "_pisadas", None))
    n("sendero_abierto", getattr(sim, "_bioma_previo", None))
    n("aldea_num", getattr(sim, "aldea_num", None))
    fauna = getattr(sim, "fauna", None)
    if fauna is not None:
        n("animales", fauna.animales)
        n("especies", fauna.esp)
    s["caminos_celdas"] = sum(len(h.camino or ()) for h in sim.habitantes.values())
    return s


def filas(con) -> Dict[str, int]:
    """Cuántas filas tiene cada tabla que crece. Usa `max(rowid)`, que es O(1) y no recorre nada."""
    out: Dict[str, int] = {}
    tablas = ("eventos", "decisiones", "entrenamiento_cerebro", "memorias", "dialogos", "capas")
    for t in tablas:
        try:
            fila = con.execute('SELECT max(rowid) FROM "%s"' % t).fetchone()
            out[t] = int(fila[0] or 0)
        except Exception:
            pass
    return out


class Latido:
    """Escribe un latido cada tanto. Preguntar si toca cuesta una comparación de reloj."""

    def __init__(self, cada_s: float = CADA_LATIDO_S, cada_base_s: float = CADA_BASE_S):
        self.cada_s = cada_s
        self.cada_base_s = cada_base_s
        self._proximo = 0.0
        self._proxima_base = 0.0

    def quizas(self, sim, *, con=None, extra: Optional[Dict[str, Any]] = None) -> None:
        ahora = time.monotonic()
        if ahora < self._proximo:
            return                                  # el caso normal: una comparación y se vuelve
        self._proximo = ahora + self.cada_s
        datos: Dict[str, Any] = {"minuto_sim": round(float(getattr(sim, "t", 0.0)), 1),
                                 "rss_kb": memoria_kb()}
        datos.update(sondas(sim))
        if extra:
            datos.update(extra)
        if con is not None and ahora >= self._proxima_base:
            self._proxima_base = ahora + self.cada_base_s
            datos["filas"] = filas(con)
        log().info("latido %s", json.dumps(datos, default=str, ensure_ascii=False))


# --------------------------------------------------------------------------- autopsia
def _cola(ruta: Path, lineas: int) -> str:
    """Las últimas `lineas` de un archivo, leyendo sólo el final."""
    if not ruta.exists():
        return "(no existe %s)" % ruta
    tam = ruta.stat().st_size
    con_cuanto = min(tam, max(4096, lineas * 400))
    with open(ruta, "rb") as f:
        f.seek(tam - con_cuanto)
        crudo = f.read().decode("utf-8", "replace")
    partes = crudo.splitlines()
    if con_cuanto < tam and partes:
        partes = partes[1:]            # la primera puede estar cortada al medio
    return "\n".join(partes[-lineas:])


def _ultimo_arranque(ruta: Path) -> str:
    """El último bloque de `caida.log`: lo que escribió faulthandler en la corrida que se murió."""
    if not ruta.exists():
        return "(nunca se cayó: no hay %s)" % ruta.name
    texto = ruta.read_text("utf-8", "replace")
    bloques = texto.split("===== arranque ")
    if len(bloques) < 2:
        return texto[-4000:]
    return "===== arranque " + bloques[-1]


def _cerebro_de_la_corrida(ruta: Optional[Path]) -> str:
    """Qué cerebro tomó las decisiones, leído de la propia base.

    El entorno no sirve para esto: `autopsia` corre en otro proceso y sin la variable, así que
    `entorno()` diría "hibrido" aunque el mundo haya corrido con el cognitivo. La verdad está en
    la columna `decisiones.modelo`; si no hay base ni decisiones, se dice.
    """
    import sqlite3

    if ruta is None or not ruta.exists():
        return "desconocido (no hay base del mundo)"
    try:
        con = sqlite3.connect("file:%s?mode=ro" % ruta, uri=True)
        try:
            filas = con.execute(
                "SELECT modelo, COUNT(*) FROM decisiones "
                "WHERE modelo IS NOT NULL AND modelo != '' "
                "GROUP BY modelo ORDER BY 2 DESC"
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        return "no se pudo leer la base (%s)" % e
    if not filas:
        return "sin decisiones guardadas todavía"
    return ", ".join("%s (%d decisiones)" % (modelo, n) for modelo, n in filas)


def informe_autopsia(datos: Path | str, nombre: Optional[str] = None, lineas: int = 80) -> str:
    """Junta en un solo texto lo que hace falta para entender una caída de madrugada."""
    import sqlite3

    datos = Path(datos)
    logs = datos / "logs"
    mundos = datos / "mundos"
    ruta = None
    if nombre:
        ruta = mundos / (nombre + ".db")
    elif mundos.is_dir():
        candidatos = sorted(mundos.glob("*.db"), key=lambda p: p.stat().st_mtime)
        ruta = candidatos[-1] if candidatos else None

    partes = ["=" * 78, "AUTOPSIA  %s" % time.strftime("%Y-%m-%d %H:%M:%S"), "=" * 78,
              "", "cerebro de la corrida (según la tabla `decisiones`):",
              "  " + _cerebro_de_la_corrida(ruta),
              "", "entorno de AHORA del proceso de autopsia (no el de la corrida que cayó):",
              json.dumps(entorno(), indent=2, default=str, ensure_ascii=False)]

    partes += ["", "-" * 78, "ÚLTIMA CAÍDA (%s)" % (logs / ARCHIVO_CAIDA), "-" * 78,
               _ultimo_arranque(logs / ARCHIVO_CAIDA)]

    partes += ["", "-" * 78, "FINAL DEL REGISTRO (%s, últimas %d líneas)" % (logs / ARCHIVO_LOG, lineas),
               "-" * 78, _cola(logs / ARCHIVO_LOG, lineas)]

    partes += ["", "-" * 78, "ÚLTIMO ESTADO GUARDADO", "-" * 78]
    if ruta is None or not ruta.exists():
        partes.append("(no hay ningún mundo en %s)" % mundos)
    else:
        partes.append("mundo: %s  (%.1f MB, guardado %s)" % (
            ruta.stem, ruta.stat().st_size / 1e6,
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ruta.stat().st_mtime))))
        try:
            con = sqlite3.connect("file:%s?mode=ro" % ruta, uri=True)
            partes.append("integridad: %s" % (con.execute("PRAGMA quick_check").fetchone() or ("?",))[0])
            partes.append("")
            partes.append("filas por tabla:")
            for (tabla,) in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
                try:
                    n = con.execute('SELECT count(*) FROM "%s"' % tabla).fetchone()[0]
                    partes.append("  %-26s %d" % (tabla, n))
                except sqlite3.Error as e:
                    partes.append("  %-26s ERROR %s" % (tabla, e))
            fila = con.execute("SELECT max(t_min) FROM decisiones").fetchone()
            if fila and fila[0] is not None:
                partes.append("")
                partes.append("último minuto con decisión guardada: %s" % fila[0])
            partes.append("")
            partes.append("últimos 12 sucesos:")
            for t, tipo, texto in con.execute(
                    "SELECT t_min, tipo, texto FROM eventos ORDER BY rowid DESC LIMIT 12"):
                partes.append("  %10s  %-22s %s" % (t, tipo, (texto or "")[:90]))
            partes.append("")
            partes.append("últimas 12 decisiones:")
            for fila in con.execute(
                    "SELECT t_min, habitante_id, accion, modelo FROM decisiones "
                    "ORDER BY rowid DESC LIMIT 12"):
                partes.append("  %10s  h%-4s %-20s %s" % fila)
            con.close()
        except sqlite3.Error as e:
            partes.append("no se pudo leer la base: %s" % e)

    partes += ["", "-" * 78, "REGISTROS DISPONIBLES", "-" * 78]
    if logs.is_dir():
        for p in sorted(logs.iterdir()):
            partes.append("  %-28s %8.1f kB  %s" % (
                p.name, p.stat().st_size / 1024,
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))))
    else:
        partes.append("  (todavía no hay carpeta %s)" % logs)
    return "\n".join(partes) + "\n"


def metricas_cerebro(cerebro, sim) -> Dict[str, Any]:
    """`latencia_s` y `rechazos_llm` del panel, que son lo que manda la velocidad del mundo."""
    try:
        e = cerebro.estado(sim)
    except Exception as exc:
        return {"cerebro_error": str(exc)[:120]}
    return {k: e.get(k) for k in ("motor", "modelo", "latencia_s", "rechazos_llm",
                                  "decisiones", "decisiones_llm", "pensando", "ultimo_error")
            if k in e}

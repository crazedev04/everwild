"""
Servidor web (FastAPI): sirve el visor 2D y la pantalla de eventos.

El servidor solo LEE los mundos (salvo al crear uno nuevo, que siempre va a un
archivo nuevo). La vista no contiene reglas de simulación.
"""
from __future__ import annotations

import asyncio
import zlib
from contextlib import asynccontextmanager
import json
import random
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..motor import biomas as B
from ..agentes.genoma import Genoma, describir_temperamento
from ..agentes import ajustes as _aj
from ..persistencia import mundo_io, sim_io, social
from .vivo import Gestor

DIR_UI = Path(__file__).resolve().parents[3] / "ui"
NOMBRE_OK = re.compile(r"^[A-Za-z0-9_\-]+$")


class NuevoHabitante(BaseModel):
    """Alta de una persona en un mundo andando. `sexo` en None es «el que esté en minoría»."""
    sexo: Optional[str] = None
    nombre: Optional[str] = None
    x: Optional[int] = None            # celda donde aparece; si falta, cerca de alguien que ya viva ahí
    y: Optional[int] = None
    dimension: int = 0


class NuevoMundo(BaseModel):
    nombre: Optional[str] = None
    semilla: Optional[int] = None
    ancho: int = mundo_io.ANCHO_POR_DEFECTO
    alto: int = mundo_io.ANCHO_POR_DEFECTO
    tam_celda_m: int = mundo_io.TAM_CELDA_POR_DEFECTO
    modelo: Optional[str] = None
    poblacion: int = 4
    # Conectar con Cognitive Engine (CCA). Default False: conserva los cerebros actuales.
    conectar_cca: bool = False


def _etiqueta_emocion(emo: dict) -> str:
    if not emo:
        return "tranquilo/a"
    c = max(emo, key=lambda k: emo[k])
    v = emo[c]
    if v < 0.25:
        return "tranquilo/a"
    return ("muy " if v >= 0.6 else "") + {"miedo": "asustado/a", "tristeza": "triste", "alegria": "contento/a", "enojo": "enojado/a"}.get(c, c)


def _pensamiento(respuesta: Optional[str], t_min: int):
    try:
        t = json.loads(respuesta or "{}").get("pensamiento")
    except ValueError:
        return None
    return {"t_min": t_min, "texto": t} if t else None


def crear_app(dir_datos: Path) -> FastAPI:
    dir_datos = Path(dir_datos)
    dir_mundos = dir_datos / "mundos"
    dir_mundos.mkdir(parents=True, exist_ok=True)
    gestor = Gestor(dir_mundos)

    @asynccontextmanager
    async def vida(_app):
        yield
        gestor.cerrar_todo()

    app = FastAPI(title="Mundo Vivo", lifespan=vida)
    cache: Dict[str, tuple] = {}  # nombre -> (mtime, meta, {capa: bytes})
    generaciones: Dict[str, dict] = {}   # mundos generándose ahora, para la pantalla de carga

    def ruta_de(nombre: str) -> Path:
        if not NOMBRE_OK.match(nombre):
            raise HTTPException(400, "Nombre de mundo inválido.")
        ruta = dir_mundos / (nombre + ".db")
        if not ruta.exists():
            raise HTTPException(404, "No existe ese mundo.")
        return ruta

    def conectar(ruta: Path) -> sqlite3.Connection:
        con = sqlite3.connect(ruta, timeout=10.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA busy_timeout=5000")
        return con

    def cargar(nombre: str, dimension: int = 0):
        """Las capas de una dimensión del mundo, cacheadas. La 0 es el mapa de siempre."""
        ruta = ruta_de(nombre)
        mtime = ruta.stat().st_mtime_ns
        clave = nombre if not dimension else "%s#%d" % (nombre, dimension)
        if clave in cache and cache[clave][0] == mtime:
            return cache[clave]
        con = conectar(ruta)
        try:
            meta = mundo_io.cargar_meta(con)
            capas = mundo_io.cargar_capas(con, dimension=dimension)
            if dimension:
                d = mundo_io.dimension_por_id(con, dimension) or {}
                meta = dict(meta, ancho=d.get("ancho"), alto=d.get("alto"), tam_celda_m=d.get("tam_celda_m"),
                            nombre=d.get("nombre"), dimension=dimension)
            meta["dimensiones"] = [{k: v for k, v in d.items() if k != "meta"} for d in mundo_io.listar_dimensiones(con)]
            fila = con.execute("SELECT t_min FROM estado_mundo WHERE id = 1").fetchone()
            meta["t_min"] = fila["t_min"] if fila else 480
        finally:
            con.close()
        crudos = {n: np.ascontiguousarray(a.astype(a.dtype.newbyteorder("<"))).tobytes() for n, a in capas.items()}
        while len(cache) >= 3:                      # a lo sumo 3 mapas con capas en memoria
            cache.pop(next(iter(cache)))
        cache[clave] = (mtime, meta, crudos)
        return cache[clave]

    # ------------------------------------------------------------- páginas
    class _SinCache(StaticFiles):
        async def get_response(self, path, scope):
            r = await super().get_response(path, scope)
            r.headers["Cache-Control"] = "no-cache"
            return r

    app.mount("/ui", _SinCache(directory=DIR_UI), name="ui")
    _SIN_CACHE = {"Cache-Control": "no-cache"}

    @app.get("/", include_in_schema=False)
    def pagina_mapa():
        return FileResponse(DIR_UI / "index.html", headers=_SIN_CACHE)

    @app.get("/eventos", include_in_schema=False)
    def pagina_eventos():
        return FileResponse(DIR_UI / "eventos.html", headers=_SIN_CACHE)

    # ----------------------------------------------------------------- API
    @app.get("/api/biomas")
    def api_biomas():
        return [{"id": i, "clave": k, "nombre": n, "color": c} for i, (k, n, c) in B.BIOMAS.items()]

    @app.get("/api/mundos")
    def api_mundos():
        out = []
        for f in sorted(dir_mundos.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                con = conectar(f)
                try:
                    m = mundo_io.cargar_meta(con)
                finally:
                    con.close()
                out.append({"nombre": f.stem, "semilla": m.get("semilla"), "ancho": m.get("ancho"),
                            "alto": m.get("alto"), "creado_en": m.get("creado_en")})
            except Exception:
                continue
        return out

    def _generar_en_hilo(trabajo: dict, datos: NuevoMundo, semilla: int) -> None:
        """Genera el mundo fuera del hilo del servidor y va anotando en qué etapa va."""
        try:
            def avisar(frac, texto):
                trabajo["frac"], trabajo["texto"] = float(frac), str(texto)
            ruta = mundo_io.crear_mundo(dir_mundos, semilla, datos.ancho, datos.alto, datos.tam_celda_m,
                                        nombre=datos.nombre, progreso=avisar,
                                        cerebro_remoto=bool(datos.conectar_cca))
            if datos.modelo and datos.modelo.strip():
                from ..agentes import ajustes as _aj
                from ..persistencia import db as _db
                con = _db.abrir(ruta)
                try:
                    _aj.guardar(con, {"modelo": datos.modelo.strip()})
                finally:
                    con.close()
            # Poblar con la cantidad pedida (por defecto 4).
            try:
                n = max(2, min(100, int(datos.poblacion or 4)))
            except (TypeError, ValueError):
                n = 4
            from ..persistencia import db as _db
            con = _db.abrir(ruta)
            try:
                sim_io.crear_habitantes_iniciales(con, n=n, semilla=semilla)
            finally:
                con.close()
            trabajo.update(frac=1.0, texto="Listo", nombre=ruta.stem, hecho=True)
        except Exception as e:                       # el visor tiene que poder mostrar el error, no quedarse colgado
            trabajo.update(hecho=True, error=str(e) or e.__class__.__name__)

    @app.post("/api/mundos")
    def api_crear(datos: NuevoMundo):
        if not (64 <= datos.ancho <= 4096 and 64 <= datos.alto <= 4096):
            raise HTTPException(400, "El tamaño debe estar entre 64 y 4096 celdas.")
        if not (1 <= datos.tam_celda_m <= 200):
            raise HTTPException(400, "La celda debe medir entre 1 y 200 metros.")
        if datos.ancho * datos.alto > 20_000_000:
            raise HTTPException(400, "Demasiadas celdas: generar ese mundo no termina nunca.")
        semilla = datos.semilla if datos.semilla is not None else random.randrange(1, 2 ** 31)
        # Generar 2048×2048 lleva más de un minuto: se hace aparte y el visor va preguntando cómo viene.
        import threading
        tid = "g%d" % random.randrange(1, 2 ** 31)
        trabajo = {"frac": 0.0, "texto": "Preparando", "hecho": False, "nombre": None, "error": None,
                   "semilla": semilla, "celdas": datos.ancho * datos.alto}
        generaciones[tid] = trabajo
        for viejo in [k for k, v in generaciones.items() if v.get("hecho") and k != tid][:-4]:
            generaciones.pop(viejo, None)            # no se acumulan trabajos terminados
        threading.Thread(target=_generar_en_hilo, args=(trabajo, datos, semilla), daemon=True).start()
        return {"trabajo": tid, "semilla": semilla}

    @app.get("/api/mundos/generando/{tid}")
    def api_generando(tid: str):
        t = generaciones.get(tid)
        if t is None:
            raise HTTPException(404, "Ese trabajo de generación no existe.")
        return t

    @app.delete("/api/mundos/{nombre}")
    def api_eliminar(nombre: str):
        """Borra el mundo (su base de datos). No se puede deshacer: la interfaz pide confirmación."""
        ruta = ruta_de(nombre)
        gestor.eliminar(nombre)
        cache.pop(nombre, None)
        for sufijo in ("", "-wal", "-shm"):
            f = Path(str(ruta) + sufijo)
            try:
                f.unlink()
            except FileNotFoundError:
                pass
            except OSError as e:
                raise HTTPException(500, "No se pudo borrar %s: %s" % (f.name, e))
        return {"ok": True, "nombre": nombre}

    @app.get("/api/modelos")
    def api_modelos():
        """Modelos instalados en Ollama (para elegir antes de crear el mundo)."""
        import urllib.request
        from ..agentes import ajustes as _aj
        host = _aj.PREDETERMINADOS["host"].rstrip("/")
        try:
            with urllib.request.urlopen(host + "/api/tags", timeout=3) as r:
                nombres = [m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])]
            return {"ok": True, "modelos": sorted(nombres), "predeterminado": _aj.PREDETERMINADOS["modelo"]}
        except Exception as e:
            return {"ok": False, "modelos": [], "predeterminado": _aj.PREDETERMINADOS["modelo"], "error": str(e)[:120]}

    @app.get("/api/mundos/{nombre}/era")
    def api_era(nombre: str):
        """Era actual según las propiedades descubiertas por los habitantes."""
        from ..agentes import conocimiento as _c
        con = conectar(ruta_de(nombre))
        try:
            props = set()
            for (mats,) in con.execute("SELECT materiales FROM conocimientos WHERE origen != 'catalogo'"):
                try:
                    for m in json.loads(mats or "[]"):
                        pass
                except Exception:
                    pass
            # propiedades descubiertas = las que aparecen en conocimientos como propiedad
            for (prop,) in con.execute("SELECT DISTINCT propiedad FROM conocimientos WHERE propiedad IS NOT NULL AND propiedad != ''"):
                props.add(prop)
            # también las del catálogo descubierto
            for (rid,) in con.execute("SELECT receta_id FROM conocimientos WHERE receta_id IS NOT NULL"):
                pass
            total = len(_c.PROPIEDADES)
            # eras por propiedad clave
            orden = [("Piedra", set()), ("Piedra tallada", {"corta", "golpea"}),
                     ("Fuego", {"enciende"}), ("Metal", {"funde"}),
                     ("Acero", {"afila", "clava"}), ("Electricidad", {"conduce"})]
            era_idx = 0
            for i, (nombre_era, claves) in enumerate(orden):
                if claves and claves.issubset(props):
                    era_idx = i
            progreso = len(props) / total if total else 0.0
            return {"era": orden[era_idx][0], "era_idx": era_idx, "eras_total": len(orden) - 1,
                    "propiedades_descubiertas": len(props), "propiedades_total": total,
                    "progreso": round(progreso, 3)}
        finally:
            con.close()

    @app.get("/api/mundos/{nombre}/meta")
    def api_meta(nombre: str, dim: int = 0):
        return cargar(nombre, dim)[1]

    @app.get("/api/mundos/{nombre}/capa/{capa}")
    def api_capa(nombre: str, capa: str, dim: int = 0):
        crudos = cargar(nombre, dim)[2]
        if capa not in crudos:
            raise HTTPException(404, "Capa desconocida.")
        raw = crudos[capa]
        comp = zlib.compress(raw, level=1)
        return Response(comp, media_type="application/octet-stream",
                        headers={"Cache-Control": "public, max-age=86400", "Content-Encoding": "deflate"})

    @app.get("/api/mundos/{nombre}/eventos")
    def api_eventos(nombre: str, tipo: Optional[str] = None, actor: Optional[int] = None,
                    antes_id: Optional[int] = None, limite: int = Query(100, ge=1, le=1000)):
        con = conectar(ruta_de(nombre))
        try:
            return {"eventos": mundo_io.listar_eventos(con, tipo, actor, antes_id, limite),
                    "tipos": mundo_io.tipos_de_evento(con)}
        finally:
            con.close()

    # ------------------------------------------------------- mundo en vivo
    @app.websocket("/ws/{nombre}")
    async def ws_vivo(ws: WebSocket, nombre: str):
        if not NOMBRE_OK.match(nombre) or not (dir_mundos / (nombre + ".db")).exists():
            await ws.close(code=4404)
            return
        await ws.accept()
        ej = gestor.de(nombre)
        q = ej.suscribir()
        await ws.send_text(json.dumps(ej.hola(), separators=(",", ":")))

        async def enviar():
            while True:
                await ws.send_text(await q.get())

        envio = asyncio.get_running_loop().create_task(enviar())
        try:
            while True:
                try:
                    c = json.loads(await ws.receive_text())
                except ValueError:
                    continue
                if isinstance(c, dict):
                    r = ej.comando(c)
                    if r:
                        await ws.send_text(json.dumps(r))
        except WebSocketDisconnect:
            pass
        finally:
            envio.cancel()
            await ej.desuscribir(q)

    @app.get("/api/mundos/{nombre}/habitantes")
    def api_habitantes(nombre: str):
        con = conectar(ruta_de(nombre))
        try:
            return [{"id": r["id"], "nombre": r["nombre"], "vivo": r["muerte_min"] is None,
                     "muerte_min": r["muerte_min"], "causa_muerte": r["causa_muerte"]}
                    for r in con.execute("SELECT id, nombre, muerte_min, causa_muerte FROM habitantes ORDER BY id")]
        finally:
            con.close()

    @app.get("/api/mundos/{nombre}/habitantes/{hid}")
    def api_ficha(nombre: str, hid: int):
        """Ficha para el OBSERVADOR (incluye memorias y relaciones privadas; los habitantes no ven esto)."""
        con = conectar(ruta_de(nombre))
        try:
            r = con.execute("SELECT * FROM habitantes WHERE id = ?", (hid,)).fetchone()
            if not r:
                raise HTTPException(404, "No existe ese habitante.")
            genoma = json.loads(r["genoma"] or "{}")
            temperamento = ""
            if genoma:
                try:
                    temperamento = describir_temperamento(Genoma.de_dict(genoma))
                except Exception:
                    pass
            return {
                "id": r["id"], "nombre": r["nombre"], "vivo": r["muerte_min"] is None,
                "nacimiento_min": r["nacimiento_min"], "muerte_min": r["muerte_min"], "causa_muerte": r["causa_muerte"],
                "estado": json.loads(r["estado"] or "{}"), "temperamento": temperamento,
                "rasgos": genoma.get("rasgos", {}), "generacion": genoma.get("generacion", 0),
                "memorias": [dict(m) for m in con.execute(
                    "SELECT t_min, tipo, contenido, importancia, veces, origen FROM memorias WHERE habitante_id = ? "
                    "ORDER BY t_min DESC LIMIT 40", (hid,))],
                "aprendizajes": [dict(m) for m in con.execute(
                    "SELECT t_min, contenido, veces FROM memorias WHERE habitante_id = ? AND tipo IN ('creencia','resumen') "
                    "ORDER BY t_min DESC LIMIT 12", (hid,))],
                "plan": (json.loads(r["estado"] or "{}")).get("plan") or [],
                "rasgos_vivos": (json.loads(r["estado"] or "{}")).get("rasgos_vivos") or {},
                "habito": {"v": (json.loads(r["estado"] or "{}")).get("habito_v") or {},
                           "n": ((json.loads(r["estado"] or "{}")).get("habito") or {}).get("n", 0)},
                "lugares": {k: v for k, v in ((json.loads(r["estado"] or "{}")).get("lugares") or {}).items()},
                "relaciones": [dict(m) for m in con.execute(
                    "SELECT rel.otro_id, h.nombre AS otro, rel.afecto, rel.confianza, rel.resumen FROM relaciones rel "
                    "JOIN habitantes h ON h.id = rel.otro_id WHERE rel.habitante_id = ?", (hid,))],
                "eventos": mundo_io.listar_eventos(con, None, hid, None, 30),
                "madre_id": r["madre_id"], "padre_id": r["padre_id"], "nacimiento_min": r["nacimiento_min"],
                "sexo": json.loads(r["identidad"] or "{}").get("sexo"),
                "edad_dias": _edad_dias(con, r),
                "inv_t": (json.loads(r["estado"] or "{}")).get("inv_t") or {},
                "emocion": _etiqueta_emocion((json.loads(r["estado"] or "{}")).get("emo") or {}),
                "inventario": (json.loads(r["estado"] or "{}")).get("inventario") or {},
                "conocimientos": [x["nombre"] for x in con.execute(
                    "SELECT c.nombre FROM conoce k JOIN conocimientos c ON c.id = k.conocimiento_id WHERE k.habitante_id = ?", (hid,))],
                "pensamientos": [p for p in (_pensamiento(x["respuesta_modelo"], x["t_min"]) for x in con.execute(
                    "SELECT t_min, respuesta_modelo FROM decisiones WHERE habitante_id = ? ORDER BY id DESC LIMIT 6", (hid,))) if p],
            }
        finally:
            con.close()

    @app.get("/api/mundos/{nombre}/recetas")
    def api_recetas(nombre: str):
        """Recetas existentes (catálogo en JSON, con quién la descubrió) y recetas inventadas por los habitantes."""
        from .. import catalogos
        from ..agentes import conocimiento as _c
        from ..reglas import Reglas
        con = conectar(ruta_de(nombre))
        try:
            reglas = Reglas.cargar()
            cat = catalogos.cargar_recetas(reglas.materiales, _c.PROPIEDADES)
            filas = [dict(r) for r in con.execute(
                "SELECT c.id, c.nombre, c.descripcion, c.materiales, c.propiedad, c.origen, c.receta_id, c.t_min, h.nombre AS creador, "
                "(SELECT COUNT(*) FROM conoce k WHERE k.conocimiento_id = c.id) AS saben "
                "FROM conocimientos c LEFT JOIN habitantes h ON h.id = c.creador_id ORDER BY c.id")]
            por_receta = {f["receta_id"]: f for f in filas if f["receta_id"]}
            existentes = []
            for rid, d in cat.items():
                f = por_receta.get(rid)
                existentes.append({"id": rid, "nombre": d["nombre"], "ingredientes": d["ingredientes"], "propiedad": d["propiedad"],
                                   "descripcion": d["descripcion"], "categoria": d["categoria"], "descubierta": f is not None,
                                   "por": f["creador"] if f else None, "t_min": f["t_min"] if f else None,
                                   "saben": f["saben"] if f else 0})
            inventadas = [{"id": f["id"], "nombre": f["nombre"], "ingredientes": json.loads(f["materiales"]), "propiedad": f["propiedad"],
                           "descripcion": f["descripcion"], "por": f["creador"], "t_min": f["t_min"], "saben": f["saben"]}
                          for f in filas if f["origen"] != "catalogo"]
            return {"existentes": existentes, "inventadas": inventadas,
                    "propiedades": _c.PROPIEDADES}
        finally:
            con.close()

    def _edad_dias(con, r) -> float:
        fin = r["muerte_min"]
        if fin is None:
            f = con.execute("SELECT t_min FROM estado_mundo WHERE id = 1").fetchone()
            fin = f["t_min"] if f else 0
        return round(max(0.0, (fin - (r["nacimiento_min"] or 0)) / 1440.0), 1)

    @app.get("/api/mundos/{nombre}/familias")
    def api_familias(nombre: str):
        """Personas con sus padres y las uniones (parejas) que se formaron: alcanza para dibujar el árbol genealógico."""
        con = conectar(ruta_de(nombre))
        try:
            t = (con.execute("SELECT t_min FROM estado_mundo WHERE id = 1").fetchone() or {"t_min": 0})["t_min"]
            gente = []
            for r in con.execute("SELECT id, nombre, nacimiento_min, muerte_min, causa_muerte, madre_id, padre_id, identidad, x, y FROM habitantes ORDER BY id"):
                gente.append({"id": r["id"], "nombre": r["nombre"], "sexo": json.loads(r["identidad"] or "{}").get("sexo"),
                              "madre_id": r["madre_id"], "padre_id": r["padre_id"], "vivo": r["muerte_min"] is None,
                              "edad_dias": round(((r["muerte_min"] if r["muerte_min"] is not None else t) - (r["nacimiento_min"] or 0)) / 1440.0, 1),
                              "x": (r["x"] or 0) / 50.0, "y": (r["y"] or 0) / 50.0})
            uniones = set()
            for r in con.execute("SELECT datos FROM eventos WHERE tipo = 'familia'"):
                try:
                    d = json.loads(r["datos"] or "{}")
                    if d.get("a") is not None and d.get("b") is not None:
                        uniones.add(tuple(sorted((int(d["a"]), int(d["b"])))))
                except ValueError:
                    pass
            for g in gente:
                if g["madre_id"] and g["padre_id"]:
                    uniones.add(tuple(sorted((g["madre_id"], g["padre_id"]))))
            return {"personas": gente, "uniones": [list(u) for u in sorted(uniones)]}
        finally:
            con.close()

    @app.get("/api/mundos/{nombre}/fauna")
    def api_fauna(nombre: str):
        from .. import catalogos
        from ..motor.fauna import CLAVES_HABITAT
        con = conectar(ruta_de(nombre))
        try:
            esp = catalogos.cargar_especies(CLAVES_HABITAT)
            fila = con.execute("SELECT valor FROM estado_dinamico WHERE clave = 'fauna'").fetchone()
            cuentas, muertes, edades = {}, {}, {}
            if fila:
                d = json.loads(bytes(fila[0]).decode("utf-8"))
                for a in d.get("animales", []):
                    cuentas[a["sp"]] = cuentas.get(a["sp"], 0) + 1
                    edades.setdefault(a["sp"], []).append(float(a.get("e", 0.0)) / 1440.0)
                muertes = d.get("muertes", {})
            lista = [{"id": k, "nombre": v["nombre"], "emoji": v["emoji"], "medio": v["medio"], "clase": v["clase"],
                      "dieta": v["dieta"], "peligro": v["peligro"], "montable": v["montable"], "n": cuentas.get(k, 0),
                      "edad_media": round(sum(edades[k]) / len(edades[k]), 1) if k in edades else None,
                      "vida_dias": v.get("vida_dias")}
                     for k, v in esp.items()]
            return {"especies": lista, "total": sum(cuentas.values()), "muertes": muertes}
        finally:
            con.close()

    @app.get("/api/mundos/{nombre}/ajustes")
    def api_ajustes(nombre: str):
        con = conectar(ruta_de(nombre))
        try:
            return {"ajustes": _aj.obtener(con), "modulos_desc": _aj.MODULOS}
        finally:
            con.close()

    @app.get("/api/mundos/{nombre}/dialogos")
    def api_dialogos(nombre: str, habitante: Optional[int] = None, limite: int = Query(50, ge=1, le=500)):
        """Registro completo de lo que se dijeron (solo para el observador)."""
        con = conectar(ruta_de(nombre))
        try:
            return {"dialogos": social.listar_dialogos(con, habitante, limite)}
        finally:
            con.close()

    @app.get("/api/mundos/{nombre}/dinamico/nieve")
    def api_nieve(nombre: str):
        """Mapa de nieve acumulada (1 byte/celda, 0-255) comprimido deflate."""
        def _resp(raw: bytes) -> Response:
            return Response(
                zlib.compress(raw, level=1),
                media_type="application/octet-stream",
                headers={"Cache-Control": "no-cache", "Content-Encoding": "deflate"},
            )
        ej = gestor.ejecutores.get(nombre)
        if ej is not None:
            return _resp(ej.sim.nieve_bytes())
        con = conectar(ruta_de(nombre))
        try:
            f = con.execute("SELECT valor FROM estado_dinamico WHERE clave = 'nieve'").fetchone()
        finally:
            con.close()
        if f:
            return _resp(bytes(f["valor"]))
        m = cargar(nombre)[1]
        return _resp(bytes(int(m["ancho"]) * int(m["alto"])))

    @app.get("/api/mundos/{nombre}/dinamico/quemado")
    def api_quemado(nombre: str):
        """Mapa de ceniza (1 byte/celda, 0-255) comprimido deflate."""
        def _resp(raw: bytes) -> Response:
            return Response(
                zlib.compress(raw, level=1),
                media_type="application/octet-stream",
                headers={"Cache-Control": "no-cache", "Content-Encoding": "deflate"},
            )
        ej = gestor.ejecutores.get(nombre)
        if ej is not None:
            return _resp(ej.sim.fuego.ceniza_bytes())
        con = conectar(ruta_de(nombre))
        try:
            f = con.execute("SELECT valor FROM estado_dinamico WHERE clave = 'quemado'").fetchone()
        finally:
            con.close()
        if f:
            return _resp(bytes(f["valor"]))
        m = cargar(nombre)[1]
        return _resp(bytes(int(m["ancho"]) * int(m["alto"])))

    @app.get("/api/mundos/{nombre}/metricas")
    def api_metricas(nombre: str):
        """Telemetria en vivo: A* cache, ms/sistema, chunks activos, fuego."""
        ej = gestor.ejecutores.get(nombre)
        if ej is None:
            raise HTTPException(404, "Mundo no está corriendo")
        sim = ej.sim
        ter = sim.terreno
        cache = ter.metricas_cache() if hasattr(ter, "metricas_cache") else {}
        fuego = sim.fuego
        from ..motor.chunks import chunks_activos as _chunks
        chunks = _chunks(sim)
        return {
            "cache_rutas": cache,
            "fuego": {
                "celdas_ardiendo": int(fuego.celda_ardiendo if hasattr(fuego, "celda_ardiendo") else (fuego.fuego > 0).sum()),
                "version": fuego.version,
                "episodio_celdas": fuego.episodio_celdas,
            },
            "chunks_activos": len(chunks),
            "habitantes_vivos": sum(1 for h in sim.habitantes.values() if h.vivo),
            "t_min": round(sim.t, 1),
        }

    @app.post("/api/mundos/{nombre}/habitantes")
    def api_sumar_habitante(nombre: str, datos: NuevoHabitante):
        """Sangre nueva en un mundo que ya corre (fase 6 del plan del motor).

        Llega sin padres, así que no es pariente de nadie: es lo que destraba el cuello de botella de
        sangre cuando toda una generación son medio hermanos y `parentesco_cercano` les prohíbe procrear.
        """
        if datos.sexo == "azar":
            datos.sexo = None
        if datos.sexo is not None and datos.sexo not in ("F", "M"):
            raise HTTPException(400, "El sexo tiene que ser 'F', 'M' o nada (para balancear solo).")
        if datos.nombre is not None and not (2 <= len(datos.nombre.strip()) <= 40):
            raise HTTPException(400, "El nombre debe tener entre 2 y 40 letras.")
        con = conectar(ruta_de(nombre))
        try:
            cerca = (datos.x, datos.y) if (datos.x is not None and datos.y is not None) else None
            try:
                ficha = sim_io.sumar_habitante(con, sexo=datos.sexo, cerca_de=cerca,
                                               nombre=(datos.nombre or "").strip() or None,
                                               dimension=datos.dimension)
            except (ValueError, KeyError, IndexError) as e:
                raise HTTPException(400, "No se pudo: %s" % e)
        finally:
            con.close()
        cache.clear()                   # la ficha del mundo cambió: que el visor la vuelva a pedir
        return ficha

    @app.post("/api/mundos/{nombre}/exportar")
    def api_exportar(nombre: str):
        ruta = ruta_de(nombre)
        destino = dir_datos / "exportaciones" / ("%s_%s.zip" % (nombre, datetime.now().strftime("%Y%m%d_%H%M%S")))
        mundo_io.exportar_paquete(ruta, destino)
        return FileResponse(destino, filename=destino.name, media_type="application/zip")

    return app

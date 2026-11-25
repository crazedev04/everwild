"""
Motor de reglas declarativas ("recetas" en JSON).

El mundo carga materiales y reacciones desde archivos JSON; agregar un fenómeno nuevo (por ejemplo la conducción
eléctrica) es agregar un archivo, no cambiar código. Ideas tomadas de Cataclysm DDA (JSON con "type"/"id" y
"copy-from"), Noita (tabla de reacciones) y Dwarf Fortress (propiedades de material: puntos de fusión/ignición).

Formato:
  {"type": "material", "id": "acero", "copy-from": "hierro", "dureza_mohs": 5, ...}
  {"type": "reaccion", "id": "...", "cuando": [{"path": "cuerpo.temperatura_C", "op": ">=", "valor": "@material.punto_ablandamiento_C"}],
   "efectos": [{"tipo": "estado", "valor": "blando"}], "probabilidad": 1.0}
Las reglas se validan AL CARGAR: un error indica archivo e id, y el mundo no arranca con reglas rotas.
Una carpeta de datos del usuario puede agregar o reemplazar entradas por id (mismo id = reemplaza).
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

OPERADORES = {"==", "!=", ">", ">=", "<", "<=", "existe", "no_existe"}
EFECTOS = {"estado", "dano", "evento", "emitir_calor", "apagar_fuego", "inflamar"}
RAIZ_PATHS = {"material", "cuerpo", "ambiente"}
DIR_BASE = Path(__file__).resolve().parents[2] / "datos_base" / "reglas"


class ErrorDeReglas(ValueError):
    pass


def _buscar(ctx: dict, path: str):
    cur: Any = ctx
    for parte in path.split("."):
        if not isinstance(cur, dict) or parte not in cur:
            return None, False
        cur = cur[parte]
    return cur, True


class Reglas:
    def __init__(self, materiales: Dict[str, dict], reacciones: List[dict], huella: str):
        self.materiales, self.reacciones, self.huella = materiales, reacciones, huella

    # ------------------------------------------------------------------ carga
    @staticmethod
    def cargar(*carpetas: Path) -> "Reglas":
        # Sin esto `datos/extra/reglas/` nunca se leía (las recetas y especies sí lo respetan, ver catalogos.py):
        # se podía agregar una receta por JSON, pero si usaba un material nuevo fallaba la validación.
        if not carpetas:
            from .catalogos import dir_extra
            carpetas = (DIR_BASE, dir_extra() / "reglas")
        crudos_mat: Dict[str, dict] = {}
        crudos_rea: Dict[str, dict] = {}
        h = hashlib.sha256()
        for carpeta in carpetas:
            for f in sorted(Path(carpeta).glob("*.json")):
                texto = f.read_text(encoding="utf-8")
                h.update(f.name.encode() + texto.encode())
                try:
                    datos = json.loads(texto)
                except ValueError as e:
                    raise ErrorDeReglas("%s: JSON inválido (%s)" % (f.name, e))
                if not isinstance(datos, list):
                    raise ErrorDeReglas("%s: debe contener una lista de entradas." % f.name)
                for d in datos:
                    if not isinstance(d, dict) or "type" not in d or "id" not in d:
                        raise ErrorDeReglas("%s: toda entrada necesita 'type' e 'id'." % f.name)
                    d["_archivo"] = f.name
                    if d["type"] == "material":
                        crudos_mat[d["id"]] = d
                    elif d["type"] == "reaccion":
                        crudos_rea[d["id"]] = d
                    else:
                        raise ErrorDeReglas("%s: tipo desconocido '%s' (id %s)." % (f.name, d["type"], d["id"]))
        materiales = {i: Reglas._resolver(i, crudos_mat, []) for i in crudos_mat}
        reacciones = [Reglas._validar_reaccion(r) for r in crudos_rea.values()]
        return Reglas(materiales, reacciones, h.hexdigest()[:16])

    @staticmethod
    def _resolver(id_: str, crudos: Dict[str, dict], pila: List[str]) -> dict:
        d = crudos[id_]
        if id_ in pila:
            raise ErrorDeReglas("%s: 'copy-from' circular en '%s'." % (d["_archivo"], id_))
        base: dict = {}
        if "copy-from" in d:
            padre = d["copy-from"]
            if padre not in crudos:
                raise ErrorDeReglas("%s: '%s' copia de '%s', que no existe." % (d["_archivo"], id_, padre))
            base = dict(Reglas._resolver(padre, crudos, pila + [id_]))
        base.update({k: v for k, v in d.items() if k not in ("copy-from", "type", "_archivo")})
        return base

    @staticmethod
    def _validar_reaccion(r: dict) -> dict:
        donde = "%s: reacción '%s'" % (r["_archivo"], r["id"])
        if not r.get("cuando") or not r.get("efectos"):
            raise ErrorDeReglas("%s necesita 'cuando' y 'efectos'." % donde)
        for c in r["cuando"]:
            if c.get("op") not in OPERADORES:
                raise ErrorDeReglas("%s: operador desconocido '%s'." % (donde, c.get("op")))
            if str(c.get("path", "")).split(".")[0] not in RAIZ_PATHS:
                raise ErrorDeReglas("%s: path inválido '%s' (debe empezar con material., cuerpo. o ambiente.)." % (donde, c.get("path")))
            v = c.get("valor")
            if isinstance(v, str) and v.startswith("@") and v[1:].split(".")[0] not in RAIZ_PATHS:
                raise ErrorDeReglas("%s: referencia inválida '%s'." % (donde, v))
        for e in r["efectos"]:
            if e.get("tipo") not in EFECTOS:
                raise ErrorDeReglas("%s: efecto desconocido '%s'." % (donde, e.get("tipo")))
        p = r.get("probabilidad", 1.0)
        if not (0.0 <= p <= 1.0):
            raise ErrorDeReglas("%s: la probabilidad debe estar entre 0 y 1." % donde)
        return r

    # ------------------------------------------------------------- evaluación
    def material(self, id_: str) -> dict:
        if id_ not in self.materiales:
            raise KeyError("Material desconocido: %s" % id_)
        return self.materiales[id_]

    @staticmethod
    def _cumple(cond: dict, ctx: dict) -> bool:
        val, hay = _buscar(ctx, cond["path"])
        op = cond["op"]
        if op == "existe":
            return hay
        if op == "no_existe":
            return not hay
        if not hay:
            return False
        ref = cond.get("valor")
        if isinstance(ref, str) and ref.startswith("@"):
            ref, ok = _buscar(ctx, ref[1:])
            if not ok:
                return False
        try:
            return {"==": val == ref, "!=": val != ref, ">": val > ref, ">=": val >= ref,
                    "<": val < ref, "<=": val <= ref}[op]
        except TypeError:
            return False

    def aplicar(self, ctx: dict, rng: Optional[random.Random] = None) -> List[dict]:
        """Devuelve los efectos de todas las reacciones cuyas condiciones se cumplen en `ctx`.
        ctx = {"material": {...propiedades...}, "cuerpo": {...estado del objeto...}, "ambiente": {...}}"""
        rng = rng or random.Random()
        out: List[dict] = []
        for r in self.reacciones:
            if all(self._cumple(c, ctx) for c in r["cuando"]) and rng.random() < r.get("probabilidad", 1.0):
                for e in r["efectos"]:
                    out.append(dict(e, regla=r["id"]))
        return out


# ----------------------------------------------------------- física del calor
COEF_CONVECCION = 25.0  # W/m²K, aire en calma junto a un fuego


def calentar(temp_c: float, fuente_c: float, masa_kg: float, area_m2: float, calor_especifico: float,
             dt_s: float, h: float = COEF_CONVECCION) -> float:
    """Modelo de capacitancia concentrada: la pieza tiende a la temperatura de la fuente con tau = m·c/(h·A).
    Una fogata (~800 °C) nunca ablanda hierro (~900 °C); una fragua de carbón (~1100 °C) sí."""
    tau = masa_kg * calor_especifico / (h * area_m2)
    return fuente_c + (temp_c - fuente_c) * math.exp(-dt_s / tau)


def minutos_hasta(umbral_c: float, fuente_c: float, masa_kg: float, area_m2: float, calor_especifico: float,
                  temp_inicial_c: float = 20.0) -> Optional[float]:
    """Minutos para que la pieza llegue a `umbral_c`, o None si la fuente no alcanza esa temperatura."""
    if fuente_c <= umbral_c:
        return None
    tau = masa_kg * calor_especifico / (COEF_CONVECCION * area_m2)
    return -tau * math.log((fuente_c - umbral_c) / (fuente_c - temp_inicial_c)) / 60.0

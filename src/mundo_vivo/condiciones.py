"""
Evaluador único de condiciones declarativas.

Toda la lógica que decide "¿se cumple esto?" en datos JSON pasa por acá: validar la propiedad de un invento,
decidir dónde aparece un material, cuándo cae un meteorito, cuándo muta un bicho, qué abre un portal.
Una sola gramática para todo; cada sistema solo aporta su contexto.

    condición simple   {"path": "material.dureza_mohs", "op": ">=", "valor": 5}
    referencia         {"path": "cuerpo.temperatura_C", "op": ">=", "valor": "@material.punto_ignicion_C"}
    combinadores       {"todas": [c, ...]} | {"cualquiera": [c, ...]} | {"no": c}
    cuantificadores    {"alguno": [c, ...]} | {"todos": [c, ...]}   (sobre una LISTA de contextos)
    lista suelta       [c, c, ...]  ==  {"todas": [...]}

REGLA DE RENDIMIENTO (ver docs/OPTIMIZACION.md): esto NUNCA se evalúa por celda por tick. Se usa solo en
sucesos discretos (inventar, fabricar, disparar un fenómeno, mutar, chequear un hito). Lo que corre en el
bucle de 20 Hz se compila antes a diccionarios planos y arrays de numpy.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

# Operadores simples: los que ya usaban las reacciones, más los que hacían falta para contenido nuevo.
OPERADORES = {"==", "!=", ">", ">=", "<", "<=", "existe", "no_existe", "en", "no_en", "contiene", "entre"}
COMBINADORES = {"todas", "cualquiera", "no"}
CUANTIFICADORES = {"alguno", "todos"}


class ErrorDeCondicion(ValueError):
    pass


def buscar(ctx: dict, path: str):
    """Sigue una ruta con puntos dentro del contexto. Devuelve (valor, existe)."""
    cur: Any = ctx
    for parte in path.split("."):
        if isinstance(cur, dict) and parte in cur:
            cur = cur[parte]
        else:
            return None, False
    return cur, True


def _resolver_valor(v, ctx: dict):
    """Un valor que empieza con @ es una referencia a otra parte del contexto."""
    if isinstance(v, str) and v.startswith("@"):
        val, _ = buscar(ctx, v[1:])
        return val
    return v


def _simple(cond: dict, ctx: dict) -> bool:
    path, op = cond["path"], cond["op"]
    val, hay = buscar(ctx, path)
    if op == "existe":
        return hay
    if op == "no_existe":
        return not hay
    if not hay:
        return False
    objetivo = _resolver_valor(cond.get("valor"), ctx)
    try:
        if op == "==":
            return val == objetivo
        if op == "!=":
            return val != objetivo
        if op == "en":
            return val in (objetivo or [])
        if op == "no_en":
            return val not in (objetivo or [])
        if op == "contiene":
            return objetivo in (val or [])
        if op == "entre":
            lo, hi = objetivo
            return lo <= val < hi
        if op == ">":
            return val > objetivo
        if op == ">=":
            return val >= objetivo
        if op == "<":
            return val < objetivo
        return val <= objetivo
    except (TypeError, ValueError):
        return False       # comparar texto con número no es un error: simplemente no se cumple


def evaluar(cond, ctx: dict, listas: Optional[Dict[str, Sequence[dict]]] = None) -> bool:
    """¿Se cumple `cond` en este contexto?

    `listas` trae las colecciones sobre las que trabajan los cuantificadores, por raíz. Por ejemplo
    `{"material": [m1, m2]}` hace que `{"alguno": [...]}` pruebe cada material por separado.
    """
    if cond is None:
        return True
    if isinstance(cond, list):
        return all(evaluar(c, ctx, listas) for c in cond)
    if not isinstance(cond, dict):
        raise ErrorDeCondicion("Condición inválida: %r" % (cond,))
    if "todas" in cond:
        return all(evaluar(c, ctx, listas) for c in cond["todas"])
    if "cualquiera" in cond:
        return any(evaluar(c, ctx, listas) for c in cond["cualquiera"])
    if "no" in cond:
        return not evaluar(cond["no"], ctx, listas)
    for cuant in CUANTIFICADORES:
        if cuant in cond:
            raiz = cond.get("sobre", "material")
            items = (listas or {}).get(raiz) or []
            prueba = cond[cuant]
            f = any if cuant == "alguno" else all
            return f(evaluar(prueba, dict(ctx, **{raiz: it}), listas) for it in items)
    return _simple(cond, ctx)


def validar(cond, raices: Sequence[str], donde: str = "") -> None:
    """Revisa la forma de una condición AL CARGAR los datos. Que un JSON mal escrito falle al abrir el mundo
    y no tres horas después, en mitad de una partida."""
    if cond is None:
        return
    if isinstance(cond, list):
        for c in cond:
            validar(c, raices, donde)
        return
    if not isinstance(cond, dict):
        raise ErrorDeCondicion("%s: condición inválida (%r)." % (donde, cond))
    for k in COMBINADORES:
        if k in cond:
            hijos = cond[k] if k != "no" else [cond[k]]
            for c in hijos:
                validar(c, raices, donde)
            return
    for k in CUANTIFICADORES:
        if k in cond:
            raiz = cond.get("sobre", "material")
            if raiz not in raices:
                raise ErrorDeCondicion("%s: «%s» no es una raíz válida (%s)." % (donde, raiz, sorted(raices)))
            validar(cond[k], raices, donde)
            return
    if "path" not in cond or "op" not in cond:
        raise ErrorDeCondicion("%s: una condición necesita «path» y «op»." % donde)
    if cond["op"] not in OPERADORES:
        raise ErrorDeCondicion("%s: operador «%s» desconocido (%s)." % (donde, cond["op"], sorted(OPERADORES)))
    raiz = str(cond["path"]).split(".", 1)[0]
    if raiz not in raices:
        raise ErrorDeCondicion("%s: «%s» no es una raíz válida (%s)." % (donde, raiz, sorted(raices)))
    v = cond.get("valor")
    if isinstance(v, str) and v.startswith("@"):
        r2 = v[1:].split(".", 1)[0]
        if r2 not in raices:
            raise ErrorDeCondicion("%s: la referencia «%s» no es una raíz válida." % (donde, v))
    if cond["op"] == "entre" and not (isinstance(v, (list, tuple)) and len(v) == 2):
        raise ErrorDeCondicion("%s: «entre» necesita [mínimo, máximo]." % donde)

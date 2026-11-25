"""
Catálogos editables en JSON: especies de animales y recetas existentes.

Se cargan de `datos_base/<tipo>/*.json`. Para agregar o cambiar cosas SIN tocar el código, poné archivos en
`datos/extra/<tipo>/*.json` (o en la carpeta que indique la variable MUNDO_VIVO_EXTRA): mismo `id` = reemplaza,
`id` nuevo = agrega. Cada archivo es una lista de objetos con "type" e "id". Se validan al cargar y un error dice
qué archivo y qué entrada está mal.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

RAIZ = Path(__file__).resolve().parents[2] / "datos_base"


def dir_extra() -> Path:
    return Path(os.environ.get("MUNDO_VIVO_EXTRA", "datos/extra"))


class ErrorDeCatalogo(ValueError):
    pass


def _leer(carpeta: Path, tipo: str, out: Dict[str, dict]) -> None:
    """Lee una carpeta de catálogo. DOS archivos de la MISMA carpeta no pueden declarar el mismo id: el
    último alfabético ganaba en silencio y la entrada del otro archivo no existía para nadie. (Pasó de
    verdad: un `pico_de_piedra` nuevo en `metalurgia.json` lo tapaba el de `recetas.json`, así que el pico
    no servía para romper roca y nada lo decía.) Reemplazar desde `datos/extra/` sigue andando: eso es
    otra carpeta y otra llamada a esta función."""
    if not carpeta.is_dir():
        return
    de_donde: Dict[str, str] = {}
    for f in sorted(carpeta.glob("*.json")):
        try:
            datos = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            raise ErrorDeCatalogo("%s: JSON inválido (%s)" % (f.name, e))
        if not isinstance(datos, list):
            raise ErrorDeCatalogo("%s: debe contener una lista." % f.name)
        for d in datos:
            if not isinstance(d, dict) or d.get("type") != tipo or not d.get("id"):
                raise ErrorDeCatalogo("%s: cada entrada necesita type='%s' e id." % (f.name, tipo))
            d["_archivo"] = f.name
            iid = str(d["id"])
            if iid in de_donde:
                raise ErrorDeCatalogo("%s: el id '%s' ya está declarado en %s (mismo tipo '%s'). Un id, un "
                                      "solo lugar." % (f.name, iid, de_donde[iid], tipo))
            de_donde[iid] = f.name
            out[iid] = d


def cargar(carpeta: str, tipo: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    _leer(RAIZ / carpeta, tipo, out)
    _leer(dir_extra() / carpeta, tipo, out)
    return out


MEDIOS = {"tierra", "agua", "aire"}
DIETAS = {"herbivoro", "carnivoro", "omnivoro", "insectivoro", "carronero", "filtrador"}
AGRESIVO = {"no", "si_provocado", "siempre"}


def cargar_especies(claves_habitat: set) -> Dict[str, dict]:
    # Desde la fase A las especies salen del registro, que resuelve `copy-from` y saltea las plantillas.
    # Sin esto una variante (`lobo_blanco` que hereda de `lobo`) no tendría ni medio ni dieta y no validaría.
    from .registro import Registro
    esp = {i: dict(d) for i, d in Registro.cargar().de_tipo("especie").items()}
    for i, d in esp.items():
        donde = "%s: especie '%s'" % (d["_archivo"], i)
        if d.get("medio") not in MEDIOS:
            raise ErrorDeCatalogo("%s: medio inválido (%s)." % (donde, sorted(MEDIOS)))
        if d.get("dieta") not in DIETAS:
            raise ErrorDeCatalogo("%s: dieta inválida (%s)." % (donde, sorted(DIETAS)))
        if d.get("agresivo", "no") not in AGRESIVO:
            raise ErrorDeCatalogo("%s: 'agresivo' debe ser %s." % (donde, sorted(AGRESIVO)))
        bad = [b for b in d.get("biomas", []) if b not in claves_habitat]
        if not d.get("biomas") or bad:
            raise ErrorDeCatalogo("%s: biomas desconocidos %s (válidos: %s)." % (donde, bad, sorted(claves_habitat)))
        for p in d.get("presas", []):
            if p not in esp:
                raise ErrorDeCatalogo("%s: presa desconocida '%s'." % (donde, p))
        for k in ("nombre", "peso_kg", "velocidad", "densidad", "vida_dias"):
            if k not in d:
                raise ErrorDeCatalogo("%s: falta '%s'." % (donde, k))
        d.setdefault("peligro", 0); d.setdefault("agresivo", "no"); d.setdefault("ayuno_dias", 2)
        d.setdefault("drops", {}); d.setdefault("emoji", "🐾"); d.setdefault("montable", False); d.setdefault("veneno", False)
        d.setdefault("presas", []); d.setdefault("vertebrado", True); d.setdefault("clase", "animal")
        # temperatura mínima que aguanta (°C). Se puede fijar en el JSON con "frio_min"; si no, se deduce de la clase y del hábitat.
        if "frio_min" not in d:
            frios = [b for b in d.get("biomas", []) if b in ("tundra", "nieve", "bosque_frio", "montana")]
            frac = len(frios) / max(1, len(d.get("biomas", [])))
            d["frio_min"] = (-40.0 if frac >= 0.5 else -22.0 if frios
                             else {"reptil": 0.0, "anfibio": 0.0, "insecto": -2.0, "aracnido": -2.0}.get(d["clase"], -14.0))
    return esp


TIEMPO_CATEGORIA = {"fuego": 20, "herramienta": 40, "caza": 60, "textil": 45, "ropa": 70, "recipiente": 45, "comida": 25,
                    "salud": 15, "transporte": 240, "refugio": 300, "metal": 60}


def cargar_etiquetas() -> Dict[str, set]:
    """Etiquetas como los tags de Minecraft: '#lena' vale por cualquier material de la lista."""
    return {i: set(d.get("valores", [])) for i, d in cargar("etiquetas", "etiqueta").items()}


def _validar_estructuras(rec: Dict[str, dict], estructuras: Dict[str, dict]) -> None:
    """Que una estructura declarada sea una estructura ALCANZABLE, y que lo que pide calor exista.

    El agujero que esto cierra: el horno (1000 °C) y la fragua (1500 °C) vivieron meses declarados y
    leídos por `calor_disponible()` sin ninguna receta que los levantara, así que el techo real de calor
    del mundo era 600 °C y la metalurgia era inalcanzable. Tres reglas, todas de datos:

      A. toda estructura que `provee` algo tiene que llegar al mundo de alguna forma: una receta con EL
         MISMO id, un bloque `natural`, o `provisto_por: "motor"` (la fogata y el incendio los crea el
         motor, no una receta);
      B. si hay una estructura con ese id, la receta tiene que traer el campo `estructura`: sin él
         `_accion_fabricar` entrega un ÍTEM de inventario y nunca levanta nada (era el caso del horno);
      C. ninguna receta puede pedir más calor del que da la estructura más caliente que se pueda tener.
    """
    for eid, e in sorted(estructuras.items()):
        if not (e.get("provee") or {}):
            continue
        donde = "%s: estructura '%s'" % (e.get("_archivo", "?"), eid)
        if e.get("provisto_por") == "motor" or e.get("natural"):
            continue
        r = rec.get(eid)
        if r is None:
            raise ErrorDeCatalogo(
                "%s: provee %s pero no hay forma de tenerla. Hace falta una receta con id '%s', un bloque "
                "'natural', o 'provisto_por': 'motor'." % (donde, sorted(e["provee"]), eid))
        if not r.get("estructura"):
            raise ErrorDeCatalogo(
                "%s: la receta '%s' existe pero le falta el campo 'estructura', así que fabricarla da un "
                "ítem y no levanta nada." % (donde, eid))
    techo = max([0.0] + [float((e.get("provee") or {}).get("calor_C", 0))
                         for eid, e in estructuras.items()
                         if e.get("provisto_por") == "motor" or e.get("natural") or eid in rec])
    for i, d in sorted(rec.items()):
        pedido = (d.get("requiere") or {}).get("calor_C", 400 if d.get("requiere_fuego") else 0)
        if isinstance(pedido, str):
            continue           # «@mena»: lo que pida el material que se use. Se chequea al fabricar.
        pide = float(pedido)
        if pide > techo:
            raise ErrorDeCatalogo(
                "%s: receta '%s' pide %g °C y lo más caliente que se puede construir da %g °C: nadie la "
                "podría hacer nunca." % (d.get("_archivo", "?"), i, pide, techo))


def cargar_recetas(materiales: dict, propiedades: dict, estructuras: Optional[dict] = None) -> Dict[str, dict]:
    rec = cargar("recetas", "receta")
    etiquetas = cargar_etiquetas()
    for i, d in rec.items():
        donde = "%s: receta '%s'" % (d["_archivo"], i)
        if not d.get("nombre") or not d.get("ingredientes"):
            raise ErrorDeCatalogo("%s: necesita 'nombre' e 'ingredientes'." % donde)
        for m in d["ingredientes"]:
            if m.startswith("#"):
                if m[1:] not in etiquetas:
                    raise ErrorDeCatalogo("%s: la etiqueta '%s' no existe." % (donde, m))
                if any(x not in materiales for x in etiquetas[m[1:]]):
                    raise ErrorDeCatalogo("%s: la etiqueta '%s' lista un material inexistente." % (donde, m))
            elif m not in materiales:
                raise ErrorDeCatalogo("%s: el material '%s' no existe." % (donde, m))
        if d.get("propiedad") not in propiedades:
            raise ErrorDeCatalogo("%s: propiedad '%s' no se puede comprobar (válidas: %s)." % (donde, d.get("propiedad"), sorted(propiedades)))
        d.setdefault("categoria", "otros"); d.setdefault("descripcion", "")
        # campos al estilo Minecraft (opcionales): tiempo de hacerla, qué entrega, herramienta y si pide fuego
        d.setdefault("tiempo_min", TIEMPO_CATEGORIA.get(d["categoria"], 20))
        d.setdefault("resultado", {"item": i, "cantidad": 1})
        d.setdefault("herramienta", [])
        d.setdefault("requiere_fuego", False)
    if estructuras is None:                 # quien no la tenga compilada (la API, los tests) la lee del registro
        from .registro import Registro
        estructuras = Registro.cargar().de_tipo("estructura")
    _validar_estructuras(rec, estructuras)
    return rec


def buscar_receta(recetas: Dict[str, dict], materiales: List[str], propiedad: str):
    """La receta del catálogo que coincide con lo que se probó (mismos materiales y misma propiedad).
    Primero la coincidencia exacta; si no, las que usan etiquetas ('#lena' acepta cualquier leña)."""
    clave = set(materiales)
    for d in recetas.values():
        if d["propiedad"] == propiedad and set(d["ingredientes"]) == clave:
            return d
    etiquetas = None
    for d in recetas.values():
        if d["propiedad"] != propiedad or not any(m.startswith("#") for m in d["ingredientes"]):
            continue
        etiquetas = etiquetas or cargar_etiquetas()
        if len(d["ingredientes"]) != len(materiales):
            continue
        libres = list(materiales)
        ok = True
        for ing in d["ingredientes"]:
            valido = etiquetas[ing[1:]] if ing.startswith("#") else {ing}
            hit = next((m for m in libres if m in valido), None)
            if hit is None:
                ok = False
                break
            libres.remove(hit)
        if ok:
            return d
    return None

"""
Conocimientos descubiertos: un habitante PROPONE una receta y el motor la VALIDA contra las reglas de materiales.

Sin esta validación el modelo de lenguaje inventaría magia. Solo se aceptan propiedades que se pueden comprobar con los
datos de `datos_base/reglas/materiales.json`.

Las propiedades comprobables ya no son código: son datos (`datos_base/propiedades/propiedades.json`, tipo
«propiedad»), con su descripción, su mensaje de error y una condición declarativa que se evalúa con
`condiciones.evaluar` sobre la lista de materiales. Agregar una propiedad nueva es agregar una entrada JSON
—también desde `datos/extra/`— sin tocar el motor.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .. import condiciones
from ..registro import Registro, registrar_validador
from ..reglas import Reglas

RAICES = ("material",)      # las condiciones de una propiedad solo hablan de materiales

_tabla: Dict[str, dict] = {}        # id -> {descripcion, error, requiere}


@registrar_validador("propiedad")
def _validar_propiedad(d: dict, _reg: Registro) -> None:
    """Un JSON mal escrito tiene que fallar al abrir el mundo, no en mitad de una partida."""
    donde = "%s: propiedad «%s»" % (d.get("_archivo", "?"), d.get("id"))
    for campo in ("descripcion", "error"):
        if not d.get(campo):
            raise condiciones.ErrorDeCondicion("%s: falta «%s»." % (donde, campo))
    condiciones.validar(d.get("requiere"), RAICES, donde)


def _cargar() -> Dict[str, dict]:
    """Lee las propiedades del registro una sola vez por proceso (no se tocan en el bucle de 20 Hz)."""
    if not _tabla:
        reg = Registro.cargar()
        reg.validar(["propiedad"])
        for pid, d in reg.de_tipo("propiedad").items():
            _tabla[pid] = {"descripcion": d.get("descripcion", ""), "error": d.get("error", ""),
                           "requiere": d.get("requiere")}
    return _tabla


# id -> descripción. Lo usan `agentes/mente.py` (para el prompt), `catalogos.py` y la API.
PROPIEDADES: Dict[str, str] = {k: v["descripcion"] for k, v in _cargar().items()}


def validar(reglas: Reglas, nombre: str, materiales: List[str], propiedad: str) -> Tuple[bool, str]:
    nombre = (nombre or "").strip()
    if not (2 <= len(nombre) <= 40):
        return False, "El nombre debe tener entre 2 y 40 letras."
    if not materiales or len(materiales) > 5:
        return False, "Hay que usar entre 1 y 5 materiales."
    mats = []
    for m in materiales:
        if m not in reglas.materiales:
            return False, "No existe el material '%s' en este mundo." % m
        mats.append(reglas.materiales[m])
    if propiedad not in PROPIEDADES:
        return False, "Eso todavía no se puede comprobar en este mundo (se puede comprobar: %s)." % ", ".join(PROPIEDADES)
    regla = _cargar()[propiedad]
    if not condiciones.evaluar(regla["requiere"], {}, {"material": mats}):
        return False, regla["error"]
    return True, "Comprobado: " + PROPIEDADES[propiedad] + "."

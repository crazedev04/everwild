"""
Registro de contenido: todo lo que el mundo "tiene" sale de acá, no del código.

Idea tomada de Factorio (el motor no trae contenido propio: todo es una entrada de datos y lo que agrega un
paquete se trata igual que lo original), Minecraft (ids con espacio de nombres y etiquetas), RimWorld (herencia
encadenable para no copiar y pegar) y Dwarf Fortress (un archivo por tipo de cosa).

Cómo se carga
  1. Se leen todos los `.json` de `datos_base/` y después los de `datos/extra/` (o `MUNDO_VIVO_EXTRA`).
  2. El tipo lo decide el campo `type` de cada entrada, NO la carpeta: así la estructura de carpetas es
     cosmética y los archivos que ya existen siguen funcionando donde están.
  3. Mismo id = reemplaza. Id nuevo = agrega.
  4. Se resuelve la herencia (`copy-from`), con detección de ciclos.
  5. Se valida en DOS pasadas: primero se registran todos los ids, después se revisan las referencias cruzadas.
     Así deja de importar en qué archivo está definida cada cosa.

Espacio de nombres
  `piedra` y `mundo:piedra` son lo mismo (el prefijo `mundo` es el contenido propio). Un paquete de terceros
  usa `supaquete:cosa` y queda a salvo de choques de nombres. No hace falta migrar nada de lo existente.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

RAIZ_DATOS = Path(__file__).resolve().parents[2] / "datos_base"
PROPIO = "mundo"                 # espacio de nombres del contenido que viene con el juego
RESERVADAS = {"type", "id", "copy-from", "abstracto", "_archivo", "_paquete"}


class ErrorDeRegistro(ValueError):
    pass


def dir_extra() -> Path:
    import os
    return Path(os.environ.get("MUNDO_VIVO_EXTRA", "datos/extra"))


def clave(id_: str) -> str:
    """Id tal como lo usa el motor. `mundo:piedra` -> `piedra`; `otro:cosa` se queda con el prefijo."""
    s = str(id_).strip()
    if ":" in s:
        esp, resto = s.split(":", 1)
        return resto if esp == PROPIO else s
    return s


class Registro:
    def __init__(self) -> None:
        self._crudos: Dict[str, Dict[str, dict]] = {}     # tipo -> id -> entrada sin resolver
        self._listo: Dict[str, Dict[str, dict]] = {}      # tipo -> id -> entrada resuelta (sin abstractos)
        self.huella = ""

    # ------------------------------------------------------------------ carga
    @staticmethod
    def cargar(*paquetes: Path) -> "Registro":
        r = Registro()
        h = hashlib.sha256()
        for paq in (paquetes or (RAIZ_DATOS, dir_extra())):
            paq = Path(paq)
            if not paq.is_dir():
                continue
            for f in sorted(paq.rglob("*.json")):
                texto = f.read_text(encoding="utf-8")
                h.update(str(f.relative_to(paq)).encode() + texto.encode())
                r._leer(f, texto, paq.name)
        r.huella = h.hexdigest()[:16]
        r._resolver_todo()
        return r

    def _leer(self, f: Path, texto: str, paquete: str) -> None:
        try:
            datos = json.loads(texto)
        except ValueError as e:
            raise ErrorDeRegistro("%s: JSON inválido (%s)" % (f.name, e))
        if not isinstance(datos, list):
            raise ErrorDeRegistro("%s: debe contener una lista de entradas." % f.name)
        for d in datos:
            if not isinstance(d, dict) or not d.get("type") or not d.get("id"):
                raise ErrorDeRegistro("%s: cada entrada necesita «type» e «id»." % f.name)
            d = dict(d)
            d["_archivo"], d["_paquete"] = f.name, paquete
            self._crudos.setdefault(str(d["type"]), {})[clave(d["id"])] = d

    # -------------------------------------------------------------- herencia
    def _resolver(self, tipo: str, id_: str, pila: List[str]) -> dict:
        if id_ in pila:
            raise ErrorDeRegistro("Herencia circular en %s: %s" % (tipo, " -> ".join(pila + [id_])))
        crudo = self._crudos[tipo][id_]
        base: dict = {}
        padre = crudo.get("copy-from")
        if padre:
            pk = clave(padre)
            if pk not in self._crudos.get(tipo, {}):
                raise ErrorDeRegistro("%s: «%s» hereda de «%s», que no existe."
                                      % (crudo["_archivo"], id_, padre))
            base = dict(self._resolver(tipo, pk, pila + [id_]))
            base.pop("abstracto", None)        # ser plantilla no se hereda
        base.update({k: v for k, v in crudo.items() if k != "copy-from"})
        base["id"] = id_
        return base

    def _resolver_todo(self) -> None:
        for tipo, entradas in self._crudos.items():
            resueltas = {i: self._resolver(tipo, i, []) for i in entradas}
            # las plantillas (`abstracto: true`) sirven para heredar, pero no existen en el mundo
            self._listo[tipo] = {i: d for i, d in resueltas.items() if not d.get("abstracto")}

    # ------------------------------------------------------------- consultas
    def de_tipo(self, tipo: str) -> Dict[str, dict]:
        return self._listo.get(tipo, {})

    def uno(self, tipo: str, id_: str) -> Optional[dict]:
        return self._listo.get(tipo, {}).get(clave(id_))

    def tipos(self) -> List[str]:
        return sorted(self._listo)

    def agregar(self, tipo: str, entradas: Dict[str, dict]) -> None:
        """Mete contenido que no salió de ningún archivo: lo que GENERA un mundo (ver
        `motor/minerales.py`). Ya viene resuelto (sin `copy-from` que resolver), así que entra directo en
        la tabla de lo listo. Es de ese mundo y nunca se escribe a `datos_base/`."""
        resueltas = {clave(i): d for i, d in entradas.items()}
        self._listo.setdefault(tipo, {}).update(resueltas)
        self._crudos.setdefault(tipo, {}).update(resueltas)

    def etiqueta(self, nombre: str) -> set:
        """Los ids de una etiqueta. Acepta «#lena», «lena» y «mundo:lena»."""
        e = self.uno("etiqueta", str(nombre).lstrip("#"))
        return {clave(v) for v in (e.get("valores") or [])} if e else set()

    def ids(self, selector) -> set:
        """Resuelve un id, una etiqueta («#lena») o una lista de ambos a un conjunto de ids."""
        if selector is None:
            return set()
        if isinstance(selector, str):
            selector = [selector]
        out: set = set()
        for s in selector:
            s = str(s)
            out |= self.etiqueta(s) if s.startswith("#") else {clave(s)}
        return out

    # ------------------------------------------------------------ validación
    VALIDADORES: Dict[str, Callable[[dict, "Registro"], None]] = {}

    def validar(self, tipos: Optional[Sequence[str]] = None) -> None:
        """Segunda pasada: con todo ya registrado, se revisan las referencias cruzadas."""
        for tipo in (tipos or self._listo):
            f = self.VALIDADORES.get(tipo)
            if f is None:
                continue
            for d in self._listo.get(tipo, {}).values():
                f(d, self)


def registrar_validador(tipo: str):
    """Agregar un tipo de contenido nuevo es agregar una función y decorarla: el motor no cambia."""
    def deco(f):
        Registro.VALIDADORES[tipo] = f
        return f
    return deco

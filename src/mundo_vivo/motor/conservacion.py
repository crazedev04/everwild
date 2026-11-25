"""Conservación de alimentos y materiales: lo fresco se pudre, lo cocinado y lo curado dura más, el cuero casi no.

Cada ítem del inventario es un lote con una edad media (`h.inv_t`, minutos). Se actualiza cada hora de juego, no en cada paso
(coste ínfimo aun con mucha gente). Datos en `datos_base/reglas/conservacion.json` si existe, si no estos valores."""
from __future__ import annotations

from typing import Tuple

# Cuánto dura cada cosa y en qué se convierte al cocinarla son DATOS: `conservacion` y `cocina` de cada
# material o ítem (datos_base/). El motor no conoce ningún alimento por su nombre.
_VIDA_MIN: dict = {}        # item -> minutos hasta pudrirse (None = no se pudre). Se llena una vez.
PASO_MIN = 60.0
TOPE_LOTE = 60          # tope por ítem en el inventario (que nadie acumule sin límite)
CURADO_MIN = 180.0
COCINAR_MIN = 25.0


def _tabla_vida() -> dict:
    """Del registro a un diccionario plano, una sola vez. El bucle no toca el registro."""
    if not _VIDA_MIN:
        from ..registro import Registro
        reg = Registro.cargar()
        for col in ("material", "item"):
            for iid, d in reg.de_tipo(col).items():
                c = d.get("conservacion")
                if c and "vida_dias" in c:
                    _VIDA_MIN[iid] = None if c["vida_dias"] is None else float(c["vida_dias"]) * 1440.0
    return _VIDA_MIN


def vida_min(item: str):
    """Minutos hasta que se pudre, o None si no se pudre."""
    return _tabla_vida().get(item)



class ConservacionMixin:
    def _compilar_conservacion(self) -> None:
        """Qué se cocina en qué, y qué abriga. Se arma al crear el mundo, no en el bucle."""
        self.crudos: dict = {}
        self.materiales_abrigo: tuple = ()
        abrigo = []
        for col in ("material", "item"):
            for iid, d in self.registro.de_tipo(col).items():
                coc = d.get("cocina")
                if coc and coc.get("resultado"):
                    self.crudos[iid] = coc["resultado"]
                if d.get("abrigo"):
                    abrigo.append(iid)
        self.materiales_abrigo = tuple(abrigo)

    def _ganar_item(self, h, item: str, cant: int) -> None:
        """Suma al inventario y mezcla la edad del lote (lo nuevo llega fresco)."""
        antes = h.inventario.get(item, 0)
        # cuánto puede cargar depende de su fuerza (ver motor/atributos.py)
        tope = self.carga_maxima(h) if self.modulo("atributos") else TOPE_LOTE
        nuevo = min(tope, antes + cant)
        if nuevo <= 0:
            return
        e = h.inv_t.get(item, 0.0)
        h.inv_t[item] = e * antes / nuevo if antes else 0.0
        h.inventario[item] = nuevo

    def estado_item(self, h, item: str) -> str:
        v = vida_min(item)
        if v is None:
            return ""
        f = h.inv_t.get(item, 0.0) / v
        return "fresco" if f < 0.4 else ("ya no tan fresco" if f < 0.8 else "a punto de pudrirse")

    def _paso_conservacion(self, paso: float) -> None:
        self._acum_cons = getattr(self, "_acum_cons", 0.0) + paso
        if self._acum_cons < PASO_MIN:
            return
        dt, self._acum_cons = self._acum_cons, 0.0
        for h in self.habitantes.values():
            if not h.vivo or not h.inventario:
                continue
            t = self.temp_base_en(h.x, h.y) + 0.0
            k = 1.6 if t > 22 else (0.3 if t < 0 else 1.0)
            for item in list(h.inventario):
                v = vida_min(item)
                if v is None or h.inventario.get(item, 0) <= 0:
                    continue
                h.inv_t[item] = h.inv_t.get(item, 0.0) + dt * k
                if h.inv_t[item] >= v and item == "antorcha_encendida":      # se consumió la llama
                    h.inventario.pop(item, None); h.inv_t.pop(item, None)
                    continue
                if h.inv_t[item] >= v:
                    n = h.inventario.pop(item)
                    h.inv_t.pop(item, None)
                    h.rotos += 1
                    self._ganar_item(h, "podrido", n)
                    self._evento("podrido", "A %s se le pudrieron %d de %s." % (h.nombre, n, item), h, importancia=2,
                                 datos={"item": item, "n": n})
                    self._recuerdo(h, "Se te pudrieron %d de %s por no usarlos a tiempo." % (n, item), 0.7)
                    self._recuerdo(h, "La %s fresca se pudre en pocos días: hay que cocinarla o curarla a tiempo." % item,
                                   0.85, "creencia", "vivido")

    # ------------------------------------------------------------ acciones
    def _accion_cocinar(self, h, it: dict) -> Tuple[bool, str]:
        crudo = next((c for c in self.crudos if h.inventario.get(c, 0) > 0), None)
        if crudo is None:
            return False, "No llevás nada crudo para cocinar."
        if not (self.fogata_cerca(h, self.r_mano) or self.fuego_cerca(h, self.r_mano)):
            return False, "Para cocinar hace falta un fuego cerca."
        n = h.inventario.pop(crudo)
        h.inv_t.pop(crudo, None)
        self._ganar_item(h, self.crudos[crudo], n)
        h.inv_t[self.crudos[crudo]] = 0.0
        h.accion, h.detalle, h.hasta = "cocinando", crudo, self.t + COCINAR_MIN
        self._evento("cocina", "%s cocinó %d de %s al fuego." % (h.nombre, n, crudo), h, importancia=3, datos={"item": crudo, "n": n})
        self._recuerdo(h, "Cocinaste %d de %s al fuego; así dura más." % (n, crudo), 0.6)
        return True, "Cocinaste %d de %s; así dura varios días." % (n, crudo)

    def _accion_curar(self, h, it: dict) -> Tuple[bool, str]:
        crudo = next((c for c in self.crudos if h.inventario.get(c, 0) > 0), None)
        if crudo is None:
            return False, "No llevás nada que curar."
        n = h.inventario.pop(crudo)
        h.inv_t.pop(crudo, None)
        self._ganar_item(h, "carne_curada", n)
        h.inv_t["carne_curada"] = 0.0
        h.accion, h.detalle, h.hasta = "curando", crudo, self.t + CURADO_MIN
        self._evento("cocina", "%s curó %d de %s (secada al aire); dura semanas." % (h.nombre, n, crudo), h, importancia=3,
                     datos={"item": crudo, "n": n, "curado": True})
        self._recuerdo(h, "Curaste %d de %s: secada, dura semanas." % (n, crudo), 0.6)
        return True, "Curaste %d de %s; se conserva semanas." % (n, crudo)

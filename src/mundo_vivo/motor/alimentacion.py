"""
Hambre y alimentos.

Las cuatro barras son INDEPENDIENTES: salud, agua, energía y hambre. Se puede estar perfectamente comido y
con poca energía, o bien alimentado y herido. Cada una tiene su causa y su efecto:

  hambre   sube con el tiempo y con el esfuerzo; baja al comer. Llegando a 100 empieza a sacar salud.
  energía  baja despierto, sube durmiendo. Lo único que la liga al hambre: con hambre alta se repone peor
           (dormir con el estómago vacío no repara del todo). No son la misma barra.
  salud    se regenera sólo si el hambre y la sed están bajas. Lo podrido y las heridas la bajan.
  agua     como siempre.

Cuánto alimenta cada cosa es un DATO (`alimento` de cada material o ítem): crudo, cocinado y podrido pueden
dar distinto, y lo podrido además puede enfermar. El motor no conoce ningún alimento por su nombre.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

# Con esta hambre uno se despierta aunque esté durmiendo. El cerebro usa el MISMO número para no volver a
# dormirse: si se separan, el que duerme se despierta de hambre, se vuelve a dormir y se muere con comida
# encima. Es exactamente la trampa que ya pasó con la sed (ver SED_DESPIERTA en simulacion.py).
HAMBRE_DESPIERTA = 80.0
HAMBRE_MORTAL = 100.0        # desde acá empieza a sacar salud
# Ritmo: ~17 por día quieto, o sea casi 6 días de ayuno hasta el límite. Con 43 por día (el primer número que
# probé) morían el día 3, antes de aprender a conseguir comida: arrancan con el inventario vacío y sin saber cazar.
SUBE_POR_MIN = 0.012
SUBE_CAMINANDO = 0.005       # el esfuerzo da más hambre
COMER_MIN = 10.0


class AlimentacionMixin:
    # ------------------------------------------------------------- datos
    def _compilar_alimentos(self) -> None:
        """De los datos a una tabla plana: item -> {estado: efectos}. Una vez al crear el mundo."""
        self.alimentos: Dict[str, dict] = {}
        for col in ("material", "item"):
            for iid, d in self.registro.de_tipo(col).items():
                if d.get("alimento"):
                    self.alimentos[iid] = d["alimento"]

    def estado_alimento(self, h, item: str) -> Optional[str]:
        """En qué estado está eso que lleva: «podrido», «cocinado» o «crudo». None si no se come."""
        a = self.alimentos.get(item)
        if not a:
            return None
        if item == "podrido" or "podrido" in a and len(a) == 1:
            return "podrido"
        return "cocinado" if "cocinado" in a else "crudo"

    def valor_alimento(self, h, item: str) -> Optional[dict]:
        a = self.alimentos.get(item)
        est = self.estado_alimento(h, item)
        return a.get(est) if a and est else None

    def comestibles(self, h) -> list:
        """Lo que lleva encima y se puede comer, lo que más alimenta primero."""
        out = []
        for item, n in h.inventario.items():
            if n <= 0:
                continue
            v = self.valor_alimento(h, item)
            if v:
                out.append((float(v.get("hambre", 0)), item))
        out.sort(reverse=True)
        return [i for _, i in out]

    # -------------------------------------------------------------- paso
    def _paso_hambre(self, h, paso: float, dormido: bool) -> None:
        if not self.modulo("hambre"):
            return
        esfuerzo = SUBE_CAMINANDO if h.accion in ("caminando", "juntando", "fabricando", "construyendo") else 0.0
        sube = (SUBE_POR_MIN + esfuerzo) * (0.45 if dormido else 1.0)
        h.hambre = min(100.0, h.hambre + sube * paso)
        if h.hambre >= HAMBRE_MORTAL:
            h.salud -= 0.035 * paso         # ~2 días más de agonía: la sed saca 0,3 y mata en horas
            h.sin_regenerar = True
        elif h.hambre >= 70.0:
            h.sin_regenerar = True          # con hambre no se cura solo
        # Dormir con hambre repone peor, pero sólo con hambre DE VERDAD. Con el umbral en 60 estaban siempre
        # penalizados (el hambre se estabiliza en 65-75 cuando se alimentan bien) y morían de agotamiento.
        if dormido and h.hambre >= 85.0:
            h.energia = max(0.0, h.energia - 0.04 * paso)

    # ----------------------------------------------------------- acciones
    def _accion_comer(self, h, it: dict) -> Tuple[bool, str]:
        if not self.modulo("hambre"):
            return False, "Comer no está habilitado."
        pedido = str(it.get("objeto") or it.get("item") or "").strip().lower()
        opciones = self.comestibles(h)
        if not opciones:
            return False, "No llevás nada para comer."
        item = pedido if pedido in opciones else opciones[0]
        v = self.valor_alimento(h, item) or {}
        h.inventario[item] -= 1
        if h.inventario[item] <= 0:
            h.inventario.pop(item, None); h.inv_t.pop(item, None)
        h.hambre = max(0.0, h.hambre - float(v.get("hambre", 0)))
        h.energia = min(100.0, h.energia + float(v.get("energia", 0)))
        h.sed = max(0.0, min(100.0, h.sed - float(v.get("sed", 0))))
        if v.get("salud"):
            h.salud = min(100.0, h.salud + float(v["salud"]))
        h.accion, h.detalle, h.hasta = "comiendo", item, self.t + COMER_MIN
        enfermo = float(v.get("riesgo", 0)) > 0 and self.rng_alimentacion.random() < float(v["riesgo"])
        if enfermo:
            h.salud -= self.rng_alimentacion.uniform(6.0, 16.0)
            self._evento("enfermo", "%s se descompuso por comer %s." % (h.nombre, item), h,
                         causa="comida en mal estado", importancia=3)
            self._recuerdo(h, "Comiste %s y te cayó mal." % item, 0.8, "semantica")
            if h.salud <= 0:
                self._morir(h, "algo que comió")
                return True, "Comiste %s y te cayó muy mal." % item
        efecto = self.aplicar_psicoactivo(h, item)          # algunas plantas mueven la cabeza
        if efecto:
            return True, "Comiste %s y %s." % (item, efecto)
        est = self.estado_alimento(h, item)
        self._recuerdo(h, "Comiste %s%s." % (item, " (estaba podrido)" if est == "podrido" else ""), 0.35)
        return True, "Comiste %s.%s" % (item, " Te cayó mal." if enfermo else "")

"""
Atributos del cuerpo y destreza por oficio: lo que mejora con el uso y se oxida sin él.

Tres atributos (0..1), independientes entre sí y de las cuatro barras:

  fuerza       cargar más, pegar más fuerte, juntar más rápido. Sube cazando, juntando y construyendo.
  resistencia  gastar menos energía y dar menos hambre al moverse. Sube caminando mucho.
  pulso        manos finas: fabricar más rápido y fallar menos. Sube fabricando e inventando.

Y una destreza por receta (0..1) que sube practicando ESA receta y se oxida si no se usa.

Cómo crecen (esto es lo que pidió el usuario: que comer bien sirva para algo más que no morirse):
  - Usar un atributo lo sube un poquito, con rendimientos decrecientes (cuesta más subir de 0,8 que de 0,3).
  - Para subir hace falta estar **alimentado y sano**: con hambre alta o salud baja no se progresa, se oxida.
  - Sin usar, todo baja muy de a poco. Nadie pierde en un día lo que le costó un año.

Los atributos NO se heredan (eso es el genoma). Se construyen viviendo.
"""
from __future__ import annotations

from typing import Dict

ATRIBUTOS = ("fuerza", "resistencia", "pulso")
BASE = 0.30                   # con lo que arranca un adulto sin oficio
TECHO = 1.0
SUBE = 0.0016                 # por uso; con rendimientos decrecientes
OXIDA_POR_DIA = 0.0022        # lo que se pierde por día sin usar
HAMBRE_FRENA = 70.0           # con más hambre que esto no se progresa
SALUD_FRENA = 55.0
DESTREZA_SUBE = 0.045         # por cada vez que se fabrica esa receta
DESTREZA_OXIDA_POR_DIA = 0.0012

# Qué actividad entrena qué. Es mecánica del cuerpo, no contenido: por eso vive acá y no en un JSON.
ENTRENA = {
    "juntando": ("fuerza",),
    "construyendo": ("fuerza", "pulso"),
    "cazando": ("fuerza", "resistencia"),
    "caminando": ("resistencia",),
    "fabricando": ("pulso",),
}


class AtributosMixin:
    # ------------------------------------------------------------ consultas
    def atributo(self, h, nombre: str) -> float:
        return float(h.atributos.get(nombre, BASE))

    def destreza(self, h, receta_id: str) -> float:
        """0..1 en ESA receta. Lo que nunca hizo lo hace con torpeza de principiante."""
        return float(h.destrezas.get(receta_id, 0.0))

    def tiempo_de_receta(self, h, r: dict) -> float:
        """Los minutos que le lleva a ESTA persona. Con pulso y práctica, hasta un 45% menos."""
        base = float(r.get("tiempo_min", 20))
        k = 1.0 - 0.25 * (self.atributo(h, "pulso") - BASE) / (TECHO - BASE) - 0.22 * self.destreza(h, r["id"])
        return max(base * 0.55, base * k)

    def carga_maxima(self, h) -> int:
        """Cuánto puede llevar encima. La fuerza manda."""
        from .conservacion import TOPE_LOTE
        return int(TOPE_LOTE * (0.7 + 0.6 * self.atributo(h, "fuerza")))

    # ------------------------------------------------------------- crecer
    def _progresa(self, h) -> bool:
        """Para mejorar hay que estar comido y entero."""
        if self.modulo("hambre") and h.hambre >= HAMBRE_FRENA:
            return False
        return h.salud >= SALUD_FRENA

    def entrenar(self, h, *nombres: str, veces: float = 1.0) -> None:
        """Sube los atributos nombrados. Rendimientos decrecientes: de 0,9 a 0,95 cuesta mucho más que de 0,3 a 0,4."""
        if not self.modulo("atributos") or not self._progresa(h):
            return
        for n in nombres:
            v = self.atributo(h, n)
            h.atributos[n] = min(TECHO, v + SUBE * veces * (1.0 - v) ** 1.5)

    def practicar(self, h, receta_id: str) -> None:
        if not self.modulo("atributos"):
            return
        v = self.destreza(h, receta_id)
        h.destrezas[receta_id] = min(TECHO, v + DESTREZA_SUBE * (1.0 - v))

    def _paso_atributos(self, h, paso: float) -> None:
        """Entrena por lo que está haciendo y oxida lo que no usa."""
        if not self.modulo("atributos"):
            return
        for n in ENTRENA.get(h.accion, ()):
            self.entrenar(h, n, veces=paso / 20.0)
        dias = paso / 1440.0
        usando = set(ENTRENA.get(h.accion, ()))
        for n in ATRIBUTOS:
            if n in usando:
                continue
            h.atributos[n] = max(BASE * 0.5, self.atributo(h, n) - OXIDA_POR_DIA * dias)
        # La oxidación de las destrezas se acumula y se aplica una vez por día del mundo. Antes usaba
        # `rng.random()` en cada tick: eso consume el generador del mundo y rompe el determinismo de la semilla.
        if h.destrezas:
            h.oxido_t = getattr(h, "oxido_t", 0.0) + paso
            if h.oxido_t >= 1440.0:
                caido = DESTREZA_OXIDA_POR_DIA * (h.oxido_t / 1440.0)
                h.oxido_t = 0.0
                for rid in list(h.destrezas):
                    h.destrezas[rid] = max(0.0, h.destrezas[rid] - caido)
                    if h.destrezas[rid] <= 0.0:
                        h.destrezas.pop(rid, None)

    # --------------------------------------------------------- descripción
    def describir_atributos(self, h) -> str:
        """Para el prompt: la persona siente su cuerpo, no lee números."""
        f, r, p = (self.atributo(h, n) for n in ATRIBUTOS)
        partes = []
        if f >= 0.6:
            partes.append("tenés brazos fuertes de tanto trabajar")
        elif f <= 0.25:
            partes.append("te falta fuerza en los brazos")
        if r >= 0.6:
            partes.append("aguantás caminando todo el día")
        elif r <= 0.25:
            partes.append("te cansás enseguida")
        if p >= 0.6:
            partes.append("tus manos ya saben lo que hacen")
        return "; ".join(partes)

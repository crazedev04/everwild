"""
Frío y nieve: las estaciones y la hora cambian la temperatura, la nieve se acumula donde hiela y se derrite donde entra calor.

  - temperatura de un punto = media del mapa (latitud y altura) + ajuste por estación y hora (ver reloj.ajuste_temp);
  - nieve (0..1 por celda): se acumula con T <= 0 °C (más donde hay humedad) y se derrite con T > 1 °C; frena el paso, apaga fuego
    y evita que un rayo prenda la vegetación;
  - frío sobre las personas: a la intemperie con T bajo 6 °C pierden energía extra y, con frío fuerte, no se recuperan y se
    debilitan. Se mitiga con abrigo (receta «abriga» + cuero, lana, pluma o fibra encima), con resiliencia y buscando un sitio
    más cálido. De día casi nunca es grave: el peligro real es la noche de invierno en zonas altas o frías.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from . import biomas as B
from . import reloj

T_CONFORT = 6.0            # sobre esta temperatura no hay frío que importe
T_EXTREMO = -10.0          # severidad máxima
PASO_NIEVE_MIN = 30.0
# qué abriga es un dato: campo `abrigo` de cada material (ver _compilar_conservacion)


class FrioMixin:
    # ---------------------------------------------------------------- consulta
    def temp_base_en(self, x: float, y: float) -> float:
        t = self.terreno
        return float(t.temperatura[min(t.alto - 1, max(0, int(y))), min(t.ancho - 1, max(0, int(x)))])

    def temp_en(self, x: float, y: float) -> float:
        # Sin estaciones (bajo tierra) la temperatura es la del mapa y nada más: no hay verano ni invierno.
        if not self.cielo.get("estaciones", True):
            return self.temp_base_en(x, y)
        return self.temp_base_en(x, y) + reloj.ajuste_temp(self.t)

    def nieve_en(self, x: float, y: float) -> float:
        return float(self.nieve[min(self.terreno.alto - 1, max(0, int(y))), min(self.terreno.ancho - 1, max(0, int(x)))])

    def abrigo_de(self, h) -> float:
        """0..0.6: cuánto lo protege lo que lleva puesto (necesita saber hacer algo que abrigue Y tener con qué)."""
        sabe = any(self.conocimientos.get(c, {}).get("propiedad") == "abriga" for c in h.conoce)
        n = sum(h.inventario.get(m, 0) for m in self.materiales_abrigo) if sabe else 0
        crudo = min(0.6, 0.25 + 0.1 * n) if n > 0 else 0.0
        return min(0.6, max(crudo, 0.0) + self.abrigo_objetos(h))

    def severidad_frio(self, h) -> float:
        """0 (sin frío) .. ~1.3 (frío extremo y sin protección), ya descontado el abrigo y la resiliencia."""
        T = self.temp_en(h.x, h.y)
        sev = max(0.0, min(1.0, (T_CONFORT - T) / (T_CONFORT - T_EXTREMO)))
        if sev <= 0.0:
            return 0.0
        return sev * (1.0 - self.abrigo_de(h)) * (1.3 - 0.5 * h.rasgo("resiliencia")) * self.calor_de_estructuras(h)

    # ------------------------------------------------------------------- nieve
    def _paso_nieve(self, dt: float) -> None:
        """Acumula y derrite nieve. Corre cada `PASO_NIEVE_MIN` minutos del mundo.

        Mismo cuidado que `Fuego.paso`: cada operación acá toca los 4,2 millones de celdas de un
        mapa de 2048², así que antes de recorrer el mapa hay que saber si hace falta. Lo único que
        cambia con el tiempo es el escalar de `reloj.ajuste_temp`, así que con el mínimo y el máximo
        del mapa alcanza para descartar la pasada entera: en un mapa templado, donde nunca baja de
        cero, no nieva nunca y no hay nada que derretir.

        Los dos extremos se calculan en vivo y NO se guardan. Son dos reducciones sobre un array de
        int8, del orden del milisegundo, y esto corre una vez cada media hora del mundo. Guardarlos
        ahorraría eso y a cambio dejaría que escribir en `terreno.temperatura` no tuviera efecto,
        que es la trampa de `Terreno.costo` contra `Terreno._c`.
        """
        self._acum_nieve += dt
        if self._acum_nieve < PASO_NIEVE_MIN:
            return
        ajuste = reloj.ajuste_temp(self.t)
        temp = self.terreno.temperatura
        puede_nevar = float(temp.min()) + ajuste <= 0.0
        puede_derretir = self._hay_nieve and float(temp.max()) + ajuste > 1.0
        if not puede_nevar and not puede_derretir:
            self._acum_nieve = 0.0      # no se acumula deuda: no había nada que hacer
            return
        pasos, self._acum_nieve = self._acum_nieve / PASO_NIEVE_MIN, 0.0
        T = temp.astype(np.float32) + ajuste
        if puede_nevar:
            cae = (T <= 0.0) & self._suelo_nevable
            if cae.any():
                self.nieve[cae] += 0.010 * pasos * self._hum_nieve[cae]
                self._hay_nieve = True
        if puede_derretir:
            derrite = (T > 1.0) & (self.nieve > 0)
            self.nieve[derrite] -= 0.0025 * pasos * T[derrite]
        np.clip(self.nieve, 0.0, 1.0, out=self.nieve)
        maximo = float(self.nieve.max())
        self._hay_nieve = maximo > 0.0
        if maximo > 0.35 and self.fuego._hubo_fuego:       # la nieve apaga el fuego
            m = (self.nieve > 0.35) & (self.fuego.fuego > 0)
            if m.any():
                self.fuego.fuego[m] = 0

    def nieve_bytes(self) -> bytes:
        return np.clip(self.nieve * 255, 0, 255).astype(np.uint8).tobytes()

    def importar_nieve(self, datos: bytes) -> None:
        a = np.frombuffer(datos, dtype=np.uint8)
        if a.size == self.nieve.size:
            self.nieve = (a.reshape(self.nieve.shape).astype(np.float32) / 255.0).copy()
            # Un mundo guardado puede traer nieve de antes: sin esto, `_paso_nieve` creería que no
            # hay nada que derretir y la nieve del invierno pasado no se iría nunca.
            self._hay_nieve = bool(self.nieve.any())

    # ------------------------------------------------------------- sobre personas
    def _aplicar_frio(self, h, paso: float, dormido: bool) -> None:
        sev = self.severidad_frio(h)
        h.frio = sev
        if sev <= 0.0:
            return
        h.energia = max(0.0, h.energia - 0.03 * sev * paso)
        if sev > 0.4:
            h.salud -= 0.02 * min(1.0, (sev - 0.4) / 0.6) * paso * (1.2 if dormido else 1.0)
            h.sin_regenerar = True
            if not h.avisado_frio and sev > 0.6:
                h.avisado_frio = True
                self._evento("frio", "%s está pasando mucho frío (%d °C)." % (h.nombre, round(self.temp_en(h.x, h.y))), h, importancia=3,
                             causa="temperatura baja y poco abrigo")
                self._recuerdo(h, "Pasaste mucho frío a la intemperie.", 0.7)
                self.sentir(h, "miedo", 0.2)
        if sev < 0.3:
            h.avisado_frio = False

    def buscar_calor(self, h) -> Optional[tuple]:
        """Una celda caminable cercana más cálida (más baja o más al sur), si vale la pena ir."""
        T0 = self.temp_base_en(h.x, h.y)
        mejor, mt = None, T0 + 2.5
        for _ in range(16):
            d = self.rng.randint(8, 24)
            a = self.rng.random() * 2 * math.pi
            c = self.terreno.caminable_cerca(int(h.x + math.cos(a) * d), int(h.y + math.sin(a) * d), 3)
            if c and self.terreno.humedad.shape[0] > c[1]:
                t = self.temp_base_en(c[0], c[1])
                if t > mt:
                    mejor, mt = c, t
        return mejor

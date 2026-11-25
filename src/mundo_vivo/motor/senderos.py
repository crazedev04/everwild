"""Desgaste del suelo: el paso repetido deja huella y el camino hecho se vuelve a usar.

Es la fase 5 del plan del motor, la más invasiva, y por eso va última. Lo que la hace delicada no es la
idea —contar pisadas— sino tres detalles del motor que hay que respetar:

1. **`Terreno` congela una copia del costo.** `self.costo` es el array de numpy y `self._c = costo.tolist()`
   es la lista que usa el A*. Cambiar una celda tiene que escribir en LAS DOS, o el A* sigue viendo el
   mapa viejo para siempre.
2. **Los caminos en curso quedan viejos.** Si una celda cambia de costo, la gente que ya venía con un
   `h.camino` calculado contra el mapa anterior sigue ese trazado. Se les invalida (sólo a los que pasan
   cerca del cambio: invalidarle el camino a todo el mundo sería peor que el problema).
3. **Nada de tocar el costo celda por celda por tick.** Las pisadas se acumulan en un diccionario disperso
   y se vuelcan cada tantos minutos simulados, igual que hace `_paso_tecnologia`.

El sendero es un BIOMA (`sendero_tierra`, en `datos_base/biomas/`), así que la UI lo dibuja gratis y su
velocidad sale del JSON como la de cualquier otro. Y si nadie vuelve a pasar, el desgaste se desvanece y
el sendero se cierra: el mapa recuerda lo que la gente usa, no lo que hizo una vez.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from . import biomas as B

MIN_DIA = 1440.0
VUELCA_CADA_MIN = 30.0          # cada cuánto se pasan las pisadas acumuladas al mapa
PISADAS_SENDERO = 60            # pisadas para que una celda se abra como sendero
TOPE_DESGASTE = 200             # no se sigue contando más allá: una autopista no existe todavía
DIAS_CERRAR = 60.0              # sin tránsito, el desgaste baja y a la larga el sendero se cierra
POR_DIA = 2                     # cuánto se desvanece por día sin que pase nadie
ID_SENDERO = "sendero_tierra"


class SenderosMixin:
    def _compilar_senderos(self) -> None:
        """El bioma del sendero y el array de pisadas. Una vez por mundo, nunca en el bucle."""
        d = self.registro.uno("bioma", ID_SENDERO) or {}
        self.bioma_sendero = int(d["id_numerico"]) if d.get("id_numerico") is not None else None
        self.desgaste = np.zeros((self.terreno.alto, self.terreno.ancho), dtype=np.uint8)
        self._pisadas: Dict[Tuple[int, int], int] = {}
        self._bioma_previo: Dict[Tuple[int, int], int] = {}   # qué había antes del sendero, para cerrarlo
        self._acum_sendero = 0.0
        self._senderos_t = None

    # --------------------------------------------------------------- pisadas
    def pisar(self, x: float, y: float) -> None:
        """Alguien pasó por acá. Barato a propósito: esto se llama en cada paso de cada persona."""
        if self.bioma_sendero is None:
            return
        k = (int(x), int(y))
        n = self._pisadas.get(k, 0)
        if n < 255:
            self._pisadas[k] = n + 1

    def _paso_senderos(self, paso: float) -> None:
        self._acum_sendero = getattr(self, "_acum_sendero", 0.0) + paso
        if self._acum_sendero < VUELCA_CADA_MIN:
            return
        self._acum_sendero = 0.0
        self._volcar_pisadas()
        self._desvanecer()

    def _volcar_pisadas(self) -> None:
        """Del diccionario disperso al mapa, y las celdas que cruzaron el umbral se abren como sendero."""
        if not self._pisadas:
            return
        pisadas, self._pisadas = self._pisadas, {}
        abiertas = []
        for (x, y), n in pisadas.items():
            if not self.terreno.dentro(x, y) or not self.terreno.caminable(x, y):
                continue
            if int(self.terreno.bioma[y, x]) == self.bioma_sendero:
                self.desgaste[y, x] = min(TOPE_DESGASTE, int(self.desgaste[y, x]) + n)
                continue
            v = min(TOPE_DESGASTE, int(self.desgaste[y, x]) + n)
            self.desgaste[y, x] = v
            if v >= PISADAS_SENDERO:
                abiertas.append((x, y))
        for x, y in abiertas:
            self._abrir_sendero(x, y)

    def _desvanecer(self) -> None:
        """Lo que nadie camina se cierra. Una vez por día simulado y vectorizado: el array entero de un
        saque, no celda por celda."""
        if self._senderos_t is None:
            self._senderos_t = self.t
            return
        dias = (self.t - self._senderos_t) / MIN_DIA
        if dias < 1.0:
            return
        self._senderos_t = self.t
        baja = int(max(1, round(POR_DIA * dias)))
        activas = self.desgaste > 0
        if not activas.any():
            return
        self.desgaste[activas] = np.maximum(0, self.desgaste[activas].astype(np.int16) - baja).astype(np.uint8)
        # las que bajaron de la mitad del umbral y son sendero vuelven a lo que eran
        if self._bioma_previo:
            umbral = PISADAS_SENDERO // 2
            for (x, y) in [k for k, _ in self._bioma_previo.items()
                           if int(self.desgaste[k[1], k[0]]) < umbral]:
                self._cerrar_sendero(x, y)

    # --------------------------------------------------------------- el mapa
    def _abrir_sendero(self, x: int, y: int) -> None:
        self._bioma_previo[(x, y)] = int(self.terreno.bioma[y, x])
        self.terreno.cambiar_bioma(x, y, self.bioma_sendero)
        self._invalidar_caminos(x, y)
        if len(self._bioma_previo) == 1:
            self._hito("senderos", None, "los primeros caminos: el paso repetido abrió una huella en el suelo.")

    def _cerrar_sendero(self, x: int, y: int) -> None:
        antes = self._bioma_previo.pop((x, y), None)
        if antes is None:
            return
        self.terreno.cambiar_bioma(x, y, antes)
        self._invalidar_caminos(x, y)

    def _invalidar_caminos(self, x: int, y: int) -> None:
        """A quien venía caminando cerca de esta celda se le descarta la ruta: la calculó contra el mapa
        viejo. Sólo a quien pasa cerca, no a todo el mundo."""
        cerca = self.celdas(300.0)
        for h in self.habitantes.values():
            if h.vivo and h.camino and abs(h.x - x) <= cerca and abs(h.y - y) <= cerca:
                h.camino = []

    # ------------------------------------------------------------- al visor
    def publico_senderos(self) -> List[List[int]]:
        """Las celdas abiertas como sendero, para que el visor las pueda dibujar.

        Son las que están en `_bioma_previo`, o sea exactamente las que se pintaron y todavía no se
        cerraron. No hace falta recorrer el mapa.
        """
        if self.bioma_sendero is None:
            return []
        return [[x, y] for (x, y) in sorted(self._bioma_previo)]

    # --------------------------------------------------------- persistencia
    def desgaste_bytes(self) -> bytes:
        """Un uint8 casi todo en cero: comprime a nada (ver `mundo_io.guardar_capas`, mismo criterio)."""
        import zlib
        return zlib.compress(self.desgaste.tobytes(), 6)

    def importar_desgaste(self, datos: bytes) -> None:
        import zlib
        try:
            a = np.frombuffer(zlib.decompress(datos), dtype=np.uint8)
        except zlib.error:
            return
        if a.size != self.desgaste.size:
            return                        # el mapa cambió de tamaño: se parte de cero
        self.desgaste = a.reshape(self.desgaste.shape).copy()
        if self.bioma_sendero is None:
            return
        # Reconstruye los senderos desde el desgaste, que es lo único que sobrevive.
        #
        # Acá había una suposición falsa: «el bioma del sendero ya viene guardado en la capa del
        # mapa». No viene. `mundo_io.guardar_capas` corre UNA sola vez, al crear el mundo (y al
        # crear una dimensión), así que la capa de biomas queda congelada en la generación y
        # `Terreno.cambiar_bioma` no llega nunca ni al disco ni a la UI. Medido: 33 celdas pintadas
        # como sendero, 0 después de recargar el mundo y 0 en la capa que sirve la API. Los
        # senderos no se guardaban ni se veían: la fase 5 entera no hacía nada visible.
        #
        # El desgaste sí se guarda, y es la fuente de verdad: una celda es sendero si lo pisaron lo
        # suficiente. Así que al cargar se vuelven a pintar desde ahí.
        ys, xs = np.nonzero(self.desgaste >= PISADAS_SENDERO)
        vecino = B.PRADERA
        for x, y in zip(xs.tolist(), ys.tolist()):
            if int(self.terreno.bioma[y, x]) == self.bioma_sendero:
                continue                  # ya estaba pintado (mundo recién generado con senderos)
            self._bioma_previo[(x, y)] = self._bioma_alrededor(x, y, vecino)
            self.terreno.cambiar_bioma(x, y, self.bioma_sendero)

    def _bioma_alrededor(self, x: int, y: int, por_omision: int) -> int:
        """El bioma más común alrededor: es lo que había antes de que el paso lo pelara."""
        cuenta: Dict[int, int] = {}
        for dy in (-2, -1, 0, 1, 2):
            for dx in (-2, -1, 0, 1, 2):
                if not self.terreno.dentro(x + dx, y + dy):
                    continue
                b = int(self.terreno.bioma[y + dy, x + dx])
                if b != self.bioma_sendero:
                    cuenta[b] = cuenta.get(b, 0) + 1
        return max(cuenta, key=cuenta.get) if cuenta else por_omision

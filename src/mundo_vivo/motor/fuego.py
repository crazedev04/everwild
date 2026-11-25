"""
Incendios: autómata celular sobre el mapa.

Cada celda tiene combustible (según bioma, estación y cuánto se quemó antes) y puede estar ardiendo con una
intensidad. El fuego se propaga a vecinos con probabilidad según su combustible, el viento y la lluvia;
el agua (ríos, lagos, mar) y el suelo pelado frenan el avance; la lluvia lo apaga. Las zonas quemadas
quedan con ceniza y el combustible vuelve a crecer muy despacio.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import biomas as B

K_PROPAGACION = 0.16        # qué tan rápido salta el fuego a un vecino
CONSUMO_POR_MIN = 0.011     # combustible que consume una celda a intensidad máxima
CRECIMIENTO_POR_MIN = 25    # cuánto sube la intensidad (0..255) por minuto
REBROTE_POR_MIN = 0.00003   # fracción del combustible perdido que vuelve por minuto (~23 días de constante de tiempo)
PARCHES_SIN_COMBUSTIBLE = 0.38  # fracción de celdas que no arden (cortafuegos naturales)
VIDA_INCENDIO_MIN = 1200.0      # el avance se debilita con la edad del incendio (rocío, noche, humedad del suelo)
CENIZA_POR_MIN = 0.00005        # cuánto se desvanece la ceniza por minuto
REBROTE_CADA_MIN = 30.0         # el rebrote y la ceniza se aplican en tandas, no minuto a minuto
REBROTE_FIN = 1e-3              # por debajo de esto el rebrote se da por terminado y se deja de recorrer el mapa
# desplazamientos de vecinos (dx, dy)
_VECINOS = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def combustible_bioma(bioma: np.ndarray) -> np.ndarray:
    """Combustible base por celda según el bioma, sacado del registro.

    La tabla se arma una sola vez y se traduce el mapa entero de un saque (nunca celda por celda).
    """
    tabla = np.array(B.tabla(B.COMBUSTIBLE, 0.0), dtype=np.float32)
    return tabla[np.asarray(bioma).astype(np.uint8)]


class Fuego:
    def __init__(self, bioma: np.ndarray, agua: np.ndarray, semilla: int, humedad: Optional[np.ndarray] = None):
        self.alto, self.ancho = bioma.shape
        base = combustible_bioma(bioma)   # una vez al construir el fuego, no por tick
        base[agua > 0] = 0.0
        if humedad is not None:   # suelo y vegetación húmedos arden menos
            base *= (1.0 - 0.55 * humedad.astype(np.float32) / 255.0)
        # parches sin combustible (roca, suelo pelado, vegetación verde): hacen que el fuego se corte solo
        parches = np.random.default_rng((int(semilla) * 2654435761) & 0x7FFFFFFF).random(bioma.shape)
        base[parches < PARCHES_SIN_COMBUSTIBLE] = 0.0
        self.base = base
        self.comb = base.copy()
        self.fuego = np.zeros(bioma.shape, dtype=np.uint8)     # intensidad 0..255
        self.quemado = np.zeros(bioma.shape, dtype=np.float32)  # ceniza reciente 0..1
        self.rng = np.random.default_rng(int(semilla) & 0x7FFFFFFF)
        ang = ((int(semilla) * 0.6180339887) % 1.0) * 2 * math.pi
        self.viento = (math.cos(ang), math.sin(ang))
        self.version = 0            # sube cuando cambia la ceniza (para refrescar el dibujo)
        self.episodio_celdas = 0    # celdas apagadas desde que empezó el incendio actual
        self._hubo_fuego = False
        self.edad_min = 0.0         # minutos desde que empezó el incendio actual
        # ¿hay combustible gastado o ceniza que atender? En un mundo donde nunca se quemó nada,
        # `comb == base` y `quemado == 0`, así que el rebrote no tiene nada que hacer (ver `paso`).
        self._sucio = False
        self._acum_rebrote = 0.0
        # pesos por vecino según el viento: el fuego avanza más a favor del viento
        self._pesos = []
        for dx, dy in _VECINOS:
            d = math.hypot(dx, dy)
            cos = (-dx * self.viento[0] + -dy * self.viento[1]) / d  # dirección vecino -> esta celda
            self._pesos.append((dx, dy, (1.0 if d == 1 else 0.7) * (1.0 + 0.6 * cos)))

    # ------------------------------------------------------------------ consulta
    @property
    def activas(self) -> int:
        return int(np.count_nonzero(self.fuego))

    def celdas_activas(self, maximo: int = 8000) -> List[List[int]]:
        ys, xs = np.nonzero(self.fuego)
        if len(xs) > maximo:
            idx = self.rng.choice(len(xs), maximo, replace=False)
            ys, xs = ys[idx], xs[idx]
        return [[int(x), int(y), int(self.fuego[y, x])] for x, y in zip(xs, ys)]

    # -------------------------------------------------------------------- acción
    def encender(self, x: int, y: int) -> bool:
        if not (0 <= x < self.ancho and 0 <= y < self.alto):
            return False
        if self.comb[y, x] < 0.08 or self.fuego[y, x] > 0:
            return False
        self.fuego[y, x] = 80
        self.version += 1
        if not self._hubo_fuego:
            self._hubo_fuego = True
            self.episodio_celdas = 0
            self.edad_min = 0.0
        return True

    def _suma_vecinos(self, a: np.ndarray) -> np.ndarray:
        """Suma ponderada de a en los 8 vecinos (el vecino a (dx,dy) de la celda aporta con su peso)."""
        p = np.pad(a, 1, mode="constant")
        h, w = a.shape
        out = np.zeros_like(a, dtype=np.float32)
        for dx, dy, peso in self._pesos:
            out += peso * p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
        return out

    def _bbox_ardiendo(self, margen: int = 2) -> Optional[Tuple[int, int, int, int]]:
        """Devuelve (y0, y1, x0, x1) delimitando las celdas con fuego con un halo alrededor."""
        ys, xs = np.nonzero(self.fuego)
        if len(ys) == 0:
            return None
        y0 = max(0, int(ys.min()) - margen)
        y1 = min(self.alto, int(ys.max()) + 1 + margen)
        x0 = max(0, int(xs.min()) - margen)
        x1 = min(self.ancho, int(xs.max()) + 1 + margen)
        return y0, y1, x0, x1

    def paso(self, dt: float, sequedad: float = 1.0, lluvia: Optional[np.ndarray] = None) -> Dict[str, object]:
        """Avanza dt minutos. Devuelve {'apagadas': n, 'termino': bool, 'celdas_episodio': n}."""
        res = {"apagadas": 0, "termino": False, "celdas_episodio": 0}
        ardiendo_todo = self.fuego > 0 if self._hubo_fuego else None
        if ardiendo_todo is not None and ardiendo_todo.any():
            bbox = self._bbox_ardiendo(margen=2)
            total_celdas = self.alto * self.ancho
            usar_sub = False
            if bbox is not None:
                y0, y1, x0, x1 = bbox
                area_sub = (y1 - y0) * (x1 - x0)
                if area_sub < 0.5 * total_celdas:
                    usar_sub = True

            if usar_sub:
                y0, y1, x0, x1 = bbox
                sub_fuego = self.fuego[y0:y1, x0:x1]
                sub_comb = self.comb[y0:y1, x0:x1]
                sub_quemado = self.quemado[y0:y1, x0:x1]
                sub_lluvia = lluvia[y0:y1, x0:x1] if lluvia is not None else None
                ardiendo = sub_fuego > 0

                inten = sub_fuego.astype(np.float32) / 255.0
                calor = self._suma_vecinos(inten)
                self.edad_min += dt
                debil = math.exp(-self.edad_min / VIDA_INCENDIO_MIN)
                p = 1.0 - np.exp(-dt * K_PROPAGACION * debil * calor * sub_comb * sequedad)
                if sub_lluvia is not None:
                    p = p * (1.0 - 0.9 * sub_lluvia)
                nuevo = (~ardiendo) & (sub_comb > 0.08) & (self.rng.random(p.shape, dtype=np.float32) < p)
                consumo = dt * CONSUMO_POR_MIN * np.maximum(inten, 0.3)
                if sub_lluvia is not None:
                    consumo = consumo * (1.0 + 6.0 * sub_lluvia)
                sub_comb[ardiendo] -= consumo[ardiendo]
                sub_fuego[ardiendo] = np.minimum(255, sub_fuego[ardiendo].astype(np.int32) + int(dt * CRECIMIENTO_POR_MIN)).astype(np.uint8)
                if sub_lluvia is not None:
                    bajada = (dt * 45.0 * sub_lluvia).astype(np.int32)
                    sub_fuego[ardiendo] = np.maximum(0, sub_fuego[ardiendo].astype(np.int32) - bajada[ardiendo]).astype(np.uint8)
                    mojadas = ardiendo & (sub_fuego == 0)
                    if mojadas.any():
                        sub_quemado[mojadas] = np.maximum(sub_quemado[mojadas], 0.6)
                        self.episodio_celdas += int(mojadas.sum())
                        self.version += 1
                apagadas = ardiendo & (sub_fuego > 0) & (sub_comb <= 0.04)
                n_apagadas = int(apagadas.sum())
                if n_apagadas:
                    sub_fuego[apagadas] = 0
                    sub_quemado[apagadas] = 1.0
                    sub_comb[apagadas] = 0.0
                    self.episodio_celdas += n_apagadas
                    res["apagadas"] = n_apagadas
                    self.version += 1
                if nuevo.any():
                    sub_fuego[nuevo] = 60
                    self.version += 1
            else:
                ardiendo = ardiendo_todo
                inten = self.fuego.astype(np.float32) / 255.0
                calor = self._suma_vecinos(inten)
                self.edad_min += dt
                debil = math.exp(-self.edad_min / VIDA_INCENDIO_MIN)
                p = 1.0 - np.exp(-dt * K_PROPAGACION * debil * calor * self.comb * sequedad)
                if lluvia is not None:
                    p = p * (1.0 - 0.9 * lluvia)
                nuevo = (~ardiendo) & (self.comb > 0.08) & (self.rng.random(p.shape, dtype=np.float32) < p)
                consumo = dt * CONSUMO_POR_MIN * np.maximum(inten, 0.3)
                if lluvia is not None:
                    consumo = consumo * (1.0 + 6.0 * lluvia)
                self.comb[ardiendo] -= consumo[ardiendo]
                self.fuego[ardiendo] = np.minimum(255, self.fuego[ardiendo].astype(np.int32) + int(dt * CRECIMIENTO_POR_MIN)).astype(np.uint8)
                if lluvia is not None:
                    bajada = (dt * 45.0 * lluvia).astype(np.int32)
                    self.fuego[ardiendo] = np.maximum(0, self.fuego[ardiendo].astype(np.int32) - bajada[ardiendo]).astype(np.uint8)
                    mojadas = ardiendo & (self.fuego == 0)
                    if mojadas.any():
                        self.quemado[mojadas] = np.maximum(self.quemado[mojadas], 0.6)
                        self.episodio_celdas += int(mojadas.sum())
                        self.version += 1
                apagadas = ardiendo & (self.fuego > 0) & (self.comb <= 0.04)
                n_apagadas = int(apagadas.sum())
                if n_apagadas:
                    self.fuego[apagadas] = 0
                    self.quemado[apagadas] = 1.0
                    self.comb[apagadas] = 0.0
                    self.episodio_celdas += n_apagadas
                    res["apagadas"] = n_apagadas
                    self.version += 1
                if nuevo.any():
                    self.fuego[nuevo] = 60
                    self.version += 1
            self._sucio = True      # algo se consumió o quedó ceniza: hay de qué rebrotar
        # rebrote lento del combustible y desvanecimiento de la ceniza, en tandas
        if dt > 0 and self._sucio:
            self._acum_rebrote += dt
            if self._acum_rebrote >= REBROTE_CADA_MIN:
                self._rebrotar(self._acum_rebrote)
                self._acum_rebrote = 0.0
        if self._hubo_fuego and not self.fuego.any():
            self._hubo_fuego = False
            res["termino"] = True
            res["celdas_episodio"] = self.episodio_celdas
        return res

    def _rebrotar(self, dt: float) -> None:
        """Devuelve combustible a lo quemado y borra la ceniza vieja, con el dt acumulado."""
        if not self._sucio:
            return
        # Optimización por chunks: solo procesar chunks que tengan ceniza o combustible < base
        CHUNK = 64
        cyn, cxn = (self.alto + CHUNK - 1) // CHUNK, (self.ancho + CHUNK - 1) // CHUNK
        fac_rebrote = min(1.0, dt * REBROTE_POR_MIN)
        fac_ceniza = (1.0 - min(0.5, dt * CENIZA_POR_MIN))

        # Si el mapa es chico (pocos chunks), el overhead de iterar chunks supera vectorizar plano
        if cyn * cxn <= 4:
            faltante = self.base - self.comb
            faltante *= fac_rebrote
            if self._hubo_fuego:
                faltante[self.fuego != 0] = 0.0
            self.comb += faltante
            self.quemado *= fac_ceniza
        else:
            hay_ardiendo = self._hubo_fuego
            for cy in range(cyn):
                y0 = cy * CHUNK
                y1 = min(self.alto, y0 + CHUNK)
                sub_quem = self.quemado[y0:y1, :]
                sub_comb = self.comb[y0:y1, :]
                sub_base = self.base[y0:y1, :]
                # Ver si hay ceniza o faltante en esta franja
                if sub_quem.max() > 0.0 or (sub_base - sub_comb).max() > 0.001:
                    for cx in range(cxn):
                        x0 = cx * CHUNK
                        x1 = min(self.ancho, x0 + CHUNK)
                        q_chunk = self.quemado[y0:y1, x0:x1]
                        c_chunk = self.comb[y0:y1, x0:x1]
                        b_chunk = self.base[y0:y1, x0:x1]
                        if q_chunk.max() > 0.0 or (b_chunk - c_chunk).max() > 0.001:
                            flt = (b_chunk - c_chunk) * fac_rebrote
                            if hay_ardiendo:
                                f_chunk = self.fuego[y0:y1, x0:x1]
                                flt[f_chunk != 0] = 0.0
                            c_chunk += flt
                            q_chunk *= fac_ceniza

        falta = float(np.abs(self.base - self.comb).max()) if self.comb.size else 0.0
        ceniza = float(self.quemado.max()) if self.quemado.size else 0.0
        if falta < REBROTE_FIN and ceniza < REBROTE_FIN:
            self.comb[...] = self.base
            self.quemado.fill(0.0)
            self._sucio = False
            self.version += 1

    # ----------------------------------------------------------- guardar / cargar
    def exportar(self) -> Dict[str, bytes]:
        return {"fuego": self.fuego.tobytes(),
                "quemado": np.clip(self.quemado * 255, 0, 255).astype(np.uint8).tobytes(),
                "combustible": np.clip(self.comb * 255, 0, 255).astype(np.uint8).tobytes(),
                "edad_min": repr(float(self.edad_min)).encode()}

    def importar(self, fuego: bytes, quemado: bytes, combustible: bytes, edad_min: Optional[bytes] = None) -> None:
        sh = (self.alto, self.ancho)
        self.fuego = np.frombuffer(fuego, dtype=np.uint8).reshape(sh).copy()
        self.quemado = np.frombuffer(quemado, dtype=np.uint8).reshape(sh).astype(np.float32) / 255.0
        self.comb = np.frombuffer(combustible, dtype=np.uint8).reshape(sh).astype(np.float32) / 255.0
        self._hubo_fuego = bool(self.fuego.any())
        self.edad_min = float(bytes(edad_min).decode()) if edad_min else 0.0
        # Un mundo guardado puede traer combustible gastado y ceniza de antes: se marca sucio y la
        # primera tanda de rebrote decide si todavía hay algo que hacer o si ya se puede dejar de
        # recorrer el mapa. Compararlo acá costaría un recorrido más, y para nada.
        self._sucio = True
        self._acum_rebrote = 0.0
        self.version += 1

    def ceniza_bytes(self) -> bytes:
        return np.clip(self.quemado * 255, 0, 255).astype(np.uint8).tobytes()

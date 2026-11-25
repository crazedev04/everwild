"""
Ruido determinista basado en hashes enteros.

No usa el generador aleatorio de numpy a propósito: así el mismo número de
semilla produce el mismo mapa aunque se actualice numpy o Python.
"""
from __future__ import annotations

import numpy as np

_M = np.uint64(0xFFFFFFFF)


def _hash2(ix: np.ndarray, iy: np.ndarray, semilla: int) -> np.ndarray:
    """Devuelve valores pseudoaleatorios en [0, 1] para coordenadas enteras."""
    x = ix.astype(np.int64).astype(np.uint64)
    y = iy.astype(np.int64).astype(np.uint64)
    h = (x * np.uint64(374761393)) & _M
    h = (h + ((y * np.uint64(668265263)) & _M)) & _M
    h = (h + np.uint64((int(semilla) * 2246822519) & 0xFFFFFFFF)) & _M
    h = h ^ (h >> np.uint64(13))
    h = (h * np.uint64(1274126177)) & _M
    h = h ^ (h >> np.uint64(16))
    return h.astype(np.float64) / 4294967295.0


def ruido_valor(xs: np.ndarray, ys: np.ndarray, semilla: int) -> np.ndarray:
    """Ruido de valor suave en [0, 1] evaluado en coordenadas reales xs, ys."""
    x0 = np.floor(xs)
    y0 = np.floor(ys)
    fx = xs - x0
    fy = ys - y0
    # curva quíntica para evitar cuadrículas visibles
    u = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
    v = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
    ix = x0.astype(np.int64)
    iy = y0.astype(np.int64)
    a = _hash2(ix, iy, semilla)
    b = _hash2(ix + 1, iy, semilla)
    c = _hash2(ix, iy + 1, semilla)
    d = _hash2(ix + 1, iy + 1, semilla)
    return (a * (1 - u) + b * u) * (1 - v) + (c * (1 - u) + d * u) * v


def fbm(xs: np.ndarray, ys: np.ndarray, escala: float, octavas: int, semilla: int,
        persistencia: float = 0.5, lacunaridad: float = 2.0) -> np.ndarray:
    """Suma de octavas de ruido (ruido fractal), normalizado a [0, 1]."""
    total = np.zeros_like(xs, dtype=np.float64)
    amp, norma, frec = 1.0, 0.0, 1.0 / escala
    for i in range(octavas):
        total += amp * ruido_valor(xs * frec, ys * frec, semilla + i * 101)
        norma += amp
        amp *= persistencia
        frec *= lacunaridad
    return total / norma


def suavizar(a: np.ndarray, pasadas: int = 1) -> np.ndarray:
    """Desenfoque simple 3x3 repetido (bordes replicados)."""
    out = a.astype(np.float64)
    for _ in range(pasadas):
        p = np.pad(out, 1, mode="edge")
        out = (p[:-2, :-2] + p[:-2, 1:-1] + p[:-2, 2:] +
               p[1:-1, :-2] + p[1:-1, 1:-1] + p[1:-1, 2:] +
               p[2:, :-2] + p[2:, 1:-1] + p[2:, 2:]) / 9.0
    return out

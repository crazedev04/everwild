"""Adaptador de compatibilidad hacia atrás para `mundo_vivo.motor.generador`.

Reexporta todo el pipeline modular desde `mundo_vivo.generador`.
"""
from __future__ import annotations

from mundo_vivo.generador.pipeline import *  # noqa: F401, F403
from mundo_vivo.generador.pipeline import (
    _relieve,
    _a_metros,
    _volcanes,
    _temperatura_mar,
    _precipitacion,
    _hidrologia,
    _erosion_hidraulica,
    _erosion_termica,
    _clasificar,
    _dist_agua,
    _dilatar,
    _seleccionar_lagos,
    _mascara,
    _generar_cavernas,
    _mayor_hueco,
    _CLIMA_CACHE,
    _CAMPOS,
)

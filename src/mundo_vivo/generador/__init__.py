"""GENERADOR DE MUNDO (Terrain/Biomes Pipeline).

Totalmente aislado, determinista por semilla, sin dependencias de WebSocket ni simulación viva.
"""
from __future__ import annotations

from typing import Dict, List, Tuple
import numpy as np

from .pipeline import (
    VERSION_GENERADOR,
    DTYPES,
    ALTURA_MAX_M,
    PROFUNDIDAD_MAX_M,
    ESCALA_REF_M,
    celdas_de_metros,
    celdas_f,
    etapa_relieve,
    etapa_clima,
    etapa_hidrologia_y_erosion,
    etapa_biomas_y_capas,
    generar_mundo,
    preset,
    tabla_clima,
    algoritmo,
)

__all__ = [
    "VERSION_GENERADOR",
    "DTYPES",
    "ALTURA_MAX_M",
    "PROFUNDIDAD_MAX_M",
    "ESCALA_REF_M",
    "celdas_de_metros",
    "celdas_f",
    "etapa_relieve",
    "etapa_clima",
    "etapa_hidrologia_y_erosion",
    "etapa_biomas_y_capas",
    "generar_mundo",
    "preset",
    "tabla_clima",
    "algoritmo",
]

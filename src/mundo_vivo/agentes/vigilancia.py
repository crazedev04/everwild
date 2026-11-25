"""
Vigilancia para el observador (NO para los habitantes).

Detecta cuándo un habitante habla o piensa como si sospechara que el mundo no es real
(simulación, salir del mundo, ser observados, etc.). Solo OBSERVA y avisa en el panel de eventos:
no induce ni refuerza nada, y ningún texto de este módulo llega nunca a un prompt de habitante.

Es una detección por patrones: da falsos positivos (p. ej. "código" en otro sentido) y no
detecta todas las formas de decirlo. Sirve como alarma, no como prueba.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List

# Patrones sobre texto SIN acentos y en minúsculas.
PATRONES = {
    "simulacion": r"\bsimulacion(?:es)?\b|\bsimulad[oa]s?\b|\bmatrix\b|\bsomos (?:una )?(?:simulacion|programa)",
    "mundo_irreal": r"no es(?:ta)? real\b|nada es real\b|mundo (?:falso|irreal|artificial)|todo es (?:falso|una mentira)",
    "salir_del_mundo": r"salir d(?:el|e este) (?:mundo|juego|sistema)|escapar d(?:el|e este) (?:mundo|juego|sistema)|romper (?:el|este) (?:mundo|sistema)",
    "observadores": r"alguien nos (?:observa|controla|mira|vigila)|nos (?:observan|controlan|vigilan|miran desde)|quien nos controla",
    "tecnologia_meta": r"\bservidor\b|\bordenador\b|\bcomputadora\b|\bmodelo de lenguaje\b|\binteligencia artificial\b|\bprogramad[oa]s?\b",
}
_COMPILADOS = {k: re.compile(v) for k, v in PATRONES.items()}


def _normalizar(texto: str) -> str:
    sin_acentos = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return sin_acentos.lower()


def detectar_sospecha(texto: str) -> List[str]:
    """Devuelve los nombres de los patrones que coinciden (lista vacía si ninguno)."""
    if not texto:
        return []
    t = _normalizar(texto)
    return [k for k, rx in _COMPILADOS.items() if rx.search(t)]

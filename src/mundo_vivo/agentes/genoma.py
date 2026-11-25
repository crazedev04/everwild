"""
Genoma de un habitante: temperamento + red neuronal pequeña de REFLEJOS.

Qué es y qué NO es
  - Es la parte HEREDABLE: rasgos de temperamento (0..1) y los pesos de una red chica que convierte
    señales del cuerpo y del entorno en impulsos (huir, pelear, buscar recursos, descansar).
  - NO piensa con palabras ni decide la estrategia: eso lo hace el modelo de lenguaje, que recibe estos
    impulsos y el temperamento como parte de lo que siente.
  - Los recuerdos y lo aprendido NO se heredan (viven en la base de memorias); solo el genoma.

Todo es determinista con una semilla y usa solo la biblioteca estándar.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

RASGOS = ("audacia", "sociabilidad", "curiosidad", "agresividad", "cautela", "empatia", "resiliencia")

# Señales que recibe la red (todas normalizadas a 0..1)
ENTRADAS = ("hambre", "sed", "cansancio", "dolor", "amenaza_cercana", "hay_otros", "noche", "familiaridad_lugar")
# Impulsos que produce (0..1)
SALIDAS = ("huir", "pelear", "buscar_recursos", "descansar")

N_ENTRADAS, N_OCULTAS, N_SALIDAS = len(ENTRADAS), 6, len(SALIDAS)
N_PESOS = N_ENTRADAS * N_OCULTAS + N_OCULTAS + N_OCULTAS * N_SALIDAS + N_SALIDAS  # 82
VERSION_GENOMA = 1


def _gauss(rng: random.Random, sigma: float) -> float:
    """Normal por Box-Muller usando solo random(): estable entre versiones de Python."""
    u1, u2 = max(rng.random(), 1e-12), rng.random()
    return sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


@dataclass
class Genoma:
    rasgos: Dict[str, float]
    pesos: List[float]
    generacion: int = 0
    version: int = VERSION_GENOMA

    def validar(self) -> "Genoma":
        if set(self.rasgos) != set(RASGOS):
            raise ValueError("Rasgos inválidos: %s" % sorted(self.rasgos))
        if any(not (0.0 <= v <= 1.0) for v in self.rasgos.values()):
            raise ValueError("Los rasgos deben estar entre 0 y 1.")
        if len(self.pesos) != N_PESOS:
            raise ValueError("Se esperaban %d pesos y hay %d." % (N_PESOS, len(self.pesos)))
        if any(not math.isfinite(p) for p in self.pesos):
            raise ValueError("Hay pesos no finitos.")
        return self

    def a_dict(self) -> dict:
        return {"version": self.version, "generacion": self.generacion,
                "rasgos": {k: round(v, 6) for k, v in self.rasgos.items()},
                "pesos": [round(p, 6) for p in self.pesos]}

    @staticmethod
    def de_dict(d: dict) -> "Genoma":
        return Genoma(rasgos=dict(d["rasgos"]), pesos=list(d["pesos"]),
                      generacion=int(d.get("generacion", 0)), version=int(d.get("version", VERSION_GENOMA))).validar()


def genoma_fundador(semilla: int) -> Genoma:
    """Genoma de un habitante de la primera generación (sin padres)."""
    rng = random.Random(semilla)
    rasgos = {k: round(0.15 + 0.70 * rng.random(), 6) for k in RASGOS}
    pesos = [_gauss(rng, 0.6) for _ in range(N_PESOS)]
    return Genoma(rasgos, pesos, generacion=0).validar()


def heredar(a: Genoma, b: Genoma, semilla: int, tasa_mutacion: float = 0.05,
            magnitud_rasgos: float = 0.12, magnitud_pesos: float = 0.15) -> Genoma:
    """Hijo de dos genomas: cruce + mutación. Los recuerdos NO se heredan."""
    rng = random.Random(semilla)
    rasgos = {}
    for k in RASGOS:
        u = rng.random()
        if u < 0.4:
            v = a.rasgos[k]
        elif u < 0.8:
            v = b.rasgos[k]
        else:
            v = 0.5 * (a.rasgos[k] + b.rasgos[k])
        if rng.random() < tasa_mutacion * 3:  # los rasgos mutan algo más que los pesos
            v += _gauss(rng, magnitud_rasgos)
        rasgos[k] = round(_clamp01(v), 6)
    pesos = []
    for pa, pb in zip(a.pesos, b.pesos):
        p = pa if rng.random() < 0.5 else pb  # cruce uniforme
        if rng.random() < tasa_mutacion:
            p += _gauss(rng, magnitud_pesos)
        pesos.append(round(p, 6))
    return Genoma(rasgos, pesos, generacion=max(a.generacion, b.generacion) + 1).validar()


def impulsos(g: Genoma, entradas: Dict[str, float]) -> Dict[str, float]:
    """Pasada hacia adelante de la red de reflejos. Las entradas faltantes valen 0."""
    x = [_clamp01(float(entradas.get(n, 0.0))) for n in ENTRADAS]
    w = g.pesos
    i = 0
    oculta = []
    for _ in range(N_OCULTAS):
        z = sum(x[j] * w[i + j] for j in range(N_ENTRADAS))
        i += N_ENTRADAS
        oculta.append(z)
    for k in range(N_OCULTAS):
        oculta[k] = math.tanh(oculta[k] + w[i + k])
    i += N_OCULTAS
    salidas = {}
    for s_idx, nombre in enumerate(SALIDAS):
        z = sum(oculta[k] * w[i + k] for k in range(N_OCULTAS))
        i += N_OCULTAS
        salidas[nombre] = z
    for s_idx, nombre in enumerate(SALIDAS):
        z = salidas[nombre] + w[i + s_idx]
        salidas[nombre] = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
    return salidas


def distancia(a: Genoma, b: Genoma) -> float:
    """Diferencia media entre dos genomas (0 = idénticos). Sirve para vigilar la endogamia."""
    dr = sum(abs(a.rasgos[k] - b.rasgos[k]) for k in RASGOS) / len(RASGOS)
    dp = sum(abs(x - y) for x, y in zip(a.pesos, b.pesos)) / N_PESOS
    return 0.5 * (dr + min(1.0, dp))


_FRASES: Dict[str, dict] = {}


def _frases() -> Dict[str, dict]:
    """Cómo se describe cada rasgo. Es TEXTO que lee el modelo, o sea contenido: vive en
    datos_base/cultura/temperamento.json y se puede matizar o traducir sin tocar código."""
    if not _FRASES:
        from ..registro import Registro
        for rid, d in Registro.cargar().de_tipo("temperamento").items():
            _FRASES[rid] = d
    return _FRASES


def describir_temperamento(g: Genoma, rasgos: Optional[Dict[str, float]] = None) -> str:
    """Frase en español para el prompt del habitante. Si se pasan los rasgos VIVOS (los que cambiaron con la experiencia), se usan esos."""
    r = rasgos or g.rasgos
    frases = []
    for rasgo, d in _frases().items():
        v = r.get(rasgo)
        if v is None:
            continue
        if v >= 0.7 and d.get("alto"):
            frases.append(d["alto"])
        elif v <= 0.3 and d.get("bajo"):
            frases.append(d["bajo"])
    return "; ".join(frases) if frases else "de caracter equilibrado"

"""Reloj del mundo: minutos simulados -> día, hora, estación, año y luz.

1 año = 4 estaciones de 30 días (120 días). El mundo empieza el día 1 a las 08:00 (t = 480).
"""
from __future__ import annotations

import math

MIN_DIA = 1440
DIAS_ESTACION = 30
ESTACIONES = ("primavera", "verano", "otoño", "invierno")
DIAS_ANIO = DIAS_ESTACION * len(ESTACIONES)


def fecha(t_min: float) -> dict:
    t = int(t_min)
    dia_abs, m = divmod(t, MIN_DIA)
    d_anio = dia_abs % DIAS_ANIO
    return {"dia": dia_abs + 1, "hora": m // 60, "minuto": m % 60,
            "estacion": ESTACIONES[d_anio // DIAS_ESTACION], "anio": dia_abs // DIAS_ANIO + 1,
            "dia_del_anio": d_anio + 1}


def luz(t_min: float) -> float:
    """0.10 (noche) .. 1.0 (mediodía), con amanecer y atardecer suaves (sale 06:00, se pone 20:00)."""
    h = (t_min % MIN_DIA) / 60.0
    s = math.sin(math.pi * (h - 6.0) / 14.0) if 6.0 <= h <= 20.0 else 0.0
    return 0.10 + 0.90 * min(1.0, s * 1.6)


def es_noche(t_min: float) -> bool:
    return luz(t_min) < 0.35


def sequedad(t_min: float) -> float:
    """Qué tan seca está la vegetación según la estación (afecta cuánto arde)."""
    return {"primavera": 0.8, "verano": 1.25, "otoño": 1.0, "invierno": 0.6}[fecha(t_min)["estacion"]]


def ajuste_temp(t_min: float) -> float:
    """Grados que se suman a la temperatura media del mapa según estación (suave entre una y otra) y hora del día."""
    f = fecha(t_min)
    d = f["dia_del_anio"] - 1                                   # 0..119
    estacional = -9.0 * math.cos(2 * math.pi * (d - 105) / DIAS_ANIO) * 1.0   # mínimo a fines de invierno (día ~105), máximo a mediados de verano
    estacional += 1.0
    diurno = 4.0 * math.cos(2 * math.pi * ((t_min % MIN_DIA) / 60.0 - 14.0) / 24.0)   # +4 a las 14:00, -4 a las 02:00
    return estacional + diurno


def probabilidad_tormenta(t_min: float) -> float:
    """Tormentas nuevas por día simulado, según la estación."""
    return {"primavera": 0.9, "verano": 1.1, "otoño": 0.7, "invierno": 0.35}[fecha(t_min)["estacion"]]


def texto(t_min: float) -> str:
    f = fecha(t_min)
    return "Día %d · %02d:%02d · %s · Año %d" % (f["dia"], f["hora"], f["minuto"], f["estacion"].capitalize(), f["anio"])

"""Presentador: traduce el estado de la simulación a los diccionarios que viajan al visor.

El motor no conoce al visor: acá vive toda la serialización. `Simulacion` expone los datos crudos
(atributos, habitantes, estructuras, colonias, fuego) y este módulo los arma en el formato que espera
la UI. Así el motor queda libre de la forma del JSON y el visor queda libre del motor.
"""
from __future__ import annotations


def estado_base(sim) -> dict:
    import mundo_vivo.motor.reloj as reloj
    luz = reloj.luz(sim.t) if sim.cielo.get("dia_noche", True) else min(0.18, reloj.luz(sim.t))
    return {"t_min": int(sim.t), "fecha": reloj.fecha(sim.t), "texto_fecha": reloj.texto(sim.t),
            "luz": round(luz, 3),
            "nieve_v": int(sim.t // 360),
            "temp_media": round(sim._temp_media_base + (reloj.ajuste_temp(sim.t) if sim.cielo.get("estaciones", True) else 0.0), 1),
            "ceniza_v": sim.fuego.version,
            "tormentas": [t + [1 if sim.temp_en(t[0], t[1]) <= 0 else 0] for t in sim.clima.a_publico()],
            "fauna": sim.fauna.publico() if sim.modulo("fauna") else [],
            "chunks_activos": __import__("mundo_vivo.motor.chunks", fromlist=["chunks_activos"]).chunks_activos(sim),
            "viento": [round(sim.fuego.viento[0], 3), round(sim.fuego.viento[1], 3)]}


def estado_liviano(sim, *, bloques: bool = False) -> dict:
    e = estado_base(sim)
    e["habitantes"] = [h.a_publico_mapa() for h in sim.habitantes.values()]
    if bloques:
        e["fuego"] = sim.fuego.celdas_activas()
        e.update(sim.publico_estructuras())
        e["colonias"] = sim.publico_colonias()
    return e


def estado_completo(sim) -> dict:
    e = estado_base(sim)
    e["habitantes"] = [dict(h.a_publico(), temp=round(sim.temp_en(h.x, h.y), 1), frio=round(h.frio, 2))
                       for h in sim.habitantes.values()]
    e["fuego"] = sim.fuego.celdas_activas()
    e.update(sim.publico_estructuras())
    e["colonias"] = sim.publico_colonias()
    return e

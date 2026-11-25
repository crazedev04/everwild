"""Ayudas compartidas por los tests."""
from __future__ import annotations

import time


def crear_mundo_api(cliente, espera_s: float = 60.0, **datos) -> str:
    """Crea un mundo por la API y espera a que termine de generarse.

    Generar un mundo grande lleva más de un minuto, así que `POST /api/mundos` devuelve un trabajo y el visor va
    preguntando cómo viene (eso es lo que alimenta la pantalla de carga). Esta función hace esa espera.
    Devuelve el nombre del mundo.
    """
    r = cliente.post("/api/mundos", json=datos)
    assert r.status_code == 200, "no se pudo pedir el mundo: %s %s" % (r.status_code, r.text)
    tid = r.json()["trabajo"]
    limite = time.monotonic() + espera_s
    while time.monotonic() < limite:
        t = cliente.get("/api/mundos/generando/%s" % tid).json()
        if t.get("error"):
            raise AssertionError("falló la generación: %s" % t["error"])
        if t.get("hecho"):
            return t["nombre"]
        time.sleep(0.05)
    raise AssertionError("la generación no terminó en %s s" % espera_s)

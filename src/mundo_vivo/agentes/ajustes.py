"""Interruptores y parámetros de cada mundo (se guardan en la tabla `ajustes`)."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict

# Qué partes del mundo están conectadas. Se pueden cambiar en vivo desde el panel.
MODULOS = {
    "percepcion_social": "Que se vean y se conozcan al cruzarse",
    "conversacion": "Que puedan hablarse (queda todo registrado)",
    "memoria": "Que guarden recuerdos privados de lo que viven",
    "reflejos_genoma": "Que sus reflejos dependan del genoma heredado",
    "cerebro_llm": "Cerebro con modelo de lenguaje (si no, camina con reglas simples)",
    "reproduccion": "Que puedan formar familia (con consentimiento de ambos)",
    "conocimientos": "Que puedan inventar y enseñar cosas nuevas",
    "fauna": "Animales (presas, depredadores, peces, aves): que existan, se muevan y se puedan cazar",
    "emociones": "Emociones simples (miedo, tristeza, alegría, enojo) que influyen en lo que piensan",
    "frio": "Frío y nieve: las estaciones y la hora cambian la temperatura, cae nieve y el frío debilita a quien no se abriga",
    "personalidad": "Que el carácter cambie con lo que viven (cautela tras un ataque, sociabilidad con buenas charlas...)",
    "atencion": "Que no todos piensen con el modelo a la vez (hace falta con mucha gente)",
    "colonias": "Hongos y líquenes que se propagan por el mapa y se pueden cosechar",
    "psique": "Plantas que mueven la cabeza: visiones, miedo, ganas de probar cosas",
    "objetivos": "Que se propongan objetivos propios y encadenen los pasos para lograrlos",
    "atributos": "Fuerza, resistencia y pulso: mejoran con el uso y se oxidan sin él",
    "fenomenos": "Sucesos raros del mundo (meteoritos y lo que se agregue por datos)",
    "hambre": "Hambre y alimentos: cada comida alimenta distinto cruda, cocida o podrida",
    "habitos": "Que cada uno tenga su propia red que aprende de lo que le sale bien o mal y sesga sus decisiones",
    "semantica": "Recordar por significado y no sólo por palabras (necesita el modelo de embeddings bajado)",
}
PREDETERMINADOS: Dict[str, Any] = {
    # El hambre cambia el balance a lo bestia: viene APAGADA por defecto para que un mundo que ya venía
    # andando no se encuentre de golpe con reglas nuevas. Los mundos nuevos la encienden al crearse.
    # `semantica` también viene apagada, pero por otro motivo: necesita un modelo de embeddings bajado
    # (`ollama pull nomic-embed-text`). Encendida sin él sólo llenaría el panel de errores.
    "modulos": {k: (k not in ("hambre", "semantica")) for k in MODULOS},
    "modelo": "qwen3.5:4b",
    "modelo_embeddings": "nomic-embed-text",
    "host": os.environ.get("OLLAMA_HOST_URL", "http://localhost:11434"),
    "temperatura": 0.7,
    "num_ctx": 8192,
    "timeout_s": 180,
    "velocidad_max_pensando": 0.0,  # min simulados por segundo mientras alguien piensa; 0 = AUTOMÁTICO (según lo que tarda el modelo)
    "paralelo": 1,  # cuántas consultas simultáneas al modelo (Ollama debe tener OLLAMA_NUM_PARALLEL igual o mayor)
    "max_tokens": 1200,  # espacio suficiente para el bloque <think> + el JSON completo
    "razonar": True,
}


def obtener(con: sqlite3.Connection) -> Dict[str, Any]:
    out = json.loads(json.dumps(PREDETERMINADOS))
    try:
        for r in con.execute("SELECT clave, valor FROM ajustes"):
            v = json.loads(r[1])
            if r[0] == "modulos" and isinstance(v, dict):
                out["modulos"].update(
                    {k: bool(x) for k, x in v.items() if k in MODULOS}
                )
            elif r[0] in out and r[0] != "modulos":
                out[r[0]] = v
    except sqlite3.OperationalError:
        pass
    return out


def guardar(con: sqlite3.Connection, cambios: Dict[str, Any]) -> Dict[str, Any]:
    """Valida y guarda un cambio parcial. Devuelve los ajustes resultantes."""
    actual = obtener(con)
    for k, v in cambios.items():
        if k == "modulos":
            if not isinstance(v, dict):
                raise ValueError("'modulos' debe ser un objeto.")
            for m, on in v.items():
                if m not in MODULOS:
                    raise ValueError("Módulo desconocido: %s" % m)
                actual["modulos"][m] = bool(on)
        elif k in ("modelo", "host", "modelo_embeddings"):
            if not isinstance(v, str) or not v.strip() or len(v) > 200:
                raise ValueError("%s inválido." % k)
            actual[k] = v.strip()
        elif k == "temperatura":
            actual[k] = max(0.0, min(5.0, float(v)))
        elif k == "velocidad_max_pensando":
            # -1 = sin tope (a pedido explícito); 0 = automático; >0 = techo fijo
            actual[k] = max(-1.0, min(500.0, float(v)))
        elif k == "paralelo":
            actual[k] = max(1, min(4, int(v)))
        elif k == "max_tokens":
            actual[k] = max(60, min(4096, int(v)))
        elif k == "razonar":
            actual[k] = bool(v)
        elif k in ("num_ctx", "timeout_s"):
            actual[k] = max(
                512 if k == "num_ctx" else 10,
                min(32768 if k == "num_ctx" else 600, int(v)),
            )
        else:
            raise ValueError("Ajuste desconocido: %s" % k)
    with con:
        for k, v in actual.items():
            con.execute(
                "INSERT OR REPLACE INTO ajustes (clave, valor) VALUES (?, ?)",
                (k, json.dumps(v)),
            )
    return actual

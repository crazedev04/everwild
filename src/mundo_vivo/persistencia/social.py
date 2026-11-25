"""
Vida social: diálogos, recuerdos de lo conversado y relaciones.

Cada vez que alguien habla:
  - queda el registro COMPLETO en `dialogos` (solo lo ve el observador),
  - quien habla y quien escucha reciben cada uno SU recuerdo privado de la conversación,
  - se crea un evento "conversacion" visible en el panel,
  - si el texto sugiere que sospechan que el mundo no es real, se crea una alerta para el observador.
Un recuerdo de una pelea puede dejar rencor: la relación se guarda y sobrevive a reinicios y actualizaciones.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Dict, Iterable, List, Optional

from ..agentes.vigilancia import detectar_sospecha
from .memoria import MemoriaPrivada
from .mundo_io import registrar_evento


def _nombre(con: sqlite3.Connection, hid: int) -> str:
    fila = con.execute("SELECT nombre FROM habitantes WHERE id = ?", (hid,)).fetchone()
    return fila["nombre"] if fila else "alguien"


def registrar_dialogo(con: sqlite3.Connection, t_min: int, emisor_id: int, receptores_ids: Iterable[int],
                      mensaje: str, x=None, y=None, z=None, certeza: float = 1.0) -> int:
    receptores = [int(r) for r in receptores_ids]
    if not receptores:
        raise ValueError("Un diálogo necesita al menos un receptor.")
    sospechas = detectar_sospecha(mensaje)
    with con:
        cur = con.execute(
            "INSERT INTO dialogos (t_min, emisor_id, receptores, mensaje, x, y, z, sospecha) VALUES (?,?,?,?,?,?,?,?)",
            (t_min, emisor_id, json.dumps(receptores), mensaje, x, y, z, json.dumps(sospechas) if sospechas else None))
    dialogo_id = cur.lastrowid

    nombre_emisor = _nombre(con, emisor_id)
    nombres_receptores = ", ".join(_nombre(con, r) for r in receptores)
    MemoriaPrivada(con, emisor_id).agregar(
        t_min, "episodica", "Le dijiste a %s: «%s»" % (nombres_receptores, mensaje), importancia=0.3)
    for r in receptores:
        # Lo que a uno le cuentan NO es un hecho: queda como «oído», con quién lo dijo y cuánto se le cree.
        MemoriaPrivada(con, r).agregar(
            t_min, "episodica", "%s te dijo: «%s»" % (nombre_emisor, mensaje), importancia=0.4,
            origen="oido", de_quien=emisor_id, certeza=certeza)

    registrar_evento(con, t_min, "conversacion",
                     "%s le dijo a %s: «%s»" % (nombre_emisor, nombres_receptores, mensaje),
                     actor_id=emisor_id, x=x, y=y, z=z, importancia=1,
                     datos={"dialogo_id": dialogo_id, "receptores": receptores})
    if sospechas:
        registrar_evento(con, t_min, "sospecha_simulacion",
                         "⚠ %s habló como si sospechara que el mundo no es real: «%s»" % (nombre_emisor, mensaje),
                         actor_id=emisor_id, x=x, y=y, z=z, importancia=4, origen="sistema",
                         causa="detección por patrones (puede ser falso positivo)",
                         datos={"dialogo_id": dialogo_id, "patrones": sospechas})
    return dialogo_id


def listar_dialogos(con: sqlite3.Connection, entre: Optional[int] = None, limite: int = 100) -> List[dict]:
    """Solo para el observador. `entre` filtra por un habitante (como emisor o receptor)."""
    filas = [dict(r) for r in con.execute("SELECT * FROM dialogos ORDER BY id DESC LIMIT ?", (max(1, int(limite)) * 5,))]
    out = []
    for f in filas:
        f["receptores"] = json.loads(f["receptores"])
        f["sospecha"] = json.loads(f["sospecha"]) if f["sospecha"] else []
        if entre is None or f["emisor_id"] == entre or entre in f["receptores"]:
            out.append(f)
    return out[:limite]


# ---------------------------------------------------------------- relaciones

def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


def ajustar_relacion(con: sqlite3.Connection, t_min: int, habitante_id: int, otro_id: int,
                     d_afecto: float = 0.0, d_confianza: float = 0.0, motivo: str = "") -> Dict[str, float]:
    """Cambia cómo `habitante_id` ve a `otro_id`. Si el cambio es fuerte, queda un recuerdo importante."""
    fila = con.execute("SELECT afecto, confianza FROM relaciones WHERE habitante_id = ? AND otro_id = ?",
                       (habitante_id, otro_id)).fetchone()
    a0, c0 = (fila["afecto"] if fila else 0.0), (fila["confianza"] if fila else 0.0)
    # rendimientos decrecientes: cuando ya hay mucha confianza o afecto, cada charla suma menos (no se satura en una semana)
    if d_afecto > 0:
        d_afecto *= max(0.1, 1.0 - max(0.0, a0))
    if d_confianza > 0:
        d_confianza *= max(0.1, 1.0 - max(0.0, c0))
    afecto = _clamp(a0 + d_afecto)
    confianza = _clamp(c0 + d_confianza)
    with con:
        con.execute(
            "INSERT INTO relaciones (habitante_id, otro_id, afecto, confianza, actualizado_min, resumen) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(habitante_id, otro_id) DO UPDATE SET "
            "afecto = excluded.afecto, confianza = excluded.confianza, "
            "actualizado_min = excluded.actualizado_min, resumen = excluded.resumen",
            (habitante_id, otro_id, afecto, confianza, t_min, motivo))
    if abs(d_afecto) >= 0.3 or abs(d_confianza) >= 0.3:
        sentido = "empeoró" if (d_afecto + d_confianza) < 0 else "mejoró"
        MemoriaPrivada(con, habitante_id).agregar(
            t_min, "semantica", "Tu relación con %s %s%s." % (_nombre(con, otro_id), sentido,
                                                              (": " + motivo) if motivo else ""),
            importancia=0.8)
    return {"afecto": afecto, "confianza": confianza}


def relaciones_de(con: sqlite3.Connection, habitante_id: int) -> List[dict]:
    """Las relaciones de UN habitante (nunca las de otros)."""
    filas = con.execute(
        "SELECT r.otro_id, h.nombre AS otro_nombre, r.afecto, r.confianza, r.actualizado_min, r.resumen "
        "FROM relaciones r JOIN habitantes h ON h.id = r.otro_id WHERE r.habitante_id = ? "
        "ORDER BY r.actualizado_min DESC", (habitante_id,))
    return [dict(f) for f in filas]


def describir_relacion(afecto: float, confianza: float) -> str:
    """Texto para el prompt del habitante (percepción de su propia relación)."""
    if afecto <= -0.6: base = "lo detestas"
    elif afecto <= -0.25: base = "estas distanciado o peleado con esa persona"
    elif afecto < 0.25: base = "es un conocido"
    elif afecto < 0.6: base = "te cae bien"
    else: base = "lo quieres mucho"
    if confianza <= -0.4: base += " y no confias en el"
    elif confianza >= 0.5: base += " y confias en el"
    return base

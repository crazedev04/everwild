"""
Memoria privada de un habitante.

La ÚNICA forma de leer o escribir memorias es a través de MemoriaPrivada, que
queda atada a un habitante_id. No existe ninguna función que devuelva memorias
de varios habitantes juntos: el aislamiento lo impone el código, no el prompt.

Diseño (síntesis de Generative Agents, MemGPT/Letta y los trabajos de memoria de largo plazo para agentes):
  * flujo de memoria: cada recuerdo tiene tiempo, importancia, lugar y etiquetas;
  * recuperación por puntaje = recencia + importancia + relevancia (relevancia = palabras en común con la situación
    actual + cercanía del lugar), cada término normalizado a 0..1 entre los candidatos;
  * repetición: lo que se repite no se duplica, se refuerza (veces) y lo que se recuerda se fortalece;
  * olvido: lo poco importante, no repetido y viejo se descarta; lo vivido muy importante nunca;
  * reflexión: los aprendizajes (tipo 'creencia', origen 'reflexion') duran mucho más que los episodios.
"""
from __future__ import annotations

import math
import re
import sqlite3
from typing import Iterable, List, Optional, Set

TIPOS = ("episodica", "semantica", "resumen", "creencia")
MIN_DIA = 1440
MEDIA_VIDA = {"episodica": 2.0 * MIN_DIA, "semantica": 15.0 * MIN_DIA, "resumen": 15.0 * MIN_DIA, "creencia": 30.0 * MIN_DIA}
MAX_POR_HABITANTE = 400
_VACIAS = {"para", "como", "pero", "porque", "tenes", "tenés", "estas", "estás", "esta", "está", "este", "esto", "cosa", "cosas", "algo",
           "hace", "hacer", "donde", "dónde", "vos", "fue", "con", "una", "uno", "unos", "unas", "que", "qué", "por", "del", "las", "los",
           "muy", "mas", "más", "sobre", "entre", "desde", "hasta", "cuando", "cuándo", "tambien", "también", "ahora", "todo", "toda"}


def tokens(texto: str) -> Set[str]:
    """Raíces (5 letras) de las palabras con contenido: 'arañas' y 'araña' coinciden."""
    out = set()
    for w in re.findall(r"[a-záéíóúñü]{4,}", (texto or "").lower()):
        if w not in _VACIAS:
            out.add(w[:5])
    return out


def _norm(vals: List[float]) -> List[float]:
    if not vals:
        return []
    lo, hi = min(vals), max(vals)
    return [0.5] * len(vals) if hi - lo < 1e-9 else [(v - lo) / (hi - lo) for v in vals]


def sin_embedding(con: sqlite3.Connection, n: int = 16) -> List[tuple]:
    """(id, contenido) de recuerdos a los que todavía no se les calculó el vector de significado.

    Es la ÚNICA consulta que cruza habitantes y existe sólo para el índice: nadie ve el texto de otro.
    El resultado va al modelo de embeddings y vuelve como vector; no se le muestra a ninguna mente."""
    return [(int(r[0]), r[1]) for r in con.execute(
        "SELECT id, contenido FROM memorias WHERE embedding IS NULL ORDER BY id DESC LIMIT ?", (int(n),))]


def guardar_embeddings(con: sqlite3.Connection, filas: Iterable[tuple]) -> None:
    """filas = [(bytes, id)]. Un bytes vacío marca «ya se intentó» (se recupera por palabras)."""
    filas = list(filas)
    if filas:
        with con:
            con.executemany("UPDATE memorias SET embedding = ? WHERE id = ?", filas)


class MemoriaPrivada:
    def __init__(self, con: sqlite3.Connection, habitante_id: int, semantica=None):
        self._con = con
        self.habitante_id = int(habitante_id)
        # Opcional: vectores de significado (agentes/semantica.py). Sin esto la relevancia es por palabras.
        self._sem = semantica

    # ------------------------------------------------------------------ escribir
    def agregar(self, t_min: int, tipo: str, contenido: str, importancia: float = 0.5, evento_id: Optional[int] = None,
                x: Optional[float] = None, y: Optional[float] = None, origen: str = "vivido",
                de_quien: Optional[int] = None, certeza: float = 1.0) -> int:
        """`origen` dice de dónde salió (vivido, visto, oido, inferido, reflexion) y `certeza` cuánto se le cree.
        Un rumor no puede valer lo mismo que algo visto con los propios ojos."""
        if tipo not in TIPOS:
            raise ValueError("tipo de memoria inválido: %r" % tipo)
        contenido = contenido.strip()
        with self._con:
            # lo que se repite se refuerza en vez de llenar la memoria de copias («Te atacó una araña» ×3)
            ya = self._con.execute(
                "SELECT id, importancia FROM memorias WHERE habitante_id = ? AND contenido = ? AND t_min >= ? ORDER BY id DESC LIMIT 1",
                (self.habitante_id, contenido, int(t_min) - (3 * MIN_DIA if tipo == "episodica" else 60 * MIN_DIA))).fetchone()
            if ya is not None:
                self._con.execute("UPDATE memorias SET veces = veces + 1, t_min = ?, importancia = ?, x = COALESCE(?, x), y = COALESCE(?, y) WHERE id = ?",
                                  (int(t_min), min(1.0, ya["importancia"] + 0.05), x, y, ya["id"]))
                return ya["id"]
            cur = self._con.execute(
                "INSERT INTO memorias (habitante_id, t_min, tipo, contenido, importancia, evento_id, x, y, etiquetas, origen, ultimo_acceso, de_quien, certeza) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.habitante_id, int(t_min), tipo, contenido, float(importancia), evento_id, x, y,
                 " ".join(sorted(tokens(contenido))), origen, int(t_min), de_quien,
                 max(0.0, min(1.0, float(certeza)))))
        return cur.lastrowid

    # ------------------------------------------------------------------- leer
    def recientes(self, n: int = 10, tipo: Optional[str] = None) -> List[dict]:
        sql, args = "SELECT * FROM memorias WHERE habitante_id = ?", [self.habitante_id]
        if tipo:
            sql += " AND tipo = ?"; args.append(tipo)
        sql += " ORDER BY t_min DESC, id DESC LIMIT ?"
        args.append(int(n))
        return [dict(r) for r in self._con.execute(sql, args)]

    def importantes(self, n: int = 5) -> List[dict]:
        return [dict(r) for r in self._con.execute(
            "SELECT * FROM memorias WHERE habitante_id = ? ORDER BY importancia DESC, t_min DESC LIMIT ?",
            (self.habitante_id, int(n)))]

    def recordar(self, t_ahora: float, contexto: str = "", x: Optional[float] = None, y: Optional[float] = None,
                 n: int = 6, tipos: Optional[Iterable[str]] = None, tocar: bool = True) -> List[dict]:
        """Los n recuerdos más útiles AHORA: recientes, importantes y relacionados con lo que está viviendo."""
        tipos = tuple(tipos) if tipos else TIPOS
        marcas = ",".join("?" * len(tipos))
        filas = [dict(r) for r in self._con.execute(
            "SELECT * FROM memorias WHERE habitante_id = ? AND tipo IN (%s) ORDER BY t_min DESC LIMIT 300" % marcas,
            (self.habitante_id, *tipos))]
        if not filas:
            return []
        ctx = tokens(contexto)
        # Vector de la situación, si ya está calculado. Nunca se espera por él: sin vector, relevancia por palabras.
        qv = self._sem.vector(contexto) if (self._sem is not None and contexto) else None
        rec, rel = [], []
        for m in filas:
            edad = max(0.0, t_ahora - m["t_min"])
            rec.append(math.pow(0.5, edad / MEDIA_VIDA.get(m["tipo"], MIN_DIA)))
            etq = set((m.get("etiquetas") or "").split())
            r = min(1.0, len(ctx & etq) / 3.0) if ctx and etq else 0.0
            if qv is not None:
                # Significado: «me atacó una araña» responde a «un bicho venenoso», que no comparte una palabra.
                # Se toma el máximo contra las palabras, así esto sólo puede sumar: nunca empeora lo que ya andaba.
                s = self._sem.parecido(qv, m.get("embedding"))
                if s is not None:
                    r = max(r, s)
            if x is not None and m.get("x") is not None:
                r = max(r, 0.8 * math.exp(-math.hypot(x - m["x"], y - m["y"]) / 15.0))
            rel.append(r)
        imp = [min(1.0, m["importancia"] + 0.08 * math.log1p(max(0, m.get("veces", 1) - 1))) for m in filas]
        nr, ni, nl = _norm(rec), _norm(imp), _norm(rel)
        puntos = sorted(((1.0 * nr[i] + 1.2 * ni[i] + 1.6 * nl[i], i) for i in range(len(filas))), reverse=True)
        elegidos = [filas[i] for _, i in puntos[:n]]
        if tocar and elegidos:
            with self._con:
                self._con.executemany("UPDATE memorias SET ultimo_acceso = ? WHERE id = ?", [(int(t_ahora), m["id"]) for m in elegidos])
        return elegidos

    def creencias(self, n: int = 3, contexto: str = "", t_ahora: float = 0.0) -> List[dict]:
        """Aprendizajes (reflexiones y saberes) más relacionados con la situación."""
        return self.recordar(t_ahora, contexto, n=n, tipos=("creencia", "resumen"), tocar=False)

    def contar(self) -> int:
        return self._con.execute("SELECT COUNT(*) FROM memorias WHERE habitante_id = ?", (self.habitante_id,)).fetchone()[0]

    # ------------------------------------------------------------------ olvidar
    def olvidar(self, t_ahora: float) -> int:
        """Descarta lo poco importante, no repetido, viejo y no repasado. Lo vivido muy importante (>=0.85) y los aprendizajes se conservan."""
        with self._con:
            c1 = self._con.execute(
                "DELETE FROM memorias WHERE habitante_id = ? AND tipo = 'episodica' AND importancia < 0.85 AND veces <= 1 "
                "AND t_min < ? AND COALESCE(ultimo_acceso, t_min) < ?",
                (self.habitante_id, int(t_ahora - 10 * MIN_DIA), int(t_ahora - 5 * MIN_DIA))).rowcount
            exceso = self.contar() - MAX_POR_HABITANTE
            c2 = 0
            if exceso > 0:      # tope duro: se van primero los episodios más flojos y viejos
                c2 = self._con.execute(
                    "DELETE FROM memorias WHERE id IN (SELECT id FROM memorias WHERE habitante_id = ? AND tipo = 'episodica' "
                    "ORDER BY importancia + 0.05 * veces ASC, t_min ASC LIMIT ?)", (self.habitante_id, exceso)).rowcount
        return c1 + c2

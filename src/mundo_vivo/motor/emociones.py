"""
Personalidad y emociones de las personas.

Personalidad plástica: las experiencias mueven los rasgos heredados dentro de un margen (±0.25), y al cruzar
umbrales (0.3 / 0.7) cambia cómo se describe a la persona. Las emociones son 4 canales (miedo, tristeza,
alegria, enojo) que suben con lo que pasa y decaen con el tiempo (vida media 2 horas del mundo).

`sabe(h, receta_id)` consulta si una persona conoce una receta. Está indexada por receta para no recorrer
todo lo que sabe cada vez (se llama cientos de miles de veces por mundo simulado).
"""
from __future__ import annotations

from typing import Dict, List, Optional

CANALES = ("miedo", "tristeza", "alegria", "enojo")
VIDA_MEDIA_EMOCION_MIN = 120.0


def _genero(h, masc: str, fem: str) -> str:
    return fem if h.sexo == "F" else masc


class EmocionesMixin:
    # --------------------------------------------------------- personalidad plástica
    def _tabla_experiencias(self) -> dict:
        """Qué experiencia mueve qué rasgo, y cuánto. Dato de datos_base/cultura/experiencias.json."""
        if not hasattr(self, "_exp"):
            self._exp = dict(self.registro.de_tipo("experiencia"))
        return self._exp

    def experiencia(self, h, id_: str) -> None:
        """Aplica una experiencia con nombre."""
        d = self._tabla_experiencias().get(id_)
        if d is None:
            return
        motivo = d.get("motivo", id_)
        for rasgo, delta in (d.get("mueve") or {}).items():
            self.moldear(h, rasgo, float(delta), motivo)

    def moldear(self, h, rasgo: str, delta: float, motivo: str = "") -> None:
        """La experiencia corre un poco el carácter (nunca más de ±0.25 de lo heredado)."""
        g = h.genoma
        if g is None or rasgo not in g.rasgos or not h.vivo or not self.modulo("personalidad"):
            return
        base = g.rasgos[rasgo]
        antes = h.rasgo(rasgo)
        nuevo = max(0.0, min(1.0, max(base - 0.25, min(base + 0.25, antes + delta))))
        if nuevo == antes:
            return
        if not h.rasgos_vivos:
            h.rasgos_vivos = dict(g.rasgos)
        h.rasgos_vivos[rasgo] = nuevo
        banda = lambda v: 2 if v >= 0.7 else 0 if v <= 0.3 else 1
        if banda(nuevo) != banda(antes):
            txt = {"audacia": ("más temeroso", "más audaz"), "cautela": ("más impulsivo", "más cauteloso"), "sociabilidad": ("más solitario", "más sociable"),
                   "curiosidad": ("más conformista", "más curioso"), "agresividad": ("más pacífico", "más combativo"),
                   "empatia": ("menos empático", "más empático"), "resiliencia": ("más frágil", "más resistente")}[rasgo][1 if nuevo > antes else 0]
            self._evento("personalidad", "%s se volvió %s%s." % (h.nombre, txt, (" (" + motivo + ")") if motivo else ""), h, importancia=3,
                         causa=motivo or "experiencia")
            self._recuerdo(h, "Sentís que cambiaste: ahora sos %s." % txt, 0.8, "semantica")

    # ---------------------------------------------------------- emociones
    def sentir(self, h, canal: str, cantidad: float) -> None:
        if canal not in h.emo or not self.modulo("emociones"):
            return
        k = 1.0
        g = h.genoma
        if g is not None:
            r = {k: h.rasgo(k) for k in g.rasgos}
            if canal in ("miedo", "tristeza"):
                k = 1.4 - 0.8 * r.get("resiliencia", 0.5)
                if canal == "miedo":
                    k *= 1.2 - 0.5 * r.get("audacia", 0.5)
                else:
                    k *= 0.7 + 0.6 * r.get("empatia", 0.5)
            elif canal == "enojo":
                k = 0.6 + 0.8 * r.get("agresividad", 0.5)
            elif canal == "alegria":
                k = 0.7 + 0.6 * r.get("sociabilidad", 0.5)
        h.emo[canal] = min(1.0, h.emo[canal] + cantidad * k)

    def _decaer_emociones(self, h, paso: float) -> None:
        f = 0.5 ** (paso / VIDA_MEDIA_EMOCION_MIN)
        for c in CANALES:
            h.emo[c] *= f
            if h.emo[c] < 0.01:
                h.emo[c] = 0.0

    def etiqueta_emocion(self, h) -> str:
        c = max(CANALES, key=lambda k: h.emo[k])
        v = h.emo[c]
        if v < 0.25:
            return "tranquilo" if h.sexo == "M" else "tranquila"
        palabra = {"miedo": _genero(h, "asustado", "asustada"), "tristeza": "triste",
                   "alegria": _genero(h, "contento", "contenta"), "enojo": _genero(h, "enojado", "enojada")}[c]
        return ("muy " if v >= 0.6 else "") + palabra

    # ---------------------------------------------------------- conoce receta
    def sabe(self, h, receta_id: str) -> bool:
        """¿Esta persona sabe hacer esta receta? Índice por receta para no recorrer todo lo que sabe."""
        if getattr(self, "_idx_recetas_n", -1) != len(self.conocimientos):
            idx: dict = {}
            for cid, c in self.conocimientos.items():
                rid = (c or {}).get("receta_id")
                if rid:
                    idx.setdefault(rid, set()).add(cid)
            self._idx_recetas = idx
            self._idx_recetas_n = len(self.conocimientos)
        cids = self._idx_recetas.get(receta_id)
        return bool(cids) and not cids.isdisjoint(h.conoce)

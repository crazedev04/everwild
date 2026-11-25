"""
Plantas que mueven la cabeza: psicoactivos, venenos que delirán, hongos que abren la percepción.

Es contenido puro, igual que un alimento: cada planta declara qué le hace a quien la come y cuánto dura.
El motor no conoce ninguna por su nombre.

    "psicoactivo": {
      "dura_min": 300,
      "nombre_efecto": "el mundo late y los colores gritan",
      "emociones": {"alegria": 0.5, "miedo": 0.25},
      "rasgos": {"curiosidad": 0.2, "cautela": -0.15},
      "alucina": 0.35,
      "inventiva": 0.4,
      "riesgo": 0.1
    }

Lo importante: **una alucinación es un recuerdo con procedencia `inferido` y certeza baja** (ver la fase I).
La persona recuerda algo que nunca pasó, lo cuenta como si fuera cierto, y el que la escucha lo recibe como
rumor. Así una visión puede volverse leyenda sin que nadie mienta y sin que el motor haga trampa: el
sistema sabe de dónde salió cada cosa y nunca la presenta como un hecho comprobado.

Los rasgos se mueven de forma TEMPORAL (vuelven solos al pasar el efecto): un viaje no te cambia el carácter
para siempre, aunque lo que recordás de él sí se queda.
"""
from __future__ import annotations

from typing import Dict, List, Optional

VISIONES = (
    "Viste el cielo abrirse y algo enorme mirándote desde arriba.",
    "Las piedras te hablaron con la voz de alguien que ya no está.",
    "Caminaste por un lugar que no existe, lleno de luces bajo la tierra.",
    "Viste a los animales hablar entre ellos y entendiste lo que decían.",
    "El río corría para arriba y del otro lado había gente esperándote.",
    "Alguien que murió se sentó al lado tuyo y no dijo nada.",
    "Viste cómo era este lugar antes de que existiera nadie.",
)


class PsiqueMixin:
    # ------------------------------------------------------------- datos
    def _compilar_psicoactivos(self) -> None:
        self.psicoactivos: Dict[str, dict] = {}
        for col in ("material", "item"):
            for iid, d in self.registro.de_tipo(col).items():
                if d.get("psicoactivo"):
                    self.psicoactivos[iid] = d["psicoactivo"]

    def bajo_efecto(self, h) -> Optional[dict]:
        """El efecto que tiene encima ahora, o None."""
        v = getattr(h, "viaje", None)
        return v if v and self.t < v.get("hasta", 0) else None

    # ---------------------------------------------------------- tomarlo
    def aplicar_psicoactivo(self, h, item: str) -> Optional[str]:
        """Lo toma. Devuelve qué siente, o None si eso no hace nada."""
        d = self.psicoactivos.get(item)
        if d is None or not self.modulo("psique"):
            return None
        h.viaje = {"item": item, "hasta": self.t + float(d.get("dura_min", 240)),
                   "rasgos": dict(d.get("rasgos") or {}), "prox_vision": self.t + 20.0}
        for canal, v in (d.get("emociones") or {}).items():
            self.sentir(h, canal, float(v))
        for rasgo, delta in (d.get("rasgos") or {}).items():
            self._mover_rasgo_temporal(h, rasgo, float(delta))
        if float(d.get("riesgo", 0)) > 0 and self.rng.random() < float(d["riesgo"]):
            h.salud -= self.rng.uniform(5.0, 15.0)
            self._evento("enfermo", "%s se puso muy mal después de comer %s." % (h.nombre, item), h,
                         causa="una planta fuerte", importancia=3)
        texto = d.get("nombre_efecto") or "todo se vuelve raro"
        self._recuerdo(h, "Comiste %s y %s." % (item, texto), 0.7, "episodica")
        self._evento("viaje", "%s comió %s y empezó a ver cosas." % (h.nombre, item), h, importancia=3,
                     datos={"item": item})
        return texto

    def _mover_rasgo_temporal(self, h, rasgo: str, delta: float) -> None:
        """Mueve un rasgo mientras dura el efecto. No toca el genoma: al pasar vuelve solo."""
        g = h.genoma
        if g is None or rasgo not in g.rasgos:
            return
        if not h.rasgos_vivos:
            h.rasgos_vivos = dict(g.rasgos)
        h.rasgos_vivos[rasgo] = max(0.0, min(1.0, h.rasgos_vivos[rasgo] + delta))

    # ------------------------------------------------------------- paso
    def _paso_psique(self, h, paso: float) -> None:
        if not self.modulo("psique"):
            return
        v = getattr(h, "viaje", None)
        if not v:
            return
        if self.t >= v.get("hasta", 0):
            for rasgo, delta in (v.get("rasgos") or {}).items():       # se deshace el corrimiento
                self._mover_rasgo_temporal(h, rasgo, -float(delta))
            self._recuerdo(h, "Se te pasó el efecto de %s. Volviste en vos." % v.get("item"), 0.4)
            h.viaje = None
            return
        d = self.psicoactivos.get(v.get("item")) or {}
        if self.t >= v.get("prox_vision", 0):
            v["prox_vision"] = self.t + self.rng.uniform(40.0, 120.0)
            if self.rng.random() < float(d.get("alucina", 0)):
                self._alucinar(h)

    def _alucinar(self, h) -> None:
        """Una visión queda como recuerdo INFERIDO con certeza baja: la persona la va a recordar, pero el
        sistema sabe que no la vivió. Si la cuenta, el que escucha la recibe como rumor."""
        texto = self.rng.choice(VISIONES)
        self._recuerdo(h, texto, 0.75, "episodica", origen="inferido", certeza=0.2)
        self.sentir(h, "miedo", 0.15)

    # ------------------------------------------------------- en el prompt
    def describir_viaje(self, h) -> str:
        v = self.bajo_efecto(h)
        if not v:
            return ""
        d = self.psicoactivos.get(v.get("item")) or {}
        return d.get("nombre_efecto") or "todo se ve raro y no estás seguro de lo que ves"

    def bono_inventiva(self, h) -> float:
        """Cuánto empuja a probar ideas nuevas mientras dura el efecto."""
        v = self.bajo_efecto(h)
        if not v:
            return 0.0
        return float((self.psicoactivos.get(v.get("item")) or {}).get("inventiva", 0.0))

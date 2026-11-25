"""
LOD cognitivo: no todos piensan igual al mismo tiempo.

El modelo de lenguaje es el cuello de botella del proyecto: una consulta tarda segundos y el mundo tiene que
esperarla (ver `tope_pensando` en api/vivo.py). Con 4 personas se banca; con 25 no, y con 60 menos.

Tres niveles, como pide docs/arquitectura/ en su sección 6:

  1. EN FOCO    — piensa con el modelo. Son pocos a la vez y se van turnando.
  2. SEGUNDO PLANO — reflejos, hábitos y objetivos. Decide igual, sin consultar al modelo.
  3. LEJOS      — avanza igual (necesidades, posición) pero no delibera. Al volver al foco retoma coherente.

Quién está en foco NO lo decide la cámara: lo decide la **urgencia**. Quien se está muriendo de sed, el que
acaba de ver algo importante o el que está hablando con alguien tienen prioridad sobre el que camina solo
hace tres días. Y hay rotación: nadie se queda sin pensar para siempre.
"""
from __future__ import annotations

from typing import Dict, List

CUPO_BASE = 4                # cuántos pueden usar el modelo a la vez
ESPERA_MAX_MIN = 2880.0      # dos días del mundo sin pensar: pasa al frente sí o sí
MIN_DIA = 1440.0


class AtencionMixin:
    def _compilar_atencion(self) -> None:
        self.ultimo_pensado: Dict[int, float] = {}
        self._foco: set = set()
        self._foco_hasta = 0.0

    # -------------------------------------------------------- prioridad
    def urgencia_cognitiva(self, h) -> float:
        """Cuánto le conviene al mundo que ESTA persona piense ahora."""
        u = 0.0
        u += max(0.0, h.sed - 50.0) / 50.0 * 3.0
        if self.modulo("hambre"):
            u += max(0.0, h.hambre - 50.0) / 50.0 * 2.5
        u += max(0.0, 40.0 - h.energia) / 40.0 * 1.2
        u += max(0.0, 60.0 - h.salud) / 60.0 * 2.0
        if h.mensajes:                       # le hablaron y no contestó
            u += 2.5
        if h.propuesta:                      # le propusieron formar familia
            u += 3.0
        if self.percibir(h)["cercanos"]:     # hay gente al lado: es cuando pasan las cosas
            u += 1.0
        if self.modulo("psique") and self.bajo_efecto(h):
            u += 0.8
        espera = self.t - self.ultimo_pensado.get(h.id, -ESPERA_MAX_MIN)
        u += min(3.0, espera / ESPERA_MAX_MIN * 3.0)      # el que hace rato que no piensa sube solo
        return u

    def nivel_cognitivo(self, h) -> int:
        """1 = piensa con el modelo, 2 = reflejos y hábitos, 3 = sólo sigue vivo."""
        if not self.modulo("atencion"):
            return 1
        if h.id in self._foco:
            return 1
        espera = self.t - self.ultimo_pensado.get(h.id, 0.0)
        if espera > 6 * MIN_DIA and not self.percibir(h)["cercanos"]:
            return 3                          # hace una semana que nadie lo ve ni le pasa nada
        return 2

    def repartir_atencion(self) -> None:
        """Elige quién está en foco. Se rehace cada tanto, no en cada tick."""
        if not self.modulo("atencion") or self.t < self._foco_hasta:
            return
        self._foco_hasta = self.t + 120.0            # dos horas del mundo con el mismo reparto
        vivos = [h for h in self.habitantes.values() if h.vivo and self.es_adulto(h)]
        if not vivos:
            self._foco = set()
            return
        cupo = max(1, min(CUPO_BASE, len(vivos)))
        vivos.sort(key=lambda h: -self.urgencia_cognitiva(h))
        self._foco = {h.id for h in vivos[:cupo]}
        for hid in self._foco:
            self.ultimo_pensado[hid] = self.t

    def resumen_atencion(self) -> dict:
        """Para el visor: cuántos hay en cada nivel."""
        n = {1: 0, 2: 0, 3: 0}
        for h in self.habitantes.values():
            if h.vivo:
                n[self.nivel_cognitivo(h)] += 1
        return {"foco": n[1], "fondo": n[2], "lejos": n[3]}

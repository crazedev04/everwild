"""
Fenómenos como datos: meteoritos, plagas, lo que se te ocurra.

El contrato (el mismo de Factorio): los **tipos de efecto son primitivas de código**, las **combinaciones son
datos**. Agregar un fenómeno nuevo es un JSON; agregar una primitiva nueva sí es código, y cada una que se
suma queda disponible para siempre. Eso está documentado en docs/DATOS.md porque es la única promesa que
este diseño puede cumplir de verdad.

    {"type":"fenomeno","id":"meteorito",
     "disparador":{"prob_por_dia":0.004,"desde_dia":30},
     "lugar":{"intentos":40,"en_tierra":true},
     "efectos":[{"tipo":"marca","clave":"crater","radio_m":120},
                {"tipo":"sembrar","material":"hierro_del_cielo","radio_m":250,"cantidad":6},
                {"tipo":"encender_fuego","radio_m":60,"prob":0.8},
                {"tipo":"dano_area","radio_m":90,"dano":60,"causa":"algo que cayó del cielo"},
                {"tipo":"evento","texto":"Algo cayó del cielo.","importancia":5},
                {"tipo":"recuerdo","radio_m":4000,"texto":"Viste caer algo del cielo.","importancia":0.95}]}

LÍMITE CONOCIDO: el terreno (elevación y bioma) se guarda una sola vez al crear el mundo y lleva un hash de
integridad, así que un efecto NO puede excavar el mapa sin invalidarlo. El cráter se guarda como una marca
aparte (`self.marcas`), que persiste y la ve el visor. Cambiar eso requiere reescribir los chunks tocados y
recalcular el hash: está anotado como trabajo de la fase E en el plan.
"""
from __future__ import annotations

import math
from typing import Dict, List

MIN_DIA = 1440.0


class FenomenosMixin:
    # ------------------------------------------------------------- datos
    def _compilar_fenomenos(self) -> None:
        self.fenomenos: Dict[str, dict] = dict(self.registro.de_tipo("fenomeno"))
        self.marcas: List[dict] = getattr(self, "marcas", [])        # cráteres y demás, persistidos
        self.depositos: Dict[str, float] = getattr(self, "depositos", {})   # "zx,zy,material" -> extra
        self._acum_fen = 0.0

    # -------------------------------------------------------------- paso
    def _paso_fenomenos(self, paso: float) -> None:
        if not self.fenomenos or not self.modulo("fenomenos"):
            return
        self._acum_fen += paso
        if self._acum_fen < 60.0:          # se revisa una vez por hora del mundo, no cada tick
            return
        dt, self._acum_fen = self._acum_fen, 0.0
        dia = self.t / MIN_DIA
        for f in self.fenomenos.values():
            d = f.get("disparador") or {}
            if dia < float(d.get("desde_dia", 0)):
                continue
            if self.rng.random() >= float(d.get("prob_por_dia", 0)) * dt / MIN_DIA:
                continue
            self._disparar_fenomeno(f)

    def _buscar_lugar(self, f: dict):
        cfg = f.get("lugar") or {}
        t = self.terreno
        for _ in range(int(cfg.get("intentos", 30))):
            x = self.rng.randrange(t.ancho)
            y = self.rng.randrange(t.alto)
            if cfg.get("en_tierra", True) and (t.agua[y, x] or not t.caminable(x, y)):
                continue
            return x, y
        return None

    def _disparar_fenomeno(self, f: dict) -> None:
        punto = self._buscar_lugar(f)
        if punto is None:
            return
        x, y = punto
        for e in f.get("efectos") or []:
            self._efecto_fenomeno(f, e, x, y)

    # --------------------------------------------------- primitivas de efecto
    def _efecto_fenomeno(self, f: dict, e: dict, x: int, y: int) -> None:
        tipo = e.get("tipo")
        radio = self.celdas(float(e.get("radio_m", 0)), minimo=0.0)
        if tipo == "marca":
            self.marcas.append({"clave": e.get("clave", f["id"]), "x": x + 0.5, "y": y + 0.5,
                                "r": round(radio, 1), "t": int(self.t)})
            if len(self.marcas) > 300:
                del self.marcas[:-300]
        elif tipo == "sembrar":
            # No se toca el terreno (lleva hash de integridad): se deja un depósito que `restante()` suma.
            mat = e.get("material")
            n = float(e.get("cantidad", 1))
            paso = max(1, self.zona)
            for zx in range(int((x - radio) // paso), int((x + radio) // paso) + 1):
                for zy in range(int((y - radio) // paso), int((y + radio) // paso) + 1):
                    k = "%d,%d,%s" % (zx, zy, mat)
                    self.depositos[k] = self.depositos.get(k, 0.0) + n
        elif tipo == "encender_fuego":
            if self.rng.random() < float(e.get("prob", 1.0)):
                self.encender(x, y, origen="sistema")
        elif tipo == "dano_area":
            for h in self.habitantes.values():
                if h.vivo and math.hypot(h.x - x, h.y - y) <= radio:
                    self._dano(h, float(e.get("dano", 10)), e.get("causa", f["id"]), "herida",
                               "%s fue alcanzado por %s." % (h.nombre, f.get("nombre", f["id"])))
        elif tipo == "evento":
            self._evento(f["id"], str(e.get("texto", "")), x=x + 0.5, y=y + 0.5,
                         importancia=int(e.get("importancia", 3)), origen="sistema")
        elif tipo == "recuerdo":
            for h in self.habitantes.values():
                if h.vivo and math.hypot(h.x - x, h.y - y) <= radio:
                    self._recuerdo(h, str(e.get("texto", "")), float(e.get("importancia", 0.7)))

    # --------------------------------------------------------- persistencia
    def exportar_fenomenos(self) -> dict:
        return {"marcas": self.marcas, "depositos": {k: round(v, 2) for k, v in self.depositos.items()}}

    def importar_fenomenos(self, d: dict) -> None:
        self.marcas = list(d.get("marcas") or [])
        self.depositos = {k: float(v) for k, v in (d.get("depositos") or {}).items()}

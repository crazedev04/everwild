#!/usr/bin/env python3
"""
Mundo Vivo - Fase 0.5: prueba del cerebro.

Mini-mundo de texto con 4 habitantes que deciden con un modelo de Ollama.
Mide si el modelo (por ejemplo qwen3.5:4b) sirve como cerebro:
  - velocidad (latencia, tokens/seg, VRAM)
  - fiabilidad (JSON valido, acciones validas)
  - calidad (atiende sed/hambre/sueno, sobrevive, no entra en bucles)
  - cuanto tiempo simulado puede avanzar por cada minuto real

Solo usa la libreria estandar de Python (no hay que instalar nada).

Uso rapido:
    python3 prueba_cerebro.py                      # 48 horas simuladas, qwen3.5:4b
    python3 prueba_cerebro.py --horas 12           # prueba corta
    python3 prueba_cerebro.py --modelo qwen2.5:7b  # comparar otro modelo
"""
from __future__ import annotations

import argparse
import heapq
import json
import os
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

# --------------------------------------------------------------------------
# Mini-mundo
# --------------------------------------------------------------------------

LUGARES = {
    "campamento": {"desc": "un claro de tierra seca, sin refugio", "recursos": {}, "refugio": False},
    "rio": {"desc": "un rio de agua dulce y clara", "recursos": {"agua": None}, "refugio": False},
    "bosque_frutal": {"desc": "un bosque con arbustos de frutos", "recursos": {"frutos": (12, 60)}, "refugio": False},
    "pradera": {"desc": "una pradera abierta con raices comestibles", "recursos": {"raices": (8, 90)}, "refugio": False},
    "colina": {"desc": "una colina rocosa con buena vista", "recursos": {}, "refugio": False},
    "cueva": {"desc": "una cueva seca y resguardada", "recursos": {}, "refugio": True},
}
# (a, b, minutos de camino)
CAMINOS = [
    ("campamento", "rio", 10),
    ("campamento", "bosque_frutal", 15),
    ("campamento", "pradera", 20),
    ("pradera", "colina", 25),
    ("bosque_frutal", "cueva", 20),
    ("rio", "cueva", 30),
]
VISIBLE_HASTA_MIN = 15  # vecinos a <= 15 min se ven; los demas hay que descubrirlos explorando
UNIDADES_COMIDA = {"frutos": 18, "raices": 10}  # cuanto baja el hambre por unidad

ACCIONES = ["ir_a", "beber", "comer", "dormir", "explorar", "esperar", "hablar"]

PERSONALIDADES = [
    ("Ayla", "curiosa y audaz; le gusta explorar y probar cosas nuevas"),
    ("Bruno", "cauteloso y prudente; prefiere asegurar agua y comida antes de arriesgarse"),
    ("Celia", "sociable y atenta; le importa que el grupo este bien y comparte lo que descubre"),
    ("Dante", "practico y reservado; trabaja solo y habla poco"),
]


def vecinos(lugar):
    for a, b, d in CAMINOS:
        if a == lugar:
            yield b, d
        elif b == lugar:
            yield a, d


def ruta_mas_corta(origen, destino):
    dist = {origen: 0}
    previo = {}
    cola = [(0, origen)]
    while cola:
        d, u = heapq.heappop(cola)
        if u == destino:
            break
        if d > dist.get(u, 1e9):
            continue
        for v, w in vecinos(u):
            nd = d + w
            if nd < dist.get(v, 1e9):
                dist[v] = nd
                previo[v] = u
                heapq.heappush(cola, (nd, v))
    if destino not in dist:
        return None, None
    camino = [destino]
    while camino[-1] != origen:
        camino.append(previo[camino[-1]])
    camino.reverse()
    return camino, dist[destino]


def fmt_hora(t):
    return "dia %d, %02d:%02d" % (t // 1440 + 1, (t % 1440) // 60, t % 60)


def es_noche(t):
    m = t % 1440
    return m >= 1200 or m < 360


class Habitante:
    def __init__(self, nombre, personalidad):
        self.nombre = nombre
        self.personalidad = personalidad
        self.lugar = "campamento"
        self.t = 480  # 08:00 del dia 1
        self.hambre = 30.0   # 0 = saciado, 100 = muriendose de hambre
        self.sed = 30.0
        self.energia = 90.0  # 100 = descansado
        self.salud = 100.0
        self.vivo = True
        self.causa_muerte = ""
        self.t_muerte = None
        self.conocidos = set()
        self.memoria = []    # lista de (t, texto) - privada
        self.saberes = []    # lista de textos - privada
        self.visitados = {"campamento"}
        self.historial = []  # (accion, destino)
        self.hongos = 0      # veces que comio hongos venenosos

    def recordar(self, texto):
        self.memoria.append((self.t, texto))

    def saber(self, texto):
        if texto not in self.saberes:
            self.saberes.append(texto)


class Mundo:
    def __init__(self, semilla, nivel="normal"):
        self.rng = random.Random(semilla)
        self.nivel = nivel
        self.oculto = nivel in ("medio", "dificil")   # los lugares no se describen hasta visitarlos
        self.dificil = nivel == "dificil"
        self.mult = {"normal": 1.0, "medio": 1.3, "dificil": 1.6}[nivel]      # necesidades suben mas rapido
        self.peligro = {"normal": 1.0, "medio": 1.8, "dificil": 2.5}[nivel]   # riesgo nocturno
        self.cantidad = {}
        self.cfg = {}
        self.ultima_regen = 0
        escasos = {"dificil": {"frutos": (6, 150), "raices": (4, 240)},
                   "medio": {"frutos": (10, 100), "raices": (7, 150)}}.get(nivel, {})
        for lugar, datos in LUGARES.items():
            for rec, cfg in datos["recursos"].items():
                if rec in escasos:
                    cfg = escasos[rec]
                self.cfg[(lugar, rec)] = cfg
                self.cantidad[(lugar, rec)] = float(cfg[0]) if cfg else None
        if nivel != "normal":  # hongos venenosos: parecen comida, hay que descubrir que enferman
            self.cfg[("bosque_frutal", "hongos")] = (10, 120)
            self.cantidad[("bosque_frutal", "hongos")] = 10.0

    def recursos_en(self, lugar):
        return [rec for (l, rec) in self.cfg if l == lugar]

    def regenerar(self, t):
        dt = t - self.ultima_regen
        if dt <= 0:
            return
        for (lugar, rec), q in list(self.cantidad.items()):
            cfg = self.cfg[(lugar, rec)]
            if cfg:
                self.cantidad[(lugar, rec)] = min(cfg[0], q + dt / cfg[1])
        self.ultima_regen = t

    def disponible(self, lugar, rec):
        if (lugar, rec) not in self.cantidad:
            return 0
        q = self.cantidad[(lugar, rec)]
        return 10 ** 6 if q is None else int(q)

    def descubrir_vecinos(self, h):
        for v, d in vecinos(h.lugar):
            if d <= VISIBLE_HASTA_MIN:
                h.conocidos.add(v)
        h.conocidos.add(h.lugar)

    def avanzar(self, h, minutos, dormido=False):
        """Pasa el tiempo para un habitante: necesidades, peligros y muerte."""
        eventos = []
        restante = minutos
        en_refugio = LUGARES[h.lugar]["refugio"]
        while restante > 0 and h.vivo:
            paso = min(5, restante)
            restante -= paso
            if dormido:
                h.energia = min(100, h.energia + paso * (0.15 if en_refugio else 0.08))
                h.hambre = min(100, h.hambre + paso * 0.04 * self.mult)
                h.sed = min(100, h.sed + paso * 0.07 * self.mult)
            else:
                h.energia = max(0, h.energia - paso * 0.05 * self.mult)
                h.hambre = min(100, h.hambre + paso * 0.07 * self.mult)
                h.sed = min(100, h.sed + paso * 0.11 * self.mult)
            # peligros nocturnos a la intemperie
            if es_noche(h.t) and not en_refugio:
                p = (0.25 if dormido else 0.10) / 60 * paso * self.peligro
                if self.rng.random() < p:
                    dano = 18 if dormido else 12
                    h.salud -= dano
                    eventos.append("De noche, a la intemperie, algo te ataco o te lastimaste (-%d salud)." % dano)
            # consecuencias de necesidades
            if h.hambre >= 90:
                h.salud -= paso * 0.3
            if h.sed >= 90:
                h.salud -= paso * 0.3
            if h.energia <= 5:
                h.salud -= paso * 0.1
            if h.hambre < 60 and h.sed < 60 and h.energia > 30 and h.salud < 100:
                h.salud = min(100, h.salud + paso * 0.05)
            h.t += paso
            if h.salud <= 0:
                h.vivo = False
                h.t_muerte = h.t
                if h.sed >= 90:
                    h.causa_muerte = "sed"
                elif h.hambre >= 90:
                    h.causa_muerte = "hambre"
                elif h.energia <= 5:
                    h.causa_muerte = "agotamiento"
                else:
                    h.causa_muerte = "heridas"
        return eventos


# --------------------------------------------------------------------------
# Percepcion y prompt
# --------------------------------------------------------------------------

SISTEMA = (
    "Eres un habitante de un mundo salvaje. Acabas de despertar en un lugar desconocido, "
    "sin casa ni herramientas, y quieres sobrevivir. Sabes que el cuerpo necesita agua, comida y descanso. "
    "No conoces nada mas del mundo que lo que ves, lo que recuerdas y lo que te cuentan. "
    "En cada turno eliges UNA accion y respondes SOLO con un objeto JSON.\n"
    "Acciones posibles:\n"
    "- ir_a: caminar a un lugar que conozcas (campo destino).\n"
    "- beber: beber agua (solo si aqui hay agua).\n"
    "- comer: comer algo de aqui (campo objeto: frutos o raices).\n"
    "- dormir: dormir (campo duracion_min, entre 60 y 480).\n"
    "- explorar: buscar lugares nuevos cerca de donde estas.\n"
    "- esperar: quedarte quieto un rato.\n"
    "- hablar: decir algo a quien este aqui (campo mensaje).\n"
    "Campos no usados: destino y objeto con \"\", duracion_min con 0, mensaje con \"\". "
    "El campo pensamiento es una frase corta con tu razon. Actua segun tu personalidad."
)

SISTEMA_V2 = (
    "Eres un habitante de un mundo salvaje. Acabas de despertar en un lugar desconocido, "
    "sin casa ni herramientas, y quieres seguir con vida. Tu cuerpo te avisa cuando necesita agua, comida o descanso. "
    "No conoces nada mas del mundo que lo que ves, lo que recuerdas y lo que te cuentan. "
    "Cada vez que decides, eliges UNA accion de las que puedes hacer ahora.\n"
    "Acciones: ir_a (destino: un lugar que conozcas), beber, comer (objeto: lo que quieras comer de aqui), "
    "dormir (duracion_min entre 60 y 480), explorar, esperar, hablar (mensaje: lo que dices a quien esta aqui).\n"
    "Lo que no uses dejalo vacio (\"\" o 0). En pensamiento escribe tu razon en una frase corta (maximo 15 palabras). "
    "Actua segun tu personalidad."
)
PROMPT_VERSION = "v2"

ESQUEMA = {
    "type": "object",
    "properties": {
        "pensamiento": {"type": "string"},
        "accion": {"type": "string", "enum": ACCIONES},
        "destino": {"type": "string"},
        "objeto": {"type": "string"},
        "duracion_min": {"type": "integer"},
        "mensaje": {"type": "string"},
    },
    "required": ["pensamiento", "accion", "destino", "objeto", "duracion_min", "mensaje"],
}


def etiqueta(v):
    """Valor 0..100 donde alto = peor, en palabras (los modelos chicos leen mejor las palabras)."""
    return "bien" if v < 30 else "algo" if v < 55 else "mucha" if v < 80 else "CRITICA"


def acciones_posibles(mundo, h, otros):
    out = []
    if mundo.disponible(h.lugar, "agua") > 0:
        out.append("beber agua")
    comida = [r for r in mundo.recursos_en(h.lugar) if r != "agua" and mundo.disponible(h.lugar, r) > 0]
    if comida:
        out.append("comer (%s)" % ", ".join(comida))
    out.append("dormir (aqui hay refugio)" if LUGARES[h.lugar]["refugio"]
               else "dormir (a la intemperie, de noche es peligroso)")
    out += ["explorar", "esperar"]
    if otros:
        out.append("hablar con %s" % ", ".join(otros))
    destinos = sorted(c for c in h.conocidos if c != h.lugar)
    if destinos:
        out.append("ir_a (%s)" % ", ".join(destinos))
    return out


def construir_prompt(mundo, h, todos):
    lugar = LUGARES[h.lugar]
    aqui = []
    for rec in mundo.recursos_en(h.lugar):
        n = mundo.disponible(h.lugar, rec)
        if rec == "agua":
            aqui.append("agua para beber (abundante)")
        elif n > 0:
            aqui.append("%s (%d disponibles)" % (rec, n))
        else:
            aqui.append("%s (ya no quedan, se estan agotando)" % rec)
    conocidos = []
    for c in sorted(h.conocidos):
        if c == h.lugar:
            continue
        _, d = ruta_mas_corta(h.lugar, c)
        if mundo.oculto and c not in h.visitados:
            conocidos.append("%s (a %d min): todavia no lo visitaste, no sabes que hay" % (c, d))
        else:
            conocidos.append("%s (a %d min): %s" % (c, d, LUGARES[c]["desc"]))
    presentes = [o.nombre for o in todos if o is not h and o.vivo and o.lugar == h.lugar]
    ultimos = [("[%s] %s" % (fmt_hora(t), x)) for t, x in h.memoria[-6:]]
    partes = [
        "Eres %s, %s." % (h.nombre, h.personalidad),
        "Ahora es %s (%s)." % (fmt_hora(h.t), "de noche" if es_noche(h.t) else "de dia"),
        ("Estado: hambre %d/100 (0=saciado), sed %d/100 (0=sin sed), energia %d/100 (100=descansado), salud %d/100."
         % (h.hambre, h.sed, h.energia, h.salud)) if PROMPT_VERSION == "v1" else
        ("Tu cuerpo: sed %d/100 (%s), hambre %d/100 (%s), cansancio %d/100 (%s), salud %d/100."
         % (h.sed, etiqueta(h.sed), h.hambre, etiqueta(h.hambre), 100 - h.energia, etiqueta(100 - h.energia), h.salud)),
        "Lugar actual: %s, %s. Refugio: %s." % (h.lugar, lugar["desc"], "si" if lugar["refugio"] else "no"),
        "Aqui hay: %s." % (", ".join(aqui) if aqui else "nada util a la vista"),
        "Lugares que conoces: %s." % ("; ".join(conocidos) if conocidos else "ninguno"),
        "Personas aqui: %s." % (", ".join(presentes) if presentes else "nadie"),
        "Lo que has aprendido: %s" % (" | ".join(h.saberes) if h.saberes else "nada todavia."),
        "Tus ultimos recuerdos:\n%s" % ("\n".join(ultimos) if ultimos else "(ninguno)"),
        "Elige tu proxima accion.",
    ]
    if PROMPT_VERSION == "v2":
        partes.insert(-1, "Ahora puedes: %s." % "; ".join(acciones_posibles(mundo, h, presentes)))
    return "\n".join(partes)


# --------------------------------------------------------------------------
# Ejecucion de acciones (decide el motor, no el modelo)
# --------------------------------------------------------------------------

def ejecutar(mundo, h, todos, dec):
    """Aplica la decision. Devuelve (ok, texto_resultado, minutos_gastados)."""
    acc = dec["accion"]
    eventos = []
    ok = True
    texto = ""
    t0 = h.t
    mundo.regenerar(h.t)

    if acc == "ir_a":
        destino = str(dec.get("destino", "")).strip().lower()
        if destino not in LUGARES:
            ok, texto = False, "Rechazada: '%s' no es un lugar que conozcas." % destino
        elif destino not in h.conocidos:
            ok, texto = False, "Rechazada: todavia no sabes como llegar a %s." % destino
        elif destino == h.lugar:
            ok, texto = False, "Rechazada: ya estas en %s." % destino
        else:
            camino, minutos = ruta_mas_corta(h.lugar, destino)
            eventos += mundo.avanzar(h, minutos)
            if h.vivo:
                for nodo in camino[1:]:
                    h.lugar = nodo
                    mundo.descubrir_vecinos(h)
                h.visitados.add(destino)
                texto = "Caminaste hasta %s (%d min)." % (destino, minutos)
    elif acc == "beber":
        if mundo.disponible(h.lugar, "agua") <= 0:
            ok, texto = False, "Rechazada: aqui no hay agua."
        else:
            eventos += mundo.avanzar(h, 5)
            if h.vivo:
                h.sed = max(0, h.sed - 45)
                texto = "Bebiste agua. Sed ahora %d." % h.sed
                h.saber("En %s se puede beber agua." % h.lugar)
    elif acc == "comer":
        objeto = str(dec.get("objeto", "")).strip().lower()
        disp = mundo.disponible(h.lugar, objeto) if objeto in UNIDADES_COMIDA else 0
        if objeto == "hongos" and mundo.disponible(h.lugar, "hongos") > 0:
            mundo.cantidad[(h.lugar, "hongos")] -= 1
            eventos += mundo.avanzar(h, 5)
            if h.vivo:
                h.hongos += 1
                h.salud -= 25
                h.hambre = max(0, h.hambre - 6)
                texto = "Comiste hongos y te sentiste muy mal: eran venenosos (-25 salud)."
                h.saber("Los hongos de %s enferman: no hay que comerlos." % h.lugar)
        elif objeto not in UNIDADES_COMIDA:
            ok, texto = False, "Rechazada: '%s' no es algo que puedas comer aqui." % objeto
        elif disp <= 0:
            ok, texto = False, "Rechazada: aqui no hay %s (o ya no quedan)." % objeto
        else:
            n = min(3, disp)
            mundo.cantidad[(h.lugar, objeto)] -= n
            eventos += mundo.avanzar(h, 5 * n)
            if h.vivo:
                h.hambre = max(0, h.hambre - UNIDADES_COMIDA[objeto] * n)
                texto = "Comiste %d de %s. Hambre ahora %d." % (n, objeto, h.hambre)
                h.saber("En %s hay %s para comer." % (h.lugar, objeto))
    elif acc == "dormir":
        dur = int(dec.get("duracion_min") or 0)
        dur = max(60, min(480, dur if dur else 240))
        eventos += mundo.avanzar(h, dur, dormido=True)
        if h.vivo:
            texto = "Dormiste %d min. Energia ahora %d." % (dur, h.energia)
            if LUGARES[h.lugar]["refugio"]:
                h.saber("En la cueva se duerme a salvo.")
    elif acc == "explorar":
        eventos += mundo.avanzar(h, 30)
        if h.vivo:
            ocultos = [(v, d) for v, d in vecinos(h.lugar) if v not in h.conocidos]
            if ocultos:
                v, d = mundo.rng.choice(ocultos)
                h.conocidos.add(v)
                texto = "Exploraste y descubriste un camino hacia %s (a %d min)." % (v, d)
            else:
                texto = "Exploraste los alrededores y no encontraste nada nuevo."
    elif acc == "esperar":
        eventos += mundo.avanzar(h, 15)
        if h.vivo:
            texto = "Esperaste un rato."
    elif acc == "hablar":
        msg = str(dec.get("mensaje", "")).strip()
        otros = [o for o in todos if o is not h and o.vivo and o.lugar == h.lugar]
        if not otros:
            ok, texto = False, "Rechazada: no hay nadie aqui con quien hablar."
        elif not msg:
            ok, texto = False, "Rechazada: no dijiste nada."
        else:
            eventos += mundo.avanzar(h, 5)
            if h.vivo:
                for o in otros:
                    o.recordar("%s te dijo: \"%s\"" % (h.nombre, msg))
                    for lugar in LUGARES:  # ensenanza social: nombrar un lugar lo hace conocido
                        if lugar in msg.lower() and lugar not in o.conocidos:
                            o.conocidos.add(lugar)
                            o.recordar("Por lo que dijo %s ahora sabes que existe %s." % (h.nombre, lugar))
                texto = "Le dijiste a %s: \"%s\"" % (", ".join(o.nombre for o in otros), msg)
    else:
        ok, texto = False, "Rechazada: accion desconocida."

    if not ok:
        mundo.avanzar(h, 5)  # equivocarse cuesta tiempo
    if not h.vivo:
        texto = (texto + " " if texto else "") + "Moriste por %s." % h.causa_muerte
    full = " ".join([texto] + eventos).strip()
    h.recordar(full)
    return ok, full, h.t - t0


# --------------------------------------------------------------------------
# Cliente de Ollama
# --------------------------------------------------------------------------

class ErrorOllama(Exception):
    pass


def http_json(url, cuerpo=None, timeout=300):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="replace")[:300]
        raise ErrorOllama("HTTP %s: %s" % (e.code, detalle))
    except urllib.error.URLError as e:
        raise ErrorOllama("No se pudo conectar: %s" % e.reason)


def llamar_modelo(args, system, user, semilla):
    cuerpo = {
        "model": args.modelo,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "think": False,
        "format": ESQUEMA,
        "keep_alive": "30m",
        "options": {
            "temperature": args.temperatura,
            "num_ctx": args.num_ctx,
            "num_predict": 300,
            "seed": semilla,
        },
    }
    t0 = time.time()
    try:
        r = http_json(args.host + "/api/chat", cuerpo)
    except ErrorOllama as e:
        if "think" in str(e).lower():  # modelos sin soporte de 'think'
            cuerpo.pop("think")
            r = http_json(args.host + "/api/chat", cuerpo)
        else:
            raise
    r["_latencia_s"] = time.time() - t0
    return r


def parsear(contenido):
    """Devuelve (dict, motivo_error)."""
    txt = re.sub(r"<think>.*?</think>", "", contenido or "", flags=re.S).strip()
    if not txt:
        return None, "respuesta vacia"
    try:
        d = json.loads(txt)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", txt, flags=re.S)
        if not m:
            return None, "no es JSON"
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None, "JSON roto"
    if not isinstance(d, dict):
        return None, "JSON no es objeto"
    if d.get("accion") not in ACCIONES:
        return None, "accion fuera de la lista: %r" % d.get("accion")
    return d, None


# --------------------------------------------------------------------------
# Metricas
# --------------------------------------------------------------------------

def necesidad_urgente(h):
    if h.sed >= 70:
        return "agua"
    if h.hambre >= 70:
        return "comida"
    if h.energia <= 25:
        return "descanso"
    return None


def necesidades_urgentes(h):
    out = []
    if h.sed >= 70: out.append("agua")
    if h.hambre >= 70: out.append("comida")
    if h.energia <= 25: out.append("descanso")
    return out


def decision_correcta(mundo, h, necesidad, dec):
    a = dec["accion"]
    destino = str(dec.get("destino", "")).strip().lower()
    if necesidad == "agua":
        return (a == "beber" and mundo.disponible(h.lugar, "agua") > 0) or \
               (a == "ir_a" and destino in LUGARES and "agua" in LUGARES[destino]["recursos"]) or \
               (a == "explorar" and not any("agua" in LUGARES[c]["recursos"] for c in h.conocidos))
    if necesidad == "comida":
        return (a == "comer") or \
               (a == "ir_a" and destino in LUGARES and any(r in UNIDADES_COMIDA for r in LUGARES[destino]["recursos"])) or \
               (a == "explorar" and not any(r in UNIDADES_COMIDA for c in h.conocidos for r in LUGARES[c]["recursos"]))
    if necesidad == "descanso":
        return a == "dormir" or (a == "ir_a" and destino in LUGARES and LUGARES[destino]["refugio"])
    return True


def percentil(valores, p):
    if not valores:
        return 0.0
    v = sorted(valores)
    k = min(len(v) - 1, int(round((p / 100) * (len(v) - 1))))
    return v[k]


def contar_bucles(historial):
    """Cuenta veces que repite la misma accion+destino 4 veces seguidas."""
    bucles, racha = 0, 1
    for i in range(1, len(historial)):
        racha = racha + 1 if historial[i] == historial[i - 1] else 1
        if racha == 4:
            bucles += 1
    return bucles


# --------------------------------------------------------------------------
# Programa principal
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Prueba del cerebro de Mundo Vivo (Fase 0.5)")
    ap.add_argument("--modelo", default="qwen3.5:4b")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST_URL", "http://localhost:11434"))
    ap.add_argument("--horas", type=float, default=48, help="horas simuladas a recorrer")
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--temperatura", type=float, default=0.7)
    ap.add_argument("--num-ctx", type=int, default=4096)
    ap.add_argument("--max-llamadas", type=int, default=2000, help="tope de seguridad")
    ap.add_argument("--nivel", choices=["normal", "medio", "dificil"], default="normal",
                    help="normal: facil | medio: comida limitada, mas peligro, hongos venenosos y lugares sin describir hasta visitarlos | dificil: casi imposible")
    ap.add_argument("--dificil", action="store_true", help="atajo de --nivel dificil")
    ap.add_argument("--prompt", choices=["v1", "v2"], default="v2",
                    help="v2 (por defecto): senales del cuerpo en palabras, acciones posibles y lenguaje del mundo; v1: el original")
    ap.add_argument("--salida", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados"))
    args = ap.parse_args()
    args.host = args.host.rstrip("/")
    if args.dificil:
        args.nivel = "dificil"
    global PROMPT_VERSION
    PROMPT_VERSION = args.prompt

    # 1) comprobar Ollama y el modelo
    print("Conectando con Ollama en %s ..." % args.host)
    try:
        tags = http_json(args.host + "/api/tags", timeout=15)
    except ErrorOllama as e:
        print("\nNo puedo hablar con Ollama (%s).\n"
              "Revisa que este corriendo (en otra terminal: 'ollama serve') y vuelve a probar." % e)
        return 2
    nombres = [m.get("name", "") for m in tags.get("models", [])]
    if args.modelo not in nombres:
        print("\nEl modelo '%s' no esta instalado. Modelos disponibles: %s" % (args.modelo, ", ".join(nombres) or "ninguno"))
        print("Instalalo con: ollama pull %s" % args.modelo)
        return 2

    # 2) calentamiento (carga el modelo en la GPU y se mide aparte)
    print("Cargando el modelo en memoria (calentamiento) ...")
    t0 = time.time()
    try:
        llamar_modelo(args, SISTEMA_V2 if PROMPT_VERSION == "v2" else SISTEMA, "Estado: hambre 10/100. Elige: esperar.", 1)
    except ErrorOllama as e:
        print("Fallo el calentamiento: %s" % e)
        return 2
    t_carga = time.time() - t0
    vram_gb = None
    try:
        ps = http_json(args.host + "/api/ps", timeout=15)
        for m in ps.get("models", []):
            if m.get("name") == args.modelo or m.get("model") == args.modelo:
                vram_gb = m.get("size_vram", 0) / 1e9
                total_gb = m.get("size", 0) / 1e9
                print("Modelo cargado: %.1f GB en total, %.1f GB en la GPU." % (total_gb, vram_gb))
    except ErrorOllama:
        pass
    print("Calentamiento: %.1f s\n" % t_carga)

    # 3) simulacion
    mundo = Mundo(args.semilla, args.nivel)
    habitantes = [Habitante(n, p) for n, p in PERSONALIDADES]
    for h in habitantes:
        if args.nivel == "dificil":
            h.hambre, h.sed, h.energia = 60.0, 60.0, 55.0
        elif args.nivel == "medio":
            h.hambre, h.sed, h.energia = 50.0, 50.0, 70.0
        mundo.descubrir_vecinos(h)
    limite = 480 + int(args.horas * 60)

    os.makedirs(args.salida, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_log = os.path.join(args.salida, "bitacora_%s.jsonl" % sello)
    ruta_rep = os.path.join(args.salida, "informe_%s.md" % sello)
    ruta_json = os.path.join(args.salida, "metricas_%s.json" % sello)

    latencias, tps, prompt_tokens, tokens_salida = [], [], [], []
    n_llamadas = n_json_malo = n_rechazadas = n_error_red = 0
    urgentes = urgentes_ok = 0
    fallos_urgentes = []
    histograma = {a: 0 for a in ACCIONES}
    motivos_json = {}
    t_inicio = time.time()

    with open(ruta_log, "w", encoding="utf-8") as log:
        while n_llamadas < args.max_llamadas:
            vivos = [h for h in habitantes if h.vivo and h.t < limite]
            if not vivos:
                break
            h = min(vivos, key=lambda x: x.t)
            mundo.regenerar(h.t)
            prompt = construir_prompt(mundo, h, habitantes)
            necesidad = necesidad_urgente(h)
            lista_urgente = necesidades_urgentes(h)

            # llamada con hasta 2 reintentos si el JSON viene mal
            dec, motivo, resp = None, None, None
            for intento in range(3):
                n_llamadas += 1
                try:
                    resp = llamar_modelo(args, SISTEMA_V2 if PROMPT_VERSION == "v2" else SISTEMA, prompt, args.semilla + n_llamadas)
                except ErrorOllama as e:
                    n_error_red += 1
                    motivo = "error de red/Ollama: %s" % e
                    continue
                latencias.append(resp["_latencia_s"])
                if resp.get("eval_duration"):
                    tps.append(resp.get("eval_count", 0) / (resp["eval_duration"] / 1e9))
                prompt_tokens.append(resp.get("prompt_eval_count", 0))
                tokens_salida.append(resp.get("eval_count", 0))
                dec, motivo = parsear(resp.get("message", {}).get("content", ""))
                if dec:
                    break
                n_json_malo += 1
                motivos_json[motivo] = motivos_json.get(motivo, 0) + 1

            if dec is None:  # el modelo fallo 3 veces: el habitante espera
                dec = {"pensamiento": "(sin respuesta valida)", "accion": "esperar", "destino": "",
                       "objeto": "", "duracion_min": 0, "mensaje": ""}
                fallback = True
            else:
                fallback = False

            histograma[dec["accion"]] += 1
            if necesidad and not fallback:
                urgentes += 1
                if any(decision_correcta(mundo, h, n, dec) for n in lista_urgente):
                    urgentes_ok += 1
                elif len(fallos_urgentes) < 10:
                    fallos_urgentes.append("[%s] %s (%s) eligio %s %s -> \"%s\"" % (
                        fmt_hora(h.t), h.nombre, "+".join(lista_urgente), dec["accion"],
                        dec.get("destino") or dec.get("objeto") or "", str(dec.get("pensamiento", ""))[:110]))
            h.historial.append((dec["accion"], str(dec.get("destino", "")) if dec["accion"] == "ir_a" else ""))
            estado_antes = (h.hambre, h.sed, h.energia, h.salud)

            ok, resultado, minutos = ejecutar(mundo, h, habitantes, dec)
            if not ok:
                n_rechazadas += 1

            log.write(json.dumps({
                "t": h.t, "hora": fmt_hora(h.t), "habitante": h.nombre,
                "estado_antes": [round(x) for x in estado_antes],
                "necesidad_urgente": necesidad, "prompt": prompt,
                "respuesta": dec, "fallback": fallback, "ok": ok, "resultado": resultado,
                "latencia_s": round(resp["_latencia_s"], 2) if resp else None,
            }, ensure_ascii=False) + "\n")

            print("[%s] %-5s %-9s %-14s %s  (%.1fs)" % (
                fmt_hora(h.t), h.nombre, dec["accion"], str(dec.get("destino") or dec.get("objeto") or ""),
                "OK" if ok else "RECHAZADA", resp["_latencia_s"] if resp else 0))
            if not h.vivo:
                print("   *** %s murio por %s ***" % (h.nombre, h.causa_muerte))

    # 4) informe
    t_real = time.time() - t_inicio
    t_sim_total = sum(min(h.t, limite) - 480 for h in habitantes)
    t_sim_promedio = t_sim_total / len(habitantes)
    vivos_fin = [h for h in habitantes if h.vivo]
    decisiones = sum(histograma.values())
    pct_json_ok = 100.0 * (1 - n_json_malo / max(1, len(latencias)))
    pct_rech = 100.0 * n_rechazadas / max(1, decisiones)
    pct_urg = 100.0 * urgentes_ok / max(1, urgentes)
    bucles = sum(contar_bucles(h.historial) for h in habitantes)
    lat_p50, lat_p95 = percentil(latencias, 50), percentil(latencias, 95)
    vel = (t_sim_promedio / 60.0) / max(1e-9, t_real / 60.0)  # horas simuladas por minuto real
    tps_prom = statistics.mean(tps) if tps else 0.0

    m = {
        "modelo": args.modelo, "horas_simuladas_objetivo": args.horas, "semilla": args.semilla,
        "llamadas_totales": n_llamadas, "decisiones": decisiones,
        "latencia_p50_s": round(lat_p50, 2), "latencia_p95_s": round(lat_p95, 2),
        "tokens_por_segundo": round(tps_prom, 1),
        "tokens_prompt_promedio": round(statistics.mean(prompt_tokens)) if prompt_tokens else 0,
        "tokens_salida_promedio": round(statistics.mean(tokens_salida)) if tokens_salida else 0,
        "tiempo_carga_s": round(t_carga, 1), "vram_gb": round(vram_gb, 1) if vram_gb is not None else None,
        "json_valido_pct": round(pct_json_ok, 1), "motivos_json_invalido": motivos_json,
        "acciones_rechazadas_pct": round(pct_rech, 1),
        "decisiones_urgentes": urgentes, "urgentes_correctas_pct": round(pct_urg, 1),
        "bucles_detectados": bucles, "errores_red": n_error_red,
        "intoxicaciones_hongos": sum(h.hongos for h in habitantes),
        "reincidencias_hongos": sum(max(0, h.hongos - 1) for h in habitantes),
        "supervivientes": len(vivos_fin),
        "habitantes": [{
            "nombre": h.nombre, "vivo": h.vivo, "causa_muerte": h.causa_muerte,
            "horas_vividas": round((min(h.t, limite) - 480) / 60, 1),
            "lugares_visitados": sorted(h.visitados), "saberes": h.saberes,
        } for h in habitantes],
        "acciones": histograma,
        "tiempo_real_s": round(t_real, 1),
        "horas_simuladas_por_minuto_real": round(vel, 2),
    }

    # veredicto simple
    problemas = []
    if pct_json_ok < 95: problemas.append("JSON valido menor al 95%%: %.1f%%" % pct_json_ok)
    if pct_rech > 25: problemas.append("demasiadas acciones imposibles: %.0f%%" % pct_rech)
    if urgentes and pct_urg < 70: problemas.append("atiende la necesidad urgente solo el %.0f%% de las veces" % pct_urg)
    if len(vivos_fin) < 3: problemas.append("sobreviven menos de 3 de 4")
    if bucles > 3: problemas.append("entra en bucles repetitivos (%d)" % bucles)
    if lat_p50 > 8: problemas.append("latencia mediana alta: %.1f s" % lat_p50)
    veredicto = ("APTO como cerebro inicial." if not problemas else
                 "NO CONCLUYENTE / MEJORABLE: " + "; ".join(problemas) + ".")
    m["veredicto"] = veredicto

    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

    filas = "\n".join(
        "| %s | %s | %.1f h | %s | %s |" % (
            h["nombre"], "vivo" if h["vivo"] else "murio (%s)" % h["causa_muerte"],
            h["horas_vividas"], len(h["lugares_visitados"]), "; ".join(h["saberes"]) or "-")
        for h in m["habitantes"])
    informe = f"""# Informe de la prueba del cerebro

- Modelo: **{args.modelo}** | Semilla: {args.semilla} | Nivel: {args.nivel.upper()} | Prompt: {args.prompt} | Fecha: {datetime.now():%Y-%m-%d %H:%M}
- Horas simuladas pedidas: {args.horas} | Tiempo real: {t_real/60:.1f} min

## Veredicto
**{veredicto}**

## Velocidad
| Medida | Valor |
|---|---|
| Latencia por decision (mediana / p95) | {lat_p50:.1f} s / {lat_p95:.1f} s |
| Tokens por segundo | {tps_prom:.1f} |
| Tokens de entrada / salida (promedio) | {m['tokens_prompt_promedio']} / {m['tokens_salida_promedio']} |
| Carga inicial del modelo | {t_carga:.1f} s |
| Memoria de GPU usada por el modelo | {m['vram_gb'] if m['vram_gb'] is not None else 'sin dato'} GB |
| Horas simuladas por minuto real (4 habitantes) | {vel:.2f} |

## Fiabilidad
| Medida | Valor | Objetivo |
|---|---|---|
| JSON valido a la primera | {pct_json_ok:.1f}% | >= 95% |
| Acciones rechazadas por el motor | {pct_rech:.1f}% | <= 25% |
| Errores de red/Ollama | {n_error_red} | 0 |

## Calidad de las decisiones
| Medida | Valor | Objetivo |
|---|---|---|
| Atiende la necesidad urgente (sed/hambre/sueno) | {pct_urg:.0f}% de {urgentes} casos | >= 70% |
| Bucles repetitivos | {bucles} | <= 3 |
| Supervivientes | {len(vivos_fin)} de 4 | >= 3 |
| Intoxicaciones con hongos (nivel medio/dificil) | {m['intoxicaciones_hongos']} | - |
| Volvio a comer hongos despues de enfermarse | {m['reincidencias_hongos']} | 0 (si es mayor, no aprende de la experiencia) |

## Decisiones urgentes que fallaron (primeras 10)
{chr(10).join('- ' + f for f in fallos_urgentes) or '(ninguna)'}

## Habitantes
| Nombre | Estado | Vivio | Lugares visitados | Lo que aprendio |
|---|---|---|---|---|
{filas}

## Acciones elegidas
{', '.join('%s: %d' % (a, n) for a, n in histograma.items())}

## Como leerlo
- Si **JSON valido** o **acciones rechazadas** salen mal, el problema es el formato del prompt o el modelo es chico.
- Si **atiende lo urgente** es bajo o hay **bucles**, el modelo razona poco: probar con otro modelo o simplificar el prompt.
- **Horas simuladas por minuto real** marca el techo de velocidad del mundo con este modelo.
- Para ver *por que* decidio cada cosa, abri `{os.path.basename(ruta_log)}` (un renglon por decision, con lo que percibio y lo que respondio).
"""
    with open(ruta_rep, "w", encoding="utf-8") as f:
        f.write(informe)

    print("\n" + "=" * 60)
    print(informe)
    print("Archivos guardados en: %s" % args.salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())

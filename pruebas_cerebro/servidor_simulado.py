#!/usr/bin/env python3
"""
Servidor falso con la misma interfaz que Ollama. SOLO para probar que
prueba_cerebro.py funciona de punta a punta sin necesitar GPU ni modelo.
No es un cerebro de verdad: usa reglas simples y a veces devuelve JSON roto
a proposito para probar el manejo de errores.

    python3 servidor_simulado.py --puerto 11555
    python3 prueba_cerebro.py --host http://localhost:11555 --modelo falso:1b
"""
import argparse
import json
import random
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

rng = random.Random(7)


def decidir(prompt):
    num = lambda pat: int(re.search(pat, prompt).group(1))
    hambre, sed = num(r"hambre (\d+)/100"), num(r"sed (\d+)/100")
    energia = num(r"energia (\d+)/100") if "energia" in prompt else 100 - num(r"cansancio (\d+)/100")
    lugar = re.search(r"Lugar actual: (\w+),", prompt).group(1)
    conocidos = re.findall(r"(\w+) \(a \d+ min\)", prompt)
    base = {"pensamiento": "decision simulada", "accion": "esperar", "destino": "", "objeto": "", "duracion_min": 0, "mensaje": ""}
    if energia <= 25:
        if lugar == "cueva":
            base.update(accion="dormir", duracion_min=300)
        elif "cueva" in conocidos:
            base.update(accion="ir_a", destino="cueva")
        else:
            base.update(accion="dormir", duracion_min=240)
    elif sed >= 45:
        if lugar == "rio":
            base.update(accion="beber")
        elif "rio" in conocidos:
            base.update(accion="ir_a", destino="rio")
        else:
            base.update(accion="explorar")
    elif hambre >= 45:
        if "frutos" in prompt.split("Aqui hay:")[1].split("\n")[0]:
            base.update(accion="comer", objeto="frutos")
        elif "bosque_frutal" in conocidos:
            base.update(accion="ir_a", destino="bosque_frutal")
        else:
            base.update(accion="explorar")
    else:
        r = rng.random()
        if r < 0.3:
            base.update(accion="explorar")
        elif r < 0.5 and "nadie" not in prompt.split("Personas aqui:")[1].split("\n")[0]:
            base.update(accion="hablar", mensaje="Hay un rio cerca y una cueva.")
        elif r < 0.55:
            base.update(accion="beber")  # a veces imposible, a proposito
        else:
            base.update(accion="esperar")
    return base


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": "falso:1b"}]})
        elif self.path == "/api/ps":
            self._send({"models": [{"name": "falso:1b", "size": 2_000_000_000, "size_vram": 2_000_000_000}]})
        else:
            self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        cuerpo = json.loads(self.rfile.read(n))
        user = cuerpo["messages"][-1]["content"]
        if ("Estado: hambre" not in user and "Tu cuerpo:" not in user) or "Lugar actual" not in user:
            contenido = json.dumps({"pensamiento": "ok", "accion": "esperar", "destino": "", "objeto": "", "duracion_min": 0, "mensaje": ""})
        elif rng.random() < 0.04:
            contenido = '{"pensamiento": "se corta'  # JSON roto a proposito
        else:
            contenido = json.dumps(decidir(user))
        self._send({
            "message": {"role": "assistant", "content": contenido},
            "prompt_eval_count": 520, "eval_count": 60, "eval_duration": 1_000_000_000,
        })


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=11555)
    a = ap.parse_args()
    print("Servidor simulado en http://localhost:%d (Ctrl+C para salir)" % a.puerto)
    HTTPServer(("127.0.0.1", a.puerto), H).serve_forever()

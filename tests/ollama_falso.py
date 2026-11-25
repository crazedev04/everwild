"""Servidor de mentira con la forma de la API de Ollama, para probar el circuito completo sin un modelo real."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def decidir(prompt: str, estado: dict) -> dict:
    alcance = re.findall(r"- (\w+) \([^)]*\), a [\d]+ celdas.*al alcance de tu voz", prompt)
    if "te propuso formar una familia" in prompt:
        return {"accion": "responder_propuesta", "acepta": True, "pensamiento": "Me cae bien."}
    if alcance:
        otro = alcance[0]
        estado["n"] = estado.get("n", 0) + 1
        if "Sabés hacer o saber: " in prompt:
            cono = re.search(r"Sabés hacer o saber: ([^.]+)\.", prompt).group(1).split(",")[0].strip()
            if estado["n"] % 2 == 0:
                return {"accion": "ensenar", "a": otro, "conocimiento": cono, "pensamiento": "Quiero compartirlo."}
        if "proponer_hijo:" in prompt and "te dijo" in prompt:
            return {"accion": "proponer_hijo", "a": otro, "pensamiento": "Quiero formar una familia."}
        if "inventar:" in prompt and "Sabés hacer o saber" not in prompt and estado["n"] % 3 == 0:
            return {"accion": "inventar", "receta": {"nombre": "balsa", "materiales": ["madera"], "propiedad": "flota",
                                                     "descripcion": "tronco atado"}, "pensamiento": "Un tronco flota."}
        return {"accion": "hablar", "a": otro, "mensaje": _FRASES[estado["n"] % len(_FRASES)] % otro,
                "impresion": 1.5, "pensamiento": "Me da curiosidad."}
    visibles = re.findall(r"- (\w+) \([^)]*\), a [\d]+ celdas", prompt)
    if visibles:
        return {"accion": "ir_hacia", "a": visibles[0], "pensamiento": "Voy a verlo."}
    return {"accion": "explorar", "pensamiento": "Miro alrededor."}


_FRASES = ["Hola %s, ¿cómo andás?", "Encontré agua limpia cerca del río, %s.", "Vi humo hacia el norte, cuidate %s.",
           "Mañana pienso explorar la colina, ¿venís %s?", "Anoche hizo frío; dormí junto a las rocas, %s.",
           "Hay frutos raros por el bosque, %s, no los probé.", "Se acerca una tormenta, %s, busquemos refugio."]


class _H(BaseHTTPRequestHandler):
    estado: dict = {}
    llamadas = 0

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        cuerpo = json.loads(self.rfile.read(n))
        prompt = cuerpo["messages"][-1]["content"]
        _H.llamadas += 1
        r = decidir(prompt, _H.estado)
        data = json.dumps({"message": {"content": json.dumps(r)}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def iniciar():
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]

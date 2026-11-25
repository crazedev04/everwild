"""Línea de comandos:  python -m mundo_vivo <comando>"""
from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

# importado con nombre propio: dentro de main() hay un `from .persistencia import db, mundo_io`,
# y eso haría local al nombre `mundo_io` en toda la función.
from .persistencia.mundo_io import ANCHO_POR_DEFECTO as _ANCHO, TAM_CELDA_POR_DEFECTO as _TAM_CELDA

RAIZ = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mundo_vivo")
    ap.add_argument("--datos", default=os.environ.get("MUNDO_VIVO_DATOS", str(RAIZ / "datos")),
                    help="carpeta de datos (por defecto ./datos)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generar", help="genera un mundo nuevo")
    g.add_argument("--semilla", type=int, default=None)
    g.add_argument("--ancho", type=int, default=_ANCHO)
    g.add_argument("--alto", type=int, default=_ANCHO)
    g.add_argument("--nombre", default=None)

    s = sub.add_parser("servir", help="abre el visor web")
    s.add_argument("--puerto", type=int, default=8000)
    s.add_argument("--host", default="0.0.0.0")

    co = sub.add_parser("correr", help="hace correr el mundo en tiempo real SIN pantalla (para dejarlo toda la noche)")
    co.add_argument("nombre")
    co.add_argument("--velocidad", type=float, default=5, help="minutos del mundo por segundo real (0,1,5,20,100,500)")
    co.add_argument("--horas", type=float, default=0, help="horas reales a correr (0 = hasta Ctrl+C)")

    sub.add_parser("listar", help="lista los mundos guardados")

    aj = sub.add_parser("ajustes", help="muestra o cambia el modelo y los interruptores de un mundo (con el mundo detenido)")
    aj.add_argument("nombre")
    aj.add_argument("--modelo", default=None, help="ej. qwen3.5:9b")
    aj.add_argument("--host", default=None, help="ej. http://localhost:11434")
    aj.add_argument("--activar", nargs="*", default=[], help="módulos a prender")
    aj.add_argument("--desactivar", nargs="*", default=[], help="módulos a apagar")

    po = sub.add_parser("poblar", help="crea los habitantes iniciales (junto al agua) en un mundo")
    po.add_argument("nombre")
    po.add_argument("--n", type=int, default=4)

    si = sub.add_parser("simular", help="hace correr el mundo sin pantalla y lo guarda")
    si.add_argument("nombre")
    si.add_argument("--dias", type=float, default=1.0)

    e = sub.add_parser("exportar", help="exporta un mundo a un .zip portable")
    e.add_argument("nombre")

    i = sub.add_parser("importar", help="restaura un .zip como mundo nuevo")
    i.add_argument("zip")
    i.add_argument("--nombre", default=None)

    au = sub.add_parser("autopsia", help="junta el último registro, la última caída y un resumen de la base")
    au.add_argument("nombre", nargs="?", default=None, help="mundo a resumir (por omisión, el más reciente)")
    au.add_argument("--lineas", type=int, default=80, help="cuántas líneas del final del registro mostrar")
    au.add_argument("--salida", default=None, help="archivo donde dejar el informe (además de imprimirlo)")

    a = ap.parse_args(argv)
    datos = Path(a.datos)
    mundos = datos / "mundos"

    # El registro y el manejador de caídas arrancan antes que todo lo demás: si el mundo se muere de
    # madrugada, esto es lo único que queda para mirar al día siguiente (ver `diagnostico.py`).
    from . import diagnostico
    diagnostico.arrancar(datos, {"comando": a.cmd, "mundo": getattr(a, "nombre", None),
                                 "datos": str(datos), "argv": list(argv or sys.argv[1:])})

    from .persistencia import db, mundo_io

    if a.cmd == "generar":
        semilla = a.semilla if a.semilla is not None else random.randrange(1, 2 ** 31)
        ruta = mundo_io.crear_mundo(mundos, semilla, a.ancho, a.alto, nombre=a.nombre)
        print("Mundo creado: %s (semilla %d)" % (ruta, semilla))
    elif a.cmd == "listar":
        for f in sorted(mundos.glob("*.db")):
            con = db.abrir(f)
            try:
                m = mundo_io.cargar_meta(con)
                print("%-30s semilla %-12s %sx%s" % (f.stem, m.get("semilla"), m.get("ancho"), m.get("alto")))
            finally:
                con.close()
    elif a.cmd == "exportar":
        destino = datos / "exportaciones" / (a.nombre + ".zip")
        print("Exportado a", mundo_io.exportar_paquete(mundos / (a.nombre + ".db"), destino))
    elif a.cmd == "importar":
        print("Restaurado en", mundo_io.importar_paquete(Path(a.zip), mundos, a.nombre))
    elif a.cmd == "autopsia":
        informe = diagnostico.informe_autopsia(datos, a.nombre, a.lineas)
        print(informe)
        if a.salida:
            Path(a.salida).write_text(informe, encoding="utf-8")
            print("(informe guardado en %s)" % a.salida)
    elif a.cmd == "poblar":
        from .persistencia import sim_io
        con = db.abrir(mundos / (a.nombre + ".db"))
        try:
            print("Habitantes:", sim_io.crear_habitantes_iniciales(con, a.n))
        finally:
            con.close()
    elif a.cmd == "simular":
        import time
        from .api.vivo import crear_cerebro
        from .persistencia import sim_io
        con = db.abrir(mundos / (a.nombre + ".db"))
        try:
            sim_io.crear_habitantes_iniciales(con, 4)
            # Respeta MUNDO_VIVO_CEREBRO igual que `servir` y `correr`. Antes este comando usaba
            # siempre el cerebro de demostración, así que adelantar días no probaba nada del cerebro.
            cerebro = crear_cerebro(con)
            sim = sim_io.cargar_simulacion(con, cerebro=cerebro)
            print("Cerebro: %s" % cerebro.nombre, flush=True)
            t0 = time.time()
            sim.avanzar(a.dias * 1440)
            n = sim_io.volcar_eventos(con, sim)
            sim_io.guardar_simulacion(con, sim)
            vivos = sum(h.vivo for h in sim.habitantes.values())
            print("Simulados %.1f días en %.1f s. Eventos: %d. Vivos: %d de %d." % (
                a.dias, time.time() - t0, n, vivos, len(sim.habitantes)))
        finally:
            con.close()
    elif a.cmd == "ajustes":
        import json
        from .agentes import ajustes as _aj
        ruta = mundos / (a.nombre + ".db")
        if not ruta.exists():
            print("No existe el mundo", a.nombre); return 1
        con = db.abrir(ruta)
        try:
            cambios = {}
            if a.modelo: cambios["modelo"] = a.modelo
            if a.host: cambios["host"] = a.host
            if a.activar or a.desactivar:
                cambios["modulos"] = {**{m: True for m in a.activar}, **{m: False for m in a.desactivar}}
            res = _aj.guardar(con, cambios) if cambios else _aj.obtener(con)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        except ValueError as e:
            print("Error:", e); return 1
        finally:
            con.close()
    elif a.cmd == "correr":
        import asyncio
        from .api.vivo import Ejecutor
        ruta = mundos / (a.nombre + ".db")
        if not ruta.exists():
            print("No existe el mundo", a.nombre); return 1

        async def _correr():
            import signal
            parar = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, parar.set)   # al cerrarlo (Ctrl+C o kill) guarda antes de salir
                except NotImplementedError:
                    pass
            ej = Ejecutor(ruta)
            ej.comando({"cmd": "velocidad", "v": a.velocidad})
            q = ej.suscribir()
            print("Corriendo %s a %g×. Ctrl+C para frenar (se guarda solo)." % (a.nombre, a.velocidad), flush=True)
            print("Modelo: %s · host: %s · modelo de lenguaje %s" % (ej.sim.ajustes["modelo"], ej.sim.ajustes["host"],
                  "PRENDIDO" if ej.sim.ajustes["modulos"].get("cerebro_llm") else "APAGADO"), flush=True)
            t0, ultimo = loop.time(), 0.0
            try:
                while not parar.is_set() and (a.horas <= 0 or loop.time() - t0 < a.horas * 3600):
                    try:
                        await asyncio.wait_for(parar.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        pass
                    if loop.time() - ultimo >= 60:
                        ultimo = loop.time()
                        f = ej.sim.estado_publico()
                        vivos = sum(1 for h in ej.sim.habitantes.values() if h.vivo)
                        print("%s · vivos %d/%d · modelo: %s" % (f["texto_fecha"], vivos, len(ej.sim.habitantes),
                              ej.cerebro.estado(ej.sim)), flush=True)
            finally:
                await ej.desuscribir(q)
                ej.cerrar()
                print("Guardado.", flush=True)

        asyncio.run(_correr())
    elif a.cmd == "servir":
        import socket
        import uvicorn
        from .api.servidor import crear_app
        ips_red = []
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                ips_red.append(ip)
            s.close()
        except Exception:
            pass
        if not ips_red:
            try:
                for res in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                    ip = res[4][0]
                    if ip and not ip.startswith("127.") and ip not in ips_red:
                        ips_red.append(ip)
            except Exception:
                pass

        print("Mundo Vivo %s listo:" % __import__("mundo_vivo").__version__)
        print("  ➜ Local: http://localhost:%d" % a.puerto)
        if a.host in ("0.0.0.0", ""):
            for ip in ips_red:
                print("  ➜ Red:   http://%s:%d" % (ip, a.puerto))
        print("  (Ctrl+C para cerrar)")
        uvicorn.run(crear_app(datos), host=a.host, port=a.puerto, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())

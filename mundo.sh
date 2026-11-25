#!/usr/bin/env bash
# Un solo comando para todo. El cerebro no se ejecuta aparte: Cognitive Engine corre dentro del
# mismo proceso, así que no hay nada más que levantar.
#
#   ./mundo.sh ver                      abre el visor (http://localhost:8767) con el cerebro cognitivo
#   ./mundo.sh ver hibrido              lo mismo, pero con el cerebro de siempre (modelo de lenguaje)
#   ./mundo.sh adelantar <mundo> 120    adelanta 120 días del mundo lo más rápido que pueda, sin pantalla
#   ./mundo.sh correr <mundo> 500       lo deja corriendo a 500× sin pantalla (Ctrl+C guarda y sale)
#   ./mundo.sh nuevo [semilla]          genera un mundo nuevo de 2048×2048 y le pone 4 habitantes
#   ./mundo.sh listar                   qué mundos hay
#   ./mundo.sh autopsia [mundo]         qué pasó: último registro, última caída y resumen de la base
#   ./mundo.sh logs                     mira el registro en vivo (datos/logs/mundo.log)
set -euo pipefail

cd "$(dirname "$0")"

PY="${PY:-.venv/bin/python}"
# Si el venv apunta a un intérprete que no existe, `-x` da falso y antes se caía a `python3` pelado,
# que no tiene numpy: el error aparecía recién al importar y no decía nada del venv. Mejor avisar.
if [ ! -x "$PY" ] || ! "$PY" -c "import numpy" 2>/dev/null; then
  echo "El venv no sirve ($PY). Recrealo:" >&2
  echo "  rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt" >&2
  exit 1
fi
DATOS="${MUNDO_VIVO_DATOS:-datos}"
PUERTO="${PUERTO:-8767}"

export PYTHONPATH="src"
export COGNITIVE_ENGINE_SRC="${COGNITIVE_ENGINE_SRC:-$(cd .. && pwd)/Cognitive Engine/src}"

cerebro_de() {   # "hibrido" como segundo argumento vuelve al cerebro con modelo de lenguaje
  if [ "${1:-cognitivo}" = "hibrido" ]; then echo "hibrido"; else echo "cognitivo"; fi
}

mundo_por_defecto() {
  "$PY" - "$DATOS" <<'EOF'
import sys
from pathlib import Path
mundos = sorted((Path(sys.argv[1]) / "mundos").glob("*.db"), key=lambda p: p.stat().st_mtime)
print(mundos[-1].stem if mundos else "")
EOF
}

cmd="${1:-ver}"
shift || true

case "$cmd" in
  ver)
    export MUNDO_VIVO_CEREBRO="$(cerebro_de "${1:-}")"
    echo "Cerebro: $MUNDO_VIVO_CEREBRO · iniciando visor…"
    exec "$PY" -u -m mundo_vivo --datos "$DATOS" servir --puerto "$PUERTO" --host "${HOST:-0.0.0.0}"
    ;;
  adelantar)
    nombre="${1:-$(mundo_por_defecto)}"
    dias="${2:-30}"
    [ -n "$nombre" ] || { echo "No hay ningún mundo todavía. Probá: ./mundo.sh nuevo"; exit 1; }
    export MUNDO_VIVO_CEREBRO="${MUNDO_VIVO_CEREBRO:-cognitivo}"
    echo "Adelantando $dias días de '$nombre' a fondo (sin pantalla)…"
    exec "$PY" -u -m mundo_vivo --datos "$DATOS" simular "$nombre" --dias "$dias"
    ;;
  correr)
    nombre="${1:-$(mundo_por_defecto)}"
    vel="${2:-500}"
    [ -n "$nombre" ] || { echo "No hay ningún mundo todavía. Probá: ./mundo.sh nuevo"; exit 1; }
    export MUNDO_VIVO_CEREBRO="${MUNDO_VIVO_CEREBRO:-cognitivo}"
    echo "Corriendo '$nombre' a ${vel}× con el cerebro $MUNDO_VIVO_CEREBRO. Ctrl+C guarda y sale."
    exec "$PY" -u -m mundo_vivo --datos "$DATOS" correr "$nombre" --velocidad "$vel"
    ;;
  nuevo)
    semilla="${1:-}"
    if [ -n "$semilla" ]; then
      "$PY" -m mundo_vivo --datos "$DATOS" generar --semilla "$semilla"
    else
      "$PY" -m mundo_vivo --datos "$DATOS" generar
    fi
    nombre="$(mundo_por_defecto)"
    "$PY" -m mundo_vivo --datos "$DATOS" poblar "$nombre" --n 4
    echo "Listo: '$nombre'. Para mirarlo:  ./mundo.sh ver"
    ;;
  listar)
    exec "$PY" -m mundo_vivo --datos "$DATOS" listar
    ;;
  autopsia)
    # Lo que queda para mirar cuando el mundo se cayó de madrugada (ver src/mundo_vivo/diagnostico.py).
    exec "$PY" -u -m mundo_vivo --datos "$DATOS" autopsia ${1:+"$1"}
    ;;
  logs)
    exec tail -f "$DATOS/logs/mundo.log"
    ;;
  *)
    sed -n '2,14p' "$0"
    exit 1
    ;;
esac

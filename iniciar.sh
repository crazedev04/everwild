#!/usr/bin/env bash
# Arranca Mundo Vivo: crea el entorno la primera vez e instala lo necesario.
# Uso:  ./iniciar.sh            (abre el visor en http://localhost:8000)
#       ./iniciar.sh generar    (ejemplo: pasa cualquier comando de "python -m mundo_vivo")
cd "$(dirname "$0")" || exit 1
# Si el entorno quedó roto (por ejemplo cambió la versión de Python), se borra y se crea de nuevo.
if [ -d .venv ] && ! .venv/bin/python -c "import sys" >/dev/null 2>&1; then
  echo "El entorno anterior no sirve más (cambió Python); lo recreo..."
  rm -rf .venv
fi
if [ ! -d .venv ]; then
  echo "Primera vez: creando el entorno (puede tardar un minuto)..."
  python3 -m venv .venv || { echo "Falta python3-venv. Instalalo con: sudo apt install python3-venv"; exit 1; }
fi
.venv/bin/pip install -q -r requirements.txt || exit 1
export PYTHONPATH=src
# Mismo default que mundo.sh: si no se pide otro cerebro, arranca con el cognitivo. Antes este
# script no tocaba la variable y el visor del README caía en el híbrido sin avisar.
export COGNITIVE_ENGINE_SRC="${COGNITIVE_ENGINE_SRC:-$(cd .. && pwd)/Cognitive Engine/src}"
export MUNDO_VIVO_CEREBRO="${MUNDO_VIVO_CEREBRO:-cognitivo}"
if [ $# -eq 0 ]; then
  exec .venv/bin/python -m mundo_vivo servir
else
  exec .venv/bin/python -m mundo_vivo "$@"
fi

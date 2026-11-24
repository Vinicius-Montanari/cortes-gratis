#!/usr/bin/env bash
# Instalador pra Linux e Mac. Precisa de Python 3.10+ e ffmpeg do sistema.
set -euo pipefail
cd "$(dirname "$0")"

command -v python3 >/dev/null || { echo "Instale o Python 3.10+"; exit 1; }
command -v ffmpeg >/dev/null || {
  echo "Instale o ffmpeg: 'sudo apt install ffmpeg' (Linux) ou 'brew install ffmpeg' (Mac)"; exit 1; }

[ -x .venv/bin/python ] || python3 -m venv .venv
export PIP_NO_CACHE_DIR=1
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt
if command -v nvidia-smi >/dev/null; then
  .venv/bin/python -m pip install -r requirements-gpu.txt || echo "Sem GPU: vai pelo processador."
fi
echo
echo "Pronto! Rode ./iniciar.sh"

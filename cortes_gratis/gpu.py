"""Detecção da placa de vídeo para a transcrição.

O faster-whisper usa a placa NVIDIA se encontrar as bibliotecas do CUDA 12
(cuBLAS e cuDNN 9). O instalador coloca essas bibliotecas como pacotes do pip,
então aqui só falta avisar o Windows onde elas estão.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_pronto = False


def preparar_dlls() -> None:
    global _pronto
    if _pronto:
        return
    _pronto = True
    if os.name != "nt":
        return
    for base in map(Path, sys.path):
        nvidia = base / "nvidia"
        if not nvidia.is_dir():
            continue
        for bin_ in nvidia.glob("*/bin"):
            try:
                os.add_dll_directory(str(bin_))
            except OSError:
                pass
            os.environ["PATH"] = str(bin_) + os.pathsep + os.environ.get("PATH", "")


def tem_cuda() -> bool:
    preparar_dlls()
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def info() -> dict:
    """Nome e memória da placa, se o nvidia-smi existir (só pra mostrar)."""
    import shutil
    import subprocess
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {"cuda": tem_cuda()}
    try:
        r = subprocess.run(
            [smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        nome, mem = [x.strip() for x in r.stdout.splitlines()[0].split(",")]
        return {"cuda": tem_cuda(), "nome": nome, "memoria_mb": int(mem)}
    except Exception:
        return {"cuda": tem_cuda()}

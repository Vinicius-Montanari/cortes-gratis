"""Baixa as bibliotecas da NVIDIA (CUDA 12 + cuDNN 9) que a transcrição na
placa de vídeo precisa, sem pip.

Na versão instalada (.exe) não tem pip. Então o programa pega os mesmos
pacotes oficiais que o pip pegaria (do PyPI), confere o hash, e extrai só
as DLLs pra dados/cuda/bin. Só acontece se tiver placa NVIDIA, uma vez só.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from . import config, ferramentas

# Versões testadas com o ctranslate2 4.x (o motor do faster-whisper).
PACOTES = [
    ("nvidia-cublas-cu12", "12.9.2.10"),
    ("nvidia-cudnn-cu12", "9.28.1.4"),
    ("nvidia-cuda-nvrtc-cu12", "12.9.86"),
]
PULAR = {"nvblas64_12.dll"}  # não é usado e ocupa espaço

PASTA = config.DADOS / "cuda"
BIN = PASTA / "bin"
MARCA = PASTA / "pronto.json"


def instalado() -> bool:
    return MARCA.exists() and (BIN / "cublas64_12.dll").exists()


def _wheel(nome: str, versao: str) -> dict:
    url = f"https://pypi.org/pypi/{nome}/{versao}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "cortes-gratis"})
    with urllib.request.urlopen(req, timeout=30) as r:
        dados = json.loads(r.read().decode())
    for arq in dados["urls"]:
        if arq["filename"].endswith("win_amd64.whl"):
            return arq
    raise RuntimeError(f"{nome} {versao}: não achei a versão pra Windows no PyPI")


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar(progresso: Callable[[float, str], None]) -> None:
    if instalado():
        return
    BIN.mkdir(parents=True, exist_ok=True)
    tmp = PASTA / "baixando"
    tmp.mkdir(exist_ok=True)
    try:
        for n, (nome, versao) in enumerate(PACOTES, 1):
            arq = _wheel(nome, versao)
            destino = tmp / arq["filename"]
            if not destino.exists() or _sha256(destino) != arq["digests"]["sha256"]:
                rotulo = f"Suporte à placa de vídeo ({n}/{len(PACOTES)}, só na 1ª vez):"
                ferramentas.baixar(arq["url"], destino, progresso, rotulo)
                if _sha256(destino) != arq["digests"]["sha256"]:
                    destino.unlink(missing_ok=True)
                    raise RuntimeError(f"{arq['filename']} veio corrompido; tente de novo")
            progresso(1.0, f"Extraindo {nome}...")
            with zipfile.ZipFile(destino) as z:
                for item in z.namelist():
                    p = Path(item)
                    if p.suffix.lower() == ".dll" and p.parent.name == "bin" and p.name not in PULAR:
                        with z.open(item) as src, open(BIN / p.name, "wb") as dst:
                            shutil.copyfileobj(src, dst, 1 << 20)
            destino.unlink(missing_ok=True)
        MARCA.write_text(json.dumps(dict(PACOTES)), encoding="utf-8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

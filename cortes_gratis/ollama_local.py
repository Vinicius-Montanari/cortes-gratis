"""IA local (Ollama): instala, liga, baixa o modelo e desliga.

Tudo fica dentro de dados/ollama (programa e modelos). Nada vai pro C:.
O programa roda o próprio Ollama numa porta separada (11435), pra não
brigar com um Ollama que você já tenha instalado no sistema.
"""
from __future__ import annotations

import atexit
import json
import os
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from . import config, ferramentas

PORTA = 11435
API_RELEASE = "https://api.github.com/repos/ollama/ollama/releases/latest"

# Modelos sugeridos na tela. Todos rodam em placa de 8 GB ou mais.
SUGERIDOS = [
    {"nome": "qwen2.5:7b", "tamanho": "4,7 GB", "nota": "recomendado: bom em português e em seguir formato"},
    {"nome": "llama3.1:8b", "tamanho": "4,9 GB", "nota": "alternativa, um pouco pior em português"},
    {"nome": "gemma3:4b", "tamanho": "3,3 GB", "nota": "mais leve, pra placa de 6 GB ou menos"},
    {"nome": "qwen2.5:3b", "tamanho": "1,9 GB", "nota": "bem leve; julga pior"},
]

_processo: subprocess.Popen | None = None


def _exe() -> Path:
    return config.PASTA_OLLAMA / ("ollama.exe" if os.name == "nt" else "bin/ollama")


def base_api(url_cfg: str | None = None) -> str:
    url = (url_cfg or f"http://127.0.0.1:{PORTA}/v1").rstrip("/")
    return url[:-3] if url.endswith("/v1") else url


def _get(url: str, timeout: float = 5) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def rodando(url_cfg: str | None = None) -> bool:
    return _get(base_api(url_cfg) + "/api/version") is not None


def modelos_baixados(url_cfg: str | None = None) -> list[str]:
    r = _get(base_api(url_cfg) + "/api/tags") or {}
    return [m["name"] for m in r.get("models", [])]


def instalado() -> bool:
    return _exe().exists()


def status(url_cfg: str | None = None) -> dict:
    rod = rodando(url_cfg)
    return {
        "instalado": instalado(),
        "rodando": rod,
        "modelos": modelos_baixados(url_cfg) if rod else [],
        "pasta": str(config.PASTA_OLLAMA),
        "sugeridos": SUGERIDOS,
    }


def _asset_desejado() -> str:
    sistema = platform.system()
    if sistema == "Windows":
        return "ollama-windows-amd64.zip"
    if sistema == "Linux":
        return "ollama-linux-amd64.tgz"
    raise RuntimeError("No Mac, instale o Ollama pelo site ollama.com e deixe o endereço "
                       "da IA local como http://127.0.0.1:11434/v1 nas Configurações.")


def instalar(progresso: Callable[[float, str], None]) -> None:
    """Baixa a versão portátil do Ollama (sem instalador, sem admin)."""
    if instalado():
        return
    nome = _asset_desejado()
    progresso(0.0, "Procurando a versão mais nova do Ollama...")
    req = urllib.request.Request(API_RELEASE, headers={"User-Agent": "cortes-gratis"})
    with urllib.request.urlopen(req, timeout=30) as r:
        rel = json.loads(r.read().decode())
    asset = next((a for a in rel.get("assets", []) if a["name"] == nome), None)
    if not asset:
        raise RuntimeError(f"Não achei o arquivo {nome} na versão {rel.get('tag_name')} do Ollama.")
    config.PASTA_OLLAMA.mkdir(parents=True, exist_ok=True)
    arq = config.PASTA_OLLAMA / nome
    ferramentas.baixar(asset["browser_download_url"], arq, progresso,
                       f"Baixando o Ollama {rel.get('tag_name', '')}:")
    progresso(1.0, "Descompactando o Ollama...")
    if nome.endswith(".zip"):
        with zipfile.ZipFile(arq) as z:
            z.extractall(config.PASTA_OLLAMA)
    else:
        with tarfile.open(arq) as t:
            t.extractall(config.PASTA_OLLAMA, filter="data")
    arq.unlink(missing_ok=True)
    if not instalado():
        raise RuntimeError("O Ollama foi baixado mas o executável não apareceu.")


def iniciar(url_cfg: str | None = None, espera: float = 60) -> None:
    global _processo
    if rodando(url_cfg):
        return
    if not instalado():
        raise RuntimeError("Ollama não instalado.")
    config.PASTA_OLLAMA_MODELOS.mkdir(parents=True, exist_ok=True)
    host = base_api(url_cfg).split("://", 1)[-1]
    env = os.environ | {
        "OLLAMA_HOST": host,
        "OLLAMA_MODELS": str(config.PASTA_OLLAMA_MODELOS),
        "OLLAMA_KEEP_ALIVE": "5m",
    }
    log = open(config.PASTA_OLLAMA / "ollama.log", "ab")
    _processo = subprocess.Popen([str(_exe()), "serve"], env=env, stdout=log, stderr=log,
                                 creationflags=ferramentas.SEM_JANELA)
    atexit.register(parar)
    _morrer_junto(_processo)
    fim = time.time() + espera
    while time.time() < fim:
        if rodando(url_cfg):
            return
        if _processo.poll() is not None:
            raise RuntimeError("O Ollama fechou ao iniciar. Veja dados/ollama/ollama.log")
        time.sleep(0.5)
    raise RuntimeError("O Ollama não respondeu a tempo.")


_job = None  # precisa continuar vivo enquanto o programa roda


def _morrer_junto(proc: subprocess.Popen) -> None:
    """No Windows, fechar a janela no X não roda o atexit. Um "Job Object"
    com KILL_ON_JOB_CLOSE garante que o Ollama fecha junto com o programa,
    em vez de ficar esquecido segurando memória da placa de vídeo."""
    global _job
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class Basico(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class Estendido(ctypes.Structure):
            _fields_ = [("Basic", Basico), ("Io", IO),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32.CreateJobObjectW.restype = wintypes.HANDLE
        job = k32.CreateJobObjectW(None, None)
        info = Estendido()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        k32.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle)))
        _job = job
    except Exception:
        pass  # se falhar, só perde essa garantia; o atexit ainda tenta fechar


def parar() -> None:
    global _processo
    if _processo and _processo.poll() is None:
        _processo.terminate()
        try:
            _processo.wait(10)
        except subprocess.TimeoutExpired:
            _processo.kill()
    _processo = None


def baixar_modelo(modelo: str, progresso: Callable[[float, str], None],
                  url_cfg: str | None = None) -> None:
    if any(m == modelo or m == modelo + ":latest" for m in modelos_baixados(url_cfg)):
        return
    corpo = json.dumps({"name": modelo, "stream": True}).encode()
    req = urllib.request.Request(base_api(url_cfg) + "/api/pull", data=corpo,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3600) as r:
        for linha in r:
            if not linha.strip():
                continue
            d = json.loads(linha)
            if d.get("error"):
                raise RuntimeError(f"Ollama: {d['error']}")
            total, feito = d.get("total") or 0, d.get("completed") or 0
            msg = f"Baixando o modelo {modelo}: {d.get('status', '')}"
            if total:
                msg += f" {feito >> 20} de {total >> 20} MB"
            progresso(feito / total if total else 0.0, msg)


def garantir_pronto(modelo: str, aviso: Callable[[str], None],
                    url_cfg: str | None = None) -> None:
    """Chamado quando chega a vez da IA local: instala, liga e baixa o modelo
    se precisar. Da segunda vez em diante é instantâneo."""
    ultimo = [0.0]

    def prog(_p: float, msg: str) -> None:
        if time.time() - ultimo[0] > 2:  # não inunda o log
            ultimo[0] = time.time()
            aviso(msg)

    if not rodando(url_cfg):
        if not instalado():
            aviso("Instalando a IA local (só na primeira vez)...")
            instalar(prog)
        aviso("Ligando a IA local...")
        iniciar(url_cfg)
    baixar_modelo(modelo, prog, url_cfg)


def desinstalar() -> None:
    parar()
    shutil.rmtree(config.PASTA_OLLAMA, ignore_errors=True)

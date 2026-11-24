"""Acha (ou baixa) o ffmpeg e oferece utilidades comuns: baixar arquivo com
progresso, rodar comando, medir duração de vídeo."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from . import config

Progresso = Callable[[float, str], None]  # (0..1, mensagem)

FFMPEG_WINDOWS = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)

# No Windows, evita abrir uma janela preta pra cada comando.
SEM_JANELA = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _nada(_p: float, _m: str) -> None:
    pass


def baixar(url: str, destino: Path, progresso: Progresso = _nada, rotulo: str = "") -> Path:
    """Baixa url para destino mostrando o progresso. Baixa primeiro num
    arquivo .parcial e só renomeia no fim, pra não deixar arquivo quebrado."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    req = urllib.request.Request(url, headers={"User-Agent": "cortes-gratis"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(parcial, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        feito = 0
        while True:
            bloco = resp.read(1 << 20)
            if not bloco:
                break
            f.write(bloco)
            feito += len(bloco)
            if total:
                progresso(feito / total, f"{rotulo} {feito >> 20} de {total >> 20} MB")
            else:
                progresso(0.0, f"{rotulo} {feito >> 20} MB")
    parcial.replace(destino)
    return destino


def _no_path(nome: str) -> str | None:
    return shutil.which(nome)


def caminho_ffmpeg() -> str | None:
    """ffmpeg baixado pelo programa tem prioridade; senão, o do sistema."""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    local = config.PASTA_FERRAMENTAS / "ffmpeg" / "bin" / exe
    if local.exists():
        # O yt-dlp, no download parcial, só procura o ffmpeg no PATH (ignora a
        # opção ffmpeg_location). Então põe a nossa pasta no PATH deste processo.
        pasta = str(local.parent)
        if pasta not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = pasta + os.pathsep + os.environ.get("PATH", "")
        return str(local)
    return _no_path("ffmpeg")


def caminho_ffprobe() -> str | None:
    ff = caminho_ffmpeg()
    if not ff:
        return None
    p = Path(ff)
    exe = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    irmao = p.with_name(exe)
    return str(irmao) if irmao.exists() else _no_path("ffprobe")


def instalar_ffmpeg(progresso: Progresso = _nada) -> str:
    """Baixa o ffmpeg pronto pro Windows dentro de dados/ferramentas.
    Em Mac e Linux, pede pra instalar pelo gerenciador do sistema."""
    if caminho_ffmpeg():
        return caminho_ffmpeg()  # type: ignore[return-value]
    if os.name != "nt":
        dica = "brew install ffmpeg" if platform.system() == "Darwin" else "sudo apt install ffmpeg"
        raise RuntimeError(f"ffmpeg não encontrado. Instale com: {dica}")
    zip_dest = config.PASTA_FERRAMENTAS / "ffmpeg.zip"
    baixar(FFMPEG_WINDOWS, zip_dest, progresso, "Baixando ffmpeg:")
    progresso(1.0, "Descompactando ffmpeg...")
    alvo = config.PASTA_FERRAMENTAS / "ffmpeg"
    tmp = config.PASTA_FERRAMENTAS / "ffmpeg-tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_dest) as z:
        z.extractall(tmp)
    # O zip tem uma pasta com nome de versão; pega a que tem bin/ffmpeg.exe.
    raiz = next(p.parent.parent for p in tmp.rglob("ffmpeg.exe") if p.parent.name == "bin")
    shutil.rmtree(alvo, ignore_errors=True)
    shutil.move(str(raiz), str(alvo))
    shutil.rmtree(tmp, ignore_errors=True)
    zip_dest.unlink(missing_ok=True)
    return caminho_ffmpeg()  # type: ignore[return-value]


def rodar(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    r = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", creationflags=SEM_JANELA,
    )
    if r.returncode != 0:
        fim = "\n".join(r.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"Falhou: {Path(args[0]).name}\n{fim}")
    return r


def duracao(arquivo: Path | str) -> float:
    r = rodar([
        caminho_ffprobe() or "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=nw=1:nk=1", str(arquivo),
    ])
    return float(r.stdout.strip() or 0)


_nvenc: bool | None = None


def tem_nvenc() -> bool:
    """Testa se o ffmpeg consegue codificar com a placa NVIDIA (bem mais
    rápido que pelo processador). Faz um teste de verdade de 1 quadro."""
    global _nvenc
    if _nvenc is None:
        try:
            rodar([
                caminho_ffmpeg() or "ffmpeg", "-hide_banner", "-f", "lavfi", "-i",
                "color=black:s=256x256:d=0.1", "-frames:v", "1", "-c:v", "h264_nvenc",
                "-f", "null", "-",
            ])
            _nvenc = True
        except Exception:
            _nvenc = False
    return _nvenc

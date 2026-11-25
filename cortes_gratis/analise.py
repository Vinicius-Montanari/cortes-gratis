"""Etapa 1: pega o áudio do vídeo, transcreve e mede o volume de cada segundo.

Para link, baixa só o áudio (bem mais leve que o vídeo). O vídeo em si só é
baixado depois, e só os trechos que viraram clipe.
"""
from __future__ import annotations

import gc
import json
import re
import wave
from pathlib import Path
from typing import Callable

import numpy as np

from . import config, ferramentas, gpu

Progresso = Callable[[float, str], None]


def eh_link(entrada: str) -> bool:
    return bool(re.match(r"^https?://", entrada.strip(), re.I))


def para_segundos(txt: str | float | int | None) -> float | None:
    """Aceita 90, '1:30', '1:02:03' ou '12:03.5'."""
    if txt is None or txt == "":
        return None
    if isinstance(txt, (int, float)):
        return float(txt)
    partes = [float(p) for p in str(txt).strip().split(":")]
    seg = 0.0
    for p in partes:
        seg = seg * 60 + p
    return seg


def hms(seg: float) -> str:
    seg = max(0, int(seg))
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------------------------------------------------------- download

def _opcoes_ytdlp() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ffmpeg_location": ferramentas.caminho_ffmpeg(),
        "retries": 5,
    }


def info_link(link: str) -> dict:
    import yt_dlp
    with yt_dlp.YoutubeDL(_opcoes_ytdlp()) as y:
        info = y.extract_info(link, download=False)
    return {
        "tipo": "link",
        "link": info.get("webpage_url") or link,
        "titulo": info.get("title") or "",
        "canal": info.get("channel") or info.get("uploader") or "",
        "canal_id": info.get("uploader_id") or "",
        "duracao": float(info.get("duration") or 0),
        "licenca": info.get("license") or "",
        "plataforma": info.get("extractor_key") or "",
    }


def baixar_audio(link: str, pasta: Path, ini: float | None, fim: float | None,
                 progresso: Progresso) -> Path:
    import yt_dlp

    def gancho(d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            feito = d.get("downloaded_bytes") or 0
            frac = feito / total if total else 0.0
            progresso(frac, f"Baixando o áudio: {feito >> 20} MB")

    opc = _opcoes_ytdlp() | {
        # Só o áudio, se o site tiver. Kick e Twitch não têm: aí pega a menor
        # qualidade de vídeo que tenha som (160p), que traz o mesmo áudio e
        # é dezenas de vezes menor que o 1080p.
        "format": "bestaudio/worst[acodec!=none]/worst",
        "outtmpl": str(pasta / "audio-original.%(ext)s"),
        "progress_hooks": [gancho],
    }
    if ini is not None or fim is not None:
        opc["download_ranges"] = yt_dlp.utils.download_range_func(
            None, [(ini or 0, fim or float("inf"))])
        # Corte exato no segundo pedido. Sem isto o trecho pode vir alguns
        # segundos antes, e todos os tempos da transcrição ficariam deslocados.
        opc["force_keyframes_at_cuts"] = True
    with yt_dlp.YoutubeDL(opc) as y:
        y.download([link])
    arqs = sorted(pasta.glob("audio-original.*"), key=lambda p: p.stat().st_size)
    if not arqs:
        raise RuntimeError("O yt-dlp não baixou o áudio. Confira se o link abre no navegador.")
    return arqs[-1]


FORMATO_AUDIO = "bestaudio/worst[acodec!=none]/worst"


def baixar_trecho_wav(link: str, wav: Path, ini: float, fim: float, progresso: Progresso) -> None:
    """Lê só o áudio do trecho direto do servidor e grava o WAV 16 kHz mono.

    Não usa o download por trecho do yt-dlp: ele pula com -ss antes do -i e,
    no HLS (Kick, Twitch), às vezes começa até ~12 s antes do pedido. Aí toda a
    transcrição fica deslocada e a legenda sai atrasada."""
    import subprocess
    import time
    from . import corte
    url, cab = corte._fontes_link_cache(link, FORMATO_AUDIO)[0]
    dur = max(1.0, fim - ini)
    ent, exato = corte.entrada_link(url, cab, ini, dur)
    args = [ferramentas.caminho_ffmpeg() or "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-copyts", *ent, "-ss", f"{exato:.3f}", "-t", f"{dur:.3f}",
            "-vn", "-ac", "1", "-ar", str(TAXA), "-c:a", "pcm_s16le", str(wav)]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            creationflags=ferramentas.SEM_JANELA)
    total = dur * TAXA * 2
    while proc.poll() is None:
        feito = wav.stat().st_size if wav.exists() else 0
        progresso(min(feito / total, 1.0), f"Baixando o áudio: {feito / total:.0%}")
        time.sleep(1)
    erro = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    if proc.returncode != 0 or not wav.exists() or wav.stat().st_size < TAXA * 2:
        raise RuntimeError("Não deu pra baixar o áudio do trecho. " + erro[-500:])


def para_wav(origem: Path, wav: Path, ini: float | None = None, fim: float | None = None) -> None:
    """Converte pra WAV 16 kHz mono, que é o que o Whisper usa."""
    args = [ferramentas.caminho_ffmpeg() or "ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if ini:
        args += ["-ss", f"{ini:.3f}"]
    if fim:
        args += ["-to", f"{fim:.3f}"]
    args += ["-i", str(origem), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]
    ferramentas.rodar(args)


# ---------------------------------------------------------------- volume

TAXA = 16000


def ler_wav(wav: Path) -> np.ndarray:
    """Lê o WAV 16 kHz mono como números de -1 a 1 (o formato que o Whisper usa).
    Passar o áudio já lido evita depender do PyAV, que muda de versão e quebra."""
    with wave.open(str(wav), "rb") as w:
        dados = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return dados.astype(np.float32) / 32768.0


def energia_por_segundo(x: np.ndarray, taxa: int = TAXA) -> list[float]:
    """Volume (em dB) de cada segundo do áudio. Silêncio fica perto de -60."""
    n = len(x) // taxa
    if n == 0:
        return []
    blocos = x[: n * taxa].reshape(n, taxa)
    rms = np.sqrt(np.mean(blocos ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    return [round(float(max(v, -60.0)), 1) for v in db]


# ---------------------------------------------------------------- transcrição

def escolher_modelo(cfg_whisper: dict, usa_gpu: bool) -> str:
    m = cfg_whisper.get("modelo", "auto")
    if m and m != "auto":
        return m
    return "large-v3-turbo" if usa_gpu else "small"


def transcrever(audio: np.ndarray, duracao: float, cfg_whisper: dict, idioma: str | None,
                deslocamento: float, progresso: Progresso) -> tuple[list[dict], str, dict]:
    """Transcreve com marcação de tempo de cada palavra.

    Tenta a placa de vídeo primeiro. Se der qualquer erro de CUDA (driver
    velho, falta de biblioteca), refaz no processador sem parar o programa.
    """
    from faster_whisper import WhisperModel

    disp = cfg_whisper.get("dispositivo", "auto")
    tentativas = []
    if disp in ("auto", "cuda") and gpu.tem_cuda():
        if not gpu.bibliotecas_ok():
            from . import cuda
            try:
                cuda.baixar(progresso)
            except Exception as e:  # noqa: BLE001 - sem internet etc.: segue no processador
                progresso(0.0, f"Não deu pra baixar o suporte à placa ({e}); "
                               "tentando de outro jeito...")
        tentativas.append(("cuda", "float16"))
    if disp in ("auto", "cpu") or not tentativas:
        tentativas.append(("cpu", "int8"))

    ultimo_erro: Exception | None = None
    for dispositivo, tipo in tentativas:
        nome = escolher_modelo(cfg_whisper, dispositivo == "cuda")
        progresso(0.0, f"Carregando o modelo de transcrição ({nome}, {dispositivo})...")
        modelo = None
        try:
            modelo = WhisperModel(nome, device=dispositivo, compute_type=tipo,
                                  download_root=str(config.PASTA_WHISPER))
            segs, info = modelo.transcribe(
                audio, language=idioma or None, word_timestamps=True,
                vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
                beam_size=5, condition_on_previous_text=False,
            )
            frases: list[dict] = []
            for s in segs:
                palavras = [
                    {"i": round(w.start + deslocamento, 2), "f": round(w.end + deslocamento, 2),
                     "p": w.word.strip()}
                    for w in (s.words or []) if w.word.strip()
                ]
                frases.append({
                    "i": round(s.start + deslocamento, 2),
                    "f": round(s.end + deslocamento, 2),
                    "texto": s.text.strip(),
                    "palavras": palavras,
                })
                if duracao:
                    progresso(min(s.end / duracao, 1.0),
                              f"Transcrevendo: {hms(s.end)} de {hms(duracao)}")
            usado = {"modelo": nome, "dispositivo": dispositivo}
            return frases, info.language, usado
        except Exception as e:  # noqa: BLE001 - qualquer falha de GPU cai pro CPU
            ultimo_erro = e
            progresso(0.0, f"Não deu na {dispositivo} ({type(e).__name__}: {e}); "
                           "tentando de outro jeito...")
        finally:
            del modelo
            gc.collect()  # libera a memória da placa pra IA local usar depois
    raise RuntimeError(f"Não consegui transcrever: {ultimo_erro}")


# ---------------------------------------------------------------- etapa inteira

def analisar(entrada: str, pasta: Path, cfg: dict, idioma: str | None,
             trecho: tuple[float | None, float | None], progresso: Progresso) -> dict:
    """Roda a etapa inteira e grava fonte.json, transcricao.json e energia.json."""
    pasta.mkdir(parents=True, exist_ok=True)
    ini, fim = trecho
    wav = pasta / "audio.wav"

    if eh_link(entrada):
        progresso(0.0, "Lendo informações do link...")
        fonte = info_link(entrada)
        if ini is not None or fim is not None:
            # Trecho: lê direto com pulo exato (ver corte.entrada_link).
            fim_real = fim if fim is not None else (fonte["duracao"] or 0) or None
            if fim_real is None:
                raise RuntimeError("Não deu pra saber a duração do vídeo. Preencha o campo 'Até'.")
            baixar_trecho_wav(entrada, wav, ini or 0.0, fim_real, progresso)
        else:
            original = baixar_audio(entrada, pasta, None, None, progresso)
            progresso(1.0, "Convertendo o áudio...")
            para_wav(original, wav)
            original.unlink(missing_ok=True)
    else:
        arq = Path(entrada.strip().strip('"')).expanduser()
        if not arq.exists():
            raise RuntimeError(f"Arquivo não encontrado: {arq}")
        fonte = {"tipo": "arquivo", "link": "", "arquivo": str(arq.resolve()),
                 "titulo": arq.stem, "canal": "", "canal_id": "",
                 "duracao": ferramentas.duracao(arq), "licenca": "", "plataforma": ""}
        progresso(0.0, "Extraindo o áudio do arquivo...")
        para_wav(arq, wav, ini, fim)

    deslocamento = ini or 0.0
    fonte["trecho"] = [ini, fim]
    audio = ler_wav(wav)
    duracao_audio = len(audio) / TAXA
    energia = energia_por_segundo(audio)
    frases, lingua, usado = transcrever(audio, duracao_audio, cfg["whisper"], idioma,
                                        deslocamento, progresso)
    del audio
    fonte["idioma"] = lingua
    fonte["whisper"] = usado

    (pasta / "fonte.json").write_text(json.dumps(fonte, ensure_ascii=False, indent=2), "utf-8")
    (pasta / "transcricao.json").write_text(json.dumps(frases, ensure_ascii=False), "utf-8")
    (pasta / "energia.json").write_text(
        json.dumps({"deslocamento": deslocamento, "db": energia}), "utf-8")
    wav.unlink(missing_ok=True)
    return {"fonte": fonte, "frases": frases,
            "energia": {"deslocamento": deslocamento, "db": energia}}

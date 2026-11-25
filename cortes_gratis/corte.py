"""Etapa 4: monta cada clipe em pé (1080x1920) com legenda palavra por palavra.

Para link, o ffmpeg lê direto do servidor do vídeo e pega só o pedaço do
clipe (não baixa a live inteira). Tudo é feito numa passada só: recorte,
layout, legenda, gancho, crédito e volume nivelado pra rede social.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Callable

from . import config, ferramentas
from .analise import hms

LARGURA, ALTURA = 1080, 1920
AMARELO = "&H0000E5FF&"  # cor do ASS é em BGR: este é um amarelo forte
BRANCO = "&H00FFFFFF&"


def slug(txt: str, n: int = 40) -> str:
    t = unicodedata.normalize("NFKD", txt.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return (t[:n].rstrip("-")) or "clipe"


def credito_de(fonte: dict, cfg_credito: str = "") -> str:
    if cfg_credito:
        return cfg_credito
    cid = (fonte.get("canal_id") or "").strip()
    if cid and not cid.startswith("UC"):  # UC... é id interno do YouTube, não o @
        return "@" + cid.lstrip("@")
    return fonte.get("canal") or ""


# ---------------------------------------------------------------- legenda (ASS)

def _t(seg: float) -> str:
    seg = max(0.0, seg)
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(txt: str) -> str:
    return txt.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def grupos(palavras: list[dict], max_palavras: int = 3, max_chars: int = 18) -> list[list[dict]]:
    """Junta as palavras em blocos curtos, que é o que cabe bem no celular."""
    saida: list[list[dict]] = []
    atual: list[dict] = []
    for w in palavras:
        tam = sum(len(x["p"]) + 1 for x in atual) + len(w["p"])
        pausa = atual and w["i"] - atual[-1]["f"] > 0.6
        fim_frase = atual and re.search(r"[.!?]$", atual[-1]["p"])
        if atual and (len(atual) >= max_palavras or tam > max_chars or pausa or fim_frase):
            saida.append(atual)
            atual = []
        atual.append(w)
    if atual:
        saida.append(atual)
    return saida


def janelas_marca(dur: float, quando: str) -> list[tuple[float, float]]:
    """Quando a marca aparece: o clipe todo, ou só 4 s no começo e no fim."""
    if quando != "inicio_fim" or dur <= 10:
        return [(0.0, dur)]
    return [(0.0, 4.0), (dur - 4.0, dur)]


def marca_ativa(marca: dict | None) -> dict | None:
    """A marca só entra se estiver ligada e tiver logo ou texto."""
    if not marca or not marca.get("ativo"):
        return None
    logo = config.PASTA_MARCA / marca["logo"] if marca.get("logo") else None
    if logo is not None and not logo.is_file():
        logo = None
    texto = str(marca.get("texto") or "").strip()
    if not logo and not texto:
        return None
    return {**marca, "texto": texto, "caminho_logo": logo}


def montar_ass(palavras: list[dict], ini: float, fim: float, gancho: str, credito: str,
               maiusculas: bool, layout: str, marca: dict | None = None) -> str:
    """Gera o arquivo de legenda. `palavras` vêm com o tempo do vídeo original."""
    dur = fim - ini
    margem_legenda = 470 if layout != "centro" else 380
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {LARGURA}
PlayResY: {ALTURA}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Legenda,Arial,82,{BRANCO},{BRANCO},&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,7,3,2,70,70,{margem_legenda},1
Style: Gancho,Arial,66,&H00000000&,&H00000000&,{BRANCO},{BRANCO},-1,0,0,0,100,100,0,0,3,18,0,8,80,80,230,1
Style: Credito,Arial,40,&H40FFFFFF&,&H40FFFFFF&,&H00000000&,&H00000000&,-1,0,0,0,100,100,0,0,1,3,0,2,60,60,140,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev: list[str] = []
    if gancho:
        ev.append(f"Dialogue: 1,{_t(0)},{_t(dur)},Gancho,,0,0,0,,{_esc(gancho)}")
    if credito:
        ev.append(f"Dialogue: 1,{_t(0)},{_t(dur)},Credito,,0,0,0,,{_esc(credito)}")
    if marca and marca.get("texto"):
        # Centro do texto na posição escolhida no editor (n5 = âncora no meio).
        x, y = round(LARGURA * float(marca["texto_x"])), round(ALTURA * float(marca["texto_y"]))
        tam = int(marca.get("texto_tam") or 44)
        alfa = f"{round(255 * (1 - float(marca.get('opacidade', 0.9)))):02X}"
        tags = f"{{\\an5\\pos({x},{y})\\fs{tam}\\alpha&H{alfa}&}}"
        for a, z in janelas_marca(dur, marca.get("quando", "sempre")):
            ev.append(f"Dialogue: 2,{_t(a)},{_t(z)},Credito,,0,0,0,,{tags}{_esc(marca['texto'])}")

    dentro = [w for w in palavras if w["f"] > ini and w["i"] < fim]
    blocos = grupos(dentro)
    for b, bloco in enumerate(blocos):
        prox = blocos[b + 1][0]["i"] if b + 1 < len(blocos) else fim
        fim_bloco = min(prox, bloco[-1]["f"] + 0.4)
        textos = [(w["p"].upper() if maiusculas else w["p"]) for w in bloco]
        for k, w in enumerate(bloco):
            a = w["i"] - ini
            z = (bloco[k + 1]["i"] if k + 1 < len(bloco) else fim_bloco) - ini
            if z <= a:
                continue
            partes = [
                (f"{{\\c{AMARELO}}}{_esc(t)}{{\\c{BRANCO}}}" if j == k else _esc(t))
                for j, t in enumerate(textos)
            ]
            ev.append(f"Dialogue: 0,{_t(a)},{_t(z)},Legenda,,0,0,0,,{' '.join(partes)}")
    return cab + "\n".join(ev) + "\n"


# ---------------------------------------------------------------- vídeo

def filtro_logo(indice: int, marca: dict, dur: float) -> str:
    """Logo por cima do vídeo [base] -> [comlogo], com transparência e posição."""
    larg = max(16, round(LARGURA * float(marca.get("logo_tam", 0.14))))
    op = max(0.05, min(1.0, float(marca.get("opacidade", 0.9))))
    x, y = round(LARGURA * float(marca["logo_x"])), round(ALTURA * float(marca["logo_y"]))
    quando = "+".join(f"between(t,{a:.2f},{z:.2f})"
                      for a, z in janelas_marca(dur, marca.get("quando", "sempre")))
    return (f"[{indice}:v]scale={larg}:-1,format=rgba,colorchannelmixer=aa={op:.2f}[logo];"
            f"[base][logo]overlay={x}-w/2:{y}-h/2:enable='{quando}'[comlogo];")


def filtro_video(layout: str, logo: str = "") -> str:
    """Monta o filtro do ffmpeg para cada layout. Saída sempre 1080x1920.
    `logo` é o pedaço de filtro_logo (ou vazio, sem logo)."""
    fundo = ("[0:v]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
             "boxblur=20:3,eq=brightness=-0.12,scale=1080:1920,setsar=1[fundo];")
    if layout == "centro":
        base = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,setsar=1[base];")
    else:
        if layout == "quadrado":
            frente = ("[0:v]crop='min(iw,ih)':'min(iw,ih)',scale=1080:1080,setsar=1[frente];")
        else:  # desfocado
            frente = "[0:v]scale=1080:-2,setsar=1[frente];"
        base = fundo + frente + "[fundo][frente]overlay=(W-w)/2:(H-h)/2[base];"
    if logo:
        return base + logo + "[comlogo]ass=legenda.ass[v]"
    return base + "[base]ass=legenda.ass[v]"


def _fontes_ffmpeg_link(link: str) -> list[tuple[str, dict]]:
    """Endereços diretos do vídeo e do áudio (até 1080p) pro ffmpeg ler."""
    return _fontes_link_cache(link, "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b")


_cache_link: dict[tuple[str, str], tuple[float, list]] = {}


def _fontes_link_cache(link: str, formato: str) -> list[tuple[str, dict]]:
    """Os endereços diretos expiram (YouTube: algumas horas), então guarda só 20 min."""
    import time
    import yt_dlp
    chave = (link, formato)
    if chave in _cache_link and time.time() - _cache_link[chave][0] < 1200:
        return _cache_link[chave][1]
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "format": formato}) as y:
        info = y.extract_info(link, download=False)
    formatos = info.get("requested_formats") or [info]
    r = [(f["url"], f.get("http_headers") or info.get("http_headers") or {}) for f in formatos]
    _cache_link[chave] = (time.time(), r)
    return r


def quadros(fonte: dict, ini: float, fim: float, n: int = 4, largura: int = 512) -> list[bytes]:
    """Tira `n` quadros espalhados pelo trecho (JPEG), pra IA que enxerga conferir.
    Por link, lê uma versão pequena (até 480p): é só pra olhar, não pra postar."""
    ff = ferramentas.caminho_ffmpeg() or "ffmpeg"
    if fonte.get("tipo") == "arquivo":
        entrada, cab = fonte["arquivo"], {}
    else:
        entrada, cab = _fontes_link_cache(
            fonte["link"], "bv*[height<=480]/b[height<=480]/worst")[0]
    saida = []
    for k in range(n):
        t = ini + (fim - ini) * (k + 0.5) / n
        args = [ff, "-loglevel", "error"]
        if cab:
            args += ["-headers", "".join(f"{a}: {b}\r\n" for a, b in cab.items())]
        args += ["-ss", f"{t:.2f}", "-i", entrada, "-frames:v", "1",
                 "-vf", f"scale={largura}:-2", "-q:v", "4", "-f", "image2", "-c:v", "mjpeg", "-"]
        r = subprocess.run(args, capture_output=True, creationflags=ferramentas.SEM_JANELA)
        if r.returncode == 0 and r.stdout:
            saida.append(r.stdout)
    return saida


def _entradas(fonte: dict, ini: float, dur: float) -> list[str]:
    if fonte.get("tipo") == "arquivo":
        return ["-ss", f"{ini:.3f}", "-t", f"{dur:.3f}", "-i", fonte["arquivo"]]
    args: list[str] = []
    for url, cab in _fontes_ffmpeg_link(fonte["link"]):
        if cab:
            args += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in cab.items())]
        args += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"] \
            if url.startswith("http") and ".m3u8" not in url else []
        args += ["-ss", f"{ini:.3f}", "-t", f"{dur:.3f}", "-i", url]
    return args


def renderizar(fonte: dict, clipe: dict, palavras: list[dict], pasta_saida: Path,
               numero: int, opcoes: dict, progresso: Callable[[float, str], None]) -> dict:
    ini, fim = float(clipe["inicio"]), float(clipe["fim"])
    dur = fim - ini
    nome = f"{numero:02d}-{slug(clipe.get('titulo') or 'clipe')}"
    trab = pasta_saida / f".trabalho-{numero:02d}"
    shutil.rmtree(trab, ignore_errors=True)
    trab.mkdir(parents=True)

    credito = credito_de(fonte, opcoes.get("credito", "")) if opcoes.get("mostrar_credito", True) else ""
    gancho = clipe.get("gancho", "") if opcoes.get("mostrar_gancho", True) else ""
    layout = opcoes.get("layout", "desfocado")
    marca = marca_ativa(opcoes.get("marca"))
    (trab / "legenda.ass").write_text(
        montar_ass(palavras, ini, fim, gancho, credito,
                   opcoes.get("legenda_maiuscula", True), layout, marca), encoding="utf-8")

    entradas = _entradas(fonte, ini, dur)
    n_entradas = entradas.count("-i")
    audio = f"{n_entradas - 1}:a:0" if n_entradas > 1 else "0:a:0?"
    pedaco_logo = ""
    if marca and marca["caminho_logo"]:
        entradas += ["-i", str(marca["caminho_logo"])]  # imagem parada: o overlay repete
        pedaco_logo = filtro_logo(n_entradas, marca, dur)
    if ferramentas.tem_nvenc():
        cod = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0",
               "-maxrate", "12M", "-bufsize", "24M"]
    else:
        cod = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
    mp4 = pasta_saida / f"{nome}.mp4"
    args = [ferramentas.caminho_ffmpeg() or "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            *entradas,
            "-filter_complex", filtro_video(layout, pedaco_logo),
            "-map", "[v]", "-map", audio,
            *cod, "-pix_fmt", "yuv420p", "-r", "30",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
            "-t", f"{dur:.3f}", str(mp4.resolve())]
    progresso(0.0, f"Montando o clipe {numero}: {clipe.get('titulo', '')}")
    ferramentas.rodar(args, cwd=trab)  # cwd = trab, pra achar legenda.ass sem caminho

    capa = pasta_saida / f"{nome}.jpg"
    ferramentas.rodar([ferramentas.caminho_ffmpeg() or "ffmpeg", "-y", "-loglevel", "error",
                       "-ss", f"{min(dur / 2, 8):.2f}", "-i", str(mp4), "-frames:v", "1",
                       "-vf", "scale=360:-2", "-q:v", "4", str(capa)])
    texto = texto_post(fonte, clipe, credito)
    (pasta_saida / f"{nome}.txt").write_text(texto, encoding="utf-8")
    shutil.rmtree(trab, ignore_errors=True)
    return {"video": mp4.name, "capa": capa.name, "texto": f"{nome}.txt"}


def link_no_tempo(fonte: dict, seg: float) -> str:
    link = fonte.get("link") or ""
    if not link:
        return ""
    s = int(seg)
    if "youtu" in link:
        return f"{link}{'&' if '?' in link else '?'}t={s}s"
    if "twitch.tv" in link:
        h, r = divmod(s, 3600)
        m, ss = divmod(r, 60)
        return f"{link}{'&' if '?' in link else '?'}t={h}h{m}m{ss}s"
    return link


def texto_post(fonte: dict, c: dict, credito: str) -> str:
    linhas = [f"TÍTULO: {c.get('titulo', '')}", "", "LEGENDA DO POST:", c.get("legenda_post", ""), ""]
    if credito or fonte.get("link"):
        linhas.append("Créditos: " + " · ".join(x for x in (credito, fonte.get("link", "")) if x))
        linhas.append("")
    linhas.append(" ".join(c.get("hashtags", [])))
    linhas += ["", "---",
               f"Nota da IA: {c.get('nota', '?')}/10 · Motivo: {c.get('motivo', '')}",
               f"Trecho original: {hms(c['inicio'])} a {hms(c['fim'])}"]
    lt = link_no_tempo(fonte, c["inicio"])
    if lt:
        linhas.append(lt)
    return "\n".join(linhas) + "\n"


def palavras_de(frases: list[dict]) -> list[dict]:
    return [w for f in frases for w in f.get("palavras", [])]


def salvar_json(caminho: Path, dados) -> None:
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

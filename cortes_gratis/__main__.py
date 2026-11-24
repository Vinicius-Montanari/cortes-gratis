"""Como rodar:

    python -m cortes_gratis              abre a interface no navegador
    python -m cortes_gratis LINK         corta direto pelo terminal, sem interface
    python -m cortes_gratis --instalar   baixa o ffmpeg (o instalar.bat chama isto)
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser


def _porta_livre(inicial: int) -> int:
    for p in range(inicial, inicial + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise SystemExit("Nenhuma porta livre entre 8765 e 8785.")


def _terminal(args) -> None:
    from . import pipeline

    opcoes = {k: v for k, v in {
        "idioma": args.idioma, "trecho_inicio": args.inicio, "trecho_fim": args.fim,
        "layout": args.layout, "nota_minima": args.nota_minima,
    }.items() if v not in (None, "")}
    p = pipeline.novo_projeto(args.entrada, opcoes)
    print(f"Projeto: {p.pasta}")
    t = threading.Thread(target=pipeline.rodar, args=(p,))
    t.start()
    ultima = ""
    while t.is_alive():
        msg = f"[{p.dados.get('progresso', 0) * 100:5.1f}%] {p.dados.get('mensagem', '')}"
        if msg != ultima:
            print(msg, flush=True)
            ultima = msg
        time.sleep(1)
    if p.dados.get("estado") == "erro":
        print("ERRO:", p.dados.get("erro"))
        sys.exit(1)
    print(f"\nClipes em: {p.pasta / 'clipes'}")


def main() -> None:
    for s in (sys.stdout, sys.stderr):  # acentos no terminal do Windows
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="cortes_gratis", description="Cortes Grátis")
    ap.add_argument("entrada", nargs="?", help="link ou arquivo de vídeo (sem isto, abre a interface)")
    ap.add_argument("--idioma", help="pt, en, es... (vazio = detecta sozinho)")
    ap.add_argument("--inicio", help="analisa só a partir daqui, ex.: 1:00:00")
    ap.add_argument("--fim", help="analisa só até aqui, ex.: 1:30:00")
    ap.add_argument("--layout", choices=["desfocado", "quadrado", "centro"])
    ap.add_argument("--nota-minima", type=float)
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--sem-navegador", action="store_true")
    ap.add_argument("--instalar", action="store_true", help="baixa o ffmpeg e sai")
    args = ap.parse_args()

    from . import config, ferramentas
    config.preparar_pastas()

    if args.instalar:
        def prog(frac: float, msg: str) -> None:
            print(f"\r{msg:<70}", end="", flush=True)
        caminho = ferramentas.instalar_ffmpeg(prog)
        print(f"\nffmpeg pronto: {caminho}")
        return

    if args.entrada:
        _terminal(args)
        return

    import uvicorn
    porta = _porta_livre(args.porta)
    url = f"http://127.0.0.1:{porta}"
    print(f"\n  Cortes Grátis rodando em {url}\n  Feche esta janela pra desligar.\n")
    if not args.sem_navegador:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("cortes_gratis.servidor:app", host="127.0.0.1", port=porta, log_level="warning")


if __name__ == "__main__":
    main()

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


def _instalar_ia_local(modelo: str, prog) -> None:
    """Mesma coisa do botão "Instalar e ligar", mas na janela de comando:
    se algo der errado (antivírus, internet, disco cheio), o erro aparece aqui."""
    from . import config, ollama_local

    cfg = config.carregar()
    modelo = (modelo or cfg["ia"]["ollama"]["modelo"]).strip()
    url = cfg["ia"]["ollama"]["url"]
    print(f"\n  Instalando a IA local em {config.PASTA_OLLAMA}")
    print(f"  Modelo: {modelo}\n")
    ok = False
    try:
        ollama_local.instalar(prog)
        print("\n  Ligando...")
        ollama_local.iniciar(url)
        ollama_local.baixar_modelo(modelo, prog, url)
        if cfg["visao"].get("ativo"):
            print(f"\n  Baixando também a IA que confere a imagem ({cfg['visao']['modelo_local']})...")
            ollama_local.baixar_modelo(cfg["visao"]["modelo_local"], prog, url)
        cfg["ia"]["ollama"]["modelo"] = modelo
        config.salvar(cfg)
        print(f"\n\n  Pronto! IA local instalada com o modelo {modelo}.")
        print("  Ela liga sozinha quando o programa precisar.")
        ok = True
    except Exception as e:  # noqa: BLE001
        print(f"\n\n  ERRO: {e}")
        print("\n  Se a janela do Cortes Grátis fechava sozinha ao instalar, confira se o")
        print("  antivírus não colocou o Cortes Gratis.exe ou o ollama.exe em quarentena.")
        log = config.PASTA_OLLAMA / "ollama.log"
        if log.exists():
            print(f"  Registro do Ollama: {log}")
    finally:
        ollama_local.parar()
    if getattr(sys, "frozen", False):
        input("\n  Aperte Enter pra fechar...")
    if not ok:
        sys.exit(1)


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
    ap.add_argument("--instalar-ia-local", nargs="?", const="", metavar="MODELO",
                    help="instala a IA local (Ollama) e baixa o modelo, mostrando tudo aqui")
    args = ap.parse_args()

    from . import config, ferramentas
    config.preparar_pastas()

    def prog(frac: float, msg: str) -> None:
        print(f"\r{msg:<78}", end="", flush=True)

    if args.instalar:
        caminho = ferramentas.instalar_ffmpeg(prog)
        print(f"\nffmpeg pronto: {caminho}")
        return

    if args.instalar_ia_local is not None:
        _instalar_ia_local(args.instalar_ia_local, prog)
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
    from .servidor import app  # objeto direto: funciona também dentro do .exe
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")


if __name__ == "__main__":
    main()

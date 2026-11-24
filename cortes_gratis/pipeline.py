"""Junta as etapas: analisar -> achar candidatos -> IA filtra -> cortar.

Cada vídeo vira um "projeto" numa pasta própria em dados/projetos. O
estado fica em projeto.json, então dá pra fechar o programa e voltar depois:
o que já foi feito (transcrição, avaliação) não é refeito.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from . import analise, candidatos, config, corte, ferramentas
from .ia import avaliar

# Peso de cada etapa na barra de progresso geral.
ETAPAS = [("analise", "Transcrevendo", 0.45), ("candidatos", "Procurando momentos", 0.02),
          ("ia", "IA filtrando", 0.13), ("corte", "Cortando", 0.40)]


class Projeto:
    def __init__(self, pasta: Path):
        self.pasta = pasta
        self.arquivo = pasta / "projeto.json"
        self.trava = threading.Lock()
        self.dados: dict = {}
        if self.arquivo.exists():
            self.dados = json.loads(self.arquivo.read_text(encoding="utf-8"))

    @property
    def id(self) -> str:
        return self.pasta.name

    def salvar(self) -> None:
        with self.trava:
            tmp = self.arquivo.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.dados, ensure_ascii=False, indent=2), "utf-8")
            tmp.replace(self.arquivo)

    def log(self, msg: str) -> None:
        linha = f"{datetime.now():%H:%M:%S} {msg}"
        self.dados.setdefault("log", []).append(linha)
        self.dados["log"] = self.dados["log"][-300:]
        self.dados["mensagem"] = msg
        self.salvar()

    def progresso(self, etapa: str):
        base = 0.0
        for nome, _rot, peso in ETAPAS:
            if nome == etapa:
                break
            base += peso
        peso = dict((n, p) for n, _r, p in ETAPAS)[etapa]
        ultimo = [0.0]

        def cb(frac: float, msg: str) -> None:
            if "tentando de outro jeito" in msg:  # aviso importante: vai pro registro
                self.log(msg)
            self.dados["etapa"] = etapa
            self.dados["progresso"] = round(base + peso * max(0.0, min(frac, 1.0)), 4)
            self.dados["mensagem"] = msg
            if time.time() - ultimo[0] > 0.7:  # grava no disco no máximo ~1x por segundo
                ultimo[0] = time.time()
                self.salvar()
        return cb

    def ler(self, nome: str):
        return json.loads((self.pasta / nome).read_text(encoding="utf-8"))


def novo_projeto(entrada: str, opcoes: dict) -> Projeto:
    config.preparar_pastas()
    rotulo = Path(entrada).stem if not analise.eh_link(entrada) else entrada.rstrip("/").split("/")[-1]
    pasta = config.PASTA_PROJETOS / f"{datetime.now():%Y%m%d-%H%M%S}-{corte.slug(rotulo, 30)}"
    pasta.mkdir(parents=True)
    p = Projeto(pasta)
    p.dados = {"entrada": entrada, "opcoes": opcoes, "estado": "na fila",
               "criado": datetime.now().isoformat(timespec="seconds"),
               "progresso": 0.0, "mensagem": "Na fila", "log": [], "clipes": []}
    p.salvar()
    return p


def listar_projetos() -> list[dict]:
    config.preparar_pastas()
    saida = []
    for pasta in sorted(config.PASTA_PROJETOS.iterdir(), reverse=True):
        arq = pasta / "projeto.json"
        if arq.exists():
            try:
                d = json.loads(arq.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            saida.append({"id": pasta.name, "titulo": d.get("titulo") or d.get("entrada"),
                          "estado": d.get("estado"), "criado": d.get("criado"),
                          "clipes": len(d.get("clipes", []))})
    return saida


def rodar(p: Projeto) -> None:
    """Roda o projeto inteiro. Feito pra rodar numa thread separada."""
    cfg = config.carregar()
    op = p.dados.get("opcoes", {})
    cfg["corte"].update({k: v for k, v in op.items() if k in cfg["corte"]})
    p.dados["estado"] = "rodando"
    p.dados.pop("erro", None)
    p.log("Começando")
    try:
        if not ferramentas.caminho_ffmpeg():
            ferramentas.instalar_ffmpeg(p.progresso("analise"))

        # 1. Análise (pula se já foi feita antes)
        if not (p.pasta / "transcricao.json").exists():
            trecho = (analise.para_segundos(op.get("trecho_inicio")),
                      analise.para_segundos(op.get("trecho_fim")))
            analise.analisar(p.dados["entrada"], p.pasta, cfg, op.get("idioma") or None,
                             trecho, p.progresso("analise"))
        fonte, frases, energia = p.ler("fonte.json"), p.ler("transcricao.json"), p.ler("energia.json")
        p.dados["titulo"] = fonte.get("titulo")
        p.dados["fonte"] = fonte
        w = fonte.get("whisper", {})
        p.log(f"Transcrição pronta: {len(frases)} frases, idioma {fonte.get('idioma')}, "
              f"modelo {w.get('modelo')} na {w.get('dispositivo')}")

        # 2. Candidatos
        cc = cfg["corte"]
        if not p.dados.get("candidatos"):
            p.progresso("candidatos")(0.0, "Procurando momentos animados...")
            cands = candidatos.achar(frases, energia, cc["candidatos"], cc["dur_min"], cc["dur_max"])
            if not cands:
                raise RuntimeError("Não achei nenhum trecho com fala ou som suficiente.")
            p.dados["candidatos"] = cands
            p.log(f"{len(cands)} trechos candidatos encontrados")

        # 3. IA
        cands = p.dados["candidatos"]
        if any("nota" not in c for c in cands):
            avaliar.avaliar(cands, frases, energia, fonte, cfg, p.log, p.progresso("ia"))
            p.dados["candidatos"] = cands
            p.log(f"IA usada: {cands[0].get('ia') if cands else '-'}")
        escolhidos = avaliar.escolher(cands, cfg)
        for c in cands:
            c["escolhido"] = c in escolhidos
        p.log(f"{len(escolhidos)} de {len(cands)} trechos aprovados pela IA "
              f"(nota mínima {cc['nota_minima']})")
        if not escolhidos:
            p.dados["estado"] = "pronto"
            p.log("Nenhum trecho passou da nota mínima. Baixe a nota mínima ou "
                  "escolha trechos na lista de descartados.")
            return

        # 4. Corte
        cortar(p, [c["id"] for c in escolhidos], cfg)
        p.dados["estado"] = "pronto"
        p.dados["progresso"] = 1.0
        p.log("Pronto!")
    except Exception as e:  # noqa: BLE001 - mostra qualquer erro na tela
        p.dados["estado"] = "erro"
        p.dados["erro"] = str(e)
        p.dados["detalhe_erro"] = traceback.format_exc()[-3000:]
        p.log(f"Erro: {e}")
    finally:
        p.salvar()


def cortar(p: Projeto, ids: list[int], cfg: dict | None = None) -> None:
    """Monta (ou refaz) os clipes dos candidatos com esses ids."""
    cfg = cfg or config.carregar()
    op = p.dados.get("opcoes", {})
    opcoes = cfg["corte"] | {k: v for k, v in op.items() if k in cfg["corte"] or k == "credito"}
    fonte, frases = p.ler("fonte.json"), p.ler("transcricao.json")
    palavras = corte.palavras_de(frases)
    por_id = {c["id"]: c for c in p.dados["candidatos"]}
    saida = p.pasta / "clipes"
    saida.mkdir(exist_ok=True)
    clipes = {cl["id"]: cl for cl in p.dados.get("clipes", [])}
    prog = p.progresso("corte")
    for n, cid in enumerate(ids):
        c = por_id[cid]
        antigo = clipes.get(cid)
        if antigo:  # refazendo: apaga a versão anterior
            for k in ("video", "capa", "texto"):
                (saida / antigo[k]).unlink(missing_ok=True)

        def sub(frac: float, msg: str, n=n) -> None:
            prog((n + frac) / len(ids), msg)

        arqs = corte.renderizar(fonte, c, palavras, saida, cid, opcoes, sub)
        clipes[cid] = {"id": cid, **arqs}
        c["escolhido"] = True
        p.dados["clipes"] = sorted(clipes.values(), key=lambda x: x["id"])
        p.log(f"Clipe {cid} pronto: {c.get('titulo')}")


def remover_clipe(p: Projeto, cid: int) -> None:
    saida = p.pasta / "clipes"
    restantes = []
    for cl in p.dados.get("clipes", []):
        if cl["id"] == cid:
            for k in ("video", "capa", "texto"):
                (saida / cl[k]).unlink(missing_ok=True)
        else:
            restantes.append(cl)
    p.dados["clipes"] = restantes
    for c in p.dados.get("candidatos", []):
        if c["id"] == cid:
            c["escolhido"] = False
    p.salvar()

"""Etapa 3: a IA lê cada trecho candidato e diz se presta.

A IA nunca vê o vídeo, só o texto falado (com o tempo e o volume). Isso é
pouco texto, então cabe folgado na cota grátis: uma live de 3 h gasta umas
6 a 8 perguntas.
"""
from __future__ import annotations

from typing import Callable

from ..analise import hms
from ..candidatos import linhas_do_trecho
from .cliente import Cadeia

# Quantos trechos vão em cada pergunta. As IAs grandes da nuvem dão conta de
# 4 de uma vez (economiza cota). A local, de 7B, se confunde e mistura os
# trechos (testado: repetiu o mesmo título nos 4), então vai um por vez.
POR_PERGUNTA_NUVEM = 4
POR_PERGUNTA_LOCAL = 1

SISTEMA = """Você é editor de cortes de live para TikTok, Reels e Shorts.
Recebe trechos candidatos de um vídeo longo, cada um com as falas numeradas
e o tempo. Sua tarefa é ser exigente e descartar o que não prende.

Primeiro escolha onde o clipe começa e termina (linha_inicio e linha_fim).
Depois dê a nota DO CLIPE JÁ RECORTADO, não do trecho inteiro: se dentro do
trecho tem um momento forte cercado de conversa morna, recorte só o momento
e dê a nota dele.

Você só tem o texto, sem imagem. Em live, a fala É o sinal: susto ("oh my
god", "não acredito", "corre"), risada, palavrão, comemoração ("let's go",
"vamos!") e frases repetidas de nervoso mostram que algo grande aconteceu.

Dê nota de 0 a 10 pensando em alguém rolando o feed que NUNCA viu essa live:
- 8 a 10: reação forte e clara (susto, raiva, risada, vitória, falha
  engraçada), história com começo, meio e fim, frase forte, briga, surpresa.
- 5 a 7: bom mas depende um pouco de contexto, ou a graça está mais na imagem.
- 0 a 4: conversa morna, leitura de doação ou de chat, propaganda, problema
  técnico, "vou ali", menu e loading, meio de explicação sem fecho, ou trecho
  que não se entende sozinho.
Não invente o que não está nas falas.

Regras do recorte (pelos números entre colchetes):
- começa no gancho: a primeira fala que dá vontade de ver o resto. Nunca
  começa em "então", "é...", "bom", nem no meio de assunto.
- termina depois do fecho (a reação, a risada ou a conclusão).
- falas marcadas (fora) estão fora do trecho original; use só se melhorar.
- o clipe precisa ficar entre {dur_min} e {dur_max} segundos.

Escreva título, gancho e legenda NO IDIOMA DO VÍDEO ({idioma}):
- titulo: até 8 palavras, diz o que acontece, sem prometer o que não tem.
- gancho: até 6 palavras, em MAIÚSCULAS, vai fixo no topo do vídeo.
- legenda_post: 1 ou 2 frases curtas pro post.
- hashtags: 3 a 5, do jogo ou tema + #cortes ou #clips. Nada enganoso.

Responda só com JSON, um item por trecho recebido, usando o id de cada trecho:
{{"avaliacoes": [{{"id": <id do trecho>, "linha_inicio": <n>, "linha_fim": <n>,
  "nota": <0 a 10>, "motivo": "uma linha", "titulo": "...", "gancho": "...",
  "legenda_post": "...", "hashtags": ["#..."]}}]}}"""


def _bloco(c: dict, linhas: list[dict], db: list[float], desl: float) -> str:
    out = [f"### Trecho id={c['id']}  ({hms(c['inicio'])} a {hms(c['fim'])}, "
           f"{c['fim'] - c['inicio']:.0f} s, pico de volume em {hms(c['pico'])})"]
    for ln in linhas:
        s = int(ln["i"] - desl)
        vol = db[s] if 0 <= s < len(db) else -60
        barulho = " [ALTO]" if vol > -18 else ""
        fora = " (fora)" if ln["fora"] else ""
        out.append(f"[{ln['n']}] {hms(ln['i'])}{fora}{barulho} {ln['texto']}")
    if not linhas:
        out.append("(sem fala: só som. Volume alto pode ser ação, música ou explosão)")
    return "\n".join(out)


def avaliar(cands: list[dict], frases: list[dict], energia: dict, fonte: dict,
            cfg: dict, aviso: Callable[[str], None],
            progresso: Callable[[float, str], None]) -> list[dict]:
    """Preenche nota, títulos e cortes ajustados em cada candidato."""
    cc = cfg["corte"]
    frases = sorted(frases, key=lambda f: f["i"])
    desl = float(energia.get("deslocamento") or 0)
    db = energia["db"]
    idioma = fonte.get("idioma") or "pt"
    sistema = SISTEMA.format(dur_min=cc["dur_min"], dur_max=cc["dur_max"], idioma=idioma)
    cadeia = Cadeia(cfg, aviso)

    linhas_de = {c["id"]: linhas_do_trecho(c, frases) for c in cands}
    feitos = 0
    while feitos < len(cands):
        prox = cadeia.proximo()
        n = POR_PERGUNTA_LOCAL if prox is None or prox.nome == "ollama" else POR_PERGUNTA_NUVEM
        grupo = cands[feitos:feitos + n]
        progresso(feitos / len(cands), f"IA avaliando o trecho {feitos + 1}"
                  + (f" a {feitos + len(grupo)}" if len(grupo) > 1 else "") + f" de {len(cands)}")
        feitos += len(grupo)
        aviso_lote = ("Cada trecho é independente: escreva título e gancho próprios pra cada um.\n\n"
                      if len(grupo) > 1 else "")
        usuario = (f"Vídeo: {fonte.get('titulo', '')}\nCanal: {fonte.get('canal', '')}\n\n"
                   + aviso_lote
                   + "\n\n".join(_bloco(c, linhas_de[c["id"]], db, desl) for c in grupo))
        resposta = cadeia.pedir_json(sistema, usuario)
        for c, a in zip(grupo, _casar(resposta, grupo)):
            if not a:
                c.update(nota=0, motivo="a IA não avaliou este trecho")
                continue
            _aplicar(c, a, linhas_de[c["id"]], cc)
    progresso(1.0, "IA terminou de avaliar")
    for c in cands:
        c["ia"] = ", ".join(f"{k} ×{v}" for k, v in cadeia.usadas.items())
    return cands


def _casar(resposta, grupo: list[dict]) -> list[dict | None]:
    """Liga cada avaliação ao seu trecho. Modelo pequeno às vezes erra o id
    (copia o do exemplo) ou devolve o objeto solto, sem a lista em volta."""
    if isinstance(resposta, dict):
        lista = resposta.get("avaliacoes")
        if lista is None:
            lista = [resposta] if "nota" in resposta else []
    else:
        lista = resposta
    lista = [a for a in (lista or []) if isinstance(a, dict)]
    por_id = {}
    for a in lista:
        try:
            por_id[int(a.get("id"))] = a
        except (TypeError, ValueError):
            pass
    ids = [c["id"] for c in grupo]
    if all(i in por_id for i in ids):
        return [por_id[i] for i in ids]
    if len(lista) == len(grupo):  # ids errados mas a quantidade bate: vai pela ordem
        return lista
    return [por_id.get(i) for i in ids]


def _aplicar(c: dict, a: dict, linhas: list[dict], cc: dict) -> None:
    try:
        c["nota"] = max(0.0, min(10.0, float(a.get("nota", 0))))
    except (TypeError, ValueError):
        c["nota"] = 0.0
    c["motivo"] = str(a.get("motivo", ""))[:200]
    c["titulo"] = str(a.get("titulo", "")).strip()[:80] or f"Clipe {c['id']}"
    c["gancho"] = str(a.get("gancho", "")).strip().upper()[:50]
    c["legenda_post"] = str(a.get("legenda_post", "")).strip()[:300]
    tags = a.get("hashtags") or []
    if isinstance(tags, str):
        tags = tags.split()
    c["hashtags"] = [("#" + t.lstrip("#")).replace(" ", "") for t in tags if str(t).strip()][:5]

    # Ajuste de começo e fim sugerido pela IA, só se der uma duração válida.
    try:
        li, lf = int(a.get("linha_inicio")), int(a.get("linha_fim"))
    except (TypeError, ValueError):
        return
    if linhas and 0 <= li <= lf < len(linhas):
        ini = max(0.0, linhas[li]["i"] - 0.3)
        fim = linhas[lf]["f"] + 1.2
        if cc["dur_min"] * 0.8 <= fim - ini <= cc["dur_max"] * 1.1:
            c["inicio"], c["fim"] = round(ini, 2), round(min(fim, ini + cc["dur_max"]), 2)


def escolher(cands: list[dict], cfg: dict) -> list[dict]:
    """Fica com os melhores acima da nota mínima, sem sobrepor, em ordem de tempo."""
    cc = cfg["corte"]
    bons = sorted((c for c in cands if c.get("nota", 0) >= cc["nota_minima"]),
                  key=lambda c: -c["nota"])
    final: list[dict] = []
    for c in bons:
        if len(final) >= cc["max_clipes"]:
            break
        if any(not (c["fim"] <= o["inicio"] or c["inicio"] >= o["fim"]) for o in final):
            continue  # depois do ajuste da IA, dois trechos podem ter encostado
        final.append(c)
    return sorted(final, key=lambda c: c["inicio"])

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

SISTEMA = """Você é um editor EXIGENTE de cortes de live para TikTok, Reels e Shorts.
Recebe trechos de um vídeo longo, com as falas numeradas, o tempo e [ALTO]
quando o volume estourou. Você só tem o texto, sem imagem.

A maioria dos trechos que você recebe é mediana. De cada 4, normalmente só 1
merece virar clipe. Na dúvida, nota baixa: um clipe ruim postado é pior que
nenhum.

Para CADA trecho, siga estes passos na ordem:

1. o_que_acontece: em uma frase concreta, o que acontece nas falas.
   Ex.: "Ele consegue o código do cofre e comemora gritando".
   Se não dá pra saber o que acontece, escreva "não dá pra entender".
2. linha_inicio e linha_fim: onde o clipe começa e termina (números entre
   colchetes). Comece na primeira fala que dá vontade de ver o resto (nunca
   em "então", "é...", "bom"). Termine logo depois da reação ou da conclusão.
   Falas marcadas (fora) só se melhorarem. Entre {dur_min} e {dur_max} segundos.
3. Responda com true ou false, só sobre o pedaço recortado:
   - se_entende_sozinho: alguém que nunca viu a live entende o que rolou?
   - tem_reacao_forte: tem susto, risada, raiva, comemoração ou frase de
     impacto clara NAS FALAS? (conversa normal, explicar o jogo, ler o chat,
     agradecer doação, "vamos lá" = false)
   - tem_fecho: termina com uma reação, piada ou conclusão (não corta no meio)?
4. nota de 0 a 10:
   - 8 a 10: reação forte e clara + se entende sozinho + tem fecho.
   - 6 a 7: bom, mas falta uma dessas coisas.
   - 0 a 5: conversa morna, explicação, leitura de chat/doação, propaganda,
     problema técnico, "vou ali", ou não se entende sozinho.
5. motivo: uma linha dizendo por que deu essa nota.

Cuidados:
- A transcrição é automática e erra. Palavra sem sentido (ex.: "DGELET") é
  erro: não use em título nem gancho e não conte como reação.
- Em jogo, falas dos personagens (NPC) aparecem misturadas com as do streamer.
  Só a reação DO STREAMER conta como reação.
- Não invente o que não está nas falas.

Escreva título, gancho e legenda NO IDIOMA DO VÍDEO ({idioma}):
- titulo: até 8 palavras, diz o que acontece. Bom: "Achou o código do cofre
  no último segundo". Ruim: "Problema com polícia", "Conversa sobre jogo".
- gancho: até 6 palavras, MAIÚSCULAS, fixo no topo do vídeo. Tem que dar
  curiosidade sobre ESTE trecho. Bom: "ELE NÃO ESPERAVA ESSE CÓDIGO",
  "A BOMBA NÃO FUNCIONOU". Ruim: "PROBLEMA!", "VAMOS LÁ!", "CONVERSANDO",
  "BOMBA!" (genérico demais).
- legenda_post: 1 ou 2 frases curtas pro post.
- hashtags: 3 a 5, do jogo ou tema + #cortes ou #clips. Nada enganoso.

Responda só com JSON, um item por trecho, usando o id de cada trecho:
{{"avaliacoes": [{{"id": <id>, "o_que_acontece": "...", "linha_inicio": <n>,
  "linha_fim": <n>, "se_entende_sozinho": <true/false>, "tem_reacao_forte": <true/false>,
  "tem_fecho": <true/false>, "nota": <0 a 10>, "motivo": "...", "titulo": "...",
  "gancho": "...", "legenda_post": "...", "hashtags": ["#..."]}}]}}"""


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
            c["avaliado_por"] = cadeia.ultimo
            if not a:
                c.update(nota=0, motivo="a IA não avaliou este trecho")
                continue
            _aplicar(c, a, linhas_de[c["id"]], cc)
            ajustar_local(c, cc)
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


def _sim(valor) -> bool | None:
    """true/false da IA, que às vezes vem como texto ("true", "sim")."""
    if isinstance(valor, bool):
        return valor
    if valor is None:
        return None
    return str(valor).strip().lower() in ("true", "sim", "yes", "1")


def _limitar(nota: float, a: dict) -> tuple[float, list[str]]:
    """Modelo pequeno dá nota alta pra tudo. A lista de verificação que ele
    mesmo preencheu segura a nota: sem reação forte, no máximo 6; não se
    entende sozinho, no máximo 5; sem fecho, perde 1."""
    porque = []
    if _sim(a.get("tem_reacao_forte")) is False and nota > 6:
        nota = 6.0
        porque.append("sem reação forte")
    if _sim(a.get("se_entende_sozinho")) is False and nota > 5:
        nota = 5.0
        porque.append("não se entende sozinho")
    if _sim(a.get("tem_fecho")) is False:
        nota -= 1
        porque.append("sem fecho")
    o_que = str(a.get("o_que_acontece", "")).lower()
    if "não dá pra entender" in o_que or "nao da pra entender" in o_que:
        nota = min(nota, 3.0)
        porque.append("a IA não entendeu o que acontece")
    return max(0.0, nota), porque


def _aplicar(c: dict, a: dict, linhas: list[dict], cc: dict) -> None:
    try:
        nota = max(0.0, min(10.0, float(a.get("nota", 0))))
    except (TypeError, ValueError):
        nota = 0.0
    c["nota_ia"] = nota
    c["nota"], porque = _limitar(nota, a)
    c["o_que_acontece"] = str(a.get("o_que_acontece", "")).strip()[:200]
    # A lista de verificação vai pra interface (selos no clipe).
    c["checagem"] = {k: _sim(a.get(k)) for k in ("se_entende_sozinho", "tem_reacao_forte", "tem_fecho")}
    motivo = str(a.get("motivo", "")).strip()[:200]
    if porque:
        motivo += f" (nota limitada: {', '.join(porque)})"
    c["motivo"] = motivo
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


def ajustar_local(c: dict, cc: dict) -> None:
    """A IA local (modelo pequeno) é mais boazinha: a nota dela perde
    `ajuste_local` pontos, e o motivo diz isso. Assim a nota mínima que a
    pessoa escolheu vale como ela escolheu (antes a régua subia sozinha)."""
    extra = float(cc.get("ajuste_local", 1.0) or 0)
    if c.get("avaliado_por") != "ollama" or extra <= 0 or "nota" not in c:
        return
    c["nota"] = round(max(0.0, c["nota"] - extra), 1)
    c["ajuste_local"] = extra
    c["motivo"] = f"{c.get('motivo', '')} (IA local: −{extra:g} de ajuste)".strip()


def minima_de(c: dict, cfg: dict) -> float:
    """Nota mínima pra esse trecho virar clipe: a que a pessoa escolheu."""
    return float(cfg["corte"]["nota_minima"])


def passou(c: dict, cfg: dict) -> bool:
    return c.get("nota", 0) >= minima_de(c, cfg)


def escolher(cands: list[dict], cfg: dict) -> list[dict]:
    """Fica com os melhores acima da nota mínima, sem sobrepor, em ordem de tempo."""
    cc = cfg["corte"]
    bons = sorted((c for c in cands if passou(c, cfg)), key=lambda c: -c["nota"])
    final: list[dict] = []
    for c in bons:
        if len(final) >= cc["max_clipes"]:
            break
        if any(not (c["fim"] <= o["inicio"] or c["inicio"] >= o["fim"]) for o in final):
            continue  # depois do ajuste da IA, dois trechos podem ter encostado
        final.append(c)
    return sorted(final, key=lambda c: c["inicio"])

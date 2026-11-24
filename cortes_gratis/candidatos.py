"""Etapa 2: acha os trechos que podem virar clipe, sem IA nenhuma.

A ideia é simples: momento bom de live quase sempre tem alguma destas pistas:
  - o volume sobe de repente (grito, risada, explosão);
  - aparece palavra de reação ("não acredito", "caralho", "kkkk", "no way");
  - a pessoa começa a falar mais rápido.

Cada segundo do vídeo ganha uma nota por essas pistas. Os picos viram
candidatos, e cada candidato é esticado até começar e terminar em frase
inteira. Depois a IA só precisa dizer quais prestam.
"""
from __future__ import annotations

import bisect
import re
import unicodedata

import numpy as np

# Palavras e expressões de reação em português, inglês e espanhol.
# Sem acento e em minúsculas, porque o texto é normalizado antes.
REACOES = [
    # português
    # (palavras comuns demais, tipo "nossa" e "vamos", ficaram de fora de propósito)
    "nao acredito", "meu deus", "caralho", "porra", "socorro", "que isso",
    "mano do ceu", "ai meu deus", "olha isso", "ce ta loco", "ta maluco", "puta merda",
    "eita", "vish", "misericordia", "pqp", "cacete", "corre corre", "morri",
    "que doideira", "absurdo", "inacreditavel", "nao pode ser", "nao nao nao",
    # inglês
    "oh my god", "no way", "what the", "holy", "wtf", "lets go", "let's go", "insane",
    "are you kidding", "oh no", "clutch", "run run",
    # espanhol
    "no puede ser", "dios mio", "que es eso", "madre mia", "increible",
]
# \b nas pontas: "run" não pode casar dentro de "running", nem "holy" em "wholly".
_REACOES_RE = re.compile(r"\b(" + "|".join(re.escape(r) for r in REACOES) + r")\b")
RISADA = re.compile(r"\b(k{3,}|(ha){2,}h?|(he){2,}|(ja){2,}|rs(rs)+|lol|lmao)\b")


def _normalizar(txt: str) -> str:
    t = unicodedata.normalize("NFKD", txt.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def pontos_reacao(texto: str) -> float:
    t = _normalizar(texto)
    t = re.sub(r"[^\w' ]+", " ", t)  # "não, não, não!" vira "nao nao nao"
    t = re.sub(r" +", " ", t)
    n = float(len(_REACOES_RE.findall(t)))
    n += 1.5 * len(RISADA.findall(t))
    n += 0.5 * texto.count("!")
    n += 0.3 * texto.count("?")
    return float(n)


def _suavizar(x: np.ndarray, janela: int) -> np.ndarray:
    if len(x) == 0 or janela <= 1:
        return x
    k = np.ones(janela) / janela
    return np.convolve(x, k, mode="same")


def nota_por_segundo(frases: list[dict], db: list[float], deslocamento: float) -> np.ndarray:
    """Nota de 'quão animado' está cada segundo do áudio analisado."""
    n = len(db)
    if n == 0:
        return np.zeros(0)
    vol = np.array(db, dtype=np.float32)

    # 1) Volume acima do normal daquele pedaço da live (mediana móvel de 2 min),
    #    em unidades de "desvio típico". Assim live baixa e live alta funcionam igual.
    janela = 120
    base = np.array([np.median(vol[max(0, i - janela // 2): i + janela // 2 + 1])
                     for i in range(0, n, 5)])
    base = np.repeat(base, 5)[:n]
    desvio = np.median(np.abs(vol - base)) + 1.0
    alto = np.clip((vol - base) / desvio, 0, 4)

    # 2) Subida brusca: silêncio seguido de explosão.
    subida = np.clip(np.diff(vol, prepend=vol[0]) / 10.0, 0, 2)

    # 3) Palavras de reação e velocidade da fala, colocadas no segundo em que aparecem.
    reacao = np.zeros(n, dtype=np.float32)
    densidade = np.zeros(n, dtype=np.float32)
    for fr in frases:
        s = int(fr["i"] - deslocamento)
        if 0 <= s < n:
            reacao[s] += pontos_reacao(fr["texto"])
        for w in fr.get("palavras", []):
            ws = int(w["i"] - deslocamento)
            if 0 <= ws < n:
                densidade[ws] += 1
    densidade = np.clip(_suavizar(densidade, 5) / 3.0, 0, 2)

    nota = 1.0 * alto + 0.6 * subida + 1.5 * np.clip(reacao, 0, 4) + 0.4 * densidade
    return _suavizar(nota, 5)


def _ajustar_ao_texto(ini: float, fim: float, frases: list[dict], inicios: list[float],
                      pico: float, dur_min: float, dur_max: float) -> tuple[float, float]:
    """Faz o trecho começar no início de uma frase e terminar no fim de uma."""
    if not frases:
        return ini, fim
    # Começo: a frase cujo início está mais perto do desejado, sem passar do pico.
    i = bisect.bisect_left(inicios, ini)
    opcoes = [j for j in (i - 1, i) if 0 <= j < len(frases) and frases[j]["i"] <= pico]
    if opcoes:
        j = min(opcoes, key=lambda k: abs(frases[k]["i"] - ini))
        ini = max(0.0, frases[j]["i"] - 0.3)
    # Fim: o fim da frase que está tocando nesse momento (mais folga pra reação).
    k = bisect.bisect_right(inicios, fim) - 1
    if 0 <= k < len(frases) and frases[k]["f"] >= fim - 0.5:
        fim = frases[k]["f"] + 1.2
    # Respeita duração mínima e máxima esticando ou encurtando pelo fim.
    while fim - ini < dur_min and k + 1 < len(frases):
        k += 1
        fim = frases[k]["f"] + 1.2
    if fim - ini < dur_min:
        fim = ini + dur_min
    if fim - ini > dur_max:
        fim = ini + dur_max
    return round(ini, 2), round(fim, 2)


def achar(frases: list[dict], energia: dict, quantos: int = 24,
          dur_min: float = 20, dur_max: float = 60) -> list[dict]:
    """Devolve até `quantos` trechos candidatos, sem sobreposição, em ordem de tempo."""
    db = energia["db"]
    desl = float(energia.get("deslocamento") or 0.0)
    nota = nota_por_segundo(frases, db, desl)
    if len(nota) == 0:
        return []
    total = desl + len(nota)
    frases = sorted(frases, key=lambda f: f["i"])
    inicios = [f["i"] for f in frases]

    usados: list[tuple[float, float]] = []
    saida: list[dict] = []
    ordem = np.argsort(-nota)
    alvo = (dur_min + dur_max) / 2  # duração ideal, ~40 s

    for s in ordem:
        if len(saida) >= quantos or nota[s] <= 0.3:
            break
        pico = desl + float(s)
        if any(a - 3 <= pico <= b + 3 for a, b in usados):
            continue
        # O que prende costuma ser a preparação + a reação: pega um pouco mais
        # antes do pico. A IA ainda pode encurtar o começo depois.
        ini = max(desl, pico - alvo * 0.5)
        fim = min(total, pico + alvo * 0.5)
        ini, fim = _ajustar_ao_texto(ini, fim, frases, inicios, pico, dur_min, dur_max)
        fim = min(fim, total)
        if fim - ini < dur_min * 0.75:
            continue
        if any(not (fim <= a - 1 or ini >= b + 1) for a, b in usados):
            continue
        usados.append((ini, fim))
        a, b = int(ini - desl), int(fim - desl)
        saida.append({
            "inicio": ini,
            "fim": fim,
            "pico": round(pico, 1),
            "pontos": round(float(nota[s]), 2),
            "volume_max": round(float(max(db[a:b] or [-60])), 1),
        })

    saida.sort(key=lambda c: c["inicio"])
    for n, c in enumerate(saida, 1):
        c["id"] = n
    return saida


def linhas_do_trecho(c: dict, frases: list[dict], extra_antes: int = 2,
                     extra_depois: int = 3) -> list[dict]:
    """As frases de dentro do trecho, mais algumas de fora, pra IA poder
    sugerir começar um pouco antes ou terminar um pouco depois."""
    dentro = [k for k, f in enumerate(frases) if f["f"] > c["inicio"] and f["i"] < c["fim"]]
    if not dentro:
        return []
    a = max(0, dentro[0] - extra_antes)
    b = min(len(frases), dentro[-1] + 1 + extra_depois)
    linhas = []
    for n, k in enumerate(range(a, b)):
        f = frases[k]
        linhas.append({"n": n, "i": f["i"], "f": f["f"], "texto": f["texto"],
                       "fora": k not in dentro})
    return linhas

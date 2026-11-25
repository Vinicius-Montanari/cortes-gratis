"""Etapa 3b: uma IA que enxerga confere a imagem dos trechos aprovados.

A IA de texto só lê a fala, então se engana fácil: "oh meu deus" numa loja
de armas vira "susto". Aqui, 4 quadros de cada trecho vão pra uma IA de
visão, que diz o que aparece e que tipo de cena é. Menu, loja, tela de
carregamento e tela preta são reprovados na hora; nos outros, a nota da
imagem entra na nota final.

Ordem: Gemini (se tiver chave; melhor e mais rápido) e depois a IA local
(Qwen3-VL 4B por padrão: 3,3 GB, ~5 GB de VRAM, ~3 s por trecho).
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Callable

from .. import corte, ollama_local
from .cliente import ErroCota, ErroIA, NOMES, Provedor, extrair_json

TIPOS_RUINS = {"menu_ou_loja", "carregamento_ou_tela_preta"}

PERGUNTA = """Estes são {n} quadros, em ordem, de um trecho de live (jogo, conversa ou
podcast) que pode virar clipe pro TikTok.
Título proposto (a partir da fala): "{titulo}"
Motivo de quem escolheu pela fala: "{motivo}"

Olhe só a IMAGEM e preencha os campos:
- o_que_aparece: descreva com as suas palavras, em uma frase, o que aparece nos quadros
- tipo: um destes: gameplay_acao, gameplay_calmo, menu_ou_loja, carregamento_ou_tela_preta, so_camera, conversa
- imagem_combina_com_titulo: true se a imagem mostra o que o título promete, senão false
- nota_visual: de 0 a 10, quanto a imagem prende quem rola o feed. Menu, inventário,
  loja, mapa, tela de carregamento ou tela preta: no máximo 3.

Responda só com o JSON, assim:
{{"o_que_aparece": "...", "tipo": "...", "imagem_combina_com_titulo": true, "nota_visual": 0}}"""

# Se o modelo devolver um destes no lugar da descrição, ele só copiou o exemplo.
_COPIAS = {"", "...", "uma frase dizendo o que se vê", "descreva aqui"}


# ------------------------------------------------------------------ provedores

def _pedir_gemini(p: Provedor, texto: str, imagens: list[bytes]) -> str:
    conteudo = [{"type": "text", "text": texto}] + [
        {"type": "image_url",
         "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(i).decode()}}
        for i in imagens]
    corpo = {"model": p.modelo, "temperature": 0.2,
             "response_format": {"type": "json_object"},
             "messages": [{"role": "user", "content": conteudo}]}
    from .cliente import _requisicao
    r = _requisicao(p.url + "/chat/completions", p.chave, corpo, 120)
    return r["choices"][0]["message"]["content"] or ""


def _pedir_ollama(url_cfg: str, modelo: str, texto: str, imagens: list[bytes]) -> str:
    # API nativa do Ollama: deixa aumentar o contexto (num_ctx). Com o padrão
    # (4096), 4 imagens estouram o limite no Qwen3-VL.
    corpo = {"model": modelo, "stream": False, "format": "json",
             "options": {"temperature": 0.2, "num_ctx": 8192},
             "messages": [{"role": "user", "content": texto,
                           "images": [base64.b64encode(i).decode() for i in imagens]}]}
    req = urllib.request.Request(ollama_local.base_api(url_cfg) + "/api/chat",
                                 data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())["message"]["content"]
    except urllib.error.HTTPError as e:
        raise ErroIA(f"erro {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e


def _liberar_texto(url_cfg: str, modelo: str) -> None:
    """Tira o modelo de texto da placa antes de carregar o de visão
    (numa placa de 8 a 12 GB, os dois juntos podem não caber)."""
    try:
        corpo = json.dumps({"model": modelo, "keep_alive": 0}).encode()
        urllib.request.urlopen(urllib.request.Request(
            ollama_local.base_api(url_cfg) + "/api/generate", data=corpo,
            headers={"Content-Type": "application/json"}), timeout=30).read()
    except Exception:
        pass


class Visao:
    def __init__(self, cfg: dict, aviso: Callable[[str], None]):
        self.cfg = cfg
        self.aviso = aviso
        self.fora: set[str] = set()
        self.prontos: set[str] = set()
        self.usadas: dict[str, int] = {}

    def _ordem(self) -> list[str]:
        saida = []
        for nome in self.cfg["visao"].get("ordem", ["gemini", "ollama"]):
            pc = self.cfg["ia"].get(nome, {})
            if nome in self.fora or not pc.get("ativo"):
                continue
            if nome != "ollama" and not pc.get("chave"):
                continue
            saida.append(nome)
        return saida

    def perguntar(self, texto: str, imagens: list[bytes]) -> dict:
        erros = []
        for nome in self._ordem():
            pc = self.cfg["ia"][nome]
            try:
                if nome == "ollama":
                    modelo = self.cfg["visao"]["modelo_local"]
                    if nome not in self.prontos:
                        ollama_local.garantir_pronto(modelo, self.aviso, pc["url"])
                        _liberar_texto(pc["url"], pc["modelo"])
                        self.prontos.add(nome)
                    resposta = _pedir_ollama(pc["url"], modelo, texto, imagens)
                    rotulo = f"{NOMES['ollama']} ({modelo})"
                else:
                    p = Provedor(nome, pc)
                    if nome not in self.prontos:
                        p.preparar(self.aviso)
                        pc["modelo"] = p.modelo  # guarda o Flash escolhido
                        self.prontos.add(nome)
                    p.modelo = pc["modelo"]
                    resposta = _pedir_gemini(p, texto, imagens)
                    rotulo = p.rotulo
                dados = extrair_json(resposta)
                if isinstance(dados, dict):
                    self.usadas[rotulo] = self.usadas.get(rotulo, 0) + 1
                    return dados
                erros.append(f"{nome}: resposta fora do formato")
            except ErroCota:
                self.aviso(f"{NOMES.get(nome, nome)}: cota de imagens esgotada, passando pra próxima")
                self.fora.add(nome)
            except Exception as e:  # noqa: BLE001
                self.aviso(f"Conferência de imagem com {NOMES.get(nome, nome)} falhou: {e}")
                erros.append(f"{nome}: {e}")
                self.fora.add(nome)
        raise ErroIA("nenhuma IA de imagem respondeu. " + " | ".join(erros))


# ------------------------------------------------------------------ regra da nota

def combinar(c: dict, v: dict, peso: float) -> None:
    """Junta a nota da fala com o que a IA viu. Muda `c` no lugar."""
    try:
        nv = max(0.0, min(10.0, float(v.get("nota_visual", 5))))
    except (TypeError, ValueError):
        nv = 5.0
    tipo = str(v.get("tipo", "")).strip().lower()
    combina = v.get("imagem_combina_com_titulo")
    combina = combina if isinstance(combina, bool) else str(combina).lower() == "true"
    c["nota_texto"] = c.get("nota_texto", c.get("nota", 0))
    nota = (1 - peso) * c["nota_texto"] + peso * nv
    if not combina:
        nota -= 1
    if tipo in TIPOS_RUINS:
        nota = min(nota, 3.0)
    c["nota"] = round(max(0.0, min(10.0, nota)), 1)
    desc = str(v.get("o_que_aparece", "")).strip()[:200]
    if desc.lower().strip(".") in _COPIAS:
        desc = tipo.replace("_", " ") or "sem descrição"
    c["visao"] = {"o_que_aparece": desc, "tipo": tipo, "combina": combina, "nota_visual": nv}
    extra = f"Imagem: {desc}"
    if tipo in TIPOS_RUINS:
        extra = "Reprovado pela imagem (" + tipo.replace("_", " ") + "). " + extra
    c["motivo"] = f"{c.get('motivo', '')} · {extra}".strip(" ·")


def conferir(cands: list[dict], fonte: dict, cfg: dict, aviso: Callable[[str], None],
             progresso: Callable[[float, str], None]) -> list[dict]:
    """Confere a imagem de todo trecho que passou na nota mínima pela fala."""
    from .avaliar import passou
    alvo = [c for c in cands if passou(c, cfg) and "visao" not in c]
    if not alvo:
        return cands
    v = Visao(cfg, aviso)
    peso = float(cfg["visao"].get("peso", 0.4))
    for k, c in enumerate(alvo):
        progresso(k / len(alvo), f"Conferindo a imagem do trecho {k + 1} de {len(alvo)}")
        imgs = corte.quadros(fonte, c["inicio"], c["fim"])
        if not imgs:
            aviso(f"Trecho {c['id']}: não consegui tirar os quadros; fica só a nota da fala")
            continue
        texto = PERGUNTA.format(n=len(imgs), titulo=c.get("titulo", ""), motivo=c.get("motivo", ""))
        try:
            combinar(c, v.perguntar(texto, imgs), peso)
        except ErroIA as e:
            aviso(f"Conferência de imagem desligada neste corte: {e}")
            break
    progresso(1.0, "Imagens conferidas")
    if v.usadas:
        aviso("IA de imagem usada: " + ", ".join(f"{k} ×{n}" for k, n in v.usadas.items()))
    return cands

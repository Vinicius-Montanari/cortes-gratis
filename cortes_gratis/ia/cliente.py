"""Conversa com as IAs. Groq, Gemini e Ollama falam o mesmo "idioma" (o
formato de API do OpenAI), então um cliente só atende as três.

A cadeia tenta as IAs na ordem configurada. Se uma estoura a cota grátis ou
está fora do ar, passa pra próxima. A IA local (Ollama) fica por último e é
ligada sozinha quando chega a vez dela.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Callable

NOMES = {"groq": "Groq", "gemini": "Gemini", "ollama": "IA local (Ollama)"}


class ErroIA(Exception):
    """Falha que faz pular pra próxima IA da lista."""


class ErroCota(ErroIA):
    """Acabou a cota grátis (por minuto ou por dia)."""

    def __init__(self, msg: str, esperar: float = 0):
        super().__init__(msg)
        self.esperar = esperar


def _requisicao(url: str, chave: str, corpo: dict | None, timeout: float) -> dict:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    cab = {"Content-Type": "application/json", "User-Agent": "cortes-gratis"}
    if chave:
        cab["Authorization"] = f"Bearer {chave}"
    req = urllib.request.Request(url, data=dados, headers=cab,
                                 method="POST" if dados else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "replace")[:500]
        if e.code == 429:
            esperar = float(e.headers.get("retry-after") or 0)
            raise ErroCota(f"cota esgotada ({e.code}): {texto}", esperar) from e
        if e.code in (401, 403):
            raise ErroIA(f"chave recusada ({e.code}). Confira a chave nas Configurações.") from e
        raise ErroIA(f"erro {e.code}: {texto}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise ErroIA(f"sem conexão: {e}") from e


def extrair_json(texto: str) -> dict | list:
    """Pega o JSON da resposta mesmo se a IA puser texto ou ``` em volta."""
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", texto, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def listar_modelos(url: str, chave: str) -> list[str]:
    r = _requisicao(url.rstrip("/") + "/models", chave, None, 30)
    return [m["id"].removeprefix("models/") for m in r.get("data", [])]


def _versao(nome: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", nome)[:3])


def escolher_gemini(url: str, chave: str) -> str:
    """O Google troca o nome do modelo grátis de tempos em tempos. Em vez de
    fixar um, pega o 'flash' mais novo que a conta enxerga."""
    ruins = ("lite", "image", "tts", "audio", "live", "embedding", "thinking", "exp", "preview")
    nomes = [m for m in listar_modelos(url, chave)
             if "gemini" in m and "flash" in m and not any(r in m for r in ruins)]
    if not nomes:
        nomes = [m for m in listar_modelos(url, chave) if "gemini" in m and "flash" in m]
    if not nomes:
        raise ErroIA("nenhum modelo Gemini Flash disponível nessa chave")
    return max(nomes, key=_versao)


class Provedor:
    def __init__(self, nome: str, cfg: dict):
        self.nome = nome
        self.url = cfg["url"].rstrip("/")
        self.chave = cfg.get("chave", "")
        self.modelo = cfg.get("modelo", "")
        self.parado_ate = 0.0  # quando a cota estourar, descansa até esse horário

    @property
    def rotulo(self) -> str:
        return f"{NOMES.get(self.nome, self.nome)} ({self.modelo or '?'})"

    def preparar(self, aviso: Callable[[str], None]) -> None:
        if self.nome == "ollama":
            from .. import ollama_local
            ollama_local.garantir_pronto(self.modelo, aviso, self.url)
        elif not self.chave:
            raise ErroIA("sem chave configurada")
        if self.nome == "gemini" and not self.modelo:
            self.modelo = escolher_gemini(self.url, self.chave)

    def conversar(self, sistema: str, usuario: str) -> str:
        corpo = {
            "model": self.modelo,
            "messages": [{"role": "system", "content": sistema},
                         {"role": "user", "content": usuario}],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }
        timeout = 600 if self.nome == "ollama" else 120
        r = _requisicao(self.url + "/chat/completions", self.chave, corpo, timeout)
        try:
            return r["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise ErroIA(f"resposta estranha: {str(r)[:300]}") from e


class Cadeia:
    """Lista ordenada de IAs com troca automática."""

    def __init__(self, cfg: dict, aviso: Callable[[str], None]):
        self.aviso = aviso
        self.provedores: list[Provedor] = []
        for nome in cfg.get("ordem_ia", []):
            pc = cfg["ia"].get(nome)
            if pc and pc.get("ativo"):
                self.provedores.append(Provedor(nome, pc))
        self._prontos: set[str] = set()
        self._fora: set[str] = set()
        self.usadas: dict[str, int] = {}
        self.ultimo = ""

    def proximo(self) -> Provedor | None:
        """A IA que vai ser usada no próximo pedido (se nada falhar)."""
        for p in self.provedores:
            tem_chave = p.nome == "ollama" or p.chave
            if tem_chave and p.nome not in self._fora and time.time() >= p.parado_ate:
                return p
        return None

    def pedir_json(self, sistema: str, usuario: str) -> dict | list:
        erros = []
        for p in self.provedores:
            if p.nome in self._fora:
                continue
            if time.time() < p.parado_ate:
                erros.append(f"{p.rotulo}: descansando da cota")
                continue
            for tentativa in range(3):
                try:
                    if p.nome not in self._prontos:
                        p.preparar(self.aviso)
                        self._prontos.add(p.nome)
                    resposta = p.conversar(sistema, usuario)
                    dados = extrair_json(resposta)
                    self.usadas[p.rotulo] = self.usadas.get(p.rotulo, 0) + 1
                    self.ultimo = p.nome  # quem respondeu (a régua da IA local é outra)
                    return dados
                except ErroCota as e:
                    # Limite por minuto: espera um pouco e tenta de novo.
                    # Limite por dia (ou espera longa): pula pra próxima IA.
                    if e.esperar and e.esperar <= 30 and tentativa < 2:
                        self.aviso(f"{p.rotulo}: limite por minuto, esperando {e.esperar:.0f} s")
                        time.sleep(e.esperar + 1)
                        continue
                    p.parado_ate = time.time() + max(e.esperar, 300)
                    erros.append(f"{p.rotulo}: cota grátis esgotada")
                    self.aviso(f"{p.rotulo}: cota grátis esgotada, passando pra próxima IA")
                    break
                except json.JSONDecodeError:
                    if tentativa < 2:
                        continue  # a IA às vezes erra o formato; tenta de novo
                    erros.append(f"{p.rotulo}: respondeu fora do formato")
                    break
                except ErroIA as e:
                    erros.append(f"{p.rotulo}: {e}")
                    if "sem chave" not in str(e):
                        self.aviso(f"{p.rotulo}: {e}")
                    self._fora.add(p.nome)
                    break
                except Exception as e:  # noqa: BLE001 - ex.: falha ao instalar Ollama
                    erros.append(f"{p.rotulo}: {e}")
                    self.aviso(f"{p.rotulo}: {e}")
                    self._fora.add(p.nome)
                    break
        raise ErroIA("Nenhuma IA respondeu. " + " | ".join(erros))

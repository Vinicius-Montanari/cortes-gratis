"""Caminhos e configuração do Cortes Grátis.

Tudo que o programa baixa (ffmpeg, modelos de transcrição, a IA local e os
vídeos) fica dentro da pasta do programa. Então, se você colocar o programa
em F:\\cortes-gratis, nada vai parar no seu C:.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from copy import deepcopy
from pathlib import Path

# Pasta raiz do programa. Rodando pelo código: onde está o README.
# Rodando pelo .exe instalado: a pasta do Cortes Gratis.exe.
if getattr(sys, "frozen", False):
    RAIZ = Path(sys.executable).resolve().parent
else:
    RAIZ = Path(__file__).resolve().parent.parent

# Dá pra mudar a pasta de dados com a variável CORTES_DADOS, se quiser
# deixar o programa num disco e os arquivos pesados em outro.
DADOS = Path(os.environ.get("CORTES_DADOS", RAIZ / "dados")).resolve()

PASTA_FERRAMENTAS = DADOS / "ferramentas"    # ffmpeg
PASTA_WHISPER = DADOS / "modelos-whisper"    # modelos de transcrição
PASTA_OLLAMA = DADOS / "ollama"              # programa da IA local
PASTA_OLLAMA_MODELOS = DADOS / "ollama" / "modelos"
PASTA_PROJETOS = DADOS / "projetos"          # um subpasta por vídeo cortado
ARQUIVO_CONFIG = DADOS / "config.json"

# Bibliotecas que guardam cache na pasta do usuário (no C:) passam a guardar aqui.
os.environ.setdefault("HF_HOME", str(DADOS / "cache-huggingface"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("XDG_CACHE_HOME", str(DADOS / "cache"))

PADRAO: dict = {
    # Ordem em que as IAs são tentadas. Quando uma falha ou acaba a cota
    # grátis, passa pra próxima. A local fica por último, como reserva.
    "ordem_ia": ["groq", "gemini", "ollama"],
    "ia": {
        "groq": {
            "ativo": True,
            "chave": "",
            "modelo": "llama-3.3-70b-versatile",
            "url": "https://api.groq.com/openai/v1",
        },
        "gemini": {
            "ativo": True,
            "chave": "",
            "modelo": "",  # vazio = escolhe sozinho o "flash" mais novo
            "url": "https://generativelanguage.googleapis.com/v1beta/openai",
        },
        "ollama": {
            "ativo": True,
            "chave": "",
            "modelo": "qwen2.5:7b",
            # Porta própria (11435) pra não misturar com um Ollama do sistema.
            "url": "http://127.0.0.1:11435/v1",
        },
    },
    # Conferência pela imagem: depois que a IA de texto aprova um trecho,
    # uma IA que enxerga olha 4 quadros e reprova menu, loja, loading etc.
    "visao": {
        "ativo": True,
        "ordem": ["gemini", "ollama"],     # Gemini se tiver chave; senão a local
        "modelo_local": "qwen3-vl:4b-instruct",
        "peso": 0.4,                       # quanto a nota da imagem pesa na nota final
    },
    "whisper": {
        "modelo": "auto",   # auto = large-v3-turbo com placa de vídeo, small sem
        "dispositivo": "auto",  # auto, cuda ou cpu
    },
    "corte": {
        "nota_minima": 6,       # clipes com nota menor são descartados
        "ajuste_local": 1,      # a IA local é mais boazinha: exige 1 ponto a mais dela
        "max_clipes": 8,
        "candidatos": 24,       # quantos trechos a IA avalia
        "dur_min": 20,
        "dur_max": 60,
        "layout": "desfocado",  # desfocado, quadrado ou centro
        "legenda_maiuscula": True,
        "mostrar_gancho": True,
        "mostrar_credito": True,
    },
}

_trava = threading.Lock()


def _mesclar(base: dict, novo: dict) -> dict:
    saida = deepcopy(base)
    for k, v in (novo or {}).items():
        if isinstance(v, dict) and isinstance(saida.get(k), dict):
            saida[k] = _mesclar(saida[k], v)
        else:
            saida[k] = v
    return saida


def carregar() -> dict:
    with _trava:
        if ARQUIVO_CONFIG.exists():
            try:
                salvo = json.loads(ARQUIVO_CONFIG.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                salvo = {}
            return _mesclar(PADRAO, salvo)
        return deepcopy(PADRAO)


def salvar(cfg: dict) -> dict:
    cfg = _mesclar(PADRAO, cfg)
    with _trava:
        DADOS.mkdir(parents=True, exist_ok=True)
        tmp = ARQUIVO_CONFIG.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(ARQUIVO_CONFIG)
    return cfg


def preparar_pastas() -> None:
    for p in (DADOS, PASTA_FERRAMENTAS, PASTA_WHISPER, PASTA_PROJETOS):
        p.mkdir(parents=True, exist_ok=True)

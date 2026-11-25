"""Servidor da interface. Roda só no seu computador (127.0.0.1) e abre no
navegador. Nada fica exposto pra internet."""
from __future__ import annotations

import os
import platform
import queue
import subprocess
import threading
import traceback
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, config, ferramentas, gpu, ollama_local, pipeline
from .ia import cliente

WEB = Path(__file__).parent / "web"
app = FastAPI(title="Cortes Grátis", docs_url=None, redoc_url=None)

# ------------------------------------------------------------------ segurança
# Um site qualquer aberto no navegador poderia tentar mandar pedidos pra
# 127.0.0.1. Isto barra: só aceita pedidos da própria página do programa.
HOSTS_OK = {"127.0.0.1", "localhost"}


@app.middleware("http")
async def so_local(request: Request, call_next):
    host = (request.headers.get("host") or "").split(":")[0]
    if host not in HOSTS_OK:
        return JSONResponse({"detail": "host não permitido"}, status_code=403)
    if request.method not in ("GET", "HEAD"):
        origem = request.headers.get("origin")
        if origem and origem.split("://", 1)[-1].split(":")[0] not in HOSTS_OK:
            return JSONResponse({"detail": "origem não permitida"}, status_code=403)
        if "application/json" not in (request.headers.get("content-type") or ""):
            return JSONResponse({"detail": "use JSON"}, status_code=415)
    return await call_next(request)


# ------------------------------------------------------------------ fila
# Um vídeo por vez: transcrição e IA local disputam a mesma placa de vídeo.
_fila: queue.Queue = queue.Queue()
_projetos: dict[str, pipeline.Projeto] = {}


def _trabalhador() -> None:
    while True:
        tarefa = _fila.get()
        try:
            tarefa()
        except Exception as e:  # noqa: BLE001
            print("Erro numa tarefa:", e)
        finally:
            _fila.task_done()


threading.Thread(target=_trabalhador, daemon=True).start()


def _projeto(pid: str) -> pipeline.Projeto:
    if pid not in _projetos:
        pasta = (config.PASTA_PROJETOS / pid).resolve()
        if pasta.parent != config.PASTA_PROJETOS.resolve() or not (pasta / "projeto.json").exists():
            raise HTTPException(404, "projeto não encontrado")
        _projetos[pid] = pipeline.Projeto(pasta)
    return _projetos[pid]


# ------------------------------------------------------------------ config e estado

def _mascarar(cfg: dict) -> dict:
    for p in cfg["ia"].values():
        ch = p.get("chave") or ""
        p["chave"] = ("•" * 8 + ch[-4:]) if ch else ""
    return cfg


@app.get("/api/estado")
def estado():
    cfg = config.carregar()
    return {
        "versao": __version__,
        "sistema": platform.system(),
        "pasta_dados": str(config.DADOS),
        "ffmpeg": bool(ferramentas.caminho_ffmpeg()),
        "nvenc": ferramentas.tem_nvenc() if ferramentas.caminho_ffmpeg() else False,
        "gpu": gpu.info(),
        "ollama": ollama_local.status(cfg["ia"]["ollama"]["url"]) | {"tarefa": _tarefa_ollama},
        "config": _mascarar(cfg),
        "na_fila": _fila.qsize(),
    }


@app.post("/api/config")
async def salvar_config(request: Request):
    novo = await request.json()
    atual = config.carregar()
    # Chave mascarada (•••) significa "não mexi": mantém a que estava salva.
    for nome, p in (novo.get("ia") or {}).items():
        if str(p.get("chave", "")).startswith("•"):
            p["chave"] = atual["ia"].get(nome, {}).get("chave", "")
    return _mascarar(config.salvar(config._mesclar(atual, novo)))


# ------------------------------------------------------------------ sua marca
# O logo chega em base64 dentro de JSON (o servidor só aceita JSON, ver so_local).
TIPOS_LOGO = {b"\x89PNG\r\n\x1a\n": ".png", b"\xff\xd8\xff": ".jpg", b"RIFF": ".webp"}
LOGO_MAX = 3 * 1024 * 1024


@app.post("/api/marca/logo")
async def enviar_logo(request: Request):
    import base64
    import binascii
    corpo = await request.json()
    dados = str(corpo.get("dados") or "")
    try:
        bruto = base64.b64decode(dados.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Arquivo inválido.") from None
    if len(bruto) > LOGO_MAX:
        raise HTTPException(400, "Logo grande demais (máximo 3 MB).")
    ext = next((e for m, e in TIPOS_LOGO.items() if bruto.startswith(m)), None)
    if ext == ".webp" and bruto[8:12] != b"WEBP":
        ext = None
    if not ext:
        raise HTTPException(400, "Use PNG (de preferência com fundo transparente), JPG ou WEBP.")
    config.PASTA_MARCA.mkdir(parents=True, exist_ok=True)
    for velho in config.PASTA_MARCA.glob("logo.*"):
        velho.unlink(missing_ok=True)
    (config.PASTA_MARCA / f"logo{ext}").write_bytes(bruto)
    config.salvar(config._mesclar(config.carregar(), {"marca": {"logo": f"logo{ext}"}}))
    return {"logo": f"logo{ext}"}


@app.delete("/api/marca/logo")
def apagar_logo():
    for velho in config.PASTA_MARCA.glob("logo.*"):
        velho.unlink(missing_ok=True)
    config.salvar(config._mesclar(config.carregar(), {"marca": {"logo": ""}}))
    return {"ok": True}


@app.get("/api/marca/logo")
def ver_logo():
    nome = config.carregar()["marca"].get("logo") or ""
    alvo = (config.PASTA_MARCA / nome).resolve()
    if not nome or alvo.parent != config.PASTA_MARCA.resolve() or not alvo.is_file():
        raise HTTPException(404)
    return FileResponse(alvo, headers={"Cache-Control": "no-store"})


@app.get("/api/marca/previa")
def previa_marca():
    """Um quadro de clipe já cortado, pra servir de fundo no editor da marca."""
    for p in pipeline.listar_projetos():
        try:
            d = _projeto(p["id"]).dados
        except HTTPException:
            continue
        for cl in d.get("clipes", []):
            if (config.PASTA_PROJETOS / p["id"] / "clipes" / cl.get("capa", "")).is_file():
                return {"url": f"/arquivos/{p['id']}/{cl['capa']}"}
    return {"url": None}


@app.post("/api/testar-ia/{nome}")
def testar_ia(nome: str):
    cfg = config.carregar()
    if nome not in cfg["ia"]:
        raise HTTPException(404)
    if nome == "ollama" and not ollama_local.rodando(cfg["ia"]["ollama"]["url"]):
        return {"ok": False, "erro": "A IA local está desligada. Instale e ligue ali embaixo."}
    p = cliente.Provedor(nome, cfg["ia"][nome])
    try:
        p.preparar(lambda _m: None)
        r = p.conversar("Responda só com JSON.", 'Responda {"ok": true}')
        cliente.extrair_json(r)
        return {"ok": True, "modelo": p.modelo}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erro": str(e)[:400]}


# ------------------------------------------------------------------ IA local

_tarefa_ollama: dict = {"rodando": False, "mensagem": "", "progresso": 0.0, "erro": ""}


@app.post("/api/ollama/instalar")
async def ollama_instalar(request: Request):
    corpo = await request.json()
    cfg = config.carregar()
    modelo = (corpo.get("modelo") or cfg["ia"]["ollama"]["modelo"]).strip()
    if _tarefa_ollama["rodando"]:
        raise HTTPException(409, "já tem uma instalação em andamento")
    cfg["ia"]["ollama"]["modelo"] = modelo
    config.salvar(cfg)
    url = cfg["ia"]["ollama"]["url"]

    def prog(frac: float, msg: str) -> None:
        _tarefa_ollama.update(progresso=frac, mensagem=msg)

    def tarefa() -> None:
        _tarefa_ollama.update(rodando=True, erro="", mensagem="Começando...", progresso=0.0)
        try:
            # Se já tem um Ollama respondendo no endereço (ex.: o oficial),
            # não instala outro: só baixa o modelo nele.
            if not ollama_local.rodando(url):
                ollama_local.instalar(prog)
                prog(0, "Ligando a IA local...")
                ollama_local.iniciar(url)
            ollama_local.baixar_modelo(modelo, prog, url)
            if cfg["visao"].get("ativo"):
                ollama_local.baixar_modelo(cfg["visao"]["modelo_local"], prog, url)
            prog(1, f"Pronto: {modelo} instalado e ligado.")
        except Exception as e:  # noqa: BLE001
            _tarefa_ollama["erro"] = str(e)
            print("\n[IA local] Erro ao instalar:", flush=True)
            traceback.print_exc()
        finally:
            _tarefa_ollama["rodando"] = False

    threading.Thread(target=tarefa, daemon=True).start()
    return {"ok": True}


@app.post("/api/ollama/{acao}")
def ollama_acao(acao: str):
    url = config.carregar()["ia"]["ollama"]["url"]
    if acao == "ligar":
        ollama_local.iniciar(url)
    elif acao == "desligar":
        ollama_local.parar()
    elif acao == "desinstalar":
        ollama_local.desinstalar()
    else:
        raise HTTPException(404)
    return ollama_local.status(url)


# ------------------------------------------------------------------ projetos

@app.get("/api/projetos")
def projetos():
    return pipeline.listar_projetos()


@app.post("/api/projetos")
async def criar(request: Request):
    corpo = await request.json()
    entrada = (corpo.get("entrada") or "").strip()
    if not entrada:
        raise HTTPException(400, "cole um link ou o caminho de um arquivo")
    p = pipeline.novo_projeto(entrada, corpo.get("opcoes") or {})
    _projetos[p.id] = p
    _fila.put(lambda: pipeline.rodar(p))
    return {"id": p.id}


@app.get("/api/projetos/{pid}")
def ver(pid: str):
    return _projeto(pid).dados


@app.get("/api/projetos/{pid}/linha")
def linha_do_tempo(pid: str, barras: int = 120):
    """Volume do vídeo resumido em N barras (0 a 1), pra linha do tempo."""
    p = _projeto(pid)
    if not (p.pasta / "energia.json").exists():
        return {"inicio": 0, "fim": 0, "barras": []}
    e = p.ler("energia.json")
    db, ini = e.get("db") or [], float(e.get("deslocamento") or 0)
    if not db:
        return {"inicio": ini, "fim": ini, "barras": []}
    n = max(10, min(int(barras), 400, len(db)))
    passo = len(db) / n
    picos = [max(db[int(i * passo):max(int((i + 1) * passo), int(i * passo) + 1)]) for i in range(n)]
    base, topo = sorted(picos)[len(picos) // 10], max(picos)  # ignora o silêncio total
    esc = (topo - base) or 1.0
    return {"inicio": ini, "fim": ini + len(db),
            "barras": [round(max(0.0, min(1.0, (v - base) / esc)), 3) for v in picos]}


@app.post("/api/projetos/{pid}/retomar")
def retomar(pid: str):
    p = _projeto(pid)
    if p.dados.get("estado") in ("rodando", "na fila"):
        raise HTTPException(409, "esse projeto já está rodando")
    p.dados["estado"] = "na fila"
    p.salvar()
    _fila.put(lambda: pipeline.rodar(p))
    return {"ok": True}


@app.post("/api/projetos/{pid}/cortar")
async def cortar(pid: str, request: Request):
    """Corta (ou refaz) clipes. Aceita ajustes de tempo, título e gancho."""
    p = _projeto(pid)
    corpo = await request.json()
    ajustes = corpo.get("ajustes") or {}
    por_id = {c["id"]: c for c in p.dados.get("candidatos", [])}
    ids = []
    for cid in corpo.get("ids", []):
        c = por_id.get(int(cid))
        if not c:
            continue
        aj = ajustes.get(str(cid)) or {}
        for campo in ("titulo", "gancho"):
            if campo in aj:
                c[campo] = str(aj[campo])[:80]
        for campo in ("inicio", "fim"):
            if aj.get(campo) not in (None, ""):
                c[campo] = pipeline.analise.para_segundos(aj[campo])
        ids.append(c["id"])
    if not ids:
        raise HTTPException(400, "nenhum clipe escolhido")
    p.dados["estado"] = "na fila"
    p.salvar()

    def tarefa() -> None:
        p.dados["estado"] = "rodando"
        try:
            pipeline.cortar(p, ids)
            p.dados["estado"] = "pronto"
            p.log("Clipes refeitos")
        except Exception as e:  # noqa: BLE001
            p.dados["estado"] = "erro"
            p.dados["erro"] = str(e)
            p.log(f"Erro: {e}")
        finally:
            p.salvar()

    _fila.put(tarefa)
    return {"ok": True}


@app.delete("/api/projetos/{pid}/clipes/{cid}")
def apagar_clipe(pid: str, cid: int):
    pipeline.remover_clipe(_projeto(pid), cid)
    return {"ok": True}


@app.post("/api/projetos/{pid}/abrir-pasta")
def abrir_pasta(pid: str):
    pasta = _projeto(pid).pasta / "clipes"
    pasta = pasta if pasta.exists() else pasta.parent
    if os.name == "nt":
        os.startfile(pasta)  # noqa: S606 - abre o Explorer na pasta do projeto
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(pasta)])
    else:
        subprocess.Popen(["xdg-open", str(pasta)])
    return {"ok": True}


@app.get("/arquivos/{pid}/{nome}")
def arquivo(pid: str, nome: str):
    pasta = (_projeto(pid).pasta / "clipes").resolve()
    alvo = (pasta / nome).resolve()
    if alvo.parent != pasta or not alvo.exists():
        raise HTTPException(404)
    return FileResponse(alvo)


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")

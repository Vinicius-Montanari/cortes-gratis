# ✂ Cortes Grátis

**Cola o link de uma live gravada e recebe os melhores momentos já cortados em 9:16, com legenda palavra por palavra, gancho e texto pro post.**

> **Projeto de estudo de LLMs locais.** A pergunta era: dá pra um modelo pequeno, rodando numa placa de vídeo comum (RTX 2060/3080), fazer um trabalho de "editor de cortes" sem depender de API paga? Este repositório é o resultado e o que aprendi no caminho ([seção 5](#5-o-que-aprendi-com-as-llms-locais)). Funciona de verdade, mas não é produto: é laboratório.

Windows (testado) · Linux e Mac pelo terminal · Licença MIT

---

## 1. O que ele faz

- Aceita link (Twitch, YouTube, Kick e tudo que o [yt-dlp](https://github.com/yt-dlp/yt-dlp) abre) ou arquivo do PC.
- Entrega até 8 clipes `.mp4` 1080x1920 de 20 a 60 s, com:
  - legenda queimada, palavra falada em amarelo;
  - gancho no topo escrito pela IA;
  - `.txt` com título, legenda do post, hashtags, crédito e link do trecho original.
- Mostra os trechos que a IA **descartou**, com nota e motivo, pra cortar mesmo assim se você discordar.
- Três layouts (`desfocado`, `quadrado`, `centro`), sua **marca** (logo e @ arrastáveis na tela, com aviso de onde os botões do TikTok/Reels/Shorts cobrem) e tema claro/escuro.

## 2. Como funciona

```
link ou arquivo
  │
  ├─ ① análise (PC)      baixa só o áudio → Whisper na GPU → volume por segundo
  ├─ ② candidatos (PC)   sem IA: picos de volume, palavras de reação, fala acelerada
  │                      → ~24 trechos ajustados pra começar e terminar em frase inteira
  ├─ ③ IA de texto       lê só a fala e dá nota 0–10, título e gancho   (local ou nuvem)
  ├─ ③b IA que enxerga   4 quadros por trecho: reprova menu, loja, loading (local ou nuvem)
  └─ ④ corte (PC)        ffmpeg lê só os pedaços aprovados e codifica na GPU (NVENC)
```

A IA **só filtra**. O trabalho pesado (achar onde tem grito, risada, explosão) é feito sem IA, por sinal de áudio e texto. Assim um modelo de 7B dá conta, e a nuvem gasta poucas perguntas.

Ordem das IAs: Groq → Gemini → local. As duas primeiras são opcionais (chave grátis, sem cartão); sem chave, tudo roda na sua placa.

## 3. Instalar

**Instalador (sem Python):** baixe o `CortesGratis-<versão>-instalador.exe` em **[Releases](https://github.com/Vinicius-Montanari/cortes-gratis/releases/latest)**. Se o Windows avisar "protegeu o computador", clique em **Mais informações → Executar assim mesmo** (o instalador é gerado pelo GitHub Actions a partir deste código). Não precisa de admin.

**Pelo código:** Python 3.10–3.13 **64 bits**, depois:

```powershell
git clone https://github.com/Vinicius-Montanari/cortes-gratis.git F:\cortes-gratis
```

Dois cliques em `instalar.bat` e depois em `iniciar.bat` (abre `http://127.0.0.1:8765`).

**Tudo fica na pasta do programa** (`dados\`): modelos, ffmpeg, IA local e clipes. Instale em outro disco e nada vai pro C:. Na primeira vez ele baixa o que falta:

| O quê | Tamanho |
|---|---|
| ffmpeg | ~0,5 GB |
| Whisper `large-v3-turbo` (ou `small` sem placa) | ~1,6 GB |
| CUDA 12 + cuDNN 9 (só com NVIDIA) | ~2 GB |
| IA local: Ollama + `qwen2.5:7b` + `qwen3-vl:4b` | ~10 GB |

## 4. IA local

Roda pelo [Ollama](https://ollama.com), em versão portátil instalada em `dados\ollama`, numa porta própria (11435) pra não brigar com um Ollama que você já tenha. Instala sozinha no primeiro corte, ou em **Configurações → IA local → Instalar e ligar** (se o botão falhar: menu Iniciar → **Instalar IA local**, que mostra cada passo).

| Papel | Modelo padrão | Disco | VRAM |
|---|---|---|---|
| Texto (dá a nota) | `qwen2.5:7b` | 4,7 GB | ~6 GB |
| Imagem (confere os quadros) | `qwen3-vl:4b-instruct` | 3,3 GB | ~5 GB |

Os dois nunca ficam na placa ao mesmo tempo (o programa descarrega um antes de carregar o outro), e o Whisper libera a placa antes deles. Por isso cabe numa RTX 2060.

**Chaves de nuvem (opcional):** [Groq](https://console.groq.com/keys) e [Gemini](https://aistudio.google.com/app/apikey), cole em **Configurações** e clique em **Testar**.

## 5. O que aprendi com as LLMs locais

Testado numa VOD da Kick (12 min de GTA RP), com `qwen2.5:7b` e `qwen3-vl:4b`:

- **Modelo pequeno é bonzinho demais.** Na primeira versão, de 6 clipes aprovados só 1 era bom. A IA dava 7–8 pra conversa comum.
- **Lista de verificação antes da nota funcionou mais que "seja exigente".** O prompt pede primeiro *o que acontece*, *se entende sozinho*, *se tem reação forte*, *se tem fecho* (sim/não), e só depois a nota. O código usa essas respostas pra limitar a nota (sem reação forte: no máximo 6). Pedir sim/não é muito mais confiável num 7B do que pedir uma nota calibrada.
- **Um trecho por pergunta.** Em lote, o 7B misturava os trechos e copiava o `id` do exemplo. Na nuvem (70B) dá pra mandar 4 de uma vez.
- **Filtrar antes da IA vale mais que um prompt melhor.** Descartar trechos com pouca fala (< 0,45 palavra/s) tirou os "1 minuto dirigindo calado" que o modelo aprovava.
- **Régua mais alta pra IA local:** nota mínima +1 quando quem julga é o modelo local (ajustável).
- **Visão resolve o que o texto não vê.** O modelo de texto chamou de "susto" uma cena na loja de armas ("oh meu deus" olhando preços). O `qwen3-vl:4b` reconheceu a loja e derrubou a nota de 8 pra 3. O `gemma3:4b` também viu a loja, mas concorda com qualquer título.
- **Modelo de visão copia o exemplo do prompt.** Pedir JSON com texto de exemplo fazia ele devolver o próprio exemplo. Solução: exemplo com `"..."` e detectar cópia.
- **Contexto:** a Qwen3-VL estourou o contexto padrão com 4 imagens; precisa de `num_ctx` 8192.

Resultado final na mesma VOD: **de 6 clipes (1 bom) pra 1 clipe (o bom)**. Perde em quantidade, mas o que sai pode ir pro ar.

## 6. Privacidade

| O quê | Pra onde |
|---|---|
| O link | Site do vídeo (yt-dlp) |
| Texto falado dos trechos | Groq ou Google, **só se** você pôs a chave |
| 4 quadros pequenos por trecho aprovado | Google, **só se** você pôs a chave do Gemini |
| Nada | Usando só a IA local |

Áudio e clipes nunca vão pra IA. A interface roda só em `127.0.0.1` e recusa pedidos de outros sites. No plano grátis do Gemini o Google pode usar o que recebe; se não quiser, use Groq + local.

**Clipe dos outros:** prefira canais que liberam corte, dê crédito (o programa já põe o @ do streamer) e não poste de quem pede pra tirar.

## 7. Problemas comuns

| Problema | O que fazer |
|---|---|
| "O programa parou de responder" | A janela preta fechou. Se foi ao instalar a IA local, veja se o antivírus pôs `ollama.exe` em quarentena |
| Transcrição no processador mesmo com NVIDIA | Atualize o driver (CUDA 12). O chip no topo mostra se a placa foi achada |
| "Nenhuma IA respondeu" | Teste as chaves em Configurações, ou instale a IA local |
| yt-dlp não baixa | `.venv\Scripts\python -m pip install -U yt-dlp` |
| Nenhum clipe passou | Baixe a nota mínima ou use **Cortar assim mesmo** nos descartados |

O registro de cada corte fica em **Ver registro** e em `dados\projetos\<projeto>\projeto.json`.

## 8. Código

```
cortes_gratis/
├── analise.py       ① yt-dlp + faster-whisper + volume
├── candidatos.py    ② picos sem IA, ajuste pra frase inteira, filtro de pouca fala
├── ia/cliente.py    Groq, Gemini e Ollama no formato OpenAI; troca quando a cota acaba
├── ia/avaliar.py    ③ o prompt, a lista de verificação e a nota
├── ia/visao.py      ③b a IA que enxerga
├── corte.py         ④ legenda .ass, layouts, marca e o comando do ffmpeg
├── pipeline.py      junta as etapas, estado em projeto.json
├── ollama_local.py  instala/liga/desliga o Ollama portátil
├── servidor.py      API local (FastAPI)
└── web/             interface (HTML + JS puro, sem build)
empacotar/           PyInstaller + Inno Setup
```

```powershell
.venv\Scripts\python -m pytest
```

Pelo terminal, sem interface: `.venv\Scripts\python -m cortes_gratis "<link>" --idioma pt --inicio 1:00:00 --fim 2:00:00`.

**Instalador:** `powershell -ExecutionPolicy Bypass -File empacotar\construir.ps1` (precisa do [Inno Setup 6](https://jrsoftware.org/isinfo.php)). Pra publicar, suba `__version__` em `cortes_gratis\__init__.py` e crie a tag `vX.Y.Z`: o GitHub Actions testa, compila e põe na página de Releases.

Próximos experimentos: ler o chat da live como sinal, testar se a `qwen3-vl` sozinha dá conta também do texto (um modelo só), rastrear o rosto pro layout `centro`.

## Créditos

A ideia de transcrever, medir volume e deixar uma IA escolher os momentos veio da skill [cortar-clipes](https://github.com/dgmidiamarketing-beep/cortar-clipes), de [@danielmourao.ia](https://www.tiktok.com/@danielmourao.ia). Este é uma reescrita independente que roda sozinha.

Feito com [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org), [Ollama](https://ollama.com) e [FastAPI](https://fastapi.tiangolo.com). Licença [MIT](LICENSE).

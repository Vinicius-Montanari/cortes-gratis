# ✂ Cortes Grátis

**Cola o link da live gravada e recebe os melhores momentos já cortados em pé (9:16), com legenda palavra por palavra, título, gancho e texto pro post.**
Roda no seu computador, usa a sua placa de vídeo e uma IA gratuita só pra descartar o que não presta. Sem assinatura, sem cartão.

Windows (testado) · Linux e Mac (pelo terminal) · Licença MIT

---

## Sumário

1. [O que ele faz](#1-o-que-ele-faz)
2. [Como funciona por dentro](#2-como-funciona-por-dentro)
3. [O que precisa](#3-o-que-precisa)
4. [Instalar no Windows](#4-instalar-no-windows)
5. [Pegar as chaves grátis de IA](#5-pegar-as-chaves-grátis-de-ia)
6. [IA local (quando a grátis acabar)](#6-ia-local-quando-a-grátis-acabar)
7. [Usar](#7-usar)
8. [Quanto tempo leva](#8-quanto-tempo-leva)
9. [Privacidade: o que sai do seu PC](#9-privacidade-o-que-sai-do-seu-pc)
10. [Antes de postar clipe dos outros](#10-antes-de-postar-clipe-dos-outros)
11. [Problemas comuns](#11-problemas-comuns)
12. [Pelo terminal (sem interface)](#12-pelo-terminal-sem-interface)
13. [Para quem quer mexer no código](#13-para-quem-quer-mexer-no-código)

---

## 1. O que ele faz

| Você entrega | Você recebe |
|---|---|
| Link de uma live gravada (Twitch, YouTube, Kick e tudo que o [yt-dlp](https://github.com/yt-dlp/yt-dlp) abre) **ou** um arquivo de vídeo do seu PC | Até 8 clipes `.mp4` de 1080x1920, de 20 a 60 s, com áudio nivelado pra rede social |
| | Legenda queimada no vídeo, palavra por palavra, com a palavra falada em amarelo |
| | Um **gancho** no topo (ex.: `ELE NÃO VIU O URSO`), escrito pela IA |
| | Um `.txt` por clipe com título, legenda do post, hashtags, crédito e o link do trecho original |
| | A lista dos trechos que a IA **descartou**, com a nota e o motivo, pra você cortar mesmo assim se discordar |

Três layouts:

| `desfocado` (padrão) | `quadrado` | `centro` |
|---|---|---|
| Vídeo inteiro no meio, fundo borrado | Recorte quadrado: jogo maior | Tela cheia, corta as laterais |
| Serve pra tudo | Gameplay sem câmera no canto | Quando a ação ou a pessoa está no meio |

---

## 2. Como funciona por dentro

```
 link ou arquivo
        │
        ▼
 ① ANÁLISE  (no seu PC)
    baixa só o áudio → transcreve com Whisper na placa de vídeo → mede o volume de cada segundo
        │
        ▼
 ② CANDIDATOS  (no seu PC, sem IA)
    dá nota pra cada segundo: volume subindo de repente, palavras de reação
    ("não acredito", "caralho", "kkkk", "no way"), fala acelerada
    → pega os ~24 picos e estica cada um até começar e terminar em frase inteira
        │
        ▼
 ③ FILTRO DA IA  (Groq → Gemini → IA local)
    a IA lê só o TEXTO de cada trecho e dá nota de 0 a 10,
    ajusta onde começa e termina, escreve título, gancho e hashtags
    → descarta o que ficar abaixo da nota mínima (padrão 6)
        │
        ▼
 ③b CONFERE A IMAGEM  (Gemini → IA local que enxerga)
    4 quadros de cada trecho aprovado vão pra uma IA de visão:
    menu, loja, mapa e tela de carregamento são reprovados;
    nos outros, a nota da imagem entra na nota final
        │
        ▼
 ④ CORTE  (no seu PC)
    o ffmpeg lê direto do servidor só os pedaços aprovados (não baixa a live inteira),
    monta em 9:16 com legenda e codifica na placa de vídeo (NVENC)
```

**Por que a IA só filtra e não "assiste" a live?** Mandar vídeo pra IA gasta a cota grátis em minutos. Mandar só o texto de 24 trechos gasta umas 6 perguntas. Assim dá pra cortar várias lives por dia sem pagar nada. O trabalho pesado (achar onde tem grito, risada, explosão) é feito por conta própria no seu PC.

**Por que três IAs?** As grátis têm limite por dia. Quando o Groq acaba, o programa passa sozinho pro Gemini. Quando o Gemini acaba, liga a IA local na sua placa de vídeo, que não tem limite nenhum.

---

## 3. O que precisa

| | Mínimo | Recomendado |
|---|---|---|
| Sistema | Windows 10/11 64 bits | |
| Python | nenhum, se usar o instalador. Pelo código: 3.10 a 3.13, **64 bits** | 3.12 |
| Placa de vídeo | nenhuma (vai pelo processador, bem mais lento) | NVIDIA com 6 GB+ (ex.: RTX 2060 12 GB, 3060, 3080) |
| Disco | ~2,5 GB sem placa de vídeo | ~4,5 GB com placa NVIDIA, +6,5 GB se usar a IA local |
| Internet | pra baixar a live e falar com a IA | |

**Tudo fica dentro da pasta do programa.** Se você instalar em `F:\Cortes Gratis`, os modelos, o ffmpeg, a IA local e os clipes vão todos pra `F:\Cortes Gratis\dados`. Nada enche o seu C:.

---

## 4. Instalar no Windows

### Jeito fácil: instalador (não precisa de Python)

1. Vá em **[Releases](https://github.com/Vinicius-Montanari/cortes-gratis/releases/latest)** e baixe o `CortesGratis-<versão>-instalador.exe` (~75 MB).
2. Abra. Se aparecer **"O Windows protegeu o computador"**, clique em **Mais informações → Executar assim mesmo**. Esse aviso aparece em todo programa sem certificado digital pago; o instalador é gerado automaticamente pelo GitHub a partir deste código (veja a aba Actions).
3. **Escolha a pasta.** Não precisa de admin. Pode ser outro disco, ex.: `F:\Cortes Gratis`. Tudo que o programa baixar depois fica dentro dela.
4. Abra pelo atalho **Cortes Grátis**. A janela preta é o programa rodando; o navegador abre sozinho. Fechou a janela, desligou.

Na primeira vez que você cortar algo, ele baixa sozinho o que falta:

| O quê | Tamanho | Quando |
|---|---|---|
| ffmpeg | ~0,5 GB | sempre |
| Modelo de transcrição | ~1,6 GB (`large-v3-turbo`) ou ~0,5 GB (`small`, sem placa) | sempre |
| Bibliotecas da NVIDIA (CUDA 12 + cuDNN 9, do PyPI oficial) | ~2 GB | só se tiver placa NVIDIA |
| IA local (Ollama + modelo) | ~6,5 GB | só se usar a IA local |

**Desinstalar:** pelo **Configurações do Windows → Aplicativos**, ou **Iniciar → Desinstalar o Cortes Grátis**. Ele pergunta se apaga também os clipes e os modelos baixados.

### Pelo código (pra quem já tem Python ou quer mexer)

1. **Python.** Se ainda não tiver, abra o PowerShell e rode:
   ```powershell
   winget install Python.Python.3.12
   ```
   (ou baixe em [python.org](https://www.python.org/downloads/) e marque **Add python.exe to PATH**).
2. **Baixe este programa.** Botão verde **Code → Download ZIP** aqui no GitHub e descompacte onde quiser (ex.: `F:\cortes-gratis`). Ou, se tiver Git:
   ```powershell
   git clone https://github.com/Vinicius-Montanari/cortes-gratis.git F:\cortes-gratis
   ```
3. **Dê dois cliques no `instalar.bat`.** Ele:
   - acha um Python compatível;
   - cria um ambiente isolado em `.venv` (não mexe no seu Python);
   - instala as bibliotecas e, se tiver placa NVIDIA, o suporte a GPU (~1 GB);
   - baixa o ffmpeg pra `dados\ferramentas`.
4. **Dê dois cliques no `iniciar.bat`.** Abre o navegador em `http://127.0.0.1:8765`. Pra desligar, feche a janela preta.

---

## 5. Pegar as chaves grátis de IA

Não precisa de cartão em nenhuma das duas. Uma já basta; as duas juntas rendem mais cortes por dia.

### Groq (recomendado, o mais rápido)
1. Entre em [console.groq.com/keys](https://console.groq.com/keys) e faça login (Google ou e-mail).
2. Clique em **Create API Key**, dê um nome qualquer e copie a chave (começa com `gsk_`).
3. No programa: **Configurações → Groq → Chave**, cole e clique em **Testar**.

### Google Gemini
1. Entre em [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) com sua conta Google.
2. **Create API key** → copie.
3. No programa: **Configurações → Google Gemini → Chave**, cole e clique em **Testar**.
   O campo **Modelo** pode ficar vazio: o programa escolhe sozinho o Gemini Flash mais novo que a sua conta tiver.

> **Atenção:** no plano grátis do Gemini, o Google pode usar o que você manda pra melhorar os produtos dele. Aqui isso é só o texto falado nos trechos da live. Se não quiser, desmarque o Gemini e use Groq + IA local.

As chaves ficam salvas só no seu PC, em `dados\config.json`. Esse arquivo não vai pro Git.

---

## 6. IA local (quando a grátis acabar)

É uma IA que roda inteira na sua placa de vídeo, pelo [Ollama](https://ollama.com). Sem limite, sem internet, sem mandar nada pra ninguém. É mais lenta e um pouco menos exigente que as da nuvem, por isso fica por último.

**Instalar:** **Configurações → IA local → escolha o modelo → Instalar e ligar.** O programa:
1. baixa a versão portátil do Ollama do GitHub oficial (sem instalador, sem pedir admin) pra `dados\ollama`;
2. liga numa porta própria (11435), que não briga com um Ollama que você já tenha;
3. baixa o modelo escolhido pra `dados\ollama\modelos`.

Se você não instalar, ele se instala sozinho na primeira vez que precisar.

**O botão deu erro?** Tem mais dois jeitos:

1. **Pela janela de comando**, que mostra cada passo e qualquer erro: menu Iniciar → **Instalar IA local**. Ou, na pasta do programa:
   ```powershell
   & ".\Cortes Gratis.exe" --instalar-ia-local
   ```
   (pelo código: `.venv\Scripts\python -m cortes_gratis --instalar-ia-local`). Dá pra escolher o modelo: `--instalar-ia-local gemma3:4b`.
2. **Usando o Ollama oficial**: instale por [ollama.com/download](https://ollama.com/download), rode `ollama pull qwen2.5:7b` e, em **Configurações → IA local → Outras formas de instalar**, troque o endereço pra `http://127.0.0.1:11434/v1`. Atenção: aí os modelos ficam onde o Ollama oficial guarda (no C:), a não ser que você crie a variável de ambiente `OLLAMA_MODELS` apontando pra outro disco.

| Modelo | Tamanho | Pra quem |
|---|---|---|
| `qwen2.5:7b` (padrão) | 4,7 GB | Placa de 8 GB+. Bom em português e em responder no formato certo |
| `llama3.1:8b` | 4,9 GB | Alternativa |
| `gemma3:4b` | 3,3 GB | Placa de 6 GB |
| `qwen2.5:3b` | 1,9 GB | Placa fraca; julga pior |

Dá pra digitar qualquer outro modelo da [biblioteca do Ollama](https://ollama.com/library) no campo **Modelo**.

### IA local que enxerga (conferência da imagem)

A IA de texto só lê a fala, então se engana: num teste com uma VOD de GTA, ela deu nota 8 e chamou de "susto" uma cena em que o personagem estava no menu da loja de armas. Com **Configurações → Conferir a imagem** ligado (vem ligado), 4 quadros de cada trecho aprovado vão pra uma IA de visão, que reprova menu, loja, mapa e tela de carregamento.

| Modelo | Disco | VRAM | Por trecho | No teste |
|---|---|---|---|---|
| `qwen3-vl:4b-instruct` (padrão) | 3,3 GB | ~5 GB | ~3 s | Reconheceu a loja e reprovou; descreveu bem as outras cenas |
| `qwen3-vl:2b-instruct` | menor | placa de 4 a 6 GB | — | Não testado |
| `gemma3:4b` | 3,4 GB | ~4,7 GB | ~3 s | Reconheceu a loja, mas concorda com qualquer título |

Ele é baixado sozinho na primeira vez. Antes de carregar o modelo de imagem, o programa tira o de texto da placa, então os dois não precisam caber juntos. Com chave do Gemini, a conferência vai pra ele primeiro (melhor e mais rápido) e a local fica de reserva.

A transcrição e a IA local não rodam ao mesmo tempo: o programa libera a placa depois de transcrever. Por isso uma RTX 2060 de 12 GB dá conta das duas coisas com folga.

**Desinstalar:** botão **Desinstalar** na mesma tela, ou apague a pasta `dados\ollama`.

---

## 7. Usar

1. Na aba **Cortar**, cole o link da live gravada ou o caminho do arquivo (ex.: `F:\Videos\live.mp4`).
2. Escolha o idioma (deixar certo acelera e evita erro quando a live começa com música).
3. **Live longa?** Preencha **Só a partir de / até** com a parte que interessa (ex.: `1:00:00` até `2:30:00`). Fica bem mais rápido.
4. Escolha o layout e clique em **Cortar os melhores momentos**.
5. Acompanhe a barra. No fim, cada clipe aparece com player, nota e motivo:
   - **Baixar** e **Texto do post** pegam o `.mp4` e o `.txt`;
   - **Ajustar e refazer** muda início, fim, título ou gancho e monta de novo só aquele;
   - em **Descartados pela IA**, **Cortar mesmo assim** monta um trecho que a IA reprovou.
6. **Abrir pasta** mostra os arquivos no Explorer. Cada vídeo vira uma pasta em `dados\projetos`.

Live **ao vivo** não dá: espere acabar e use o link da gravação (VOD).

Se der erro no meio (internet caiu, cota acabou), clique em **Tentar de novo**: o que já foi feito (transcrição, notas) não é refeito.

---

## 8. Quanto tempo leva

Medido em 24/11/2026 num PC com RTX 3080 10 GB, transcrição com `large-v3-turbo`:

| Etapa | Medido | O que isso dá numa live de 3 h (estimativa) |
|---|---|---|
| Baixar o áudio + transcrever | 3 min de fala em ~6 s; 2 min por link em ~7 s | uns 6 a 10 min |
| IA filtrando, IA local `qwen2.5:7b` | ~4 s por trecho | 24 trechos: ~2 min (Groq: segundos) |
| Corte com NVENC, arquivo do PC | ~7 s por clipe de 40 s | 8 clipes: ~1 min |
| Corte com NVENC, por link | ~14 s por clipe de 25 s | 8 clipes: ~2 min |

A primeira vez demora mais: baixa o modelo de transcrição (~1,6 GB) e, se usar, a IA local (~1,6 GB do Ollama + 4,7 GB do modelo).

**Numa RTX 2060** a transcrição e a IA local devem levar mais ou menos o dobro. **Sem placa de vídeo**, a transcrição leva de 15% a 35% da duração do vídeo (uma live de 3 h: 30 min a 1 h). Pra acelerar, use **Só a partir de / até** ou o modelo `base` nas Configurações.

---

## 9. Privacidade: o que sai do seu PC

| O quê | Pra onde | Quando |
|---|---|---|
| O link que você colou | Site do vídeo (via yt-dlp) | Pra baixar o áudio e os trechos |
| **Texto falado** dos trechos candidatos + título e canal do vídeo | Groq ou Google, se você colocou a chave | Na etapa de filtro |
| **4 quadros (imagens pequenas) de cada trecho aprovado** | Google, se você colocou a chave do Gemini e a conferência da imagem está ligada | Na conferência da imagem |
| Nada | — | Se usar só a IA local |

O áudio e os clipes prontos nunca são enviados pra IA nenhuma. Se não quiser mandar imagens pro Google, deixe a chave do Gemini vazia: a conferência é feita pela IA local. O programa não posta nada em rede social: quem decide o que vai pro ar é você.

A interface roda só em `127.0.0.1` (o próprio PC) e recusa pedidos vindos de outros sites.

---

## 10. Antes de postar clipe dos outros

- **Prefira quem libera ou paga clipe.** Muito streamer tem programa ou campanha de clipes.
- **Dê crédito sempre.** O programa já põe o @ do canal no vídeo e no texto do post.
- **Fique longe de canal que derruba corte.** Se o canal já pediu pra tirar clipes do ar, não poste: é strike.
- **Sua própria live é sempre liberada.**

---

## 11. Problemas comuns

| Problema | O que fazer |
|---|---|
| "O programa parou de responder" (ou "Failed to fetch") | A janela preta fechou. Se fechou sozinha ao instalar a IA local, provavelmente foi o antivírus: veja se ele pôs `Cortes Gratis.exe` ou `ollama.exe` em quarentena e libere. Pra ver o erro exato, use o atalho **Instalar IA local** |
| A janela do programa abre e fecha na hora | Abra pelo atalho de novo; se continuar, a janela agora espera você ler o erro. Mande o print numa issue |
| Primeira vez parada em "Suporte à placa de vídeo" | É o download de ~2 GB das bibliotecas da NVIDIA, uma vez só. Se cair a internet, ele tenta de novo no próximo corte e, enquanto isso, transcreve pelo processador |
| `instalar.bat` diz que não achou Python 64 bits | Rode `winget install Python.Python.3.12` e tente de novo. Python 3.14 ainda não serve (falta a biblioteca de transcrição) |
| A transcrição está no processador mesmo com placa NVIDIA | Atualize o driver da NVIDIA (precisa suportar CUDA 12). Rode o `instalar.bat` de novo. O chip no topo da tela mostra se a placa foi encontrada |
| "Nenhuma IA respondeu" | Confira as chaves em Configurações → Testar. Se a cota do dia acabou, instale a IA local |
| A IA local está muito lenta | Escolha um modelo menor (`gemma3:4b`) ou confira se a placa não está ocupada com outro programa |
| O yt-dlp não baixa o link | O site pode ter mudado. Atualize: `.venv\Scripts\python -m pip install -U yt-dlp` |
| Legenda com palavras erradas | Configurações → Transcrição → `large-v3-turbo` e o idioma certo na hora de cortar |
| Nenhum clipe passou da nota mínima | Baixe a nota mínima (ex.: 5) ou use **Cortar mesmo assim** nos descartados |

O registro completo de cada corte fica em **Ver registro**, na tela do projeto, e em `dados\projetos\<projeto>\projeto.json`.

---

## 12. Pelo terminal (sem interface)

```powershell
.venv\Scripts\python -m cortes_gratis "https://www.twitch.tv/videos/123" --idioma pt --inicio 1:00:00 --fim 2:00:00 --layout quadrado
```

| Opção | O que faz |
|---|---|
| `--idioma pt` | Idioma da fala (`pt`, `en`, `es`...) |
| `--inicio`, `--fim` | Analisa só esse pedaço |
| `--layout` | `desfocado`, `quadrado` ou `centro` |
| `--nota-minima 5` | Nota mínima pra virar clipe |
| `--porta 9000` | Porta da interface (quando roda sem link) |

As chaves e o resto vêm de `dados\config.json` (o mesmo da interface).

---

## 13. Para quem quer mexer no código

```
cortes_gratis/
├── analise.py        ① baixa o áudio (yt-dlp), transcreve (faster-whisper), mede volume
├── candidatos.py     ② acha os picos sem IA e ajusta pra frase inteira
├── ia/
│   ├── cliente.py    conversa com Groq, Gemini e Ollama (formato OpenAI) e troca quando a cota acaba
│   ├── avaliar.py    ③ o pedido que a IA recebe e como a resposta vira nota/corte
│   └── visao.py      ③b a IA que enxerga confere 4 quadros de cada trecho
├── corte.py          ④ legenda .ass, layouts e o comando do ffmpeg
├── pipeline.py       junta as etapas e guarda o estado em projeto.json
├── ollama_local.py   instala, liga e desliga a IA local
├── ferramentas.py    acha/baixa o ffmpeg, detecta NVENC
├── gpu.py            prepara as bibliotecas CUDA no Windows
├── cuda.py           baixa as DLLs da NVIDIA do PyPI (versão instalada, sem pip)
├── config.py         caminhos (tudo em dados/) e configuração padrão
├── servidor.py       API local (FastAPI) da interface
└── web/              a interface (HTML + JS puro, sem build)
empacotar/            receita do .exe (PyInstaller) e do instalador (Inno Setup)
tests/                testes (pytest)
```

Rodar os testes:

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

### Gerar o instalador

Precisa de Python 3.12 e [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`):

```powershell
powershell -ExecutionPolicy Bypass -File empacotar\construir.ps1
```

Sai em `dist\CortesGratis-<versão>-instalador.exe`. O PyInstaller junta o Python e as bibliotecas (`empacotar\cortes-gratis.spec`), e o Inno Setup transforma isso num instalador (`empacotar\instalador.iss`). As bibliotecas da NVIDIA ficam de fora de propósito: o programa baixa só se precisar (`cortes_gratis\cuda.py`).

**Publicar uma versão:** mude `__version__` em `cortes_gratis\__init__.py`, faça o commit e crie a tag com o mesmo número:

```powershell
git tag v0.2.0
```

```powershell
git push origin v0.2.0
```

O GitHub Actions (`.github\workflows\instalador.yml`) roda os testes, compila e põe o instalador na página de Releases sozinho.

Ideias que cabem bem: ler o chat da live (picos de mensagens são ótimos sinais), rastrear o rosto pro layout `centro`, testar se a `qwen3-vl` sozinha dá conta também do texto (um modelo só em vez de dois).

---

## Créditos

A ideia de transcrever, medir o volume e deixar uma IA escolher os momentos veio da skill [cortar-clipes](https://github.com/dgmidiamarketing-beep/cortar-clipes), de [@danielmourao.ia](https://www.tiktok.com/@danielmourao.ia), que faz isso dentro do Claude Code. Este programa é uma reescrita independente que roda sozinha, sem agente.

Feito com [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org), [Ollama](https://ollama.com) e [FastAPI](https://fastapi.tiangolo.com).

Licença [MIT](LICENSE): use, modifique e distribua à vontade.

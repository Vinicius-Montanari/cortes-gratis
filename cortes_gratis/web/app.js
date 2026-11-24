// Interface do Cortes Grátis. JavaScript puro, sem build.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

async function api(caminho, metodo = "GET", corpo) {
  const opc = { method: metodo, headers: {} };
  if (metodo !== "GET") {
    opc.headers["Content-Type"] = "application/json";
    opc.body = JSON.stringify(corpo || {});
  }
  let r;
  try {
    r = await fetch(caminho, opc);
  } catch {
    // "Failed to fetch": o navegador não achou o programa. Quase sempre a
    // janela preta fechou (ou o antivírus derrubou o programa).
    throw new Error(
      "O programa parou de responder.\n\n" +
      "A janela preta do Cortes Grátis ainda está aberta? Se ela fechou sozinha, " +
      "o antivírus pode ter bloqueado o programa. Abra de novo pelo atalho.\n\n" +
      "Pra instalar a IA local vendo cada passo e qualquer erro, use o atalho " +
      "\"Instalar IA local\" no menu Iniciar.");
  }
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}

function hms(s) {
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
  const p = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(ss)}` : `${m}:${p(ss)}`;
}

const NOMES_IA = { groq: "Groq", gemini: "Google Gemini", ollama: "IA local (Ollama)" };
const LINKS_CHAVE = {
  groq: ["https://console.groq.com/keys", "Pegar chave grátis no Groq"],
  gemini: ["https://aistudio.google.com/app/apikey", "Pegar chave grátis no Google AI Studio"],
};

let estado = null;
let projetoAtual = null;
let timerProjeto = null;

// ------------------------------------------------------------------ abas
$$("nav button").forEach((b) =>
  b.addEventListener("click", () => abrirAba(b.dataset.aba)));

function abrirAba(nome) {
  $$("nav button").forEach((b) => b.classList.toggle("ativa", b.dataset.aba === nome));
  $$(".aba").forEach((s) => s.classList.toggle("escondido", s.id !== `aba-${nome}`));
  if (nome === "projetos") carregarProjetos();
  if (nome === "config") carregarEstado().then(preencherConfig);
}

// ------------------------------------------------------------------ estado geral
async function carregarEstado() {
  estado = await api("/api/estado");
  $("#versao").textContent = "v" + estado.versao;
  const g = estado.gpu || {};
  const chips = [
    [g.cuda ? `Placa: ${g.nome || "NVIDIA"}` : "Sem placa NVIDIA (vai pelo processador)", g.cuda],
    [estado.ffmpeg ? (estado.nvenc ? "ffmpeg + NVENC" : "ffmpeg") : "ffmpeg: baixa no 1º uso", estado.ffmpeg],
    [estado.ollama.rodando ? "IA local ligada" : estado.ollama.instalado ? "IA local desligada" : "IA local não instalada", estado.ollama.rodando],
  ];
  $("#chips").innerHTML = chips.map(([t, ok]) => `<span class="chip ${ok ? "ok" : ""}">${t}</span>`).join("");

  const c = estado.config;
  const temNuvem = ["groq", "gemini"].some((n) => c.ia[n].ativo && c.ia[n].chave);
  const temLocal = c.ia.ollama.ativo && estado.ollama.instalado;
  const aviso = $("#aviso-ia");
  if (!temNuvem && !temLocal) {
    aviso.innerHTML = `Nenhuma IA configurada ainda. Vá em <a href="#" id="ir-config">Configurações</a> e cole uma chave grátis do Groq ou do Gemini, ou instale a IA local. Se não fizer nada, a IA local é instalada sozinha no primeiro corte.`;
    aviso.classList.remove("escondido");
    $("#ir-config").onclick = (e) => { e.preventDefault(); abrirAba("config"); };
  } else {
    aviso.classList.add("escondido");
  }
  atualizarOllama();
}

// ------------------------------------------------------------------ novo corte
$("#nota-minima").addEventListener("input", (e) => ($("#nota-valor").textContent = e.target.value));

$("#form-novo").addEventListener("submit", async (e) => {
  e.preventDefault();
  const botao = $("#form-novo button[type=submit]");
  botao.disabled = true;
  try {
    const opcoes = {
      idioma: $("#idioma").value,
      trecho_inicio: $("#trecho-inicio").value.trim(),
      trecho_fim: $("#trecho-fim").value.trim(),
      nota_minima: parseFloat($("#nota-minima").value),
      layout: $("input[name=layout]:checked").value,
      credito: $("#credito").value.trim(),
    };
    const { id } = await api("/api/projetos", "POST", { entrada: $("#entrada").value.trim(), opcoes });
    abrirProjeto(id);
  } catch (err) {
    alert(err.message);
  } finally {
    botao.disabled = false;
  }
});

// ------------------------------------------------------------------ projeto
function abrirProjeto(id) {
  projetoAtual = id;
  abrirAba("cortar");
  $("#projeto").classList.remove("escondido");
  $("#p-clipes").innerHTML = "";
  $("#p-descartados").innerHTML = "";
  clearTimeout(timerProjeto);
  atualizarProjeto();
  $("#projeto").scrollIntoView({ behavior: "smooth" });
}

let assinaturaClipes = "";
let rodandoAntes = false;

async function atualizarProjeto() {
  if (!projetoAtual) return;
  let d;
  try { d = await api(`/api/projetos/${projetoAtual}`); } catch { return; }
  $("#p-titulo").textContent = d.titulo || d.entrada;
  $("#p-barra").style.width = `${Math.round((d.progresso || 0) * 100)}%`;
  $("#p-msg").textContent = d.estado === "pronto" ? "Pronto. Assista cada clipe antes de postar." : d.mensagem || "";
  $("#p-log").textContent = (d.log || []).join("\n");
  const erro = $("#p-erro");
  erro.classList.toggle("escondido", d.estado !== "erro");
  erro.textContent = d.erro || "";
  $("#p-retomar").classList.toggle("escondido", d.estado !== "erro");

  // Só redesenha os clipes quando algo mudou, pra não parar o vídeo que está tocando.
  const assinatura = JSON.stringify([d.clipes, (d.candidatos || []).map((c) => [c.id, c.nota, c.escolhido, c.inicio, c.fim])]);
  if (assinatura !== assinaturaClipes) {
    assinaturaClipes = assinatura;
    desenharClipes(d);
  }
  if (d.estado === "rodando" || d.estado === "na fila") {
    timerProjeto = setTimeout(atualizarProjeto, 1500);
    rodandoAntes = true;
  } else if (rodandoAntes) {
    rodandoAntes = false;
    carregarEstado(); // a IA local pode ter sido ligada durante o corte
  }
}

function desenharClipes(d) {
  const cands = Object.fromEntries((d.candidatos || []).map((c) => [c.id, c]));
  const grade = $("#p-clipes");
  grade.innerHTML = "";
  for (const cl of d.clipes || []) {
    const c = cands[cl.id] || {};
    const el = $("#tpl-clipe").content.cloneNode(true);
    const base = `/arquivos/${projetoAtual}/`;
    const v = $("video", el);
    v.src = base + encodeURIComponent(cl.video) + `?v=${encodeURIComponent(c.inicio)}-${encodeURIComponent(c.fim)}`;
    v.poster = base + encodeURIComponent(cl.capa);
    $(".nota", el).textContent = `Nota ${c.nota ?? "?"} · ${hms(c.inicio)}–${hms(c.fim)} (${Math.round(c.fim - c.inicio)} s)`;
    $(".titulo", el).textContent = c.titulo || `Clipe ${cl.id}`;
    $(".motivo", el).textContent = c.motivo || "";
    $(".aj-titulo", el).value = c.titulo || "";
    $(".aj-gancho", el).value = c.gancho || "";
    $(".aj-inicio", el).value = hms(c.inicio);
    $(".aj-fim", el).value = hms(c.fim);
    $(".baixar", el).href = base + encodeURIComponent(cl.video);
    $(".txt", el).href = base + encodeURIComponent(cl.texto);
    const caixa = el.firstElementChild;
    $(".refazer", el).onclick = () => cortarClipes([cl.id], {
      [cl.id]: {
        titulo: $(".aj-titulo", caixa).value, gancho: $(".aj-gancho", caixa).value,
        inicio: $(".aj-inicio", caixa).value, fim: $(".aj-fim", caixa).value,
      },
    });
    $(".apagar", el).onclick = async () => {
      if (!confirm("Apagar este clipe? O arquivo some da pasta.")) return;
      await api(`/api/projetos/${projetoAtual}/clipes/${cl.id}`, "DELETE");
      atualizarProjeto();
    };
    grade.appendChild(el);
  }
  $("#p-clipes-titulo").classList.toggle("escondido", !(d.clipes || []).length);

  const feitos = new Set((d.clipes || []).map((c) => c.id));
  const desc = (d.candidatos || []).filter((c) => "nota" in c && !feitos.has(c.id))
    .sort((a, b) => b.nota - a.nota);
  $("#p-desc-titulo").classList.toggle("escondido", !desc.length);
  const lista = $("#p-descartados");
  lista.innerHTML = "";
  for (const c of desc) {
    const linha = document.createElement("div");
    linha.className = "descartado";
    linha.innerHTML = `<span class="nota"></span><span class="tempo"></span><span class="motivo"></span><button>Cortar mesmo assim</button>`;
    $(".nota", linha).textContent = c.nota;
    $(".tempo", linha).textContent = `${hms(c.inicio)}–${hms(c.fim)}`;
    $(".motivo", linha).textContent = `${c.titulo || ""} — ${c.motivo || ""}`;
    $("button", linha).onclick = () => cortarClipes([c.id]);
    lista.appendChild(linha);
  }
}

async function cortarClipes(ids, ajustes = {}) {
  try {
    await api(`/api/projetos/${projetoAtual}/cortar`, "POST", { ids, ajustes });
    clearTimeout(timerProjeto);
    atualizarProjeto();
  } catch (e) { alert(e.message); }
}

$("#p-pasta").onclick = () => api(`/api/projetos/${projetoAtual}/abrir-pasta`, "POST");
$("#p-retomar").onclick = async () => {
  await api(`/api/projetos/${projetoAtual}/retomar`, "POST");
  atualizarProjeto();
};

// ------------------------------------------------------------------ lista de projetos
async function carregarProjetos() {
  const lista = await api("/api/projetos");
  const box = $("#lista-projetos");
  box.innerHTML = lista.length ? "" : `<p class="dica">Nenhum projeto ainda.</p>`;
  for (const p of lista) {
    const el = document.createElement("div");
    el.className = "projeto-item";
    el.innerHTML = `<div><b></b><br><small></small></div><small></small>`;
    $("b", el).textContent = p.titulo;
    $$("small", el)[0].textContent = p.criado?.replace("T", " ") || "";
    $$("small", el)[1].textContent = `${p.clipes} clipes · ${p.estado}`;
    el.onclick = () => abrirProjeto(p.id);
    box.appendChild(el);
  }
}

// ------------------------------------------------------------------ configurações
function preencherConfig() {
  if (!estado) return;
  const c = estado.config;
  $("#pasta-dados").textContent = estado.pasta_dados;
  $("#whisper-modelo").value = c.whisper.modelo;
  $("#whisper-disp").value = c.whisper.dispositivo;
  $("#max-clipes").value = c.corte.max_clipes;
  $("#n-candidatos").value = c.corte.candidatos;
  $("#dur-min").value = c.corte.dur_min;
  $("#dur-max").value = c.corte.dur_max;
  $("#maiuscula").checked = c.corte.legenda_maiuscula;
  $("#mostrar-gancho").checked = c.corte.mostrar_gancho;
  $("#mostrar-credito").checked = c.corte.mostrar_credito;
  desenharIAs(c.ordem_ia.slice());
}

let ordemIA = [];
function desenharIAs(ordem) {
  ordemIA = ordem;
  const c = estado.config;
  const box = $("#lista-ias");
  box.innerHTML = "";
  ordem.forEach((nome, i) => {
    const p = c.ia[nome];
    const el = document.createElement("div");
    el.className = "ia";
    el.dataset.nome = nome;
    const link = LINKS_CHAVE[nome];
    el.innerHTML = `
      <div class="ia-topo">
        <label class="check"><input type="checkbox" class="ativo"> <b>${i + 1}. ${NOMES_IA[nome]}</b></label>
        ${link ? `<a href="${link[0]}" target="_blank" rel="noopener">${link[1]} ↗</a>` : ""}
        <span class="ordem"><button class="subir" title="Subir">↑</button><button class="descer" title="Descer">↓</button></span>
      </div>
      <div class="linha">
        ${nome !== "ollama" ? `<label>Chave <input class="chave" type="password" autocomplete="off" placeholder="cole a chave aqui"></label>` : ""}
        ${nome !== "ollama"
          ? `<label>Modelo <input class="modelo" placeholder="${nome === "gemini" ? "vazio = escolhe o Flash mais novo" : ""}"></label>`
          : `<p class="dica" style="flex:1">Modelo, instalação e liga/desliga ficam no quadro "IA local", logo abaixo.</p>`}
        <button class="testar">Testar</button>
      </div>
      <div class="resultado"></div>`;
    $(".ativo", el).checked = p.ativo;
    if ($(".chave", el)) $(".chave", el).value = p.chave;
    if ($(".modelo", el)) $(".modelo", el).value = p.modelo;
    $(".subir", el).disabled = i === 0;
    $(".descer", el).disabled = i === ordem.length - 1;
    $(".subir", el).onclick = () => { lerIAs(); trocar(i, i - 1); };
    $(".descer", el).onclick = () => { lerIAs(); trocar(i, i + 1); };
    $(".testar", el).onclick = async () => {
      const res = $(".resultado", el);
      res.textContent = "Salvando e testando...";
      await salvarConfig();
      const r = await api(`/api/testar-ia/${nome}`, "POST");
      res.innerHTML = r.ok ? `<span class="ok">Funcionando ✓ (${r.modelo})</span>` : "";
      if (!r.ok) res.textContent = "Não funcionou: " + r.erro;
    };
    box.appendChild(el);
  });
}

function trocar(a, b) {
  const o = ordemIA.slice();
  [o[a], o[b]] = [o[b], o[a]];
  desenharIAs(o);
}

function lerIAs() {
  for (const el of $$("#lista-ias .ia")) {
    const p = estado.config.ia[el.dataset.nome];
    p.ativo = $(".ativo", el).checked;
    if ($(".chave", el)) p.chave = $(".chave", el).value.trim();
    if ($(".modelo", el)) p.modelo = $(".modelo", el).value.trim();
  }
}

async function salvarConfig() {
  lerIAs();
  const c = estado.config;
  c.ordem_ia = ordemIA;
  c.ia.ollama.modelo = $("#ollama-modelo").value || c.ia.ollama.modelo;
  c.whisper.modelo = $("#whisper-modelo").value;
  c.whisper.dispositivo = $("#whisper-disp").value;
  Object.assign(c.corte, {
    max_clipes: +$("#max-clipes").value, candidatos: +$("#n-candidatos").value,
    dur_min: +$("#dur-min").value, dur_max: +$("#dur-max").value,
    legenda_maiuscula: $("#maiuscula").checked, mostrar_gancho: $("#mostrar-gancho").checked,
    mostrar_credito: $("#mostrar-credito").checked,
  });
  estado.config = await api("/api/config", "POST", c);
  await carregarEstado();
}

$("#salvar-config").onclick = async () => {
  await salvarConfig();
  preencherConfig();
  $("#salvo").textContent = "Salvo ✓";
  setTimeout(() => ($("#salvo").textContent = ""), 2500);
};

// ------------------------------------------------------------------ IA local
let timerOllama = null;
function atualizarOllama() {
  const o = estado.ollama;
  $("#ollama-pasta").textContent = o.pasta;
  if (document.activeElement !== $("#ollama-url")) $("#ollama-url").value = estado.config.ia.ollama.url;
  const sel = $("#ollama-modelo");
  if (!sel.options.length) {
    for (const m of o.sugeridos) {
      sel.add(new Option(`${m.nome} — ${m.tamanho} — ${m.nota}`, m.nome));
    }
    const atual = estado.config.ia.ollama.modelo;
    if (![...sel.options].some((op) => op.value === atual)) sel.add(new Option(atual, atual));
    sel.value = atual;
  }
  const baixados = o.modelos.length ? o.modelos.join(", ") : "nenhum";
  $("#ollama-status").innerHTML =
    `<p>${o.instalado ? "✓ Instalado" : "Não instalado"} · ${o.rodando ? '<span class="ok">ligado</span>' : "desligado"}` +
    (o.rodando ? ` · modelos baixados: ${baixados}` : "") + "</p>";
  $("#ollama-ligar").disabled = !o.instalado || o.rodando;
  $("#ollama-desligar").disabled = !o.rodando;
  $("#ollama-remover").disabled = !o.instalado;

  const t = o.tarefa;
  $("#ollama-instalar").disabled = t.rodando;
  $("#ollama-instalar").textContent = o.instalado ? "Baixar modelo e ligar" : "Instalar e ligar";
  $("#ollama-barra-box").classList.toggle("escondido", !t.rodando);
  $("#ollama-barra").style.width = `${Math.round(t.progresso * 100)}%`;
  $("#ollama-msg").textContent = t.erro ? "Erro: " + t.erro : t.mensagem;
  if (t.rodando) {
    clearTimeout(timerOllama);
    timerOllama = setTimeout(carregarEstado, 1500);
  }
}

$("#ollama-url-salvar").onclick = async () => {
  const url = $("#ollama-url").value.trim() || "http://127.0.0.1:11435/v1";
  try {
    await api("/api/config", "POST", { ia: { ollama: { url } } });
    await carregarEstado();
    $("#ollama-msg").textContent = estado.ollama.rodando
      ? `Endereço salvo. Encontrei a IA local em ${url} ✓`
      : `Endereço salvo, mas nada respondeu em ${url}. O Ollama está aberto?`;
  } catch (e) { alert(e.message); }
};

$("#ollama-instalar").onclick = async () => {
  try {
    await api("/api/ollama/instalar", "POST", { modelo: $("#ollama-modelo").value });
    await carregarEstado();
  } catch (e) { alert(e.message); }
};
for (const [id, acao] of [["#ollama-ligar", "ligar"], ["#ollama-desligar", "desligar"], ["#ollama-remover", "desinstalar"]]) {
  $(id).onclick = async () => {
    if (acao === "desinstalar" && !confirm("Apagar a IA local e os modelos baixados?")) return;
    try { await api(`/api/ollama/${acao}`, "POST"); } catch (e) { alert(e.message); }
    await carregarEstado();
  };
}

carregarEstado();

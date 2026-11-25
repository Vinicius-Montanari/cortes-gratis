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

// ------------------------------------------------------------------ tema
$("#trocar-tema").onclick = () => {
  const novo = document.documentElement.dataset.tema === "claro" ? "escuro" : "claro";
  document.documentElement.dataset.tema = novo;
  localStorage.setItem("tema", novo);
};

// ------------------------------------------------------------------ abas
$$("nav.abas button").forEach((b) =>
  b.addEventListener("click", () => abrirAba(b.dataset.aba)));

function abrirAba(nome) {
  const aba = nome === "projeto" ? "projetos" : nome;
  $$("nav.abas button").forEach((b) => b.classList.toggle("ativa", b.dataset.aba === aba));
  $$(".aba").forEach((s) => s.classList.toggle("escondido", s.id !== `aba-${nome}`));
  if (nome !== "projeto") { projetoAtual = null; clearTimeout(timerProjeto); }
  if (nome === "cortar") carregarRecentes();
  if (nome === "projetos") carregarProjetos();
  if (nome === "config") { preencherConfig(); carregarEstado().then(preencherConfig); }
  window.scrollTo(0, 0);
}

// Etapas do pipeline (mesmos nomes de pipeline.ETAPAS).
const ETAPAS = [["analise", "Baixar e transcrever"], ["candidatos", "Achar momentos"],
  ["ia", "IA filtra"], ["visao", "Conferir a imagem"], ["corte", "Cortar em 9:16"]];

function desenharEtapas(ol, d) {
  const pronto = d.estado === "pronto";
  const atual = ETAPAS.findIndex(([n]) => n === d.etapa);
  ol.innerHTML = "";
  ETAPAS.forEach(([, nome], i) => {
    const li = document.createElement("li");
    const feito = pronto || i < atual;
    li.className = feito ? "feito" : i === atual ? "agora" : "falta";
    li.innerHTML = `<span class="bola"></span><span></span>`;
    li.firstChild.textContent = feito ? "✓" : String(i + 1);
    li.lastChild.textContent = nome;
    ol.appendChild(li);
  });
}

// ------------------------------------------------------------------ estado geral
async function carregarEstado() {
  estado = await api("/api/estado");
  $("#versao").textContent = "v" + estado.versao;
  const g = estado.gpu || {};
  const nomePlaca = (g.nome || "NVIDIA").replace(/^NVIDIA\s+(GeForce\s+)?/i, "");
  const chips = [
    [g.cuda ? nomePlaca : "sem placa NVIDIA", g.cuda, g.cuda ? `Placa de vídeo: ${g.nome}` : "A transcrição vai pelo processador (mais lento)"],
    [estado.ffmpeg ? (estado.nvenc ? "NVENC" : "ffmpeg") : "ffmpeg no 1º uso", estado.ffmpeg, "Programa que corta o vídeo"],
    ["IA local", estado.ollama.rodando, estado.ollama.rodando ? "IA local ligada" : estado.ollama.instalado ? "IA local desligada" : "IA local não instalada"],
  ];
  $("#chips").innerHTML = "";
  for (const [t, ok, dica] of chips) {
    const s = document.createElement("span");
    s.className = "chip" + (ok ? " ok" : "");
    s.textContent = t;
    s.title = dica;
    $("#chips").appendChild(s);
  }

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
  abrirAba("projeto");
  projetoAtual = id;
  assinaturaClipes = "";
  linhaDoTempo = null;
  $("#p-clipes").innerHTML = "";
  $("#p-descartados").innerHTML = "";
  $("#p-linha").classList.add("escondido");
  atualizarProjeto();
}

$("#p-voltar").onclick = () => abrirAba("projetos");

function metaDoProjeto(d) {
  const f = d.fonte || {};
  const partes = [];
  if (f.trecho && (f.trecho[0] || f.trecho[1])) partes.push(`${hms(f.trecho[0] || 0)} → ${hms(f.trecho[1] || f.duracao || 0)}`);
  if (f.plataforma) partes.push(String(f.plataforma).toLowerCase());
  const cands = d.candidatos || [];
  if (cands.length) partes.push(`${cands.length} trechos`);
  if ((d.clipes || []).length) partes.push(`${d.clipes.length} ${d.clipes.length === 1 ? "clipe" : "clipes"}`);
  const quem = cands.find((c) => c.ia)?.ia;
  if (quem) partes.push(quem.replace(/\s*\(.*?\)/g, "").replace(/ ×\d+/g, ""));
  return partes.join(" · ");
}

// ------------------------------------------------------------------ linha do tempo
let linhaDoTempo = null;

async function desenharLinha(d) {
  const caixa = $("#p-linha");
  if (!d.candidatos?.length) { caixa.classList.add("escondido"); return; }
  if (!linhaDoTempo) {
    try { linhaDoTempo = await api(`/api/projetos/${projetoAtual}/linha?barras=110`); } catch { return; }
  }
  const { inicio, fim, barras } = linhaDoTempo;
  if (!barras.length || fim <= inicio) return;
  const dur = fim - inicio, passo = dur / barras.length;
  const tipo = (t0, t1) => {
    let r = "";
    for (const c of d.candidatos) {
      if (c.fim < t0 || c.inicio > t1) continue;
      if (c.escolhido) return "aprovado";
      r = "cand";
    }
    return r;
  };
  const ondas = $("#p-ondas");
  ondas.innerHTML = "";
  barras.forEach((v, i) => {
    const s = document.createElement("span");
    const t0 = inicio + i * passo;
    s.className = tipo(t0, t0 + passo);
    s.style.height = `${Math.round(6 + v * 58)}px`;
    s.title = hms(t0);
    ondas.appendChild(s);
  });
  $("#p-marcas").innerHTML = [0, 1, 2, 3, 4].map((k) => `<span>${hms(inicio + (dur * k) / 4)}</span>`).join("");
  caixa.classList.remove("escondido");
}

let assinaturaClipes = "";
let rodandoAntes = false;

async function atualizarProjeto() {
  if (!projetoAtual) return;
  let d;
  try { d = await api(`/api/projetos/${projetoAtual}`); } catch { return; }
  $("#p-titulo").textContent = d.titulo || d.entrada;
  $("#p-meta").textContent = metaDoProjeto(d);
  const pronto = d.estado === "pronto";
  desenharEtapas($("#p-etapas"), d);
  $("#p-etapas").classList.toggle("escondido", pronto);
  $("#p-barra").parentElement.classList.toggle("escondido", pronto);
  $("#p-barra").style.width = `${Math.round((d.progresso || 0) * 100)}%`;
  $("#p-msg").textContent = pronto ? "Pronto. Assista cada clipe antes de postar." : d.mensagem || "";
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
    desenharLinha(d);
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
    $(".nota-selo", el).textContent = Number(c.nota ?? 0).toFixed(1);
    $(".tempo", el).textContent = `#${cl.id} · ${hms(c.inicio)} → ${hms(c.fim)} · ${Math.round(c.fim - c.inicio)} s`;
    const ch = c.checagem || {};
    const selos = [[ch.se_entende_sozinho, "entende sozinho"], [ch.tem_reacao_forte, "reação forte"], [ch.tem_fecho, "tem fecho"],
      [c.visao ? c.visao.combina !== false : undefined, "imagem confere"]];
    for (const [v, nome] of selos) {
      if (v === undefined || v === null) continue;
      const s = document.createElement("span");
      s.className = v ? "" : "nao";
      s.textContent = (v ? "✓ " : "✗ ") + nome;
      $(".selos", el).appendChild(s);
    }
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

  const feitos = new Set((d.clipes || []).map((c) => c.id));
  const desc = (d.candidatos || []).filter((c) => "nota" in c && !feitos.has(c.id))
    .sort((a, b) => b.nota - a.nota);
  $("#p-desc-box").classList.toggle("escondido", !desc.length);
  const op = d.opcoes || {}, cc = estado?.config?.corte || {};
  const minima = Number(op.nota_minima ?? cc.nota_minima ?? 6), extra = Number(cc.ajuste_local ?? 1);
  $("#p-regua").textContent = desc.some((c) => c.avaliado_por === "ollama")
    ? `nota mínima ${(minima + extra).toFixed(1)} (${minima} + ${extra} da IA local)` : `nota mínima ${minima}`;
  const lista = $("#p-descartados");
  lista.innerHTML = "";
  for (const c of desc) {
    const linha = document.createElement("div");
    linha.className = "descartado";
    linha.innerHTML = `<span class="nota-contorno"></span><span class="texto"><b></b><small></small></span><span class="tempo"></span><button>Cortar assim mesmo</button>`;
    $(".nota-contorno", linha).textContent = Number(c.nota ?? 0).toFixed(1);
    $("b", linha).textContent = c.titulo || `Trecho ${c.id}`;
    $("small", linha).textContent = c.motivo || "";
    $("small", linha).title = c.motivo || "";
    $(".tempo", linha).textContent = hms(c.inicio);
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
  box.innerHTML = lista.length ? "" : `<p class="dica">Nenhum projeto ainda. Cole um link na aba Cortar.</p>`;
  for (const p of lista) {
    const el = document.createElement("button");
    el.className = "projeto-item";
    el.innerHTML = `<span><b></b><br><small></small></span><small class="qtd"></small>`;
    $("b", el).textContent = p.titulo;
    $$("small", el)[0].textContent = (p.criado?.replace("T", " ") || "") + (p.estado !== "pronto" ? ` · ${p.estado}` : "");
    $$("small", el)[1].textContent = `${p.clipes} ${p.clipes === 1 ? "clipe" : "clipes"}`;
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
  $("#ajuste-local").value = c.corte.ajuste_local;
  $("#maiuscula").checked = c.corte.legenda_maiuscula;
  $("#mostrar-gancho").checked = c.corte.mostrar_gancho;
  $("#mostrar-credito").checked = c.corte.mostrar_credito;
  $("#visao-ativo").checked = c.visao.ativo;
  const selV = $("#visao-modelo");
  if (![...selV.options].some((o) => o.value === c.visao.modelo_local)) selV.add(new Option(c.visao.modelo_local, c.visao.modelo_local));
  selV.value = c.visao.modelo_local;
  $("#visao-peso").value = c.visao.peso;
  $("#visao-peso-valor").textContent = Math.round(c.visao.peso * 100) + "%";
  desenharIAs(c.ordem_ia.slice());
}

$("#visao-peso").addEventListener("input", (e) => ($("#visao-peso-valor").textContent = Math.round(e.target.value * 100) + "%"));

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
        <span class="num">${i + 1}</span>
        <label class="check"><input type="checkbox" class="ativo"> <b>${NOMES_IA[nome]}</b></label>
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
    ajuste_local: +$("#ajuste-local").value,
    legenda_maiuscula: $("#maiuscula").checked, mostrar_gancho: $("#mostrar-gancho").checked,
    mostrar_credito: $("#mostrar-credito").checked,
  });
  Object.assign(c.visao, {
    ativo: $("#visao-ativo").checked,
    modelo_local: $("#visao-modelo").value,
    peso: parseFloat($("#visao-peso").value),
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
    `<p class="meta" style="font-size:13px;margin:0 0 14px">${o.instalado ? "instalada" : "não instalada"} · ${o.rodando ? '<span class="ok">ligada</span>' : "desligada"}` +
    (o.rodando ? ` · modelos: ${baixados}` : "") + "</p>";
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

// ------------------------------------------------------------------ painel lateral
let timerLado = null;
async function carregarRecentes() {
  clearTimeout(timerLado);
  let lista;
  try { lista = await api("/api/projetos"); } catch { return; }
  const box = $("#lista-recentes");
  box.innerHTML = lista.length ? "" : `<p class="dica">Os vídeos que você cortar aparecem aqui.</p>`;
  for (const p of lista.slice(0, 5)) {
    const a = document.createElement("a");
    a.href = "#";
    a.innerHTML = "<span></span><span></span>";
    a.firstChild.textContent = p.titulo;
    a.lastChild.textContent = p.estado === "pronto" ? `${p.clipes} ${p.clipes === 1 ? "clipe" : "clipes"}` : p.estado;
    a.onclick = (e) => { e.preventDefault(); abrirProjeto(p.id); };
    box.appendChild(a);
  }
  const ativo = lista.find((p) => p.estado === "rodando" || p.estado === "na fila");
  $("#lado-andamento").classList.toggle("escondido", !ativo);
  if (!ativo) return;
  try {
    const d = await api(`/api/projetos/${ativo.id}`);
    $("#lado-titulo").textContent = d.titulo || d.entrada;
    $("#lado-meta").textContent = metaDoProjeto(d) || d.entrada;
    desenharEtapas($("#lado-etapas"), d);
    $("#lado-barra").style.width = `${Math.round((d.progresso || 0) * 100)}%`;
    $("#lado-log").textContent = (d.log || []).slice(-2).join("\n") || d.mensagem || "";
    $("#lado-log").style.whiteSpace = "pre-line";
    $("#lado-ver").onclick = (e) => { e.preventDefault(); abrirProjeto(ativo.id); };
  } catch { /* tenta de novo na próxima volta */ }
  if (!$("#aba-cortar").classList.contains("escondido")) timerLado = setTimeout(carregarRecentes, 2000);
}

carregarEstado();
carregarRecentes();

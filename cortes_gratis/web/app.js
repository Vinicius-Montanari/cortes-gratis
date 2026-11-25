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

const OMNICLIP = "https://omniclip.app/";
let estado = null;

// Aviso rápido no canto da tela.
function avisar(texto) {
  let el = $("#aviso-rapido");
  if (!el) {
    el = document.createElement("div");
    el.id = "aviso-rapido";
    el.setAttribute("role", "status");
    document.body.appendChild(el);
  }
  el.textContent = texto;
  el.classList.add("ver");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove("ver"), 7000);
}
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
  if (!carregarEstado.feito) { $("#legenda-corte").checked = c.corte.mostrar_legenda !== false; carregarEstado.feito = true; }
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
      mostrar_legenda: $("#legenda-corte").checked,
      ...(camAtual && $("input[name=layout]:checked").value === "camera" ? { camera: camAtual.camera } : {}),
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
  $("#p-retomar").classList.toggle("escondido", !["erro", "cancelado"].includes(d.estado));
  $("#p-cancelar").classList.toggle("escondido", !["rodando", "na fila"].includes(d.estado));

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
    if (cl.srt) $(".srt", el).href = base + encodeURIComponent(cl.srt);
    else $(".srt", el).remove();
    const caixa = el.firstElementChild;
    $(".refazer", el).onclick = () => cortarClipes([cl.id], {
      [cl.id]: {
        titulo: $(".aj-titulo", caixa).value, gancho: $(".aj-gancho", caixa).value,
        inicio: $(".aj-inicio", caixa).value, fim: $(".aj-fim", caixa).value,
      },
    });
    const sel = $(".sel", el);
    sel.dataset.id = cl.id;
    sel.addEventListener("change", () => { sel.closest(".clipe").classList.toggle("marcado", sel.checked); contarSelecao(); });
    $(".omniclip", el).onclick = async () => {
      // O OmniClip roda no navegador e não envia o vídeo: abre o editor e
      // mostra o arquivo no Explorer pra arrastar pra dentro dele.
      window.open(OMNICLIP, "_blank", "noopener");
      try { await api(`/api/projetos/${projetoAtual}/mostrar-arquivo`, "POST", { nome: cl.video }); } catch {}
      avisar("Arraste o .mp4 que apareceu no Explorer pra dentro do OmniClip. Ele precisa do Chrome ou do Edge.");
    };
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
  const minima = Number(op.nota_minima ?? cc.nota_minima ?? 6);
  $("#p-regua").textContent = `nota mínima ${minima}`;
  const lista = $("#p-descartados");
  lista.innerHTML = "";
  for (const c of desc) {
    const linha = document.createElement("div");
    linha.className = "descartado";
    linha.innerHTML = `<input type="checkbox" class="sel" aria-label="Selecionar este trecho"><span class="nota-contorno"></span><span class="texto"><b></b><small></small></span><span class="tempo"></span><button>Cortar assim mesmo</button>`;
    const sel = $(".sel", linha);
    sel.dataset.id = c.id;
    sel.addEventListener("change", () => { linha.classList.toggle("marcado", sel.checked); contarSelecao(); });
    $(".nota-contorno", linha).textContent = Number(c.nota ?? 0).toFixed(1);
    $("b", linha).textContent = c.titulo || `Trecho ${c.id}`;
    $("small", linha).textContent = c.motivo || "";
    $("small", linha).title = c.motivo || "";
    $(".tempo", linha).textContent = hms(c.inicio);
    $("button", linha).onclick = () => cortarClipes([c.id]);
    lista.appendChild(linha);
  }
  $("#p-clipes-barra").classList.toggle("escondido", (d.clipes || []).length < 2);
  contarSelecao();
}

// ------------------------------------------------------------------ selecionar vários
function marcados(caixa) {
  return $$(`${caixa} .sel:checked`).map((x) => Number(x.dataset.id));
}

function contarSelecao() {
  const nd = marcados("#p-descartados").length, totalD = $$("#p-descartados .sel").length;
  $("#desc-qtd").textContent = nd ? `${nd} de ${totalD} selecionado(s)` : "";
  $("#desc-aprovar").disabled = !nd;
  $("#desc-aprovar").textContent = nd > 1 ? `Aprovar e cortar ${nd} trechos` : "Aprovar e cortar selecionados";
  $("#desc-todos").checked = totalD > 0 && nd === totalD;
  const nc = marcados("#p-clipes").length, totalC = $$("#p-clipes .sel").length;
  $("#clipes-qtd").textContent = nc ? `${nc} de ${totalC} selecionado(s)` : "";
  $("#clipes-descartar").disabled = !nc;
  $("#clipes-todos").checked = totalC > 0 && nc === totalC;
}

function marcarTodos(caixa, sim) {
  for (const x of $$(`${caixa} .sel`)) {
    x.checked = sim;
    x.closest(".descartado, .clipe")?.classList.toggle("marcado", sim);
  }
  contarSelecao();
}
$("#desc-todos").addEventListener("change", (e) => marcarTodos("#p-descartados", e.target.checked));
$("#clipes-todos").addEventListener("change", (e) => marcarTodos("#p-clipes", e.target.checked));

$("#desc-aprovar").onclick = () => {
  const ids = marcados("#p-descartados");
  if (ids.length) cortarClipes(ids);
};

$("#clipes-descartar").onclick = async () => {
  const ids = marcados("#p-clipes");
  if (!ids.length) return;
  if (!confirm(`Tirar ${ids.length} clipe(s) dos aprovados? Os arquivos .mp4 são apagados e o trecho volta pra lista de descartados (dá pra cortar de novo).`)) return;
  for (const id of ids) await api(`/api/projetos/${projetoAtual}/clipes/${id}`, "DELETE");
  assinaturaClipes = "";
  atualizarProjeto();
};

// ------------------------------------------------------------------ cancelar e excluir
$("#p-cancelar").onclick = async () => {
  await api(`/api/projetos/${projetoAtual}/cancelar`, "POST");
  avisar("Cancelando... para no próximo passo (pode levar alguns segundos).");
  atualizarProjeto();
};

$("#p-excluir").onclick = async () => {
  const titulo = $("#p-titulo").textContent;
  if (!confirm(`Excluir o projeto "${titulo}"?\n\nApaga a pasta inteira: clipes, transcrição e tudo. Não dá pra desfazer.`)) return;
  try {
    await api(`/api/projetos/${projetoAtual}`, "DELETE");
    avisar("Projeto excluído.");
    abrirAba("projetos");
  } catch (e) { alert(e.message); }
};

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
  $("#proj-barra").classList.toggle("escondido", !lista.length);
  for (const p of lista) {
    const linha = document.createElement("div");
    linha.className = "projeto-linha";
    linha.innerHTML = `<input type="checkbox" class="sel" aria-label="Selecionar este projeto"><button class="projeto-item"><span><b></b><br><small></small></span><small class="qtd"></small></button>`;
    const el = $(".projeto-item", linha);
    $("b", el).textContent = p.titulo;
    $$("small", el)[0].textContent = p.criado?.replace("T", " ") || "";
    if (p.estado !== "pronto") {
      const tag = document.createElement("span");
      tag.className = "estado-tag";
      tag.textContent = p.estado;
      $("b", el).after(tag);
    }
    $$("small", el)[1].textContent = `${p.clipes} ${p.clipes === 1 ? "clipe" : "clipes"}`;
    el.onclick = () => abrirProjeto(p.id);
    const sel = $(".sel", linha);
    sel.dataset.id = p.id;
    sel.addEventListener("change", () => { linha.classList.toggle("marcado", sel.checked); contarProjetos(); });
    box.appendChild(linha);
  }
  contarProjetos();
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
  $("#mostrar-legenda").checked = c.corte.mostrar_legenda !== false;
  $("#visao-ativo").checked = c.visao.ativo;
  const selV = $("#visao-modelo");
  if (![...selV.options].some((o) => o.value === c.visao.modelo_local)) selV.add(new Option(c.visao.modelo_local, c.visao.modelo_local));
  selV.value = c.visao.modelo_local;
  $("#visao-peso").value = c.visao.peso;
  $("#visao-peso-valor").textContent = Math.round(c.visao.peso * 100) + "%";
  desenharIAs(c.ordem_ia.slice());
  preencherMarca();
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
    mostrar_legenda: $("#mostrar-legenda").checked,
  });
  Object.assign(c.visao, {
    ativo: $("#visao-ativo").checked,
    modelo_local: $("#visao-modelo").value,
    peso: parseFloat($("#visao-peso").value),
  });
  if (marca) c.marca = { ...marca, logo: c.marca.logo };
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

// ------------------------------------------------------------------ sua marca
// Áreas que cada app cobre com botões e texto (aproximado, em fração da tela).
const ZONAS = {
  tiktok: [[0.83, 0.40, 1, 0.86], [0, 0.80, 0.80, 1], [0.15, 0, 0.85, 0.07]],
  reels: [[0.84, 0.50, 1, 0.90], [0, 0.81, 0.80, 1], [0, 0, 1, 0.06]],
  shorts: [[0.82, 0.42, 1, 0.88], [0, 0.78, 0.80, 1], [0, 0, 1, 0.06]],
};
const NOME_APP = { tiktok: "TikTok", reels: "Reels", shorts: "Shorts" };
let marca = null;

function preencherMarca() {
  if (!estado) return;
  marca = { ...estado.config.marca };
  $("#marca-ativo").checked = marca.ativo;
  $("#marca-texto-campo").value = marca.texto || "";
  $("#marca-logo-tam").value = marca.logo_tam;
  $("#marca-texto-tam").value = marca.texto_tam;
  $("#marca-opacidade").value = marca.opacidade;
  $("#marca-quando").value = marca.quando;
  $("#marca-zona").value = marca.zona || "";
  $("#marca-logo").src = marca.logo ? `/api/marca/logo?v=${Date.now()}` : "";
  $("#marca-tirar-logo").classList.toggle("escondido", !marca.logo);
  api("/api/marca/previa").then((r) => {
    $("#marca-fundo").src = r.url || "";
    $("#marca-palco").classList.toggle("com-fundo", !!r.url);
  }).catch(() => {});
  desenharMarca();
}

function desenharMarca() {
  if (!marca) return;
  const logo = $("#marca-logo"), txt = $("#marca-texto");
  logo.style.left = `${marca.logo_x * 100}%`;
  logo.style.top = `${marca.logo_y * 100}%`;
  logo.style.width = `${marca.logo_tam * 100}%`;
  logo.style.opacity = marca.opacidade;
  txt.textContent = marca.texto || "";
  txt.style.left = `${marca.texto_x * 100}%`;
  txt.style.top = `${marca.texto_y * 100}%`;
  txt.style.fontSize = `${(marca.texto_tam / 1080) * 100}cqw`;
  txt.style.opacity = marca.opacidade;
  $("#marca-logo-tam-v").textContent = `${Math.round(marca.logo_tam * 100)}%`;
  $("#marca-texto-tam-v").textContent = `${marca.texto_tam}`;
  $("#marca-opacidade-v").textContent = `${Math.round(marca.opacidade * 100)}%`;

  const zonas = ZONAS[marca.zona] || [];
  $("#marca-zonas").innerHTML = zonas.map(([x0, y0, x1, y1]) =>
    `<span style="left:${x0 * 100}%;top:${y0 * 100}%;width:${(x1 - x0) * 100}%;height:${(y1 - y0) * 100}%"></span>`).join("");
  // Avisa se algum pedaço da marca cai embaixo dos botões do app.
  const palco = $("#marca-palco").getBoundingClientRect();
  const cobertos = [];
  for (const [el, nome] of [[logo, "O logo"], [txt, "O texto"]]) {
    const r = el.getBoundingClientRect();
    if (!r.width || !palco.width) { el.classList.remove("fora"); continue; }
    const a = [(r.left - palco.left) / palco.width, (r.top - palco.top) / palco.height,
      (r.right - palco.left) / palco.width, (r.bottom - palco.top) / palco.height];
    const bate = zonas.some(([x0, y0, x1, y1]) => a[0] < x1 && a[2] > x0 && a[1] < y1 && a[3] > y0);
    el.classList.toggle("fora", bate);
    if (bate) cobertos.push(nome);
  }
  $("#marca-aviso").textContent = cobertos.length
    ? `${cobertos.join(" e ")} fica embaixo dos botões do ${NOME_APP[marca.zona]}.` : "";
}

function arrastar(el, chaveX, chaveY) {
  el.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    el.setPointerCapture(e.pointerId);
    const palco = $("#marca-palco").getBoundingClientRect();
    const r = el.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
    const mover = (ev) => {
      let x = (ev.clientX - dx - palco.left) / palco.width;
      const y = (ev.clientY - dy - palco.top) / palco.height;
      const noCentro = Math.abs(x - 0.5) < 0.025; // gruda no meio
      if (noCentro) x = 0.5;
      $("#marca-guia").classList.toggle("ver", noCentro);
      marca[chaveX] = Math.round(Math.min(1, Math.max(0, x)) * 1000) / 1000;
      marca[chaveY] = Math.round(Math.min(1, Math.max(0, y)) * 1000) / 1000;
      desenharMarca();
    };
    const soltar = () => {
      el.removeEventListener("pointermove", mover);
      $("#marca-guia").classList.remove("ver");
    };
    el.addEventListener("pointermove", mover);
    el.addEventListener("pointerup", soltar, { once: true });
    el.addEventListener("pointercancel", soltar, { once: true });
  });
}
arrastar($("#marca-logo"), "logo_x", "logo_y");
arrastar($("#marca-texto"), "texto_x", "texto_y");
$("#marca-logo").addEventListener("load", desenharMarca);

for (const [id, chave, conv] of [["#marca-logo-tam", "logo_tam", Number], ["#marca-texto-tam", "texto_tam", Number],
  ["#marca-opacidade", "opacidade", Number], ["#marca-texto-campo", "texto", String],
  ["#marca-quando", "quando", String], ["#marca-zona", "zona", String]]) {
  $(id).addEventListener("input", (e) => { if (marca) { marca[chave] = conv(e.target.value); desenharMarca(); } });
}
$("#marca-ativo").addEventListener("change", (e) => { if (marca) marca.ativo = e.target.checked; });

$("#marca-arquivo").addEventListener("change", async (e) => {
  const arq = e.target.files[0];
  e.target.value = "";
  if (!arq) return;
  if (arq.size > 3 * 1024 * 1024) { alert("Logo grande demais (máximo 3 MB)."); return; }
  const dados = await new Promise((ok, erro) => {
    const r = new FileReader();
    r.onload = () => ok(r.result);
    r.onerror = erro;
    r.readAsDataURL(arq);
  });
  try {
    const r = await api("/api/marca/logo", "POST", { dados });
    marca.logo = estado.config.marca.logo = r.logo;
    if (!marca.ativo) { marca.ativo = true; $("#marca-ativo").checked = true; }
    $("#marca-logo").src = `/api/marca/logo?v=${Date.now()}`;
    $("#marca-tirar-logo").classList.remove("escondido");
  } catch (err) { alert(err.message); }
});

$("#marca-tirar-logo").onclick = async () => {
  await api("/api/marca/logo", "DELETE");
  marca.logo = estado.config.marca.logo = "";
  $("#marca-logo").src = "";
  $("#marca-tirar-logo").classList.add("escondido");
  desenharMarca();
};

$("#marca-salvar").onclick = async () => {
  try {
    estado.config = await api("/api/config", "POST", { marca });
    marca = { ...estado.config.marca };
    $("#marca-salvo").textContent = "Salvo ✓";
    setTimeout(() => ($("#marca-salvo").textContent = ""), 2500);
  } catch (e) { alert(e.message); }
};

// ------------------------------------------------------------------ layout câmera + jogo
// Marca no quadro do vídeo onde está a câmera e o jogo (frações 0–1) e
// desenha a prévia 9:16 do mesmo jeito que o ffmpeg monta (corte.geometria_camera).
let camAtual = null;  // {canal, camera, img}

function mostrarPainelCamera() {
  const ativo = $("input[name=layout]:checked").value === "camera";
  $("#painel-camera").classList.toggle("escondido", !ativo);
  if (ativo && !camAtual && $("#entrada").value.trim()) carregarQuadro();
}
$$("input[name=layout]").forEach((r) => r.addEventListener("change", mostrarPainelCamera));
$("#entrada").addEventListener("change", () => { camAtual = null; $("#cam-editor").classList.add("escondido"); mostrarPainelCamera(); });

async function carregarQuadro(t) {
  const entrada = $("#entrada").value.trim();
  if (!entrada) { $("#cam-msg").textContent = "Cole o link ou o caminho do vídeo primeiro."; return; }
  $("#cam-msg").textContent = "Pegando um quadro do vídeo...";
  $("#cam-carregar").disabled = true;
  try {
    const r = await api("/api/camera/quadro", "POST", {
      entrada, t, inicio: $("#trecho-inicio").value.trim(), fim: $("#trecho-fim").value.trim(),
    });
    const img = new Image();
    await new Promise((ok, erro) => { img.onload = ok; img.onerror = erro; img.src = r.imagem; });
    camAtual = { canal: r.canal, camera: r.camera, img, t: r.t };
    $("#cam-img").src = r.imagem;
    $("#cam-topo").value = r.camera.topo;
    $("#cam-largura").value = r.camera.cam_largura;
    $("#cam-espaco").value = r.camera.espaco;
    $("#cam-msg").textContent = r.salvo
      ? `Usando a posição salva do canal ${r.nome_canal}. Confira se a câmera está no lugar.`
      : `Canal ${r.nome_canal || "sem nome"}: marque a câmera uma vez e salve.`;
    $("#cam-editor").classList.remove("escondido");
    desenharCamera();
  } catch (e) {
    $("#cam-msg").textContent = e.message;
  } finally {
    $("#cam-carregar").disabled = false;
  }
}
$("#cam-carregar").onclick = () => carregarQuadro();
$("#cam-outro").onclick = () => carregarQuadro(camAtual ? camAtual.t + 97 : undefined);
$("#cam-jogo-todo").onclick = () => { if (camAtual) { camAtual.camera.jogo = [0, 0, 1, 1]; desenharCamera(); } };

function posRet(el, [x, y, w, h]) {
  Object.assign(el.style, { left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` });
}

// Mesma conta de corte.geometria_camera (em pixels de 1080x1920).
function geometriaCamera(c, aspecto) {
  const par = (v) => Math.max(2, Math.round(v / 2) * 2);
  const [, , w, h] = c.cam;
  let cw = par(1080 * Math.min(1, Math.max(0.3, c.cam_largura)));
  const prop = (Math.max(h, 0.02) / Math.max(w, 0.02)) / aspecto;
  const yCam = par(1920 * Math.min(0.5, Math.max(0, c.topo)));
  let ch = par(cw * prop);
  const max = 1920 - yCam - 480;
  if (ch > max) { ch = par(max); cw = par(ch / prop); }
  const yJogo = par(yCam + ch + 1920 * Math.min(0.2, Math.max(0, c.espaco)));
  const jh = par(1920 - yJogo);
  return { cw, ch, xCam: (1080 - cw) / 2, yCam, yJogo, jh, jogoCorte: recorteJogo(c.jogo, c.cam, 1080 / jh, aspecto) };
}

// Mesma conta de corte.recorte_jogo: maior pedaço com a proporção da área de
// baixo, centralizado no retângulo do jogo, desviando da câmera do streamer.
function recorteJogo([jx, jy, jw, jh], [cx, cy, cw, ch], aspTela, aspFonte) {
  const w = Math.min(jw, jh * aspTela / aspFonte), h = Math.min(jh, jw * aspFonte / aspTela);
  let x = jx + (jw - w) / 2;
  const y = jy + (jh - h) / 2;
  if (cy < y + h && cy + ch > y && cx < x + w && cx + cw > x) {
    x = cx + cw / 2 < x + w / 2 ? Math.min(Math.max(x, cx + cw), jx + jw - w) : Math.max(Math.min(x, cx - w), jx);
  }
  return [x, y, w, h];
}

function desenharCamera() {
  if (!camAtual) return;
  const c = camAtual.camera, img = camAtual.img;
  c.topo = +$("#cam-topo").value; c.cam_largura = +$("#cam-largura").value; c.espaco = +$("#cam-espaco").value;
  $("#cam-topo-v").textContent = `${Math.round(c.topo * 100)}%`;
  $("#cam-largura-v").textContent = `${Math.round(c.cam_largura * 100)}%`;
  $("#cam-espaco-v").textContent = `${(c.espaco * 100).toFixed(1)}%`;
  posRet($("#ret-cam"), c.cam);
  posRet($("#ret-jogo"), c.jogo);

  const cv = $("#cam-previa"), ctx = cv.getContext("2d"), k = cv.width / 1080;
  const W = img.naturalWidth, H = img.naturalHeight, g = geometriaCamera(c, W / H);
  ctx.clearRect(0, 0, cv.width, cv.height);
  // fundo borrado (cobre a tela toda)
  ctx.save();
  ctx.filter = "blur(6px) brightness(0.85)";
  const esc = Math.max(cv.width / W, cv.height / H);
  ctx.drawImage(img, (cv.width - W * esc) / 2, (cv.height - H * esc) / 2, W * esc, H * esc);
  ctx.restore();
  // câmera
  const [cx, cy, cw, ch] = c.cam;
  ctx.drawImage(img, cx * W, cy * H, cw * W, ch * H, g.xCam * k, g.yCam * k, g.cw * k, g.ch * k);
  // jogo: pedaço calculado igual ao do corte (desvia da câmera)
  const [jx, jy, jw, jh] = g.jogoCorte;
  ctx.drawImage(img, jx * W, jy * H, jw * W, jh * H, 0, g.yJogo * k, 1080 * k, g.jh * k);
  // onde o gancho vai ficar
  ctx.fillStyle = "#fff";
  ctx.fillRect(cv.width * 0.18, (g.yCam + g.ch) * k - 9, cv.width * 0.64, 18);
  ctx.fillStyle = "#000"; ctx.font = "bold 10px Arial"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText("GANCHO DO CLIPE", cv.width / 2, (g.yCam + g.ch) * k);
}
["#cam-topo", "#cam-largura", "#cam-espaco"].forEach((id) => $(id).addEventListener("input", desenharCamera));

// Arrastar (miolo) e redimensionar (alça do canto) os retângulos.
for (const el of [$("#ret-cam"), $("#ret-jogo")]) {
  el.addEventListener("pointerdown", (e) => {
    if (!camAtual) return;
    e.preventDefault();
    e.stopPropagation();
    el.setPointerCapture(e.pointerId);
    const palco = $("#cam-palco").getBoundingClientRect();
    const r = camAtual.camera[el.dataset.chave];
    const [x0, y0, w0, h0] = r;
    const mx0 = e.clientX, my0 = e.clientY;
    const redimensionar = e.target.classList.contains("alca");
    const mover = (ev) => {
      const dx = (ev.clientX - mx0) / palco.width, dy = (ev.clientY - my0) / palco.height;
      if (redimensionar) {
        r[2] = Math.min(1 - x0, Math.max(0.03, w0 + dx));
        r[3] = Math.min(1 - y0, Math.max(0.03, h0 + dy));
      } else {
        r[0] = Math.min(1 - w0, Math.max(0, x0 + dx));
        r[1] = Math.min(1 - h0, Math.max(0, y0 + dy));
      }
      r.forEach((v, i) => (r[i] = Math.round(v * 1000) / 1000));
      desenharCamera();
    };
    el.addEventListener("pointermove", mover);
    el.addEventListener("pointerup", () => el.removeEventListener("pointermove", mover), { once: true });
  });
}

$("#cam-salvar").onclick = async () => {
  if (!camAtual) return;
  try {
    const r = await api("/api/camera/salvar", "POST", { canal: camAtual.canal, camera: camAtual.camera });
    $("#cam-salvo").textContent = `Salvo pro canal ${r.canal} ✓`;
    setTimeout(() => ($("#cam-salvo").textContent = ""), 3000);
  } catch (e) { alert(e.message); }
};

function contarProjetos() {
  const todos = $$("#lista-projetos .sel"), sel = todos.filter((x) => x.checked);
  $("#proj-qtd").textContent = sel.length ? `${sel.length} de ${todos.length} selecionado(s)` : "";
  $("#proj-excluir").disabled = !sel.length;
  $("#proj-todos").checked = todos.length > 0 && sel.length === todos.length;
}
$("#proj-todos").addEventListener("change", (e) => {
  for (const x of $$("#lista-projetos .sel")) {
    x.checked = e.target.checked;
    x.closest(".projeto-linha").classList.toggle("marcado", x.checked);
  }
  contarProjetos();
});
$("#proj-excluir").onclick = async () => {
  const ids = $$("#lista-projetos .sel:checked").map((x) => x.dataset.id);
  if (!ids.length) return;
  if (!confirm(`Excluir ${ids.length} projeto(s)?\n\nApaga as pastas inteiras: clipes, transcrição e tudo. Não dá pra desfazer. Projeto que estiver rodando é cancelado antes.`)) return;
  try {
    const r = await api("/api/projetos/excluir", "POST", { ids });
    avisar(`${r.excluidos} projeto(s) excluído(s).`);
  } catch (e) { alert(e.message); }
  carregarProjetos();
};

"""Testes das partes que não precisam de internet, placa de vídeo nem IA."""
import json

import pytest

from cortes_gratis import candidatos, config, corte
from cortes_gratis.analise import hms, para_segundos
from cortes_gratis.ia import avaliar, cliente


def _frases_sinteticas(total=600):
    """Uma live falsa: uma frase a cada 4 s, com um momento de reação aos 300 s."""
    frases = []
    for t in range(0, total, 4):
        texto = "hoje a gente vai jogar mais uma partida aqui"
        if 296 <= t <= 304:
            texto = "NÃO ACREDITO! caralho kkkkkk"
        palavras = [{"i": t + k * 0.4, "f": t + k * 0.4 + 0.35, "p": p}
                    for k, p in enumerate(texto.split())]
        frases.append({"i": float(t), "f": t + 3.5, "texto": texto, "palavras": palavras})
    db = [-35.0] * total
    for s in range(298, 306):
        db[s] = -8.0
    return frases, {"deslocamento": 0.0, "db": db}


def test_tempos():
    assert para_segundos("1:02:03") == 3723
    assert para_segundos("12:03.5") == 723.5
    assert para_segundos("") is None
    assert hms(3723) == "1:02:03"
    assert hms(65) == "1:05"


def test_reacao_pontua():
    assert candidatos.pontos_reacao("Não acredito! kkkkk") > 2
    assert candidatos.pontos_reacao("vamos ver o inventário") == 0
    assert candidatos.pontos_reacao("I am running to the store") == 0  # "run" dentro de palavra
    assert candidatos.pontos_reacao("Não, não, não! Socorro") >= 2


def test_candidato_pega_o_pico():
    frases, energia = _frases_sinteticas()
    cands = candidatos.achar(frases, energia, quantos=5, dur_min=20, dur_max=60)
    assert cands, "deveria achar pelo menos um trecho"
    melhor = max(cands, key=lambda c: c["pontos"])
    assert melhor["inicio"] < 300 < melhor["fim"]
    for c in cands:
        assert 15 <= c["fim"] - c["inicio"] <= 60
    # sem sobreposição
    ordenados = sorted(cands, key=lambda c: c["inicio"])
    for a, b in zip(ordenados, ordenados[1:]):
        assert a["fim"] <= b["inicio"]


def test_candidato_comeca_em_frase():
    frases, energia = _frases_sinteticas()
    inicios = {f["i"] for f in frases}
    for c in candidatos.achar(frases, energia, quantos=5):
        assert any(abs(c["inicio"] - (i - 0.3)) < 0.01 for i in inicios) or c["inicio"] == 0


def test_linhas_do_trecho_marca_fora():
    frases, energia = _frases_sinteticas()
    c = candidatos.achar(frases, energia, quantos=1)[0]
    linhas = candidatos.linhas_do_trecho(c, frases)
    assert linhas[0]["fora"] and linhas[-1]["fora"]
    assert any(not ln["fora"] for ln in linhas)
    assert [ln["n"] for ln in linhas] == list(range(len(linhas)))


def test_ass_destaca_palavra_falada():
    palavras = [{"i": 10.0, "f": 10.4, "p": "olha"}, {"i": 10.5, "f": 10.9, "p": "isso"},
                {"i": 11.0, "f": 11.5, "p": "aqui!"}]
    ass = corte.montar_ass(palavras, 9.0, 20.0, "GANCHO {X}", "@canal", True, "desfocado")
    assert "PlayResX: 1080" in ass
    assert "GANCHO (X)" in ass  # chave escapada pra não virar comando do ASS
    assert "@canal" in ass
    linhas = [ln for ln in ass.splitlines() if ln.startswith("Dialogue: 0")]
    assert len(linhas) == 3
    assert "0:00:01.00" in linhas[0]  # 10.0 - 9.0
    assert corte.AMARELO + "}OLHA" in linhas[0]
    assert corte.AMARELO + "}ISSO" in linhas[1]


def test_grupos_quebram_em_pausa_e_tamanho():
    w = lambda i, p: {"i": i, "f": i + 0.3, "p": p}  # noqa: E731
    g = corte.grupos([w(0, "a"), w(0.4, "b"), w(2.0, "c"), w(2.4, "palavragrandona"), w(2.8, "x")])
    assert [len(x) for x in g][0] == 2  # pausa de 1.6 s quebra o bloco


def test_slug_e_credito():
    assert corte.slug("Ele não viu o CAMINHÃO!") == "ele-nao-viu-o-caminhao"
    assert corte.credito_de({"canal_id": "@gaules"}) == "@gaules"
    assert corte.credito_de({"canal_id": "UCabc123", "canal": "Canal X"}) == "Canal X"
    assert corte.credito_de({"canal_id": "x"}, "@meu") == "@meu"


def test_link_no_tempo():
    assert corte.link_no_tempo({"link": "https://www.youtube.com/watch?v=abc"}, 723) \
        == "https://www.youtube.com/watch?v=abc&t=723s"
    assert corte.link_no_tempo({"link": "https://www.twitch.tv/videos/1"}, 3723) \
        == "https://www.twitch.tv/videos/1?t=1h2m3s"


def test_extrair_json_tolerante():
    assert cliente.extrair_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert cliente.extrair_json('Claro! Aqui está: {"a": [1, 2]} espero ter ajudado') == {"a": [1, 2]}
    with pytest.raises(json.JSONDecodeError):
        cliente.extrair_json("sem json nenhum")


def test_aplicar_resposta_da_ia():
    cc = config.PADRAO["corte"]
    c = {"id": 1, "inicio": 100.0, "fim": 140.0}
    linhas = [{"n": k, "i": 95.0 + k * 4, "f": 98.5 + k * 4} for k in range(15)]
    avaliar._aplicar(c, {"nota": "8.5", "motivo": "susto", "titulo": "T", "gancho": "olha isso",
                         "hashtags": "gta clips", "linha_inicio": 2, "linha_fim": 10}, linhas, cc)
    assert c["nota"] == 8.5
    assert c["gancho"] == "OLHA ISSO"
    assert c["hashtags"] == ["#gta", "#clips"]
    assert c["inicio"] == pytest.approx(102.7)
    assert c["fim"] == pytest.approx(139.7)  # fim da linha 10 (138.5) + 1.2 de folga
    # sugestão absurda (clipe de 4 s) é ignorada
    c2 = {"id": 2, "inicio": 100.0, "fim": 140.0}
    avaliar._aplicar(c2, {"nota": 7, "linha_inicio": 3, "linha_fim": 3}, linhas, cc)
    assert (c2["inicio"], c2["fim"]) == (100.0, 140.0)


def test_escolher_respeita_nota_e_maximo():
    cfg = config.carregar()
    cfg["corte"].update(nota_minima=6, max_clipes=2)
    cands = [{"id": 1, "inicio": 0, "fim": 30, "nota": 9},
             {"id": 2, "inicio": 40, "fim": 70, "nota": 5},
             {"id": 3, "inicio": 80, "fim": 110, "nota": 7},
             {"id": 4, "inicio": 120, "fim": 150, "nota": 8}]
    ids = [c["id"] for c in avaliar.escolher(cands, cfg)]
    assert ids == [1, 4]


def test_cadeia_pula_ia_sem_chave_e_cota(monkeypatch):
    cfg = config.carregar()
    cfg["ordem_ia"] = ["groq", "gemini"]
    cfg["ia"]["groq"]["chave"] = ""
    cfg["ia"]["gemini"].update(chave="x", modelo="gemini-teste")
    chamadas = []

    def falso(self, sistema, usuario):
        chamadas.append(self.nome)
        return '{"avaliacoes": []}'

    monkeypatch.setattr(cliente.Provedor, "conversar", falso)
    cad = cliente.Cadeia(cfg, lambda m: None)
    assert cad.pedir_json("s", "u") == {"avaliacoes": []}
    assert chamadas == ["gemini"]

    # Groq com cota estourada por dia -> pula pro Gemini
    cfg["ia"]["groq"]["chave"] = "y"
    chamadas.clear()

    def cota(self, sistema, usuario):
        chamadas.append(self.nome)
        if self.nome == "groq":
            raise cliente.ErroCota("acabou", esperar=3600)
        return '{"ok": 1}'

    monkeypatch.setattr(cliente.Provedor, "conversar", cota)
    cad = cliente.Cadeia(cfg, lambda m: None)
    assert cad.pedir_json("s", "u") == {"ok": 1}
    assert cad.pedir_json("s", "u") == {"ok": 1}
    assert chamadas == ["groq", "gemini", "gemini"]  # 2ª vez nem tenta o Groq


def test_casar_tolera_id_errado_e_objeto_solto():
    grupo = [{"id": 7}]
    assert avaliar._casar({"avaliacoes": [{"id": 1, "nota": 8}]}, grupo) == [{"id": 1, "nota": 8}]
    assert avaliar._casar({"id": 1, "nota": 3}, grupo) == [{"id": 1, "nota": 3}]
    dois = [{"id": 3}, {"id": 4}]
    r = avaliar._casar({"avaliacoes": [{"id": 4, "nota": 1}, {"id": 3, "nota": 2}]}, dois)
    assert [a["nota"] for a in r] == [2, 1]
    assert avaliar._casar({"avaliacoes": [{"id": 9, "nota": 1}]}, dois) == [None, None]


def test_visao_reprova_menu_e_mistura_nota():
    from cortes_gratis.ia import visao
    c = {"id": 1, "nota": 8.0, "motivo": "susto"}
    visao.combinar(c, {"tipo": "menu_ou_loja", "nota_visual": 7, "o_que_aparece": "loja de armas",
                       "imagem_combina_com_titulo": True}, 0.4)
    assert c["nota"] <= 3 and c["nota_texto"] == 8.0
    assert "Reprovado pela imagem" in c["motivo"] and "loja de armas" in c["motivo"]

    c = {"id": 2, "nota": 8.0, "motivo": "fuga"}
    visao.combinar(c, {"tipo": "gameplay_acao", "nota_visual": 6,
                       "imagem_combina_com_titulo": "false"}, 0.4)
    assert c["nota"] == pytest.approx(0.6 * 8 + 0.4 * 6 - 1)

    c = {"id": 3, "nota": 7.0}
    visao.combinar(c, {"tipo": "gameplay_acao", "nota_visual": "lixo",
                       "imagem_combina_com_titulo": True}, 0.5)
    assert c["nota"] == pytest.approx(6.0)  # nota visual inválida vira 5


def test_lista_de_verificacao_segura_nota():
    lim = avaliar._limitar
    assert lim(8.0, {"tem_reacao_forte": False})[0] == 6.0
    assert lim(8.0, {"se_entende_sozinho": "false"})[0] == 5.0
    assert lim(8.0, {"tem_reacao_forte": True, "se_entende_sozinho": True, "tem_fecho": False})[0] == 7.0
    assert lim(9.0, {"o_que_acontece": "Não dá pra entender"})[0] == 3.0
    # sem a lista (IA que não preencheu), a nota fica como veio
    assert lim(8.0, {})[0] == 8.0


def test_nota_da_ia_local_perde_o_ajuste_e_a_minima_e_a_escolhida():
    cfg = config.carregar()
    cfg["corte"].update(nota_minima=8, ajuste_local=1)
    nuvem = {"nota": 8.0, "avaliado_por": "groq", "motivo": "bom"}
    local = {"nota": 8.0, "avaliado_por": "ollama", "motivo": "bom"}
    avaliar.ajustar_local(nuvem, cfg["corte"])
    avaliar.ajustar_local(local, cfg["corte"])
    assert nuvem["nota"] == 8.0 and local["nota"] == 7.0 and "ajuste" in local["motivo"]
    assert avaliar.minima_de(local, cfg) == 8.0  # a nota mínima não muda sozinha
    assert avaliar.passou(nuvem, cfg) and not avaliar.passou(local, cfg)


def test_trecho_com_pouca_fala_cai():
    # 10 min de jogo: só uma fala solta aos 300 s, mas um pico de volume moderado ali
    frases = [{"i": 300.0, "f": 301.0, "texto": "o que é isso?",
               "palavras": [{"i": 300.0, "f": 300.3, "p": "o"}, {"i": 300.3, "f": 300.6, "p": "que"},
                            {"i": 300.6, "f": 300.8, "p": "é"}, {"i": 300.8, "f": 301.0, "p": "isso?"}]}]
    db = [-30.0] * 600
    for s in range(298, 305):
        db[s] = -22.0  # 8 dB acima do normal: não é estouro
    assert candidatos.achar(frases, {"deslocamento": 0, "db": db}, quantos=5) == []
    # com um estouro de verdade (explosão), o trecho sem fala é aceito
    for s in range(298, 305):
        db[s] = -8.0
    assert candidatos.achar(frases, {"deslocamento": 0, "db": db}, quantos=5)


def test_marca_entra_na_legenda_e_no_filtro(tmp_path, monkeypatch):
    from cortes_gratis import config, corte
    monkeypatch.setattr(config, "PASTA_MARCA", tmp_path)
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    m = dict(config.PADRAO["marca"], ativo=True, logo="logo.png", texto="corte: @eu",
             texto_x=0.5, texto_y=0.25, quando="inicio_fim")
    ativa = corte.marca_ativa(m)
    assert ativa and ativa["caminho_logo"] == tmp_path / "logo.png"
    ass = corte.montar_ass([], 0, 30, "", "", True, "desfocado", ativa)
    linhas = [x for x in ass.splitlines() if "corte: @eu" in x]
    assert len(linhas) == 2  # começo e fim
    assert r"\an5\pos(540,480)" in linhas[0]
    f = corte.filtro_video("desfocado", corte.filtro_logo(2, ativa, 30))
    assert "[2:v]scale=151:-1" in f and "between(t,26.00,30.00)" in f
    assert f.endswith("[comlogo]ass=legenda.ass[v]")


def test_marca_desligada_ou_vazia_nao_entra():
    from cortes_gratis import config, corte
    assert corte.marca_ativa(dict(config.PADRAO["marca"])) is None
    assert corte.marca_ativa(dict(config.PADRAO["marca"], ativo=True)) is None
    assert corte.filtro_video("centro").endswith("[base]ass=legenda.ass[v]")


def test_corte_de_link_usa_relogio_original(monkeypatch):
    """Link: pula largo antes do -i e corta exato no filtro (HLS da Kick erra o -ss)."""
    from cortes_gratis import corte
    monkeypatch.setattr(corte, "inicio_do_fluxo", lambda url, cab: 64.171)
    args, exato = corte.entrada_link("https://x/v.m3u8", {}, 11344.0, 30.0)
    assert args[args.index("-ss") + 1] == "11314.000" and abs(exato - 11408.171) < 1e-6
    f = corte.filtro_video("desfocado", "", exato)
    assert f.startswith("[0:v]trim=start=11408.171,setpts=PTS-STARTPTS,split=2[srca][srcb];")
    assert "[0:v]" not in f.split(";", 1)[1]
    assert corte.filtro_video("centro", "", exato).startswith("[0:v]trim=start=11408.171,setpts=PTS-STARTPTS[src];")


def test_layout_camera_monta_camera_em_cima_e_jogo_embaixo():
    from cortes_gratis import config, corte
    cam = dict(config.PADRAO["camera"]["padrao"], cam=[0.0, 0.115, 0.24, 0.278], topo=0.15)
    g = corte.geometria_camera(cam)
    assert g["y_cam"] == 288 and g["cw"] == 1080 and g["y_jogo"] == g["y_cam"] + g["ch"]
    assert g["jh"] >= 480 and g["y_jogo"] + g["jh"] == 1920
    f = corte.filtro_video("camera", "", 500.0, g)
    assert "split=3[srca][srcb][srcc]" in f and "[t1][jogo]overlay=0:" in f
    ass = corte.montar_ass([], 0, 10, "GANCHO", "", True, "camera", gancho_y=g["divisa"])
    assert rf"\pos(540,{g['divisa']})" in ass


def test_recorte_do_jogo_desvia_da_camera():
    from cortes_gratis import corte
    asp_tela = 1080 / 1024
    # câmera no canto de cima à esquerda (até 24% da largura): recorte começa depois dela
    x, y, w, h = corte.recorte_jogo([0, 0, 1, 1], [0.0, 0.115, 0.24, 0.278], asp_tela, 16 / 9)
    assert x >= 0.24 and x + w <= 1.0 and h == 1.0
    # câmera no canto direito: recorte termina antes dela
    x, y, w, h = corte.recorte_jogo([0, 0, 1, 1], [0.78, 0.7, 0.22, 0.3], asp_tela, 16 / 9)
    assert x + w <= 0.78 + 1e-6 and x >= 0
    # câmera fora do recorte central: fica no centro
    x, y, w, h = corte.recorte_jogo([0, 0, 1, 1], [0.0, 0.0, 0.1, 0.1], asp_tela, 16 / 9)
    assert abs((x + w / 2) - 0.5) < 1e-3


def test_legenda_desligada_e_srt():
    from cortes_gratis import corte
    pal = [{"i": 10.0, "f": 10.4, "p": "não"}, {"i": 10.4, "f": 11.0, "p": "acreditaram."},
           {"i": 12.0, "f": 12.5, "p": "caramba"}]
    com = corte.montar_ass(pal, 9.0, 20.0, "GANCHO", "@x", True, "desfocado")
    sem = corte.montar_ass(pal, 9.0, 20.0, "GANCHO", "@x", True, "desfocado", legenda=False)
    assert "ACREDITARAM" in com and "ACREDITARAM" not in sem
    assert "GANCHO" in sem and "@x" in sem  # gancho e crédito continuam
    srt = corte.montar_srt(pal, 9.0, 20.0)
    assert srt.startswith("1\n00:00:01,000 --> 00:00:02,400\nnão acreditaram.")
    assert "2\n00:00:03,000 --> " in srt

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

"""Testes da extração em blocos (invoice gigante) + conciliação em escala.

Partes 1-2 são puras (sem rede/banco). A parte 3 usa o Gemini real com blocos pequenos
forçados — se a quota do dia estiver esgotada, reporta SKIP honesto (não falha).

Rodar: mcp-server/.venv/Scripts/python.exe app/test_extracao_blocos.py
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import llm_extracao  # noqa: E402
from llm_extracao import _dividir_em_blocos, _mesclar  # noqa: E402
from processamento import conciliar_itens  # noqa: E402


def parte1_divisao_e_merge():
    # divisão: nenhuma linha perdida, nenhum bloco acima do limite, item nunca cortado no meio
    linhas = [f"Item {i:04d}: Produto sintético número {i} - Qty {i%7+1}" for i in range(500)]
    texto = "\n".join(linhas)
    blocos = _dividir_em_blocos(texto, max_chars=2000)
    assert len(blocos) > 1, "texto grande deveria dividir"
    assert all(len(b) <= 2000 for b in blocos)
    assert "\n".join(blocos).splitlines() == linhas, "linhas perdidas/reordenadas na divisão"
    # texto pequeno: 1 bloco
    assert _dividir_em_blocos("curto", max_chars=2000) == ["curto"]

    # merge: itens concatenam; campos first-wins; falhas contadas
    p1 = {"tipo_transporte": None, "campos": {"numero": "INV-1"}, "itens": [{"codigo": "A"}]}
    p2 = None  # bloco que falhou
    p3 = {"tipo_transporte": "B/L", "campos": {"numero": "OUTRO", "valor_total": "9"},
          "itens": [{"codigo": "B"}, {"codigo": "C"}]}
    m = _mesclar([p1, p2, p3])
    assert [i["codigo"] for i in m["itens"]] == ["A", "B", "C"]
    assert m["campos"]["numero"] == "INV-1"          # 1º não-vazio vence (cabeçalho no bloco 1)
    assert m["campos"]["valor_total"] == "9"          # completado por bloco posterior
    assert m["tipo_transporte"] == "B/L"
    assert m["blocos_falhos"] == 1 and m["blocos_total"] == 3
    print("parte 1 OK — divisão sem perda + merge com falha CONTADA (nunca silenciosa)")


def parte2_conciliacao_em_escala():
    """O 'santo graal': conferir milhares de itens item a item — impossível à mão, trivial aqui."""
    n = 3000
    inv = [{"codigo": f"SKU{i:05d}", "descricao": f"Produto {i}", "quantidade": str(i % 50 + 1)} for i in range(n)]
    pk = [dict(item) for item in inv]
    pk[137]["quantidade"] = "999"          # divergência de quantidade
    pk[2500]["quantidade"] = "998"         # outra
    del pk[42]                             # item sumido do packing list
    t0 = time.perf_counter()
    divs = conciliar_itens(inv, pk)
    dt = time.perf_counter() - t0
    assert len(divs) == 3, f"esperado 3 divergências, veio {len(divs)}"
    tipos = sorted(d["severidade"] for d in divs)
    assert tipos == ["atencao", "critico", "critico"]
    assert dt < 2.0, f"conciliação de {n} itens lenta demais: {dt:.2f}s"
    print(f"parte 2 OK — {n} itens conciliados em {dt*1000:.0f}ms, 3/3 divergências plantadas achadas")


def parte3_extracao_real_em_blocos():
    """Extração real (Gemini) com blocos forçados pequenos sobre o doc real da Luciana."""
    import extracao
    conteudo = open("C:/Users/Alexandre/Downloads/IVPL-Luciana.xls", "rb").read()
    abas = extracao.abas_texto("IVPL-Luciana.xls", "", conteudo)
    original = llm_extracao.BLOCO_MAX_CHARS
    llm_extracao.BLOCO_MAX_CHARS = 1200   # força ~3 blocos no invoice real
    try:
        r = llm_extracao.extrair("invoice", abas["INVOICE"])
    finally:
        llm_extracao.BLOCO_MAX_CHARS = original
    if r is None:
        print("parte 3 SKIP — quota do Gemini esgotada agora (fallback OpenRouter sem chave)")
        return
    print(f"parte 3 OK — {r['blocos_total']} blocos, {r['blocos_falhos']} falhos, "
          f"{len(r['itens'])} itens, campos={list(r['campos'])}")
    assert r["blocos_total"] >= 2, "deveria ter dividido em blocos"
    cods = [i["codigo"] for i in r["itens"] if i.get("codigo")]
    assert "LU001" in cods and "LU011" in cods, f"itens das pontas ausentes: {cods}"


if __name__ == "__main__":
    parte1_divisao_e_merge()
    parte2_conciliacao_em_escala()
    parte3_extracao_real_em_blocos()
    print("TESTES DE BLOCO/ESCALA CONCLUÍDOS")

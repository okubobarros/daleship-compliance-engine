"""Teste da regra de coerência Invoice × documento de transporte (puro)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import regras_documentais as rd  # noqa: E402


def _codigos(achados):
    return {a["codigo"] for a in achados}


def _riscos(achados):
    return [a for a in achados if a["severidade"] != "info"]


def main() -> None:
    # helpers de parsing
    assert rd.codigo_incoterm("FOB Ningbo") == "FOB"
    assert rd.codigo_incoterm("CIF Santos") == "CIF"
    assert rd.codigo_incoterm("C&F Paranaguá") == "CFR"
    assert rd.codigo_incoterm("sem incoterm aqui") is None
    assert rd.condicao_frete("Freight Prepaid") == "prepaid"
    assert rd.condicao_frete("FRETE A PAGAR") == "collect"
    assert rd.condicao_frete(None) is None
    print("OK regras_documentais — parsing de Incoterm e condição de frete")

    # 1) Incoterm divergente entre Invoice e BL -> crítico, com os 3 campos de decisão
    ach = rd.avaliar({"invoice": {"incoterm": "FOB Ningbo"},
                      "documento_transporte": {"incoterm": "CIF Santos"}})
    assert "INCOTERM_MISMATCH" in _codigos(ach)
    m = next(a for a in ach if a["codigo"] == "INCOTERM_MISMATCH")
    assert m["severidade"] == "critico"
    assert m["evidencia"] and m["por_que_importa"] and m["acao_recomendada"]
    print("OK regras_documentais — Incoterm divergente (FOB×CIF) é crítico e estruturado")

    # 2) FOB (comprador paga) + Freight Prepaid -> incompatível (atenção)
    ach = rd.avaliar({"invoice": {"incoterm": "FOB"},
                      "documento_transporte": {"condicao_frete": "Freight Prepaid"}})
    assert "FREIGHT_RULE" in _codigos(ach)
    assert next(a for a in ach if a["codigo"] == "FREIGHT_RULE")["severidade"] == "atencao"
    print("OK regras_documentais — FOB + Prepaid é incompatível")

    # 3) Tudo presente e coerente -> nenhum RISCO e nenhum 'não avaliado' (nada faltando)
    ach = rd.avaliar({"invoice": {"incoterm": "CIF", "condicao_frete": "Freight Prepaid"},
                      "documento_transporte": {"incoterm": "CIF"}})
    assert ach == [], f"esperado silêncio quando tudo presente e coerente, veio {ach}"
    # FOB + Collect com os dois Incoterms presentes -> coerente, silêncio
    assert rd.avaliar({"invoice": {"incoterm": "FOB"},
                       "documento_transporte": {"incoterm": "FOB", "condicao_frete": "Freight Collect"}}) == []
    print("OK regras_documentais — tudo presente e coerente = silêncio (sem risco, sem 'não avaliado')")

    # 4) Dado ausente NÃO vira risco falso, MAS gera 'não avaliado' explícito (info)
    ach = rd.avaliar({"invoice": {"incoterm": "FOB"}, "documento_transporte": {}})
    assert _riscos(ach) == [], "ausência não pode gerar risco falso"
    na = next(a for a in ach if a["codigo"] == "COERENCIA_NAO_AVALIADA")
    assert na["severidade"] == "info"
    assert "BL" in na["descricao"] and "frete" in na["descricao"]
    assert na["evidencia"] and na["por_que_importa"] and na["acao_recomendada"]

    # sem nenhum dado -> também explícito, nunca silêncio
    ach = rd.avaliar({"invoice": {}, "documento_transporte": {}})
    assert _riscos(ach) == [] and "COERENCIA_NAO_AVALIADA" in _codigos(ach)
    print("OK regras_documentais — dado ausente = 'não avaliado' explícito (info), nunca risco falso nem silêncio")

    # 5) 'Não avaliado' e risco coexistem: mismatch dispara E o frete fica não avaliado
    ach = rd.avaliar({"invoice": {"incoterm": "FOB"}, "documento_transporte": {"incoterm": "CIF"}})
    cods = _codigos(ach)
    assert "INCOTERM_MISMATCH" in cods and "COERENCIA_NAO_AVALIADA" in cods
    na = next(a for a in ach if a["codigo"] == "COERENCIA_NAO_AVALIADA")
    assert "frete" in na["descricao"]  # o que faltou foi a condição de frete
    print("OK regras_documentais — risco e 'não avaliado' coexistem quando cabe")


if __name__ == "__main__":
    main()

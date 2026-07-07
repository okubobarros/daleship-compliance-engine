"""Teste da regra de coerência Invoice × documento de transporte (puro)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import regras_documentais as rd  # noqa: E402


def _codigos(achados):
    return {a["codigo"] for a in achados}


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

    # 3) CIF (vendedor paga) + Prepaid -> coerente, nenhum achado
    assert rd.avaliar({"invoice": {"incoterm": "CIF"},
                       "documento_transporte": {"condicao_frete": "Freight Prepaid"}}) == []
    # FOB + Collect -> coerente
    assert rd.avaliar({"invoice": {"incoterm": "FOB"},
                       "documento_transporte": {"condicao_frete": "Freight Collect"}}) == []
    print("OK regras_documentais — combinações coerentes não geram achado")

    # 4) Dado ausente NÃO vira divergência falsa
    assert rd.avaliar({"invoice": {"incoterm": "FOB"}, "documento_transporte": {}}) == []
    assert rd.avaliar({"invoice": {}, "documento_transporte": {}}) == []
    print("OK regras_documentais — dado ausente não gera falso positivo")


if __name__ == "__main__":
    main()

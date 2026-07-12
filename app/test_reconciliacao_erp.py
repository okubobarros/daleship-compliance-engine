"""Teste do Reconciliation Agent — comparar()/determinar_nivel()/contexto (tudo puro, sem banco)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import reconciliacao_erp as ra  # noqa: E402


def _codigos(achados):
    return {a["codigo"] for a in achados}


def main() -> None:
    catalogo = {
        "SKU-1": {"ncm": "8471.30.19", "descricao": "Notebook"},
        "SKU-2": {"ncm": "8544.42.00", "descricao": "Cabo"},
    }

    # 1) Item da invoice ausente do catálogo -> ERP_ITEM_NAO_CADASTRADO
    ach = ra.comparar([{"codigo": "SKU-9", "descricao": "Item novo", "ncm": "1234.56.78"}], catalogo)
    assert "ERP_ITEM_NAO_CADASTRADO" in _codigos(ach)
    a = next(x for x in ach if x["codigo"] == "ERP_ITEM_NAO_CADASTRADO")
    assert a["severidade"] == "atencao"
    assert a["evidencia"] and a["por_que_importa"] and a["acao_recomendada"]
    print("OK reconciliacao_erp — item ausente do catálogo -> ERP_ITEM_NAO_CADASTRADO")

    # 2) Item presente mas NCM diverge -> ERP_NCM_DIVERGENTE
    ach = ra.comparar([{"codigo": "SKU-1", "descricao": "Notebook", "ncm": "8471.30.99"}], catalogo)
    assert "ERP_NCM_DIVERGENTE" in _codigos(ach)
    print("OK reconciliacao_erp — NCM divergente entre Invoice e ERP -> ERP_NCM_DIVERGENTE")

    # 3) Item presente e coerente -> silêncio
    ach = ra.comparar([{"codigo": "SKU-1", "descricao": "Notebook", "ncm": "8471.30.19"}], catalogo)
    assert ach == [], f"esperado silêncio quando item bate com o catálogo, veio {ach}"
    print("OK reconciliacao_erp — item coerente com o catálogo = silêncio")

    # 4) Item sem código na invoice -> ignorado (não há o que cruzar)
    assert ra.comparar([{"descricao": "sem código"}], catalogo) == []

    # 5) Catálogo vazio -> silêncio total (ausência de ERP não é erro, cai pro nível 2 em conciliar())
    assert ra.comparar([{"codigo": "SKU-1", "ncm": "9999.99.99"}], {}) == []
    print("OK reconciliacao_erp — catálogo vazio = silêncio total (decisão de nível é de conciliar(), não de comparar())")

    # 6) determinar_nivel
    assert ra.determinar_nivel(catalogo) == ra.NIVEL_1_TRIPLE_MATCH
    assert ra.determinar_nivel({}) == ra.NIVEL_2_REGULATORY_MATCH
    assert ra.determinar_nivel(catalogo, "Apenas conferir impostos, ignorar catálogo interno") == ra.NIVEL_2_REGULATORY_MATCH
    print("OK reconciliacao_erp — determinar_nivel: catálogo->N1, sem catálogo->N2, contexto pedindo ignorar->N2")

    # 7) contexto_pede_ignorar_catalogo
    assert ra.contexto_pede_ignorar_catalogo(None) is False
    assert ra.contexto_pede_ignorar_catalogo("") is False
    assert ra.contexto_pede_ignorar_catalogo("Este importador sempre usa o porto de Santos") is False
    assert ra.contexto_pede_ignorar_catalogo("Apenas conferir impostos, ignorar catálogo interno") is True
    assert ra.contexto_pede_ignorar_catalogo("IGNORAR CADASTRO por favor") is True
    print("OK reconciliacao_erp — contexto_pede_ignorar_catalogo reconhece o pedido explícito, ignora o resto")

    # 8) narrativa cobre os 3 níveis com texto não-vazio
    for n in (ra.NIVEL_1_TRIPLE_MATCH, ra.NIVEL_2_REGULATORY_MATCH, ra.NIVEL_3_CONSISTENCIA_INTERNA):
        assert ra.narrativa(n)
    print("OK reconciliacao_erp — narrativa presente para os 3 níveis")


if __name__ == "__main__":
    main()

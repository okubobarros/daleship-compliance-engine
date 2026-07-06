"""Teste unitário do loader de Atributos NPI (puro, sem rede/banco).

Cobre: resolver dinâmico que SÓ aceita _prod (recusa _tre por construção), escolha da
data mais recente, falha explícita em snapshot incompleto, e parse de detalhes (dedup de
definição + valores de domínio) e vínculos (hierárquicos, booleans, vigências).

Uso: mcp-server/.venv/Scripts/python.exe ingestion/test_atributos_loader.py
"""
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from atributos_npi import parse_detalhes, parse_vinculos, resolver_csvs_prod  # noqa: E402

HTML = """
<a href="https://x/detalhes_dos_atributos_20260326_tre.csv">tre det</a>
<a href="https://x/vinculos_dos_atributos_20260326_tre.csv">tre vin</a>
<a href="https://x/detalhes_dos_atributos_20260301_prod.csv">prod velho</a>
<a href="https://x/vinculos_dos_atributos_20260301_prod.csv">prod velho</a>
<a href="https://x/detalhes_dos_atributos_20260415_prod.csv">prod novo</a>
<a href="https://x/vinculos_dos_atributos_20260415_prod.csv">prod novo</a>
"""

DET = [
    ["Código do atributo", "cond", "condado", "Nome", "Apres", "Obj", "Órgãos", "Forma",
     "CodValor", "DescValor", "IniValor", "FimValor", "Máscara", "Tamanho", "IniAtt", "FimAtt"],
    ["ATT_1", "", "", "Classe de risco", "Classe", "Duimp", "MAPA", "Lista estática",
     "01", "Classe I", "06/11/2023", "", "", "2", "06/11/2023", ""],
    ["ATT_1", "", "", "Classe de risco", "Classe", "Duimp", "MAPA", "Lista estática",
     "02", "Classe II", "06/11/2023", "", "", "2", "06/11/2023", ""],
    ["ATT_2", "ATT_1", "", "Detalhe texto", "Detalhe", "Produto", "IBAMA", "Texto",
     "", "", "", "", "", "50", "01/01/2024", ""],
]

VIN = [
    ["Código", "Nome", "Apres", "NCM vinculada", "Modalidade", "Obrig", "Multi", "Ini", "Fim"],
    ["ATT_1", "Classe de risco", "Classe", "0101", "Importação", "true", "false", "30/05/2025", ""],
    ["ATT_2", "Detalhe texto", "Detalhe", "01012100", "Importação", "false", "true", "06/11/2023", ""],
    ["ATT_2", "Detalhe texto", "Detalhe", "28", "Exportação", "false", "false", "06/11/2023", "01/01/2026"],
]


def main() -> None:
    det_url, vin_url, ref = resolver_csvs_prod(HTML)
    assert ref == date(2026, 4, 15), f"deveria escolher a data mais recente, veio {ref}"
    assert "_prod" in det_url and "_prod" in vin_url
    assert "_tre" not in det_url and "_tre" not in vin_url
    print("OK resolver — só _prod, data mais recente, _tre recusado por construção")

    try:
        resolver_csvs_prod('<a href="https://x/detalhes_dos_atributos_20260415_prod.csv">so um</a>')
        raise AssertionError("snapshot incompleto deveria falhar explicitamente")
    except RuntimeError:
        print("OK resolver — snapshot incompleto falha explícito (não carrega metade)")

    defs, dom = parse_detalhes(DET)
    assert len(defs) == 2, f"2 definições dedup, veio {len(defs)}"
    d1 = next(d for d in defs if d["codigo"] == "ATT_1")
    assert d1["orgaos"] == "MAPA" and d1["forma_preenchimento"] == "Lista estática"
    assert d1["vigencia_inicio"] == date(2023, 11, 6)
    d2 = next(d for d in defs if d["codigo"] == "ATT_2")
    assert d2["atributo_condicionante"] == "ATT_1"   # estrutura condicional preservada
    assert len(dom) == 2 and dom[0]["codigo_valor"] == "01" and dom[1]["descricao_valor"] == "Classe II"
    print("OK parse detalhes — dedup de definição, domínio, condicionante, datas")

    vins = parse_vinculos(VIN)
    assert len(vins) == 3
    assert vins[0]["ncm_prefixo"] == "0101" and vins[0]["obrigatorio"] is True
    assert vins[1]["ncm_prefixo"] == "01012100" and vins[1]["multivalorado"] is True
    assert vins[2]["modalidade"] == "Exportação" and vins[2]["vigencia_fim"] == date(2026, 1, 1)
    print("OK parse vínculos — prefixo hierárquico, booleans, vigência de fim")


if __name__ == "__main__":
    main()

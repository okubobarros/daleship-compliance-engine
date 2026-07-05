"""Teste unitário do parser do compilado de Tratamento Administrativo (puro, sem rede).

Valida: síntese de uma linha em prosa citável, filtro por órgão, desambiguação de
identificador quando o mesmo órgão+escopo aparece 2x, e a validação de cabeçalho
(aborta se a estrutura da planilha mudar).

Uso: mcp-server/.venv/Scripts/python.exe ingestion/test_ta_loader.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from loaders import parse_ta_rows  # noqa: E402

CAB1 = ("ÓRGÃO", "ENTREGA: MODELO DE LPCO/ TIPO PRODUTO/CONDIÇÕES",
        "FUNDAMENTAÇÃO LEGAL PARA ATUAÇÃO NA IMPORTAÇÃO", "TIPO DE CONTROLE ADMINISTRATIVO",
        "TIPO DE LPCO", "DETALHAMENTO DO LICENCIAMENTO DO TIPO LPCO", "", "", "", "", "", "",
        "CONFERÊNCIA/INSPEÇÃO DO ANUENTE NA DUIMP", "LINKS MANUAIS")
CAB2 = ("", "", "", "", "", "LPCO DEMANDA CATÁLOGO", "VALIDADE DO LPCO", "TIPO DE CNPJ NO LPCO",
        "LPCO RETIFICÁVEL", "", "", "LPCO PRÉVIO AO EMBARQUE", "", "")

ROWS = [
    ("TRATAMENTOS ADMINISTRATIVOS", "", "", "", "", "", "", "", "", "", "", "", "", ""),  # L0 título
    CAB1,  # L1
    CAB2,  # L2
    ("ANVISA", "Medicamentos", "RDC nº 977/2025", "Monitoramento+DUIMP", "LPCO de taxa",
     "Não", "5 anos", "14 dígitos", "Sempre", "Não", "Sim - valor fixo", "Não se aplica", "Sim", "link"),
    ("MAPA", "Azeite e produtos vegetais", "PORTARIA 531/1994", "Monitoramento+DUIMP", "LPCO de taxa",
     "Sim", "5 anos", "14 dígitos", "Sempre", "Não", "Não", "Não", "Sim", "link"),
    ("ANVISA", "Medicamentos", "RDC nº 977/2025", "Monitoramento+DUIMP", "LPCO de taxa",
     "Não", "5 anos", "14 dígitos", "Sempre", "Não", "Sim", "Não", "Sim", "link"),  # mesmo órgão+escopo
    (None, "", "", "", "", "", "", "", "", "", "", "", "", ""),  # linha vazia -> ignorada
]


def main() -> None:
    unidades = parse_ta_rows(ROWS)
    assert len(unidades) == 3, f"esperado 3 unidades, veio {len(unidades)}"

    anvisa = unidades[0]
    assert anvisa.identificador.startswith("Tratamento Administrativo Importação — ANVISA: Medicamentos")
    assert "Órgão anuente: ANVISA." in anvisa.texto
    assert "Fundamentação legal para atuação na importação: RDC nº 977/2025." in anvisa.texto
    assert "Tipo de LPCO: LPCO de taxa." in anvisa.texto
    # desambiguação da 3ª linha (ANVISA/Medicamentos repetida)
    assert unidades[2].identificador.endswith("(2)"), unidades[2].identificador
    print("OK: síntese em prosa, rótulos por coluna, desambiguação de identificador.")

    # filtro por órgão
    so_mapa = parse_ta_rows(ROWS, filtro_orgaos=["MAPA"])
    assert len(so_mapa) == 1 and so_mapa[0].texto.startswith("Órgão anuente: MAPA.")
    print("OK: filtro_orgaos=['MAPA'] mantém 1.")

    # cabeçalho alterado -> aborta
    ruins = [ROWS[0], ("OUTRA COISA",) + CAB1[1:], CAB2] + list(ROWS[3:])
    try:
        parse_ta_rows(ruins)
        raise AssertionError("deveria abortar com cabeçalho alterado")
    except RuntimeError:
        print("OK: aborta quando o cabeçalho da planilha muda.")


if __name__ == "__main__":
    main()

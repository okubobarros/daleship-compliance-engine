"""Teste unitário do parser das RGI (transformação pura, sem rede/PDF).

Valida que parse_rgi_texto isola as 6 regras (enunciado de 'REGRA N' até 'NOTA
EXPLICATIVA') e que aborta se faltar alguma — nunca indexa RGI parcial.

Uso: mcp-server/.venv/Scripts/python.exe ingestion/test_rgi_loader.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from loaders import parse_rgi_texto  # noqa: E402

# Texto sintético com as 6 regras + notas, no mesmo formato da NESH.
TEXTO = """RGI
REGRAS GERAIS PARA INTERPRETAÇÃO DO SISTEMA HARMONIZADO
REGRA 1
Enunciado da regra um sobre títulos e valor indicativo.
NOTA EXPLICATIVA
Comentário longo da regra um que não deve entrar no enunciado.
REGRA 2
a) enunciado dois-a. b) enunciado dois-b.
NOTA EXPLICATIVA
Comentário da regra dois.
REGRA 3
a) mais específica. b) característica essencial. c) última posição.
NOTA EXPLICATIVA
Comentário três.
REGRA 4
Enunciado da regra quatro, artigos mais semelhantes.
NOTA EXPLICATIVA
Comentário quatro.
REGRA 5
a) estojos. b) embalagens.
NOTA EXPLICATIVA
Comentário cinco.
REGRA 6
Enunciado da regra seis sobre subposições.
NOTA EXPLICATIVA
Comentário seis.
"""


def main() -> None:
    unidades = parse_rgi_texto(TEXTO)
    assert len(unidades) == 6, f"esperado 6 regras, veio {len(unidades)}"
    assert unidades[0].identificador == "RGI Regra 1"
    assert unidades[5].identificador == "RGI Regra 6"
    # o enunciado não deve conter o comentário da NOTA EXPLICATIVA
    assert "Comentário" not in unidades[0].texto
    assert "dois-a" in unidades[1].texto and "dois-b" in unidades[1].texto
    assert "subposições" in unidades[5].texto
    print("OK: parse_rgi_texto isola as 6 regras e exclui as notas explicativas.")

    # deve abortar se faltar uma regra
    try:
        parse_rgi_texto("REGRA 1\nsó a um\nNOTA EXPLICATIVA\n")
        raise AssertionError("deveria ter abortado com RGI incompleta")
    except RuntimeError:
        print("OK: aborta em RGI parcial (nunca indexa incompleta).")


if __name__ == "__main__":
    main()

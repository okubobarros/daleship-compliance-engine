"""Teste unitário do parsing da NCM (transformação pura, sem rede).

Prova que parse_ncm_payload chunka corretamente por código, mesmo com o Portal
Único em parada programada — a coleta real (fetch) fica para fora da janela 01:00–03:00
e exige conferir os nomes de campo contra o payload real na primeira execução.

Uso: mcp-server/.venv/Scripts/python.exe ingestion/test_ncm_loader.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from loaders import parse_ncm_payload  # noqa: E402

# Amostra sintética com a estrutura documentada do endpoint (a conferir na coleta real).
PAYLOAD = {
    "Nomenclaturas": [
        {"Codigo": "0101.21.00", "Descricao": "- Reprodutores de raça pura"},
        {"Codigo": "2204.10.10", "Descricao": "Vinho espumante, em garrafas"},
        {"Codigo": "", "Descricao": "linha sem código — deve ser ignorada"},
    ]
}


def main() -> None:
    unidades = parse_ncm_payload(PAYLOAD)
    assert len(unidades) == 2, f"esperado 2 unidades válidas, veio {len(unidades)}"
    assert unidades[0].identificador == "NCM 0101.21.00"
    assert "Reprodutores" in unidades[0].texto
    assert unidades[1].identificador == "NCM 2204.10.10"
    print("OK: parse_ncm_payload chunka por código e ignora linha sem código.")
    for u in unidades:
        print(" -", u.identificador, "|", u.texto)


if __name__ == "__main__":
    main()

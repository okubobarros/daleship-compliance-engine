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

# Amostra sintética com os NÍVEIS ancestrais (2/4/6/8 díg) para testar a concatenação.
PAYLOAD = {
    "Nomenclaturas": [
        {"Codigo": "01", "Descricao": "Animais vivos."},
        {"Codigo": "0101", "Descricao": "Cavalos, asininos e muares."},
        {"Codigo": "0101.21", "Descricao": "- Cavalos"},
        {"Codigo": "0101.21.00", "Descricao": "-- Reprodutores de raça pura"},
        {"Codigo": "2204.10.10", "Descricao": "Vinho espumante, em garrafas"},
        {"Codigo": "", "Descricao": "linha sem código — deve ser ignorada"},
    ]
}


def main() -> None:
    unidades = parse_ncm_payload(PAYLOAD)
    ids = {u.identificador: u.texto for u in unidades}
    assert "NCM 0101.21.00" in ids
    # descrição hierárquica: junta capítulo > posição > subposição > item
    texto = ids["NCM 0101.21.00"]
    assert "Animais vivos" in texto and "Cavalos" in texto and "Reprodutores" in texto, texto
    assert " > " in texto, "esperado descrição concatenada com ' > '"
    print("OK: parse_ncm_payload concatena a descrição hierárquica (capítulo > ... > item).")
    print("   NCM 0101.21.00 ->", texto)


if __name__ == "__main__":
    main()

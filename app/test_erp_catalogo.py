"""Teste de erp_catalogo.parse_arquivo — CSV/XLSX, casamento flexível de coluna (puro, sem banco)."""
import io
import pathlib
import sys

import openpyxl

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import erp_catalogo as ec  # noqa: E402


def _xlsx_bytes(linhas: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for linha in linhas:
        ws.append(linha)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main() -> None:
    # 1) CSV com cabeçalho em português, colunas fora de ordem
    csv_bytes = "Descrição,SKU,NCM\nNotebook,SKU-1,8471.30.19\nCabo USB,SKU-2,8544.42.00\n".encode("utf-8")
    regs = ec.parse_arquivo("catalogo.csv", "text/csv", csv_bytes)
    assert len(regs) == 2
    r1 = next(r for r in regs if r["codigo_interno"] == "SKU-1")
    assert r1["ncm"] == "8471.30.19" and r1["descricao"] == "Notebook"
    print("OK erp_catalogo — CSV com cabeçalho pt-BR fora de ordem casa as 3 colunas")

    # 2) XLSX com cabeçalho em inglês (part_number/description)
    xlsx_bytes = _xlsx_bytes([
        ["part_number", "description", "ncm"],
        ["PN-100", "Widget", "1234.56.78"],
    ])
    regs = ec.parse_arquivo("catalogo.xlsx", "application/vnd.openxmlformats", xlsx_bytes)
    assert len(regs) == 1 and regs[0]["codigo_interno"] == "PN-100" and regs[0]["ncm"] == "1234.56.78"
    print("OK erp_catalogo — XLSX com cabeçalho em inglês (part_number/description) reconhecido")

    # 3) Sem coluna de código -> [] (não há como identificar o item)
    csv_sem_codigo = "Descrição,NCM\nAlgo,1111.11.11\n".encode("utf-8")
    assert ec.parse_arquivo("sem_codigo.csv", "text/csv", csv_sem_codigo) == []
    print("OK erp_catalogo — sem coluna de código reconhecível = [] (não adivinha)")

    # 4) Arquivo corrompido/formato não suportado -> [] (não quebra o fluxo)
    assert ec.parse_arquivo("arquivo.pdf", "application/pdf", b"nao e uma planilha") == []
    print("OK erp_catalogo — formato não suportado = [] (silêncio, não exceção)")

    # 5) Linha sem código -> pulada; linha com código vazio após strip -> pulada
    csv_linha_vazia = "SKU,NCM\nSKU-A,1111.11.11\n,2222.22.22\n".encode("utf-8")
    regs = ec.parse_arquivo("x.csv", "text/csv", csv_linha_vazia)
    assert len(regs) == 1 and regs[0]["codigo_interno"] == "SKU-A"
    print("OK erp_catalogo — linha sem código é pulada, não vira registro fantasma")


if __name__ == "__main__":
    main()

"""Catálogo mestre do cliente (ERP) — SKU/part number × NCM × descrição.

Base do Reconciliation Agent (app/reconciliacao_erp.py): permite checar se um item da Invoice
está cadastrado no ERP do cliente e se o NCM confere. Aceita CSV/XLSX/XLS "como está" (mesma
fricção mínima de app/extracao.py), casando colunas por nome flexível — cliente não precisa
adaptar a planilha ao nosso formato.

`parse_arquivo` é pura (bytes -> list[dict]), testável sem banco. `importar`/`buscar_por_cliente`
tocam o banco (app/db.py).
"""
from __future__ import annotations

import csv
import io
import json

import openpyxl
import xlrd

import db

# Nomes de coluna aceitos por campo canônico (case/acento-insensível, ver _norm_cabecalho).
_ALIASES = {
    "codigo_interno": {"sku", "codigo", "código", "cod", "part number", "partnumber",
                        "part_number", "codigo interno", "código interno", "codigo_interno"},
    "ncm": {"ncm"},
    "descricao": {"descricao", "descrição", "desc", "produto", "description", "item"},
}


def _norm_cabecalho(valor) -> str:
    s = str(valor or "").strip().lower()
    for de, para in (("á", "a"), ("â", "a"), ("ã", "a"), ("é", "e"), ("ê", "e"),
                     ("í", "i"), ("ó", "o"), ("ô", "o"), ("õ", "o"), ("ú", "u"), ("ç", "c")):
        s = s.replace(de, para)
    return s


def _mapear_colunas(cabecalho: list) -> dict[int, str]:
    """Índice de coluna -> campo canônico, casando por nome flexível. Colunas não reconhecidas
    são ignoradas (não viram campo algum) — cliente pode ter colunas extras no ERP."""
    aliases_norm = {campo: {_norm_cabecalho(a) for a in nomes} for campo, nomes in _ALIASES.items()}
    mapa: dict[int, str] = {}
    for i, valor in enumerate(cabecalho):
        h = _norm_cabecalho(valor)
        for campo, nomes in aliases_norm.items():
            if h in nomes:
                mapa[i] = campo
                break
    return mapa


def _linhas_para_registros(linhas: list[list]) -> list[dict]:
    if not linhas:
        return []
    mapa = _mapear_colunas(linhas[0])
    if "codigo_interno" not in mapa.values():
        return []  # sem coluna de código, não há como identificar o item — nada a importar
    registros = []
    for linha in linhas[1:]:
        reg: dict[str, str | None] = {"codigo_interno": None, "ncm": None, "descricao": None}
        for i, campo in mapa.items():
            if i < len(linha) and linha[i] not in (None, ""):
                reg[campo] = str(linha[i]).strip()
        if reg["codigo_interno"]:
            registros.append(reg)
    return registros


def parse_arquivo(nome: str, mime: str, conteudo: bytes) -> list[dict]:
    """Bytes de CSV/XLSX/XLS -> lista de {codigo_interno, ncm, descricao}. Função pura, sem I/O
    de banco — testável isoladamente. Formato não reconhecido ou sem coluna de código -> []
    (silêncio explícito, nunca acerta por adivinhação)."""
    nome_l = (nome or "").lower()
    try:
        if nome_l.endswith(".xls") and not nome_l.endswith(".xlsx"):
            wb = xlrd.open_workbook(file_contents=conteudo)
            sh = wb.sheet_by_index(0)
            linhas = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
            return _linhas_para_registros(linhas)
        if nome_l.endswith(".xlsx") or "spreadsheet" in mime:
            wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
            ws = wb.worksheets[0]
            linhas = [list(row) for row in ws.iter_rows(values_only=True)]
            wb.close()
            return _linhas_para_registros(linhas)
        if nome_l.endswith(".csv") or "csv" in mime:
            texto = conteudo.decode("utf-8-sig", errors="replace")
            linhas = [row for row in csv.reader(io.StringIO(texto))]
            return _linhas_para_registros(linhas)
    except Exception:
        return []  # arquivo corrompido/ilegível — não quebra o fluxo, só não importa nada
    return []


def importar(cliente_id: str, dossie_id: str | None, nome_arquivo: str, mime: str,
             conteudo: bytes) -> int:
    """Importa o catálogo (upsert por cliente_id+codigo_interno — catálogo mestre é reposto a
    cada upload, não é log). Registra em log_auditoria quantas linhas entraram. Retorna a
    contagem real de linhas importadas (nunca reporta sucesso sem ter de fato inserido)."""
    registros = parse_arquivo(nome_arquivo, mime, conteudo)
    if not registros:
        db_log(dossie_id, "erp_catalogo_importado",
               {"linhas": 0, "nome_arquivo": nome_arquivo, "aviso": "nenhuma linha reconhecida"})
        return 0
    with db.conectar() as conn, conn.cursor() as cur:
        for reg in registros:
            cur.execute(
                "INSERT INTO erp_catalogo_itens (cliente_id, codigo_interno, ncm, descricao, "
                "dossie_origem_id) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (cliente_id, codigo_interno) DO UPDATE SET "
                "ncm=EXCLUDED.ncm, descricao=EXCLUDED.descricao, "
                "dossie_origem_id=EXCLUDED.dossie_origem_id",
                (cliente_id, reg["codigo_interno"], reg["ncm"], reg["descricao"], dossie_id),
            )
        conn.commit()
    db_log(dossie_id, "erp_catalogo_importado", {"linhas": len(registros), "nome_arquivo": nome_arquivo})
    return len(registros)


def buscar_por_cliente(cliente_id: str) -> dict[str, dict]:
    """{codigo_interno: {ncm, descricao}} — lookup O(1) para o Reconciliation Agent. Catálogo
    vazio/inexistente -> {} (silêncio; ausência de ERP não é erro, é um nível de match menor —
    ver app/reconciliacao_erp.py)."""
    with db.conectar() as conn, db._dict_cur(conn) as cur:
        cur.execute("SELECT codigo_interno, ncm, descricao FROM erp_catalogo_itens WHERE cliente_id=%s",
                    (cliente_id,))
        return {r["codigo_interno"]: {"ncm": r["ncm"], "descricao": r["descricao"]} for r in cur.fetchall()}


def db_log(dossie_id: str | None, evento: str, detalhe: dict) -> None:
    """Igual a processamento._log, sem importar processamento (evita import circular:
    processamento ainda não depende de erp_catalogo). dossie_id pode ser None só em teste manual
    fora de um dossiê real — nunca no fluxo real (importação sempre ocorre dentro de um upload)."""
    if dossie_id is None:
        return
    with db.conectar() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO log_auditoria (dossie_id, evento, detalhe) VALUES (%s, %s, %s)",
                    (dossie_id, evento, json.dumps(detalhe)))
        conn.commit()

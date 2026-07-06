"""Busca híbrida SÍNCRONA para o app (Streamlit é sync).

Reusa o embedder Voyage e o MESMO limiar calibrado (`DISTANCIA_MAXIMA`) do rag_search do
mcp-server — uma só fonte de verdade para o grounding. Nunca cita sem chunk de origem:
retorna None quando nada passa do limiar.
"""
import asyncio
import pathlib
import sys

import psycopg2
import psycopg2.extras

from config import DATABASE_URL

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
from embeddings import get_embedder  # noqa: E402
from grounding import DISTANCIA_MAXIMA  # noqa: E402  (mesmo limiar do rag_search, sem puxar o pacote db)


def _emb_query(query: str):
    emb = get_embedder()
    if not getattr(emb, "disponivel", False):
        return None
    # embedder.embed é async; roda numa loop própria (sem pool asyncpg envolvido = seguro).
    return asyncio.run(emb.embed([query], input_type="query"))[0]


def buscar_norma(query: str, tipo_documento: str | None = None) -> dict | None:
    """Melhor norma para a query (lexical + semântica com limiar). None = sem base localizada."""
    vetor = _emb_query(query)
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if vetor is not None:
            lit = "[" + ",".join(str(x) for x in vetor) + "]"
            cur.execute(
                "SELECT id, identificador, texto, fonte_url, tipo_documento, orgao, "
                "       embedding <=> %s::vector AS distancia "
                "FROM normas WHERE data_vigencia_fim IS NULL AND embedding IS NOT NULL "
                "  AND (%s::text IS NULL OR tipo_documento = %s) "
                "  AND embedding <=> %s::vector < %s "
                "ORDER BY embedding <=> %s::vector LIMIT 1",
                (lit, tipo_documento, tipo_documento, lit, DISTANCIA_MAXIMA, lit),
            )
            row = cur.fetchone()
            if row:
                return dict(row)
        # fallback lexical (útil p/ código/número exato; ex.: NCM)
        cur.execute(
            "SELECT id, identificador, texto, fonte_url, tipo_documento, orgao, NULL AS distancia "
            "FROM normas WHERE data_vigencia_fim IS NULL "
            "  AND (%s::text IS NULL OR tipo_documento = %s) "
            "  AND (texto ILIKE '%%'||%s||'%%' OR identificador ILIKE '%%'||%s||'%%') LIMIT 1",
            (tipo_documento, tipo_documento, query, query),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def melhores_precedentes(descricoes: list[str], tipo_documento: str = "solucao_consulta") -> list[dict | None]:
    """Melhor precedente por descrição de item. Embeda TODAS as descrições numa única chamada
    Voyage (poupa rate limit) e roda a busca semântica com o limiar calibrado por item.
    Retorna lista alinhada a `descricoes` (None onde nada passa do limiar)."""
    emb = get_embedder()
    if not descricoes or not getattr(emb, "disponivel", False):
        return [None] * len(descricoes)
    vetores = asyncio.run(emb.embed(descricoes, input_type="query"))
    resultados: list[dict | None] = []
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for v in vetores:
            lit = "[" + ",".join(str(x) for x in v) + "]"
            cur.execute(
                "SELECT id, identificador, texto, fonte_url, tipo_documento, orgao, "
                "       embedding <=> %s::vector AS distancia "
                "FROM normas WHERE data_vigencia_fim IS NULL AND embedding IS NOT NULL "
                "  AND tipo_documento = %s AND embedding <=> %s::vector < %s "
                "ORDER BY embedding <=> %s::vector LIMIT 1",
                (lit, tipo_documento, lit, DISTANCIA_MAXIMA, lit),
            )
            row = cur.fetchone()
            resultados.append(dict(row) if row else None)
    return resultados


def anuencia_por_ncm(codigo: str) -> dict | None:
    """Anuência via busca LEXICAL do código NCM no compilado de Tratamento Administrativo.

    Muito mais confiável que semântica para isto: as linhas do TA enumeram os NCMs sob
    controle, então o código bate exato — ou nada (abstém). Evita o erro de órgão que a
    busca semântica cometia (ex.: medicamento -> MAPA). Tenta 8 dígitos e depois 6 (posição
    + subposição); não usa 4 dígitos para não colidir com números de lei/data.
    """
    digitos = "".join(ch for ch in codigo if ch.isdigit())
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for pref in (digitos, digitos[:6]):
            if len(pref) < 6:
                continue
            cur.execute(
                "SELECT id, identificador, texto, fonte_url, tipo_documento, orgao "
                "FROM normas WHERE tipo_documento = 'tratamento_administrativo' "
                "  AND data_vigencia_fim IS NULL "
                "  AND replace(replace(texto,'.',''),' ','') ILIKE '%%'||%s||'%%' LIMIT 1",
                (pref,),
            )
            row = cur.fetchone()
            if row:
                return dict(row)
    return None


def tratamento_por_orgao(orgao: str) -> dict | None:
    """Uma norma de Tratamento Administrativo do órgão (para citar como referência no flag
    regulatório). O anuente está no identificador ('... — ANATEL: ...')."""
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, identificador, texto, fonte_url, tipo_documento, orgao "
            "FROM normas WHERE tipo_documento = 'tratamento_administrativo' "
            "  AND data_vigencia_fim IS NULL AND identificador ILIKE '%%'||%s||'%%' LIMIT 1",
            (orgao,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def descricao_ncm(codigo: str) -> str | None:
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT texto FROM normas WHERE tipo_documento = 'NCM' AND identificador = %s "
            "AND data_vigencia_fim IS NULL LIMIT 1",
            (f"NCM {codigo}",),
        )
        row = cur.fetchone()
        return row[0] if row else None

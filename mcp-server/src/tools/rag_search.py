"""Busca híbrida na base normativa (`normas`): lexical + semântica combinadas.

Princípio não negociável (CLAUDE.md §4.1): nunca retorna afirmação sem chunk de origem.
Se nada é recuperado, sinaliza "sem base normativa localizada" — nunca inventa.

Híbrido de verdade: a busca lexical (ILIKE — pega número de IN/NCM/código exato) e a
semântica (pgvector `<=>` sobre embeddings voyage-law-2) rodam ambas e os resultados são
combinados por id, nunca uma substitui a outra. Se não houver chave Voyage (NullEmbedder)
ou nenhuma norma com embedding ainda, a parte semântica simplesmente não contribui e a
busca degrada para lexical — com segurança, sem jamais fabricar fonte.
"""
from __future__ import annotations

from embeddings import get_embedder
from grounding import DISTANCIA_MAXIMA  # limiar calibrado (fonte única de verdade)
from db.connection import get_pool

K = 5

_COLUNAS = (
    "id, orgao, tipo_documento, identificador, texto, fonte_url, "
    "data_vigencia_inicio, data_vigencia_fim"
)


async def buscar_norma(query: str, orgao: str | None = None) -> dict:
    pool = await get_pool()
    resultados: dict[str, dict] = {}

    # --- Parte lexical (sempre) ---
    sql_lex = f"""
        SELECT {_COLUNAS}
        FROM normas
        WHERE data_vigencia_fim IS NULL
          AND texto ILIKE '%' || $1 || '%'
          AND ($2::text IS NULL OR orgao = $2)
        ORDER BY data_vigencia_inicio DESC
        LIMIT {K}
    """
    async with pool.acquire() as conn:
        for row in await conn.fetch(sql_lex, query, orgao):
            d = dict(row)
            d["match"] = "lexical"
            resultados[str(d["id"])] = d

        # --- Parte semântica (só se houver embedder disponível e embeddings na base) ---
        embedder = get_embedder()
        if getattr(embedder, "disponivel", False):
            vetores = await embedder.embed([query], input_type="query")
            query_emb = vetores[0]
            if query_emb is not None:
                emb_literal = "[" + ",".join(str(x) for x in query_emb) + "]"
                sql_sem = f"""
                    SELECT {_COLUNAS}, embedding <=> $1::vector AS distancia
                    FROM normas
                    WHERE data_vigencia_fim IS NULL
                      AND embedding IS NOT NULL
                      AND ($2::text IS NULL OR orgao = $2)
                      AND embedding <=> $1::vector < {DISTANCIA_MAXIMA}
                    ORDER BY embedding <=> $1::vector
                    LIMIT {K}
                """
                for row in await conn.fetch(sql_sem, emb_literal, orgao):
                    d = dict(row)
                    chave = str(d["id"])
                    if chave in resultados:
                        resultados[chave]["match"] = "lexical+semantica"
                    else:
                        d["match"] = "semantica"
                        resultados[chave] = d

    if not resultados:
        return {"encontrado": False, "motivo": "sem base normativa localizada"}

    return {"encontrado": True, "resultados": list(resultados.values())}

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
from db.connection import get_pool

K = 5

# Limiar de distância de cosseno (pgvector `<=>`) acima do qual um vizinho semântico é
# considerado IRRELEVANTE e descartado — sem isso, a busca vetorial sempre devolve os K
# mais próximos e uma query fora do domínio "citaria" a norma menos distante (fura o
# grounding).
# CALIBRADO com o golden eval set (eval/run_eval.py) sobre a base real de comex (2026-07-05):
# positivos no-domínio até dist 0.494, negativos fora do domínio a partir de 0.518 — folga
# fina (+0.024). 0.51 = ponto médio da folga: 100% no golden set (11/11 positivos recuperados,
# 6/6 negativos rejeitados) vs 88% no antigo 0.65 (que deixava passar 'bolo de cenoura' 0.518).
# Como a folga é estreita, favorecemos rejeitar (citação errada > miss). Reavaliar ao crescer
# o golden set / adicionar fontes.
DISTANCIA_MAXIMA = 0.51

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

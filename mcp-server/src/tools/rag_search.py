from db.connection import get_pool


async def buscar_norma(query: str, orgao: str | None = None) -> dict:
    """Busca híbrida (lexical) na tabela `normas`, restrita a normas vigentes.

    A busca semântica (embedding) entra quando o pipeline de ingestão (Semana 1)
    já tiver populado a coluna `embedding` — por enquanto a base está vazia, então
    esta função já sinaliza "sem base normativa localizada" em vez de inventar,
    conforme o princípio não negociável de grounding do CLAUDE.md."""
    pool = await get_pool()

    sql = """
        SELECT id, orgao, tipo_documento, identificador, texto, fonte_url,
               data_vigencia_inicio, data_vigencia_fim
        FROM normas
        WHERE data_vigencia_fim IS NULL
          AND texto ILIKE '%' || $1 || '%'
          AND ($2::text IS NULL OR orgao = $2)
        ORDER BY data_vigencia_inicio DESC
        LIMIT 5
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, query, orgao)

    if not rows:
        return {"encontrado": False, "motivo": "sem base normativa localizada"}

    return {
        "encontrado": True,
        "resultados": [dict(row) for row in rows],
    }

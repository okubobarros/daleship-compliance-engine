import os

import asyncpg

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Retorna o pool de conexão com o Postgres (Supabase), criando na primeira chamada.

    Requer a variável de ambiente DATABASE_URL (connection string direta do Supabase,
    Settings > Database > Connection string — não confundir com NEXT_PUBLIC_SUPABASE_URL,
    que é a URL da API REST, não do Postgres)."""
    global _pool
    if _pool is None:
        database_url = os.environ["DATABASE_URL"]
        _pool = await asyncpg.create_pool(database_url)
    return _pool

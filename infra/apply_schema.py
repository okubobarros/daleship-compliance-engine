"""Aplica infra/schema_fase1.sql no Postgres do Supabase e verifica o resultado.

Uso: rodar da raiz do repo com o venv do mcp-server:
    mcp-server/.venv/Scripts/python.exe infra/apply_schema.py
"""
import asyncio
import os
import pathlib

import asyncpg
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SCHEMA_PATH = ROOT / "infra" / "schema_fase1.sql"
TABELAS_ESPERADAS = {"normas", "dossies", "apontamentos", "correcoes", "log_auditoria"}


async def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(database_url)
    try:
        server_version = await conn.fetchval("SELECT version()")
        print("Conectado:", server_version.split(",")[0])

        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        await conn.execute(sql)
        print("Schema aplicado sem erro.")

        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        tabelas = {r["table_name"] for r in rows}
        faltando = TABELAS_ESPERADAS - tabelas
        print("Tabelas public:", sorted(tabelas))
        if faltando:
            print("FALTANDO:", sorted(faltando))
        else:
            print("Todas as tabelas esperadas existem.")

        has_vector = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )
        print("Extensão pgvector instalada:", has_vector)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

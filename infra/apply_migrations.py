"""Runner de migrations formais (append-only, rastreado em schema_migrations).

Aplica, em ordem, os arquivos infra/migrations/*.sql que ainda não constam na tabela
`schema_migrations`. Idempotente: rodar de novo não reaplica o que já foi aplicado.

Uso: mcp-server/.venv/Scripts/python.exe infra/apply_migrations.py
"""
import asyncio
import os
import pathlib

import asyncpg
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent / "migrations"


async def main() -> None:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                versao TEXT PRIMARY KEY,
                aplicada_em TIMESTAMPTZ DEFAULT now()
            )
            """
        )
        aplicadas = {
            r["versao"] for r in await conn.fetch("SELECT versao FROM schema_migrations")
        }
        arquivos = sorted(MIGRATIONS_DIR.glob("*.sql"))
        pendentes = [f for f in arquivos if f.stem not in aplicadas]

        if not pendentes:
            print("Nenhuma migration pendente.")
            return

        for arquivo in pendentes:
            sql = arquivo.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (versao) VALUES ($1)", arquivo.stem
                )
            print(f"Aplicada: {arquivo.stem}")

        # Verificação: tipo/dimensão da coluna embedding (pgvector guarda a dim direto no typmod;
        # format_type dá o tipo legível, ex.: 'vector(1024)').
        tipo = await conn.fetchval(
            """
            SELECT format_type(atttypid, atttypmod)
            FROM pg_attribute
            WHERE attrelid = 'normas'::regclass AND attname = 'embedding'
            """
        )
        print(f"Tipo atual de normas.embedding: {tipo}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

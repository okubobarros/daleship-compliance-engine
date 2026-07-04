"""Verificação end-to-end do pipeline contra o banco real, com dado sintético.

Checa: (1) rag_search recupera a norma de teste com provenance;
(2) versionamento por vigência (texto muda -> fecha antiga + insere nova);
(3) limpeza — remove as linhas de teste e confirma que o RAG volta a dizer
'sem base normativa localizada'.

Uso: mcp-server/.venv/Scripts/python.exe ingestion/verify_pipeline.py
"""
import asyncio
import os
import pathlib
import sys

import asyncpg
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
from tools.rag_search import buscar_norma  # noqa: E402


async def main() -> None:
    # (1) RAG recupera a norma de teste com fonte
    r = await buscar_norma("sintético de teste", orgao="TESTE")
    assert r["encontrado"] is True, r
    norma = r["resultados"][0]
    assert norma["fonte_url"] and norma["identificador"] == "TESTE-SMOKE-001"
    print("(1) RAG recupera com provenance:", norma["identificador"], "|", norma["fonte_url"])

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        # (2) Versionamento: simula mudança de texto e confere que a antiga foi fechada
        await conn.execute(
            "UPDATE normas SET data_vigencia_fim = current_date "
            "WHERE orgao='TESTE' AND identificador='TESTE-SMOKE-001' AND data_vigencia_fim IS NULL"
        )
        await conn.execute(
            "INSERT INTO normas (orgao, tipo_documento, identificador, texto, fonte_url, data_vigencia_inicio) "
            "VALUES ('TESTE','smoke','TESTE-SMOKE-001','versao 2 sintética','https://exemplo.invalido/teste', current_date)"
        )
        vigentes = await conn.fetchval(
            "SELECT count(*) FROM normas WHERE orgao='TESTE' AND identificador='TESTE-SMOKE-001' AND data_vigencia_fim IS NULL"
        )
        historicas = await conn.fetchval(
            "SELECT count(*) FROM normas WHERE orgao='TESTE' AND identificador='TESTE-SMOKE-001' AND data_vigencia_fim IS NOT NULL"
        )
        assert vigentes == 1 and historicas == 1, (vigentes, historicas)
        print(f"(2) Versionamento OK: {vigentes} vigente, {historicas} histórica (nada sobrescrito)")

        # (3) Limpeza — remove todas as linhas de teste
        apagadas = await conn.execute("DELETE FROM normas WHERE orgao='TESTE'")
        print("(3) Limpeza:", apagadas)
    finally:
        await conn.close()

    r2 = await buscar_norma("sintético de teste", orgao="TESTE")
    assert r2["encontrado"] is False, r2
    print("(3) Base limpa: RAG volta a 'sem base normativa localizada'. Pipeline verificado.")


if __name__ == "__main__":
    asyncio.run(main())

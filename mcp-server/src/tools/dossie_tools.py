import json
import uuid

from db.connection import get_pool


async def criar_dossie(cliente_id: str, dados_extraidos: dict) -> dict:
    pool = await get_pool()
    dossie_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO dossies (id, cliente_id, dados_extraidos, status)
            VALUES ($1, $2, $3, 'em_analise')
            """,
            dossie_id,
            cliente_id,
            json.dumps(dados_extraidos),
        )
        await conn.execute(
            """
            INSERT INTO log_auditoria (dossie_id, evento, detalhe)
            VALUES ($1, 'dossie_criado', $2)
            """,
            dossie_id,
            json.dumps({"cliente_id": cliente_id}),
        )
    return {"dossie_id": dossie_id, "status": "em_analise"}


async def obter_dossie(dossie_id: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM dossies WHERE id = $1", dossie_id)
    if row is None:
        return {"encontrado": False}
    return {"encontrado": True, "dossie": dict(row)}

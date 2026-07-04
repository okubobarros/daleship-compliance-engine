from mcp.server import Server
from mcp.server.stdio import stdio_server

from tools.rag_search import buscar_norma
from tools.siscomex_client import consultar_ncm_siscomex
from tools.dossie_tools import criar_dossie, obter_dossie

server = Server("compliance-engine")


@server.tool()
async def buscar_norma_regulatoria(query: str, orgao: str | None = None) -> dict:
    """Busca trecho normativo relevante na base indexada (RAG),
    retornando texto, fonte e data de vigência."""
    return await buscar_norma(query, orgao)


@server.tool()
async def consultar_ncm(codigo_ncm: str, chave_acesso: str) -> dict:
    """Consulta dados de NCM no Portal Único Siscomex usando a
    chave de acesso fornecida pelo cliente final."""
    return await consultar_ncm_siscomex(codigo_ncm, chave_acesso)


@server.tool()
async def registrar_dossie(cliente_id: str, dados_extraidos: dict) -> dict:
    """Cria um dossiê de processo de importação a partir dos dados
    extraídos dos documentos (Invoice, Packing List, B/L)."""
    return await criar_dossie(cliente_id, dados_extraidos)


@server.tool()
async def consultar_dossie(dossie_id: str) -> dict:
    """Consulta um dossiê já registrado pelo id."""
    return await obter_dossie(dossie_id)


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

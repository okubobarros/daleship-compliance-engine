from auth.pucomex_auth import autenticar


async def consultar_ncm_siscomex(codigo_ncm: str, chave_acesso: str) -> dict:
    """Consulta dados de NCM no Portal Único Siscomex.

    Ainda não implementado de verdade: depende de um certificado digital ICP-Brasil
    de teste e de a trading gerar uma Chave de Acesso no ambiente de validação
    (val.portalunico.siscomex.gov.br) — ver docs/MCP_SISCOMEX_INTEGRATION.md, seção 5,
    item 5. Não mockar a autenticação por certificado; aguardar acesso real."""
    raise NotImplementedError(
        "consultar_ncm_siscomex requer certificado digital de teste e Chave de Acesso "
        "da trading no ambiente de validação PUCOMEX — ainda não configurado."
    )

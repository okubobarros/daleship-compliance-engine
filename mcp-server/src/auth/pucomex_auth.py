import httpx

PUCOMEX_BASE_URL = "https://val.portalunico.siscomex.gov.br"  # ambiente de validação


async def autenticar(chave_acesso: str, role_type: str, cert_path: str, cert_key: str) -> dict:
    """Autentica no PUCOMEX usando certificado digital + chave de acesso
    do cliente (gerada por ele mesmo no portal)."""
    async with httpx.AsyncClient(cert=(cert_path, cert_key)) as client:
        response = await client.post(
            f"{PUCOMEX_BASE_URL}/portal/api/autenticar",
            headers={"Role-Type": role_type},
        )
        response.raise_for_status()
        return {
            "token": response.headers["Set-Token"],
            "csrf_token": response.headers["X-CSRF-Token"],
            "expiration": response.headers["X-CSRF-Expiration"],
        }

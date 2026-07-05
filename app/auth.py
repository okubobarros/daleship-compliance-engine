"""Autenticação simples (usuário/senha) para o time da trading.

Sem registro público, sem identidade/marca — isso fica para depois da demo validada.
Credenciais vêm de APP_USERS no .env (formato "usuario:senha,usuario2:senha2"); na ausência,
um usuário de demonstração. cliente_id é derivado do usuário (uuid5) para isolar os dossiês
por cliente de forma estável entre reinícios (Guardrail 3: isolamento por cliente_id).
"""
import os
import uuid

_NS = uuid.UUID("6d9f1e5a-0000-4000-8000-000000000001")


def _usuarios() -> dict[str, str]:
    bruto = os.environ.get("APP_USERS", "").strip()
    if not bruto:
        return {"trading": "demo"}  # credencial de demonstração (trocar via APP_USERS)
    pares = {}
    for item in bruto.split(","):
        if ":" in item:
            u, s = item.split(":", 1)
            pares[u.strip()] = s.strip()
    return pares


def autenticar(usuario: str, senha: str) -> str | None:
    """Retorna o cliente_id (uuid estável) se as credenciais baterem, senão None."""
    usuarios = _usuarios()
    if usuario in usuarios and senha == usuarios[usuario]:
        return str(uuid.uuid5(_NS, usuario))
    return None

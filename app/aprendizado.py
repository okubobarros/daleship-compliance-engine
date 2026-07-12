"""Loop de aprendizado mínimo — lookup de correção anterior, NÃO fine-tuning/retraining.

Exceção aprovada em 09/07/2026 pelo dono do produto (CLAUDE.md §8): a versão construída aqui é
deliberadamente rasa — busca a correção humana mais recente para o mesmo cliente + mesmo tipo de
achado (`apontamentos.codigo`, migration 0009) e sugere aplicá-la de novo. NÃO retreina embedding,
NÃO ajusta prompt, NÃO faz few-shot automático (ver docs/STAKEHOLDER_VISION.md:66 — "não façam
isso cedo demais"). Isolamento entre clientes é essencial: nunca sugerir a correção de um cliente
para outro, mesmo que o `codigo` do achado seja idêntico.
"""
from __future__ import annotations

import db


def buscar_correcao_anterior(cliente_id: str, codigo: str) -> dict | None:
    """Última correção HUMANA real (valor_corrigido preenchido — um simples "aceitar" não conta,
    só correção de fato) para o mesmo cliente + mesmo tipo de achado. None quando não há
    histórico (silêncio — ausência de dado não vira suposição, mesma lição de sempre)."""
    if not cliente_id or not codigo:
        return None
    with db.conectar() as conn, db._dict_cur(conn) as cur:
        cur.execute(
            "SELECT c.valor_sugerido, c.valor_corrigido, c.justificativa_analista, c.criado_em "
            "FROM correcoes c "
            "JOIN apontamentos a ON a.id = c.apontamento_id "
            "JOIN dossies d ON d.id = a.dossie_id "
            "WHERE d.cliente_id = %s AND a.codigo = %s AND c.valor_corrigido IS NOT NULL "
            "ORDER BY c.criado_em DESC LIMIT 1",
            (cliente_id, codigo),
        )
        return cur.fetchone()


def sugestao_texto(correcao: dict | None) -> str | None:
    """Frase pronta para anexar ao por_que_importa de um novo apontamento do mesmo tipo/cliente.
    None quando não há correção anterior — não anexa nada (silêncio, nunca uma suposição)."""
    if not correcao:
        return None
    data = correcao["criado_em"].strftime("%d/%m/%Y") if correcao.get("criado_em") else "uma vez"
    de = correcao.get("valor_sugerido") or "o valor sugerido"
    para = correcao["valor_corrigido"]
    return f"Da última vez ({data}) você corrigiu de '{de}' para '{para}' — aplicar de novo?"

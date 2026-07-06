"""Nó 3 — Verificação e cruzamento: dados extraídos × exigências recuperadas -> lacunas.

Contrato:
    entrada: state['dados_extraidos'], state['chunks_recuperados']
    saída:   {'lacunas': [Lacuna, ...]}

Implementação mínima real (não só stub): checa presença dos campos mínimos do dossiê.
A verificação plena da Fase 2 (cruzar com exigência normativa recuperada e com precedente
— tabela `precedentes`) entra quando houver base ingerida. Determinístico e testável —
mesma disciplina dos Code nodes do workflow n8n da Fase 1 (nunca verificação via prompt).
"""
from __future__ import annotations

from ..state import EstadoDossie

# Campos mínimos de um dossiê da Fase 2 (PRD RF02). Ajustar quando o schema real fechar.
CAMPOS_MINIMOS = ("ingrediente_ativo", "formulacao")


def no_verificacao(state: EstadoDossie) -> dict:
    """Identifica lacunas: campos mínimos ausentes + (futuro) inconsistências contra a base."""
    dados = state.get("dados_extraidos") or {}
    lacunas = [
        {
            "campo": campo,
            "descricao": f"Campo obrigatório '{campo}' ausente no dossiê.",
            "chunk_ids": [],  # Nó 5 tentará ancorar em norma recuperada; sem chunk = abstém
        }
        for campo in CAMPOS_MINIMOS
        if not dados.get(campo)
    ]
    return {"lacunas": lacunas}

"""Nó 6 — Registro de correção e log: persiste a decisão humana (append-only).

Contrato:
    entrada: state['apontamentos'], state['revisao'] (OBRIGATÓRIO — vem do resume
             pós-interrupt; sem ele o nó RECUSA executar)
    saída:   {'eventos_log': [...], 'status': 'concluido'}

Regras herdadas da Fase 1:
- NUNCA executa sem revisão humana no estado — o interrupt do grafo garante a pausa, e
  este guard garante em profundidade (defesa dupla; CLAUDE.md §4.2 'nunca decidir sozinho').
- Log é APPEND-ONLY: só INSERT em log_auditoria (o schema da Fase 2 ainda reforça com
  trigger que bloqueia UPDATE/DELETE no banco).
- Correção estruturada (valor sugerido, corrigido, justificativa, autor) — o ativo de dado
  proprietário (tabela `correcoes`); ver `app/db.py::registrar_revisao` da Fase 1.

Persistência via injeção de dependência (`gravar`) para o nó ser testável sem banco —
o default apenas acumula em `eventos_log` (espelho do que iria a log_auditoria).
"""
from __future__ import annotations

from typing import Callable

from ..state import EstadoDossie


def no_registro_correcao(state: EstadoDossie, gravar: Callable[[dict], None] | None = None) -> dict:
    """Grava correções estruturadas + eventos de auditoria. Recusa executar sem revisão."""
    revisao = state.get("revisao")
    if not revisao:
        raise RuntimeError(
            "Nó 6 recusado: nenhum resultado é final sem revisão humana "
            "(state['revisao'] ausente — o interrupt não foi honrado?)."
        )
    eventos = list(state.get("eventos_log") or [])  # append-only: nunca remove/reescreve
    for correcao in revisao:
        evento = {"evento": "apontamento_revisado", "detalhe": dict(correcao)}
        eventos.append(evento)
        if gravar is not None:
            gravar(evento)  # produção: INSERT em correcoes + log_auditoria (nunca UPDATE)
    eventos.append({"evento": "dossie_concluido", "detalhe": {"apontamentos": len(state.get("apontamentos") or [])}})
    return {"eventos_log": eventos, "status": "concluido"}

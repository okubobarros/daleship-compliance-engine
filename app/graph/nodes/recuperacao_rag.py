"""Nó 2 — Recuperação normativa (RAG híbrido): dados extraídos -> chunks citáveis.

Contrato:
    entrada: state['dados_extraidos'] (+ state['setor'])
    saída:   {'chunks_recuperados': [ChunkRecuperado, ...]}

STUB — a implementar portando o padrão validado na Fase 1:
- `mcp-server/src/tools/rag_search.py`: busca HÍBRIDA (lexical + semântica COMBINADAS,
  nunca uma substituindo a outra) com limiar de distância calibrado por golden eval set
  (`mcp-server/src/grounding.py::DISTANCIA_MAXIMA` — fonte única de verdade).
- `mcp-server/src/embeddings.py`: voyage-law-2 (1024 dims), lotes por orçamento de tokens,
  throttle por janela deslizante de TPM.
- Lição da anuência Fase 1: para casar CÓDIGO exato (nº de IN, NCM), a via lexical é a
  confiável — semântica deriva de órgão. Recuperar pelos dois caminhos e marcar `via`.

O chunk carrega orgao/identificador/vigência (metadados obrigatórios, ARCHITECTURE §4) —
o Nó 5 só pode citar o que sair daqui.
"""
from __future__ import annotations

from ..state import EstadoDossie


def no_recuperacao_rag(state: EstadoDossie) -> dict:
    """Recupera chunks normativos relevantes. Stub: preserva `chunks_recuperados` já
    injetados no estado (fixtures de teste); nunca fabrica chunks."""
    return {"chunks_recuperados": state.get("chunks_recuperados") or []}

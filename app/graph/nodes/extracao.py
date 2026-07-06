"""Nó 1 — Extração: documento do dossiê -> JSON estruturado.

Contrato:
    entrada: state['documento_bruto'] (texto já extraído dos arquivos)
    saída:   {'dados_extraidos': {...}, 'tokens_consumidos': {'extracao': N}}

STUB — a implementar portando o padrão validado na Fase 1:
- `app/llm_extracao.py`: LLM com responseSchema JSON forçado, retry/backoff com retryDelay,
  fallback heurístico quando o LLM está indisponível, e prompt endurecido ("itens = só
  linhas de mercadoria, nunca cabeçalho/CNPJ/totais" — lição do flash-lite).
- Campos da Fase 2 (defensivos/bioinsumos): ingrediente_ativo, formulação, dados de
  eficácia/toxicologia (ver PRD RF02) — definir schema quando a Fase 2 começar.
- Falha de extração NUNCA é silenciosa: sinalizar em `eventos_log` (lição: falha parcial
  gerava divergência falsa na Fase 1).
"""
from __future__ import annotations

from ..state import EstadoDossie


def no_extracao(state: EstadoDossie) -> dict:
    """Extrai campos estruturados do dossiê. Stub: passa adiante `dados_extraidos` já
    presentes no estado (permite injetar fixtures nos testes) sem inventar nada."""
    return {
        "dados_extraidos": state.get("dados_extraidos") or {},
        "tokens_consumidos": {**state.get("tokens_consumidos", {}), "extracao": 0},
    }

"""Montagem do grafo LangGraph (Fase 2) — 6 nós + interrupt de revisão humana.

Fluxo (ARCHITECTURE §2):
    extracao -> recuperacao_rag -> verificacao -> classificacao_orgao -> justificativa
    -> [INTERRUPT: revisão humana obrigatória] -> registro_correcao -> END

O interrupt NÃO É OPCIONAL nem contornável por configuração (Guardrail 5): nenhum resultado
é final sem humano. Defesa em profundidade: além do interrupt, o próprio Nó 6 recusa rodar
sem `state['revisao']` (ver registro_correcao.py).

O import do langgraph é lazy (dentro de montar_grafo) de propósito: o scaffold é trabalho
antecipado — os nós são testáveis isoladamente sem a dependência instalada. Quando a Fase 2
começar: `pip install langgraph` e um checkpointer Postgres (mesma instância do resto).
"""
from __future__ import annotations

from .nodes import (
    no_classificacao_orgao,
    no_extracao,
    no_justificativa,
    no_recuperacao_rag,
    no_registro_correcao,
    no_verificacao,
)
from .state import EstadoDossie

# Nome do nó gatado pelo interrupt — exportado para os testes garantirem a pausa.
NO_POS_REVISAO = "registro_correcao"


def montar_grafo(checkpointer=None):
    """Compila o grafo com interrupt ANTES do registro (pausa para revisão humana).

    Uso (quando a Fase 2 ativar):
        grafo = montar_grafo(checkpointer=PostgresSaver(...))
        config = {"configurable": {"thread_id": dossie_id}}
        grafo.invoke(estado_inicial, config)          # roda até o interrupt (status=revisao_humana)
        # ... humano revisa na UI, produz state['revisao'] ...
        grafo.update_state(config, {"revisao": correcoes})
        grafo.invoke(None, config)                     # resume: executa registro_correcao
    """
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "langgraph não instalado — scaffold da Fase 2. `pip install langgraph` ao ativar."
        ) from e

    g = StateGraph(EstadoDossie)
    g.add_node("extracao", no_extracao)
    g.add_node("recuperacao_rag", no_recuperacao_rag)
    g.add_node("verificacao", no_verificacao)
    g.add_node("classificacao_orgao", no_classificacao_orgao)
    g.add_node("justificativa", no_justificativa)
    g.add_node(NO_POS_REVISAO, no_registro_correcao)

    g.set_entry_point("extracao")
    g.add_edge("extracao", "recuperacao_rag")
    g.add_edge("recuperacao_rag", "verificacao")
    g.add_edge("verificacao", "classificacao_orgao")
    g.add_edge("classificacao_orgao", "justificativa")
    g.add_edge("justificativa", NO_POS_REVISAO)
    g.add_edge(NO_POS_REVISAO, END)

    # A pausa obrigatória: o grafo NUNCA entra no registro sem um resume explícito.
    return g.compile(checkpointer=checkpointer, interrupt_before=[NO_POS_REVISAO])


def executar_pipeline_sem_langgraph(estado: EstadoDossie) -> EstadoDossie:
    """Execução sequencial dos nós 1-5 SEM langgraph (para testes/golden eval do scaffold).

    Para no mesmo ponto do interrupt: retorna o estado em 'revisao_humana', SEM executar o
    Nó 6 — quem chama decide injetar `revisao` e chamar no_registro_correcao explicitamente,
    espelhando o resume."""
    atual: dict = dict(estado)
    for no in (no_extracao, no_recuperacao_rag, no_verificacao, no_classificacao_orgao, no_justificativa):
        atual.update(no(atual))  # type: ignore[arg-type]
    return atual  # type: ignore[return-value]

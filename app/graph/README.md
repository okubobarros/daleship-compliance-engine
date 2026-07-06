# Grafo Fase 2 (MAPA/Bioinsumos) — scaffold antecipado

**Status: fundação, não roda em produção.** Trabalho "bancado" para quando a Fase 2 ativar
(ROADMAP: só após a Fase 1 validada com a trading). Branch `fase2-scaffold`, fora da main.

## O que está aqui

- `state.py` — estado do grafo (TypedDicts serializáveis; sobrevivem a checkpoint e viram JSONB).
- `nodes/` — os 6 nós do ARCHITECTURE §2, funções puras testáveis isoladamente.
  Os guards NÃO são stubs: grounding do Nó 5 (citação só de chunk recuperado, dentro do limiar
  calibrado, referência forjada descartada, abstenção honesta), órgão-do-chunk no Nó 4, e
  recusa-sem-revisão no Nó 6 são lógica real, coberta por `app/tests/test_grounding.py`.
- `graph.py` — montagem LangGraph com `interrupt_before=['registro_correcao']` (revisão humana
  obrigatória — não negociável). Import do langgraph é lazy: os nós testam sem a dependência.
- `../db/schema.sql` — schema de destino consolidado (aplicar via migrations formais).

## O que portar da Fase 1 ao ativar (código já validado nesta base)

| Nó | Fonte do padrão validado |
|---|---|
| 1 Extração | `app/llm_extracao.py` (schema JSON forçado, retry, fallback, prompt endurecido) |
| 2 RAG | `mcp-server/src/tools/rag_search.py` (híbrido) + `embeddings.py` (TPM throttle) + `grounding.py` (limiar — fonte única, já importado pelo Nó 5) |
| 3 Verificação | Code nodes do `n8n/workflows/comex_conciliacao.json` + `app/processamento.py::_conciliar` (normalização numérica — divergência falsa) |
| 5 Justificativa | guard já portado (este scaffold) |
| 6 Registro | `app/db.py::registrar_revisao` (correção estruturada + log append-only) |
| Ingestão | `ingestion/` (config-driven por órgão, versionamento por vigência, chunks de escrita) |

## O que NÃO fazer aqui (decidido)

- Ingestão de MAPA/Anvisa/Ibama/ICMBio — trabalho de dado da Fase 2 real (`fontes_anuencia.yaml` já
  tem os stubs bloqueados/desbloqueados na Fase 1).
- Roteamento multi-LLM (CLAUDE.md §3). UI (o scaffold é só orquestração).

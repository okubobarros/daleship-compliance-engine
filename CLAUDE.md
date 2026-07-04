# CLAUDE.md — Contexto do Projeto para Claude Code

Este arquivo é a **fonte de verdade sobre a ordem de execução do projeto**. Se qualquer outro documento em `docs/` parecer contradizer o que está aqui sobre qual vertical vem primeiro, **este arquivo e o `docs/ROADMAP.md` prevalecem** — os demais documentos foram escritos em momentos diferentes da decisão de produto e alguns ainda carregam escopo desatualizado (sinalizado em cada um, ver seção 5).

## 1. O que este projeto é

Motor de conformidade (compliance engine) horizontal, com arquitetura de raciocínio regulatório explicável (extração → recuperação normativa via RAG → verificação → justificativa com citação obrigatória → revisão humana → log auditável). Essa arquitetura é agnóstica de domínio regulatório — o que muda entre verticais é a base normativa consumida, não o motor.

## 2. Ordem de execução — duas fases, decidida e não ambígua

**Fase 1 (agora): Comex.** Demonstração para uma trading real (onde o contato de domínio "Bonano" trabalha). **Correção importante (registrada aqui para não repetir o erro):** não existe protótipo n8n pronto do PIPE/FAPESP para reaproveitar, nem base normativa de comex já indexada — a Fase 1 do FAPESP não tem nada construído ainda; são duas frentes paralelas e independentes, não uma decorrência da outra. A Fase 1 deste produto é construída do zero, orientada pelo documento `docs/ComexPilot.md` (levantamento de requisitos feito por especialista de domínio da trading) — ver esse documento para a lista completa de fontes normativas a indexar e as perguntas de produto já mapeadas por quem vive a operação. Escopo: conciliação Invoice × Packing List × B/L + verificação de anuência (LPCO) para 1-2 órgãos. Orquestração via n8n nesta fase (mais rápido para prototipar do zero do que já ir para LangGraph), não LangGraph ainda — ver `docs/ROADMAP.md` para a justificativa dessa escolha.

**Fase 2 (depois, quando Fase 1 estiver validada com a trading): MAPA/Anvisa/Ibama — defensivos agrícolas e bioinsumos.** Esta é a aposta de negócio de maior margem e potencial de receita (ver `Simulacao_Daleship_v2.xlsx`), mas entra depois de Comex, não antes. Migração de orquestração para LangGraph/Python nesta fase — ver `docs/ARCHITECTURE.md`.

**Importante**: Fase 1 (Comex) é validação técnica e porta de entrada comercial rápida, não a tese de receita principal de longo prazo — a simulação financeira mostra que Comex sozinho tem a pior margem estrutural das opções avaliadas. Não invistam em Comex além do necessário para a demonstração funcionar bem.

## 3. Sobre roteamento dinâmico multi-LLM

A tese científica original da Fase 1 do PIPE/FAPESP trata roteamento dinâmico entre múltiplos LLMs (por complexidade de tarefa) como parte central da pesquisa. **Para o MVP de produto (tanto Fase 1 Comex quanto Fase 2 MAPA), essa otimização fica fora de escopo por decisão deliberada** — usem um único modelo forte por enquanto (ver `docs/ARCHITECTURE.md` e `docs/INFRA_COST_GUARDRAILS.md`). Roteamento dinâmico volta a ser relevante só depois que houver volume real de uso que justifique otimizar custo — não é pré-requisito para nenhuma das duas fases atuais.

## 4. Princípios não negociáveis de engenharia (valem para as duas fases, qualquer domínio)

1. **Nunca gerar citação normativa sem grounding.** Toda afirmação sobre exigência regulatória precisa vir de um chunk recuperado da base indexada. Sem fonte, o sistema sinaliza explicitamente a ausência — nunca inventa.
2. **Nunca decidir sozinho.** Todo fluxo termina em um ponto de revisão humana antes de qualquer resultado ser considerado final.
3. **Log é append-only.** Nunca UPDATE ou DELETE em log de auditoria — só INSERT.
4. **Versionamento de norma por data de vigência.** Mudança normativa nunca sobrescreve uma linha existente — fecha a vigência antiga e insere uma nova.
5. **Escopo estreito em cada fase.** Resistir à expansão de cobertura antes de validar o recorte atual. Ver `docs/ROADMAP.md` para a ordem correta dentro de cada fase.

## 5. Nota de escopo por documento (para evitar a ambiguidade que já aconteceu uma vez)

| Documento | Escopo real | Observação |
|---|---|---|
| `docs/ROADMAP.md` | **Ambas as fases, na ordem correta** | Fonte de verdade sobre sequência — sempre consultar primeiro |
| `docs/MCP_SISCOMEX_INTEGRATION.md` | Fase 1 (Comex) | Trata comex como frente ativa, corretamente |
| `docs/PROJECT_STRUCTURE.md` | Ambas as fases | Estrutura de pastas já contempla `n8n/` (Fase 1) e `app/` (Fase 2) |
| `docs/PRD.md` | **Fase 2 (MAPA/defensivos)** | Escrito antes da inversão de ordem — os requisitos funcionais valem para a Fase 2, não para o MVP de Comex da Fase 1 |
| `docs/ARCHITECTURE.md` | **Fase 2 (MAPA/defensivos)**, mas a decisão de stack (LangGraph, pgvector, modelo único) vale como destino final também para quando Comex migrar de n8n para código | Ler junto com a seção 2 deste arquivo |
| `docs/DATA_SOURCES.md` | **Fase 2 (MAPA/defensivos)** | Para as fontes de Comex (NCM, Tratamento Administrativo, Soluções de Consulta), usar a base já indexada no protótipo FAPESP original, não este documento |
| `docs/CUSTOMER_JOURNEY.md` | **Fase 2 (MAPA/defensivos)** | A jornada da Fase 1 (Comex-demo) está descrita de forma mais enxuta dentro do próprio `docs/ROADMAP.md` e `docs/MVP_PRODUCT_SPEC.md` |
| `docs/STAKEHOLDER_VISION.md` | **Fase 2 (MAPA/defensivos)**, mas os princípios de UX/negócio/CIO se aplicam igualmente à Fase 1 | Ler com essa ressalva |
| `docs/MVP_PRODUCT_SPEC.md` | **Fase 1 (Comex-demo)** | Este é o documento de produto correto para a fase atual |
| `docs/DOU_SISCOMEX_MONITORING.md` | Ambas — mas na Fase 1 só a parte de Comex/Siscomex é relevante; a parte de defensivos entra na Fase 2 | — |
| `docs/INFRA_COST_GUARDRAILS.md` | Ambas as fases | Guardrails e stack de custo mínimo valem igualmente |

**Se estiver decidindo o que fazer agora e a orientação parecer ambígua**: siga `docs/ROADMAP.md` → Fase 1 → Comex, com `docs/MVP_PRODUCT_SPEC.md` como referência de produto e `docs/MCP_SISCOMEX_INTEGRATION.md` como referência técnica. Os documentos focados em MAPA/defensivos (`PRD`, `ARCHITECTURE`, `DATA_SOURCES`, `CUSTOMER_JOURNEY`, `STAKEHOLDER_VISION`) só voltam a ser a referência ativa quando o `ROADMAP.md` indicar a transição para a Fase 2.

## 6. Stack (Fase 1 — Comex)

- Orquestração: n8n (reaproveitando o protótipo do PIPE/FAPESP)
- MCP server: Python, compartilhado entre Fase 1 e Fase 2 (ver `docs/MCP_SISCOMEX_INTEGRATION.md`)
- Banco: Postgres + pgvector
- LLM: um único modelo forte (não implementar roteamento multi-modelo)

## 7. Stack (Fase 2 — MAPA/Bioinsumos, destino após migração)

- Orquestração: LangGraph (Python)
- Backend: FastAPI
- Banco: Postgres + pgvector (mesmo banco, schema estendido)
- LLM: um único modelo forte no início; roteamento dinâmico fica para depois (seção 3)

## 8. O que explicitamente não construir em nenhuma das duas fases agora

- Roteamento dinâmico multi-LLM (seção 3).
- Integração automática com SISPA (sem API pública conhecida — Fase 2).
- Dashboard executivo, cobrança automatizada, multi-tenancy enterprise.
- Qualquer expansão de escopo (nova vertical, novo módulo de upsell) antes de validar a fase atual com um cliente real.

## 9. Convenções de código

- Nomes de tabelas e campos em português, alinhados ao domínio regulatório.
- Todo nó de orquestração (seja fluxo n8n ou nó LangGraph) deve ser testável isoladamente.
- Toda função que toca a base normativa deve registrar de qual norma/fonte a informação veio, para permitir auditoria retroativa.

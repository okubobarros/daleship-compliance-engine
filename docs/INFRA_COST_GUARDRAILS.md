# Infraestrutura Free-Tier e Guardrails

**Referência:** ARCHITECTURE.md, STAKEHOLDER_VISION.md (seção CIO)

---

## 1. Stack de menor custo para começar hoje

O objetivo é rodar o MVP inteiro dentro de free tiers/hobby tiers até haver receita ou necessidade real de escala.

| Camada | Serviço recomendado | Por quê |
|---|---|---|
| Postgres + pgvector | **Supabase** (free tier) | Postgres gerenciado com pgvector nativo, storage de arquivo incluso, autenticação pronta se precisarem depois |
| Object storage (documentos brutos) | **Supabase Storage** (incluso no free tier) ou **Cloudflare R2** (tier gratuito generoso, sem custo de egress) | Evita multiplicar provedores no início |
| Backend/API | **Railway** ou **Render** (hobby/free tier) | Deploy simples de FastAPI, suficiente para tráfego de MVP/design partners |
| Cron jobs (ingestão DOU, reindexação) | **GitHub Actions** (free tier generoso para repositórios privados de pequeno uso) | Evita pagar por worker dedicado só para jobs agendados no início |
| Frontend mínimo | **Vercel** (free tier) ou Streamlit no próprio backend | Zero custo para poucos usuários |
| LLM | Pagar por uso (API), sem free tier realista para uso de produção — orçar por token, não por assinatura fixa | Ver seção de controle de token abaixo |

**Estimativa de custo mensal no estágio de MVP/design partners**: infraestrutura próxima de R$0-200/mês (dentro dos free tiers), com o custo real concentrado em chamadas de LLM — que é exatamente o custo que o "roteamento dinâmico" da Fase 1 do PIPE foi desenhado para reduzir mais adiante.

## 2. Controle de tokens — desde o primeiro commit

- **Orçamento de token por dossiê processado.** Definam um teto (ex: N tokens por dossiê) e logem o consumo real por execução do grafo LangGraph — cada nó reporta quanto consumiu. Sem isso, é impossível saber depois se o roteamento dinâmico futuro está realmente economizando.
- **Cache de recuperação RAG.** Se dois dossiês fazem a mesma pergunta normativa (comum, já que o MVP cobre uma única categoria de ingrediente ativo), cacheiem o resultado da busca — não paguem para recuperar o mesmo chunk duas vezes.
- **Truncamento inteligente de contexto.** Nunca joguem o dossiê inteiro + toda a base normativa recuperada para o modelo sem filtro — o Nó 2 (RAG) já deve entregar só os chunks mais relevantes (top-N pós-reranking), não tudo que foi indexado.
- **Modelo certo para cada nó, não o mais caro para tudo.** Mesmo sem roteamento dinâmico multi-modelo completo no MVP (decisão em ARCHITECTURE.md), o nó de extração (Nó 1) pode already usar um modelo mais barato que o nó de justificativa (Nó 5) — são tarefas de complexidade diferente desde o início.

## 3. Guardrails — o que impede o sistema de "inventar" ou vazar dado

**Guardrail 1 — grounding obrigatório (o mais importante).**
O Nó 5 (justificativa) nunca deve aceitar gerar uma afirmação normativa sem um `norma.id` de origem anexado. Implementem isso como checagem programática (não só instrução de prompt) — se o output do LLM citar algo sem referência rastreável na base, o sistema descarta essa afirmação e sinaliza "sem base normativa localizada" em vez de mostrar ao usuário.

**Guardrail 2 — validação de output estruturado.**
Toda saída do grafo que vai para a interface deve ser validada contra um schema (ex: Pydantic) antes de renderizar — nunca mostrem texto livre do LLM diretamente sem passar por essa validação, para evitar que um erro de formatação vire uma alegação de compliance mal interpretada pelo usuário.

**Guardrail 3 — isolamento de dado entre clientes.**
Mesmo em banco único (Postgres compartilhado no MVP), toda query precisa filtrar por `cliente_id` explicitamente — nunca por confiança implícita de sessão. Um erro aqui vaza dado comercialmente sensível de um cliente para outro, o pior cenário possível de reputação nesse nicho.

**Guardrail 4 — proteção contra conteúdo malicioso na base normativa.**
Como o pipeline de ingestão (DOU, Agrofit, SISPA) puxa conteúdo de fontes externas, tratem esse conteúdo como não confiável até validado — nunca permitam que texto de uma fonte externa seja interpretado como instrução para o LLM (risco de prompt injection via conteúdo indexado). O conteúdo normativo entra como dado a ser citado, nunca como comando a ser seguido.

**Guardrail 5 — humano é sempre o guardrail final.**
Reforçando o que já está em ARCHITECTURE.md: o `interrupt` do LangGraph antes de qualquer resultado final não é opcional nem contornável por configuração — é a garantia de que nenhuma decisão de compliance sai do sistema sem revisão humana, mesmo que todos os guardrails automáticos acima funcionem perfeitamente.

## 4. Checklist mínimo antes de mostrar a uma trading

- [ ] Grounding obrigatório testado com casos adversariais (perguntar algo fora da base e confirmar que o sistema diz "não encontrado", não inventa).
- [ ] Orçamento de token por dossiê medido e registrado, mesmo que ainda não otimizado.
- [ ] Isolamento de `cliente_id` testado explicitamente (não assumido).
- [ ] Todo output validado por schema antes de chegar à UI.
- [ ] Log de auditoria append-only confirmado — testem tentando fazer UPDATE/DELETE e confirmem que a aplicação impede.

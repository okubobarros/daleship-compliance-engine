# Roadmap de Execução — Duas Fases (Comex-demo → MAPA/Bioinsumos)

**Referência:** PRD.md, ARCHITECTURE.md, DATA_SOURCES.md, MCP_SISCOMEX_INTEGRATION.md

**Mudança de estratégia (registrada aqui para contexto):** a ordem de exposição ao mercado foi invertida. Fase 1 é o motor de raciocínio (extração, explicabilidade, trilha auditável) construído do zero e aplicado ao domínio de Comex, guiado pelo levantamento de requisitos em `docs/ComexPilot.md`, para gerar uma demonstração rápida a uma trading real. **Não há protótipo n8n do PIPE/FAPESP pronto para reaproveitar** — essa é uma frente paralela e independente, sem nada construído ainda. Fase 2 é a transição para a vertical MAPA/Bioinsumos, que continua sendo a aposta de negócio principal (ver `Simulacao_Daleship_v2.xlsx` — Comex tem a pior margem estrutural das quatro simulações). **Fase 1 é validação técnica e porta de entrada comercial, não a tese de receita de longo prazo.**

---

## Decisão de arquitetura: n8n vs. código (LangGraph) — o que usar em cada fase

Essa pergunta tem resposta diferente por fase, não uma resposta única.

### Fase 1 (Comex-demo): n8n para prototipar rápido do zero, não LangGraph ainda

Não existe workflow n8n pronto de nenhum protótipo anterior — a Fase 1 é construída do zero. Mesmo assim, n8n (em vez de já ir direto para LangGraph) ganha tempo real nesse primeiro ciclo:

- **n8n já suporta MCP nativamente** — como cliente (chama servidores MCP externos, incluindo o `MCP_SISCOMEX_INTEGRATION.md` que já especificamos) e, via node comunitário, como servidor (expõe um workflow n8n como ferramenta MCP para outros sistemas consumirem). Isso significa que **o MCP server que vamos construir não é retrabalho** — ele serve tanto o n8n quanto o código Python do LangGraph, qualquer que seja o orquestrador escolhido.
- Ganho real de n8n aqui: prototipagem visual rápida e menor fricção para conectar APIs externas (PUCOMEX, DOU) sem escrever cliente HTTP do zero.
- **Risco a controlar**: os guardrails mais importantes que definimos (`INFRA_COST_GUARDRAILS.md`) — grounding obrigatório, validação de schema antes de mostrar ao usuário, isolamento de `cliente_id` — são mais frágeis de garantir dentro de nós visuais do n8n do que em código testável. **Mitigação**: qualquer nó do n8n que faça verificação de grounding ou validação de saída deve ser um nó de código (Function/Code node), nunca depender só de instrução de prompt dentro de um nó de IA.

### Fase 2 (MAPA/Bioinsumos): migrar para código (LangGraph), como já decidido em ARCHITECTURE.md

Para o produto de longo prazo, a decisão registrada em `ARCHITECTURE.md` continua correta e não muda:
- Testabilidade e CI real (n8n não versiona bem em git, dificulta revisão de código e testes automatizados).
- `interrupt`/`resume` nativo do LangGraph para o human-in-the-loop é mais robusto do que qualquer padrão de "esperar aprovação" montado à mão em n8n.
- Menor custo operacional em escala — n8n como motor de produção (self-hosted ou cloud) adiciona uma camada de infraestrutura e execução que o roadmap de custo mínimo (`INFRA_COST_GUARDRAILS.md`) não precisa pagar.
- Auditoria e log append-only são mais fáceis de garantir por contrato de código do que por configuração de workflow visual.

### Recomendação prática de transição

Tratem o n8n da Fase 1 como **protótipo descartável de front-door**, não como fundação do produto. O ativo que sobrevive da Fase 1 para a Fase 2 é o **MCP server** (interface de ferramentas) e a **base RAG/schema de banco**, não o workflow n8n em si. Ao migrar para MAPA/Bioinsumos, reescrevam a orquestração em LangGraph reaproveitando os nós de verificação/schema que já terão sido testados como código dentro do n8n (os Function nodes viram funções Python quase diretamente).

---

## FASE 1 — Comex-demo (semanas 1-4, escopo estreito construído do zero)

### Semana 1 — Construção do zero (não há protótipo a reaproveitar)

**Correção de premissa:** não existe workflow n8n do PIPE/FAPESP pronto, nem base normativa de comex já indexada — essa suposição estava errada nas versões anteriores deste roadmap. As duas frentes (produto/trading e PIPE/FAPESP) são paralelas e independentes. A Semana 1 é construção real do zero, orientada pelo `docs/ComexPilot.md`.

- [ ] Criar o workflow n8n do zero: nó de extração de documento, nó de verificação/conciliação, nó de explicabilidade — usando o `docs/ComexPilot.md` como especificação de requisitos.
- [ ] Indexar a base normativa de comex pela primeira vez, seguindo as fontes listadas em `docs/ComexPilot.md`: campos DUIMP/LPCO, tabela TEC/NCM, Soluções de Consulta da RFB, RGI, Tratamento Administrativo por NCM, Acordos Comerciais.
- [ ] Priorizar 1-2 órgãos anuentes para o escopo inicial (a lista completa em `docs/ComexPilot.md` inclui Anvisa, MAPA, Inmetro, Ibama, Anatel, ANP, Exército — não tentem cobrir todos de uma vez).
- [ ] Configurar o node MCP do n8n para consumir o `MCP_SISCOMEX_INTEGRATION.md` (tools de busca normativa e consulta Siscomex).

### Semana 2 — Escopo estreito de conciliação + anuência

- [ ] Definir o recorte mínimo: conciliação Invoice × Packing List × B/L + verificação de LPCO para 1-2 órgãos anuentes.
- [ ] Implementar/testar a checagem de grounding (nó de código, não nó de IA solto) — mesma regra não negociável do `ARCHITECTURE.md`: nunca citar sem `norma.id` de origem.
- [ ] Testar com 2-3 casos reais ou simulados de conciliação documental.

### Semana 3 — Human-in-the-loop e trilha de auditoria no n8n

- [ ] Montar o ponto de pausa para revisão humana (aprovação manual antes de finalizar).
- [ ] Garantir log append-only das correções (mesmo em n8n, isso deve escrever em uma tabela Postgres com a mesma disciplina do `ARCHITECTURE.md` — não fica só no histórico de execução do n8n).

### Semana 4 — Demonstração com a trading

- [ ] Rodar com 1-2 dossiês reais da trading (ou simulados com dado público, se a trading não puder compartilhar dado real ainda).
- [ ] Se a trading topar gerar Chave de Acesso PUCOMEX no ambiente de validação, mostrar consulta real, não mockada.
- [ ] Capturar feedback estruturado — mesmo critério do `CUSTOMER_JOURNEY.md`: o que gerou confiança, o que gerou dúvida.

**Critério de saída da Fase 1:** demonstração funcional com trading, feedback capturado, decisão tomada sobre se vale continuar investindo em Comex como receita ou tratá-lo só como validação encerrada.

---

## FASE 2 — MAPA/Bioinsumos (roadmap original, com esforço redistribuído)

Como já discutido, o núcleo de agente (extração, explicabilidade, human-in-the-loop, auditoria) já estará testado em produção real pela Fase 1 — o esforço aqui se concentra em dado, não em engenharia de agente do zero.

### Semana 5-6 — Migração de orquestração + base de conhecimento regulatório

- [ ] Reescrever a orquestração em LangGraph (Python), reaproveitando a lógica dos Function nodes do n8n como funções testáveis.
- [ ] Setup Postgres + pgvector definitivo, aplicar schema de `ARCHITECTURE.md`.
- [ ] Escolher a categoria/ingrediente ativo único para o MVP de MAPA (defensivo químico genérico ou bioinsumo, conforme decisão de negócio).
- [ ] Capturar dados do Agrofit para essa categoria → popular `precedentes_agrofit`.
- [ ] Indexar IN SDA relevantes, monografia Anvisa, normas Ibama aplicáveis → popular `normas`.

**Critério de saída:** consulta de teste no RAG retorna chunk correto e citável para uma pergunta normativa da nova vertical.

### Semana 7 — Agente de análise (reaproveitando nós já testados na Fase 1)

- [ ] Portar Nó 1 (extração), Nó 2 (RAG), Nó 3 (verificação), Nó 4 (classificação por órgão), Nó 5 (justificativa) — grande parte é reconfiguração de prompt/schema, não implementação nova.

### Semana 8 — Validação contra caso conhecido

- [ ] Pegar um dossiê de produto já registrado com sucesso (resultado conhecido) na nova vertical.
- [ ] Meta: 80% de acerto nas lacunas identificadas (mesma métrica do `PRD.md`).

### Semana 9 — Human-in-the-loop e captura de correção (reaproveitando padrão da Fase 1)

- [ ] Portar interrupt/resume e interface de revisão da Fase 1, adaptando aos campos da nova vertical.

### Semana 10-11 — Endurecimento e preparação de demo

- [ ] Testar com dossiês adicionais.
- [ ] Revisar todas as justificativas geradas — grounding sem exceção.
- [ ] Preparar roteiro de demonstração para design partners de MAPA/Bioinsumos (fabricante de genérico/bioinsumo + consultoria regulatória).

### Semana 12 — Primeira rodada de demonstração MAPA/Bioinsumos

- [ ] Sessões de demo conforme `CUSTOMER_JOURNEY.md`.
- [ ] Capturar feedback estruturado e decidir expansão de categoria.

---

## O que fica fora de escopo em ambas as fases

- Roteamento dinâmico multi-LLM (decisão mantida do `ARCHITECTURE.md`).
- Integração automática com SISPA (sem API pública conhecida).
- Dashboard executivo e métricas de ROI para o cliente.
- Multi-tenancy e autenticação enterprise.
- Módulos de expansão (pós-registro contínuo, inteligência de portfólio etc.) — entram só depois de Fase 2 validada.

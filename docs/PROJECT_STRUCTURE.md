# Estrutura de Pastas e Stack — Guia para o VS Code

**Referência:** todos os documentos anteriores (`CLAUDE.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `MCP_SISCOMEX_INTEGRATION.md`)
**Objetivo:** dar ao Claude Code (e a qualquer pessoa abrindo o projeto no VS Code) um mapa físico de onde cada coisa mora.

---

## Árvore de pastas completa

```
daleship-compliance-engine/
├── CLAUDE.md                       # Claude Code lê isso automaticamente ao abrir o projeto
├── README.md                       # Explicação geral do projeto para humanos
├── .env.example                    # Modelo de variáveis de ambiente (chaves de API etc.)
├── .gitignore
│
├── docs/                           # Toda a documentação de produto/arquitetura já criada
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATA_SOURCES.md
│   ├── ROADMAP.md
│   ├── CUSTOMER_JOURNEY.md
│   ├── STAKEHOLDER_VISION.md
│   ├── DOU_SISCOMEX_MONITORING.md
│   ├── INFRA_COST_GUARDRAILS.md
│   └── MCP_SISCOMEX_INTEGRATION.md
│
├── n8n/                            # FASE 1 — demonstração de Comex
│   ├── workflows/
│   │   ├── comex_conciliacao.json  # o workflow exportado do n8n (isso É código, versionem no git)
│   │   └── README.md               # como importar esse workflow num n8n novo
│   └── docker-compose.yml          # sobe um n8n local com um comando
│
├── mcp-server/                     # Camada de ferramentas — usada pelo n8n E pelo app em Python
│   ├── src/
│   │   ├── server.py               # entrypoint do servidor MCP
│   │   ├── tools/
│   │   │   ├── rag_search.py       # busca na base normativa
│   │   │   ├── siscomex_client.py  # cliente PUCOMEX autenticado
│   │   │   ├── agrofit_lookup.py   # consulta a precedentes
│   │   │   └── dossie_tools.py     # criação/consulta de dossiê
│   │   ├── auth/
│   │   │   └── pucomex_auth.py     # handshake de certificado digital
│   │   └── db/
│   │       └── connection.py
│   ├── requirements.txt
│   └── README.md
│
├── app/                            # FASE 2 — o produto de verdade, em Python/LangGraph
│   ├── graph/
│   │   ├── nodes/
│   │   │   ├── extracao.py
│   │   │   ├── recuperacao_rag.py
│   │   │   ├── verificacao.py
│   │   │   ├── classificacao_orgao.py
│   │   │   ├── justificativa.py    # o nó mais crítico — grounding obrigatório
│   │   │   └── registro_correcao.py
│   │   ├── state.py                # define o que passa entre os nós
│   │   └── graph.py                # monta o LangGraph inteiro
│   │
│   ├── api/
│   │   └── main.py                 # FastAPI — expõe o sistema como API
│   │
│   ├── db/
│   │   ├── models.py
│   │   ├── schema.sql              # o schema completo já definido em ARCHITECTURE.md
│   │   └── connection.py
│   │
│   ├── ingestion/                  # os robôs que mantêm a base normativa atualizada
│   │   ├── agrofit_scraper.py
│   │   ├── dou_monitor.py          # baseado no Ro-DOU (ver DOU_SISCOMEX_MONITORING.md)
│   │   └── normas_versioning.py
│   │
│   ├── ui/
│   │   └── app.py                  # interface mínima (Streamlit) de revisão humana
│   │
│   ├── tests/
│   │   ├── test_grounding.py       # o teste mais importante do projeto inteiro
│   │   ├── test_nodes.py
│   │   └── fixtures/                # dossiês de exemplo para teste
│   │
│   ├── requirements.txt
│   └── README.md
│
├── infra/
│   ├── docker-compose.yml          # Postgres + pgvector local, um comando sobe tudo
│   └── github-actions/
│       └── ingest-dou.yml          # roda o monitoramento do DOU de graça, agendado
│
└── scripts/
    └── setup_local_dev.sh          # um script só para preparar o ambiente do zero
```

## Por que essa organização (explicação sem jargão)

Pensem nas quatro pastas principais como quatro "departamentos" da empresa:

- **`docs/`** é a sala de reuniões — onde ficam as decisões já tomadas, para qualquer pessoa (ou o próprio Claude Code) reler antes de agir.
- **`n8n/`** é a oficina rápida — onde vocês montam e testam a demonstração de Comex sem precisar escrever muito código, reaproveitando o que já existe do projeto FAPESP.
- **`mcp-server/`** é o balcão de atendimento compartilhado — tanto a oficina rápida (`n8n/`) quanto a fábrica principal (`app/`) batem nesse balcão para consultar norma, consultar Siscomex, etc. Construir isso uma vez e os dois lados usam.
- **`app/`** é a fábrica principal — o produto de verdade, em código, que vai crescer e durar. É aqui que mora a maior parte do valor de longo prazo da empresa.

## Stack, explicado item por item

| Peça | O que é, em termos simples | Por que essa escolha |
|---|---|---|
| **n8n** | Ferramenta visual de automação — você conecta "caixinhas" numa tela em vez de escrever código para tarefas de integração | Vocês já têm experiência com ela do protótipo FAPESP; ganha tempo na Fase 1 |
| **Python** | A linguagem de programação da parte séria do sistema | Padrão da indústria para IA/agentes; todas as bibliotecas que precisamos (LangGraph, RAG) são em Python |
| **LangGraph** | Uma biblioteca que organiza "o que a IA faz, em que ordem, com pausa para humano revisar" | É como um fluxograma que vira código — dá controle fino sobre cada etapa do raciocínio |
| **FastAPI** | Framework para expor o sistema Python como um serviço que outras coisas (site, n8n, apps) podem chamar | Padrão simples e rápido para times pequenos |
| **Postgres** | Banco de dados — onde ficam guardadas as informações estruturadas (dossiês, normas, correções) | É o banco mais usado do mundo, gratuito, confiável |
| **pgvector** | Um "complemento" do Postgres que permite busca por significado (não só por palavra exata) | Evita precisar de um banco separado só para isso — menos peça para gerenciar |
| **Streamlit** | Forma rápida de criar uma tela (interface) em Python sem precisar aprender programação de front-end de verdade | Suficiente para a tela onde o analista revisa e corrige o que o sistema encontrou, no início |
| **MCP (Model Context Protocol)** | Um "padrão de conexão" que permite que a IA (seja no n8n, seja no código Python) chame ferramentas de forma organizada | Constrói a ferramenta uma vez, usa em vários lugares |
| **GitHub Actions** | Executa tarefas agendadas (tipo "todo dia às 8h, verifique o Diário Oficial") de graça | Evita pagar por um servidor ligado 24 horas só para isso |
| **Supabase** (sugestão de hospedagem) | Um serviço que já entrega Postgres + pgvector + armazenamento de arquivo prontos, com plano gratuito | Menos peças para configurar sozinho no início |

## Como abrir isso no VS Code, na prática

1. Criem o repositório vazio no GitHub, cheguem no VS Code e façam `git clone`.
2. Rodem `scripts/setup_local_dev.sh` (a criar) — ele deve subir o `infra/docker-compose.yml` (Postgres local) e instalar as dependências Python de `app/requirements.txt` e `mcp-server/requirements.txt`.
3. Abram a pasta inteira no VS Code (`code .`) — o Claude Code, quando chamado dentro do VS Code ou pelo terminal integrado, já vai ler o `CLAUDE.md` da raiz automaticamente.
4. Para a Fase 1, trabalhem dentro de `n8n/` e `mcp-server/`. Para a Fase 2 (mais adiante), o trabalho migra para `app/`.

## Ordem sugerida de criação (não construam tudo de uma vez)

1. `docs/` — já pronto, só copiar os arquivos que já geramos.
2. `infra/docker-compose.yml` — sobe o Postgres local primeiro, antes de qualquer código.
3. `mcp-server/` — porque tanto a Fase 1 quanto a Fase 2 dependem dele.
4. `n8n/` — a demonstração de Comex.
5. `app/` — só começa depois que a Fase 1 estiver validada com a trading, conforme o `ROADMAP.md`.

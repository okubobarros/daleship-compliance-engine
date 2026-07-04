# MCP Server — Compliance Engine

Camada de ferramentas compartilhada entre o n8n (Fase 1) e o app LangGraph (Fase 2), conforme
`docs/MCP_SISCOMEX_INTEGRATION.md`.

## Setup local

```bash
cd mcp-server
python -m venv .venv
.venv/Scripts/activate  # ou source .venv/bin/activate no Linux/Mac
pip install -r requirements.txt
```

## Variáveis de ambiente necessárias (`.env` na raiz do repo)

- `DATABASE_URL` — connection string direta do Postgres do Supabase (Settings > Database > Connection
  string). **Ainda não configurada** — `NEXT_PUBLIC_SUPABASE_URL` + a chave publishable não são
  suficientes para `asyncpg` (são para chamadas REST/client, não conexão direta ao Postgres).

## Rodar o servidor

```bash
cd src
python server.py
```

## Estado atual (Semana 1)

- `rag_search.py`: busca **híbrida** (lexical + semântica) contra `normas`. A parte semântica usa
  `embeddings.py` (Voyage `voyage-law-2`, dim 1024) e só contribui quando há `VOYAGE_API_KEY` e normas com
  embedding; caso contrário degrada para lexical, sem nunca inventar fonte.
- `embeddings.py`: cliente Voyage compartilhado (ingestão embeda documento, rag_search embeda query).
  `NullEmbedder` como fallback sem chave.
- `siscomex_client.py`: ainda não implementado de verdade — depende de certificado digital de teste +
  Chave de Acesso da trading no ambiente de validação PUCOMEX.
- `dossie_tools.py`: funcional, depende do schema em `infra/schema_fase1.sql` + migrations
  (`infra/apply_migrations.py`) já aplicados.

## Variável adicional

- `VOYAGE_API_KEY` — chave da Voyage AI (embeddings). Sem ela, a busca roda só lexical.

# API — Índice de confiança (fatia vertical fina)

Endpoint **mínimo** (só este — não o Cockpit inteiro; Frente 2 segue pausada) que expõe o
`resumo_consolidado` de um dossiê para a seção "Índice de confiança" em despachantedebolso.com.br.

## Arquivos
- `main.py` — FastAPI. `GET /dossies/{id}/resumo` → `{indice_confianca, score_risco, excecoes, mensagem, ncm}`.
- `static/indice-confianca.html` — componente visual (gauge reaproveitado do brief `cockpit-decisao.html`),
  com a explicação FIXA de "confiança baixa" acoplada ao número (nunca um sem o outro).

## Variáveis de ambiente (nomes EXATOS lidos no código; nunca hardcode)
Só o endpoint `/resumo` precisa das 3 primeiras. Se for usar `/admin/processar-fila` (ou rodar o
worker), precisa também das de LLM/embeddings.
| Var (exata) | Obrigatória p/ | Uso |
|---|---|---|
| `DATABASE_URL` | /resumo e worker | connection string Postgres (`postgresql://postgres:SENHA@db.<ref>.supabase.co:5432/postgres`) — use a **senha rotacionada**. O código NÃO usa `SUPABASE_SERVICE_ROLE_KEY`. |
| `API_TOKEN` | /resumo e /admin | Bearer (fail-closed: sem ele → 503) |
| `ALLOWED_ORIGINS` | /resumo (browser) | origens CORS, separadas por vírgula (default `https://despachantedebolso.com.br`) |
| `GEMINI_API_KEY` | worker/admin | rerank NCM (é `GEMINI_API_KEY`, não `GOOGLE_API_KEY`) |
| `GEMINI_MODEL` | opcional | default `gemini-3.5-flash` |
| `OPENROUTER_API_KEY` | worker/admin | fallback do rerank |
| `VOYAGE_API_KEY` | worker/admin | embeddings (retrieval k=25) |
| `NCM_WORKER_PARALELO` | opcional | N do worker (default 3) |

## Processar a fila de NCM — SOB DEMANDA (não há worker 24/7)
`worker_ncm.processar()` **drena a fila até esvaziar e encerra** (não fica em loop de polling). Duas formas:
- **(a) Endpoint** `POST /admin/processar-fila` (protegido pelo `API_TOKEN`) — drena e retorna as stats.
  `?max=N` drena no máximo N itens por chamada (evita timeout de HTTP em fila grande). Ex.:
  `curl -X POST -H "Authorization: Bearer $API_TOKEN" https://<api>/admin/processar-fila?max=25`
  Como é um Web Service já ligado, não custa um Background Worker extra no Render.
- **(b) Comando manual** (Render Shell ou local apontando para o Supabase de produção):
  `DATABASE_URL=... GEMINI_API_KEY=... OPENROUTER_API_KEY=... VOYAGE_API_KEY=... python app/worker_ncm.py`
  (roda uma vez, drena tudo e sai). Bom para um Render **Cron/One-off Job** manual.

## Rodar
```
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
curl -H "Authorization: Bearer $API_TOKEN" http://localhost:8000/dossies/<uuid>/resumo
```

## Como a seção entra no site (token NÃO vai ao cliente)
O backend do site chama o endpoint **server-side** (com o `API_TOKEN`), injeta o JSON como
`window.__RESUMO__` na página, e inclui `static/indice-confianca.html`. Assim o token nunca é
exposto no browser. Se `window.__RESUMO__` não existir, o componente cai num exemplo de demonstração.

## ⚠️ Passo 1 (BLOQUEANTE) — rotacionar as credenciais vazadas (só o dono faz)
As keys abaixo vazaram em texto claro nos anexos n8n; rotacione ANTES de publicar:
- **Supabase service_role** (projeto `cpzjxgcekxyunktmcmay`): Dashboard → Project Settings → API →
  "Reset service_role" (ou Legacy API keys → regenerar). Atualize também a senha do DB se foi exposta.
- **Gemini** (`classificador_fiscal.txt`): https://aistudio.google.com/apikey → apagar a key antiga → criar nova.
- **OpenRouter** (`custos CTI.json`/n8n): https://openrouter.ai/keys → revogar a antiga → criar nova.
Depois, cole as novas em `DATABASE_URL` / `GEMINI_API_KEY` / `OPENROUTER_API_KEY` **no host** (não no repo).

## Passo 2 — publicar (turnkey, host-agnóstico via Dockerfile)
Railway: `railway up` na pasta `api/` (detecta o Dockerfile) e defina as env vars no painel.
Render: novo Web Service apontando para `api/` (Docker) + env vars. Fly: `fly launch` em `api/`.
Em qualquer um: setar `DATABASE_URL`, `API_TOKEN` (gere um forte), `API_CORS_ORIGENS=https://despachantedebolso.com.br`.
Só falta o acesso de infra ao domínio — que é do dono. A auditoria do repo já está limpa
(`.env` gitignorado, histórico sem secret, `.env.example` só placeholder).

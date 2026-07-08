# API — Índice de confiança (fatia vertical fina)

Endpoint **mínimo** (só este — não o Cockpit inteiro; Frente 2 segue pausada) que expõe o
`resumo_consolidado` de um dossiê para a seção "Índice de confiança" em despachantedebolso.com.br.

## Status (08/07/2026): NO AR e conectado ao site público
API validada ao vivo em `https://daleship-compliance-engine.onrender.com` — `GET /saude` → `200`,
as 3 rotas conferem, endpoint protegido responde 401 sem token. A seção "Índice de confiança" está
ligada em `resultado.html` (site Vercel) via `resumo.js` (proxy) — ver §"Como a seção entra no site"
abaixo. Ver `docs/STATUS.md` (raiz do repo) para o estado completo do projeto.

## Arquivos
- `main.py` — FastAPI (Render). `GET /dossies/{id}/resumo` → `{indice_confianca, score_risco, excecoes, mensagem, ncm}`.
- `resumo.js` — Vercel Serverless Function (Node.js). Proxy server-side: `resultado.html` chama
  `/api/resumo?dossie_id=...` same-origin; esta função injeta o `API_TOKEN` (env var do Vercel) e
  repassa a resposta do Render. O token nunca aparece no browser.
- `static/indice-confianca.html` — componente standalone original (gauge + explicação fixa), usado
  como referência/demo isolada. A versão em produção está inlined em `resultado.html` (mesmo texto
  fixo de "confiança baixa", mesma técnica de gauge via `conic-gradient`).

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

## Rodar localmente
```
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000        # a partir de api/
curl -H "Authorization: Bearer $API_TOKEN" http://localhost:8000/dossies/<uuid>/resumo
```
Via Docker (mesmo contexto do deploy real — ver Dockerfile): a partir da RAIZ do repo,
`docker build -f api/Dockerfile -t daleship-api .`

## Como a seção entra no site (token NÃO vai ao cliente)
`resultado.html` é 100% estático (sem servidor próprio) — por isso o desenho original ("backend do
site injeta `window.__RESUMO__`") não se aplicava. Implementação real: **`resumo.js`, uma Vercel
Serverless Function** (auto-detectada por estar em `api/*.js`), guarda o `API_TOKEN` como env var do
Vercel e faz a chamada ao Render server-side. O browser chama `/api/resumo?dossie_id=<uuid>`
(same-origin, sem CORS, sem token exposto); `resultado.html` lê `?dossie_id=` da própria URL.

**Config necessária no projeto Vercel** (Project Settings → Environment Variables):
| Var | Valor |
|---|---|
| `API_TOKEN` | **mesmo valor** configurado no Render |
| `RENDER_API_URL` | opcional, default `https://daleship-compliance-engine.onrender.com` |

Sem `?dossie_id=` na URL, ou se o dossiê não estiver consolidado, a seção fica **oculta** — nunca
mostra um número sem lastro real. Demo com dado real: acrescente
`?dossie_id=bc9afb26-982a-4235-90b9-f4c79c6ad80b` (dossiê de validação, IVPL Paulo) à URL de
`resultado.html`.

**`.vercelignore`** (raiz do repo) exclui `api/main.py` do build do Vercel — sem isso, o Vercel
auto-detecta `main.py`+`requirements.txt` como uma Serverless Function Python própria (convenção
zero-config), que colide com o deploy real (Render) e quebra com 500 (`DATABASE_URL` não existe como
env var do Vercel). Confirmado em produção antes do fix: `GET /api/main` e `/api/main.py` no domínio
Vercel retornavam 500; o site principal não era afetado.

## ⚠️ Pendente (BLOQUEANTE, só o dono confirma) — rotacionar as credenciais vazadas
As keys abaixo vazaram em texto claro nos anexos n8n; rotação ainda **não confirmada**:
- **Supabase service_role** (projeto `cpzjxgcekxyunktmcmay`): Dashboard → Project Settings → API →
  "Reset service_role" (ou Legacy API keys → regenerar). Atualize também a senha do DB se foi exposta.
- **Gemini** (`classificador_fiscal.txt`): https://aistudio.google.com/apikey → apagar a key antiga → criar nova.
- **OpenRouter** (`custos CTI.json`/n8n): https://openrouter.ai/keys → revogar a antiga → criar nova.
As novas keys vão em `DATABASE_URL` / `GEMINI_API_KEY` / `OPENROUTER_API_KEY` **no host** (Render →
Environment), nunca no repo.

## Deploy real (Render, host atual)
Dockerfile Path: `api/Dockerfile` · Root Directory: `.` (raiz do repo — o contexto de build é a raiz,
não `api/`; ver comentário no topo do Dockerfile). Env vars mínimas: `DATABASE_URL`, `API_TOKEN`,
`ALLOWED_ORIGINS` (nome exato — não é `API_CORS_ORIGENS`). Auto-deploy no push a `main`.

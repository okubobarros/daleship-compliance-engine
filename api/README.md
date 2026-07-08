# API — Índice de confiança (fatia vertical fina)

Endpoint **mínimo** (só este — não o Cockpit inteiro; Frente 2 segue pausada) que expõe o
`resumo_consolidado` de um dossiê para a seção "Índice de confiança" em despachantedebolso.com.br.

## Arquivos
- `main.py` — FastAPI. `GET /dossies/{id}/resumo` → `{indice_confianca, score_risco, excecoes, mensagem, ncm}`.
- `static/indice-confianca.html` — componente visual (gauge reaproveitado do brief `cockpit-decisao.html`),
  com a explicação FIXA de "confiança baixa" acoplada ao número (nunca um sem o outro).

## Variáveis de ambiente (nunca hardcode)
| Var | Uso |
|---|---|
| `DATABASE_URL` | Postgres (Supabase) — **use a key ROTACIONADA** |
| `API_TOKEN` | Bearer exigido (fail-closed: sem ele, o endpoint responde 503) |
| `API_CORS_ORIGENS` | origens permitidas (default `https://despachantedebolso.com.br`) |

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

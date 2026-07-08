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

## ⚠️ Pré-requisito BLOQUEANTE antes de publicar (não automatizável por aqui)
1. **Rotacionar** as credenciais que vazaram nos anexos n8n e confirmar: service_role do Supabase
   (`cpzjxgcekxyunktmcmay`), Gemini key (`classificador_fiscal.txt`), OpenRouter key.
2. Configurar as vars acima **no host de deploy** com as keys rotacionadas (nunca commitar).
3. Auditoria do repo já confirmada limpa (`.env` gitignorado, histórico sem secret, `.env.example`
   só placeholder). O deploy público espera (1) e o acesso de infra ao domínio.

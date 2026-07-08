# STATUS.md — Estado real do projeto (08/07/2026)

Este documento é a **fonte de verdade sobre o que existe de fato hoje** — código rodando, deploy no
ar, dado real na base. Os demais documentos em `docs/` (PRD, ARCHITECTURE, ROADMAP, PROJECT_STRUCTURE)
descrevem o **plano original** da Fase 1 (orquestração via n8n) — **não é o que foi construído**. Ver
§5 para o detalhe dessa divergência. Para "o que existe agora", leia este arquivo primeiro.

## 1. O que está NO AR agora

### API (Render) — `https://daleship-compliance-engine.onrender.com`
Deploy validado ao vivo em 08/07/2026: `GET /saude` → `200 {"ok":true}`; as 3 rotas batem com o
código (`/saude`, `/dossies/{id}/resumo`, `POST /admin/processar-fila`); endpoint protegido responde
**401 sem token** (fail-closed funcionando). Fonte: [api/main.py](../api/main.py),
[api/Dockerfile](../api/Dockerfile).

### Site público (Vercel) — `www.despachantedebolso.com.br`
Construído em paralelo (commits `da5df1b`…`0577376`, 06–07/07/2026), fora desta sessão de engenharia
de backend. É um **shell de jornada estático** (`index.html`, `simulacao.html`, `loading.html`,
`resultado.html`), com estado guardado em `sessionStorage` do navegador.

**Correção sobre o próprio site em produção (achada e corrigida em 08/07/2026):** `GET /api/main` e
`/api/main.py` no domínio Vercel retornavam **500** — o Vercel auto-detecta `api/main.py` +
`api/requirements.txt` (convenção zero-config) como uma Serverless Function Python própria, que
colide com o deploy real do Render e quebra (sem `DATABASE_URL` como env var do Vercel). O site
principal não era afetado. Corrigido com `.vercelignore` (exclui só `api/main.py` do build do Vercel).

**Índice de confiança: ligado.** `resultado.html` agora tem a seção real, alimentada por
`api/resumo.js` (Vercel Serverless Function, proxy server-side que guarda o `API_TOKEN` — nunca vai
ao browser). Fluxo: `resultado.html?dossie_id=<uuid>` → `fetch('/api/resumo?dossie_id=...')` →
`resumo.js` injeta o Bearer e chama o Render → renderiza gauge + a explicação fixa de "confiança
baixa" (sempre no mesmo bloco do número, nunca separada) + badge de exceções + mensagem agregada.
Validado em browser real (harness local espelhando o comportamento do Vercel) com o dossiê real
`bc9afb26-982a-4235-90b9-f4c79c6ad80b`. Sem `?dossie_id=`, a seção fica oculta — nunca mostra número
sem lastro. **Falta:** configurar `API_TOKEN` (mesmo valor do Render) no projeto Vercel e confirmar
que o deploy do Vercel pegou o `.vercelignore` novo — isso só se confirma olhando o dashboard/próximo
build do Vercel.

## 2. O motor (app/) — Fase 1 Comex, em Python, não em n8n

Contrário ao que `docs/ROADMAP.md`/`docs/PROJECT_STRUCTURE.md` planejavam (n8n para prototipar
rápido), o motor real da Fase 1 foi construído inteiramente em **Python** (`app/`, 2793 linhas, 8
módulos de motor + 5 suites de teste), rodando hoje como app Streamlit e, agora, também como API
FastAPI. Existe um `n8n/workflows/comex_conciliacao.json` (112 linhas) — é um esqueleto de referência,
não o motor de produção.

| Módulo | Função |
|---|---|
| `extracao.py` + `llm_extracao.py` | Extração de PDF/Excel/imagem; LLM (Gemini→OpenRouter) com fallback heurístico; divide invoices gigantes em blocos |
| `processamento.py` | Orquestra extração → conciliação Invoice×Packing List → classificação → flags regulatórios |
| `regras_documentais.py` | Coerência Invoice×BL (Incoterm/frete) — a jornada principal de auditoria pré-embarque |
| `regras_regulatorias.py` | Flags por palavra-chave (wi-fi→ANATEL etc.) |
| `rag.py` | Busca híbrida (lexical+semântica) com grounding obrigatório; sugestão de NCM |
| `rerank_ncm.py` | Rerank de NCM por LLM+RGI, cadeia de fallback multi-provedor (Gemini→OpenRouter), nunca trava |
| `worker_ncm.py` | Fila híbrida (Postgres como fila, `FOR UPDATE SKIP LOCKED`) para reranquear invoices grandes sob demanda |
| `orquestracao.py` | Máquina de estados idempotente do dossiê, unifica extração+regras+fila NCM+consolidação |
| `score_risco.py` | Índice de risco agregado dos apontamentos |
| `cti.py` | Cálculo de Custo Total de Importação |
| `ui.py` | App Streamlit (login, upload, conferência, revisão humana, trilha de auditoria) |

**Princípios não negociáveis do CLAUDE.md, verificados no código real:** grounding obrigatório
(`rag.py` nunca cita sem chunk recuperado), log append-only (`log_auditoria`, só INSERT), human-in-
-the-loop (todo apontamento nasce `pendente`, precisa de revisão), versionamento de norma por vigência.

## 3. Base normativa (Postgres/Supabase)

| Tabela | Conteúdo | Escala |
|---|---|---|
| `normas` | NCM (15.156, hierárquico), Soluções de Consulta (5.735), Tratamento Administrativo (99), RGI (6) — todos com embedding Voyage (1024d) | 20.998 linhas |
| `atributos_definicoes/vinculos` | Atributos DUIMP | 561 defs, 36.477 vínculos |
| `tributos_ncm` / `icms_uf` | Referência de alíquotas (não-oficial, `tax_calc.xlsx`) | 10.500 NCM, 27 UF |
| `dossie_item_status` | Fila/progresso do rerank de NCM em lote | migration 0007 |
| `dossies.estado_pipeline` / `resumo_consolidado` | Máquina de estados + resumo consolidado | migration 0008 |

**Índice pgvector HNSW** criado em `normas.embedding` (migration 0006) — busca semântica caiu de
~2826ms para ~134-464ms/item.

## 4. Segurança

Auditoria do repositório (08/07/2026): **limpa** — `.env` gitignorado, histórico (55+ commits) sem
nenhum padrão de secret, `.env.example` só placeholder. Credenciais só via variável de ambiente (nomes
exatos em [api/README.md](../api/README.md)). **Pendente de confirmação do dono:** rotação das
credenciais que vazaram nos anexos n8n antigos (`classificador_fiscal.txt`, `custos CTI.json` —
service_role Supabase, Gemini, OpenRouter).

## 5. Documentos desatualizados — precisam de decisão, não foram reescritos

`docs/PROJECT_STRUCTURE.md` e `docs/ROADMAP.md` descrevem um plano (Fase 1 = n8n, `app/` reservado
para Fase 2 em LangGraph, `api/` aninhado dentro de `app/`) que **não é o que foi construído**. Não
reescrevi esses documentos porque `CLAUDE.md` os trata como fonte de verdade sobre decisão de
arquitetura — mudar isso é uma decisão sua, não uma correção editorial minha. Duas opções:
(a) atualizar `ROADMAP.md`/`PROJECT_STRUCTURE.md` para refletir a realidade (motor Python desde o
início, n8n nunca usado em produção); ou (b) marcá-los explicitamente como "plano original,
superado — ver STATUS.md" e mantê-los como histórico. Recomendo (b): preserva o registro de decisão
sem fingir que o plano n8n nunca existiu.

`docs/PRD.md`, `docs/CUSTOMER_JOURNEY.md`, `docs/STAKEHOLDER_VISION.md`, `docs/DATA_SOURCES.md`,
`docs/ARCHITECTURE.md` (Fase 2/MAPA) não foram tocados — continuam corretos como documentos de Fase 2,
que segue não iniciada.

## 6. Próximos passos (ordem sugerida)

1. **Confirmar rotação de credenciais** (bloqueante de segurança, só o dono confirma) — segue
   pendente mesmo com a API e o site conectados.
2. **Configurar `API_TOKEN` no projeto Vercel** e confirmar que o `.vercelignore` novo entrou no
   próximo build (dashboard do Vercel — só o dono vê o log). Sem isso, o índice de confiança em
   `resultado.html?dossie_id=...` volta o erro 503 do proxy (fail-closed, não quebra o site).
3. **Decidir o destino de `ROADMAP.md`/`PROJECT_STRUCTURE.md`** (§5).
4. **Conectar o restante da jornada pública** (`simulacao.html`, `loading.html`) ao motor real
   (`app/processamento.py` via a mesma API), substituindo o `sessionStorage` mockado — hoje só
   `resultado.html` lê dado real, e só quando `?dossie_id=` aponta para um dossiê já consolidado
   (não existe ainda upload real de documento a partir do site público).
5. **Habilitar quota paga** (Gemini billing ou créditos OpenRouter) para o rerank de NCM em lote —
   hoje o free tier degrada ~71% dos itens para confiança baixa sob carga (ver
   [ncm_rerank_status] na memória da sessão).
6. Frente 2 (Cockpit completo / migração para FastAPI pleno) segue **pausada**, como decidido.

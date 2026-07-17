# STATUS.md — Estado real do projeto (atualizado 17/07/2026)

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

## 1b. Em andamento (09/07/2026) — Cockpit AI-native: Reconciliation Agent + auditoria imutável

Trabalho aprovado pelo dono em 09/07/2026 para transformar o site público de mock client-side em
motor real, com um Reconciliation Agent multinível e log de raciocínio real (não decorativo).
Plano completo em `C:\Users\Alexandre\.claude\plans\eventual-sleeping-locket-agent-a1e51d8e9c83b7e67.md`
(fora do repo, arquivo de planejamento local). Executado fase a fase, com checkpoint do dono entre
elas — ver progresso no início do plano.

**Concluído:**
- Migrations `0009`-`0012` aplicadas em produção: `apontamentos` ganhou `codigo`/
  `confianca_rotulo`/`confianca_pct`/`impacto_financeiro_texto`; `log_auditoria` agora tem um
  trigger real bloqueando UPDATE/DELETE (testado manualmente contra o Supabase real — antes era
  só convenção de código, sem enforcement); nova tabela `erp_catalogo_itens`.
- **Reconciliation Agent multinível** (`app/reconciliacao_erp.py`, ver §2 abaixo) — cascata de 3
  níveis pela disponibilidade real de dado (Triple Match com ERP / Regulatory Match sem ERP /
  Internal Consistency documental, que já rodava sempre). Decisão de nível narrada em
  `log_auditoria` (`nivel_reconciliacao_definido`) — fonte real do "log de raciocínio" da UI
  futura, não texto decorativo. Confiança da classificação agregada é capada
  (`confianca_rotulo="revisao_necessaria"`) quando não houve cruzamento com o ERP do cliente,
  mesmo com similaridade individual alta.
- Campo `pais_origem` extraído pela primeira vez (`extracao.py` regex + `llm_extracao.py` schema
  Gemini) para sustentar o novo achado `PAIS_ORIGEM_AUSENTE` em `regras_documentais.py`.

- **Loop de aprendizado mínimo** (`app/aprendizado.py`, **novo 10/07/2026** — exceção de escopo
  aprovada pelo dono, registrada em `CLAUDE.md` §8): `buscar_correcao_anterior(cliente_id, codigo)`
  procura a última correção humana real (não conta "aceitar" puro) para o mesmo cliente + mesmo
  tipo de achado, e `sugestao_texto` gera a frase "Da última vez você corrigiu de X para Y —
  aplicar de novo?", anexada ao `por_que_importa` do apontamento (tanto em
  `regras_documentais` quanto no Reconciliation Agent). **Não é fine-tuning nem retraining de
  embedding** — deliberadamente raso, ver `docs/STAKEHOLDER_VISION.md:66`.

**Decisão de produto tomada nesse trabalho:** o upload público (`POST /dossies`, ainda não
construído) vai exigir **login real** (reusa `app/auth.py::autenticar`), não um `cliente_id`
anônimo gerado no navegador — necessário para o Reconciliation Agent e o loop de aprendizado
fazerem sentido entre visitas do mesmo cliente.

- **Telemetria de progresso do worker de NCM** (`worker_ncm.py`, **novo 10/07/2026**, pedido
  estratégico do dono para a Fase 3 — "nunca deixar o log de raciocínio em silêncio durante um
  lote grande"): evento `classificacao_ncm_progresso` em `log_auditoria` a cada
  `NCM_PROGRESSO_A_CADA` itens (default 25, env-configurável) POR DOSSIÊ, mais um evento forçado
  quando a fila do dossiê esvazia — telemetria proporcional ao volume (não um evento por item,
  que inundaria a auditoria num lote de milhares; não silêncio até o fim). Testado com
  `app/test_worker_ncm_progresso.py` (monkeypatcha `rag.sugerir_ncm`, sem chamada de LLM real).

- **Fase 3 backend CONCLUÍDA e verificada AO VIVO** (10/07/2026, contra o Supabase de produção
  real, com extração por Gemini de verdade — não mock): `api/main.py` ganhou `POST /auth/login`
  (sessão HMAC, reusa `app/auth.py::autenticar`), **`POST /dossies`** (primeiro endpoint que deixa
  alguém de fato subir Invoice/Packing List/BL/catálogo ERP e disparar `app/orquestracao.py` — até
  aqui só o Streamlit interno processava dossiês de verdade), e `GET /dossies/{id}/estado|eventos|
  apontamentos` (protegidos pelo `API_TOKEN` de serviço, como `/resumo`). `api/requirements.txt`
  ganhou `pdfplumber`/`openpyxl`/`xlrd`/`PyYAML` (a API agora importa `app/processamento.py` de
  verdade). Proxies Vercel novos: `api/estado.js`, `api/eventos.js`, `api/apontamentos.js` (clones
  de `resumo.js`) — `POST /dossies` propositalmente NÃO passa por proxy (limite de payload da
  Vercel para PDF; autenticado pelo token de sessão, não pelo `API_TOKEN` de serviço).
  **Verificação ao vivo**: upload de uma invoice sintética → passou por
  recebido→extraindo→regras_documentais_ok→classificando_ncm→consolidando→concluido_com_excecoes
  em ~100s reais (extração LLM real), `GET /eventos` devolveu a trilha inteira narrada em pt-BR
  (incl. `nivel_reconciliacao_definido` com a narrativa do Reconciliation Agent), e
  `GET /apontamentos` trouxe o achado de classificação com `confianca_rotulo="revisao_necessaria"`
  — a ponderação por ausência de ERP (§ acima) funcionando de ponta a ponta, não só em teste
  isolado. `app/test_orquestracao.py` novo (round-trip com `rag.sugerir_ncm` monkeypatchado,
  sem rede) cobre a máquina de estados em CI/regressão sem depender de LLM real.

- **Fase 3 frontend CONCLUÍDA e verificada em browser real** (10/07/2026, Playwright headless
  contra a API local + um servidor estático replicando os proxies Vercel): `login.html` **novo** —
  formulário simples, chama `POST /auth/login`, guarda a sessão em `localStorage`. `simulacao.html`
  ganhou um gate de login (redireciona para `login.html` sem sessão válida), um campo **"Contexto
  do cliente"** novo, e o submit agora faz upload real (`FormData` → `POST /dossies` com o Bearer
  da sessão) em vez de só gravar `sessionStorage`. `loading.html` faz polling real de
  `/api/estado` + `/api/eventos` (a cada ~1,5s) e renderiza o log de raciocínio verdadeiro —
  removido o `setTimeout` decorativo antigo. `resultado.html` busca `/api/apontamentos` +
  `/api/eventos` e renderiza achados reais com badge de confiança, citação e impacto quando
  existirem; o modo de pré-visualização local (sem `?dossie_id=`) permanece como fallback isolado,
  nunca mais misturado com dado real (bug corrigido no caminho: `score_risco` é um objeto
  estruturado, não um número solto — o `typeof === 'number'` antigo silenciosamente nunca
  disparava).
  **Verificado em 3 cenários reais no browser**: (a) upload intercept confirma o POST /dossies sai
  com multipart + Bearer corretos; (b) `loading.html` aberto num dossiê já concluído redireciona
  corretamente para `resultado.html`; (c) `resultado.html` renderiza os 2 achados reais do dossiê
  de teste (`COERENCIA_NAO_AVALIADA` info + classificação com badge "revisão necessária" roxo) e a
  trilha completa narrada. Screenshots confirmaram visualmente — sem números fabricados, sem texto
  contraditório entre os painéis do topo e os achados reais.

## 1c. Supabase Auth real + todos os botões funcionais (11/07/2026)

Pedido explícito do dono: "todos os botões que inserirmos devem estar funcionais... todo o
processo até fase 3 funcional" + registro via Supabase Auth. Isso **substituiu** a sessão HMAC
custom criada um dia antes (§1b) — não coexistem duas identidades para o site público.

**Mudança de arquitetura de identidade:** `login.html`/`registro.html` agora falam DIRETO com o
Supabase Auth (`POST {SUPABASE_URL}/auth/v1/signup` e `/auth/v1/token?grant_type=password`),
usando a chave publicável (`sb_publishable_...`, já existente em `.env` como
`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, nunca usada até agora). `api/main.py` removeu inteiramente
o HMAC (`_criar_token`/`_verificar_token`/`POST /auth/login`) — `exigir_sessao_cliente` agora
introspecciona o `access_token` contra `GET {SUPABASE_URL}/auth/v1/user` (via `httpx`, já
dependência existente) e usa `user.id` do Supabase como `cliente_id`. O login interno do time
(`app/auth.py`, `APP_USERS`, Streamlit) não foi tocado — são identidades separadas por design.

**Botões antes decorativos, agora reais** (`resultado.html`): cada card de achado ganhou
"Aceitar" (1 clique) e "Corrigir" (formulário inline com valor+justificativa), chamando
`POST /dossies/{id}/apontamentos/{apontamento_id}/revisao` (novo). O painel "Parecer do Cockpit"
ganhou "Aceitar todos" / "Escalar" / "Travar avanço", chamando `POST /dossies/{id}/decisao`
(novo) — `db.decidir_dossie()` aceita todos os pendentes e conclui, ou muda o status do dossiê
para `escalado`/`travado` com o motivo registrado em `log_auditoria`. Ambos os endpoints
verificam posse (`db.obter_dossie(dossie_id, cliente_id)`/apontamento pertence ao dossiê) — 404
para quem não é dono, nunca vaza achado de outro cliente.

**Verificação realizada e uma limitação real, honesta:**
- Signup real contra o Supabase de produção: confirmado funcionando (curl direto ao endpoint).
- Login de usuário não confirmado: erro correto (`email_not_confirmed`), tratado com mensagem
  clara em `login.html`.
- Token forjado contra `POST /dossies/.../decisao` real: 401 correto (introspecção Supabase real
  rejeitou).
- Lógica de `db.decidir_dossie`/`registrar_revisao`/isolamento por cliente: testada via
  `app/test_revisao_dossie.py` (round-trip real no Postgres).
- Lógica dos ENDPOINTS (parsing, validação, isolamento 404/400): testada via `TestClient` do
  FastAPI com `dependency_overrides` (sem depender do Supabase confirmado) — todos os casos
  passaram.
- Browser real (Playwright): `resultado.html` sem sessão mostra os 3 botões globais
  `disabled` + hint "Entre com sua conta..."; clicar num botão por-card sem sessão redireciona
  para `login.html`; `registro.html`↔`login.html` linkam entre si. Zero erros de console.
- **Limitação não resolvida**: o projeto Supabase exige confirmação de e-mail para novos
  cadastros — não há como completar um clique real "criar conta → confirmar e-mail → logar →
  clicar Aceitar" de ponta a ponta sem acesso a uma caixa de entrada real ou a
  `SUPABASE_SERVICE_ROLE_KEY` (não disponível neste ambiente). A lógica de cada camada foi
  verificada isoladamente (acima), mas o clique-a-clique completo com uma conta nova e confirmada
  ainda não foi presenciado por mim — só pelo dono, quando testar manualmente.

`app/test_revisao_dossie.py` novo — regressão completa (12 arquivos `app/test_*.py`) passando.

## 1d. Cockpit do Despachante — dashboard pós-login + classificação fiscal + custeio VMLD + feed normativo real (16-17/07/2026)

Pedido do dono em 16/07/2026: o login não pode mais cair direto na simulação — passa a existir um
**dashboard (cockpit)** como hub, com a simulação virando uma das funcionalidades, mais duas
features novas (classificação fiscal sob demanda e calculadora de custeio de importação VMLD) e um
feed normativo com **fontes reais** (DOU e notícias de comex). Mockups TradeGuard AI fornecidos
pelo dono foram adaptados à marca Despachante de Bolso, em pt-BR, e **sem nenhum número fabricado**
— todo widget ou é dado real ou é estado vazio honesto (os KPIs/tabelas fictícios dos mockups não
foram reproduzidos).

**Backend novo em `api/main.py` (todos verificados contra o banco/LLM reais):**
- `GET /noticias` — feed normativo real, público, cache em memória TTL 30min (`api/noticias.py`):
  DOU Seção 1 lido da Imprensa Nacional (`in.gov.br/leiturajornal`, JSON embutido na página
  oficial, recua até 3 dias para fim de semana) filtrado para comex por órgão
  (SECEX/GECEX/Receita) + palavras-chave aduaneiras; RSS gov.br do MDIC e da Receita Federal
  entram inteiros. O payload relata o status real de cada fonte (`fontes: {ok, itens|erro}`) — a
  UI mostra "fora do ar" quando uma coleta falha, nunca preenche com conteúdo inventado.
  Verificado ao vivo: 58 itens reais (44 DOU + 4 MDIC + 10 RFB), incl. Portaria SECEX nº 523 de
  15/07/2026.
- `GET /dossies` — lista os dossiês do cliente logado (sessão Supabase), só campos de resumo.
- `POST /classificacao` — classificação fiscal sob demanda: descrição → `rag.sugerir_ncm` (mesma
  cadeia do motor: HNSW top-25 + rerank LLM+RGI) + anuência (`anuencia_por_ncm`) + alíquotas
  (`tributos_por_ncm`). Verificado ao vivo: "fonte de alimentação chaveada 850W" → 8504.40.40,
  confiança alta, RGI 1 e 6, anuência ANATEL real do Tratamento Administrativo.
- `POST /custeio` — calculadora VMLD: `cti.calcular_cti` (módulo puro já existente) com alíquotas
  reais de `tributos_ncm`/`icms_uf` (com `data_referencia` exposta). **Abstém com 422** quando o
  NCM não está na referência — nunca inventa alíquota (CLAUDE.md §4). Verificado ao vivo.

**Frontend novo (Tailwind CDN + shell compartilhado `assets/comum.js`/`cockpit-tema.js`/`cockpit.css`):**
- `cockpit.html` — dashboard pós-login: KPIs calculados dos dossiês reais (em processamento / com
  exceções / travadas-escaladas), operações recentes, radar normativo com contagem real, status
  real das fontes coletadas, atalhos de ferramentas, trilha da última operação (via proxy
  `/api/eventos`, com fallback honesto quando indisponível).
- `classificacao.html` — busca por descrição, NCM sugerido com badge de confiança, justificativa
  RGI, candidatos com similaridade, anuência, alíquotas, histórico local e ponte "usar no custeio".
- `custeio.html` — formulário (NCM/UF/modal/preço/qtde/câmbio/frete/seguro opcionais) →
  detalhamento completo (VMLE→VMLD/CIF→II/IPI/PIS/COFINS/ICMS por dentro/AFRMM/Siscomex), aceita
  `?ncm=` vindo da classificação.
- `feed.html` — feed com filtros por fonte + busca, links para a fonte oficial, painel de status
  de coleta.
- `processos.html` — lista completa de dossiês com filtro por situação e busca, links para
  resultado/trilha.
- `login.html`/`registro.html` — redirecionam para `/cockpit.html` (antes `/simulacao.html`) e
  guardam o e-mail na sessão para o topbar.

**Verificação (17/07/2026):** endpoints testados com `TestClient` + override de sessão (mesmo
padrão de `app/test_*`) contra o Supabase real; telas verificadas em browser real servidas por
API local com o mesmo override (sessão real continua bloqueada pela confirmação de e-mail, §1c),
usando o cliente de teste com 3 dossiês reais — KPIs, tabelas, filtros, gate de login
(sem sessão → `/login.html?next=...`) e zero erros de console. `.venv/` local criado (gitignorado).
**Nota de escopo:** isto NÃO é o "dashboard executivo" vetado em CLAUDE.md §8 (BI/upsell) — é o
cockpit operacional do usuário, pedido explicitamente pelo dono. O dono sinalizou que "a estrutura
vem em seguida" (automações/estruturas de dados adicionais para alimentar o feed e as telas).

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
| `regras_documentais.py` | Coerência Invoice×BL (Incoterm/frete/**país de origem ausente**, novo 09/07) — a jornada principal de auditoria pré-embarque |
| `regras_regulatorias.py` | Flags por palavra-chave (wi-fi→ANATEL etc.) |
| `rag.py` | Busca híbrida (lexical+semântica) com grounding obrigatório; sugestão de NCM |
| `rerank_ncm.py` | Rerank de NCM por LLM+RGI, cadeia de fallback multi-provedor (Gemini→OpenRouter), nunca trava |
| `worker_ncm.py` | Fila híbrida (Postgres como fila, `FOR UPDATE SKIP LOCKED`) para reranquear invoices grandes sob demanda |
| `erp_catalogo.py` | **Novo (09/07).** Parse CSV/XLSX do catálogo ERP do cliente (casamento flexível de coluna) + import/lookup no banco |
| `reconciliacao_erp.py` | **Novo (09/07).** Reconciliation Agent — cascata Triple Match/Regulatory Match/Internal Consistency pela disponibilidade real de dado |
| `aprendizado.py` | **Novo (10/07).** Loop de aprendizado mínimo — lookup de correção humana anterior por cliente+tipo de achado, não fine-tuning |
| `orquestracao.py` | Máquina de estados idempotente do dossiê, unifica extração+regras+reconciliação ERP+fila NCM+consolidação (capa confiança quando não há Triple Match) |
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
| `apontamentos.codigo/confianca_rotulo/confianca_pct/impacto_financeiro_texto` | Identificador estável do achado + confiança/impacto estruturados | migration 0009 |
| `log_auditoria` (trigger) | Append-only **enforçado no banco** (antes só convenção de código) | migration 0010 |
| `erp_catalogo_itens` | Catálogo mestre do cliente (SKU/part number × NCM × descrição), base do Reconciliation Agent | migration 0011 |

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
   (`app/processamento.py`/`app/orquestracao.py` via a mesma API), substituindo o `sessionStorage`
   mockado — hoje só `resultado.html` lê dado real, e só quando `?dossie_id=` aponta para um
   dossiê já consolidado (não existe ainda upload real de documento a partir do site público). Em
   andamento (ver §1b): próximo passo imediato é `app/aprendizado.py` (lookup de correção
   anterior), depois `POST /auth/login` + `POST /dossies` em `api/main.py` e um `login.html` novo
   (upload público vai exigir login real, decisão tomada em 09/07/2026).
5. **Habilitar quota paga** (Gemini billing ou créditos OpenRouter) para o rerank de NCM em lote —
   hoje o free tier degrada ~71% dos itens para confiança baixa sob carga (ver
   [ncm_rerank_status] na memória da sessão).
6. Frente 2 (Cockpit completo / migração para FastAPI pleno) segue **pausada**, como decidido.

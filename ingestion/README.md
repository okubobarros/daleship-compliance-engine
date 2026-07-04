# Pipeline de Ingestão Normativa

Popula a tabela `normas` (base do RAG) de forma **genérica e dirigida por configuração**,
parametrizada por órgão. Adicionar um órgão ou fonte novos = novo bloco em `config/*.yaml`,
**não** código novo.

## Estrutura

- `config/` — fontes descritas em YAML (uma entrada por fonte normativa).
  - `fontes_comex.yaml` — Frente 2: bases de comex (TEC/NCM, RGI, Soluções de Consulta, Tratamento Administrativo, Acordos). Independem da escolha de órgão anuente.
  - `fontes_anuencia.yaml` — LPCO por órgão anuente. Escopo inicial Anvisa + MAPA (ambos `bloqueado: true` até o Bonano confirmar o perfil de mercadoria). Inmetro/Ibama/Anatel/ANP/Exército já listados como bloqueados para deixar claro que expandir = destravar config.
  - `fontes_teste.yaml` — teste de fumaça com dado sintético.
- `loaders.py` — loaders plugáveis: `file` (JSON verificado em `seeds/`) e `http` (stub — não ingere conteúdo não verificado).
- `pipeline.py` — orquestrador: config → loader → upsert versionado em `normas` com provenance.
- `models.py` — `FonteConfig`, `UnidadeNormativa`.
- `seeds/` — texto normativo já coletado e **verificado**, em JSON, consumido pelo loader `file`.

## Rodar

```bash
mcp-server/.venv/Scripts/python.exe ingestion/pipeline.py ingestion/config/fontes_comex.yaml
```

## Princípios embutidos (CLAUDE.md §4)

- **Grounding**: só entra na base conteúdo verificado. O loader `http` é stub proposital — buscar e parsear site governamental sem conferência humana violaria o princípio de citação confiável.
- **Versionamento por vigência**: texto igual = idempotente (skip); texto mudou = fecha a vigência antiga (`data_vigencia_fim`) + insere nova versão; nunca sobrescreve.
- **Provenance**: toda unidade carrega `orgao`, `tipo_documento`, `identificador`, `fonte_url`, `data_vigencia_inicio`.

## Embeddings

- Provedor fechado: **Voyage AI, modelo `voyage-law-2`** (especialização jurídica, dim **1024**, contexto 16k, free tier 50M tokens). Cliente em `mcp-server/src/embeddings.py` (camada compartilhada).
- A coluna `normas.embedding` é `VECTOR(1024)` (migration `infra/migrations/0001_...`). Sem `VOYAGE_API_KEY`, o pipeline usa `NullEmbedder` (embedding NULL) e a busca degrada para lexical — nunca inventa fonte.
- A busca é **híbrida** (lexical + semântica combinadas em `rag_search`), nunca uma substituindo a outra. O caminho semântico tem **limiar de distância** (`DISTANCIA_MAXIMA` em `rag_search.py`, provisório 0.65) para não "citar" o vizinho mais próximo quando a query está fora do domínio — recalibrar com o golden eval set.
- **Rate limit**: o que morde no free tier da Voyage é o **TPM (~10K tokens/min)**, não o RPM. O cliente faz throttle por **janela deslizante de TPM** (`_LimitadorTPM`), então qualquer carga completa sem 429 — só mais devagar. No free tier, ~2,4M tokens (todas as Soluções de Consulta) levam ~4h; com billing (env `VOYAGE_TPM`/`VOYAGE_TOKEN_BUDGET_LOTE` altos) cai para minutos. Fontes de consulta por código exato (NCM) usam `sem_embedding: true` (lexical, sem gastar Voyage); embedding fica reservado a normas em prosa, onde a semântica agrega.

## Estado da base (Frente 2)

- **NCM** (`loader: ncm_json`, `sem_embedding: true`): 15.156 códigos indexados, lexical (consulta por código). Health-check da parada programada 01:00–03:00 embutido.
- **RGI** (`loader: rgi_nesh`): 6 regras extraídas da NESH (IN RFB 2.169/2023), com embedding — busca híbrida verificada. O loader resolve o PDF vigente na página (não assume o nome) e detecta a seção RGI dinamicamente.
- **Soluções de Consulta** (`loader: sijut2_sc`): coleta as ementas direto da listagem do SIJUT2 (~100 atos/página, paginação GET `p=N`, total lido da página). Filtro client-side pelo campo oficial `Assunto:` (config `params.filtro_assunto`, hoje "Classificação de Mercadorias" — o que o ComexPilot pede). Cada ato entra com **permalink próprio** (`link.action?idAto=N`) como `fonte_url`. Particularidades do HTML tratadas: `idAto` só existe dentro de comentários HTML; comentários duplicam `<td>`s (remover antes de parsear, senão desloca colunas); republicações do mesmo ato (mesmo identificador, `idAto` novo) — mantém-se a publicação mais recente para nunca gerar dois vigentes no mesmo lote.

## Pendências / próxima fila

- **Tratamento Administrativo** (gov.br/siscomex Plone) — próximo loader da fila. (Acordos saiu do escopo Fase 1 — não aciona anuência.)
- **Anuência Anvisa/MAPA**: desbloqueadas, mas ainda com loader `http` — falta o coletor da legislação de LPCO por NCM/procedimento.
- **Fontes bloqueadas (robots.txt)**: NÃO fazer scraping em `siscomex.desenvolvimento.gov.br`. Usar as alternativas em `gov.br/siscomex` (ver comentários em `config/fontes_comex.yaml`).

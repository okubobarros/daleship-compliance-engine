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
- A busca é **híbrida** (lexical + semântica combinadas em `rag_search`), nunca uma substituindo a outra.

## Pendências / próxima fila de loaders

- **NCM (loader `ncm_json`)**: implementado com health-check da parada programada. A coleta real depende do Portal Único estar fora da janela 01:00–03:00, e da conferência dos nomes de campo do payload na primeira execução.
- **Loader `http`** (ainda stub) para, nesta ordem: **RGI → Soluções de Consulta → Tratamento Administrativo → Acordos**. Cada uma precisa de coletor + verificação, salvando em `seeds/` (loader `file`) ou implementando o fetch dedicado.
- **Anuência Anvisa/MAPA**: desbloqueadas, mas ainda com loader `http` — falta o coletor da legislação de LPCO por NCM/procedimento.
- **Fontes bloqueadas (robots.txt)**: NÃO fazer scraping em `siscomex.desenvolvimento.gov.br`. Usar as alternativas em `gov.br/siscomex` (ver comentários em `config/fontes_comex.yaml`).

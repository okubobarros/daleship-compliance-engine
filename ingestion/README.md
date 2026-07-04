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

## Pendências conhecidas

- **Embeddings**: a coluna `embedding VECTOR(1536)` fica NULL até a escolha do provedor de embedding (Voyage/OpenAI/local — Claude não gera embedding). A busca lexical do `rag_search` já funciona sem isso. A dimensão 1536 é suposição a revisar quando o provedor for definido.
- **Loader `http`**: implementar coleta + chunking por unidade normativa + etapa de verificação para cada fonte da Frente 2 (hoje todas com `loader: http`, portanto ainda não populam a base — precisam de coleta manual → `seeds/` → `loader: file`, ou do loader `http` real).

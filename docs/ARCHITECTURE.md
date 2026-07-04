# Arquitetura Técnica — MVP Motor de Conformidade (Registro de Defensivos)

> **Nota de escopo (ver CLAUDE.md, seção 5):** este documento descreve a Fase 2 do projeto (MAPA/Anvisa/Ibama — defensivos e bioinsumos). A Fase 1 atual é Comex — consulte `docs/ROADMAP.md` e `docs/MVP_PRODUCT_SPEC.md` para o escopo em execução agora.

**Referência:** PRD.md
**Objetivo deste documento:** guiar a construção via Claude Code, com decisões técnicas já tomadas para evitar retrabalho de discussão durante a implementação.

---

## 1. Stack

| Camada | Escolha | Por quê |
|---|---|---|
| Orquestração de agentes | **LangGraph** | Modela o pipeline como grafo de estados com checkpoints, retry e interrupção para human-in-the-loop — necessário para a trilha auditável |
| Banco vetorial | **pgvector (dentro do Postgres)** | Volume do MVP não justifica vetorial dedicado; um único banco simplifica auditoria/LGPD |
| Banco relacional | **Postgres** | Dossiês, log de auditoria, correções humanas |
| Armazenamento de documentos brutos | **Filesystem local no MVP** → migrar para S3-compatible depois | Sem necessidade de infraestrutura cloud no estágio de demo |
| Modelo de LLM | **Um único modelo forte** (Claude, via API) | Roteamento dinâmico multi-modelo é otimização de Fase 2, não necessária para provar a tese no MVP |
| Backend | **Python** (FastAPI) | Padrão para LangGraph e bibliotecas de RAG |
| Frontend do MVP | **Interface mínima** (React simples ou até Streamlit para acelerar) | Objetivo é validar o núcleo de raciocínio, não polir produto ainda |

## 2. Grafo de agentes (LangGraph)

```
[Entrada: dossiê do usuário]
        │
        ▼
┌─────────────────────┐
│ Nó 1: Extração       │  → extrai campos estruturados do dossiê
│ (ingrediente ativo,  │     (documento → JSON estruturado)
│  formulação, dados)  │
└─────────┬────────────┘
          ▼
┌─────────────────────┐
│ Nó 2: Recuperação    │  → RAG híbrido (lexical + semântico) sobre
│ normativa (RAG)      │     Agrofit + normas MAPA/Anvisa/Ibama
└─────────┬────────────┘
          ▼
┌─────────────────────┐
│ Nó 3: Verificação    │  → cruza dados extraídos com exigências
│ e cruzamento         │     recuperadas; identifica lacunas
└─────────┬────────────┘
          ▼
┌─────────────────────┐
│ Nó 4: Classificação  │  → rotula cada lacuna por órgão responsável
│ por órgão            │     (MAPA / Anvisa / Ibama)
└─────────┬────────────┘
          ▼
┌─────────────────────┐
│ Nó 5: Justificativa  │  → monta explicação citando fonte exata
│ explicável           │     (nunca aceita citação sem chunk de origem)
└─────────┬────────────┘
          ▼
┌─────────────────────┐
│ INTERRUPT: revisão   │  → LangGraph interrupt/resume — pausa para
│ humana obrigatória   │     humano validar/corrigir antes de finalizar
└─────────┬────────────┘
          ▼
┌─────────────────────┐
│ Nó 6: Registro de    │  → grava correção estruturada + log auditável
│ correção e log       │     (append-only)
└──────────────────────┘
```

**Princípio de design não negociável:** o Nó 5 nunca produz uma afirmação que não tenha um chunk de origem recuperado no Nó 2 anexado. Se não houver fonte, o sistema sinaliza "sem base normativa localizada" em vez de inventar.

## 3. Esquema de dados (Postgres)

```sql
-- Base normativa indexada (fonte de verdade para RAG)
CREATE TABLE normas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    orgao TEXT NOT NULL,              -- 'MAPA' | 'ANVISA' | 'IBAMA'
    tipo_documento TEXT NOT NULL,     -- 'IN' | 'monografia' | 'resolucao' etc.
    identificador TEXT NOT NULL,      -- ex: 'IN SDA 36/2009'
    texto TEXT NOT NULL,
    embedding VECTOR(1536),
    data_vigencia_inicio DATE NOT NULL,
    data_vigencia_fim DATE,           -- NULL = ainda vigente
    fonte_url TEXT,
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Precedentes do Agrofit (produtos já registrados)
CREATE TABLE precedentes_agrofit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingrediente_ativo TEXT NOT NULL,
    nome_comercial TEXT,
    formulacao TEXT,
    classe_toxicologica TEXT,
    dados_brutos JSONB,               -- payload completo capturado do Agrofit
    atualizado_em TIMESTAMPTZ DEFAULT now()
);

-- Dossiês submetidos pelos usuários (clientes)
CREATE TABLE dossies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id UUID NOT NULL,
    ingrediente_ativo TEXT NOT NULL,
    dados_extraidos JSONB NOT NULL,
    status TEXT NOT NULL,             -- 'em_analise' | 'revisao_humana' | 'concluido'
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Apontamentos gerados pelo sistema
CREATE TABLE apontamentos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossie_id UUID REFERENCES dossies(id),
    orgao TEXT NOT NULL,
    descricao TEXT NOT NULL,
    norma_citada_id UUID REFERENCES normas(id),
    status TEXT NOT NULL,             -- 'pendente' | 'validado' | 'corrigido'
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Correções humanas (o ativo de dado proprietário)
CREATE TABLE correcoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    apontamento_id UUID REFERENCES apontamentos(id),
    valor_sugerido TEXT,
    valor_corrigido TEXT,
    justificativa_analista TEXT,
    autor TEXT NOT NULL,
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Log de auditoria append-only (nunca UPDATE ou DELETE)
CREATE TABLE log_auditoria (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossie_id UUID REFERENCES dossies(id),
    evento TEXT NOT NULL,
    detalhe JSONB,
    criado_em TIMESTAMPTZ DEFAULT now()
);
```

## 4. RAG — detalhes de implementação

- **Chunking**: por unidade normativa (artigo/inciso), não por página — precisão de citação exige granularidade fina.
- **Metadado obrigatório por chunk**: `orgao`, `identificador`, `data_vigencia_inicio`, `data_vigencia_fim`.
- **Recuperação híbrida**: busca lexical (por nome de ingrediente ativo, número de IN) + busca vetorial semântica combinadas, porque busca puramente vetorial erra em código/número exato.
- **Reranking**: aplicar reranking sobre os top-N resultados antes de passar ao Nó 5, para reduzir ruído.
- **Nunca sem fonte**: se a recuperação não retornar chunk com confiança mínima, o Nó 5 deve sinalizar ausência de base normativa em vez de gerar afirmação sem grounding.

## 5. O que explicitamente não construir no MVP

- Roteamento dinâmico entre múltiplos LLMs por complexidade — usar um modelo único forte.
- Integração automática com SISPA — sem API pública conhecida; mapear estrutura manualmente.
- Vetorial dedicado (Pinecone/Qdrant/Weaviate) — pgvector é suficiente neste volume.
- Multi-tenancy robusto — MVP pode rodar em ambiente único de demonstração controlada.
- Autenticação enterprise (SSO etc.) — autenticação simples é suficiente para design partners.

## 6. Ordem de implementação sugerida para o Claude Code

1. Setup do Postgres + pgvector, criação do schema (seção 3).
2. Script de ingestão da base normativa (Agrofit + IN SDA + monografias Anvisa + normas Ibama) → popular tabela `normas` e `precedentes_agrofit`.
3. Nó 1 (extração) e Nó 2 (RAG) do grafo LangGraph, testados isoladamente antes de integrar.
4. Nó 3, 4, 5 (verificação, classificação, justificativa) — testar com 1 ingrediente ativo apenas.
5. Interrupt/resume do LangGraph para revisão humana (Nó de interrupção).
6. Interface mínima de revisão (pode ser Streamlit no MVP).
7. Nó 6 (registro de correção + log auditável).
8. Teste end-to-end com dossiê real de um produto já registrado (comparar contra resultado conhecido).

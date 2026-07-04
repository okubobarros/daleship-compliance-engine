-- Schema Fase 1 (Comex-demo), adaptado do schema definitivo em docs/ARCHITECTURE.md
-- (que é escopo Fase 2/defensivos, mas a decisão de stack/schema vale como destino final
-- também para a Fase 1, ver CLAUDE.md secao 5). Omite `precedentes_agrofit`, que é
-- específica de defensivos/Agrofit e não se aplica a comex.
--
-- Rodar no SQL Editor do Supabase (dashboard do projeto) ou via psql com DATABASE_URL.

CREATE EXTENSION IF NOT EXISTS vector;

-- Base normativa indexada (fonte de verdade para RAG) — comex nesta fase
CREATE TABLE IF NOT EXISTS normas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    orgao TEXT NOT NULL,              -- 'RFB' | 'ANVISA' | 'MAPA' | 'INMETRO' | 'IBAMA' | 'ANATEL' | 'ANP' | 'EXERCITO' etc.
    tipo_documento TEXT NOT NULL,     -- 'IN' | 'TEC' | 'solucao_consulta' | 'tratamento_administrativo' | 'acordo_comercial' etc.
    identificador TEXT NOT NULL,
    texto TEXT NOT NULL,
    -- NOTA: dimensão baseline 1536 é histórica. A decisão de embedding fechou em Voyage
    -- voyage-law-2 (1024). Após aplicar este schema, rode infra/apply_migrations.py —
    -- a migration 0001 ajusta esta coluna para VECTOR(1024). Não editar direto em produção.
    embedding VECTOR(1536),
    data_vigencia_inicio DATE NOT NULL,
    data_vigencia_fim DATE,           -- NULL = ainda vigente
    fonte_url TEXT,
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Dossiês (processos de importação) submetidos pelos clientes
CREATE TABLE IF NOT EXISTS dossies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id UUID NOT NULL,
    dados_extraidos JSONB NOT NULL,
    status TEXT NOT NULL,             -- 'em_analise' | 'revisao_humana' | 'concluido'
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Apontamentos gerados pelo sistema (divergência/lacuna, com citação obrigatória)
CREATE TABLE IF NOT EXISTS apontamentos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossie_id UUID REFERENCES dossies(id),
    orgao TEXT NOT NULL,
    descricao TEXT NOT NULL,
    norma_citada_id UUID REFERENCES normas(id),
    status TEXT NOT NULL,             -- 'pendente' | 'validado' | 'corrigido'
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Correções humanas (o ativo de dado proprietário)
CREATE TABLE IF NOT EXISTS correcoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    apontamento_id UUID REFERENCES apontamentos(id),
    valor_sugerido TEXT,
    valor_corrigido TEXT,
    justificativa_analista TEXT,
    autor TEXT NOT NULL,
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Log de auditoria append-only (nunca UPDATE ou DELETE)
CREATE TABLE IF NOT EXISTS log_auditoria (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossie_id UUID REFERENCES dossies(id),
    evento TEXT NOT NULL,
    detalhe JSONB,
    criado_em TIMESTAMPTZ DEFAULT now()
);

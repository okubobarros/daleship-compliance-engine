-- Schema Fase 2 (MAPA/Bioinsumos) — ESTENDIDO a partir do que já está vivo na Fase 1
-- (normas, dossies, documentos, apontamentos, correcoes, log_auditoria + migrations 0001/0002).
--
-- NÃO APLICAR DIRETO EM PRODUÇÃO: quando a Fase 2 ativar, converter os deltas em migrations
-- formais (infra/migrations/000N_*.sql, runner infra/apply_migrations.py) — mesma disciplina
-- da migration 0001. Este arquivo é a REFERÊNCIA consolidada do destino.
--
-- Generalizações deliberadas (mesmo espírito do tipo_documento_transporte B/L/AWB/CRT):
--  * `orgao` é TEXT + tabela de referência `orgaos_anuentes` (MAPA/Anvisa/Ibama/ICMBio/...)
--    — órgão novo = INSERT, não migration.
--  * `dossies.setor` — o mesmo motor serve comex/defensivos/bioinsumos (CLAUDE.md §1).
--  * `precedentes` substitui `precedentes_agrofit` (ARCHITECTURE §3): Agrofit vira UMA fonte
--    (`fonte='agrofit'`), não a tabela inteira — outra base de precedente = INSERT.
--  * Classificação NUNCA é campo único definitivo: `apontamento_candidatos` guarda a lista
--    RANQUEADA (prováveis + alternativas, "verifique") — padrão validado na sugestão de NCM.

CREATE EXTENSION IF NOT EXISTS vector;

-- Órgãos anuentes/reguladores (referência extensível; NÃO usar CHECK hardcoded em `orgao`)
CREATE TABLE IF NOT EXISTS orgaos_anuentes (
    sigla TEXT PRIMARY KEY,           -- 'MAPA' | 'ANVISA' | 'IBAMA' | 'ICMBIO' | ...
    nome TEXT NOT NULL,
    criado_em TIMESTAMPTZ DEFAULT now()
);
INSERT INTO orgaos_anuentes (sigla, nome) VALUES
    ('MAPA',   'Ministério da Agricultura e Pecuária'),
    ('ANVISA', 'Agência Nacional de Vigilância Sanitária'),
    ('IBAMA',  'Instituto Brasileiro do Meio Ambiente e dos Recursos Naturais Renováveis'),
    ('ICMBIO', 'Instituto Chico Mendes de Conservação da Biodiversidade')
ON CONFLICT (sigla) DO NOTHING;

-- Base normativa indexada (IGUAL à Fase 1 — mesma tabela, mesma disciplina).
-- ATENÇÃO: VECTOR(1024) = voyage-law-2 (migration 0001), NÃO os 1536 do ARCHITECTURE.md.
-- Versionamento por vigência: mudança fecha data_vigencia_fim e INSERE nova linha. Nunca UPDATE do texto.
CREATE TABLE IF NOT EXISTS normas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    orgao TEXT NOT NULL,
    tipo_documento TEXT NOT NULL,     -- 'IN' | 'monografia' | 'resolucao' | 'NCM' | ...
    identificador TEXT NOT NULL,
    texto TEXT NOT NULL,
    embedding VECTOR(1024),
    data_vigencia_inicio DATE NOT NULL,
    data_vigencia_fim DATE,           -- NULL = vigente
    fonte_url TEXT,
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Precedentes (GENERALIZAÇÃO de precedentes_agrofit): produtos/registros já aprovados,
-- de qualquer fonte, para cruzamento no Nó 3. Campos específicos ficam em `atributos`.
CREATE TABLE IF NOT EXISTS precedentes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    setor TEXT NOT NULL,              -- 'defensivos' | 'bioinsumos' | ...
    fonte TEXT NOT NULL,              -- 'agrofit' | ...
    chave_busca TEXT NOT NULL,        -- ex.: ingrediente ativo (índice de consulta principal)
    atributos JSONB,                  -- ex.: formulacao, classe_toxicologica (era coluna fixa)
    dados_brutos JSONB,               -- payload completo capturado da fonte
    embedding VECTOR(1024),
    atualizado_em TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_precedentes_chave ON precedentes(setor, chave_busca);

-- Dossiês (Fase 1 + setor). Campos específicos do domínio (ingrediente_ativo etc.) vivem
-- em dados_extraidos JSONB — não viram coluna até serem necessários em consulta relacional.
CREATE TABLE IF NOT EXISTS dossies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id UUID NOT NULL,         -- isolamento lógico por cliente (toda query filtra)
    setor TEXT NOT NULL DEFAULT 'comex',
    referencia TEXT,
    dados_extraidos JSONB NOT NULL,
    status TEXT NOT NULL,             -- 'em_analise' | 'revisao_humana' | 'concluido'
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Documentos do dossiê (migration 0002 da Fase 1, inalterada — já generalizada)
CREATE TABLE IF NOT EXISTS documentos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossie_id UUID REFERENCES dossies(id) ON DELETE CASCADE,
    papel TEXT NOT NULL,
    tipo_documento_transporte TEXT,
    tipo_transporte_confirmado BOOLEAN NOT NULL DEFAULT FALSE,
    nome_arquivo TEXT,
    mime TEXT,
    texto_extraido TEXT,
    dados_extraidos JSONB,
    criado_em TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_documentos_dossie ON documentos(dossie_id);

-- Apontamentos: citação obrigatória OU abstenção EXPLÍCITA (nunca implícita).
CREATE TABLE IF NOT EXISTS apontamentos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossie_id UUID REFERENCES dossies(id),
    tipo TEXT,                        -- 'lacuna' | 'inconsistencia' | 'anuencia' | ...
    severidade TEXT,                  -- 'critico' | 'atencao' | 'info'
    orgao TEXT,                       -- NULL = não atribuível com base recuperada
    descricao TEXT NOT NULL,
    norma_citada_id UUID REFERENCES normas(id),
    sem_base_normativa BOOLEAN NOT NULL DEFAULT FALSE,  -- abstenção honesta declarada
    status TEXT NOT NULL,             -- 'pendente' | 'validado' | 'corrigido'
    criado_em TIMESTAMPTZ DEFAULT now(),
    -- ou cita norma, ou declara a ausência — nunca os dois, nunca nenhum:
    CONSTRAINT citacao_ou_abstencao CHECK (
        (norma_citada_id IS NOT NULL AND sem_base_normativa = FALSE)
        OR (norma_citada_id IS NULL AND sem_base_normativa = TRUE)
    )
);

-- Candidatos ranqueados por apontamento: o padrão "prováveis + alternativas, VERIFIQUE".
-- A classificação definitiva NÃO é campo do apontamento — é decisão humana (correcoes).
CREATE TABLE IF NOT EXISTS apontamento_candidatos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    apontamento_id UUID REFERENCES apontamentos(id) ON DELETE CASCADE,
    norma_id UUID REFERENCES normas(id),
    rotulo TEXT NOT NULL,             -- o que se sugere (ex.: 'NCM 6301.40.00', 'IN SDA 36/2009')
    posicao INT NOT NULL,             -- 1 = mais provável
    distancia REAL,                   -- NULL = via lexical
    escolhido_pelo_analista BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_candidatos_apontamento ON apontamento_candidatos(apontamento_id);

-- Correções humanas (o ativo de dado proprietário) — Fase 1, inalterada
CREATE TABLE IF NOT EXISTS correcoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    apontamento_id UUID REFERENCES apontamentos(id),
    valor_sugerido TEXT,
    valor_corrigido TEXT,
    justificativa_analista TEXT,
    autor TEXT NOT NULL,
    criado_em TIMESTAMPTZ DEFAULT now()
);

-- Log de auditoria APPEND-ONLY — Fase 1, agora com contrato NO BANCO (não só disciplina
-- de aplicação): trigger bloqueia UPDATE/DELETE. CLAUDE.md §4.3.
CREATE TABLE IF NOT EXISTS log_auditoria (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossie_id UUID REFERENCES dossies(id),
    evento TEXT NOT NULL,
    detalhe JSONB,
    criado_em TIMESTAMPTZ DEFAULT now()
);

CREATE OR REPLACE FUNCTION bloquear_mutacao_log() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'log_auditoria é append-only: % proibido (CLAUDE.md §4.3)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS log_auditoria_append_only ON log_auditoria;
CREATE TRIGGER log_auditoria_append_only
    BEFORE UPDATE OR DELETE ON log_auditoria
    FOR EACH ROW EXECUTE FUNCTION bloquear_mutacao_log();

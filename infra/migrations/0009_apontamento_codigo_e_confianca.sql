-- Migration 0009 — identificador estável de achado + confiança/impacto estruturados.
--
-- `codigo` já existe no dict retornado por regras_documentais.avaliar() (ex.: INCOTERM_MISMATCH,
-- FREIGHT_RULE) mas era descartado em db.inserir_apontamento — sem coluna, não dava para
-- (a) ter um identificador estável de card de achado no front, nem (b) indexar por
-- "mesmo tipo de achado, mesmo cliente" para o lookup de correção anterior (migration 0012).
--
-- `confianca_rotulo`/`confianca_pct`/`impacto_financeiro_texto` só devem ser preenchidos quando
-- houver uma medida real por trás (ex.: sim_top1 do rag.py, um cálculo de tributos_ncm) — nunca
-- um número inventado. NULL é o valor honesto quando não há medida (CLAUDE.md §4: nunca citar
-- sem grounding vale igual para confiança/impacto).
ALTER TABLE apontamentos ADD COLUMN IF NOT EXISTS codigo TEXT;
ALTER TABLE apontamentos ADD COLUMN IF NOT EXISTS confianca_rotulo TEXT; -- 'alta' | 'media' | 'baixa' | 'deterministico'
ALTER TABLE apontamentos ADD COLUMN IF NOT EXISTS confianca_pct NUMERIC;
ALTER TABLE apontamentos ADD COLUMN IF NOT EXISTS impacto_financeiro_texto TEXT;

CREATE INDEX IF NOT EXISTS idx_apontamentos_codigo ON apontamentos (codigo) WHERE codigo IS NOT NULL;

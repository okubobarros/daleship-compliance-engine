-- Migration 0002 — documentos do dossiê + tipo de documento de transporte GENÉRICO.
--
-- Decisão (2026-07-05): não hardcodar "B/L". Um dossiê tem 3 documentos, um deles é o
-- "documento de transporte", cujo tipo é DETECTADO automaticamente (Nó 1) — B/L (marítimo),
-- AWB (aéreo) e, no futuro, CRT (rodoviário Mercosul) — sem precisar de nova migration.
-- O usuário confirma/corrige o tipo em 1 clique na tela de detalhe (confirmação depois,
-- não pergunta antes do upload).

CREATE TABLE IF NOT EXISTS documentos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossie_id UUID REFERENCES dossies(id) ON DELETE CASCADE,
    papel TEXT NOT NULL,                       -- 'invoice' | 'packing_list' | 'documento_transporte'
    -- Só preenchido quando papel = 'documento_transporte'. Genérico e extensível:
    tipo_documento_transporte TEXT,            -- 'B/L' | 'AWB' | 'CRT' | NULL (indetectado)
    tipo_transporte_confirmado BOOLEAN NOT NULL DEFAULT FALSE,  -- humano confirmou/corrigiu?
    nome_arquivo TEXT,
    mime TEXT,
    texto_extraido TEXT,
    dados_extraidos JSONB,
    criado_em TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documentos_dossie ON documentos(dossie_id);

-- Rótulo humano do processo (para as listas/telas). dados_extraidos vira o consolidado.
ALTER TABLE dossies ADD COLUMN IF NOT EXISTS referencia TEXT;

-- Classifica o apontamento para a UI (divergência documental vs. exigência normativa).
ALTER TABLE apontamentos ADD COLUMN IF NOT EXISTS tipo TEXT;          -- 'divergencia' | 'anuencia' | 'classificacao'
ALTER TABLE apontamentos ADD COLUMN IF NOT EXISTS severidade TEXT;    -- 'critico' | 'atencao' | 'info'

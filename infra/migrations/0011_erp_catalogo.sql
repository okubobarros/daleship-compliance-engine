-- Migration 0011 — catálogo mestre do cliente (ERP), base para o Reconciliation Agent
-- (app/reconciliacao_erp.py): confere se um código/NCM da Invoice existe no cadastro do
-- cliente, importado de um CSV/XLSX real — não existia nenhuma tabela para isso até aqui.
CREATE TABLE IF NOT EXISTS erp_catalogo_itens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id UUID NOT NULL,
    codigo_interno TEXT NOT NULL,
    ncm TEXT,
    descricao TEXT,
    dossie_origem_id UUID REFERENCES dossies(id), -- de qual upload de catálogo veio esta linha
    criado_em TIMESTAMPTZ DEFAULT now(),
    UNIQUE (cliente_id, codigo_interno)
);

CREATE INDEX IF NOT EXISTS idx_erp_catalogo_cliente ON erp_catalogo_itens (cliente_id);

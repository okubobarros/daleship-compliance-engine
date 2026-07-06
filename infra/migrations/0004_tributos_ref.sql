-- Migration 0004 — Camada de Tributos (referência). Alíquotas por NCM + ICMS por UF +
-- taxa Siscomex + câmbio. FONTE ATUAL: planilha de referência fornecida pelo time
-- (tax_calc.xlsx) — marcada como snapshot datado, "pode não estar atualizada" (palavras do
-- usuário). Fonte OFICIAL de destino: TEC (CAMEX, II) + TIPI (RFB, IPI) — substituem esta
-- referência quando a camada Tributos entrar de vez (mapa do Bonano). Por isso `origem` e
-- `data_referencia` em cada tabela: dá para trocar a fonte sem migração nova.
--
-- Snapshot-versionado (como atributos_npi): carga nova = nova data_referencia, nunca
-- sobrescreve; consultas usam a referência mais recente.

CREATE TABLE IF NOT EXISTS tributos_ncm (
    ncm TEXT NOT NULL,                    -- '0101.21.00' (8 díg formatado)
    ii REAL, ipi REAL, pis REAL, cofins REAL,   -- alíquotas em %
    cide TEXT, antidumping TEXT, medidas_compensatorias TEXT,
    tratamento_administrativo TEXT,
    descricao TEXT,
    origem TEXT NOT NULL,                 -- 'tax_calc.xlsx (referência)' | 'TEC/TIPI' | ...
    data_referencia DATE NOT NULL,
    PRIMARY KEY (ncm, data_referencia)
);

CREATE TABLE IF NOT EXISTS icms_uf (
    uf TEXT NOT NULL,
    estado TEXT,
    icms REAL, afrmm REAL, taxa_utilizacao_mm REAL,
    origem TEXT NOT NULL,
    data_referencia DATE NOT NULL,
    PRIMARY KEY (uf, data_referencia)
);

CREATE TABLE IF NOT EXISTS taxa_siscomex (
    qtde_adicoes INT NOT NULL,
    valor_por_adicao REAL, valor_total REAL,
    origem TEXT NOT NULL,
    data_referencia DATE NOT NULL,
    PRIMARY KEY (qtde_adicoes, data_referencia)
);

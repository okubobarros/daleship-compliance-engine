-- Migration 0003 — Atributos DUIMP por NCM (camada 4 da base; fonte: Atributos NPI,
-- CSVs oficiais de PRODUÇÃO em gov.br/siscomex — a base de treinamento tem atributos
-- ainda em avaliação pelos órgãos e NÃO é usada).
--
-- Modelagem segue o princípio "sem campo único definitivo" (mesmo espírito de
-- apontamento_candidatos no scaffold Fase 2): um NCM pode ter N vínculos válidos
-- conforme órgão/modalidade/nível hierárquico — todos são guardados; quem decide é o
-- analista. Vínculo é HIERÁRQUICO: ncm_prefixo com 2/4/5/6/7/8 dígitos (capítulo →
-- item); a consulta casa todos os prefixos do código.
--
-- Versionamento por SNAPSHOT (data_referencia = data no nome do arquivo oficial):
-- carga nova insere nova referência, nunca sobrescreve a anterior — consultas usam a
-- referência mais recente.

-- Definições dos atributos (1 linha por atributo por snapshot)
CREATE TABLE IF NOT EXISTS atributos_definicoes (
    codigo TEXT NOT NULL,                 -- 'ATT_9534'
    nome TEXT NOT NULL,
    nome_apresentacao TEXT,
    objetivos TEXT,                       -- 'Duimp' | 'Produto' | ...
    orgaos TEXT,                          -- 'MAPA' | 'MAPA, RECEITA' | ... (como na fonte)
    forma_preenchimento TEXT,             -- 'Texto' | 'Lista estática' | 'Booleano' | ...
    atributo_condicionante TEXT,          -- estrutura condicional da fonte
    atributo_condicionado TEXT,
    mascara TEXT,
    tamanho TEXT,
    vigencia_inicio DATE,
    vigencia_fim DATE,
    data_referencia DATE NOT NULL,
    PRIMARY KEY (codigo, data_referencia)
);

-- Valores de domínio (atributos tipo lista: 1 linha por valor por snapshot)
CREATE TABLE IF NOT EXISTS atributos_dominio (
    codigo_atributo TEXT NOT NULL,
    codigo_valor TEXT NOT NULL,
    descricao_valor TEXT,
    vigencia_inicio DATE,
    vigencia_fim DATE,
    data_referencia DATE NOT NULL,
    PRIMARY KEY (codigo_atributo, codigo_valor, data_referencia)
);

-- Vínculos NCM(prefixo) -> atributo
CREATE TABLE IF NOT EXISTS atributos_vinculos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo_atributo TEXT NOT NULL,
    ncm_prefixo TEXT NOT NULL,            -- '01' | '0101' | '010121' | '01012100' (hierárquico)
    modalidade TEXT,                      -- 'Importação' | 'Exportação'
    obrigatorio BOOLEAN NOT NULL DEFAULT FALSE,
    multivalorado BOOLEAN NOT NULL DEFAULT FALSE,
    vigencia_inicio DATE,
    vigencia_fim DATE,
    data_referencia DATE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_atributos_vinculos_prefixo
    ON atributos_vinculos (ncm_prefixo, modalidade, data_referencia);

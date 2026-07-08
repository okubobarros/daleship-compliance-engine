-- Migration 0007 — fila híbrida de sugestão de NCM em lote (fila + progresso numa só tabela).
--
-- Serve de FILA (o worker puxa 'pendente' com FOR UPDATE SKIP LOCKED) e de PROGRESSO (o frontend
-- faz polling do status por item). Não trava o caminho síncrono do dossiê: a sugestão de NCM em
-- invoice grande (~300 itens) roda fora do request, item a item.
--
-- `descricao` é ADITIVO à lista pedida no goal: o worker precisa do texto do item como entrada do
-- rerank (senão teria que rejoinar em documentos.dados_extraidos por item_id).
--
-- Estados (terminais nunca voltam para retry infinito):
--   pendente                  — enfileirado, ainda não processado
--   processando               — um worker reivindicou o item (SKIP LOCKED)
--   concluido                 — rerank devolveu confiança ALTA (um provedor escolheu NCM válido)
--   concluido_confianca_baixa — TODOS os provedores falharam/não deram NCM na lista -> top-1 por
--                               similaridade, a conferir (terminal; sem retry infinito)
CREATE TABLE IF NOT EXISTS dossie_item_status (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossie_id      UUID NOT NULL,
    item_id        TEXT NOT NULL,          -- id do item dentro do dossiê (índice posicional estável)
    descricao      TEXT NOT NULL,          -- descrição da mercadoria (entrada do rerank)
    ncm_sugerido   TEXT,
    confianca      TEXT,                   -- 'alta' | 'baixa' | NULL (ainda não processado)
    provedor_usado TEXT,                   -- ex.: 'gemini:...', 'openrouter:...', 'retrieval'
    posicao_fila   INT,                    -- 0 = provedor principal; >0 = caiu para o N-ésimo
    status         TEXT NOT NULL DEFAULT 'pendente',
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (dossie_id, item_id)
);

-- Índice parcial que serve exatamente à query de polling do worker (só as linhas pendentes).
CREATE INDEX IF NOT EXISTS dossie_item_status_pendentes
    ON dossie_item_status (criado_em) WHERE status = 'pendente';

-- Migration 0012 — índices de suporte ao lookup "correção anterior" (app/aprendizado.py):
-- dado um cliente_id + codigo de achado, achar a correção humana mais recente para o mesmo
-- padrão. `correcoes` já existe (schema_fase1.sql) e não precisa mudar de forma — só faltam
-- os índices para o JOIN correcoes × apontamentos × dossies não fazer sequential scan.
CREATE INDEX IF NOT EXISTS idx_apontamentos_dossie_codigo ON apontamentos (dossie_id, codigo);
CREATE INDEX IF NOT EXISTS idx_dossies_cliente ON dossies (cliente_id);
CREATE INDEX IF NOT EXISTS idx_correcoes_apontamento ON correcoes (apontamento_id);

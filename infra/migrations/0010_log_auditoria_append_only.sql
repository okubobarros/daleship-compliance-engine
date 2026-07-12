-- Migration 0010 — torna log_auditoria append-only de verdade (CLAUDE.md §4: "Log é
-- append-only. Nunca UPDATE ou DELETE em log de auditoria — só INSERT").
--
-- Até aqui isso era só convenção de código (nenhum call site em app/ faz UPDATE/DELETE nessa
-- tabela) — sem garantia no banco. Um REVOKE não adianta porque a app conecta como o role dono
-- da tabela no Supabase (ignora GRANT/REVOKE comuns); só um trigger bloqueia de fato, inclusive
-- contra acesso direto via SQL editor do Supabase ou um bug futuro.
CREATE OR REPLACE FUNCTION bloquear_alteracao_log_auditoria()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'log_auditoria é append-only: % não é permitido (CLAUDE.md §4)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_log_auditoria_append_only ON log_auditoria;
CREATE TRIGGER trg_log_auditoria_append_only
    BEFORE UPDATE OR DELETE ON log_auditoria
    FOR EACH ROW EXECUTE FUNCTION bloquear_alteracao_log_auditoria();

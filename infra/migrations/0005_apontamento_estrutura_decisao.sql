-- Migration 0005 — estrutura de decisão do apontamento (Cockpit de decisão).
--
-- Os layouts do Cockpit e do Resumo apresentam cada achado em três colunas:
--   Evidência (o dado bruto observado) · Por que importa · Ação recomendada.
-- Hoje o apontamento só tem `descricao` + citação. Estes campos são ADITIVOS e OPCIONAIS
-- (NULL nos apontamentos antigos e nos que não seguem esse formato) — nenhum insert existente
-- quebra. Apontamentos que os preenchem (ex.: regra documental Invoice×BL) renderizam no
-- formato decisório; os demais continuam usando só `descricao`.
ALTER TABLE apontamentos ADD COLUMN IF NOT EXISTS evidencia TEXT;
ALTER TABLE apontamentos ADD COLUMN IF NOT EXISTS por_que_importa TEXT;
ALTER TABLE apontamentos ADD COLUMN IF NOT EXISTS acao_recomendada TEXT;

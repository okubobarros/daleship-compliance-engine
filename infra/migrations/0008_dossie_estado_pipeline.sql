-- Migration 0008 — estado explícito do pipeline do dossiê (máquina de estados) + consolidação.
--
-- `status` (existente) dirige a REVISÃO HUMANA na UI (em_analise/revisao_humana/concluido).
-- `estado_pipeline` (novo) é a MÁQUINA DE ESTADOS do processamento, separada e explícita:
--   recebido → extraindo → regras_documentais_ok → classificando_ncm → consolidando
--            → concluido | concluido_com_excecoes
-- Cada token marca a fase CONCLUÍDA; a orquestração (app/orquestracao.py) avança uma fase por
-- chamada, de forma idempotente (reprocessar não refaz fase já passada nem duplica apontamento).
--
-- `resumo_consolidado` guarda o resumo por dossiê (score_risco + apontamentos por severidade +
-- exceções agregadas + NCM alta/baixa) pronto para o Cockpit consumir quando a Frente 2 abrir.
ALTER TABLE dossies ADD COLUMN IF NOT EXISTS estado_pipeline TEXT;
ALTER TABLE dossies ADD COLUMN IF NOT EXISTS resumo_consolidado JSONB;

-- Migration 0001 — ajusta a dimensão da coluna `normas.embedding` para 1024.
--
-- Motivo: a decisão de embedding fechou em Voyage AI, modelo voyage-law-2, cuja
-- dimensão de saída é 1024 (confirmado na doc oficial da Voyage em 2026-07-04),
-- não 1536 como no schema baseline (infra/schema_fase1.sql).
--
-- A tabela `normas` está vazia neste momento, mas a mudança de dimensão de coluna
-- vetorial é tratada como migration formal (não edit direto em produção), por disciplina.

ALTER TABLE normas ALTER COLUMN embedding TYPE vector(1024);

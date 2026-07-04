# Workflows n8n — Fase 1 (Comex-demo)

Este diretório guarda o workflow n8n exportado (JSON), versionado como código conforme `docs/PROJECT_STRUCTURE.md`.

## Como importar

1. Suba o n8n local: `docker compose -f n8n/docker-compose.yml up -d`.
2. Acesse `http://localhost:5678`.
3. No menu do workflow, use **Import from File** e selecione `comex_conciliacao.json` (ainda não existe — é o primeiro artefato da Semana 1).

## Como exportar (depois de editar no n8n)

No menu do workflow, **Download** → salvar como `comex_conciliacao.json` neste diretório e commitar.

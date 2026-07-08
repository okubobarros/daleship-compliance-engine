# Imagem turnkey do endpoint de índice de confiança (host-agnóstico: Render/Railway/Fly/VPS).
# BUILD A PARTIR DA RAIZ DO REPO (contexto padrão do Render). No Render: Dockerfile Path =
# api/Dockerfile, Root Directory = . (raiz). Credenciais NUNCA vão na imagem — só via env do host.
FROM python:3.12-slim
WORKDIR /srv

# Deps da API + do worker (o endpoint /admin/processar-fila importa o worker: httpx, python-dotenv).
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copia SÓ o necessário (cópia explícita evita embutir .env / venvs / dados por engano):
#   api/            -> o endpoint FastAPI
#   app/            -> worker da fila, rag, config, rerank (usado por /admin/processar-fila)
#   mcp-server/src/ -> embeddings (Voyage) + grounding, importados por app/rag.py
COPY api ./api
COPY app ./app
COPY mcp-server/src ./mcp-server/src

# uvicorn importa api.main:app a partir de /srv (api e app são pacotes-namespace do Python 3).
# Honra $PORT do host (Render/Railway injetam); default 8000 localmente.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

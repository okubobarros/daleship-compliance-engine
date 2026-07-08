# Imagem turnkey do endpoint de índice de confiança (host-agnóstico: Railway/Render/Fly/VPS).
# Credenciais NUNCA vão na imagem — só por variável de ambiente do host (ver README).
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Honra $PORT do host (Railway/Render injetam); default 8000 localmente.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]

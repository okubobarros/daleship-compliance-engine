"""Endpoint mínimo (FastAPI) — expõe o `resumo_consolidado` de um dossiê (índice de confiança).

APENAS este endpoint — NÃO o Cockpit inteiro (Frente 2 segue pausada). Fatia vertical fina.

Segurança:
- Credenciais só de ENV (`DATABASE_URL`). Nunca hardcode.
- FAIL-CLOSED: exige `API_TOKEN` (Bearer). Um endpoint público que serve dado de dossiê JAMAIS
  pode ficar aberto; sem token configurado no servidor, responde 503 (não abre por engano).
- CORS restrito ao domínio do produto (`API_CORS_ORIGENS`, default despachantedebolso.com.br).
"""
import os
import uuid

import psycopg2
import psycopg2.extras
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

DATABASE_URL = os.environ["DATABASE_URL"]
API_TOKEN = os.environ.get("API_TOKEN", "").strip()
ORIGENS = [o.strip() for o in os.environ.get(
    "API_CORS_ORIGENS", "https://despachantedebolso.com.br").split(",") if o.strip()]

app = FastAPI(title="Despachante de Bolso — Índice de Confiança", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=ORIGENS, allow_methods=["GET"], allow_headers=["*"])


def _auth(authorization: str = Header(default="")):
    if not API_TOKEN:
        raise HTTPException(503, "Servidor sem API_TOKEN configurado (fail-closed).")
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(401, "Token inválido.")


@app.get("/saude")
def saude():
    return {"ok": True}


@app.get("/dossies/{dossie_id}/resumo", dependencies=[Depends(_auth)])
def resumo_dossie(dossie_id: str):
    try:
        uuid.UUID(dossie_id)
    except ValueError:
        raise HTTPException(404, "Dossiê não encontrado.")
    with psycopg2.connect(DATABASE_URL) as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT referencia, estado_pipeline, resumo_consolidado FROM dossies WHERE id=%s",
                    (dossie_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Dossiê não encontrado.")
    resumo = row["resumo_consolidado"]
    if not resumo:
        raise HTTPException(409, "Dossiê ainda não consolidado.")
    ncm = resumo.get("ncm") or {}
    total, alta = ncm.get("total") or 0, ncm.get("alta") or 0
    # Índice de confiança = % de itens com sugestão de NCM de confiança ALTA (reordenada por LLM+RGI).
    indice = round(alta / total * 100) if total else None
    return {
        "dossie_id": dossie_id,
        "referencia": row["referencia"],
        "estado": row["estado_pipeline"],
        "indice_confianca": indice,
        "score_risco": resumo.get("score_risco"),
        "excecoes": resumo.get("excecoes"),      # inclui ncm_confianca_baixa
        "mensagem": resumo.get("mensagem"),      # mensagem agregada já existente
        "ncm": ncm,
    }

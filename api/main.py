"""Endpoint mínimo (FastAPI) — expõe o `resumo_consolidado` de um dossiê (índice de confiança).

APENAS este endpoint — NÃO o Cockpit inteiro (Frente 2 segue pausada). Fatia vertical fina.

Segurança:
- Credenciais só de ENV (`DATABASE_URL`). Nunca hardcode.
- FAIL-CLOSED: exige `API_TOKEN` (Bearer). Um endpoint público que serve dado de dossiê JAMAIS
  pode ficar aberto; sem token configurado no servidor, responde 503 (não abre por engano).
- CORS restrito ao domínio do produto (`API_CORS_ORIGENS`, default despachantedebolso.com.br).
"""
import os
import sys
import uuid
from datetime import datetime, timezone
from time import perf_counter

import httpx
import psycopg2
import psycopg2.extras
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
API_TOKEN = os.environ.get("API_TOKEN", "").strip()
# Identidade do usuário do site público é o Supabase Auth (login+registro reais, ver
# login.html/registro.html) — mesmo projeto Supabase que já hospeda o Postgres. Reusa as vars
# NEXT_PUBLIC_* já existentes no .env (nome herdado de um quickstart Next.js, mantido por
# convenção do projeto — não é segredo, é a URL pública + chave publicável do projeto).
SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "").strip()
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
VERSAO_API = "0.1.0"
# Origens de CORS por env var (lista separada por vírgula) — setar no Render/Vercel sem editar
# código a cada mudança de domínio. Default: o domínio de produção.
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "https://despachantedebolso.com.br").split(",") if o.strip()]

app = FastAPI(title="Despachante de Bolso — Índice de Confiança", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_methods=["GET", "POST"], allow_headers=["*"])


def _auth(authorization: str = Header(default="")):
    if not API_TOKEN:
        raise HTTPException(503, "Servidor sem API_TOKEN configurado (fail-closed).")
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(401, "Token inválido.")


def _importar_app():
    """sys.path para importar os módulos de app/ — mesmo padrão lazy já usado em
    /admin/processar-fila (endpoints leves como /saude não carregam essa árvore)."""
    caminho = os.path.join(os.path.dirname(__file__), "..", "app")
    if caminho not in sys.path:
        sys.path.insert(0, caminho)


def exigir_sessao_cliente(authorization: str = Header(default="")) -> str:
    """Dependency para endpoints que agem EM NOME de um cliente logado (ex.: POST /dossies,
    revisão humana) — diferente de `_auth`, que é o token de SERVIÇO (proxy Vercel). Valida o
    access_token do Supabase Auth por INTROSPECÇÃO (GET /auth/v1/user) — sem biblioteca de JWT
    nova, um round-trip HTTP ao próprio Supabase que já hospeda o banco. cliente_id = user.id do
    Supabase (UUID estável, o mesmo em toda sessão do mesmo usuário). Fail-closed: sem
    NEXT_PUBLIC_SUPABASE_URL/PUBLISHABLE_KEY configurados, ninguém consegue autenticar."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(503, "Servidor sem Supabase Auth configurado (fail-closed).")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sessão ausente — faça login.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        resp = httpx.get(f"{SUPABASE_URL}/auth/v1/user",
                         headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_ANON_KEY},
                         timeout=10)
    except httpx.HTTPError:
        raise HTTPException(503, "Supabase Auth indisponível — tente novamente.")
    if resp.status_code != 200:
        raise HTTPException(401, "Sessão inválida ou expirada — faça login novamente.")
    usuario = resp.json()
    cliente_id = usuario.get("id")
    if not cliente_id:
        raise HTTPException(401, "Sessão inválida — faça login novamente.")
    return cliente_id


@app.get("/saude")
def saude():
    return {"ok": True}


@app.get("/dossies/{dossie_id}/resumo", dependencies=[Depends(_auth)])
def resumo_dossie(dossie_id: str):
    inicio = perf_counter()
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
    processamento_ms = round((perf_counter() - inicio) * 1000)
    return {
        "versao_api": VERSAO_API,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "tempo_processamento_ms": processamento_ms,
        "dossie_id": dossie_id,
        "referencia": row["referencia"],
        "estado": row["estado_pipeline"],
        "indice_confianca": indice,
        "score_risco": resumo.get("score_risco"),
        "excecoes": resumo.get("excecoes"),      # inclui ncm_confianca_baixa
        "mensagem": resumo.get("mensagem"),      # mensagem agregada já existente
        "ncm": ncm,
    }


@app.post("/admin/processar-fila", dependencies=[Depends(_auth)])
def processar_fila(max: int | None = None):
    """Modo SOB DEMANDA (opção a): drena a fila de NCM até esvaziar e ENCERRA — não é worker 24/7.
    Reaproveita worker_ncm.processar (já validado), sem reescrever a lógica de fila. Protegido pelo
    mesmo API_TOKEN. `?max=N` drena no máximo N itens (útil p/ drenar em blocos e evitar timeout de
    HTTP em fila grande). Import é lazy: o endpoint /resumo não carrega a árvore do app.

    Nota: a chamada BLOQUEIA enquanto processa (o rerank LLM leva segundos/minutos). Para fila grande,
    chame com `?max=N` repetidamente, ou rode o script (ver README) num Cron/One-off Job do Render."""
    _importar_app()
    import worker_ncm
    stats = worker_ncm.processar(max_itens=max)
    return {"processado": True, "stats": stats}


_EXTENSOES_PERMITIDAS = (".pdf", ".xlsx", ".xls", ".csv", ".png", ".jpg", ".jpeg")


def _validar_arquivo(nome: str, tamanho: int) -> None:
    if tamanho > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"Arquivo '{nome}' excede o tamanho máximo "
                                 f"({MAX_UPLOAD_BYTES // (1024 * 1024)}MB).")
    if not any(nome.lower().endswith(ext) for ext in _EXTENSOES_PERMITIDAS):
        raise HTTPException(400, f"Extensão de '{nome}' não suportada.")


def _drenar_e_concluir(dossie_id: str) -> None:
    """Roda em BackgroundTasks (depois da resposta HTTP já ter sido enviada): drena a fila de
    NCM — GLOBAL, não isolada por dossiê, aceitável na escala atual (ver plano) — e consolida
    este dossiê especificamente. Import lazy (mesmo padrão do resto do arquivo)."""
    _importar_app()
    import orquestracao
    import worker_ncm
    worker_ncm.processar()
    orquestracao.processar(dossie_id)


@app.post("/dossies")
async def criar_dossie_endpoint(
    background_tasks: BackgroundTasks,
    referencia: str = Form(...),
    contexto_cliente: str | None = Form(default=None),
    invoice: UploadFile = File(...),
    packing_list: UploadFile | None = File(default=None),
    documento_transporte: UploadFile | None = File(default=None),
    erp_catalogo: UploadFile | None = File(default=None),
    cliente_id: str = Depends(exigir_sessao_cliente),
):
    """Primeiro endpoint que deixa o site público de fato submeter documentos e disparar o
    motor real (app/orquestracao.py) — antes disso a jornada pública era 100% mock client-side.
    cliente_id vem da SESSÃO (não de um campo enviado pelo cliente — fecha a possibilidade de
    forjar outro cliente_id)."""
    _importar_app()
    import db
    import erp_catalogo as erp_catalogo_mod
    import orquestracao
    import processamento

    arquivos_upload = {"invoice": invoice}
    if packing_list is not None:
        arquivos_upload["packing_list"] = packing_list
    if documento_transporte is not None:
        arquivos_upload["documento_transporte"] = documento_transporte

    arquivos: dict[str, dict] = {}
    for papel, up in arquivos_upload.items():
        conteudo = await up.read()
        nome = up.filename or papel
        _validar_arquivo(nome, len(conteudo))
        arquivos[papel] = {"nome": nome, "mime": up.content_type or "", "bytes": conteudo}

    dossie_id = db.criar_dossie(cliente_id, referencia, contexto_cliente)

    fontes = set()
    for papel, arq in arquivos.items():
        ext = processamento._extrair_documento(papel, arq)
        fontes.add(ext["fonte"])
        dados = {"campos": ext["campos"], "itens": ext["itens"], "fonte_extracao": ext["fonte"]}
        db.inserir_documento(dossie_id, papel, ext["tipo_transporte"], arq["nome"], arq["mime"],
                             ext["texto"], dados)
    processamento._log(dossie_id, "extracao_concluida",
                       {"documentos": list(arquivos.keys()), "fonte_extracao": sorted(fontes)})

    if erp_catalogo is not None:
        conteudo_erp = await erp_catalogo.read()
        nome_erp = erp_catalogo.filename or "erp_catalogo"
        _validar_arquivo(nome_erp, len(conteudo_erp))
        erp_catalogo_mod.importar(cliente_id, dossie_id, nome_erp,
                                  erp_catalogo.content_type or "", conteudo_erp)

    estado = orquestracao.processar(dossie_id)
    if estado == "classificando_ncm":
        background_tasks.add_task(_drenar_e_concluir, dossie_id)
    return {"dossie_id": dossie_id, "estado": estado}


def _validar_uuid(dossie_id: str) -> None:
    try:
        uuid.UUID(dossie_id)
    except ValueError:
        raise HTTPException(404, "Dossiê não encontrado.")


@app.get("/dossies/{dossie_id}/estado", dependencies=[Depends(_auth)])
def estado_dossie(dossie_id: str):
    _validar_uuid(dossie_id)
    with psycopg2.connect(DATABASE_URL) as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT estado_pipeline, status FROM dossies WHERE id=%s", (dossie_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Dossiê não encontrado.")
    return {"dossie_id": dossie_id, "estado_pipeline": row["estado_pipeline"] or "recebido",
            "status": row["status"]}


# Narrativa em pt-BR por evento — a fonte real é sempre log_auditoria (cada linha corresponde a
# um evento de fato gravado pelo motor, nunca um texto decorativo/scriptado no frontend).
_NARRATIVA_EVENTO = {
    "dossie_criado": "Recebendo a operação...",
    "extracao_concluida": "Lendo Invoice/Packing List/BL e extraindo campos...",
    "pipeline_extracao_vazia": "Extração sem itens — aguardando dado externo.",
    "pipeline_consolidado": "Consolidando o parecer final...",
    "tipo_transporte_confirmado": "Tipo de documento de transporte confirmado.",
    "apontamento_revisado": "Um achado foi revisado por um analista.",
    "erp_catalogo_importado": "Catálogo ERP do cliente importado.",
}


def _narrar(evento: str, detalhe: dict) -> str:
    if evento == "nivel_reconciliacao_definido":
        return detalhe.get("narrativa") or "Nível de reconciliação definido."
    if evento == "classificacao_ncm_progresso":
        return f"Classificando NCM: {detalhe.get('concluidos')}/{detalhe.get('total')} itens."
    if evento == "pipeline_transicao":
        return f"Avançando para: {detalhe.get('estado')}."
    return _NARRATIVA_EVENTO.get(evento, evento)


@app.get("/dossies/{dossie_id}/eventos", dependencies=[Depends(_auth)])
def eventos_dossie(dossie_id: str):
    _validar_uuid(dossie_id)
    _importar_app()
    import db
    trilha = db.listar_trilha(dossie_id)
    return {"dossie_id": dossie_id, "eventos": [
        {"evento": e["evento"], "narrativa": _narrar(e["evento"], e["detalhe"] or {}),
         "detalhe": e["detalhe"], "criado_em": e["criado_em"]}
        for e in trilha
    ]}


@app.get("/dossies/{dossie_id}/apontamentos", dependencies=[Depends(_auth)])
def apontamentos_dossie(dossie_id: str):
    _validar_uuid(dossie_id)
    _importar_app()
    import db
    return {"dossie_id": dossie_id, "apontamentos": db.listar_apontamentos(dossie_id)}


class RevisaoRequest(BaseModel):
    aceito: bool
    valor_corrigido: str | None = None
    justificativa: str | None = None


@app.post("/dossies/{dossie_id}/apontamentos/{apontamento_id}/revisao")
def revisar_apontamento(dossie_id: str, apontamento_id: str, body: RevisaoRequest,
                        cliente_id: str = Depends(exigir_sessao_cliente)):
    """Aceitar (1 clique) ou corrigir (com texto) um achado — os botões "Aceitar"/"Corrigir" de
    cada card em resultado.html, antes decorativos. Isolamento: só quem é dono do dossiê pode
    revisar seus achados (verifica via db.obter_dossie(dossie_id, cliente_id))."""
    _validar_uuid(dossie_id)
    _importar_app()
    import db
    if not db.obter_dossie(dossie_id, cliente_id):
        raise HTTPException(404, "Dossiê não encontrado para este usuário.")
    apontamento = db.obter_apontamento(apontamento_id)
    if not apontamento or apontamento["dossie_id"] != dossie_id:
        raise HTTPException(404, "Achado não encontrado neste dossiê.")
    if not body.aceito and not body.valor_corrigido:
        raise HTTPException(400, "Informe o valor corrigido para registrar uma correção.")
    db.registrar_revisao(apontamento_id, dossie_id, body.aceito, apontamento["descricao"],
                         body.valor_corrigido, body.justificativa, cliente_id)
    return {"ok": True, "apontamento_id": apontamento_id,
            "status": "validado" if body.aceito else "corrigido"}


class DecisaoRequest(BaseModel):
    decisao: str  # 'aceitar_tudo' | 'escalar' | 'travar'
    nota: str | None = None


@app.post("/dossies/{dossie_id}/decisao")
def decidir_dossie_endpoint(dossie_id: str, body: DecisaoRequest,
                            cliente_id: str = Depends(exigir_sessao_cliente)):
    """Ações de nível dossiê — os botões "Aceitar"/"Escalar"/"Travar avanço" do painel "Parecer
    do Cockpit" em resultado.html, antes decorativos."""
    _validar_uuid(dossie_id)
    _importar_app()
    import db
    if not db.obter_dossie(dossie_id, cliente_id):
        raise HTTPException(404, "Dossiê não encontrado para este usuário.")
    if body.decisao not in ("aceitar_tudo", "escalar", "travar"):
        raise HTTPException(400, "Decisão inválida — use 'aceitar_tudo', 'escalar' ou 'travar'.")
    db.decidir_dossie(dossie_id, body.decisao, body.nota, cliente_id)
    return {"ok": True, "dossie_id": dossie_id, "decisao": body.decisao}

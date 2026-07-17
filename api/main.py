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
# código a cada mudança de domínio. Default: o domínio de produção. Barra final é normalizada
# (Origin do browser nunca tem barra — um "/" a mais na env var silenciosamente quebrava tudo).
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in os.environ.get(
    "ALLOWED_ORIGINS",
    "https://despachantedebolso.com.br,https://www.despachantedebolso.com.br").split(",") if o.strip()]

app = FastAPI(title="Despachante de Bolso — Índice de Confiança", version="0.1.0")
# allow_origin_regex: o domínio do produto SEMPRE passa, mesmo que a env var ALLOWED_ORIGINS
# esteja errada no host (aconteceu em produção em 17/07/2026 — cockpit inteiro sem CORS).
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_origin_regex=r"https://(www\.)?despachantedebolso\.com\.br",
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


@app.get("/noticias")
def noticias_endpoint(limite: int = 60):
    """Feed normativo com fontes REAIS (DOU Seção 1 filtrado para comex + RSS MDIC + RSS
    Receita Federal), cache em memória com TTL — ver api/noticias.py. Público (é dado
    público da Imprensa Nacional/gov.br; não expõe nada de cliente)."""
    from api import noticias as noticias_mod
    coleta = noticias_mod.obter()
    return {
        "gerado_em": coleta["gerado_em"],
        "fontes": coleta["fontes"],
        "total": len(coleta["itens"]),
        "itens": coleta["itens"][:max(1, min(limite, 200))],
    }


@app.get("/dossies")
def listar_dossies_endpoint(cliente_id: str = Depends(exigir_sessao_cliente)):
    """Lista os dossiês do cliente logado — alimenta os KPIs do cockpit e a tela de
    processos. Só campos de resumo (nunca o dado extraído bruto inteiro)."""
    _importar_app()
    import db
    saida = []
    for d in db.listar_dossies(cliente_id):
        resumo = d.get("resumo_consolidado") or {}
        saida.append({
            "id": str(d["id"]),
            "referencia": d.get("referencia"),
            "estado_pipeline": d.get("estado_pipeline") or "recebido",
            "status": d.get("status"),
            "criado_em": d["criado_em"].isoformat() if d.get("criado_em") else None,
            "n_apontamentos": d.get("n_apontamentos") or 0,
            "score_risco": resumo.get("score_risco"),
            "excecoes": resumo.get("excecoes"),
            "mensagem": resumo.get("mensagem"),
        })
    return {"cliente_id": cliente_id, "total": len(saida), "dossies": saida}


class ClassificacaoRequest(BaseModel):
    descricao: str


@app.post("/classificacao")
def classificar_endpoint(body: ClassificacaoRequest,
                         cliente_id: str = Depends(exigir_sessao_cliente)):
    """Classificação fiscal sob demanda: descrição de mercadoria → sugestão de NCM
    (retrieval HNSW + rerank LLM+RGI, o MESMO caminho do motor de dossiês —
    rag.sugerir_ncm), com anuência (Tratamento Administrativo) e alíquotas de referência
    do NCM sugerido. Nunca afirma: toda resposta carrega confiança + justificativa."""
    descricao = body.descricao.strip()
    if len(descricao) < 3:
        raise HTTPException(400, "Descreva a mercadoria (mínimo 3 caracteres).")
    _importar_app()
    import rag
    sugestao = rag.sugerir_ncm([descricao])[0]
    resposta = {
        "descricao": descricao,
        "ncm": sugestao.get("ncm"),
        "texto_ncm": sugestao.get("texto"),
        "confianca": sugestao.get("confianca"),
        "provedor": sugestao.get("provedor"),
        "rgi": sugestao.get("rgi"),
        "justificativa": sugestao.get("justificativa"),
        "sim_top1": sugestao.get("sim_top1"),
        "candidatos": [
            {"ncm": c["identificador"].replace("NCM ", ""),
             "texto": (c.get("texto") or "")[:220],
             "similaridade": round((1 - c["distancia"]) * 100, 1)}
            for c in (sugestao.get("candidatos") or [])[:8]
        ],
        "anuencia": None,
        "tributos": None,
    }
    if resposta["ncm"]:
        anuencia = rag.anuencia_por_ncm(resposta["ncm"])
        if anuencia:
            resposta["anuencia"] = {"orgao": anuencia.get("orgao"),
                                    "identificador": anuencia.get("identificador"),
                                    "trecho": (anuencia.get("texto") or "")[:300],
                                    "fonte_url": anuencia.get("fonte_url")}
        tributos = rag.tributos_por_ncm(resposta["ncm"])
        if tributos:
            tributos["data_referencia"] = str(tributos.get("data_referencia") or "")
            resposta["tributos"] = tributos
    return resposta


def _normalizar_ncm(codigo: str) -> str:
    digitos = "".join(ch for ch in (codigo or "") if ch.isdigit())
    if len(digitos) != 8:
        raise HTTPException(400, "NCM inválido — informe os 8 dígitos (ex.: 8471.30.12).")
    return f"{digitos[:4]}.{digitos[4:6]}.{digitos[6:8]}"


class CusteioRequest(BaseModel):
    ncm: str
    uf: str
    preco_unitario: float
    quantidade: float = 1.0
    cambio: float
    frete: float | None = None      # em BRL; None = estimativa do modelo
    seguro: float | None = None     # em BRL; None = estimativa do modelo
    modal: str = "maritimo"         # 'maritimo' | 'aereo' | 'rodoviario'


@app.post("/custeio")
def custeio_endpoint(body: CusteioRequest,
                     cliente_id: str = Depends(exigir_sessao_cliente)):
    """Calculadora de custeio de importação (VMLD/CIF + tributos + despesas → custo total).
    Alíquotas vêm da camada de REFERÊNCIA (tributos_ncm/icms_uf com data_referencia) e o
    cálculo é o mesmo módulo puro do motor (app/cti.py). Se o NCM não está na referência,
    ABSTÉM (422) — nunca inventa alíquota (CLAUDE.md §4)."""
    ncm = _normalizar_ncm(body.ncm)
    if body.quantidade <= 0 or body.cambio <= 0 or body.preco_unitario < 0:
        raise HTTPException(400, "Quantidade e câmbio devem ser positivos.")
    _importar_app()
    import cti
    import rag
    tributos = rag.tributos_por_ncm(ncm)
    if not tributos:
        raise HTTPException(422, f"NCM {ncm} não encontrado na referência de alíquotas — "
                                 "não estimamos sem fonte.")
    uf_info = rag.icms_por_uf(body.uf.strip())
    if not uf_info:
        raise HTTPException(422, f"UF '{body.uf}' não encontrada na referência de ICMS.")
    resultado = cti.calcular_cti(
        preco_unitario=body.preco_unitario, quantidade=body.quantidade, cambio=body.cambio,
        ii=tributos.get("ii") or 0.0, ipi=tributos.get("ipi") or 0.0,
        pis=tributos.get("pis") or 0.0, cofins=tributos.get("cofins") or 0.0,
        icms=uf_info.get("icms") or 0.0,
        frete=body.frete, seguro=body.seguro,
        afrmm_pct=uf_info.get("afrmm") or 0.0, modal=body.modal,
    )
    return {
        "ncm": ncm,
        "uf": uf_info.get("uf"),
        "estado": uf_info.get("estado"),
        "modal": body.modal,
        "aliquotas": {
            "ii": tributos.get("ii"), "ipi": tributos.get("ipi"),
            "pis": tributos.get("pis"), "cofins": tributos.get("cofins"),
            "icms": uf_info.get("icms"), "afrmm": uf_info.get("afrmm"),
            "data_referencia": str(tributos.get("data_referencia") or ""),
        },
        "alertas": {
            "cide": tributos.get("cide"),
            "antidumping": tributos.get("antidumping"),
            "medidas_compensatorias": tributos.get("medidas_compensatorias"),
        },
        "frete_estimado": body.frete is None,
        "seguro_estimado": body.seguro is None,
        "resultado": {k: round(v, 2) for k, v in resultado.items()},
    }


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

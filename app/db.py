"""Acesso a dados do app (psycopg2, síncrono — casa bem com Streamlit).

Disciplina do CLAUDE.md: log_auditoria é APPEND-ONLY (só INSERT). Toda ação relevante
(criação de dossiê, correção, confirmação de tipo de transporte) registra um evento aqui.
"""
import json
import uuid

import psycopg2
import psycopg2.extras

from config import DATABASE_URL


def conectar():
    return psycopg2.connect(DATABASE_URL)


def _dict_cur(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# --- Dossiês ---

def criar_dossie(cliente_id: str, referencia: str, contexto_cliente: str | None = None) -> str:
    """contexto_cliente é o texto livre do campo "Contexto do cliente" (mockup
    estado-vazio.html) — guardado em dados_extraidos (sem migration nova) para o
    Reconciliation Agent poder lê-lo depois (ex.: "apenas conferir impostos, ignorar catálogo")."""
    dossie_id = str(uuid.uuid4())
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO dossies (id, cliente_id, referencia, dados_extraidos, status) "
            "VALUES (%s, %s, %s, %s, 'em_analise')",
            (dossie_id, cliente_id, referencia, json.dumps({"contexto_cliente": contexto_cliente})),
        )
        cur.execute(
            "INSERT INTO log_auditoria (dossie_id, evento, detalhe) VALUES (%s, %s, %s)",
            (dossie_id, "dossie_criado", json.dumps({"referencia": referencia, "cliente_id": cliente_id})),
        )
        conn.commit()
    return dossie_id


def cliente_id_do_dossie(dossie_id: str) -> str | None:
    with conectar() as conn, conn.cursor() as cur:
        cur.execute("SELECT cliente_id FROM dossies WHERE id=%s", (dossie_id,))
        r = cur.fetchone()
        return str(r[0]) if r else None


def contexto_cliente_do_dossie(dossie_id: str) -> str | None:
    with conectar() as conn, conn.cursor() as cur:
        cur.execute("SELECT dados_extraidos->>'contexto_cliente' FROM dossies WHERE id=%s", (dossie_id,))
        r = cur.fetchone()
        return r[0] if r else None


def listar_dossies(cliente_id: str) -> list[dict]:
    with conectar() as conn, _dict_cur(conn) as cur:
        cur.execute(
            "SELECT d.*, "
            "(SELECT count(*) FROM apontamentos a WHERE a.dossie_id = d.id) AS n_apontamentos "
            "FROM dossies d WHERE cliente_id = %s ORDER BY criado_em DESC",
            (cliente_id,),
        )
        return list(cur.fetchall())


def obter_dossie(dossie_id: str, cliente_id: str) -> dict | None:
    with conectar() as conn, _dict_cur(conn) as cur:
        cur.execute("SELECT * FROM dossies WHERE id = %s AND cliente_id = %s", (dossie_id, cliente_id))
        return cur.fetchone()


def atualizar_status(dossie_id: str, status: str) -> None:
    with conectar() as conn, conn.cursor() as cur:
        cur.execute("UPDATE dossies SET status = %s WHERE id = %s", (status, dossie_id))
        conn.commit()


# --- Documentos ---

def inserir_documento(dossie_id: str, papel: str, tipo_transp: str | None,
                      nome_arquivo: str, mime: str, texto: str, dados: dict) -> str:
    doc_id = str(uuid.uuid4())
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documentos (id, dossie_id, papel, tipo_documento_transporte, "
            "nome_arquivo, mime, texto_extraido, dados_extraidos) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (doc_id, dossie_id, papel, tipo_transp, nome_arquivo, mime, texto, json.dumps(dados)),
        )
        conn.commit()
    return doc_id


def listar_documentos(dossie_id: str) -> list[dict]:
    with conectar() as conn, _dict_cur(conn) as cur:
        cur.execute("SELECT * FROM documentos WHERE dossie_id = %s ORDER BY criado_em", (dossie_id,))
        return list(cur.fetchall())


def confirmar_tipo_transporte(doc_id: str, dossie_id: str, novo_tipo: str, autor: str) -> None:
    """Confirma/corrige o tipo do documento de transporte (1 clique). Registra no log."""
    with conectar() as conn, _dict_cur(conn) as cur:
        cur.execute("SELECT tipo_documento_transporte FROM documentos WHERE id = %s", (doc_id,))
        anterior = cur.fetchone()
        cur.execute(
            "UPDATE documentos SET tipo_documento_transporte = %s, tipo_transporte_confirmado = TRUE "
            "WHERE id = %s",
            (novo_tipo, doc_id),
        )
        cur.execute(
            "INSERT INTO log_auditoria (dossie_id, evento, detalhe) VALUES (%s, %s, %s)",
            (dossie_id, "tipo_transporte_confirmado",
             json.dumps({"documento_id": doc_id, "de": (anterior or {}).get("tipo_documento_transporte"),
                         "para": novo_tipo, "autor": autor})),
        )
        conn.commit()


# --- Apontamentos ---

def inserir_apontamento(dossie_id: str, tipo: str, severidade: str, orgao: str,
                        descricao: str, norma_id: str | None,
                        evidencia: str | None = None, por_que_importa: str | None = None,
                        acao_recomendada: str | None = None, codigo: str | None = None,
                        confianca_rotulo: str | None = None, confianca_pct: float | None = None,
                        impacto_financeiro_texto: str | None = None) -> str:
    """Insere um apontamento. Os campos de decisão (evidencia/por_que_importa/acao_recomendada)
    e os de identidade/confiança (codigo/confianca_rotulo/confianca_pct/impacto_financeiro_texto,
    migration 0009) são todos opcionais: preenchidos por regras que seguem o formato do Cockpit,
    NULL nos demais — confianca_pct só deve vir de uma medida real (ex.: sim_top1 do rerank de
    NCM), nunca um número inventado (CLAUDE.md §4)."""
    ap_id = str(uuid.uuid4())
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO apontamentos (id, dossie_id, tipo, severidade, orgao, descricao, "
            "norma_citada_id, evidencia, por_que_importa, acao_recomendada, codigo, "
            "confianca_rotulo, confianca_pct, impacto_financeiro_texto, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pendente')",
            (ap_id, dossie_id, tipo, severidade, orgao, descricao, norma_id,
             evidencia, por_que_importa, acao_recomendada, codigo,
             confianca_rotulo, confianca_pct, impacto_financeiro_texto),
        )
        conn.commit()
    return ap_id


def listar_apontamentos(dossie_id: str) -> list[dict]:
    """Apontamentos + a norma citada (texto/fonte) por JOIN — citação SEMPRE ao lado."""
    with conectar() as conn, _dict_cur(conn) as cur:
        cur.execute(
            "SELECT a.*, n.identificador AS norma_identificador, n.texto AS norma_texto, "
            "n.fonte_url AS norma_fonte_url, n.tipo_documento AS norma_tipo "
            "FROM apontamentos a LEFT JOIN normas n ON n.id = a.norma_citada_id "
            "WHERE a.dossie_id = %s ORDER BY "
            "CASE a.severidade WHEN 'critico' THEN 0 WHEN 'atencao' THEN 1 ELSE 2 END, a.criado_em",
            (dossie_id,),
        )
        return list(cur.fetchall())


def registrar_revisao(apontamento_id: str, dossie_id: str, aceito: bool,
                      valor_sugerido: str, valor_corrigido: str | None,
                      justificativa: str | None, autor: str) -> None:
    """Aceita (1 clique) ou corrige (com texto) um apontamento. Correção + log append-only."""
    novo_status = "validado" if aceito else "corrigido"
    with conectar() as conn, conn.cursor() as cur:
        cur.execute("UPDATE apontamentos SET status = %s WHERE id = %s", (novo_status, apontamento_id))
        cur.execute(
            "INSERT INTO correcoes (apontamento_id, valor_sugerido, valor_corrigido, justificativa_analista, autor) "
            "VALUES (%s, %s, %s, %s, %s)",
            (apontamento_id, valor_sugerido, valor_corrigido, justificativa, autor),
        )
        cur.execute(
            "INSERT INTO log_auditoria (dossie_id, evento, detalhe) VALUES (%s, %s, %s)",
            (dossie_id, "apontamento_revisado",
             json.dumps({"apontamento_id": apontamento_id, "status": novo_status,
                         "valor_corrigido": valor_corrigido, "justificativa": justificativa, "autor": autor})),
        )
        conn.commit()


def obter_apontamento(apontamento_id: str) -> dict | None:
    with conectar() as conn, _dict_cur(conn) as cur:
        cur.execute("SELECT * FROM apontamentos WHERE id = %s", (apontamento_id,))
        return cur.fetchone()


def decidir_dossie(dossie_id: str, decisao: str, nota: str | None, autor: str) -> None:
    """Ações de nível DOSSIÊ acionadas pelo painel "Parecer do Cockpit" (botões antes
    decorativos): 'aceitar_tudo' aceita todos os apontamentos ainda pendentes (1 clique cada,
    via registrar_revisao) e conclui a revisão; 'escalar'/'travar' mudam o status do dossiê e
    registram o motivo em log_auditoria — nunca some sem deixar rastro (CLAUDE.md §4)."""
    if decisao == "aceitar_tudo":
        pendentes = [a for a in listar_apontamentos(dossie_id) if a["status"] == "pendente"]
        for ap in pendentes:
            registrar_revisao(ap["id"], dossie_id, True, ap["descricao"], None, nota, autor)
        atualizar_status(dossie_id, "concluido")
        return
    novo_status = {"escalar": "escalado", "travar": "travado"}.get(decisao)
    if not novo_status:
        raise ValueError(f"decisão desconhecida: {decisao}")
    atualizar_status(dossie_id, novo_status)
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO log_auditoria (dossie_id, evento, detalhe) VALUES (%s, %s, %s)",
            (dossie_id, f"dossie_{novo_status}", json.dumps({"nota": nota, "autor": autor})),
        )
        conn.commit()


# --- Trilha de auditoria ---

def listar_trilha(dossie_id: str) -> list[dict]:
    with conectar() as conn, _dict_cur(conn) as cur:
        cur.execute(
            "SELECT evento, detalhe, criado_em FROM log_auditoria WHERE dossie_id = %s ORDER BY criado_em",
            (dossie_id,),
        )
        return list(cur.fetchall())

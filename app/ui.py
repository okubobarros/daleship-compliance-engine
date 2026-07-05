"""UI mínima do MVP (Fase 1 — Comex-demo). Streamlit, sem polimento visual.

Telas (MVP_PRODUCT_SPEC.md): login simples -> lista de processos -> upload -> detalhe do
dossiê (apontamentos com citação SEMPRE ao lado) -> revisão humana -> trilha de auditoria.
"""
import html

import streamlit as st

import auth
import db
import estilo
import processamento
from config import PAPEIS, TIPOS_TRANSPORTE, nome_tipo_transporte

st.set_page_config(page_title="Daleship — Conferência de Comex", layout="wide")
estilo.aplicar()

ss = st.session_state
ss.setdefault("cliente_id", None)
ss.setdefault("usuario", None)
ss.setdefault("pagina", "lista")
ss.setdefault("dossie_atual", None)


def ir(pagina: str, dossie_id: str | None = None):
    ss.pagina = pagina
    if dossie_id is not None:
        ss.dossie_atual = dossie_id


# ---------- Login ----------

def tela_login():
    st.title("Daleship — Conferência de Comex")
    st.caption("Acesso do time da trading")
    with st.form("login"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            cid = auth.autenticar(usuario, senha)
            if cid:
                ss.cliente_id, ss.usuario, ss.pagina = cid, usuario, "lista"
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")


# ---------- Lista de processos ----------

def tela_lista():
    col1, col2 = st.columns([4, 1])
    col1.title("Processos de importação")
    if col2.button("+ Novo processo", use_container_width=True):
        ir("novo"); st.rerun()

    dossies = db.listar_dossies(ss.cliente_id)
    if not dossies:
        st.info("Nenhum processo ainda. Clique em **+ Novo processo** para enviar os documentos.")
        return
    for d in dossies:
        c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
        c1.markdown(f"**{d['referencia'] or '(sem referência)'}**")
        c2.write(_status_legivel(d["status"]))
        c3.write(f"{d['n_apontamentos']} apontamento(s)")
        if c4.button("Abrir", key=f"abrir_{d['id']}", use_container_width=True):
            ir("detalhe", d["id"]); st.rerun()


def _status_legivel(s: str) -> str:
    return {"em_analise": "Em análise", "revisao_humana": "Aguardando revisão",
            "concluido": "Concluído"}.get(s, s)


# ---------- Novo processo (upload) ----------

def tela_novo():
    st.title("Novo processo — envio de documentos")
    st.caption("Aceitamos PDF, imagem ou Excel como estão. Não é preciso escolher o modal "
               "de transporte: o sistema detecta pelo próprio documento.")
    referencia = st.text_input("Referência do processo (ex.: PO-2026-0142)")
    arquivos = {}
    for papel, rotulo in PAPEIS.items():
        up = st.file_uploader(rotulo, type=["pdf", "png", "jpg", "jpeg", "xlsx", "xls"], key=papel)
        if up is not None:
            arquivos[papel] = {"nome": up.name, "mime": up.type or "", "bytes": up.getvalue()}

    col1, col2 = st.columns([1, 5])
    if col1.button("Voltar"):
        ir("lista"); st.rerun()
    if col2.button("Processar", type="primary", disabled=not arquivos):
        with st.spinner("Extraindo, conciliando e cruzando com a base normativa…"):
            dossie_id = processamento.processar_dossie(
                ss.cliente_id, referencia or "(sem referência)", arquivos)
        ir("detalhe", dossie_id); st.rerun()


# ---------- Detalhe do dossiê ----------

def tela_detalhe():
    dossie = db.obter_dossie(ss.dossie_atual, ss.cliente_id)
    if not dossie:
        st.error("Processo não encontrado."); return
    c1, c2, c3, c4 = st.columns([4, 1, 1, 1])
    c1.title(dossie["referencia"] or "Processo")
    if c2.button("Revisar", use_container_width=True):
        ir("revisao"); st.rerun()
    if c3.button("Trilha", use_container_width=True):
        ir("trilha"); st.rerun()
    if c4.button("Voltar", use_container_width=True):
        ir("lista"); st.rerun()

    _confirmacao_transporte(dossie)

    st.subheader("Apontamentos")
    st.caption("Cada apontamento traz a norma citada ao lado — a fonte nunca fica escondida.")
    apontamentos = db.listar_apontamentos(ss.dossie_atual)
    if not apontamentos:
        st.info("Sem apontamentos.")
    for ap in apontamentos:
        _cartao_apontamento(ap)


def _confirmacao_transporte(dossie):
    """Confirmação rápida e NÃO bloqueante do tipo de transporte detectado (1 clique p/ corrigir)."""
    docs = db.listar_documentos(ss.dossie_atual)
    transp = next((d for d in docs if d["papel"] == "documento_transporte"), None)
    if not transp:
        return
    detectado = transp["tipo_documento_transporte"]
    confirmado = transp["tipo_transporte_confirmado"]
    st.markdown(
        f'<div class="confirma-tipo">Detectamos: <b>{html.escape(nome_tipo_transporte(detectado))}</b>'
        + (" ✓ confirmado" if confirmado else " — confira abaixo se está correto") + "</div>",
        unsafe_allow_html=True)
    if not confirmado:
        col1, col2 = st.columns([3, 1])
        opcoes = list(TIPOS_TRANSPORTE.keys())
        idx = opcoes.index(detectado) if detectado in opcoes else 0
        escolha = col1.selectbox("Tipo do documento de transporte", opcoes,
                                 index=idx, format_func=nome_tipo_transporte, label_visibility="collapsed")
        if col2.button("Confirmar tipo", use_container_width=True):
            db.confirmar_tipo_transporte(transp["id"], ss.dossie_atual, escolha, ss.usuario)
            st.rerun()


def _cartao_apontamento(ap, com_acoes=False):
    sev = ap.get("severidade") or "info"
    tag = {"critico": "Crítico", "atencao": "Atenção", "info": "Informativo"}.get(sev, sev)
    st.markdown(f'<div class="apontamento {sev}">'
                f'<span class="tag {sev}">{tag}</span> '
                f'<b>{html.escape(ap["orgao"] or "-")}</b> · {html.escape(ap["descricao"])}'
                + _bloco_citacao(ap) + '</div>', unsafe_allow_html=True)


def _bloco_citacao(ap) -> str:
    if ap.get("norma_identificador"):
        trecho = (ap["norma_texto"] or "")[:320]
        fonte = html.escape(ap["norma_fonte_url"] or "")
        link = f'<a class="fonte" href="{fonte}" target="_blank">{html.escape(ap["norma_identificador"])}</a>' if fonte \
            else f'<span class="fonte">{html.escape(ap["norma_identificador"])}</span>'
        return f'<div class="citacao">📎 {link}<br>{html.escape(trecho)}…</div>'
    return '<div class="citacao sem-fonte">Sem base normativa localizada — nenhuma citação atribuída.</div>'


# ---------- Revisão humana ----------

def tela_revisao():
    dossie = db.obter_dossie(ss.dossie_atual, ss.cliente_id)
    st.title(f"Revisão — {dossie['referencia'] or 'Processo'}")
    st.caption("Aceite com 1 clique quando o apontamento estiver correto; corrija só quando necessário.")
    if st.button("← Voltar ao detalhe"):
        ir("detalhe"); st.rerun()

    apontamentos = db.listar_apontamentos(ss.dossie_atual)
    pendentes = [a for a in apontamentos if a["status"] == "pendente"]
    if not pendentes:
        st.success("Todos os apontamentos foram revisados.")
    for ap in pendentes:
        _cartao_apontamento(ap)
        c1, c2 = st.columns([1, 4])
        if c1.button("✓ Aceitar", key=f"aceitar_{ap['id']}"):
            db.registrar_revisao(ap["id"], ss.dossie_atual, True, ap["descricao"], None, None, ss.usuario)
            st.rerun()
        with c2.expander("Corrigir"):
            correcao = st.text_area("Correção / justificativa", key=f"txt_{ap['id']}")
            if st.button("Salvar correção", key=f"corrigir_{ap['id']}"):
                db.registrar_revisao(ap["id"], ss.dossie_atual, False, ap["descricao"],
                                     correcao, correcao, ss.usuario)
                st.rerun()

    revisados = [a for a in apontamentos if a["status"] != "pendente"]
    if revisados and not pendentes:
        if st.button("Concluir processo", type="primary"):
            db.atualizar_status(ss.dossie_atual, "concluido")
            ir("detalhe"); st.rerun()


# ---------- Trilha de auditoria ----------

def tela_trilha():
    dossie = db.obter_dossie(ss.dossie_atual, ss.cliente_id)
    st.title(f"Trilha de auditoria — {dossie['referencia'] or 'Processo'}")
    st.caption("Quem fez o quê e quando — o registro é append-only.")
    if st.button("← Voltar ao detalhe"):
        ir("detalhe"); st.rerun()
    for ev in db.listar_trilha(ss.dossie_atual):
        st.markdown(f"**{ev['criado_em']:%d/%m/%Y %H:%M}** · `{ev['evento']}`")
        if ev["detalhe"]:
            st.json(ev["detalhe"], expanded=False)


# ---------- Router ----------

if not ss.cliente_id:
    tela_login()
else:
    with st.sidebar:
        st.write(f"👤 **{ss.usuario}**")
        if st.button("Sair"):
            ss.cliente_id = ss.usuario = None; ss.pagina = "lista"; st.rerun()
    {"lista": tela_lista, "novo": tela_novo, "detalhe": tela_detalhe,
     "revisao": tela_revisao, "trilha": tela_trilha}.get(ss.pagina, tela_lista)()

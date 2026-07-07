"""Daleship — plataforma SaaS de conferência aduaneira (Fase 1 — Comex).

A Fase 1 tem uma jornada principal: conferência documental pré-embarque. A navegação
exposta ao usuário deve refletir isso sem competir com outras propostas de valor.
"""
import html

import streamlit as st

import auth
import db
import estilo
import processamento
from config import PAPEIS, TIPOS_TRANSPORTE, nome_tipo_transporte

st.set_page_config(page_title="Daleship — Conferência Aduaneira", page_icon="🛃", layout="wide")
estilo.aplicar()

# Navegação exposta ao usuário na Fase 1.
FEATURES = [
    {"id": "conferencia", "rotulo": "Conferência de processo", "icone": "📋",
     "resumo": "Suba Invoice, Packing List e documento de transporte: extração, conciliação "
               "item a item, flags regulatórios e apontamentos com citação."},
]

ss = st.session_state
ss.setdefault("cliente_id", None)
ss.setdefault("usuario", None)
ss.setdefault("feature", "conferencia")
ss.setdefault("pagina", "lista")
ss.setdefault("dossie_atual", None)


def ir(pagina: str, dossie_id: str | None = None):
    ss.pagina = pagina
    if dossie_id is not None:
        ss.dossie_atual = dossie_id


# ---------- Login ----------

def tela_login():
    st.title("Daleship — Conferência de Comex")
    st.caption("Acesso do time da trading para conferência documental pré-embarque")
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
    st.caption("Aceitamos PDF, imagem ou Excel (inclusive .xls) como estão. O sistema detecta "
               "o tipo de cada documento pelo próprio conteúdo.")
    referencia = st.text_input("Referência do processo (ex.: PO-2026-0142)")
    tipos = ["pdf", "png", "jpg", "jpeg", "xlsx", "xls"]

    modo = st.radio("Formato dos documentos", [
        "Arquivo combinado (Invoice + Packing List no mesmo arquivo)",
        "Documentos separados (Invoice, Packing List, Transporte)"],
        help="Muitas tradings enviam Invoice e Packing List juntos, em abas do mesmo Excel.")

    if st.button("Voltar"):
        ir("lista"); st.rerun()

    if modo.startswith("Arquivo combinado"):
        up = st.file_uploader("Arquivo do processo (Invoice + Packing List)", type=tipos)
        if st.button("Processar", type="primary", disabled=up is None):
            arq = {"nome": up.name, "mime": up.type or "", "bytes": up.getvalue()}
            with st.spinner("Extraindo, conciliando Invoice × Packing List e buscando precedentes…"):
                dossie_id = processamento.processar_ivpl(
                    ss.cliente_id, referencia or "(sem referência)", arq)
            ir("detalhe", dossie_id); st.rerun()
    else:
        arquivos = {}
        for papel, rotulo in PAPEIS.items():
            up = st.file_uploader(rotulo, type=tipos, key=papel)
            if up is not None:
                arquivos[papel] = {"nome": up.name, "mime": up.type or "", "bytes": up.getvalue()}
        if st.button("Processar", type="primary", disabled=not arquivos):
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
    _dados_extraidos(dossie)

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


def _dados_extraidos(dossie):
    """Mostra o que o Nó 1 extraiu — o valor tangível: dados estruturados de um arquivo bruto."""
    docs = db.listar_documentos(ss.dossie_atual)
    invoice = next((d for d in docs if d["papel"] == "invoice"), None)
    if not invoice:
        return
    dados = invoice["dados_extraidos"] or {}
    itens = dados.get("itens") or []
    campos = dados.get("campos") or {}
    with st.expander(f"Dados extraídos — {len(itens)} item(ns)"
                     + (f" · fonte: {dados.get('fonte_extracao')}" if dados.get("fonte_extracao") else ""),
                     expanded=True):
        if campos:
            st.caption("  ·  ".join(f"**{k.replace('_',' ')}**: {v}" for k, v in campos.items()))
        if itens:
            st.dataframe(
                [{"Código": i.get("codigo"), "Descrição": i.get("descricao"),
                  "Qtd": i.get("quantidade"), "NCM": i.get("ncm") or "—"} for i in itens],
                use_container_width=True, hide_index=True)


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


# ---------- Início (dashboard de features) ----------

def tela_inicio():
    st.title("Conferência documental")
    st.caption("Jornada única da Fase 1: subir documentos, revisar apontamentos e fechar a trilha.")
    st.markdown(
        '<div class="apontamento info"><span class="tag info">📋 Conferência de processo</span>'
        '<br><br>Suba Invoice, Packing List e documento de transporte. O sistema extrai, '
        'concilia, cita a norma e pede revisão humana antes de concluir.</div>',
        unsafe_allow_html=True)
    if st.button("Abrir conferência", use_container_width=True):
        ss.feature = "conferencia"
        ss.pagina = "lista"
        st.rerun()


# ---------- Router ----------

_PAGINAS_CONFERENCIA = {"lista": tela_lista, "novo": tela_novo, "detalhe": tela_detalhe,
                        "revisao": tela_revisao, "trilha": tela_trilha}

if not ss.cliente_id:
    tela_login()
else:
    if ss.feature != "conferencia":
        ss.feature = "conferencia"

    with st.sidebar:
        st.markdown("### 🛃 Daleship")
        st.caption("Conferência documental pré-embarque")
        st.divider()
        for feat in FEATURES:
            tipo = "primary" if ss.feature == feat["id"] else "secondary"
            if st.button(f"{feat['icone']} {feat['rotulo']}", key=f"nav_{feat['id']}",
                         use_container_width=True, type=tipo):
                ss.feature = feat["id"]
                ss.pagina = "lista"
                st.rerun()
        st.divider()
        st.write(f"👤 **{ss.usuario}**")
        if st.button("Sair", use_container_width=True):
            ss.cliente_id = ss.usuario = None
            ss.feature = "conferencia"
            st.rerun()

    _PAGINAS_CONFERENCIA.get(ss.pagina, tela_lista)()

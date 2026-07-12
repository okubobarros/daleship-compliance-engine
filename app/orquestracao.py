"""Orquestração do dossiê — máquina de estados EXPLÍCITA unificando extração, regras_documentais
e a fila de NCM (worker_ncm). Sem Cockpit/FastAPI (Frente 2 pausada).

Estados (em `dossies.estado_pipeline`), cada token = fase CONCLUÍDA:
    recebido → extraindo → regras_documentais_ok → classificando_ncm → consolidando
             → concluido | concluido_com_excecoes

`avancar()` faz UMA transição por chamada. `processar()` roda até um estado terminal OU até
"estacionar" em classificando_ncm aguardando o worker drenar a fila. IDEMPOTENTE por design:
- fases estruturais só rodam quando o estado é o anterior a elas (não refazem fase já passada);
- e são delete+reinsert dos próprios apontamentos (pré-revisão) — reprocessar não duplica;
- a fila de NCM é idempotente (enfileirar ON CONFLICT; worker só toca 'pendente');
- consolidação sobrescreve o resumo, não acumula.
Assim, reprocessar um dossiê que caiu no meio (ex.: apagão de provedor) só retoma o pendente.
"""
from __future__ import annotations

import json

import psycopg2
import psycopg2.extras

import aprendizado
import db
import erp_catalogo
import processamento
import reconciliacao_erp
import regras_documentais
import score_risco
import worker_ncm
from config import DATABASE_URL

TERMINAIS = {"concluido", "concluido_com_excecoes"}
# Apontamentos da fase ESTRUTURAL (regenerados a cada run pré-revisão -> idempotência).
_TIPOS_ESTRUTURAIS = ["divergencia", "documental", "anuencia", "atributos", "regulatorio",
                      "extracao", "reconciliacao_erp"]


# ---------- estado ----------

def estado(dossie_id: str) -> str:
    with psycopg2.connect(DATABASE_URL) as c, c.cursor() as cur:
        cur.execute("SELECT estado_pipeline FROM dossies WHERE id=%s", (dossie_id,))
        r = cur.fetchone()
    return (r[0] if r and r[0] else "recebido")


def _set_estado(dossie_id: str, novo: str) -> str:
    with psycopg2.connect(DATABASE_URL) as c, c.cursor() as cur:
        cur.execute("UPDATE dossies SET estado_pipeline=%s WHERE id=%s", (novo, dossie_id))
        c.commit()
    processamento._log(dossie_id, "pipeline_transicao", {"estado": novo})
    return novo


# ---------- utilidades ----------

def _docs(dossie_id: str) -> list[dict]:
    return db.listar_documentos(dossie_id)


def _campos_por_papel(dossie_id: str) -> dict:
    return {d["papel"]: (d.get("dados_extraidos") or {}).get("campos", {}) for d in _docs(dossie_id)}


def _itens_invoice(dossie_id: str) -> list[dict]:
    inv = next((d for d in _docs(dossie_id) if d["papel"] == "invoice"), None)
    return ((inv or {}).get("dados_extraidos") or {}).get("itens") or []


def _limpar_apontamentos(dossie_id: str, tipos: list[str]) -> None:
    """Remove apontamentos AINDA PENDENTES (pré-revisão) dos tipos dados — base da idempotência.
    Nunca remove apontamento já revisado por humano (status != 'pendente')."""
    with psycopg2.connect(DATABASE_URL) as c, c.cursor() as cur:
        cur.execute("DELETE FROM apontamentos WHERE dossie_id=%s AND status='pendente' "
                    "AND tipo = ANY(%s)", (dossie_id, tipos))
        c.commit()


# ---------- fases ----------

def _fase_extracao(dossie_id: str) -> None:
    """Verifica/garante a extração (idempotente). A extração de fato ocorre no upload
    (processamento). Aqui a fase apenas confirma que há itens; se não houver, sinaliza."""
    if not _itens_invoice(dossie_id):
        processamento._log(dossie_id, "pipeline_extracao_vazia",
                           {"aviso": "sem itens na invoice — extração externa pendente"})


def _apontamento_com_aprendizado(dossie_id: str, cliente_id: str | None, ach: dict) -> None:
    """Insere um achado (formato regras_documentais.avaliar()/reconciliacao_erp.comparar()) e,
    quando há `codigo` + `cliente_id`, anexa ao por_que_importa a correção anterior mais recente
    para o mesmo cliente+tipo de achado (app/aprendizado.py — loop de aprendizado mínimo, CLAUDE.md
    §8). Sem correção anterior, não anexa nada (silêncio, nunca uma suposição)."""
    por_que_importa = ach.get("por_que_importa")
    codigo = ach.get("codigo")
    if cliente_id and codigo:
        sugestao = aprendizado.sugestao_texto(aprendizado.buscar_correcao_anterior(cliente_id, codigo))
        if sugestao:
            por_que_importa = f"{por_que_importa} {sugestao}" if por_que_importa else sugestao
    db.inserir_apontamento(dossie_id, ach["tipo"], ach["severidade"], ach["orgao"],
                           ach["descricao"], None, ach.get("evidencia"),
                           por_que_importa, ach.get("acao_recomendada"), codigo=codigo)


def _fase_regras(dossie_id: str) -> None:
    """Regras estruturais: coerência Invoice×BL (regras_documentais) + flags regulatórios +
    conciliação Invoice×Packing List + Reconciliation Agent (ERP) quando houver. Idempotente
    (delete+reinsert)."""
    _limpar_apontamentos(dossie_id, _TIPOS_ESTRUTURAIS)
    itens = _itens_invoice(dossie_id)
    cliente_id = db.cliente_id_do_dossie(dossie_id)
    for ach in regras_documentais.avaliar(_campos_por_papel(dossie_id)):
        _apontamento_com_aprendizado(dossie_id, cliente_id, ach)
    processamento._flags_regulatorios(dossie_id, itens)
    # conciliação item a item se a invoice e o packing list tiverem itens
    docs = _docs(dossie_id)
    pk = next((d for d in docs if d["papel"] == "packing_list"), None)
    itens_pk = ((pk or {}).get("dados_extraidos") or {}).get("itens") or [] if pk else []
    if itens and itens_pk:
        for div in processamento.conciliar_itens(itens, itens_pk):
            db.inserir_apontamento(dossie_id, "divergencia", div["severidade"], "RFB",
                                   div["descricao"], None)
    # Reconciliation Agent (Nível 1/2 em cascata — Nível 3 é a própria coerência documental
    # acima, que já roda sempre). Retorna o nível alcançado p/ _fase_consolidar poder capar
    # a confiança da classificação quando não houve cruzamento com o catálogo ERP do cliente.
    contexto_cliente = db.contexto_cliente_do_dossie(dossie_id)
    if cliente_id:
        reconciliacao_erp.conciliar(dossie_id, cliente_id, itens, contexto_cliente)


def _fase_enfileirar_ncm(dossie_id: str) -> int:
    """Enfileira os itens da invoice na fila de NCM (idempotente: ON CONFLICT DO NOTHING)."""
    return worker_ncm.enfileirar(dossie_id, _itens_invoice(dossie_id))


def _ncm_pendentes(dossie_id: str) -> int:
    with psycopg2.connect(DATABASE_URL) as c, c.cursor() as cur:
        cur.execute("SELECT count(*) FROM dossie_item_status WHERE dossie_id=%s "
                    "AND status IN ('pendente','processando')", (dossie_id,))
        return cur.fetchone()[0]


def _fase_consolidar(dossie_id: str) -> bool:
    """Converge score_risco + apontamentos + resultado da fila de NCM num resumo único por dossiê,
    com as EXCEÇÕES agregadas (item de baixa confiança / coerência não avaliada). Idempotente.
    Retorna True se houver exceções (-> concluido_com_excecoes)."""
    with psycopg2.connect(DATABASE_URL) as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT status, count(*) n FROM dossie_item_status WHERE dossie_id=%s GROUP BY status",
                    (dossie_id,))
        por_status = {r["status"]: r["n"] for r in cur.fetchall()}
    ncm_alta = por_status.get("concluido", 0)
    ncm_baixa = por_status.get("concluido_confianca_baixa", 0)

    # apontamento agregado de NCM (idempotente): limpa o classificacao pendente e reinsere o resumo
    _limpar_apontamentos(dossie_id, ["classificacao"])
    if ncm_alta or ncm_baixa:
        sev = "atencao" if ncm_baixa else "info"
        # Ponderação por contexto (CLAUDE.md §4 — confiança não pode ser maior do que o que foi
        # de fato cruzado): sem catálogo ERP do cliente, a classificação só foi verificada contra
        # a base normativa (Nível 2), não contra o cadastro interno (Nível 1) — o rótulo de
        # confiança do agregado reflete isso, mesmo quando a similaridade individual (sim_top1)
        # é alta. "revisao_necessaria" = badge amarelo "Review Required" no Cockpit.
        cliente_id = db.cliente_id_do_dossie(dossie_id)
        catalogo = erp_catalogo.buscar_por_cliente(cliente_id) if cliente_id else {}
        contexto_cliente = db.contexto_cliente_do_dossie(dossie_id)
        nivel = reconciliacao_erp.determinar_nivel(catalogo, contexto_cliente)
        por_que_importa = ("Itens de confiança baixa não foram reordenados por LLM+RGI (rate limit/"
                           "provedor) — a sugestão é só por similaridade, a conferir.")
        if nivel != reconciliacao_erp.NIVEL_1_TRIPLE_MATCH:
            confianca_rotulo = "revisao_necessaria"
            por_que_importa += (" Sem catálogo ERP do cliente, a classificação não pôde ser "
                                "cruzada contra o cadastro interno — confiança limitada ao "
                                "cruzamento regulatório (Nível 2).")
        else:
            confianca_rotulo = "alta" if not ncm_baixa else "media"
        db.inserir_apontamento(
            dossie_id, "classificacao", sev, "RFB",
            f"Classificação de NCM: {ncm_alta} item(ns) com sugestão de confiança alta, "
            f"{ncm_baixa} com confiança BAIXA" + (" — revisão manual recomendada." if ncm_baixa else "."),
            None,
            evidencia=f"alta={ncm_alta} · baixa={ncm_baixa} · nível de reconciliação={nivel}",
            por_que_importa=por_que_importa,
            acao_recomendada="Revisar manualmente os itens de confiança baixa antes de submeter.",
            confianca_rotulo=confianca_rotulo)

    # exceções agregadas: baixa confiança + coerência não avaliada + críticos
    aps = db.listar_apontamentos(dossie_id)
    coerencia = sum(1 for a in aps if "não avaliada" in (a.get("descricao") or "").lower())
    criticos = sum(1 for a in aps if a.get("severidade") == "critico")
    score = score_risco.calcular(aps)
    excecoes = {"ncm_confianca_baixa": ncm_baixa, "coerencia_nao_avaliada": coerencia,
                "apontamentos_criticos": criticos}
    tem_excecoes = ncm_baixa > 0 or coerencia > 0 or criticos > 0

    partes = []
    if ncm_baixa:
        partes.append(f"{ncm_baixa} item(ns) com confiança baixa (revisão manual recomendada)")
    if coerencia:
        partes.append(f"{coerencia} coerência(s) Invoice×BL não avaliada(s)")
    if criticos:
        partes.append(f"{criticos} apontamento(s) crítico(s)")
    mensagem = "; ".join(partes) if partes else "Sem exceções — pronto para revisão."

    resumo = {
        "estado": "concluido_com_excecoes" if tem_excecoes else "concluido",
        "score_risco": score,
        "ncm": {"alta": ncm_alta, "baixa": ncm_baixa, "total": ncm_alta + ncm_baixa},
        "excecoes": excecoes, "mensagem": mensagem,
        "apontamentos_total": len(aps),
    }
    with psycopg2.connect(DATABASE_URL) as c, c.cursor() as cur:
        cur.execute("UPDATE dossies SET resumo_consolidado=%s, status='revisao_humana' WHERE id=%s",
                    (json.dumps(resumo), dossie_id))
        c.commit()
    processamento._log(dossie_id, "pipeline_consolidado", resumo)
    return tem_excecoes


# ---------- máquina de estados ----------

def avancar(dossie_id: str) -> str:
    """Executa UMA transição a partir do estado atual e retorna o novo estado (idempotente)."""
    e = estado(dossie_id)
    if e in TERMINAIS:
        return e
    if e == "recebido":
        _fase_extracao(dossie_id)
        return _set_estado(dossie_id, "extraindo")
    if e == "extraindo":
        _fase_regras(dossie_id)
        return _set_estado(dossie_id, "regras_documentais_ok")
    if e == "regras_documentais_ok":
        _fase_enfileirar_ncm(dossie_id)
        return _set_estado(dossie_id, "classificando_ncm")
    if e == "classificando_ncm":
        if _ncm_pendentes(dossie_id) > 0:
            return e  # estacionado: aguardando o worker drenar a fila
        return _set_estado(dossie_id, "consolidando")
    if e == "consolidando":
        com_exc = _fase_consolidar(dossie_id)
        return _set_estado(dossie_id, "concluido_com_excecoes" if com_exc else "concluido")
    return e


def processar(dossie_id: str) -> str:
    """Avança o dossiê até um estado terminal OU até estacionar aguardando o worker."""
    anterior = None
    while True:
        atual = avancar(dossie_id)
        if atual in TERMINAIS or atual == anterior:
            return atual
        anterior = atual

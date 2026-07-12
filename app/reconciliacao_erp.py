"""Reconciliation Agent — cruzamento em cascata conforme os dados disponíveis (não é tudo-ou-nada).

Nível 1 (Triple Match):        Invoice × catálogo ERP do cliente × base normativa (NCM/TEC/RGI).
                                O cenário ideal — permite validar o item específico contra o
                                cadastro interno do cliente, não só contra a regra geral.
Nível 2 (Regulatory Match):    sem catálogo ERP, cruza só Invoice × base normativa. A
                                classificação de NCM e a checagem de anuência (worker_ncm/rag.py)
                                continuam rodando normalmente — é um "revisor de classificação
                                fiscal" sem o cruzamento extra contra o ERP.
Nível 3 (Internal Consistency): coerência documental pura (app/regras_documentais.py) — SEMPRE
                                roda, independente do nível 1/2 acima. Não é um modo exclusivo:
                                é a base que nunca falta, já que Invoice+BL são obrigatórios no
                                gate de upload.

A cascata é sobre O QUE PODE SER CRUZADO PARA CADA ITEM, não uma escolha exclusiva de "modo" —
por isso este módulo só decide e narra o nível 1×2 (a comparação com o ERP); o nível 3 já está
implementado à parte em regras_documentais.py e roda sempre, em paralelo.
"""
from __future__ import annotations

import aprendizado
import erp_catalogo
import processamento
import db

NIVEL_1_TRIPLE_MATCH = 1
NIVEL_2_REGULATORY_MATCH = 2
NIVEL_3_CONSISTENCIA_INTERNA = 3

_NARRATIVA_NIVEL = {
    NIVEL_1_TRIPLE_MATCH: "Catálogo ERP do cliente encontrado — cruzando Invoice × ERP × base "
                          "normativa (Triple Match).",
    NIVEL_2_REGULATORY_MATCH: "Contexto ERP não detectado. Iniciando auditoria regulatória "
                              "baseada em tabelas Siscomex/TEC — sem cruzamento com o cadastro "
                              "interno do cliente.",
    NIVEL_3_CONSISTENCIA_INTERNA: "Sem catálogo ERP nem base normativa aplicável — restrito à "
                                  "coerência documental interna (Invoice × Packing List/BL).",
}

# Checagem por PALAVRA-CHAVE, deliberadamente simples — o campo "Contexto do cliente" (mockup
# design/mockups/estado-vazio.html) é texto livre; interpretamos só a intenção mais comum e
# explícita de pular o cruzamento com o catálogo. Não é um parser de linguagem natural: instrução
# mais sutil/indireta não é capturada. Limitação conhecida, documentada aqui de propósito.
_PEDIDOS_IGNORAR_CATALOGO = (
    "ignorar catalogo", "ignorar cadastro", "nao conferir catalogo", "sem catalogo",
    "apenas impostos", "so impostos", "so conferir impostos",
)


def _normalizar(s: str | None) -> str:
    t = (s or "").lower()
    for de, para in (("á", "a"), ("â", "a"), ("ã", "a"), ("é", "e"), ("ê", "e"),
                     ("í", "i"), ("ó", "o"), ("ô", "o"), ("õ", "o"), ("ú", "u"), ("ç", "c")):
        t = t.replace(de, para)
    return t


def contexto_pede_ignorar_catalogo(contexto_cliente: str | None) -> bool:
    if not contexto_cliente:
        return False
    t = _normalizar(contexto_cliente)
    return any(p in t for p in _PEDIDOS_IGNORAR_CATALOGO)


def determinar_nivel(catalogo: dict, contexto_cliente: str | None = None) -> int:
    """Nível 1 se há catálogo (e o cliente não pediu para ignorá-lo); senão nível 2. A base
    normativa (NCM/RGI/Soluções de Consulta) está sempre populada nesta base (Fase 1), então o
    nível 3 "puro" (nem ERP nem normativa) não é alcançado por este critério simples — fica
    documentado como caso futuro (ex.: quando a classificação abstém para 100% dos itens do
    dossiê por falta de base normativa aplicável)."""
    if catalogo and not contexto_pede_ignorar_catalogo(contexto_cliente):
        return NIVEL_1_TRIPLE_MATCH
    return NIVEL_2_REGULATORY_MATCH


def narrativa(nivel: int) -> str:
    return _NARRATIVA_NIVEL.get(nivel, _NARRATIVA_NIVEL[NIVEL_2_REGULATORY_MATCH])


def comparar(itens_invoice: list[dict], catalogo: dict[str, dict]) -> list[dict]:
    """Nível 1 apenas: compara itens da Invoice contra o catálogo ERP do cliente. Função PURA,
    mesmo formato de achado de regras_documentais.avaliar() — testável sem banco. Catálogo vazio
    -> [] (silêncio; a decisão de cair para o nível 2 é tomada em conciliar(), não aqui)."""
    if not catalogo:
        return []
    achados: list[dict] = []
    for item in itens_invoice:
        codigo = (item.get("codigo") or "").strip()
        if not codigo:
            continue  # sem código do item na invoice, não há o que cruzar contra o ERP
        cadastro = catalogo.get(codigo)
        if cadastro is None:
            achados.append({
                "codigo": "ERP_ITEM_NAO_CADASTRADO", "tipo": "reconciliacao_erp",
                "severidade": "atencao", "orgao": "-",
                "descricao": f"Item '{codigo}' da Invoice não encontrado no catálogo do cliente.",
                "evidencia": f"código: {codigo} · descrição: {item.get('descricao', '-')}",
                "por_que_importa": "Item novo (fornecedor/produto ainda não cadastrado) ou "
                                   "divergência de código entre a Invoice e o ERP — vale "
                                   "confirmar antes de classificar.",
                "acao_recomendada": "Confirme se é um item novo ou um erro de código antes de "
                                    "prosseguir.",
            })
            continue
        ncm_catalogo = (cadastro.get("ncm") or "").strip()
        ncm_invoice = (item.get("ncm") or "").strip()
        if ncm_catalogo and ncm_invoice and ncm_catalogo != ncm_invoice:
            achados.append({
                "codigo": "ERP_NCM_DIVERGENTE", "tipo": "reconciliacao_erp",
                "severidade": "atencao", "orgao": "RFB",
                "descricao": f"NCM do item '{codigo}' diverge entre a Invoice ({ncm_invoice}) e "
                             f"o catálogo do cliente ({ncm_catalogo}).",
                "evidencia": f"Invoice: {ncm_invoice} · ERP: {ncm_catalogo}",
                "por_que_importa": "Pode ser reclassificação recente, erro de cadastro no ERP ou "
                                   "erro na Invoice — os dois lados discordam sobre a mesma "
                                   "mercadoria.",
                "acao_recomendada": "Confirme qual NCM está correto e atualize o lado "
                                    "desatualizado.",
            })
    return achados


def conciliar(dossie_id: str, cliente_id: str, itens_invoice: list[dict],
              contexto_cliente: str | None = None) -> int:
    """Chamado pela orquestração (app/orquestracao.py::_fase_regras). Decide o nível alcançável,
    narra a decisão em log_auditoria (fonte real do "log de raciocínio" da UI — cada linha
    corresponde a um evento de fato gravado, nunca texto decorativo) e, só no nível 1, insere os
    achados de comparar(). Retorna o nível — usado por _fase_consolidar para não atribuir
    confiança "alta" a uma classificação que não pôde ser cruzada contra o cadastro do cliente."""
    catalogo = erp_catalogo.buscar_por_cliente(cliente_id)
    nivel = determinar_nivel(catalogo, contexto_cliente)
    processamento._log(dossie_id, "nivel_reconciliacao_definido", {
        "nivel": nivel,
        "narrativa": narrativa(nivel),
        "catalogo_encontrado": bool(catalogo),
        "contexto_cliente_pediu_ignorar": contexto_pede_ignorar_catalogo(contexto_cliente),
    })
    if nivel == NIVEL_1_TRIPLE_MATCH:
        for ach in comparar(itens_invoice, catalogo):
            # Loop de aprendizado mínimo (app/aprendizado.py, CLAUDE.md §8): anexa a correção
            # anterior mais recente do mesmo cliente para este tipo de achado, se houver.
            por_que_importa = ach.get("por_que_importa")
            sugestao = aprendizado.sugestao_texto(
                aprendizado.buscar_correcao_anterior(cliente_id, ach["codigo"]))
            if sugestao:
                por_que_importa = f"{por_que_importa} {sugestao}" if por_que_importa else sugestao
            db.inserir_apontamento(
                dossie_id, ach["tipo"], ach["severidade"], ach["orgao"], ach["descricao"], None,
                ach.get("evidencia"), por_que_importa, ach.get("acao_recomendada"),
                codigo=ach["codigo"], confianca_rotulo="alta",
            )
    return nivel

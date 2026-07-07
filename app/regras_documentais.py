"""Regras de coerência ENTRE documentos (Invoice × documento de transporte / Draft BL).

É a jornada principal da Fase 1 (DESIGN_SYSTEM §3, homepage.html): detectar, antes do embarque,
incoerências que a alfândega apontaria depois — divergência de Incoterm entre a fatura e o BL, e
condição de frete (Prepaid/Collect) incompatível com o Incoterm.

Função pura, sem I/O — recebe os `campos` já extraídos de cada documento e devolve achados no
formato de decisão (evidencia / por_que_importa / acao_recomendada), testável isoladamente
(CLAUDE.md §9). NÃO cita norma: é regra de coerência documental/contratual (Incoterms 2020), não
exigência de uma norma indexada — por isso `norma_id` fica None e nunca inventa citação.
"""
from __future__ import annotations

import re

# Incoterms 2020 e quem, pela regra, contrata/paga o frete principal.
#   Grupo E/F (EXW, FCA, FAS, FOB): o COMPRADOR paga o frete  -> normalmente "Collect".
#   Grupo C/D (CFR, CIF, CPT, CIP, DAP, DPU, DDP): o VENDEDOR paga -> normalmente "Prepaid".
_INCOTERMS = ("EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP")
_FRETE_COMPRADOR = {"EXW", "FCA", "FAS", "FOB"}          # esperado: Collect
_FRETE_VENDEDOR = {"CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"}  # esperado: Prepaid

_RE_INCOTERM = re.compile(r"\b(" + "|".join(_INCOTERMS) + r")\b", re.I)


def codigo_incoterm(valor: str | None) -> str | None:
    """Extrai o código Incoterm de 3 letras de um campo livre ('FOB Ningbo' -> 'FOB').
    'C&F'/'C+F' são sinônimos históricos de CFR. None quando não há Incoterm reconhecível."""
    if not valor:
        return None
    s = str(valor)
    if re.search(r"\bC\s*[&+]\s*F\b", s, re.I):
        return "CFR"
    m = _RE_INCOTERM.search(s)
    return m.group(1).upper() if m else None


def condicao_frete(valor: str | None) -> str | None:
    """Normaliza a condição de frete para 'prepaid' | 'collect' | None.
    Cobre PT/EN: 'freight prepaid'/'frete pago (na origem)' -> prepaid; 'freight collect'/
    'frete a pagar (no destino)' -> collect."""
    if not valor:
        return None
    t = str(valor).lower()
    if "prepaid" in t or "pré-pago" in t or "pre-pago" in t or "pago na origem" in t or "frete pago" in t:
        return "prepaid"
    if "collect" in t or "a pagar" in t or "pagar no destino" in t or "frete a cobrar" in t:
        return "collect"
    return None


def _frete_esperado(incoterm: str) -> str | None:
    if incoterm in _FRETE_COMPRADOR:
        return "collect"
    if incoterm in _FRETE_VENDEDOR:
        return "prepaid"
    return None


def avaliar(campos_por_papel: dict[str, dict]) -> list[dict]:
    """Cruza Invoice × documento de transporte. Retorna achados no formato de decisão.

    Cada achado: {codigo, tipo, severidade, orgao, descricao, evidencia, por_que_importa,
    acao_recomendada}. Só emite um achado quando os DOIS dados necessários existem — dado
    ausente NÃO vira divergência falsa (lição da conciliação da Fase 1)."""
    inv = campos_por_papel.get("invoice") or {}
    transp = campos_por_papel.get("documento_transporte") or {}

    inc_inv = codigo_incoterm(inv.get("incoterm"))
    inc_bl = codigo_incoterm(transp.get("incoterm"))
    # A condição de frete costuma constar no BL; aceita também a da invoice como fallback.
    frete = condicao_frete(transp.get("condicao_frete")) or condicao_frete(inv.get("condicao_frete"))
    incoterm_efetivo = inc_inv or inc_bl

    achados: list[dict] = []

    # 1) Incoterm divergente entre a Invoice e o BL — precisa dos dois lados para comparar.
    if inc_inv and inc_bl and inc_inv != inc_bl:
        achados.append({
            "codigo": "INCOTERM_MISMATCH", "tipo": "documental", "severidade": "critico",
            "orgao": "RFB",
            "descricao": f"Incoterm divergente: {inc_inv} na Invoice e {inc_bl} no documento de transporte.",
            "evidencia": f"Invoice: {inc_inv} · BL: {inc_bl}",
            "por_que_importa": "Incoterm inconsistente entre os documentos redistribui frete, seguro e "
                               "responsabilidade — e é divergência que trava conferência e atrai fiscalização.",
            "acao_recomendada": "Alinhe o Incoterm entre a Invoice e o BL antes de fechar o embarque.",
        })

    # 2) Condição de frete incompatível com o Incoterm — precisa de Incoterm + condição de frete.
    if incoterm_efetivo and frete:
        esperado = _frete_esperado(incoterm_efetivo)
        if esperado and frete != esperado:
            achados.append({
                "codigo": "FREIGHT_RULE", "tipo": "documental", "severidade": "atencao",
                "orgao": "RFB",
                "descricao": f"Frete {frete.capitalize()} incompatível com o Incoterm {incoterm_efetivo} "
                             f"(esperado {esperado.capitalize()}).",
                "evidencia": f"Incoterm {incoterm_efetivo} · frete {frete.capitalize()}",
                "por_que_importa": "No Incoterm " + incoterm_efetivo + " quem contrata o frete principal é "
                                   + ("o comprador (Collect)" if esperado == "collect" else "o vendedor (Prepaid)")
                                   + "; a condição lida contradiz isso e pode indicar erro de digitação ou de acordo.",
                "acao_recomendada": "Confirme com o exportador/agente qual é a condição de frete correta.",
            })

    return achados

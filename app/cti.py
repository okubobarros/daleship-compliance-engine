"""Feature: Custo Total de Importação (CTI) — cálculo puro, testável sem UI/banco.

Modelo de custo de desembaraço (estimativa — nunca definitivo; alíquotas vêm da camada
Tributos de REFERÊNCIA, frete/seguro são estimados salvo input). ICMS calculado "por dentro"
(gross-up), como na importação real. Cada componente é retornado separado para transparência
— o analista vê a conta inteira, não só o total.
"""
from __future__ import annotations

SISCOMEX_BASE = 115.67   # taxa Siscomex base (1 adição) — camada taxa_siscomex refina depois


def calcular_cti(
    *, preco_unitario: float, quantidade: float, cambio: float,
    ii: float, ipi: float, pis: float, cofins: float, icms: float,
    frete: float | None = None, seguro: float | None = None,
    afrmm_pct: float = 0.0, siscomex: float = SISCOMEX_BASE, modal: str = "maritimo",
) -> dict:
    """Retorna o detalhamento do CTI em BRL. Alíquotas em % (ex.: 16.0). `modal='maritimo'`
    aplica AFRMM sobre o frete; aéreo/outros não têm AFRMM."""
    def pct(x: float) -> float:
        return (x or 0.0) / 100.0

    mercadoria = preco_unitario * quantidade * cambio
    frete = frete if frete is not None else mercadoria * 0.20            # estimativa 20% (ajustável)
    seguro = seguro if seguro is not None else max(mercadoria * 0.002, 60 * cambio)
    cif = mercadoria + frete + seguro

    v_ii = cif * pct(ii)
    v_ipi = (cif + v_ii) * pct(ipi)
    v_pis = cif * pct(pis)
    v_cofins = cif * pct(cofins)

    v_afrmm = frete * pct(afrmm_pct) if modal == "maritimo" else 0.0
    despesas = siscomex + v_afrmm

    # ICMS na importação é "por dentro": entra na própria base. Gross-up.
    base_antes_icms = cif + v_ii + v_ipi + v_pis + v_cofins + despesas
    aliq_icms = pct(icms)
    base_icms = base_antes_icms / (1 - aliq_icms) if aliq_icms < 1 else base_antes_icms
    v_icms = base_icms - base_antes_icms

    impostos = v_ii + v_ipi + v_pis + v_cofins + v_icms
    custo_total = base_antes_icms + v_icms
    return {
        "mercadoria": mercadoria, "frete": frete, "seguro": seguro, "cif": cif,
        "ii": v_ii, "ipi": v_ipi, "pis": v_pis, "cofins": v_cofins, "icms": v_icms,
        "afrmm": v_afrmm, "siscomex": siscomex, "despesas": despesas,
        "impostos": impostos, "custo_total": custo_total,
        "custo_unitario": custo_total / quantidade if quantidade else custo_total,
    }

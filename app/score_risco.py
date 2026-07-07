"""Índice de risco de um processo — agregação dos apontamentos para o gauge do Cockpit.

O layout `cockpit-decisao.html` mostra um "índice de risco / 100" e um rótulo (Baixo/Médio/Alto).
Este módulo é a fonte desse número: função pura sobre a lista de apontamentos, testável isolada
(CLAUDE.md §9). NÃO é um score preditivo/estatístico — é uma agregação determinística e explicável
da severidade do que o motor já apontou (crítico pesa muito mais que atenção, que pesa mais que
informativo). Saturante: nunca passa de 100 e cresce de forma monótona com o nº de achados.

Faixas e cores acompanham o próprio layout do Cockpit:
  < 40  Baixo  (#16A34A) · 40–69 Médio (#F97316) · >= 70 Alto (#E05252)
"""
from __future__ import annotations

# Fator de "sobrevivência" por achado: quanto menor, mais aquele achado empurra o risco pra cima.
# indice = 100 * (1 - Π fator_i). 1 crítico -> 45 (Médio); 2 críticos -> 70 (Alto);
# 1 atenção -> 18 (Baixo); 1 crítico + 2 atenção -> 63 (Médio, quase Alto).
_FATOR = {"critico": 0.55, "atencao": 0.82, "info": 0.96}

_FAIXAS = (
    (40, "Baixo", "#16A34A"),
    (70, "Médio", "#F97316"),
    (10**9, "Alto", "#E05252"),
)


def calcular(apontamentos: list[dict]) -> dict:
    """Recebe apontamentos (cada um com chave 'severidade') e devolve o resumo de risco:
    {indice: 0-100, rotulo, cor, contagem: {critico, atencao, info}, total}."""
    contagem = {"critico": 0, "atencao": 0, "info": 0}
    produto = 1.0
    for ap in apontamentos:
        sev = ap.get("severidade") or "info"
        if sev not in _FATOR:
            sev = "info"
        contagem[sev] += 1
        produto *= _FATOR[sev]
    indice = round(100 * (1 - produto))
    rotulo, cor = next((r, c) for lim, r, c in _FAIXAS if indice < lim)
    return {"indice": indice, "rotulo": rotulo, "cor": cor,
            "contagem": contagem, "total": len(apontamentos)}

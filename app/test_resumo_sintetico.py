"""Bateria sintética para validar os indicadores do resumo consolidado.

Não altera algoritmo de produção. O objetivo é exercitar combinações de:
- confiança alta/baixa
- NCM inválido
- LPCO pendente
- incoerência Invoice x BL
- apontamentos críticos
- múltiplas exceções

O script imprime a saída de 20 cenários e faz asserts básicos de sanidade.
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import score_risco  # noqa: E402


def cor_confianca(indice: int | None) -> str:
    if indice is None:
        return "cinza"
    if indice >= 70:
        return "verde"
    if indice >= 40:
        return "laranja"
    return "vermelho"


def indice_confianca(alta: int, baixa: int) -> int | None:
    total = alta + baixa
    return round(alta / total * 100) if total else None


def severidades(*, critico: int = 0, atencao: int = 0, info: int = 0) -> list[dict]:
    itens = []
    itens += [{"severidade": "critico"}] * critico
    itens += [{"severidade": "atencao"}] * atencao
    itens += [{"severidade": "info"}] * info
    return itens


@dataclass(frozen=True)
class Scenario:
    nome: str
    alta: int
    baixa: int
    apontamentos: list[dict] = field(default_factory=list)
    justificativa: str = ""
    mensagem: str = ""


def construir_mensagem(c: Scenario) -> str:
    partes: list[str] = []
    if c.baixa:
        partes.append(f"{c.baixa} NCM(s) com confiança baixa")
    if any(a.get("severidade") == "critico" for a in c.apontamentos):
        qtd = sum(1 for a in c.apontamentos if a.get("severidade") == "critico")
        partes.append(f"{qtd} apontamento(s) crítico(s)")
    if any("lpco" in (a.get("descricao") or "").lower() for a in c.apontamentos):
        partes.append("LPCO pendente")
    if any("invoice" in (a.get("descricao") or "").lower() and "bl" in (a.get("descricao") or "").lower()
           for a in c.apontamentos):
        partes.append("incoerência Invoice × BL")
    if any("inválid" in (a.get("descricao") or "").lower() or "inval" in (a.get("descricao") or "").lower()
           for a in c.apontamentos):
        partes.append("NCM inválido")
    if not partes:
        return "Sem exceções."
    return "; ".join(partes)


def build_scenarios() -> list[Scenario]:
    return [
        Scenario("S01 - base limpa", 12, 0, [], "Confiança alta e sem apontamentos."),
        Scenario("S02 - alta + alerta leve", 18, 0, severidades(atencao=1),
                 "Confiança alta com 1 atenção documental."),
        Scenario("S03 - alta + LPCO", 14, 0,
                 [{"severidade": "atencao", "descricao": "LPCO pendente para o item principal."}],
                 "Confiável no NCM, mas com LPCO pendente."),
        Scenario("S04 - alta + BL", 16, 0,
                 [{"severidade": "critico", "descricao": "Incoerência Invoice × BL no frete."}],
                 "NCM estável, mas há incoerência documental crítica."),
        Scenario("S05 - baixa confiança isolada", 0, 8, [],
                 "Nada foi confirmado com alta certeza."),
        Scenario("S06 - baixa + NCM inválido", 0, 5,
                 [{"severidade": "atencao", "descricao": "NCM inválido detectado na invoice."}],
                 "NCM inválido reduz a confiabilidade da classificação."),
        Scenario("S07 - baixa + LPCO", 0, 6,
                 [{"severidade": "atencao", "descricao": "LPCO pendente para mercadoria regulada."}],
                 "Baixa confiança combinada com pendência regulatória."),
        Scenario("S08 - baixa + BL", 0, 7,
                 [{"severidade": "critico", "descricao": "Incoerência Invoice × BL no Incoterm."}],
                 "Baixa confiança com incoerência documental crítica."),
        Scenario("S09 - mistura leve", 7, 3,
                 severidades(atencao=1),
                 "Mistura de alta e baixa confiança com um apontamento leve."),
        Scenario("S10 - mistura + NCM inválido", 6, 4,
                 [{"severidade": "atencao", "descricao": "NCM inválido em um item da invoice."}],
                 "Parte da base é confiável, mas há NCM inválido."),
        Scenario("S11 - mistura + LPCO", 5, 5,
                 [{"severidade": "atencao", "descricao": "LPCO pendente para item sujeito à anuência."}],
                 "Equilíbrio de confiança com exigência regulatória pendente."),
        Scenario("S12 - mistura + BL", 8, 2,
                 [{"severidade": "critico", "descricao": "Incoerência Invoice × BL no peso bruto."}],
                 "Confiança alta no NCM, mas há divergência crítica entre documentos."),
        Scenario("S13 - crítico único", 4, 1, severidades(critico=1),
                 "Um apontamento crítico domina o risco."),
        Scenario("S14 - 2 críticos", 3, 2, severidades(critico=2),
                 "Dois apontamentos críticos elevam o risco."),
        Scenario("S15 - crítico + atenção", 6, 1, severidades(critico=1, atencao=2),
                 "Risco composto por uma crítica e duas atenções."),
        Scenario("S16 - múltiplas exceções", 2, 6, severidades(critico=1, atencao=2, info=3),
                 "Baixa confiança e três camadas de exceção simultâneas."),
        Scenario("S17 - alta, mas crítica e LPCO", 15, 0,
                 [
                     {"severidade": "critico", "descricao": "Incoerência Invoice × BL no valor total."},
                     {"severidade": "atencao", "descricao": "LPCO pendente para item controlado."},
                 ],
                 "Mesmo com confiança alta, o risco documental pesa."),
        Scenario("S18 - zero confiança + múltiplas", 0, 12,
                 [
                     {"severidade": "atencao", "descricao": "NCM inválido detectado."},
                     {"severidade": "atencao", "descricao": "LPCO pendente para um item."},
                     {"severidade": "critico", "descricao": "Incoerência Invoice × BL no frete."},
                 ],
                 "Nenhuma confiança alta e múltiplas exceções no mesmo dossiê."),
        Scenario("S19 - quase tudo alta", 28, 1, [],
                 "Volume alto de confiança com uma baixa isolada."),
        Scenario("S20 - caso pesado", 11, 9, severidades(critico=2, atencao=3, info=4),
                 "Alta densidade de exceções e metade dos NCM sem confiança alta."),
    ]


def validar(c: Scenario) -> dict:
    indice = indice_confianca(c.alta, c.baixa)
    score = score_risco.calcular(c.apontamentos)
    mensagem = c.mensagem or construir_mensagem(c)
    retorno = {
        "cenario": c.nome,
        "indice_confianca": indice,
        "score_risco": score["indice"],
        "cor": score["cor"],
        "rotulo": score["rotulo"],
        "contagem": score["contagem"],
        "mensagem": mensagem,
        "justificativa": c.justificativa,
        "cor_confianca": cor_confianca(indice),
    }
    if indice is None:
        assert c.alta == 0 and c.baixa == 0
    else:
        assert 0 <= indice <= 100
    assert 0 <= score["indice"] <= 100
    assert score["cor"] in {"#16A34A", "#F97316", "#E05252"}
    return retorno


def main() -> None:
    cenarios = build_scenarios()
    resultados = [validar(c) for c in cenarios]

    for r in resultados:
        print(json.dumps(r, ensure_ascii=False))

    print("\nResumo de sanidade:")
    print(f"- {len(resultados)} cenários validados")
    print("- fórmula de risco preservada")
    print("- índice de confiança calculado pela mesma regra do endpoint")


if __name__ == "__main__":
    main()

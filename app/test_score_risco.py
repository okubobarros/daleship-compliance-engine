"""Teste do índice de risco (puro)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import score_risco  # noqa: E402


def _aps(**kw):
    out = []
    for sev, n in kw.items():
        out += [{"severidade": sev}] * n
    return out


def main() -> None:
    # Sem apontamentos -> risco 0, Baixo
    z = score_risco.calcular([])
    assert z["indice"] == 0 and z["rotulo"] == "Baixo" and z["total"] == 0

    # Monotonicidade e faixas (acompanham o layout do Cockpit)
    assert score_risco.calcular(_aps(critico=1))["rotulo"] == "Médio"    # 45
    assert score_risco.calcular(_aps(critico=2))["rotulo"] == "Alto"     # 70
    assert score_risco.calcular(_aps(atencao=1))["rotulo"] == "Baixo"    # 18

    # Mais achados nunca diminui o risco
    a = score_risco.calcular(_aps(critico=1))["indice"]
    b = score_risco.calcular(_aps(critico=1, atencao=2))["indice"]
    assert b > a

    # Contagem e severidade desconhecida cai em 'info'
    r = score_risco.calcular(_aps(critico=1, atencao=2, info=3) + [{"severidade": "xpto"}])
    assert r["contagem"] == {"critico": 1, "atencao": 2, "info": 4}
    assert 0 <= r["indice"] <= 100
    print(f"OK score_risco — 1 crít={score_risco.calcular(_aps(critico=1))['indice']}, "
          f"2 crít={score_risco.calcular(_aps(critico=2))['indice']}, "
          f"1 aten={score_risco.calcular(_aps(atencao=1))['indice']}")


if __name__ == "__main__":
    main()

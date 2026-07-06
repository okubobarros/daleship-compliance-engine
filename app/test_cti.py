"""Teste da calculadora de CTI (puro)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cti import calcular_cti  # noqa: E402


def main() -> None:
    r = calcular_cti(preco_unitario=100.0, quantidade=10, cambio=5.0,
                     ii=16.0, ipi=5.0, pis=2.1, cofins=9.65, icms=18.0,
                     frete=1000.0, seguro=50.0, afrmm_pct=8.0, modal="maritimo")
    # mercadoria = 100*10*5 = 5000; cif = 5000+1000+50 = 6050
    assert abs(r["mercadoria"] - 5000) < 1e-6
    assert abs(r["cif"] - 6050) < 1e-6
    assert abs(r["ii"] - 6050 * 0.16) < 1e-6                 # 968
    assert abs(r["ipi"] - (6050 + 968) * 0.05) < 1e-6         # 350.9
    assert abs(r["afrmm"] - 1000 * 0.08) < 1e-6               # 80 (marítimo)
    # ICMS por dentro: base sem icms = cif+ii+ipi+pis+cofins+despesas
    base = 6050 + r["ii"] + r["ipi"] + r["pis"] + r["cofins"] + r["despesas"]
    icms_esperado = base / (1 - 0.18) - base
    assert abs(r["icms"] - icms_esperado) < 1e-6
    assert abs(r["custo_total"] - (base + r["icms"])) < 1e-6
    assert abs(r["custo_unitario"] - r["custo_total"] / 10) < 1e-6
    print(f"OK CTI — CIF R${r['cif']:.2f}, impostos R${r['impostos']:.2f}, "
          f"total R${r['custo_total']:.2f}, unitário R${r['custo_unitario']:.2f}")

    # aéreo não tem AFRMM
    ar = calcular_cti(preco_unitario=100, quantidade=1, cambio=5, ii=0, ipi=0, pis=2.1,
                      cofins=9.65, icms=18, frete=200, seguro=10, afrmm_pct=8, modal="aereo")
    assert ar["afrmm"] == 0.0
    # frete/seguro default quando None
    d = calcular_cti(preco_unitario=100, quantidade=1, cambio=5, ii=0, ipi=0, pis=0,
                     cofins=0, icms=0)
    assert abs(d["frete"] - 500 * 0.20) < 1e-6 and d["seguro"] > 0
    print("OK CTI — aéreo sem AFRMM; frete/seguro estimados quando ausentes")


if __name__ == "__main__":
    main()

"""Teste do matcher de flags regulatórios (sem rede)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import regras_regulatorias as rr  # noqa: E402


def orgaos(desc):
    return {r["orgao"] for r in rr.avaliar(desc)}


def main():
    assert "ANATEL" in orgaos("Roteador Wi-Fi dual band"), orgaos("Roteador Wi-Fi dual band")
    assert "ANATEL" in orgaos("Fone com Bluetooth 5.0")
    assert "Inmetro" in orgaos("Carregador de parede USB-C")
    assert "Inmetro" in orgaos("Bateria de lítio recarregável")
    assert "ANVISA" in orgaos("Termômetro digital infravermelho")
    assert "Inmetro" in orgaos("Brinquedo boneca de pano")
    # acento e caixa não importam
    assert "ANATEL" in orgaos("APARELHO DE RADIOFREQUÊNCIA")
    # produto neutro não dispara
    assert orgaos("Cobertor de estampa coração 80x110cm") == set(), orgaos("Cobertor de estampa coração")
    print("OK: matcher casa wi-fi/ANATEL, carregador-bateria/Inmetro, termometro/ANVISA, e ignora neutro.")


if __name__ == "__main__":
    main()

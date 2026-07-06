"""Flags regulatórios por palavra-chave (call Bonano, dor nº 4).

Sinaliza exigência POSSÍVEL a partir da descrição do produto — ex.: 'wi-fi' → verificar
homologação ANATEL. É probabilidade/alerta, nunca afirmação: o analista decide.
Regras vêm de `regras_regulatorias.yaml` (config-driven — adicionar regra sem tocar em código).
"""
from __future__ import annotations

import pathlib
import re
import unicodedata

import yaml

_ARQ = pathlib.Path(__file__).resolve().parent / "regras_regulatorias.yaml"


def _normalizar(texto: str) -> str:
    """Minúsculas + sem acento — para casar 'radiofrequência' com 'radiofrequencia' etc."""
    nfkd = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _carregar() -> list[dict]:
    dados = yaml.safe_load(_ARQ.read_text(encoding="utf-8"))
    regras = dados.get("regras", [])
    for r in regras:
        # pré-compila cada palavra com FRONTEIRA DE PALAVRA — senão 'raçao' casaria dentro de
        # 'coraçao' (false positive real que pegamos). Hífen tratado como limite.
        padroes = []
        for p in r.get("palavras", []):
            pn = _normalizar(p)
            if pn:
                padroes.append(re.compile(r"(?<![a-z0-9])" + re.escape(pn) + r"(?![a-z0-9])"))
        r["_padroes"] = padroes
    return regras


_REGRAS = _carregar()


def avaliar(descricao: str) -> list[dict]:
    """Regras disparadas por uma descrição de produto (0..N)."""
    alvo = _normalizar(descricao)
    if not alvo:
        return []
    return [r for r in _REGRAS if any(pad.search(alvo) for pad in r["_padroes"])]

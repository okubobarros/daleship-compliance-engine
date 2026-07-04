"""Loaders plugáveis por tipo de fonte.

Cada loader recebe uma FonteConfig e devolve uma lista de UnidadeNormativa já
chunkada (uma unidade citável por item). Adicionar suporte a um novo tipo de fonte
= registrar um novo loader, sem tocar no pipeline.

Princípio de grounding: NUNCA ingerir conteúdo não verificado. O loader 'file' lê
texto normativo já coletado e conferido (JSON estruturado sob seeds/). O loader
'http' é stub proposital — buscar+parsear site governamental sem verificação humana
violaria o princípio de citação confiável, então ele falha explicitamente até ter
uma etapa de verificação real.
"""
from __future__ import annotations

import json
import pathlib
from typing import Callable

from models import FonteConfig, UnidadeNormativa

SEEDS_DIR = pathlib.Path(__file__).resolve().parent / "seeds"

_LOADERS: dict[str, Callable[[FonteConfig], list[UnidadeNormativa]]] = {}


def register(nome: str):
    def deco(fn: Callable[[FonteConfig], list[UnidadeNormativa]]):
        _LOADERS[nome] = fn
        return fn

    return deco


def get_loader(nome: str) -> Callable[[FonteConfig], list[UnidadeNormativa]]:
    if nome not in _LOADERS:
        raise KeyError(f"Loader '{nome}' não registrado. Disponíveis: {sorted(_LOADERS)}")
    return _LOADERS[nome]


@register("file")
def file_loader(fonte: FonteConfig) -> list[UnidadeNormativa]:
    """Lê unidades normativas verificadas de um JSON sob seeds/.

    Formato esperado: lista de objetos {"identificador": str, "texto": str}.
    """
    if not fonte.caminho:
        raise ValueError(f"Fonte {fonte.orgao}/{fonte.tipo_documento}: loader 'file' exige 'caminho'.")
    caminho = SEEDS_DIR / fonte.caminho
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return [UnidadeNormativa(identificador=u["identificador"], texto=u["texto"]) for u in dados]


@register("http")
def http_loader(fonte: FonteConfig) -> list[UnidadeNormativa]:
    """Stub: busca+chunk de fonte HTTP oficial ainda não implementado.

    Exige etapa de verificação humana do conteúdo parseado antes de virar norma
    citável — não ingerir automaticamente sem isso."""
    raise NotImplementedError(
        f"Loader 'http' ainda não implementado para {fonte.fonte_url}. "
        "Colete e verifique o conteúdo, salve como JSON em seeds/ e use o loader 'file'."
    )

"""Loaders plugáveis por tipo de fonte.

Cada loader recebe uma FonteConfig e devolve uma lista de UnidadeNormativa já
chunkada (uma unidade citável por item). Adicionar suporte a um novo tipo de fonte
= registrar um novo loader, sem tocar no pipeline.

Princípio de grounding: NUNCA ingerir conteúdo não verificado. O loader 'file' lê
texto normativo já coletado e conferido (JSON estruturado sob seeds/). O loader
'http' é stub proposital para fontes cuja coleta+parse ainda não foi implementada.
O loader 'ncm_json' consome o JSON oficial da nomenclatura NCM do Portal Único.
"""
from __future__ import annotations

import json
import pathlib
from typing import Callable

import httpx

from models import FonteConfig, UnidadeNormativa

SEEDS_DIR = pathlib.Path(__file__).resolve().parent / "seeds"

# Endpoint oficial do JSON da nomenclatura NCM (Portal Único Siscomex).
NCM_JSON_URL = "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json"

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
    """Stub: coleta+chunk de fonte HTTP oficial ainda não implementada para esta fonte.

    Exige etapa de verificação humana do conteúdo parseado antes de virar norma
    citável — não ingerir automaticamente sem isso."""
    raise NotImplementedError(
        f"Loader 'http' ainda não implementado para {fonte.fonte_url}. "
        "Colete e verifique o conteúdo, salve como JSON em seeds/ e use o loader 'file'."
    )


# --- NCM (Portal Único) ---

def parse_ncm_payload(payload: dict) -> list[UnidadeNormativa]:
    """Transforma o payload JSON da nomenclatura NCM em unidades citáveis.

    Uma unidade por código de nomenclatura. `identificador` = 'NCM <codigo>'.
    Estrutura esperada (a CONFERIR contra o payload real na primeira coleta com o
    portal fora da parada programada): {"Nomenclaturas": [{"Codigo","Descricao",...}]}.
    """
    itens = payload.get("Nomenclaturas") or payload.get("nomenclaturas") or []
    unidades: list[UnidadeNormativa] = []
    for item in itens:
        codigo = (item.get("Codigo") or item.get("codigo") or "").strip()
        descricao = (item.get("Descricao") or item.get("descricao") or "").strip()
        if not codigo:
            continue
        unidades.append(
            UnidadeNormativa(identificador=f"NCM {codigo}", texto=f"{codigo} — {descricao}")
        )
    return unidades


def _portal_em_parada(resp: httpx.Response) -> bool:
    """Detecta a parada programada diária do Portal Único (01:00–03:00): a chamada
    redireciona para parada-programada.json. Não indexar o conteúdo de status."""
    if resp.is_redirect:
        return "parada-programada" in resp.headers.get("location", "")
    return False


@register("ncm_json")
def ncm_json_loader(fonte: FonteConfig) -> list[UnidadeNormativa]:
    """Baixa o JSON oficial da nomenclatura NCM e chunka por código.

    Health-check embutido: se o Portal Único estiver na parada programada, aborta
    com mensagem clara em vez de ingerir o payload de status."""
    with httpx.Client(timeout=120, follow_redirects=False) as client:
        resp = client.get(NCM_JSON_URL)
        if _portal_em_parada(resp):
            raise RuntimeError(
                "Portal Único em parada programada (01:00–03:00). "
                "Rodar a coleta da NCM fora dessa janela."
            )
        resp.raise_for_status()
        payload = resp.json()
    return parse_ncm_payload(payload)

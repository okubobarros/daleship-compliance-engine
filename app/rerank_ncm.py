"""Rerank de NCM por LLM + RGI, com fallback multi-provedor e degradação segura.

Por quê: a similaridade pura (Voyage + pgvector) tem RECALL correto mas RANKING fraco — o NCM
certo do produto acabado (ex.: cobertor 6301) só aparece em ~#8-#20, perdendo para a matéria-prima
têxtil (6006/5516). Dar ao LLM os top-k candidatos + as Regras Gerais de Interpretação (RGI) e pedir
a escolha justificada reordena o certo para o topo (validado nos 3 itens reais do IVPL Luciana).

Resiliência (a lição do Gemini 503): NÃO depender de um provedor. Cadeia de fallback; qualquer
erro/429/5xx cai para o próximo. Se TODOS falharem, devolve o top-1 do retrieval marcado como
`confianca='baixa'` — a sugestão NUNCA trava nem falha em silêncio.

Nota de provedores (2026-07): a lista de free do goal envelheceu. `qwen-2.5-72b:free` e
`deepseek-chat:free` saíram do tier gratuito (404); `llama-3.3-70b:free`, `qwen3-next-80b:free` e
`gpt-oss-120b:free` retornam 429 "rate-limited upstream" de forma persistente. Mas a conta NÃO está
globalmente throttled — 13 outros free respondem 200. A cadeia usa os que foram VALIDADOS respondendo
E classificando o cobertor em 6301 (ver PROVEDORES). Gemini segue principal (padrão fica p/ depois).
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import re
from collections import Counter

import httpx
from dotenv import load_dotenv

_log = logging.getLogger("rerank_ncm")

# Telemetria em processo: quantas vezes cada provedor foi o que RESPONDEU (e quantas caiu em
# confiança baixa). Em processo = reseta no restart do app; para histórico durável, ler o log.
# Serve para saber, em uso real, com que frequência caímos para o 2º/3º da fila (ver estatisticas()).
USO_PROVEDOR: Counter = Counter()

load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
_GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent"

_OR_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
_OR_URL = "https://openrouter.ai/api/v1/chat/completions"

# Cadeia de fallback, em ordem. (tipo, modelo). Gemini principal; depois free do OpenRouter,
# MAIORES PRIMEIRO (mais confiáveis na subposição — ver divergência do gpt-oss-20b no item 2:
# 6301.10 elétrico vs 6301.90 correto). Validados respondendo 200 + classificando o cobertor em
# 6301 (08/07/2026). Os "populares" (llama-3.3-70b, qwen3-next-80b, gpt-oss-120b) estavam em 429
# upstream — fora da cadeia. Escolha de provedor padrão fica para depois (goal).
PROVEDORES: list[tuple[str, str]] = [
    ("gemini", _GEMINI_MODEL),
    ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"),
    ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    ("openrouter", "openai/gpt-oss-20b:free"),
]

_INSTRUCAO = ("Você é classificador fiscal NCM/SH brasileiro. Classifique a mercadoria pelo que ELA "
              "É (produto acabado), não pela matéria-prima. Escolha SOMENTE entre os candidatos "
              "fornecidos, aplicando as Regras Gerais de Interpretação (RGI). Responda só o pedido.")

_FORMATO = ('Responda APENAS com JSON: {"ncm_escolhido": "0000.00.00", "rgi_aplicavel": "RGI 1", '
            '"justificativa": "..."}. O ncm_escolhido DEVE ser um dos candidatos.')


def _normalizar_ncm(valor) -> str | None:
    d = re.sub(r"\D", "", str(valor or ""))
    return f"{d[:4]}.{d[4:6]}.{d[6:8]}" if len(d) >= 8 else None


def _prompt(item: str, candidatos: list[dict], rgi_texto: str) -> str:
    lista = "\n".join(f"{i+1}. NCM {c['ncm']} — {c['texto']}" for i, c in enumerate(candidatos))
    return (f"MERCADORIA: {item}\n\nCANDIDATOS (escolha SOMENTE entre estes):\n{lista}\n\n"
            f"REGRAS GERAIS DE INTERPRETAÇÃO (RGI):\n{rgi_texto}\n\n"
            "Escolha o ÚNICO NCM de 8 dígitos mais adequado para a mercadoria.")


def _parse(texto: str) -> dict | None:
    try:
        limpo = re.sub(r"^```(?:json)?\s*|\s*```$", "", (texto or "").strip())
        d = json.loads(limpo)
        return d if isinstance(d, dict) and d.get("ncm_escolhido") else None
    except Exception:
        return None


def _gemini(item: str, candidatos: list[dict], rgi_texto: str) -> dict | None:
    if not _GEMINI_KEY:
        return None
    corpo = {
        "systemInstruction": {"parts": [{"text": _INSTRUCAO}]},
        "contents": [{"parts": [{"text": _prompt(item, candidatos, rgi_texto)}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": {
            "type": "object", "properties": {
                "ncm_escolhido": {"type": "string"}, "rgi_aplicavel": {"type": "string"},
                "justificativa": {"type": "string"}}}},
    }
    r = httpx.post(_GEMINI_URL, params={"key": _GEMINI_KEY}, json=corpo, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"gemini HTTP {r.status_code}")
    return _parse(r.json()["candidates"][0]["content"]["parts"][0]["text"])


def _openrouter(modelo: str, item: str, candidatos: list[dict], rgi_texto: str) -> dict | None:
    if not _OR_KEY:
        return None
    corpo = {
        "model": modelo, "temperature": 0, "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": f"{_INSTRUCAO} {_FORMATO}"},
            {"role": "user", "content": _prompt(item, candidatos, rgi_texto)},
        ],
    }
    r = httpx.post(_OR_URL, headers={"Authorization": f"Bearer {_OR_KEY}"}, json=corpo, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"openrouter {modelo} HTTP {r.status_code}")
    return _parse(r.json()["choices"][0]["message"]["content"])


def _chamar(tipo: str, modelo: str, item: str, candidatos: list[dict], rgi_texto: str) -> dict | None:
    if tipo == "gemini":
        return _gemini(item, candidatos, rgi_texto)
    return _openrouter(modelo, item, candidatos, rgi_texto)


def escolher(item: str, candidatos: list[dict], rgi_texto: str,
             provedores: list[tuple[str, str]] | None = None) -> dict:
    """Escolhe o NCM entre `candidatos` ([{ncm, texto}], já ordenados por similaridade) via LLM+RGI.

    Percorre a cadeia de provedores; o 1º que responder com um NCM VÁLIDO (presente na lista) vence.
    Se todos falharem/ divergirem para fora da lista, cai no top-1 do retrieval com confiança BAIXA.
    Retorna: {ncm, confianca ('alta'|'baixa'), provedor, rgi, justificativa, tentativas}.
    """
    validos = {c["ncm"] for c in candidatos}
    tentativas: list[str] = []
    for posicao, (tipo, modelo) in enumerate(provedores or PROVEDORES):
        try:
            resp = _chamar(tipo, modelo, item, candidatos, rgi_texto)
        except Exception as e:
            tentativas.append(f"{modelo}: {type(e).__name__}")
            continue
        ncm = _normalizar_ncm((resp or {}).get("ncm_escolhido"))
        if ncm and ncm in validos:
            chave = f"{tipo}:{modelo}"
            USO_PROVEDOR[chave] += 1
            # posicao 0 = venceu o principal; >0 = caiu para o N-ésimo da fila.
            _log.info("rerank via %s (posição %d na fila; %d provedor(es) falharam antes)",
                      chave, posicao, len(tentativas))
            return {"ncm": ncm, "confianca": "alta", "provedor": chave, "posicao_fila": posicao,
                    "rgi": (resp.get("rgi_aplicavel") or "").strip() or None,
                    "justificativa": (resp.get("justificativa") or "").strip(),
                    "tentativas": tentativas}
        tentativas.append(f"{modelo}: {'fora-da-lista' if ncm else 'sem-json'}")
    # Degradação segura: top-1 do retrieval, confiança BAIXA — nunca trava nem silencia.
    USO_PROVEDOR["fallback:retrieval"] += 1
    _log.warning("rerank em confianca_baixa — todos os provedores falharam: %s", tentativas)
    return {"ncm": candidatos[0]["ncm"] if candidatos else None, "confianca": "baixa",
            "provedor": "retrieval", "posicao_fila": None, "rgi": None,
            "justificativa": "Rerank indisponível (todos os provedores falharam) — top-1 por "
                             "similaridade pura, a confirmar.", "tentativas": tentativas}


def estatisticas() -> dict:
    """Contagem em processo de qual provedor respondeu cada rerank (e quantas caíram em baixa).
    Para inspecionar em uso real com que frequência caímos para o 2º/3º da fila. Reseta no restart
    do app — histórico durável fica no log (logger 'rerank_ncm')."""
    return dict(USO_PROVEDOR)

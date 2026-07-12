"""Nó 1 (extração) com LLM real — Gemini (primário) + OpenRouter (fallback de redundância).

Cadeia de provedores (decisão 2026-07-06):
  1. Google Gemini (gemini-3.5-flash, free tier — SEM billing, por decisão; custo ~zero).
  2. OpenRouter (fallback quando o Gemini bate rate limit — redundância, NÃO substituto).
     Exige OPENROUTER_API_KEY no .env; sem a chave, o fallback é pulado.
  3. None -> o caller cai na extração heurística (regex) e/ou sinaliza a falha.
  (Hugging Face inference hospedada: NÃO usar em produção — tier gratuito instável demais
   para o piloto; reservado a experimentação pontual.)

INVOICE GIGANTE (dor "santo graal" da call Bonano — 2.700+ itens): o texto NÃO é mais
truncado silenciosamente; é dividido em BLOCOS por orçamento de caracteres, cada bloco é
extraído separadamente e os resultados são mesclados. Falha de bloco é CONTADA e reportada
(`blocos_falhos`) — extração parcial nunca é silenciosa (lição da Fase 1: parcial silencioso
virava divergência falsa).
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import time

import httpx
from dotenv import load_dotenv

# Garante o .env carregado independente da ordem de import (não depende de config.py).
load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
_OR_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
_OR_URL = "https://openrouter.ai/api/v1/chat/completions"

# Tamanho de bloco p/ invoice gigante. ~18k chars ≈ bem dentro do contexto dos dois provedores;
# os testes reduzem via monkeypatch para exercitar a divisão sem texto enorme.
BLOCO_MAX_CHARS = 18000

_INSTRUCAO = (
    "Você extrai dados estruturados de documentos de comércio exterior (importação): "
    "invoice (fatura comercial), packing list e documento de transporte "
    "(B/L marítimo, AWB aéreo, CRT rodoviário Mercosul). Use null quando não encontrar. "
    "NCM deve ter 8 dígitos no formato 0000.00.00. Detecte o tipo do documento de transporte "
    "pelo próprio conteúdo (ex.: 'Bill of Lading'=B/L, 'Air Waybill'=AWB, 'CRT'=CRT). "
    "IMPORTANTE: 'itens' são APENAS as linhas de MERCADORIA/PRODUTO da fatura (com descrição do "
    "produto, quantidade, valor). NUNCA inclua como item: cabeçalho, endereço, CEP, CNPJ, nome do "
    "comprador/vendedor, condições de pagamento, totais ou observações. "
    "'incoterm' é o termo Incoterms 2020 (EXW/FCA/FAS/FOB/CFR/CIF/CPT/CIP/DAP/DPU/DDP) com o local, "
    "quando houver (ex.: 'FOB Ningbo'). 'condicao_frete' é como o frete aparece no documento "
    "(ex.: 'Freight Prepaid', 'Freight Collect', 'Frete a pagar'). 'pais_origem' é o país de "
    "origem/fabricação da mercadoria (ex.: 'Country of Origin: China', 'Made in Vietnam')."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "tipo_detectado": {"type": "string"},
        "tipo_documento_transporte": {"type": "string", "nullable": True},
        "numero_documento": {"type": "string", "nullable": True},
        "valor_total": {"type": "string", "nullable": True},
        "moeda": {"type": "string", "nullable": True},
        "peso_bruto_kg": {"type": "string", "nullable": True},
        "volumes": {"type": "string", "nullable": True},
        "incoterm": {"type": "string", "nullable": True},
        "condicao_frete": {"type": "string", "nullable": True},
        "pais_origem": {"type": "string", "nullable": True},
        "itens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "codigo": {"type": "string", "nullable": True},
                    "descricao": {"type": "string"},
                    "ncm": {"type": "string", "nullable": True},
                    "quantidade": {"type": "string", "nullable": True},
                },
            },
        },
    },
}

# Descrição textual do formato p/ provedores sem responseSchema nativo (OpenRouter).
_FORMATO_JSON = (
    'Responda APENAS com JSON válido neste formato (sem markdown, sem comentários): '
    '{"tipo_detectado": str, "tipo_documento_transporte": str|null, "numero_documento": str|null, '
    '"valor_total": str|null, "moeda": str|null, "peso_bruto_kg": str|null, "volumes": str|null, '
    '"incoterm": str|null, "condicao_frete": str|null, "pais_origem": str|null, '
    '"itens": [{"codigo": str|null, "descricao": str, "ncm": str|null, "quantidade": str|null}]}'
)

_RE_NCM = re.compile(r"(\d{4})\.?(\d{2})\.?(\d{2})")


def disponivel() -> bool:
    return bool(_KEY or _OR_KEY)


# --- Provedor 1: Gemini ---

def _gemini(papel: str, texto: str) -> dict | None:
    if not _KEY:
        return None
    corpo = {
        "systemInstruction": {"parts": [{"text": _INSTRUCAO}]},
        "contents": [{"parts": [{"text": f"Documento (papel informado: {papel}):\n{texto}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": _SCHEMA},
    }
    return _post_com_retry(corpo)


def _post_com_retry(corpo: dict, tentativas: int = 5) -> dict | None:
    """POST Gemini com backoff em 429/5xx respeitando retryDelay. None = esgotou/definitivo."""
    for tentativa in range(tentativas):
        try:
            resp = httpx.post(_URL, params={"key": _KEY}, json=corpo, timeout=90)
        except httpx.HTTPError:
            time.sleep(2 ** tentativa)
            continue
        if resp.status_code in (429, 500, 503):
            if tentativa == tentativas - 1:
                return None
            espera = _retry_delay(resp) or min(30.0, 3 * (tentativa + 1))
            time.sleep(espera)
            continue
        if resp.status_code != 200:
            return None
        try:
            return json.loads(resp.json()["candidates"][0]["content"]["parts"][0]["text"])
        except Exception:
            return None
    return None


def _retry_delay(resp: httpx.Response) -> float | None:
    try:
        for det in resp.json().get("error", {}).get("details", []):
            rd = det.get("retryDelay")
            if rd:
                return float(str(rd).rstrip("s"))
    except Exception:
        pass
    return None


# --- Provedor 2: OpenRouter (redundância p/ rate limit do Gemini) ---

def _openrouter(papel: str, texto: str, tentativas: int = 2) -> dict | None:
    if not _OR_KEY:
        return None
    corpo = {
        "model": OPENROUTER_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": f"{_INSTRUCAO} {_FORMATO_JSON}"},
            {"role": "user", "content": f"Documento (papel informado: {papel}):\n{texto}"},
        ],
    }
    for tentativa in range(tentativas):
        try:
            resp = httpx.post(_OR_URL, headers={"Authorization": f"Bearer {_OR_KEY}"},
                              json=corpo, timeout=120)
            if resp.status_code == 429:
                time.sleep(10 * (tentativa + 1))
                continue
            resp.raise_for_status()
            conteudo = resp.json()["choices"][0]["message"]["content"]
            # alguns modelos embrulham em cerca markdown mesmo com response_format
            conteudo = re.sub(r"^```(?:json)?\s*|\s*```$", "", conteudo.strip())
            return json.loads(conteudo)
        except Exception:
            if tentativa == tentativas - 1:
                return None
            time.sleep(5)
    return None


# --- Divisão em blocos (invoice gigante) e mesclagem ---

def _dividir_em_blocos(texto: str, max_chars: int | None = None) -> list[str]:
    """Divide por LINHAS respeitando o orçamento de chars — nunca corta item no meio."""
    limite = max_chars or BLOCO_MAX_CHARS
    if len(texto) <= limite:
        return [texto]
    blocos, atual, tamanho = [], [], 0
    for linha in texto.splitlines():
        if atual and tamanho + len(linha) + 1 > limite:
            blocos.append("\n".join(atual))
            atual, tamanho = [], 0
        atual.append(linha)
        tamanho += len(linha) + 1
    if atual:
        blocos.append("\n".join(atual))
    return blocos


def _norm_ncm(valor) -> str | None:
    if not valor:
        return None
    m = _RE_NCM.search(str(valor))
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else None


def _normalizar_bruto(bruto: dict) -> dict:
    campos = {
        "numero": bruto.get("numero_documento"),
        "valor_total": bruto.get("valor_total"),
        "peso_bruto": bruto.get("peso_bruto_kg"),
        "volumes": bruto.get("volumes"),
        "incoterm": bruto.get("incoterm"),
        "condicao_frete": bruto.get("condicao_frete"),
        "pais_origem": bruto.get("pais_origem"),
    }
    itens = []
    for it in bruto.get("itens") or []:
        desc = (it.get("descricao") or "").strip()
        if not desc and not it.get("codigo"):
            continue
        itens.append({
            "codigo": (it.get("codigo") or "").strip() or None,
            "descricao": desc,
            "ncm": _norm_ncm(it.get("ncm")),
            "quantidade": (str(it.get("quantidade")).strip() if it.get("quantidade") is not None else None),
        })
    return {
        "tipo_transporte": bruto.get("tipo_documento_transporte"),
        "campos": {k: v for k, v in campos.items() if v},
        "itens": itens,
    }


def _mesclar(parciais: list[dict | None]) -> dict:
    """Mescla resultados por bloco: itens concatenam; campos/tipo = primeiro não-vazio
    (cabeçalho vive no 1º bloco, totais podem vir no último). Blocos falhos são CONTADOS."""
    itens: list[dict] = []
    campos: dict = {}
    tipo = None
    falhos = 0
    for parcial in parciais:
        if parcial is None:
            falhos += 1
            continue
        itens.extend(parcial["itens"])
        for k, v in parcial["campos"].items():
            campos.setdefault(k, v)
        tipo = tipo or parcial.get("tipo_transporte")
    return {"tipo_transporte": tipo, "campos": campos, "itens": itens,
            "blocos_falhos": falhos, "blocos_total": len(parciais)}


# --- API pública ---

def extrair(papel: str, texto: str) -> dict | None:
    """Extrai o documento (em blocos, se gigante) via Gemini -> OpenRouter -> None.

    Retorna {tipo_transporte, campos, itens, blocos_falhos, blocos_total} ou None quando
    NENHUM bloco pôde ser extraído (caller cai na heurística e/ou sinaliza).
    blocos_falhos > 0 = extração PARCIAL — o caller DEVE sinalizar (nunca silenciar)."""
    if not disponivel() or not (texto or "").strip():
        return None
    parciais: list[dict | None] = []
    for bloco in _dividir_em_blocos(texto):
        bruto = _gemini(papel, bloco)
        if bruto is None:
            bruto = _openrouter(papel, bloco)  # redundância: entra quando o Gemini falha
        parciais.append(_normalizar_bruto(bruto) if bruto is not None else None)
    if all(p is None for p in parciais):
        return None
    return _mesclar(parciais)

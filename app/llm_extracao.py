"""Nó 1 (extração) com LLM real — Google Gemini.

Extração é o nó mais exposto à variação real de documento; nesta fase de piloto (volume
pequeno) vale o modelo melhor. Plugável: sem GEMINI_API_KEY, `disponivel()` é False e o
processamento cai na extração heurística (regex) — o app roda de qualquer jeito.

Recebe o TEXTO já extraído (PDF/Excel); imagem sem OCR fica de fora por ora (decisão de
produto). Enviar o PDF/imagem bruto ao Gemini multimodal é o próximo passo natural quando
os formatos reais da trading forem confirmados.
"""
from __future__ import annotations

import json
import os
import re

import httpx

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

_INSTRUCAO = (
    "Você extrai dados estruturados de documentos de comércio exterior (importação): "
    "invoice (fatura comercial), packing list e documento de transporte "
    "(B/L marítimo, AWB aéreo, CRT rodoviário Mercosul). Use null quando não encontrar. "
    "NCM deve ter 8 dígitos no formato 0000.00.00. Detecte o tipo do documento de transporte "
    "pelo próprio conteúdo (ex.: 'Bill of Lading'=B/L, 'Air Waybill'=AWB, 'CRT'=CRT)."
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
        "itens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "descricao": {"type": "string"},
                    "ncm": {"type": "string", "nullable": True},
                },
            },
        },
    },
}

_RE_NCM = re.compile(r"(\d{4})\.?(\d{2})\.?(\d{2})")


def disponivel() -> bool:
    return bool(_KEY)


def _norm_ncm(valor) -> str | None:
    if not valor:
        return None
    m = _RE_NCM.search(str(valor))
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else None


def extrair(papel: str, texto: str) -> dict | None:
    """Retorna dict normalizado {tipo_transporte, campos, itens} ou None (indisponível/erro)."""
    if not _KEY or not (texto or "").strip():
        return None
    corpo = {
        "systemInstruction": {"parts": [{"text": _INSTRUCAO}]},
        "contents": [{"parts": [{"text": f"Documento (papel informado: {papel}):\n{texto[:20000]}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": _SCHEMA},
    }
    try:
        resp = httpx.post(_URL, params={"key": _KEY}, json=corpo, timeout=90)
        resp.raise_for_status()
        bruto = json.loads(resp.json()["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        return None  # qualquer falha (rede/quota/JSON) -> caller usa heurística

    campos = {
        "numero": bruto.get("numero_documento"),
        "valor_total": bruto.get("valor_total"),
        "peso_bruto": bruto.get("peso_bruto_kg"),
        "volumes": bruto.get("volumes"),
    }
    itens = []
    for it in bruto.get("itens") or []:
        ncm = _norm_ncm(it.get("ncm"))
        desc = (it.get("descricao") or "").strip()
        if ncm or desc:
            itens.append({"descricao": desc, "ncm": ncm})
    return {
        "tipo_transporte": bruto.get("tipo_documento_transporte"),
        "campos": {k: v for k, v in campos.items() if v},
        "itens": itens,
    }

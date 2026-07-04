"""Cliente de embedding — camada compartilhada (ingestão embeda documento, rag_search embeda query).

Decisão fechada: Voyage AI, modelo `voyage-law-2` (especialização jurídica, encaixe para
conteúdo normativo), dimensão de saída fixa 1024, contexto 16k tokens. Free tier 50M tokens.

Interface plugável: se VOYAGE_API_KEY não estiver setada, cai no NullEmbedder (retorna None
por texto → coluna `embedding` fica NULL e a busca segue lexical). Isso mantém o pipeline
rodável sem a chave, e a busca híbrida degrada com segurança para lexical — nunca inventa fonte.
"""
from __future__ import annotations

import asyncio
import os

import httpx

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-law-2"
VOYAGE_DIM = 1024

# Free tier da Voyage (sem cartão): ~3 req/min e ~10K tokens/min. Um lote maior que o
# teto de tokens/min falha com 429 DETERMINÍSTICO (nenhum backoff resolve). Por isso:
#  - lotes montados por ORÇAMENTO DE TOKENS estimados (seguro por default p/ free tier);
#  - pacing proativo entre lotes (60/RPM segundos).
# Com billing habilitado (tier pago: ~2000 RPM / 3M TPM), suba via env:
#   VOYAGE_TPM_BUDGET=120000  VOYAGE_RPM=300
TOKEN_BUDGET_LOTE = int(os.environ.get("VOYAGE_TPM_BUDGET", "8000"))
RPM = float(os.environ.get("VOYAGE_RPM", "3"))
MAX_ITENS_LOTE = 96


def _tokens_estimados(texto: str) -> int:
    # Heurística p/ português: ~3 chars/token, com margem.
    return max(1, len(texto) // 3)


def _montar_lotes(textos: list[str]) -> list[list[str]]:
    """Agrupa textos em lotes que caibam no orçamento de tokens por requisição."""
    lotes: list[list[str]] = []
    atual: list[str] = []
    tokens_atual = 0
    for t in textos:
        t_tokens = _tokens_estimados(t)
        if atual and (tokens_atual + t_tokens > TOKEN_BUDGET_LOTE or len(atual) >= MAX_ITENS_LOTE):
            lotes.append(atual)
            atual, tokens_atual = [], 0
        atual.append(t)
        tokens_atual += t_tokens
    if atual:
        lotes.append(atual)
    return lotes


class NullEmbedder:
    """Fallback sem chave: não gera embedding (mantém a busca lexical)."""

    dim = VOYAGE_DIM
    disponivel = False

    async def embed(self, textos: list[str], input_type: str = "document") -> list[list[float] | None]:
        return [None] * len(textos)


class VoyageEmbedder:
    dim = VOYAGE_DIM
    disponivel = True

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def embed(self, textos: list[str], input_type: str = "document") -> list[list[float]]:
        """Gera embeddings. `input_type`: 'document' na ingestão, 'query' na busca
        (a Voyage otimiza a representação conforme o lado da recuperação)."""
        resultados: list[list[float]] = []
        lotes = _montar_lotes(textos)
        intervalo = 60.0 / RPM if RPM > 0 else 0.0
        async with httpx.AsyncClient(timeout=60) as client:
            for n, lote in enumerate(lotes, start=1):
                if n > 1 and intervalo:
                    await asyncio.sleep(intervalo)  # pacing proativo: não estourar o RPM
                dados = await self._post_com_retry(client, lote, input_type)
                resultados.extend(item["embedding"] for item in dados)
                if len(lotes) > 10 and n % 10 == 0:
                    print(f"  [voyage] lote {n}/{len(lotes)} embedado", flush=True)
        return resultados

    async def _post_com_retry(self, client, lote, input_type, tentativas=7):
        """POST com backoff em rate limit (429) e erros transitórios — necessário para
        ingest grande (ex.: ~15k NCM) não falhar no meio. O free tier da Voyage tem RPM
        baixo (~3/min), então respeitamos Retry-After e usamos espera longa em 429."""
        for tentativa in range(tentativas):
            resp = await client.post(
                VOYAGE_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"input": lote, "model": VOYAGE_MODEL, "input_type": input_type},
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                if tentativa == tentativas - 1:
                    resp.raise_for_status()
                retry_after = resp.headers.get("retry-after")
                espera = float(retry_after) if retry_after else min(25.0, 5 * (tentativa + 1))
                await asyncio.sleep(espera)
                continue
            resp.raise_for_status()
            return resp.json()["data"]
        raise RuntimeError("Voyage: esgotadas as tentativas de embedding.")


def get_embedder() -> NullEmbedder | VoyageEmbedder:
    api_key = os.environ.get("VOYAGE_API_KEY", "").strip()
    if api_key:
        return VoyageEmbedder(api_key)
    return NullEmbedder()

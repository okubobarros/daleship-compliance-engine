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
# Voyage aceita lotes grandes; mantemos conservador por limite de tokens/lote.
BATCH_SIZE = 96


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
        async with httpx.AsyncClient(timeout=60) as client:
            for i in range(0, len(textos), BATCH_SIZE):
                lote = textos[i : i + BATCH_SIZE]
                dados = await self._post_com_retry(client, lote, input_type)
                resultados.extend(item["embedding"] for item in dados)
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

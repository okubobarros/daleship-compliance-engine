"""Cliente de embedding — camada compartilhada (ingestão embeda documento, rag_search embeda query).

Decisão fechada: Voyage AI, modelo `voyage-law-2` (especialização jurídica, encaixe para
conteúdo normativo), dimensão de saída fixa 1024, contexto 16k tokens. Free tier 50M tokens.

Interface plugável: se VOYAGE_API_KEY não estiver setada, cai no NullEmbedder (retorna None
por texto → coluna `embedding` fica NULL e a busca segue lexical). Isso mantém o pipeline
rodável sem a chave, e a busca híbrida degrada com segurança para lexical — nunca inventa fonte.
"""
from __future__ import annotations

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
                resp = await client.post(
                    VOYAGE_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"input": lote, "model": VOYAGE_MODEL, "input_type": input_type},
                )
                resp.raise_for_status()
                dados = resp.json()["data"]
                resultados.extend(item["embedding"] for item in dados)
        return resultados


def get_embedder() -> NullEmbedder | VoyageEmbedder:
    api_key = os.environ.get("VOYAGE_API_KEY", "").strip()
    if api_key:
        return VoyageEmbedder(api_key)
    return NullEmbedder()

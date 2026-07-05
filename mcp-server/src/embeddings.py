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
import time

import httpx

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-law-2"
VOYAGE_DIM = 1024

# Limites da Voyage. O que MORDE no free tier (sem cartão) é o TPM (~10K tokens/min),
# não o RPM: 3 lotes de 8K tokens/min = 24K TPM → 429 DETERMINÍSTICO (backoff não resolve
# o que não cabe na janela de tokens). Por isso o throttle é por JANELA DESLIZANTE DE TPM.
# Defaults conservadores p/ free tier. Com billing (paid: ~2000 RPM / 3M TPM), suba via env:
#   VOYAGE_TPM=2000000  VOYAGE_TOKEN_BUDGET_LOTE=100000
TPM_LIMITE = int(os.environ.get("VOYAGE_TPM", "9000"))          # teto de tokens/60s (margem sob 10K)
TOKEN_BUDGET_LOTE = int(os.environ.get("VOYAGE_TOKEN_BUDGET_LOTE", "2800"))  # tokens/requisição
MAX_ITENS_LOTE = int(os.environ.get("VOYAGE_MAX_ITENS_LOTE", "96"))
# Nunca deixar o orçamento de lote encostar no teto duro de 120K, mesmo se mal configurado.
TOKEN_BUDGET_LOTE = min(TOKEN_BUDGET_LOTE, 110000)


# Teto DURO da Voyage por requisição (não é rate limit — é validação): voyage-law-2
# recusa lote com >120K tokens (400 TOO_MANY_TOKENS_IN_BATCH). O orçamento de lote fica
# com folga sob isso, e o estimador é conservador (superestima), porque a tokenização real
# do texto jurídico PT (números, pontuação) ficou ~13% acima de chars/3 na medição.
MAX_TOKENS_REQUISICAO = 120000


def _tokens_estimados(texto: str) -> int:
    # ~2.6 chars/token: levemente conservador (superestima) para não estourar o teto de lote.
    return max(1, round(len(texto) / 2.6))


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


class _LimitadorTPM:
    """Janela deslizante de 60s: garante que a soma de tokens enviados no último minuto
    (mais o próximo lote) não ultrapasse TPM_LIMITE — o throttle correto para o free tier."""

    def __init__(self, tpm: int):
        self._tpm = tpm
        self._eventos: list[tuple[float, int]] = []  # (monotonic_ts, tokens)

    async def aguardar(self, tokens: int) -> None:
        if self._tpm <= 0:
            return
        while True:
            agora = time.monotonic()
            self._eventos = [(t, n) for t, n in self._eventos if agora - t < 60.0]
            usados = sum(n for _, n in self._eventos)
            if usados + tokens <= self._tpm or not self._eventos:
                self._eventos.append((agora, tokens))
                return
            # dorme até o evento mais antigo sair da janela de 60s
            mais_antigo = min(t for t, _ in self._eventos)
            await asyncio.sleep(max(0.5, 60.0 - (agora - mais_antigo)))


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
        self._limitador = _LimitadorTPM(TPM_LIMITE)  # compartilhado entre chamadas da instância

    async def embed(self, textos: list[str], input_type: str = "document") -> list[list[float]]:
        """Gera embeddings. `input_type`: 'document' na ingestão, 'query' na busca
        (a Voyage otimiza a representação conforme o lado da recuperação)."""
        resultados: list[list[float]] = []
        lotes = _montar_lotes(textos)
        async with httpx.AsyncClient(timeout=60) as client:
            for n, lote in enumerate(lotes, start=1):
                tokens = sum(_tokens_estimados(t) for t in lote)
                await self._limitador.aguardar(tokens)  # respeita o TPM antes de enviar
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

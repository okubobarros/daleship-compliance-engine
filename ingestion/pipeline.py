"""Pipeline genérico de ingestão normativa, dirigido por configuração.

Uso (da raiz do repo, com o venv):
    mcp-server/.venv/Scripts/python.exe ingestion/pipeline.py ingestion/config/fontes_comex.yaml

Fluxo por fonte configurada:
  1. Pula fontes com bloqueado: true (ex.: LPCO de órgão fora do escopo inicial).
  2. Carrega unidades normativas via loader plugável (file/ncm_json/http). Loader não
     implementado é reportado e a fonte é pulada, sem derrubar a execução inteira.
  3. Classifica cada unidade: inalterada (skip idempotente), nova (insert) ou alterada
     (versiona: fecha vigência antiga + insere nova — CLAUDE.md §4, nunca sobrescreve).
  4. Gera embedding (Voyage voyage-law-2) SÓ das unidades que serão escritas — não gasta
     token com o que não mudou. Sem VOYAGE_API_KEY, embedding fica NULL e a busca segue lexical.
  5. Registra provenance completa (orgao, tipo_documento, identificador, fonte_url, vigência).
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from datetime import date

import asyncpg
import httpx
import yaml
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
load_dotenv(ROOT / ".env")

from loaders import get_loader  # noqa: E402
from models import FonteConfig, UnidadeNormativa  # noqa: E402
from embeddings import get_embedder  # noqa: E402


def carregar_fontes(config_path: pathlib.Path) -> list[FonteConfig]:
    dados = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return [FonteConfig.from_dict(item) for item in dados.get("fontes", [])]


def _emb_literal(vetor: list[float] | None) -> str | None:
    if vetor is None:
        return None
    return "[" + ",".join(str(x) for x in vetor) + "]"


# Unidades gravadas por transação. Em runs longos (embedding no free tier da Voyage leva
# ~1h para milhares de ementas), cada chunk commitado sobrevive a uma falha posterior —
# o re-run idempotente pula o que já entrou ('inalterado') e retoma do ponto da falha.
CHUNK_ESCRITA = 500


async def _ingerir_fonte(
    conn: asyncpg.Connection, fonte: FonteConfig, embedder, total: dict
) -> None:
    """Carga em lote: 1 SELECT dos vigentes da fonte, classificação em memória, e
    escrita incremental em chunks (embed do chunk -> transação do chunk).

    IMPORTANTE (auditabilidade): os contadores em `total` só são incrementados DEPOIS
    do commit de cada chunk — o Resumo reporta o que foi realmente gravado, nunca
    intenção. ('inalterado' é contado na classificação: não gera escrita.)"""
    unidades = get_loader(fonte.loader)(fonte)
    vigencia = fonte.data_vigencia_inicio or date.today()

    # Existentes vigentes desta fonte, num único fetch: identificador -> (id, texto).
    linhas = await conn.fetch(
        """
        SELECT id, identificador, texto FROM normas
        WHERE orgao = $1 AND tipo_documento = $2 AND data_vigencia_fim IS NULL
        """,
        fonte.orgao,
        fonte.tipo_documento,
    )
    existentes = {r["identificador"]: (r["id"], r["texto"]) for r in linhas}

    # (unidade, id_antigo_a_fechar_ou_None)
    a_escrever: list[tuple[UnidadeNormativa, object | None]] = []
    for u in unidades:
        atual = existentes.get(u.identificador)
        if atual is None:
            a_escrever.append((u, None))
        elif atual[1] == u.texto:
            total["inalterado"] += 1
        else:
            a_escrever.append((u, atual[0]))

    if not a_escrever:
        return

    n_chunks = (len(a_escrever) + CHUNK_ESCRITA - 1) // CHUNK_ESCRITA
    for c in range(n_chunks):
        chunk = a_escrever[c * CHUNK_ESCRITA : (c + 1) * CHUNK_ESCRITA]

        # Embeda só o chunk. Fontes sem_embedding (NCM = código exato) não embedam.
        if fonte.sem_embedding:
            embeddings: list[list[float] | None] = [None] * len(chunk)
        else:
            embeddings = await embedder.embed([u.texto for u, _ in chunk], input_type="document")

        # Fechar a vigência antiga e inserir a nova versão na MESMA transação do chunk —
        # nunca fica um identificador sem versão vigente se algo falhar no meio.
        ids_antigos = [id_antigo for _, id_antigo in chunk if id_antigo is not None]
        async with conn.transaction():
            if ids_antigos:
                await conn.execute(
                    "UPDATE normas SET data_vigencia_fim = $1 WHERE id = ANY($2::uuid[])",
                    vigencia,
                    ids_antigos,
                )
            await conn.executemany(
                """
                INSERT INTO normas
                    (orgao, tipo_documento, identificador, texto, fonte_url, data_vigencia_inicio, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
                """,
                [
                    (
                        fonte.orgao,
                        fonte.tipo_documento,
                        u.identificador,
                        u.texto,
                        u.fonte_url or fonte.fonte_url,  # permalink por unidade quando existir
                        vigencia,
                        _emb_literal(emb),
                    )
                    for (u, _), emb in zip(chunk, embeddings)
                ],
            )
        # Só conta o que foi de fato commitado.
        for _, id_antigo in chunk:
            total["versionado" if id_antigo is not None else "inserido"] += 1
        if n_chunks > 1:
            print(f"  [chunk] {c + 1}/{n_chunks} gravado ({len(chunk)} unidades)", flush=True)


async def ingerir(config_path: pathlib.Path, filtro_tipo: str | None = None) -> None:
    fontes = carregar_fontes(config_path)
    if filtro_tipo:
        fontes = [f for f in fontes if f.tipo_documento.lower() == filtro_tipo.lower()]
        print(f"Filtro por tipo_documento='{filtro_tipo}': {len(fontes)} fonte(s).")
    embedder = get_embedder()
    print(f"Embedder: {type(embedder).__name__} (disponível={getattr(embedder, 'disponivel', False)})")
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        total = {
            "inserido": 0, "versionado": 0, "inalterado": 0,
            "bloqueado": 0, "sem_loader": 0, "indisponivel": 0,
        }
        for fonte in fontes:
            rotulo = f"{fonte.orgao}/{fonte.tipo_documento}"
            if fonte.bloqueado:
                total["bloqueado"] += 1
                print(f"[BLOQUEADO] {rotulo} — {fonte.descricao or 'represada'} (pulada)")
                continue
            try:
                await _ingerir_fonte(conn, fonte, embedder, total)
                print(f"[OK] {rotulo}")
            except NotImplementedError as e:
                total["sem_loader"] += 1
                print(f"[SEM LOADER] {rotulo}: {e}")
            except (RuntimeError, httpx.HTTPError) as e:
                total["indisponivel"] += 1
                print(f"[INDISPONÍVEL] {rotulo}: {e}")
        print("Resumo:", total)
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("Uso: python ingestion/pipeline.py <config.yaml> [tipo_documento]")
        raise SystemExit(2)
    filtro = sys.argv[2] if len(sys.argv) == 3 else None
    asyncio.run(ingerir(pathlib.Path(sys.argv[1]), filtro))

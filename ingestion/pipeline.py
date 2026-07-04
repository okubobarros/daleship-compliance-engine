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


async def _classificar(
    conn: asyncpg.Connection, fonte: FonteConfig, unidade: UnidadeNormativa
) -> tuple[str, str | None]:
    """Retorna (acao, id_existente): acao ∈ {'inalterado','inserir','versionar'}."""
    existente = await conn.fetchrow(
        """
        SELECT id, texto FROM normas
        WHERE orgao = $1 AND tipo_documento = $2 AND identificador = $3
          AND data_vigencia_fim IS NULL
        """,
        fonte.orgao,
        fonte.tipo_documento,
        unidade.identificador,
    )
    if existente is None:
        return "inserir", None
    if existente["texto"] == unidade.texto:
        return "inalterado", str(existente["id"])
    return "versionar", str(existente["id"])


async def _escrever(
    conn: asyncpg.Connection,
    fonte: FonteConfig,
    unidade: UnidadeNormativa,
    acao: str,
    id_existente: str | None,
    embedding: list[float] | None,
) -> None:
    vigencia = fonte.data_vigencia_inicio or date.today()
    if acao == "versionar":
        await conn.execute(
            "UPDATE normas SET data_vigencia_fim = $1 WHERE id = $2", vigencia, id_existente
        )
    await conn.execute(
        """
        INSERT INTO normas
            (orgao, tipo_documento, identificador, texto, fonte_url, data_vigencia_inicio, embedding)
        VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
        """,
        fonte.orgao,
        fonte.tipo_documento,
        unidade.identificador,
        unidade.texto,
        fonte.fonte_url,
        vigencia,
        _emb_literal(embedding),
    )


async def _ingerir_fonte(
    conn: asyncpg.Connection, fonte: FonteConfig, embedder, total: dict
) -> None:
    unidades = get_loader(fonte.loader)(fonte)

    classificadas = []
    for u in unidades:
        acao, id_existente = await _classificar(conn, fonte, u)
        classificadas.append((u, acao, id_existente))

    # Embeda só o que será escrito (novo/alterado) — poupa token no que não mudou.
    a_escrever = [c for c in classificadas if c[1] != "inalterado"]
    embeddings: list[list[float] | None] = []
    if a_escrever:
        embeddings = await embedder.embed([c[0].texto for c in a_escrever], input_type="document")

    idx = 0
    for unidade, acao, id_existente in classificadas:
        if acao == "inalterado":
            total["inalterado"] += 1
            continue
        await _escrever(conn, fonte, unidade, acao, id_existente, embeddings[idx])
        idx += 1
        total["inserido" if acao == "inserir" else "versionado"] += 1


async def ingerir(config_path: pathlib.Path) -> None:
    fontes = carregar_fontes(config_path)
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
            except RuntimeError as e:
                total["indisponivel"] += 1
                print(f"[INDISPONÍVEL] {rotulo}: {e}")
        print("Resumo:", total)
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python ingestion/pipeline.py <config.yaml>")
        raise SystemExit(2)
    asyncio.run(ingerir(pathlib.Path(sys.argv[1])))

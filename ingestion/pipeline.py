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


async def _ingerir_fonte(
    conn: asyncpg.Connection, fonte: FonteConfig, embedder, total: dict
) -> None:
    """Carga em lote: 1 SELECT dos vigentes da fonte, classificação em memória,
    executemany para versionar (fechar antigas) e inserir — evita 2 round-trips por
    unidade (inviável para ~15k NCM contra Postgres remoto)."""
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

    a_versionar_ids: list = []       # ids de versões antigas a fechar
    a_inserir: list[UnidadeNormativa] = []
    for u in unidades:
        atual = existentes.get(u.identificador)
        if atual is None:
            a_inserir.append(u)
            total["inserido"] += 1
        elif atual[1] == u.texto:
            total["inalterado"] += 1
        else:
            a_versionar_ids.append(atual[0])
            a_inserir.append(u)
            total["versionado"] += 1

    if not a_inserir:
        return

    # Embeda só o que será escrito. Fontes sem_embedding (NCM = código exato) não embedam.
    if fonte.sem_embedding:
        embeddings: list[list[float] | None] = [None] * len(a_inserir)
    else:
        embeddings = await embedder.embed([u.texto for u in a_inserir], input_type="document")

    async with conn.transaction():
        if a_versionar_ids:
            await conn.execute(
                "UPDATE normas SET data_vigencia_fim = $1 WHERE id = ANY($2::uuid[])",
                vigencia,
                a_versionar_ids,
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
                    fonte.fonte_url,
                    vigencia,
                    _emb_literal(emb),
                )
                for u, emb in zip(a_inserir, embeddings)
            ],
        )


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

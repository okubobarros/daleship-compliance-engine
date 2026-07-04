"""Pipeline genérico de ingestão normativa, dirigido por configuração.

Uso (da raiz do repo, com o venv):
    mcp-server/.venv/Scripts/python.exe ingestion/pipeline.py ingestion/config/fontes_comex.yaml

Fluxo por fonte configurada:
  1. Pula fontes com bloqueado: true (ex.: LPCO Anvisa/MAPA aguardando confirmação).
  2. Carrega unidades normativas via loader plugável (file/http).
  3. Faz upsert versionado em `normas` (CLAUDE.md §4): texto igual = idempotente (skip);
     texto mudou = fecha vigência antiga (data_vigencia_fim) + insere nova; inexistente = insere.
  4. Registra provenance completa (orgao, tipo_documento, identificador, fonte_url, vigência).

Não gera embedding ainda: a coluna `embedding` fica NULL até a decisão de provedor de
embedding (Voyage/OpenAI/local) — a busca lexical do rag_search já funciona sem isso.
A dimensão VECTOR(1536) do schema é uma suposição a revisar quando o provedor for escolhido.
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from loaders import get_loader  # noqa: E402
from models import FonteConfig, UnidadeNormativa  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def carregar_fontes(config_path: pathlib.Path) -> list[FonteConfig]:
    dados = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return [FonteConfig.from_dict(item) for item in dados.get("fontes", [])]


async def upsert_norma(
    conn: asyncpg.Connection, fonte: FonteConfig, unidade: UnidadeNormativa
) -> str:
    """Insere/versiona uma unidade em `normas`. Retorna 'inserido' | 'versionado' | 'inalterado'."""
    vigencia = fonte.data_vigencia_inicio or date.today()

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

    if existente is not None and existente["texto"] == unidade.texto:
        return "inalterado"

    if existente is not None:
        # Norma mudou: fecha a vigência da versão antiga (nunca sobrescreve — CLAUDE.md §4).
        await conn.execute(
            "UPDATE normas SET data_vigencia_fim = $1 WHERE id = $2",
            vigencia,
            existente["id"],
        )

    await conn.execute(
        """
        INSERT INTO normas (orgao, tipo_documento, identificador, texto, fonte_url, data_vigencia_inicio)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        fonte.orgao,
        fonte.tipo_documento,
        unidade.identificador,
        unidade.texto,
        fonte.fonte_url,
        vigencia,
    )
    return "versionado" if existente is not None else "inserido"


async def ingerir(config_path: pathlib.Path) -> None:
    fontes = carregar_fontes(config_path)
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        total = {"inserido": 0, "versionado": 0, "inalterado": 0, "bloqueado": 0}
        for fonte in fontes:
            rotulo = f"{fonte.orgao}/{fonte.tipo_documento}"
            if fonte.bloqueado:
                total["bloqueado"] += 1
                print(f"[BLOQUEADO] {rotulo} — {fonte.descricao or 'represada'} (pulada)")
                continue
            unidades = get_loader(fonte.loader)(fonte)
            for unidade in unidades:
                acao = await upsert_norma(conn, fonte, unidade)
                total[acao] += 1
            print(f"[OK] {rotulo}: {len(unidades)} unidade(s) processada(s)")
        print("Resumo:", total)
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python ingestion/pipeline.py <config.yaml>")
        raise SystemExit(2)
    asyncio.run(ingerir(pathlib.Path(sys.argv[1])))

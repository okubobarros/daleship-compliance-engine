"""Harness do golden eval set — mede qualidade de recuperação e CALIBRA o limiar semântico.

Roda cada query do golden_set.yaml contra a base real e:
  - positivos: acha o resultado que casa a expectativa (tipo_documento + substring) e
    registra a distância semântica em que ele apareceu (ou 'lexical' quando só a busca
    lexical o pega — caso da NCM por código);
  - negativos: registra a MENOR distância semântica de qualquer norma (risco de citar
    algo irrelevante).
Depois faz uma VARREDURA DE LIMIAR: para cada candidato T, quantos positivos semânticos
seriam recuperados (dist <= T) e quantos negativos seriam corretamente rejeitados
(dist > T). Reporta o T que maximiza a acurácia e a folga, e o desempenho do 0.65 atual.

Eficiência: embeda TODAS as queries numa única chamada Voyage (poupa rate limit do free tier).

Uso: mcp-server/.venv/Scripts/python.exe eval/run_eval.py
"""
import asyncio
import os
import pathlib
import sys

import asyncpg
import yaml
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
from embeddings import get_embedder  # noqa: E402
from tools.rag_search import DISTANCIA_MAXIMA  # noqa: E402

TOPK = 10
GOLDEN = pathlib.Path(__file__).resolve().parent / "golden_set.yaml"


def _emb_literal(v):
    return "[" + ",".join(str(x) for x in v) + "]"


async def _semantico(conn, emb_lit, k=TOPK):
    return await conn.fetch(
        f"""
        SELECT tipo_documento, identificador, texto, embedding <=> $1::vector AS dist
        FROM normas
        WHERE data_vigencia_fim IS NULL AND embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT {k}
        """,
        emb_lit,
    )


async def _lexical(conn, query, k=TOPK):
    return await conn.fetch(
        f"""
        SELECT tipo_documento, identificador, texto
        FROM normas
        WHERE data_vigencia_fim IS NULL
          AND (texto ILIKE '%'||$1||'%' OR identificador ILIKE '%'||$1||'%')
        LIMIT {k}
        """,
        query,
    )


def _casa(row, espera) -> bool:
    if row["tipo_documento"] != espera["tipo_documento"]:
        return False
    alvo = espera["contem"].lower()
    return alvo in (row["texto"] or "").lower() or alvo in (row["identificador"] or "").lower()


async def main() -> None:
    dados = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    positivos = dados["positivos"]
    negativos = dados["negativos"]

    queries = [p["query"] for p in positivos] + [n["query"] for n in negativos]
    emb = get_embedder()
    if not getattr(emb, "disponivel", False):
        print("VOYAGE_API_KEY ausente — eval semântico precisa de embeddings. Abortando.")
        return
    print(f"Embedando {len(queries)} queries numa chamada...")
    vetores = await emb.embed(queries, input_type="query")
    vpos = vetores[: len(positivos)]
    vneg = vetores[len(positivos):]

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        # --- Positivos ---
        d_pos_semanticos: list[float] = []  # distâncias dos positivos recuperados por semântica
        print("\n=== POSITIVOS ===")
        for p, v in zip(positivos, vpos):
            sem = await _semantico(conn, _emb_literal(v))
            match = next((r for r in sem if _casa(r, p["espera"])), None)
            if match is not None:
                d_pos_semanticos.append(float(match["dist"]))
                print(f"  OK  d={match['dist']:.3f}  {p['query'][:52]:52} -> {match['identificador'][:40]}")
            else:
                lex = await _lexical(conn, p["query"])
                if any(_casa(r, p["espera"]) for r in lex):
                    print(f"  LEX (lexical)   {p['query'][:52]:52} -> {p['espera']['contem']}")
                else:
                    print(f"  MISS            {p['query'][:52]:52} (esperava {p['espera']})")

        # --- Negativos ---
        d_neg_min: list[float] = []
        print("\n=== NEGATIVOS (menor distância = risco de citar irrelevante) ===")
        for n, v in zip(negativos, vneg):
            sem = await _semantico(conn, _emb_literal(v), k=1)
            d = float(sem[0]["dist"]) if sem else 9.9
            d_neg_min.append(d)
            print(f"  d_min={d:.3f}  {n['query'][:60]}")

        # --- Varredura de limiar (só positivos semânticos vs negativos) ---
        print("\n=== VARREDURA DE LIMIAR ===")
        print(f"positivos semânticos: {len(d_pos_semanticos)} | negativos: {len(d_neg_min)}")
        if d_pos_semanticos and d_neg_min:
            print(f"  distância dos positivos: max={max(d_pos_semanticos):.3f} (o mais 'longe' que ainda é relevante)")
            print(f"  distância dos negativos: min={min(d_neg_min):.3f} (o mais 'perto' que ainda é irrelevante)")
            folga = min(d_neg_min) - max(d_pos_semanticos)
            print(f"  FOLGA entre as classes: {folga:+.3f}" + ("  (separáveis)" if folga > 0 else "  (SOBREPOSTAS)"))

            melhor = None
            t = 0.40
            while t <= 0.85 + 1e-9:
                tp = sum(1 for d in d_pos_semanticos if d <= t)
                tn = sum(1 for d in d_neg_min if d > t)
                acc = (tp + tn) / (len(d_pos_semanticos) + len(d_neg_min))
                if melhor is None or acc > melhor[1]:
                    melhor = (round(t, 2), acc, tp, tn)
                t += 0.01

            tp0 = sum(1 for d in d_pos_semanticos if d <= DISTANCIA_MAXIMA)
            tn0 = sum(1 for d in d_neg_min if d > DISTANCIA_MAXIMA)
            acc0 = (tp0 + tn0) / (len(d_pos_semanticos) + len(d_neg_min))
            print(f"\n  Limiar ATUAL {DISTANCIA_MAXIMA}: acurácia={acc0:.0%} "
                  f"(positivos recuperados {tp0}/{len(d_pos_semanticos)}, negativos rejeitados {tn0}/{len(d_neg_min)})")
            print(f"  Melhor limiar da varredura: T={melhor[0]} acurácia={melhor[1]:.0%} "
                  f"(TP {melhor[2]}/{len(d_pos_semanticos)}, TN {melhor[3]}/{len(d_neg_min)})")
            if folga > 0:
                recomendado = round(max(d_pos_semanticos) + folga / 2, 2)
                print(f"  RECOMENDADO (ponto médio da folga): T={recomendado}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

"""Worker standalone da fila híbrida de sugestão de NCM em lote (tabela dossie_item_status).

Roda FORA do request (o rerank LLM em ~300 itens leva minutos — não cabe no caminho síncrono do
dossiê). Puxa itens 'pendente' com FOR UPDATE SKIP LOCKED (N threads não colidem), reranqueia via
rag.sugerir_ncm (retrieval k=25 + LLM+RGI com failover multi-provedor) e grava o resultado por item.

Concorrência (N): o teto real é o RATE LIMIT dos provedores free, não a CPU. Limites documentados
(08/07/2026): OpenRouter free ~20 req/min e ~50 req/dia (conta sem créditos); Gemini free flash
~15 RPM. N=3 sobrepõe a latência (~3-8 s/item) sem estourar muito além dessas RPMs; o failover da
cadeia absorve os 429. Ajuste via env NCM_WORKER_PARALELO. Estado terminal
'concluido_confianca_baixa' NUNCA volta para retry (evita loop infinito quando os provedores caem).

Uso:
    python worker_ncm.py            # processa todos os pendentes e sai
    python worker_ncm.py --resumo   # só imprime a contagem por status
"""
from __future__ import annotations

import os
import sys
import threading
import time
from collections import Counter

import psycopg2
import psycopg2.extras

import rag
from config import DATABASE_URL

N_PARALELO = int(os.environ.get("NCM_WORKER_PARALELO", "3"))


def enfileirar(dossie_id: str, itens: list[dict]) -> int:
    """Insere os itens do dossiê como 'pendente' (idempotente por (dossie_id, item_id)).
    item_id = índice posicional estável; usa a descrição da mercadoria como entrada do rerank."""
    linhas = []
    for i, it in enumerate(itens):
        desc = (it.get("descricao") or "").strip()
        if desc:
            linhas.append((dossie_id, f"{i:04d}", desc))
    if not linhas:
        return 0
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO dossie_item_status (dossie_id, item_id, descricao) VALUES %s "
            "ON CONFLICT (dossie_id, item_id) DO NOTHING",
            linhas)
        conn.commit()
    return len(linhas)


def _claim_one(conn) -> dict | None:
    """Reivindica atomicamente 1 item pendente (SKIP LOCKED) e marca 'processando'."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "UPDATE dossie_item_status SET status='processando', atualizado_em=now() "
            "WHERE id = (SELECT id FROM dossie_item_status WHERE status='pendente' "
            "            ORDER BY criado_em FOR UPDATE SKIP LOCKED LIMIT 1) "
            "RETURNING id, descricao")
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def _gravar(conn, item_pk: str, res: dict) -> str:
    """Grava o resultado do rerank e fecha o item num estado TERMINAL."""
    alta = res.get("confianca") == "alta" and res.get("ncm")
    status = "concluido" if alta else "concluido_confianca_baixa"
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE dossie_item_status SET ncm_sugerido=%s, confianca=%s, provedor_usado=%s, "
            "posicao_fila=%s, status=%s, atualizado_em=now() WHERE id=%s",
            (res.get("ncm"), res.get("confianca"), res.get("provedor"),
             res.get("posicao_fila"), status, item_pk))
        conn.commit()
    return status


def _processar_item(descricao: str) -> dict:
    """Rerank de 1 item. Erro inesperado NÃO estraga a fila: vira confiança baixa (terminal)."""
    try:
        return rag.sugerir_ncm([descricao])[0]
    except Exception as e:  # noqa: BLE001 — qualquer falha dura fecha o item, sem retry infinito
        return {"ncm": None, "confianca": "baixa", "provedor": f"erro:{type(e).__name__}",
                "posicao_fila": None}


def processar(n_paralelo: int = N_PARALELO, max_itens: int | None = None) -> dict:
    """Processa pendentes com N threads até esvaziar a fila (ou até max_itens, p/ simular
    parada/crash no meio). Retorna estatísticas."""
    stats: Counter = Counter()
    lock = threading.Lock()
    processados = [0]

    def loop():
        conn = psycopg2.connect(DATABASE_URL)   # 1 conexão por thread (claim/gravar)
        try:
            while True:
                with lock:
                    if max_itens is not None and processados[0] >= max_itens:
                        return
                item = _claim_one(conn)
                if item is None:
                    return
                res = _processar_item(item["descricao"])
                status = _gravar(conn, item["id"], res)
                with lock:
                    processados[0] += 1
                    stats[status] += 1
                    stats[f"provedor::{res.get('provedor')}"] += 1
        finally:
            conn.close()

    threads = [threading.Thread(target=loop, name=f"ncm-{i}") for i in range(n_paralelo)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return dict(stats)


def resumo(dossie_id: str | None = None) -> dict:
    """Contagem por status (para o polling do frontend / validação)."""
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        if dossie_id:
            cur.execute("SELECT status, count(*) FROM dossie_item_status WHERE dossie_id=%s "
                        "GROUP BY status", (dossie_id,))
        else:
            cur.execute("SELECT status, count(*) FROM dossie_item_status GROUP BY status")
        return {s: n for s, n in cur.fetchall()}


if __name__ == "__main__":
    if "--resumo" in sys.argv:
        print(resumo())
    else:
        t0 = time.perf_counter()
        st = processar()
        print(f"processado em {time.perf_counter()-t0:.1f}s (N={N_PARALELO}):")
        for k, v in sorted(st.items()):
            print(f"   {k}: {v}")

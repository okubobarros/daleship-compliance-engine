"""Teste da telemetria de progresso do worker_ncm (classificacao_ncm_progresso em log_auditoria).

Round-trip real contra o banco (dossie_item_status/log_auditoria não são fáceis de simular sem
banco), mas `rag.sugerir_ncm` é monkeypatchado para não fazer chamada de LLM real (determinístico,
rápido). Objetivo: confirmar que o "log de raciocínio" não fica em silêncio durante um lote grande
(cenário de milhares de itens) — eventos de progresso a cada N itens + um evento final forçado
quando a fila do dossiê esvazia."""
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import db  # noqa: E402
import rag  # noqa: E402
import worker_ncm as wn  # noqa: E402


def main() -> None:
    dossie_id = db.criar_dossie(str(uuid.uuid4()), "teste-worker-ncm-progresso")
    n_itens = 7
    wn.enfileirar(dossie_id, [{"descricao": f"item de teste {i}"} for i in range(n_itens)])

    # monkeypatch: sem chamada de LLM real, resultado determinístico e instantâneo
    rag.sugerir_ncm = lambda descs: [{"ncm": "0000.00.00", "confianca": "alta",
                                      "provedor": "teste", "posicao_fila": 1} for _ in descs]

    original_a_cada = wn.NCM_PROGRESSO_A_CADA
    wn.NCM_PROGRESSO_A_CADA = 2  # força progresso visível com poucos itens
    try:
        stats = wn.processar(n_paralelo=1)
        assert stats.get("concluido") == n_itens, f"esperado {n_itens} concluídos, veio {stats}"

        eventos = [e for e in db.listar_trilha(dossie_id) if e["evento"] == "classificacao_ncm_progresso"]
        assert eventos, "esperado ao menos 1 evento de progresso, veio nenhum"
        # ao menos um evento intermediário (concluidos < total) — log não é só no final
        intermediarios = [e for e in eventos if e["detalhe"]["concluidos"] < e["detalhe"]["total"]]
        assert intermediarios, "esperado ao menos 1 evento intermediário (progresso real, não só no fim)"
        # o último evento deve refletir a fila esvaziada
        final = eventos[-1]
        assert final["detalhe"]["concluidos"] == final["detalhe"]["total"] == n_itens
        print(f"OK worker_ncm — {len(eventos)} eventos de progresso gravados, "
              f"{len(intermediarios)} intermediário(s), evento final reflete fila esvaziada")
    finally:
        wn.NCM_PROGRESSO_A_CADA = original_a_cada
        with db.conectar() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM dossie_item_status WHERE dossie_id=%s", (dossie_id,))
            conn.commit()
        # dossie/log_auditoria ficam (log é append-only — mesma lição de test_aprendizado.py)


if __name__ == "__main__":
    main()

"""Teste da máquina de estados (app/orquestracao.py) — round-trip real contra o banco.

`app/orquestracao.py` não tinha teste algum antes deste trabalho (achado da exploração inicial:
zero chamadores em produção até a Fase 3 conectar `POST /dossies` a ela). `rag.sugerir_ncm` é
monkeypatchado (determinístico, sem chamada de LLM/rede) para o teste ficar rápido e não depender
de rate limit de provedor — a extração em si também não passa por aqui (fixture já vem com
documentos inseridos, como o próprio _fase_extracao assume)."""
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import db  # noqa: E402
import orquestracao as orq  # noqa: E402
import rag  # noqa: E402
import worker_ncm  # noqa: E402


def main() -> None:
    cliente_id = str(uuid.uuid4())
    dossie_id = db.criar_dossie(cliente_id, "teste-orquestracao")

    # fixture: invoice com 1 item + documento_transporte com Incoterm divergente (gera 1 achado
    # crítico), sem packing_list (não testa a conciliação item a item aqui, já coberta em
    # test_regras_documentais.py/test_extracao_blocos.py)
    itens = [{"codigo": "SKU-T1", "descricao": "produto de teste", "ncm": "1234.56.78"}]
    db.inserir_documento(dossie_id, "invoice", None, "invoice.xlsx", "application/vnd", "texto",
                        {"campos": {"incoterm": "FOB", "pais_origem": "China"}, "itens": itens})
    db.inserir_documento(dossie_id, "documento_transporte", "B/L", "bl.pdf", "application/pdf", "texto",
                        {"campos": {"incoterm": "CIF", "condicao_frete": "Freight Prepaid"}, "itens": []})

    # monkeypatch: sem chamada de LLM/rede real
    rag.sugerir_ncm = lambda descs: [{"ncm": "1234.56.78", "confianca": "alta",
                                      "provedor": "teste", "posicao_fila": 1,
                                      "texto": "teste — produto de teste", "candidatos": []}
                                     for _ in descs]

    try:
        estado1 = orq.processar(dossie_id)
        assert estado1 == "classificando_ncm", f"esperado estacionar em classificando_ncm, veio {estado1}"
        assert orq._ncm_pendentes(dossie_id) == 1
        print("OK orquestracao — passa por recebido->extraindo->regras_documentais_ok e estaciona "
              "em classificando_ncm aguardando o worker")

        # achado crítico de Incoterm já deve existir (fase de regras roda antes de estacionar)
        aps = db.listar_apontamentos(dossie_id)
        assert any(a["codigo"] == "INCOTERM_MISMATCH" and a["severidade"] == "critico" for a in aps)
        print("OK orquestracao — achado INCOTERM_MISMATCH (FOB×CIF) já presente antes de estacionar")

        # drena a fila (worker real, mas rag.sugerir_ncm monkeypatchado = sem rede)
        worker_ncm.processar()
        assert orq._ncm_pendentes(dossie_id) == 0

        estado2 = orq.processar(dossie_id)
        assert estado2 in orq.TERMINAIS, f"esperado estado terminal após drenar a fila, veio {estado2}"
        print(f"OK orquestracao — segunda chamada pós-drenagem chega em estado terminal: {estado2}")

        # idempotência: reprocessar um estado terminal não muda nada nem duplica apontamentos
        n_antes = len(db.listar_apontamentos(dossie_id))
        estado3 = orq.processar(dossie_id)
        assert estado3 == estado2
        assert len(db.listar_apontamentos(dossie_id)) == n_antes
        print("OK orquestracao — reprocessar um estado terminal é idempotente (não duplica achados)")
    finally:
        with db.conectar() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM dossie_item_status WHERE dossie_id=%s", (dossie_id,))
            conn.commit()
        # dossie/documentos/apontamentos/log_auditoria ficam (log é append-only — mesma lição de
        # test_aprendizado.py/test_worker_ncm_progresso.py)


if __name__ == "__main__":
    main()

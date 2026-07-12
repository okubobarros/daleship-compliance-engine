"""Teste de db.decidir_dossie / db.registrar_revisao / db.obter_apontamento — as ações antes
decorativas dos botões Aceitar/Corrigir/Escalar/Travar avanço em resultado.html. Round-trip real
contra o banco (cria um dossiê + apontamentos de teste, limpa correcoes ao final — dossiê/
apontamentos ficam, log_auditoria é append-only, mesma lição de test_aprendizado.py)."""
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import db  # noqa: E402


def main() -> None:
    cliente_a = str(uuid.uuid4())
    cliente_b = str(uuid.uuid4())
    dossie_id = db.criar_dossie(cliente_a, "teste-revisao-dossie")
    ap1 = db.inserir_apontamento(dossie_id, "documental", "atencao", "-", "achado 1", None,
                                 codigo="TESTE_REVISAO_1")
    ap2 = db.inserir_apontamento(dossie_id, "documental", "critico", "-", "achado 2", None,
                                 codigo="TESTE_REVISAO_2")

    try:
        # 1) obter_apontamento
        ap = db.obter_apontamento(ap1)
        assert ap["dossie_id"] == dossie_id and ap["status"] == "pendente"
        assert db.obter_apontamento(str(uuid.uuid4())) is None
        print("OK db — obter_apontamento encontra por id, None quando não existe")

        # 2) isolamento por cliente (obter_dossie)
        assert db.obter_dossie(dossie_id, cliente_a) is not None
        assert db.obter_dossie(dossie_id, cliente_b) is None
        print("OK db — obter_dossie isola por cliente_id (dono vs não-dono)")

        # 3) registrar_revisao: aceitar 1 achado (per-card "Aceitar")
        db.registrar_revisao(ap1, dossie_id, True, "achado 1", None, None, cliente_a)
        assert db.obter_apontamento(ap1)["status"] == "validado"
        print("OK db — registrar_revisao(aceito=True) marca 'validado'")

        # 4) registrar_revisao: corrigir o outro achado (per-card "Corrigir")
        db.registrar_revisao(ap2, dossie_id, False, "achado 2", "valor corrigido pelo analista",
                             "justificativa de teste", cliente_a)
        assert db.obter_apontamento(ap2)["status"] == "corrigido"
        print("OK db — registrar_revisao(aceito=False, valor_corrigido=...) marca 'corrigido'")

        # 5) decidir_dossie: aceitar_tudo com um 3º achado ainda pendente
        ap3 = db.inserir_apontamento(dossie_id, "documental", "info", "-", "achado 3", None,
                                     codigo="TESTE_REVISAO_3")
        db.decidir_dossie(dossie_id, "aceitar_tudo", "revisão em lote", cliente_a)
        assert db.obter_apontamento(ap3)["status"] == "validado"
        assert db.obter_dossie(dossie_id, cliente_a)["status"] == "concluido"
        print("OK db — decidir_dossie('aceitar_tudo') aceita pendentes e conclui o dossiê")

        # 6) decidir_dossie: escalar / travar (outro dossiê, para não conflitar com o já concluído)
        dossie2 = db.criar_dossie(cliente_a, "teste-revisao-dossie-2")
        db.decidir_dossie(dossie2, "escalar", "precisa de segunda opinião", cliente_a)
        assert db.obter_dossie(dossie2, cliente_a)["status"] == "escalado"
        eventos = [e["evento"] for e in db.listar_trilha(dossie2)]
        assert "dossie_escalado" in eventos
        print("OK db — decidir_dossie('escalar') muda status e grava evento em log_auditoria")

        dossie3 = db.criar_dossie(cliente_a, "teste-revisao-dossie-3")
        db.decidir_dossie(dossie3, "travar", None, cliente_a)
        assert db.obter_dossie(dossie3, cliente_a)["status"] == "travado"
        print("OK db — decidir_dossie('travar') muda status para 'travado'")

        # 7) decisão inválida levanta erro (o endpoint da API traduz isso pra 400)
        try:
            db.decidir_dossie(dossie3, "decisao_inventada", None, cliente_a)
            raise AssertionError("esperava ValueError para decisão desconhecida")
        except ValueError:
            print("OK db — decidir_dossie rejeita decisão desconhecida (ValueError)")
    finally:
        with db.conectar() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM correcoes WHERE apontamento_id IN "
                       "(SELECT id FROM apontamentos WHERE dossie_id=%s)", (dossie_id,))
            conn.commit()


if __name__ == "__main__":
    main()

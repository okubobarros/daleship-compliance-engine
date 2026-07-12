"""Teste de aprendizado.py — sugestao_texto (puro) + buscar_correcao_anterior (round-trip real
contra o banco, limpa os próprios dados de teste ao final, nunca toca log_auditoria por ser
append-only)."""
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import aprendizado as ap  # noqa: E402
import db  # noqa: E402


def testar_sugestao_texto() -> None:
    assert ap.sugestao_texto(None) is None
    import datetime
    correcao = {"valor_sugerido": "8471.30.19", "valor_corrigido": "8471.41.00",
                "justificativa_analista": "produto tem teclado embutido",
                "criado_em": datetime.datetime(2026, 6, 12)}
    texto = ap.sugestao_texto(correcao)
    assert texto and "8471.30.19" in texto and "8471.41.00" in texto and "12/06/2026" in texto
    print("OK aprendizado — sugestao_texto: None quando não há correção, texto com de/para/data quando há")


def testar_buscar_correcao_anterior_roundtrip() -> None:
    """Cria dossiê/apontamento/correção de teste para 2 clientes, confirma que o lookup só
    encontra a correção do cliente certo (isolamento) e ignora um 'aceitar' puro (sem correção)."""
    cliente_a = str(uuid.uuid4())
    cliente_b = str(uuid.uuid4())
    codigo = f"TESTE_APRENDIZADO_{uuid.uuid4().hex[:8]}"
    ids_dossie = []
    try:
        dossie_a = db.criar_dossie(cliente_a, "teste-aprendizado-a")
        ids_dossie.append(dossie_a)
        ap_id = db.inserir_apontamento(dossie_a, "documental", "atencao", "-",
                                       "achado de teste", None, codigo=codigo)
        db.registrar_revisao(ap_id, dossie_a, aceito=False, valor_sugerido="X",
                             valor_corrigido="Y", justificativa="teste", autor="teste")

        # cliente B nunca corrigiu nada com esse código -> None
        assert ap.buscar_correcao_anterior(cliente_b, codigo) is None

        # cliente A -> encontra a correção real
        achada = ap.buscar_correcao_anterior(cliente_a, codigo)
        assert achada is not None
        assert achada["valor_sugerido"] == "X" and achada["valor_corrigido"] == "Y"

        # 'aceitar' puro (valor_corrigido None) não conta como correção para efeito de aprendizado
        dossie_a2 = db.criar_dossie(cliente_a, "teste-aprendizado-a2")
        ids_dossie.append(dossie_a2)
        ap_id2 = db.inserir_apontamento(dossie_a2, "documental", "atencao", "-",
                                        "achado de teste 2", None, codigo=f"{codigo}_ACEITO")
        db.registrar_revisao(ap_id2, dossie_a2, aceito=True, valor_sugerido="X",
                             valor_corrigido=None, justificativa=None, autor="teste")
        assert ap.buscar_correcao_anterior(cliente_a, f"{codigo}_ACEITO") is None

        print("OK aprendizado — buscar_correcao_anterior: isolado por cliente, ignora 'aceitar' puro")
    finally:
        # Limpeza PARCIAL, de propósito: criar_dossie()/registrar_revisao() gravam em
        # log_auditoria, que é append-only (migration 0010, trigger no banco) — não dá pra apagar
        # dossies/apontamentos sem violar a FK de log_auditoria, e não deveria mesmo (é o ponto do
        # append-only). Os dossiês de teste ficam no banco, claramente marcados pela `referencia`
        # ("teste-aprendizado-..."), como qualquer outro registro real — inofensivo, e consistente
        # com o princípio de que uma vez gerado um evento de auditoria, ele é permanente.
        with db.conectar() as conn, conn.cursor() as cur:
            for did in ids_dossie:
                cur.execute("DELETE FROM correcoes WHERE apontamento_id IN "
                           "(SELECT id FROM apontamentos WHERE dossie_id=%s)", (did,))
            conn.commit()


def main() -> None:
    testar_sugestao_texto()
    testar_buscar_correcao_anterior_roundtrip()


if __name__ == "__main__":
    main()

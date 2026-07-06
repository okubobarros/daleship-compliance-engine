"""Golden eval de grounding do grafo Fase 2 — o teste mais importante do projeto inteiro
(STAKEHOLDER_VISION §1: suíte de regressão dedicada a "nunca alucinar citação").

Porta os princípios já validados (e os bugs já pagos) na Fase 1 para a estrutura LangGraph:
- nunca citar sem chunk de origem recuperado (Guardrail 1);
- chunk semântico fora do limiar calibrado não fundamenta citação (caso 'bolo de cenoura');
- referência forjada no estado é descartada, não repetida;
- abstenção honesta ("sem base normativa localizada") é o resultado correto sem fonte;
- classificação nunca é definitiva única (prováveis + alternativas) e órgão nunca é chutado;
- nenhum resultado é final sem revisão humana (interrupt + guard do Nó 6).

Puro Python — sem banco, sem langgraph, sem rede. Rodar:
    mcp-server/.venv/Scripts/python.exe app/tests/test_grounding.py
"""
from __future__ import annotations

import pathlib
import sys

_RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_RAIZ / "app"))                    # pacote `graph`
sys.path.insert(0, str(_RAIZ / "mcp-server" / "src"))     # limiar calibrado (fonte única)

from grounding import DISTANCIA_MAXIMA  # noqa: E402
from graph.graph import executar_pipeline_sem_langgraph  # noqa: E402
from graph.nodes import no_registro_correcao  # noqa: E402
from graph.nodes.justificativa import SEM_BASE  # noqa: E402

# --- Fixtures: chunks como o Nó 2 os produziria ---

CHUNK_MAPA_LEXICAL = {   # match lexical (distancia None) — sempre citável
    "norma_id": "aaaaaaaa-0000-4000-8000-000000000001",
    "orgao": "MAPA", "identificador": "IN SDA 36/2009, art. 12",
    "texto": "O registro exige indicação do ingrediente ativo...", "fonte_url": "https://x",
    "distancia": None, "via": "lexical",
}
CHUNK_ANVISA_PERTO = {   # semântico DENTRO do limiar — citável
    "norma_id": "aaaaaaaa-0000-4000-8000-000000000002",
    "orgao": "ANVISA", "identificador": "Monografia X, item 3",
    "texto": "A formulação deve declarar...", "fonte_url": "https://y",
    "distancia": round(DISTANCIA_MAXIMA - 0.05, 3), "via": "semantica",
}
CHUNK_LONGE = {          # semântico FORA do limiar — NÃO fundamenta citação
    "norma_id": "aaaaaaaa-0000-4000-8000-000000000003",
    "orgao": "IBAMA", "identificador": "Norma irrelevante",
    "texto": "...", "fonte_url": None,
    "distancia": round(DISTANCIA_MAXIMA + 0.10, 3), "via": "semantica",
}


def _rodar(dados_extraidos, chunks, chunk_ids_por_lacuna=None):
    """Roda o pipeline 1-5 e, se pedido, injeta os chunk_ids na(s) lacuna(s) antes do Nó 4/5."""
    estado = {
        "dossie_id": "d-teste", "cliente_id": "c-teste", "setor": "defensivos",
        "documento_bruto": "(fixture)", "dados_extraidos": dados_extraidos,
        "chunks_recuperados": chunks,
    }
    if chunk_ids_por_lacuna is None:
        return executar_pipeline_sem_langgraph(estado)
    # variante com ancoragem: reproduz o Nó 3 tendo relacionado chunks às lacunas
    from graph.nodes import (no_classificacao_orgao, no_extracao,  # noqa: E402
                             no_justificativa, no_recuperacao_rag, no_verificacao)
    atual = dict(estado)
    for no in (no_extracao, no_recuperacao_rag, no_verificacao):
        atual.update(no(atual))
    for lacuna in atual["lacunas"]:
        lacuna["chunk_ids"] = list(chunk_ids_por_lacuna)
    for no in (no_classificacao_orgao, no_justificativa):
        atual.update(no(atual))
    return atual


def caso_1_cita_quando_ha_fonte():
    """Lacuna ancorada em chunk citável -> apontamento cita a norma e ranqueia candidatos."""
    r = _rodar({}, [CHUNK_MAPA_LEXICAL, CHUNK_ANVISA_PERTO],
               chunk_ids_por_lacuna=[CHUNK_MAPA_LEXICAL["norma_id"], CHUNK_ANVISA_PERTO["norma_id"]])
    ap = r["apontamentos"][0]
    assert ap["sem_base_normativa"] is False
    assert ap["norma_citada_id"] == CHUNK_MAPA_LEXICAL["norma_id"]
    assert ap["orgao"] == "MAPA"                       # órgão vem do chunk, não de palpite
    assert len(ap["candidatos"]) == 2                  # prováveis + alternativas ("verifique")
    assert ap["candidatos"][0]["posicao"] == 1
    print("  caso 1 OK — cita com fonte, órgão do chunk, candidatos ranqueados")


def caso_2_abstem_sem_chunks():
    """Sem nenhum chunk recuperado -> abstenção honesta, órgão None, zero candidatos."""
    r = _rodar({}, [])
    for ap in r["apontamentos"]:
        assert ap["sem_base_normativa"] is True
        assert ap["norma_citada_id"] is None
        assert ap["orgao"] is None
        assert ap["candidatos"] == []
        assert SEM_BASE in ap["descricao"].lower()
    print("  caso 2 OK — abstém sem fonte (nunca inventa)")


def caso_3_fora_do_limiar_nao_cita():
    """Chunk existe mas está FORA do limiar calibrado -> não fundamenta citação
    (porta o caso 'bolo de cenoura' do golden eval da Fase 1)."""
    r = _rodar({}, [CHUNK_LONGE], chunk_ids_por_lacuna=[CHUNK_LONGE["norma_id"]])
    ap = r["apontamentos"][0]
    assert ap["sem_base_normativa"] is True and ap["norma_citada_id"] is None
    print(f"  caso 3 OK — dist {CHUNK_LONGE['distancia']} > {DISTANCIA_MAXIMA} rejeitada")


def caso_4_referencia_forjada_descartada():
    """chunk_id que NÃO está em chunks_recuperados (forjado/alucinado) é descartado."""
    r = _rodar({}, [CHUNK_MAPA_LEXICAL], chunk_ids_por_lacuna=["ffffffff-9999-4999-8999-999999999999"])
    ap = r["apontamentos"][0]
    assert ap["sem_base_normativa"] is True and ap["norma_citada_id"] is None
    print("  caso 4 OK — referência forjada descartada, não repetida")


def caso_5_pipeline_para_na_revisao():
    """O pipeline 1-5 termina em 'revisao_humana' e NÃO executa o Nó 6 sozinho."""
    r = _rodar({"ingrediente_ativo": "X", "formulacao": "Y"}, [])
    assert r["status"] == "revisao_humana"
    assert "eventos_log" not in r or not any(
        e.get("evento") == "dossie_concluido" for e in r.get("eventos_log", []))
    print("  caso 5 OK — para no interrupt (nada é final sem humano)")


def caso_6_no6_recusa_sem_revisao_e_grava_com():
    """Nó 6: recusa sem state['revisao']; com revisão, gravação append-only e conclusão."""
    estado = _rodar({}, [])
    try:
        no_registro_correcao(estado)
        raise AssertionError("Nó 6 deveria recusar sem revisão humana")
    except RuntimeError:
        pass
    estado["revisao"] = [{"indice_apontamento": 0, "acao": "validado", "autor": "analista-teste"}]
    gravados = []
    r = no_registro_correcao(estado, gravar=gravados.append)
    assert r["status"] == "concluido"
    assert any(e["evento"] == "apontamento_revisado" for e in r["eventos_log"])
    assert gravados and gravados[0]["evento"] == "apontamento_revisado"
    print("  caso 6 OK — Nó 6 recusa sem revisão; com revisão grava append-only")


if __name__ == "__main__":
    print(f"Golden eval de grounding (limiar compartilhado = {DISTANCIA_MAXIMA}):")
    caso_1_cita_quando_ha_fonte()
    caso_2_abstem_sem_chunks()
    caso_3_fora_do_limiar_nao_cita()
    caso_4_referencia_forjada_descartada()
    caso_5_pipeline_para_na_revisao()
    caso_6_no6_recusa_sem_revisao_e_grava_com()
    print("TODOS OS CASOS PASSARAM — grounding preservado na estrutura do grafo.")

"""Nó 5 — Justificativa explicável: lacunas -> apontamentos com citação OU abstenção.

Contrato:
    entrada: state['lacunas'] (enriquecidas pelo Nó 4), state['chunks_recuperados']
    saída:   {'apontamentos': [Apontamento, ...], 'status': 'revisao_humana'}

ESTE É O NÓ MAIS CRÍTICO DO GRAFO (ARCHITECTURE §2, princípio não negociável): nunca
produz afirmação sem chunk de origem recuperado no Nó 2. O guard é PROGRAMÁTICO (nunca
instrução de prompt) — mesma disciplina do Code node de grounding do n8n da Fase 1 e do
Guardrail 1 de INFRA_COST_GUARDRAILS.

Regras (todas testadas em app/tests/test_grounding.py):
1. Citação só de chunk PRESENTE em chunks_recuperados (referência forjada é descartada).
2. Chunk semântico fora do limiar calibrado (DISTANCIA_MAXIMA) NÃO fundamenta citação —
   lição do golden eval da Fase 1 ('bolo de cenoura' a 0.518 era citado com limiar frouxo).
   Match lexical (distancia None) é aceito — código/número exato é a via confiável.
3. Sem fonte válida → sem_base_normativa=True + "sem base normativa localizada". Abstenção
   honesta é resultado legítimo; inventar nunca é.
4. Saída sempre carrega candidatos ranqueados (prováveis + alternativas — "verifique").
"""
from __future__ import annotations

import pathlib
import sys

# Limiar calibrado — FONTE ÚNICA DE VERDADE, compartilhada com a Fase 1 (rag_search + app).
_RAIZ = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_RAIZ / "mcp-server" / "src"))
from grounding import DISTANCIA_MAXIMA  # noqa: E402

from ..state import EstadoDossie  # noqa: E402

SEM_BASE = "sem base normativa localizada"


def _chunk_citavel(chunk: dict) -> bool:
    """Um chunk fundamenta citação se tem norma_id e está dentro do limiar (ou é lexical)."""
    if not chunk.get("norma_id"):
        return False
    dist = chunk.get("distancia")
    return dist is None or dist <= DISTANCIA_MAXIMA


def no_justificativa(state: EstadoDossie) -> dict:
    """Converte lacunas em apontamentos: citação grounded ou abstenção explícita."""
    chunks_por_id = {c["norma_id"]: c for c in state.get("chunks_recuperados") or [] if c.get("norma_id")}
    apontamentos = []
    for lacuna in state.get("lacunas") or []:
        # Só chunks REALMENTE recuperados contam — id que não está no estado é forjado.
        citaveis = [
            chunks_por_id[cid]
            for cid in lacuna.get("chunk_ids") or []
            if cid in chunks_por_id and _chunk_citavel(chunks_por_id[cid])
        ]
        orgaos = lacuna.get("_orgaos_candidatos") or []
        if citaveis:
            candidatos = [
                {"norma_id": c["norma_id"], "rotulo": c.get("identificador", ""),
                 "posicao": i + 1, "distancia": c.get("distancia")}
                for i, c in enumerate(citaveis)
            ]
            apontamentos.append({
                "tipo": "lacuna",
                "severidade": "atencao",
                "orgao": orgaos[0] if orgaos else citaveis[0].get("orgao"),
                "descricao": f"{lacuna['descricao']} Base: {citaveis[0].get('identificador', '')} — VERIFIQUE.",
                "norma_citada_id": citaveis[0]["norma_id"],
                "sem_base_normativa": False,
                "candidatos": candidatos,
            })
        else:
            apontamentos.append({
                "tipo": "lacuna",
                "severidade": "info",
                "orgao": None,                      # nunca chutar órgão sem base
                "descricao": f"{lacuna['descricao']} {SEM_BASE.capitalize()}.",
                "norma_citada_id": None,
                "sem_base_normativa": True,
                "candidatos": [],
            })
    return {"apontamentos": apontamentos, "status": "revisao_humana"}

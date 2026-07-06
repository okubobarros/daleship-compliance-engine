"""Nó 4 — Classificação por órgão: rotula cada lacuna pelo órgão anuente responsável.

Contrato:
    entrada: state['lacunas'], state['chunks_recuperados']
    saída:   {'lacunas': lacunas_enriquecidas}  (cada lacuna ganha '_orgaos_candidatos')

Regras herdadas da Fase 1 (lições pagas):
- O órgão vem do METADADO do chunk recuperado, nunca de inferência solta — na Fase 1 a
  semântica atribuía MAPA a medicamento (deriva de órgão); e o órgão anuente real estava
  no identificador, não na coluna `orgao` da fonte (lição SISCOMEX vs ANATEL).
- SEM chunk relacionado → NÃO atribui órgão (None). Chutar órgão é citação errada.
- Saída é LISTA RANQUEADA de órgãos candidatos (prováveis + alternativas), não um único
  definitivo — o padrão validado na sugestão de NCM.
"""
from __future__ import annotations

from ..state import EstadoDossie


def no_classificacao_orgao(state: EstadoDossie) -> dict:
    """Anexa a cada lacuna os órgãos candidatos, derivados só dos chunks relacionados."""
    chunks_por_id = {c["norma_id"]: c for c in state.get("chunks_recuperados") or [] if c.get("norma_id")}
    lacunas = []
    for lacuna in state.get("lacunas") or []:
        orgaos: list[str] = []
        for cid in lacuna.get("chunk_ids") or []:
            chunk = chunks_por_id.get(cid)
            if chunk and chunk.get("orgao") and chunk["orgao"] not in orgaos:
                orgaos.append(chunk["orgao"])  # ordem = ranking dos chunks (mais próximo 1º)
        lacunas.append({**lacuna, "_orgaos_candidatos": orgaos})  # [] = não atribuível
    return {"lacunas": lacunas}

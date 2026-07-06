"""Estado que passa entre os nós do grafo (Fase 2 — MAPA/Bioinsumos).

Princípios herdados da Fase 1 (já validados em produção de demo):
- GROUNDING: toda afirmação normativa referencia um chunk recuperado (norma_id). Sem
  fonte dentro do limiar, o campo fica None e `sem_base_normativa=True` — nunca se inventa.
- PROVÁVEIS + ALTERNATIVAS: classificações/citações são listas RANQUEADAS de candidatos
  ("verifique"), nunca um campo único definitivo (padrão validado na sugestão de NCM).
- MULTIRÓRGÃO: `orgao` é texto livre (MAPA/ANVISA/IBAMA/ICMBio/...) — mesmo espírito da
  generalização tipo_documento_transporte (B/L/AWB/CRT) da Fase 1: config, não hardcode.
- CUSTO: cada nó reporta consumo de tokens (INFRA_COST_GUARDRAILS — orçamento por dossiê).

Sub-estruturas são TypedDicts (dicts serializáveis — sobrevivem a checkpoint do LangGraph
e viram JSONB no Postgres sem conversão).
"""
from __future__ import annotations

from typing import Any, TypedDict


class ChunkRecuperado(TypedDict, total=False):
    """Um trecho normativo recuperado pelo Nó 2 — a ÚNICA fonte legítima de citação."""

    norma_id: str            # UUID em `normas` — obrigatório para citação
    orgao: str               # 'MAPA' | 'ANVISA' | 'IBAMA' | 'ICMBIO' | ... (texto livre)
    identificador: str       # ex.: 'IN SDA 36/2009, art. 12'
    texto: str
    fonte_url: str | None
    distancia: float | None  # cosseno pgvector; None = match lexical
    via: str                 # 'lexical' | 'semantica' | 'lexical+semantica'


class Candidato(TypedDict, total=False):
    """Um candidato ranqueado (padrão 'prováveis + alternativas, verifique')."""

    norma_id: str | None
    rotulo: str              # o que está sendo sugerido (ex.: exigência, enquadramento)
    posicao: int             # 1 = mais provável
    distancia: float | None


class Lacuna(TypedDict, total=False):
    """Saída do Nó 3: um campo/exigência ausente ou inconsistente no dossiê."""

    campo: str
    descricao: str
    chunk_ids: list[str]     # normas relacionadas (podem estar vazias — Nó 5 decide citação)


class Apontamento(TypedDict, total=False):
    """Saída do Nó 5 — o que o humano revisa. Citação obrigatória OU abstenção explícita."""

    tipo: str                        # 'lacuna' | 'inconsistencia' | 'exigencia'
    severidade: str                  # 'critico' | 'atencao' | 'info'
    orgao: str | None                # None = não atribuível com base recuperada (nunca chutar)
    descricao: str
    norma_citada_id: str | None      # None SOMENTE com sem_base_normativa=True
    sem_base_normativa: bool         # True = "sem base normativa localizada" (abstenção honesta)
    candidatos: list[Candidato]      # prováveis + alternativas — nunca um definitivo único


class CorrecaoHumana(TypedDict, total=False):
    """Entrada do resume (pós-interrupt): decisão do analista sobre um apontamento."""

    indice_apontamento: int
    acao: str                        # 'validado' | 'corrigido'
    valor_corrigido: str | None
    justificativa_analista: str | None
    autor: str


class EstadoDossie(TypedDict, total=False):
    """O estado completo do grafo. Nós retornam ATUALIZAÇÕES PARCIAIS (convenção LangGraph)."""

    # Identidade / entrada
    dossie_id: str
    cliente_id: str                  # isolamento lógico por cliente (Guardrail 3)
    setor: str                       # 'defensivos' | 'bioinsumos' | ... (generalização)
    documento_bruto: str             # texto já extraído do(s) arquivo(s) do dossiê

    # Nó 1 — extração
    dados_extraidos: dict[str, Any]

    # Nó 2 — recuperação normativa
    chunks_recuperados: list[ChunkRecuperado]

    # Nó 3 — verificação
    lacunas: list[Lacuna]

    # Nós 4+5 — classificação por órgão + justificativa
    apontamentos: list[Apontamento]

    # INTERRUPT → resume: revisão humana (obrigatória antes do Nó 6)
    revisao: list[CorrecaoHumana]

    # Nó 6 / telemetria
    eventos_log: list[dict]          # espelho append-only do que vai a log_auditoria
    tokens_consumidos: dict[str, int]  # por nó — orçamento de custo por dossiê
    status: str                      # 'em_analise' | 'revisao_humana' | 'concluido'

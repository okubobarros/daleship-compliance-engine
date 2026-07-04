"""Modelos de dados do pipeline de ingestão normativa.

Genéricos por órgão: nenhuma lógica específica de Anvisa/MAPA/qualquer órgão mora
aqui. Um órgão novo (Inmetro, Ibama, Anatel, ANP, Exército) é apenas mais um bloco
de configuração em `ingestion/config/*.yaml`, não código novo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class FonteConfig:
    """Uma fonte normativa a indexar, descrita 100% por configuração."""

    orgao: str                 # 'RFB' | 'CAMEX' | 'ANVISA' | 'MAPA' | ... (autoridade da fonte)
    tipo_documento: str        # 'TEC' | 'RGI' | 'solucao_consulta' | 'tratamento_administrativo' | 'LPCO' | ...
    fonte_url: str             # URL oficial da fonte (obrigatória — provenance)
    loader: str                # nome do loader registrado ('file' | 'http')
    caminho: str | None = None         # para loader 'file': arquivo sob ingestion/seeds/
    data_vigencia_inicio: date | None = None
    bloqueado: bool = False    # True = fonte represada (ex.: LPCO Anvisa/MAPA até confirmação do Bonano)
    descricao: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "FonteConfig":
        vigencia = d.get("data_vigencia_inicio")
        if isinstance(vigencia, str):
            vigencia = date.fromisoformat(vigencia)
        return cls(
            orgao=d["orgao"],
            tipo_documento=d["tipo_documento"],
            fonte_url=d["fonte_url"],
            loader=d["loader"],
            caminho=d.get("caminho"),
            data_vigencia_inicio=vigencia,
            bloqueado=bool(d.get("bloqueado", False)),
            descricao=d.get("descricao", ""),
        )


@dataclass
class UnidadeNormativa:
    """Uma unidade citável (artigo/inciso/regra/NCM) — granularidade de chunk do RAG.

    `identificador` é a chave estável de versionamento junto de (orgao, tipo_documento).
    Ex.: 'RGI Regra 1', 'TEC NCM 2204.10.10', 'Solução de Consulta COSIT 12/2023'.
    """

    identificador: str
    texto: str

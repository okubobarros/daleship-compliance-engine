"""Carga dos Atributos DUIMP por NCM — camada 4 da base normativa (fonte: Atributos NPI).

Fonte oficial (mapa do Bonano, confirmada com CSV estruturado — sem scraping):
    https://www.gov.br/siscomex/pt-br/programa-portal-unico/atributos-novo-processo-de-importacao-npi

Regras:
- Resolver DINÂMICO: o nome do arquivo carrega a data (detalhes_dos_atributos_YYYYMMDD_prod.csv)
  e muda a cada publicação — nunca fixar o nome (mesmo padrão do compilado de anuentes).
- SÓ PRODUÇÃO (_prod). A base de treinamento (_tre) tem atributos ainda em avaliação pelos
  órgãos — não é fonte confiável para o motor. O resolver recusa _tre por construção.
- Snapshot idempotente: `data_referencia` vem do nome do arquivo; se a referência já está
  carregada, a carga é pulada. Referências antigas nunca são sobrescritas.
- Provenance citável: cada snapshot registra uma linha em `normas` (tipo 'atributos_npi',
  versionada por vigência) para os apontamentos de atributo citarem fonte real.

Uso: mcp-server/.venv/Scripts/python.exe ingestion/atributos_npi.py
"""
from __future__ import annotations

import asyncio
import csv
import io
import os
import pathlib
import re
import sys
from datetime import date, datetime

import asyncpg
import httpx
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PAGINA_NPI = "https://www.gov.br/siscomex/pt-br/programa-portal-unico/atributos-novo-processo-de-importacao-npi"
_UA = {"User-Agent": "Mozilla/5.0 (compatible; daleship-compliance-engine/1.0)"}

_RE_CSV_PROD = re.compile(r'href="([^"]*(detalhes|vinculos)_dos_atributos_(\d{8})_prod\.csv)"', re.I)


def resolver_csvs_prod(html: str) -> tuple[str, str, date]:
    """Acha na página oficial os DOIS CSVs de PRODUÇÃO e a data de referência.

    Recusa _tre por construção (o regex só casa _prod). Se houver mais de uma data,
    usa a mais recente. Falha explícita se faltar um dos dois arquivos."""
    encontrados: dict[str, dict[str, str]] = {}
    for url, tipo, ymd in _RE_CSV_PROD.findall(html):
        encontrados.setdefault(ymd, {})[tipo.lower()] = url
    if not encontrados:
        raise RuntimeError("Nenhum CSV _prod encontrado na página oficial do Atributos NPI.")
    ymd = max(encontrados)
    par = encontrados[ymd]
    if "detalhes" not in par or "vinculos" not in par:
        raise RuntimeError(f"Snapshot {ymd} incompleto na página (faltou detalhes ou vinculos).")
    ref = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:]))
    return par["detalhes"], par["vinculos"], ref


def _data(valor: str) -> date | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    return datetime.strptime(valor, "%d/%m/%Y").date()


def _bool(valor: str) -> bool:
    return (valor or "").strip().lower() == "true"


def parse_detalhes(linhas: list[list[str]]) -> tuple[list[dict], list[dict]]:
    """CSV de detalhes -> (definições, valores de domínio).

    O CSV repete o atributo 1x por valor de domínio; a definição é deduplicada pelo código
    (primeira ocorrência) e cada linha com 'Código do valor' vira uma linha de domínio."""
    definicoes: dict[str, dict] = {}
    dominio: list[dict] = []
    for r in linhas[1:]:
        if len(r) < 16 or not r[0].strip():
            continue
        cod = r[0].strip()
        if cod not in definicoes:
            definicoes[cod] = {
                "codigo": cod, "atributo_condicionante": r[1].strip() or None,
                "atributo_condicionado": r[2].strip() or None, "nome": r[3].strip(),
                "nome_apresentacao": r[4].strip() or None, "objetivos": r[5].strip() or None,
                "orgaos": r[6].strip() or None, "forma_preenchimento": r[7].strip() or None,
                "mascara": r[12].strip() or None, "tamanho": r[13].strip() or None,
                "vigencia_inicio": _data(r[14]), "vigencia_fim": _data(r[15]),
            }
        if r[8].strip():
            dominio.append({
                "codigo_atributo": cod, "codigo_valor": r[8].strip(),
                "descricao_valor": r[9].strip() or None,
                "vigencia_inicio": _data(r[10]), "vigencia_fim": _data(r[11]),
            })
    return list(definicoes.values()), dominio


def parse_vinculos(linhas: list[list[str]]) -> list[dict]:
    """CSV de vínculos -> lista de vínculos NCM(prefixo hierárquico) -> atributo."""
    out = []
    for r in linhas[1:]:
        if len(r) < 9 or not r[0].strip() or not r[3].strip():
            continue
        out.append({
            "codigo_atributo": r[0].strip(),
            "ncm_prefixo": re.sub(r"\D", "", r[3]),
            "modalidade": r[4].strip() or None,
            "obrigatorio": _bool(r[5]),
            "multivalorado": _bool(r[6]),
            "vigencia_inicio": _data(r[7]),
            "vigencia_fim": _data(r[8]),
        })
    return out


def _ler_csv(conteudo: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(conteudo.decode("utf-8-sig")), delimiter=";"))


async def carregar() -> None:
    with httpx.Client(timeout=300, follow_redirects=True, headers=_UA) as client:
        pagina = client.get(PAGINA_NPI)
        pagina.raise_for_status()
        url_det, url_vin, ref = resolver_csvs_prod(pagina.text)
        print(f"Snapshot de PRODUÇÃO: {ref} \n  {url_det}\n  {url_vin}")

        conn = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            ja_tem = await conn.fetchval(
                "SELECT 1 FROM atributos_vinculos WHERE data_referencia = $1 LIMIT 1", ref)
            if ja_tem:
                print(f"Referência {ref} já carregada — nada a fazer (idempotente).")
                return

            det = _ler_csv(client.get(url_det).content)
            vin = _ler_csv(client.get(url_vin).content)
            definicoes, dominio = parse_detalhes(det)
            vinculos = parse_vinculos(vin)
            print(f"parse: {len(definicoes)} definições, {len(dominio)} valores de domínio, "
                  f"{len(vinculos)} vínculos")

            async with conn.transaction():
                await conn.executemany(
                    "INSERT INTO atributos_definicoes (codigo, nome, nome_apresentacao, objetivos, "
                    "orgaos, forma_preenchimento, atributo_condicionante, atributo_condicionado, "
                    "mascara, tamanho, vigencia_inicio, vigencia_fim, data_referencia) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
                    [(d["codigo"], d["nome"], d["nome_apresentacao"], d["objetivos"], d["orgaos"],
                      d["forma_preenchimento"], d["atributo_condicionante"], d["atributo_condicionado"],
                      d["mascara"], d["tamanho"], d["vigencia_inicio"], d["vigencia_fim"], ref)
                     for d in definicoes])
                await conn.executemany(
                    "INSERT INTO atributos_dominio (codigo_atributo, codigo_valor, descricao_valor, "
                    "vigencia_inicio, vigencia_fim, data_referencia) VALUES ($1,$2,$3,$4,$5,$6) "
                    "ON CONFLICT DO NOTHING",
                    [(v["codigo_atributo"], v["codigo_valor"], v["descricao_valor"],
                      v["vigencia_inicio"], v["vigencia_fim"], ref) for v in dominio])
                await conn.executemany(
                    "INSERT INTO atributos_vinculos (codigo_atributo, ncm_prefixo, modalidade, "
                    "obrigatorio, multivalorado, vigencia_inicio, vigencia_fim, data_referencia) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                    [(v["codigo_atributo"], v["ncm_prefixo"], v["modalidade"], v["obrigatorio"],
                      v["multivalorado"], v["vigencia_inicio"], v["vigencia_fim"], ref)
                     for v in vinculos])

                # Provenance citável em `normas` (versionada por vigência: fecha a anterior).
                await conn.execute(
                    "UPDATE normas SET data_vigencia_fim = $1 WHERE tipo_documento = 'atributos_npi' "
                    "AND data_vigencia_fim IS NULL", ref)
                await conn.execute(
                    "INSERT INTO normas (orgao, tipo_documento, identificador, texto, fonte_url, "
                    "data_vigencia_inicio) VALUES ('SISCOMEX', 'atributos_npi', $1, $2, $3, $4)",
                    f"Atributos NPI (produção) — referência {ref}",
                    f"Tabela oficial de atributos do Novo Processo de Importação (DUIMP): "
                    f"{len(definicoes)} atributos, {len(vinculos)} vínculos NCM-atributo. "
                    f"Fonte: CSVs de produção publicados em gov.br/siscomex (referência {ref}). "
                    f"A base de treinamento não é usada (atributos em avaliação pelos órgãos).",
                    PAGINA_NPI, ref)
            print(f"Carga concluída (referência {ref}).")
        finally:
            await conn.close()


if __name__ == "__main__":
    asyncio.run(carregar())

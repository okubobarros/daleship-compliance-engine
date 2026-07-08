"""Busca híbrida SÍNCRONA para o app (Streamlit é sync).

Reusa o embedder Voyage e o MESMO limiar calibrado (`DISTANCIA_MAXIMA`) do rag_search do
mcp-server — uma só fonte de verdade para o grounding. Nunca cita sem chunk de origem:
retorna None quando nada passa do limiar.
"""
import asyncio
import pathlib
import sys

import psycopg2
import psycopg2.extras

import rerank_ncm
from config import DATABASE_URL

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
from embeddings import get_embedder  # noqa: E402
from grounding import DISTANCIA_MAXIMA  # noqa: E402  (mesmo limiar do rag_search, sem puxar o pacote db)


def _emb_query(query: str):
    emb = get_embedder()
    if not getattr(emb, "disponivel", False):
        return None
    # embedder.embed é async; roda numa loop própria (sem pool asyncpg envolvido = seguro).
    return asyncio.run(emb.embed([query], input_type="query"))[0]


def _conectar_ann():
    """Conexão para busca vetorial (HNSW). Liga o iterative scan do pgvector 0.8 para o índice
    ANN devolver k resultados mesmo APÓS os filtros (tipo_documento/regex) — sem isso o Index Scan
    pode retornar menos/zero linhas (os vizinhos mais próximos podem ser de outro tipo_documento e
    caírem no filtro). strict_order + ef_search=100 dão PARIDADE com a busca exata (mesmos top-k),
    só mais rápido. Ver migration 0006_normas_embedding_hnsw.sql."""
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SET hnsw.iterative_scan = 'strict_order'")
        cur.execute("SET hnsw.ef_search = 100")
    return conn


def buscar_norma(query: str, tipo_documento: str | None = None) -> dict | None:
    """Melhor norma para a query (lexical + semântica com limiar). None = sem base localizada."""
    vetor = _emb_query(query)
    with _conectar_ann() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if vetor is not None:
            lit = "[" + ",".join(str(x) for x in vetor) + "]"
            cur.execute(
                "SELECT id, identificador, texto, fonte_url, tipo_documento, orgao, "
                "       embedding <=> %s::vector AS distancia "
                "FROM normas WHERE data_vigencia_fim IS NULL AND embedding IS NOT NULL "
                "  AND (%s::text IS NULL OR tipo_documento = %s) "
                "  AND embedding <=> %s::vector < %s "
                "ORDER BY embedding <=> %s::vector LIMIT 1",
                (lit, tipo_documento, tipo_documento, lit, DISTANCIA_MAXIMA, lit),
            )
            row = cur.fetchone()
            if row:
                return dict(row)
        # fallback lexical (útil p/ código/número exato; ex.: NCM)
        cur.execute(
            "SELECT id, identificador, texto, fonte_url, tipo_documento, orgao, NULL AS distancia "
            "FROM normas WHERE data_vigencia_fim IS NULL "
            "  AND (%s::text IS NULL OR tipo_documento = %s) "
            "  AND (texto ILIKE '%%'||%s||'%%' OR identificador ILIKE '%%'||%s||'%%') LIMIT 1",
            (tipo_documento, tipo_documento, query, query),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def melhores_precedentes(descricoes: list[str], tipo_documento: str = "solucao_consulta") -> list[dict | None]:
    """Melhor precedente por descrição de item. Embeda TODAS as descrições numa única chamada
    Voyage (poupa rate limit) e roda a busca semântica com o limiar calibrado por item.
    Retorna lista alinhada a `descricoes` (None onde nada passa do limiar)."""
    emb = get_embedder()
    if not descricoes or not getattr(emb, "disponivel", False):
        return [None] * len(descricoes)
    vetores = asyncio.run(emb.embed(descricoes, input_type="query"))
    resultados: list[dict | None] = []
    with _conectar_ann() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for v in vetores:
            lit = "[" + ",".join(str(x) for x in v) + "]"
            cur.execute(
                "SELECT id, identificador, texto, fonte_url, tipo_documento, orgao, "
                "       embedding <=> %s::vector AS distancia "
                "FROM normas WHERE data_vigencia_fim IS NULL AND embedding IS NOT NULL "
                "  AND tipo_documento = %s AND embedding <=> %s::vector < %s "
                "ORDER BY embedding <=> %s::vector LIMIT 1",
                (lit, tipo_documento, lit, DISTANCIA_MAXIMA, lit),
            )
            row = cur.fetchone()
            resultados.append(dict(row) if row else None)
    return resultados


def _carregar_rgi(cur) -> str:
    """Texto das Regras Gerais de Interpretação (6 linhas) para alimentar o rerank."""
    cur.execute("SELECT identificador, texto FROM normas WHERE tipo_documento = 'RGI' "
                "AND data_vigencia_fim IS NULL ORDER BY identificador")
    return "\n\n".join(f"{r['identificador']}: {r['texto']}" for r in cur.fetchall())


def _candidatos_ncm(cur, vetor, k: int) -> list[dict]:
    lit = "[" + ",".join(str(x) for x in vetor) + "]"
    cur.execute(
        "SELECT id, identificador, texto, fonte_url, embedding <=> %s::vector AS distancia "
        "FROM normas WHERE tipo_documento = 'NCM' AND data_vigencia_fim IS NULL "
        "  AND embedding IS NOT NULL "
        "  AND identificador ~ 'NCM [0-9]{4}\\.[0-9]{2}\\.[0-9]{2}$' "
        "ORDER BY embedding <=> %s::vector LIMIT %s",
        (lit, lit, k),
    )
    return [dict(r) for r in cur.fetchall()]


def sugerir_ncm(descricoes: list[str], k: int = 25) -> list[dict]:
    """Sugere o NCM por item: retrieval top-k (índice HNSW) + rerank LLM+RGI (rerank_ncm),
    substituindo a similaridade pura — que tem recall ok mas ranking fraco (produto acabado perde
    para matéria-prima). Retorna, por item, um dict:
      {ncm, texto, id, confianca ('alta'|'baixa'), provedor, rgi, justificativa, candidatos, sim_top1}
    ou {ncm: None, candidatos: []} quando o retrieval não traz nada. NUNCA afirma (é 'VERIFIQUE');
    confianca='baixa' quando o rerank cai no fallback de similaridade pura."""
    emb = get_embedder()
    if not descricoes or not getattr(emb, "disponivel", False):
        return [{"ncm": None, "confianca": "baixa", "candidatos": []} for _ in descricoes]
    vetores = asyncio.run(emb.embed(descricoes, input_type="query"))

    # 1) Retrieval (rápido, via índice) — pega candidatos de todos os itens e fecha a conexão
    #    ANTES de chamar o LLM (não segura conexão de banco durante o rerank).
    with _conectar_ann() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        rgi = _carregar_rgi(cur)
        cands_por_item = [_candidatos_ncm(cur, v, k) for v in vetores]

    # 2) Rerank por item (LLM + RGI, com fallback multi-provedor)
    saida: list[dict] = []
    for desc, cands in zip(descricoes, cands_por_item):
        if not cands:
            saida.append({"ncm": None, "confianca": "baixa", "candidatos": []})
            continue
        cand_llm = [{"ncm": c["identificador"].replace("NCM ", ""), "texto": (c["texto"] or "")[:150]}
                    for c in cands]
        esc = rerank_ncm.escolher(desc, cand_llm, rgi)
        escolhido = next((c for c in cands if c["identificador"].replace("NCM ", "") == esc["ncm"]), cands[0])
        saida.append({
            "ncm": esc["ncm"] or cands[0]["identificador"].replace("NCM ", ""),
            "texto": escolhido["texto"], "id": escolhido["id"],
            "confianca": esc["confianca"], "provedor": esc["provedor"],
            "posicao_fila": esc.get("posicao_fila"),
            "rgi": esc["rgi"], "justificativa": esc["justificativa"],
            "candidatos": cands, "sim_top1": round((1 - cands[0]["distancia"]) * 100, 1),
        })
    return saida


def anuencia_por_ncm(codigo: str) -> dict | None:
    """Anuência via busca LEXICAL do código NCM no compilado de Tratamento Administrativo.

    Muito mais confiável que semântica para isto: as linhas do TA enumeram os NCMs sob
    controle, então o código bate exato — ou nada (abstém). Evita o erro de órgão que a
    busca semântica cometia (ex.: medicamento -> MAPA). Tenta 8 dígitos e depois 6 (posição
    + subposição); não usa 4 dígitos para não colidir com números de lei/data.
    """
    digitos = "".join(ch for ch in codigo if ch.isdigit())
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for pref in (digitos, digitos[:6]):
            if len(pref) < 6:
                continue
            cur.execute(
                "SELECT id, identificador, texto, fonte_url, tipo_documento, orgao "
                "FROM normas WHERE tipo_documento = 'tratamento_administrativo' "
                "  AND data_vigencia_fim IS NULL "
                "  AND replace(replace(texto,'.',''),' ','') ILIKE '%%'||%s||'%%' LIMIT 1",
                (pref,),
            )
            row = cur.fetchone()
            if row:
                return dict(row)
    return None


def icms_por_uf(uf: str) -> dict | None:
    """ICMS/AFRMM/taxa MM por UF (snapshot de referência mais recente)."""
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT uf, estado, icms, afrmm, taxa_utilizacao_mm FROM icms_uf WHERE uf = %s "
            "AND data_referencia = (SELECT max(data_referencia) FROM icms_uf) LIMIT 1", (uf.upper(),))
        row = cur.fetchone()
        return dict(row) if row else None


def ufs_disponiveis() -> list[dict]:
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT uf, estado FROM icms_uf WHERE data_referencia = "
            "(SELECT max(data_referencia) FROM icms_uf) ORDER BY estado")
        return [dict(r) for r in cur.fetchall()]


def tributos_por_ncm(codigo: str) -> dict | None:
    """Alíquotas de importação por NCM (camada Tributos, snapshot de referência mais recente).
    Retorna II/IPI/PIS/COFINS + flags (CIDE, antidumping) + provenance para citação. None = NCM
    não encontrado na referência (abstém — não inventa alíquota)."""
    ncm = codigo.strip()
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT ii, ipi, pis, cofins, cide, antidumping, medidas_compensatorias, data_referencia "
            "FROM tributos_ncm WHERE ncm = %s "
            "AND data_referencia = (SELECT max(data_referencia) FROM tributos_ncm) LIMIT 1",
            (ncm,))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("SELECT id FROM normas WHERE tipo_documento='tributos_ref' AND data_vigencia_fim IS NULL LIMIT 1")
        prov = cur.fetchone()
    d = dict(row)
    d["norma_provenance_id"] = prov["id"] if prov else None
    return d


def _prefixos_ncm(codigo: str) -> list[str]:
    """Prefixos hierárquicos de um NCM para casar vínculos de atributo (capítulo 2 díg →
    item 8 díg; a fonte também tem níveis 5/6/7)."""
    digitos = "".join(ch for ch in codigo if ch.isdigit())
    return [digitos[:n] for n in (2, 4, 5, 6, 7, 8) if len(digitos) >= n]


def atributos_por_ncm(codigo: str, modalidade: str = "Importação") -> dict:
    """Atributos DUIMP exigidos/vinculados a um NCM (dor 'atributos' da call Bonano).

    Casa TODOS os prefixos hierárquicos do código no snapshot de produção mais recente,
    só vínculos vigentes. Retorna TODAS as leituras válidas (múltiplos órgãos/níveis —
    nunca colapsa num único definitivo; o analista decide) + a norma de provenance
    (linha 'atributos_npi' em `normas`) para citação grounded."""
    prefixos = _prefixos_ncm(codigo)
    if not prefixos:
        return {"vinculos": [], "norma_provenance_id": None}
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT v.codigo_atributo, v.ncm_prefixo, v.obrigatorio, v.multivalorado, "
            "       d.nome, d.nome_apresentacao, d.orgaos, d.forma_preenchimento "
            "FROM atributos_vinculos v "
            "LEFT JOIN atributos_definicoes d "
            "  ON d.codigo = v.codigo_atributo AND d.data_referencia = v.data_referencia "
            "WHERE v.ncm_prefixo = ANY(%s) AND v.modalidade = %s "
            "  AND v.data_referencia = (SELECT max(data_referencia) FROM atributos_vinculos) "
            "  AND (v.vigencia_fim IS NULL OR v.vigencia_fim >= CURRENT_DATE) "
            "ORDER BY v.obrigatorio DESC, length(v.ncm_prefixo) DESC, v.codigo_atributo",
            (prefixos, modalidade),
        )
        vinculos = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT id FROM normas WHERE tipo_documento = 'atributos_npi' "
            "AND data_vigencia_fim IS NULL LIMIT 1")
        row = cur.fetchone()
    return {"vinculos": vinculos, "norma_provenance_id": row["id"] if row else None}


def tratamento_por_orgao(orgao: str) -> dict | None:
    """Uma norma de Tratamento Administrativo do órgão (para citar como referência no flag
    regulatório). O anuente está no identificador ('... — ANATEL: ...')."""
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, identificador, texto, fonte_url, tipo_documento, orgao "
            "FROM normas WHERE tipo_documento = 'tratamento_administrativo' "
            "  AND data_vigencia_fim IS NULL AND identificador ILIKE '%%'||%s||'%%' LIMIT 1",
            (orgao,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def descricao_ncm(codigo: str) -> str | None:
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT texto FROM normas WHERE tipo_documento = 'NCM' AND identificador = %s "
            "AND data_vigencia_fim IS NULL LIMIT 1",
            (f"NCM {codigo}",),
        )
        row = cur.fetchone()
        return row[0] if row else None

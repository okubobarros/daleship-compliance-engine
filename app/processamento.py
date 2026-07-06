"""Orquestração do processamento de um dossiê — espelha o grafo do comex_conciliacao.json.

  Nó 1 (Extração)      -> extracao.extrair_texto / detectar_tipo_transporte / extrair_ncms
  Nó 2+5 (RAG + just.) -> app.rag.buscar_norma  (citação SEMPRE com norma de origem)
  Nó 3 (Conciliação)   -> compara campos entre os 3 documentos
  INTERRUPT            -> status 'revisao_humana' (nada é final sem humano)
  Nó 6 (Registro/Log)  -> db.* (append-only em log_auditoria)

Guardrail: um apontamento normativo só cita norma quando `buscar_norma` retornou algo dentro
do limiar calibrado (0.51); caso contrário sinaliza "sem base normativa localizada".
"""
from __future__ import annotations

import json
import re

import db
import extracao
import llm_extracao
import rag
import regras_regulatorias


def _valor(campos: dict, chave: str) -> str | None:
    v = campos.get(chave)
    return str(v) if v not in (None, "") else None


def _num(v: str | None) -> float | None:
    """Número comparável a partir de '18 cartons', 'USD 12,800.00', '12.800,00', '240 kg'.
    Sem isso, variação de formato entre documentos vira divergência FALSA."""
    if v is None:
        return None
    m = re.search(r"\d[\d.,]*", str(v))
    if not m:
        return None
    t = m.group(0)
    if "," in t and "." in t:                     # separador decimal = o último
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:                                # só vírgula: decimal se '123,45', senão milhar
        t = t.replace(",", ".") if re.fullmatch(r"\d+,\d{1,2}", t) else t.replace(",", "")
    try:
        return round(float(t), 2)
    except ValueError:
        return None


def _orgao_anuente(identificador: str) -> str:
    """Extrai o órgão anuente do identificador do TA ('... — ANATEL: escopo' -> 'ANATEL')."""
    if "—" in identificador and ":" in identificador:
        return identificador.split("—", 1)[1].split(":", 1)[0].strip()
    return "órgão anuente"


# Distância de cosseno acima da qual não sugerimos NCM (evita palpite ruim). Provisório —
# calibrar com casos reais; NCM é taxonomia, distribuição diferente das normas em prosa.
NCM_DIST_MAX = 0.62


def _sugerir_classificacao(dossie_id: str, itens: list[dict]) -> None:
    """Para cada item, sugere o NCM mais provável (semântico sobre a base NCM hierárquica).
    Nunca afirma: mostra 'provável X, alternativas Y/Z — verifique'. Item já com NCM na origem
    é apenas conferido (coerência)."""
    descricoes = [i.get("descricao", "") for i in itens]
    sugestoes = rag.sugerir_ncm(descricoes, k=3)
    sem_sugestao = []
    for item, cands in zip(itens, sugestoes):
        rotulo = item.get("codigo") or (item.get("descricao", "")[:30])
        validos = [c for c in cands if c["distancia"] <= NCM_DIST_MAX]
        if not validos:
            sem_sugestao.append(rotulo)
            continue
        melhor = validos[0]
        ncm_prov = melhor["identificador"].replace("NCM ", "")
        alt = ", ".join(c["identificador"].replace("NCM ", "") for c in validos[1:3])
        desc_prov = melhor["texto"].split(" — ", 1)[-1][:70]
        # Alíquotas da NCM provável (camada Tributos) — carga tributária estimada, a verificar.
        trib = rag.tributos_por_ncm(ncm_prov)
        trib_txt = ""
        if trib:
            trib_txt = (f" Alíquotas (ref.): II {trib['ii']}% · IPI {trib['ipi']}% · "
                        f"PIS {trib['pis']}% · COFINS {trib['cofins']}%.")
        db.inserir_apontamento(
            dossie_id, "classificacao", "atencao", "RFB",
            f"Item {rotulo} ({item.get('descricao','')[:45]}): NCM provável {ncm_prov} "
            f"({desc_prov})" + (f"; alternativas {alt}" if alt else "") + " — VERIFIQUE."
            + trib_txt,
            melhor["id"])
    if sem_sugestao:
        db.inserir_apontamento(dossie_id, "classificacao", "info", "-",
            f"{len(sem_sugestao)} item(ns) sem sugestão de NCM com confiança — classificar manualmente: "
            f"{', '.join(sem_sugestao[:20])}.", None)


def _flags_regulatorios(dossie_id: str, itens: list[dict]) -> None:
    """Dor nº 4 (Bonano): flag regulatório por palavra-chave, AGREGADO por regra (não um por
    item — invoice tem milhares). Cita o Tratamento Administrativo do órgão como referência."""
    por_regra: dict[str, dict] = {}
    for item in itens:
        rotulo = item.get("codigo") or (item.get("descricao", "")[:30])
        for regra in regras_regulatorias.avaliar(item.get("descricao", "")):
            acc = por_regra.setdefault(regra["nome"], {"regra": regra, "itens": []})
            if rotulo and rotulo not in acc["itens"]:
                acc["itens"].append(rotulo)
    for nome, acc in por_regra.items():
        regra = acc["regra"]
        norma = rag.tratamento_por_orgao(regra["orgao"])
        itens_txt = ", ".join(acc["itens"][:20])
        db.inserir_apontamento(
            dossie_id, "regulatorio", regra.get("severidade", "atencao"), regra["orgao"],
            f"{regra['exigencia']}. Itens: {itens_txt}.",
            norma["id"] if norma else None)


def _extrair_documento(papel: str, arq: dict) -> dict:
    """Nó 1 unificado: LLM (Gemini) quando disponível, senão heurística (regex).
    Retorna {texto, tipo_transporte, campos, itens, fonte}. Mesma forma nos dois modos."""
    texto = extracao.extrair_texto(arq["nome"], arq["mime"], arq["bytes"])
    dados = llm_extracao.extrair(papel, texto) if llm_extracao.disponivel() else None
    if dados:
        tipo = dados["tipo_transporte"] if papel == "documento_transporte" else None
        if papel == "documento_transporte" and not tipo:
            tipo = extracao.detectar_tipo_transporte(texto)  # rede de segurança
        return {"texto": texto, "tipo_transporte": tipo, "campos": dados["campos"],
                "itens": dados["itens"], "fonte": "llm"}
    # Fallback heurístico
    itens = [{"descricao": extracao.contexto_ncm(texto, n), "ncm": n}
             for n in extracao.extrair_ncms(texto)]
    tipo = extracao.detectar_tipo_transporte(texto) if papel == "documento_transporte" else None
    return {"texto": texto, "tipo_transporte": tipo, "campos": extracao.extrair_campos(texto),
            "itens": itens, "fonte": "heuristica"}


def _conciliar(docs: list[dict]) -> list[dict]:
    """Compara campos-chave entre os documentos. Retorna divergências (Nó 3).

    Campos numéricos (peso/volumes/valor) são comparados por VALOR normalizado — variação
    de formato ('18' vs '18 cartons', '12800' vs '12,800.00') não gera divergência falsa.
    """
    campos_por_papel = {d["papel"]: (d.get("dados_extraidos") or {}).get("campos", {}) for d in docs}
    numericos = {"peso_bruto": "Peso bruto", "volumes": "Volumes", "valor_total": "Valor total"}
    textuais = {"numero": "Número do documento"}
    divergencias = []

    for chave, rotulo in numericos.items():
        valores = {p: _valor(c, chave) for p, c in campos_por_papel.items() if _valor(c, chave)}
        nums = {p: _num(v) for p, v in valores.items() if _num(v) is not None}
        if len(set(nums.values())) > 1:
            detalhe = "; ".join(f"{p}={valores[p]}" for p in nums)
            divergencias.append({"tipo": "divergencia", "severidade": "critico", "orgao": "RFB",
                                 "descricao": f"{rotulo} divergente entre documentos: {detalhe}."})

    for chave, rotulo in textuais.items():
        valores = {p: _valor(c, chave).upper().replace(" ", "") for p, c in campos_por_papel.items()
                   if _valor(c, chave)}
        if len(set(valores.values())) > 1:
            detalhe = "; ".join(f"{p}={_valor(campos_por_papel[p], chave)}" for p in valores)
            divergencias.append({"tipo": "divergencia", "severidade": "atencao", "orgao": "RFB",
                                 "descricao": f"{rotulo} divergente entre documentos: {detalhe}."})
    return divergencias


def processar_dossie(cliente_id: str, referencia: str, arquivos: dict) -> str:
    """arquivos: {papel: {'nome','mime','bytes'}} para invoice, packing_list, documento_transporte."""
    dossie_id = db.criar_dossie(cliente_id, referencia)

    # --- Nó 1: extração (LLM/heurística) + detecção de tipo de transporte ---
    docs_meta = []
    ncms: list[str] = []
    contexto: dict[str, str] = {}   # ncm -> descrição da mercadoria (preferir a da invoice)
    fontes = set()
    for papel, arq in arquivos.items():
        ext = _extrair_documento(papel, arq)
        fontes.add(ext["fonte"])
        for item in ext["itens"]:
            n = item.get("ncm")
            if not n:
                continue
            if n not in ncms:
                ncms.append(n)
            desc = (item.get("descricao") or "").strip()
            if desc and (papel == "invoice" or n not in contexto):
                contexto[n] = desc
        dados = {"campos": ext["campos"], "itens": ext["itens"], "fonte_extracao": ext["fonte"]}
        db.inserir_documento(dossie_id, papel, ext["tipo_transporte"], arq["nome"], arq["mime"],
                             ext["texto"], dados)
        docs_meta.append({"papel": papel, "dados_extraidos": dados})

    _log(dossie_id, "extracao_concluida",
         {"ncms": ncms, "documentos": list(arquivos.keys()), "fonte_extracao": sorted(fontes)})

    # --- Nó 3: conciliação documental ---
    for div in _conciliar(docs_meta):
        db.inserir_apontamento(dossie_id, div["tipo"], div["severidade"], div["orgao"],
                               div["descricao"], None)

    # --- Nó 2+5: para cada NCM, exigência de anuência e precedente de classificação, com citação ---
    for ncm in ncms:
        desc = rag.descricao_ncm(ncm) or ncm
        # a mercadoria descrita no documento é melhor consulta que a descrição terse do NCM
        alvo = (contexto.get(ncm) or desc).strip()

        # Anuência: LEXICAL pelo código (a linha do TA que enumera o NCM) — cita exato ou abstém,
        # sem arriscar apontar o órgão errado (a semântica derivava, ex.: medicamento -> MAPA).
        anuencia = rag.anuencia_por_ncm(ncm)
        if anuencia:
            # o órgão anuente real está no identificador ("... — ANATEL: ..."); a coluna
            # `orgao` da tabela é a fonte (SISCOMEX), não o anuente.
            anuente = _orgao_anuente(anuencia["identificador"])
            db.inserir_apontamento(
                dossie_id, "anuencia", "atencao", anuente,
                f"NCM {ncm} ({desc[:60]}): consta no controle administrativo de {anuente} "
                f"— verificar exigência de anuência/LPCO.", anuencia["id"])
        else:
            db.inserir_apontamento(
                dossie_id, "anuencia", "info", "-",
                f"NCM {ncm}: não localizado no compilado de anuentes — verificar anuência manualmente.",
                None)

        precedente = rag.buscar_norma(
            f"classificação fiscal de {alvo}", tipo_documento="solucao_consulta")
        if precedente:
            db.inserir_apontamento(
                dossie_id, "classificacao", "info", "RFB",
                f"NCM {ncm}: precedente de classificação da RFB relacionado.", precedente["id"])

        # Atributos DUIMP vinculados ao NCM (dor 'atributos' — call Bonano). Todas as leituras
        # válidas (múltiplos órgãos/níveis hierárquicos) são apresentadas; nunca colapsa em um
        # definitivo. Citação grounded na linha de provenance do snapshot oficial.
        attrs = rag.atributos_por_ncm(ncm)
        vinculos = attrs["vinculos"]
        if vinculos:
            obrig = [v for v in vinculos if v["obrigatorio"]]
            orgaos = sorted({p.strip() for v in vinculos
                             for p in (v["orgaos"] or "").split(",") if p.strip()})
            nomes = ", ".join((v["nome_apresentacao"] or v["nome"])[:38] for v in obrig[:4])
            db.inserir_apontamento(
                dossie_id, "atributos", "atencao" if obrig else "info",
                ", ".join(orgaos[:3]) or "-",
                f"NCM {ncm}: {len(vinculos)} atributo(s) DUIMP vinculados, {len(obrig)} obrigatório(s)"
                + (f" (ex.: {nomes})" if nomes else "")
                + " — verifique o preenchimento no catálogo/DUIMP.",
                attrs["norma_provenance_id"])

    if not ncms:
        db.inserir_apontamento(
            dossie_id, "classificacao", "atencao", "-",
            "Nenhum NCM detectado nos documentos — revisar extração antes de submeter.", None)

    # --- Flags regulatórios por palavra-chave (wi-fi → ANATEL etc.) ---
    itens_todos = [it for d in docs_meta for it in (d["dados_extraidos"].get("itens") or [])]
    _flags_regulatorios(dossie_id, itens_todos)

    # --- INTERRUPT: revisão humana obrigatória ---
    db.atualizar_status(dossie_id, "revisao_humana")
    _log(dossie_id, "processamento_concluido", {"status": "revisao_humana"})
    return dossie_id


def _extrair_aba(papel: str, texto: str) -> dict:
    """Extração de uma aba (Invoice ou Packing List) — LLM se disponível, senão heurística."""
    dados = llm_extracao.extrair(papel, texto) if llm_extracao.disponivel() else None
    if dados:
        return {"campos": dados["campos"], "itens": dados["itens"], "fonte": "llm"}
    itens = [{"codigo": None, "descricao": extracao.contexto_ncm(texto, n), "ncm": n, "quantidade": None}
             for n in extracao.extrair_ncms(texto)]
    return {"campos": extracao.extrair_campos(texto), "itens": itens, "fonte": "heuristica"}


def _chave_item(item: dict) -> str:
    return (item.get("codigo") or item.get("descricao") or "")[:40].upper().strip()


def conciliar_itens(itens_inv: list[dict], itens_pk: list[dict]) -> list[dict]:
    """Concilia Invoice × Packing List item a item (por código/descrição): presença e
    quantidade. Retorna divergências. Função pura — testável em escala (o 'santo graal'
    do Bonano é exatamente isto em invoices de milhares de itens; dicts O(1) por item)."""
    divergencias = []
    pk_por_chave = {_chave_item(i): i for i in itens_pk}
    for item in itens_inv:
        par = pk_por_chave.get(_chave_item(item))
        rotulo = item.get("codigo") or (item.get("descricao") or "")[:30]
        if not par:
            divergencias.append({"severidade": "atencao",
                                 "descricao": f"Item {rotulo} presente na Invoice mas não localizado no Packing List."})
            continue
        qi, qp = _num(item.get("quantidade")), _num(par.get("quantidade"))
        if qi is not None and qp is not None and qi != qp:
            divergencias.append({"severidade": "critico",
                                 "descricao": f"Quantidade divergente no item {rotulo}: "
                                              f"Invoice={item.get('quantidade')} vs Packing List={par.get('quantidade')}."})
    return divergencias


def processar_ivpl(cliente_id: str, referencia: str, arq: dict) -> str:
    """Processa um arquivo COMBINADO Invoice + Packing List (abas separadas) — o formato
    real dos documentos da trading. Sem documento de transporte, sem NCM na origem: o valor
    é (1) extração estruturada, (2) conciliação Invoice×Packing List item a item, (3)
    precedentes de classificação como REFERÊNCIA para o analista (nunca afirma o NCM)."""
    dossie_id = db.criar_dossie(cliente_id, referencia)
    abas = extracao.abas_texto(arq["nome"], arq["mime"], arq["bytes"])

    def _achar(*chaves):
        for nome, txt in abas.items():
            if any(k in nome.upper() for k in chaves):
                return txt
        return None

    txt_inv = _achar("INVOICE", "FATURA") or next(iter(abas.values()), "")
    txt_pk = _achar("PACKING", "ROMANEIO")

    ext_inv = _extrair_aba("invoice", txt_inv)
    db.inserir_documento(dossie_id, "invoice", None, arq["nome"], arq["mime"], txt_inv,
                         {"campos": ext_inv["campos"], "itens": ext_inv["itens"], "fonte_extracao": ext_inv["fonte"]})
    ext_pk = None
    if txt_pk:
        ext_pk = _extrair_aba("packing_list", txt_pk)
        db.inserir_documento(dossie_id, "packing_list", None, arq["nome"], arq["mime"], txt_pk,
                             {"campos": ext_pk["campos"], "itens": ext_pk["itens"], "fonte_extracao": ext_pk["fonte"]})
    _log(dossie_id, "extracao_concluida",
         {"itens_invoice": len(ext_inv["itens"]), "itens_packing": len(ext_pk["itens"]) if ext_pk else 0})

    # --- Falha de extração é sinalizada, NUNCA silenciada nem transformada em divergência falsa ---
    llm_on = llm_extracao.disponivel()
    inv_falhou = llm_on and not ext_inv["itens"]      # LLM disponível mas 0 itens = extração falhou
    if inv_falhou:
        db.inserir_apontamento(dossie_id, "extracao", "atencao", "-",
            "Não foi possível extrair os itens da Invoice automaticamente (possível limite de "
            "requisições do extrator) — reprocessar o dossiê.", None)
    # Extração PARCIAL (invoice gigante em blocos: alguns blocos falharam) — itens podem faltar.
    for rotulo_doc, ext in (("Invoice", ext_inv), ("Packing List", ext_pk or {})):
        falhos = ext.get("blocos_falhos") or 0
        if falhos:
            db.inserir_apontamento(dossie_id, "extracao", "critico", "-",
                f"Extração PARCIAL do {rotulo_doc}: {falhos} de {ext.get('blocos_total')} bloco(s) "
                f"falharam — itens podem estar faltando. Reprocessar antes de confiar na conciliação.",
                None)

    # --- Conciliação Invoice × Packing List: só quando AMBAS as abas foram extraídas ---
    if ext_pk and ext_inv["itens"] and ext_pk["itens"]:
        for div in conciliar_itens(ext_inv["itens"], ext_pk["itens"]):
            db.inserir_apontamento(dossie_id, "divergencia", div["severidade"], "RFB",
                                   div["descricao"], None)
    elif ext_pk and not (ext_inv["itens"] and ext_pk["itens"]):
        db.inserir_apontamento(dossie_id, "extracao", "info", "-",
            "Conciliação Invoice × Packing List não realizada: uma das abas não pôde ser extraída "
            "automaticamente. Reprocessar para tentar novamente.", None)

    # --- Sugestão de classificação (risco de NCM): descrição -> NCM provável, VERIFIQUE ---
    itens = ext_inv["itens"]
    _sugerir_classificacao(dossie_id, itens)

    # --- Flags regulatórios por palavra-chave (wi-fi → ANATEL etc.) ---
    _flags_regulatorios(dossie_id, itens)

    db.atualizar_status(dossie_id, "revisao_humana")
    _log(dossie_id, "processamento_concluido", {"status": "revisao_humana", "modo": "ivpl_combinado"})
    return dossie_id


def _log(dossie_id: str, evento: str, detalhe: dict) -> None:
    with db.conectar() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO log_auditoria (dossie_id, evento, detalhe) VALUES (%s, %s, %s)",
                    (dossie_id, evento, json.dumps(detalhe)))
        conn.commit()

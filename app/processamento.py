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

    if not ncms:
        db.inserir_apontamento(
            dossie_id, "classificacao", "atencao", "-",
            "Nenhum NCM detectado nos documentos — revisar extração antes de submeter.", None)

    # --- INTERRUPT: revisão humana obrigatória ---
    db.atualizar_status(dossie_id, "revisao_humana")
    _log(dossie_id, "processamento_concluido", {"status": "revisao_humana"})
    return dossie_id


def _log(dossie_id: str, evento: str, detalhe: dict) -> None:
    with db.conectar() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO log_auditoria (dossie_id, evento, detalhe) VALUES (%s, %s, %s)",
                    (dossie_id, evento, json.dumps(detalhe)))
        conn.commit()

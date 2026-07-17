"""Feed normativo — fontes REAIS, nunca conteúdo fabricado.

Fontes (todas públicas, sem chave):
- DOU Seção 1 (`in.gov.br/leiturajornal` — JSON embutido na página oficial da Imprensa
  Nacional), filtrado para matérias de comércio exterior/aduaneiro por órgão e palavra-chave.
- Notícias MDIC (RSS gov.br) — Ministério do Desenvolvimento, Indústria, Comércio e Serviços.
- Notícias Receita Federal (RSS gov.br).

Princípio do projeto (CLAUDE.md §4): se a fonte falhar, o item simplesmente não aparece —
nunca preenchemos com texto inventado. Cache em memória com TTL (o DOU do dia tem centenas de
matérias e ~0,5MB; não faz sentido rebaixar a Imprensa Nacional a cada pageview).
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta
from xml.etree import ElementTree

import httpx

_UA = {"User-Agent": "Mozilla/5.0 (compatible; DespachanteDeBolso/1.0; +https://despachantedebolso.com.br)"}
_TTL_SEGUNDOS = 30 * 60
_cache: dict = {"quando": 0.0, "itens": [], "fontes": {}}
_lock = threading.Lock()

# Órgãos cuja hierarquia no DOU marca a matéria como relevante para comex, mesmo sem keyword.
_ORGAOS_COMEX = (
    "comercio exterior",          # Secretaria/Câmara de Comércio Exterior (SECEX/GECEX/CAMEX)
    "receita federal",
    "secretaria especial de comercio",
)

# Palavras-chave no título/tipo que marcam matéria de comex fora desses órgãos.
_PALAVRAS_COMEX = (
    "importac", "exportac", "aduaneir", "drawback", "antidumping", "ex-tarifari",
    "tarifa externa", "ncm", "duimp", "du-e", "lpco", "siscomex", "recof",
    "imposto de importacao", "regime aduaneiro", "despacho aduaneiro", "camex", "gecex",
)


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFD", texto or "").encode("ascii", "ignore").decode("ascii").lower()


def _e_comex(titulo: str, orgao: str, conteudo: str) -> bool:
    orgao_n = _sem_acento(orgao)
    if any(o in orgao_n for o in _ORGAOS_COMEX):
        return True
    texto_n = _sem_acento(f"{titulo} {conteudo[:400]}")
    return any(p in texto_n for p in _PALAVRAS_COMEX)


def _resumo(texto: str, limite: int = 260) -> str:
    limpo = re.sub(r"<[^>]+>", " ", texto or "")
    limpo = re.sub(r"\s+", " ", limpo).strip()
    return limpo[:limite] + ("…" if len(limpo) > limite else "")


def _dou_itens(cliente: httpx.Client) -> list[dict]:
    """DOU Seção 1 do dia (recuando até 3 dias — fim de semana/feriado não tem edição)."""
    for recuo in range(0, 4):
        dia = date.today() - timedelta(days=recuo)
        url = f"https://www.in.gov.br/leiturajornal?data={dia.strftime('%d-%m-%Y')}&secao=do1"
        resp = cliente.get(url)
        if resp.status_code != 200:
            continue
        m = re.search(r'<script[^>]*id="params"[^>]*>(.*?)</script>', resp.text, re.S)
        if not m:
            continue
        try:
            materias = json.loads(m.group(1)).get("jsonArray") or []
        except ValueError:
            continue
        if not materias:
            continue
        itens = []
        for mat in materias:
            titulo = (mat.get("title") or "").strip()
            orgao = (mat.get("hierarchyStr") or "").strip()
            conteudo = mat.get("content") or ""
            if not titulo or not _e_comex(titulo, orgao, conteudo):
                continue
            itens.append({
                "fonte": "DOU Seção 1",
                "orgao": orgao or "Diário Oficial da União",
                "tipo": (mat.get("artType") or "Ato").strip(),
                "titulo": titulo,
                "resumo": _resumo(conteudo),
                "url": f"https://www.in.gov.br/web/dou/-/{mat.get('urlTitle')}",
                "data": dia.isoformat(),
            })
        return itens
    return []


def _rss_itens(cliente: httpx.Client, url: str, fonte: str, orgao: str) -> list[dict]:
    """RSS 1.0 (RDF) do gov.br — title/link/description/dc:date por item."""
    resp = cliente.get(url)
    resp.raise_for_status()
    raiz = ElementTree.fromstring(resp.content)
    itens = []
    for el in raiz.iter():
        if not el.tag.endswith("}item") and el.tag != "item":
            continue
        campos = {}
        for filho in el:
            chave = filho.tag.rsplit("}", 1)[-1]
            campos[chave] = (filho.text or "").strip()
        if not campos.get("title") or not campos.get("link"):
            continue
        data_iso = ""
        bruto = campos.get("date") or campos.get("pubDate") or ""
        m = re.search(r"\d{4}-\d{2}-\d{2}", bruto)
        if m:
            data_iso = m.group(0)
        itens.append({
            "fonte": fonte,
            "orgao": orgao,
            "tipo": "Notícia",
            "titulo": campos["title"],
            "resumo": _resumo(campos.get("description", "")),
            "url": campos["link"],
            "data": data_iso,
        })
    return itens


_FONTES_RSS = [
    ("https://www.gov.br/mdic/pt-br/assuntos/noticias/RSS", "MDIC",
     "Ministério do Desenvolvimento, Indústria, Comércio e Serviços"),
    ("https://www.gov.br/receitafederal/pt-br/assuntos/noticias/RSS", "Receita Federal",
     "Secretaria Especial da Receita Federal do Brasil"),
]


def obter(forcar: bool = False) -> dict:
    """Retorna {itens, fontes, gerado_em} do cache (TTL 30min) ou refaz a coleta.

    `fontes` relata o status real de cada coleta (ok/erro + contagem) — a UI mostra
    honestamente quando uma fonte está fora, em vez de esconder a falha."""
    with _lock:
        agora = time.time()
        if not forcar and _cache["itens"] and agora - _cache["quando"] < _TTL_SEGUNDOS:
            return {"itens": _cache["itens"], "fontes": _cache["fontes"],
                    "gerado_em": _cache["gerado_em"]}

        itens: list[dict] = []
        status_fontes: dict[str, dict] = {}
        with httpx.Client(headers=_UA, timeout=30, follow_redirects=True) as cliente:
            try:
                dou = _dou_itens(cliente)
                itens += dou
                status_fontes["DOU Seção 1"] = {"ok": True, "itens": len(dou)}
            except Exception as e:  # fonte fora não derruba o feed inteiro
                status_fontes["DOU Seção 1"] = {"ok": False, "erro": str(e)[:200]}
            for url, fonte, orgao in _FONTES_RSS:
                try:
                    parciais = _rss_itens(cliente, url, fonte, orgao)
                    itens += parciais
                    status_fontes[fonte] = {"ok": True, "itens": len(parciais)}
                except Exception as e:
                    status_fontes[fonte] = {"ok": False, "erro": str(e)[:200]}

        itens.sort(key=lambda i: i.get("data") or "", reverse=True)
        gerado_em = datetime.now().astimezone().isoformat(timespec="seconds")
        if itens or not _cache["itens"]:
            _cache.update({"quando": agora, "itens": itens, "fontes": status_fontes,
                           "gerado_em": gerado_em})
        return {"itens": _cache["itens"], "fontes": status_fontes, "gerado_em": gerado_em}

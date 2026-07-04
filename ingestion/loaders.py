"""Loaders plugáveis por tipo de fonte.

Cada loader recebe uma FonteConfig e devolve uma lista de UnidadeNormativa já
chunkada (uma unidade citável por item). Adicionar suporte a um novo tipo de fonte
= registrar um novo loader, sem tocar no pipeline.

Princípio de grounding: NUNCA ingerir conteúdo não verificado. O loader 'file' lê
texto normativo já coletado e conferido (JSON estruturado sob seeds/). O loader
'http' é stub proposital para fontes cuja coleta+parse ainda não foi implementada.
O loader 'ncm_json' consome o JSON oficial da nomenclatura NCM do Portal Único.
"""
from __future__ import annotations

import io
import json
import pathlib
import re
from typing import Callable

import httpx

from models import FonteConfig, UnidadeNormativa

SEEDS_DIR = pathlib.Path(__file__).resolve().parent / "seeds"

# Endpoint oficial do JSON da nomenclatura NCM (Portal Único Siscomex).
NCM_JSON_URL = "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json"

# User-Agent de navegador — gov.br às vezes recusa clientes sem UA.
_UA = {"User-Agent": "Mozilla/5.0 (compatible; daleship-compliance-engine/1.0)"}

_LOADERS: dict[str, Callable[[FonteConfig], list[UnidadeNormativa]]] = {}


def register(nome: str):
    def deco(fn: Callable[[FonteConfig], list[UnidadeNormativa]]):
        _LOADERS[nome] = fn
        return fn

    return deco


def get_loader(nome: str) -> Callable[[FonteConfig], list[UnidadeNormativa]]:
    if nome not in _LOADERS:
        raise KeyError(f"Loader '{nome}' não registrado. Disponíveis: {sorted(_LOADERS)}")
    return _LOADERS[nome]


@register("file")
def file_loader(fonte: FonteConfig) -> list[UnidadeNormativa]:
    """Lê unidades normativas verificadas de um JSON sob seeds/.

    Formato esperado: lista de objetos {"identificador": str, "texto": str}.
    """
    if not fonte.caminho:
        raise ValueError(f"Fonte {fonte.orgao}/{fonte.tipo_documento}: loader 'file' exige 'caminho'.")
    caminho = SEEDS_DIR / fonte.caminho
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return [UnidadeNormativa(identificador=u["identificador"], texto=u["texto"]) for u in dados]


@register("http")
def http_loader(fonte: FonteConfig) -> list[UnidadeNormativa]:
    """Stub: coleta+chunk de fonte HTTP oficial ainda não implementada para esta fonte.

    Exige etapa de verificação humana do conteúdo parseado antes de virar norma
    citável — não ingerir automaticamente sem isso."""
    raise NotImplementedError(
        f"Loader 'http' ainda não implementado para {fonte.fonte_url}. "
        "Colete e verifique o conteúdo, salve como JSON em seeds/ e use o loader 'file'."
    )


# --- NCM (Portal Único) ---

def parse_ncm_payload(payload: dict) -> list[UnidadeNormativa]:
    """Transforma o payload JSON da nomenclatura NCM em unidades citáveis.

    Uma unidade por código de nomenclatura. `identificador` = 'NCM <codigo>'.
    Estrutura esperada (a CONFERIR contra o payload real na primeira coleta com o
    portal fora da parada programada): {"Nomenclaturas": [{"Codigo","Descricao",...}]}.
    """
    itens = payload.get("Nomenclaturas") or payload.get("nomenclaturas") or []
    unidades: list[UnidadeNormativa] = []
    for item in itens:
        codigo = (item.get("Codigo") or item.get("codigo") or "").strip()
        descricao = (item.get("Descricao") or item.get("descricao") or "").strip()
        # A fonte traz tags HTML (ex.: <i>champagne</i>) — remover para citação limpa.
        descricao = re.sub(r"<[^>]+>", "", descricao)
        if not codigo:
            continue
        unidades.append(
            UnidadeNormativa(identificador=f"NCM {codigo}", texto=f"{codigo} — {descricao}")
        )
    return unidades


def _portal_em_parada(resp: httpx.Response) -> bool:
    """Detecta a parada programada diária do Portal Único (01:00–03:00): a chamada
    acaba em parada-programada.json. Não indexar o conteúdo de status.

    (Segue redirects normais, ex.: 307 que só acrescenta ?perfil=PUBLICO — a parada é
    identificada pela URL FINAL, não por qualquer redirect.)"""
    return "parada-programada" in str(resp.url)


@register("ncm_json")
def ncm_json_loader(fonte: FonteConfig) -> list[UnidadeNormativa]:
    """Baixa o JSON oficial da nomenclatura NCM e chunka por código.

    Health-check embutido: se o Portal Único estiver na parada programada, aborta
    com mensagem clara em vez de ingerir o payload de status."""
    with httpx.Client(timeout=180, follow_redirects=True, headers=_UA) as client:
        resp = client.get(NCM_JSON_URL)
        if _portal_em_parada(resp):
            raise RuntimeError(
                "Portal Único em parada programada (01:00–03:00). "
                "Rodar a coleta da NCM fora dessa janela."
            )
        resp.raise_for_status()
        payload = resp.json()
    return parse_ncm_payload(payload)


# --- RGI via NESH (Notas Explicativas do Sistema Harmonizado, Receita Federal) ---

def resolver_pdf_nesh(html: str, base_url: str) -> str:
    """Acha, no HTML da página oficial, o link de download do PDF vigente da NESH.

    Não assume o nome do arquivo (a versão pode mudar). Prefere o link cujo texto de
    âncora referencia a IN vigente (2.169/2023); descarta explicitamente a 'versão anterior'.
    """
    ancoras = re.findall(r'<a[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.I | re.S)
    candidatos = []
    for href, texto in ancoras:
        texto_limpo = re.sub(r"<[^>]+>", " ", texto)
        if "anterior" in texto_limpo.lower():
            continue
        candidatos.append((href, texto_limpo))
    if not candidatos:
        raise RuntimeError("Nenhum link de PDF da NESH encontrado na página oficial.")

    # Preferência: âncora que cita a IN vigente (2.169 / 2169).
    for href, texto in candidatos:
        if "2.169" in texto or "2169" in texto:
            return httpx.URL(base_url).join(href).__str__()
    # Fallback: primeiro candidato que não é a versão anterior.
    href = candidatos[0][0]
    return httpx.URL(base_url).join(href).__str__()


def parse_rgi_texto(texto: str) -> list[UnidadeNormativa]:
    """Extrai as 6 Regras Gerais de Interpretação do texto da seção RGI da NESH.

    Cada unidade = o enunciado normativo da REGRA N (de 'REGRA N' até 'NOTA EXPLICATIVA').
    Se qualquer uma das 6 faltar, aborta — nunca indexa RGI parcial (grounding)."""
    unidades: list[UnidadeNormativa] = []
    for n in range(1, 7):
        m = re.search(rf"(?m)^REGRA {n}\s*$", texto)
        if not m:
            raise RuntimeError(f"RGI Regra {n} não localizada no texto extraído da NESH.")
        ini = m.end()
        mnota = re.search(r"NOTA EXPLICATIVA", texto[ini:])
        fim = ini + mnota.start() if mnota else len(texto)
        corpo = re.sub(r"\s+", " ", texto[ini:fim]).strip()
        if not corpo:
            raise RuntimeError(f"RGI Regra {n} veio vazia na extração.")
        unidades.append(UnidadeNormativa(identificador=f"RGI Regra {n}", texto=corpo))
    return unidades


def _extrair_secao_rgi(pdf_bytes: bytes) -> str:
    """Concatena as páginas da seção RGI, detectadas dinamicamente (não por número fixo):
    começa na página com 'REGRA 1' + 'valor indicativo'; termina ao chegar na Seção I."""
    import pdfplumber

    paginas: list[str] = []
    capturando = False
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for idx, page in enumerate(pdf.pages):
            if idx > 60 and not capturando:
                raise RuntimeError("Início da seção RGI não encontrado nas primeiras páginas da NESH.")
            texto = page.extract_text() or ""
            up = texto.upper()
            if not capturando:
                if "REGRA 1" in up and "VALOR INDICATIVO" in up:
                    capturando = True
                    paginas.append(texto)
                continue
            if "ANIMAIS VIVOS E PRODUTOS DO REINO ANIMAL" in up and "REGRA" not in up:
                break  # fronteira: começou a Seção I
            paginas.append(texto)
            if len(paginas) > 20:
                raise RuntimeError("Fim da seção RGI não detectado — estrutura da NESH pode ter mudado.")
    return "\n".join(paginas)


@register("rgi_nesh")
def rgi_nesh_loader(fonte: FonteConfig) -> list[UnidadeNormativa]:
    """Coleta as RGI a partir da NESH oficial (Receita Federal).

    fonte_url deve ser a PÁGINA da NESH (não o PDF direto) — o loader resolve o link do
    PDF vigente ali, baixa, isola a seção RGI e chunka nas 6 regras."""
    with httpx.Client(timeout=180, follow_redirects=True, headers=_UA) as client:
        pagina = client.get(fonte.fonte_url)
        pagina.raise_for_status()
        pdf_url = resolver_pdf_nesh(pagina.text, str(pagina.url))
        pdf_resp = client.get(pdf_url)
        pdf_resp.raise_for_status()
        pdf_bytes = pdf_resp.content
    secao = _extrair_secao_rgi(pdf_bytes)
    return parse_rgi_texto(secao)

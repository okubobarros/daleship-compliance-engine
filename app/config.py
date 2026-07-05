"""Configuração do app MVP (Fase 1 — Comex-demo)."""
import os
import pathlib

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]

# Paleta (variáveis leves de CSS — sem identidade visual completa ainda).
PALETA = {
    "primaria": "#2563EB",
    "roxo": "#6D28D9",
    "laranja": "#F97316",
    "escuro": "#111827",
    "cinza": "#6B7280",
    "claro": "#F3F4F6",
}

# Tipos de documento de transporte — GENÉRICO e extensível (schema não hardcoda B/L).
# Detectado automaticamente pelo Nó 1; confirmado/corrigido pelo humano em 1 clique.
TIPOS_TRANSPORTE = {
    "B/L": "Conhecimento de Embarque Marítimo (B/L)",
    "AWB": "Conhecimento Aéreo (AWB)",
    "CRT": "Conhecimento Rodoviário Mercosul (CRT)",  # espaço reservado — sem nova migration
}

PAPEIS = {
    "invoice": "Invoice (Fatura Comercial)",
    "packing_list": "Packing List",
    "documento_transporte": "Documento de Transporte",
}


def nome_tipo_transporte(codigo: str | None) -> str:
    if not codigo:
        return "Tipo de transporte não detectado"
    return TIPOS_TRANSPORTE.get(codigo, codigo)

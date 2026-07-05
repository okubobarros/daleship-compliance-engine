"""CSS leve: paleta + fonte Poppins como variáveis. Sem polimento visual além disso."""
import streamlit as st

from config import PALETA

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');
:root {{
  --primaria: {PALETA['primaria']};
  --roxo: {PALETA['roxo']};
  --laranja: {PALETA['laranja']};
  --escuro: {PALETA['escuro']};
  --cinza: {PALETA['cinza']};
  --claro: {PALETA['claro']};
}}
html, body, [class*="css"], .stMarkdown, .stButton>button, input, textarea, label {{
  font-family: 'Poppins', sans-serif !important;
}}
h1, h2, h3 {{ color: var(--escuro); font-weight: 600; }}
.stButton>button {{ border-radius: 8px; }}
/* Cartão de apontamento: citação SEMPRE ao lado, nunca escondida */
.apontamento {{
  border-left: 5px solid var(--cinza); background: var(--claro);
  border-radius: 8px; padding: 14px 16px; margin-bottom: 12px;
}}
.apontamento.critico {{ border-left-color: var(--laranja); }}
.apontamento.atencao {{ border-left-color: var(--primaria); }}
.apontamento.info {{ border-left-color: var(--roxo); }}
.citacao {{
  background: #fff; border: 1px solid #E5E7EB; border-radius: 8px;
  padding: 10px 12px; margin-top: 8px; font-size: 0.9em; color: var(--escuro);
}}
.citacao .fonte {{ color: var(--primaria); font-weight: 600; }}
.sem-fonte {{ color: var(--cinza); font-style: italic; }}
.tag {{
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-size: 0.75em; font-weight: 600; color: #fff; margin-right: 6px;
}}
.tag.critico {{ background: var(--laranja); }}
.tag.atencao {{ background: var(--primaria); }}
.tag.info {{ background: var(--roxo); }}
.confirma-tipo {{
  background: #EEF2FF; border: 1px solid #C7D2FE; border-radius: 8px;
  padding: 10px 14px; margin-bottom: 14px; color: var(--escuro);
}}
</style>
"""


def aplicar() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

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
/* Banner de risco (prévia do gauge do Cockpit — Frente 2 traz o medidor real) */
.risco-banner {{
  display: flex; align-items: center; gap: 16px;
  border: 1px solid #eceef1; border-radius: 12px; padding: 14px 18px; margin-bottom: 16px;
  background: #fff;
}}
.risco-num {{
  width: 58px; height: 58px; border-radius: 14px; flex: 0 0 58px;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: 700; color: #fff;
}}
.risco-txt .rot {{ font-size: 15px; font-weight: 600; }}
.risco-txt .sub {{ font-size: 12.5px; color: var(--cinza); margin-top: 2px; }}
/* Achado no formato de decisão: Evidência · Por que importa · Ação recomendada */
.decisao {{
  display: grid; grid-template-columns: 1fr 1.3fr 1.3fr; gap: 18px; margin-top: 10px;
}}
.decisao .rot {{
  font-size: 10.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #9aa1ab;
}}
.decisao .val {{ font-size: 13.5px; color: var(--escuro); margin-top: 4px; line-height: 1.45; }}
.decisao .evid {{
  font-family: ui-monospace, Menlo, monospace; background: var(--claro);
  border-radius: 8px; padding: 8px 10px;
}}
</style>
"""


def aplicar() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

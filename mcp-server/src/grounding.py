"""Constantes de grounding — fonte única de verdade, sem dependência de banco.

Importado tanto pelo rag_search (mcp-server) quanto pelo app (Streamlit), para que o
limiar calibrado não seja duplicado nem divergir entre os dois caminhos de busca.
"""

# Limiar de distância de cosseno (pgvector `<=>`) acima do qual um vizinho semântico é
# descartado como IRRELEVANTE — sem isso a busca vetorial sempre devolve os K mais próximos
# e uma query fora do domínio "citaria" a norma menos distante (fura o grounding).
# CALIBRADO com o golden eval set (eval/run_eval.py) na base real de comex (2026-07-05):
# positivos no-domínio até 0.494, negativos a partir de 0.518 — folga fina (+0.024). 0.51 =
# ponto médio: 100% no golden set vs 88% no antigo 0.65. Citação errada > miss ⇒ favorecer
# rejeitar. Reavaliar ao crescer o golden set / adicionar fontes.
DISTANCIA_MAXIMA = 0.51

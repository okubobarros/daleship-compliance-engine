# DESIGN_SYSTEM.md — Referência de UX/marca (a partir dos layouts entregues)

Fonte: 7 layouts de alta fidelidade entregues pelo time de design em 04/07/2026, versionados em
`design/mockups/`. Este documento captura as **decisões** que os layouts implicam — não substitui os
arquivos, que são a fonte visual de verdade.

> ⚠️ Os mockups são estáticos (exportados de uma ferramenta de design; usam um mini-runtime `x-dc` com
> dados fictícios). Não são o app. São a **especificação visual** do frontend.

## 1. Marca e tokens
- **Nome de produto nos layouts:** "Despachante de Bolso" (agente de IA chamado **"ComexPilot"**).
  ⚠️ Diferente do nome interno do repo (`daleship-compliance-engine`). Decisão de naming em aberto — ver §5.
- **Símbolo:** tucano (`lucide: bird`) em gradiente azul→roxo.
- **Fonte:** Poppins (400/500/600/700).
- **Paleta (confirma a que já usamos):**
  - Azul primário `#2563EB` · Roxo `#6D28D9` · Laranja/atenção `#F97316`
  - Tinta/texto `#111827` · Cinza `#6B7280` · Fundo claro `#F3F4F6`
  - Semânticos: crítico `#F97316`/`#E05252` · médio `#2563EB` · ok `#16A34A`
  - Homepage usa um tema **escuro** próprio (`#0A0F1E`) — só a landing.
- **Componentes recorrentes:** cards `border-radius:16–20px` + sombra suave; nav-rail lateral escura de 78px
  com ícones; "pill" de severidade; barra de progresso/gauge; donut de composição de custo.

## 2. Telas entregues e a que feature do nosso backend cada uma corresponde
| Layout | Tela | Mapeia para (backend já existente) |
|---|---|---|
| `homepage.html` (escuro) | Landing / marketing | — (aquisição; posiciona a **conferência** de Invoice × Draft BL) |
| `registro.html` | Cadastro self-serve | auth (hoje: login fixo trading/demo) — **não temos** cadastro real |
| `redefinir-senha.html` | Fluxo de reset de senha | idem — **não temos** |
| `estado-vazio.html` | Onboarding / primeira simulação | entrada da feature CTI |
| `estados-carregamento.html` | Biblioteca de loading/skeleton/"agente pensando" | estados de UI de qualquer feature |
| `resumo-importacao.html` | Dashboard-resumo de uma importação | `cti.py` (cards de custo, donut) + apontamentos |
| `cockpit-decisao.html` | Cockpit de decisão (gauge de risco + achados) | `processamento._flags/_sugerir` (apontamentos com severidade) |

## 3. Jornada principal definida
Os 7 layouts ainda mostram mais de uma possibilidade de produto, mas a decisão da Fase 1 foi fechada:
1. **Jornada principal: auditoria pré-embarque de documentos** (`homepage.html`): Invoice × Draft BL,
   mismatch de Incoterm, regra de frete (FOB×Prepaid), alerta de NCM, "segurar embarque". Esse é o
   núcleo da demo e deve orientar navegação, CTA e narrativa.
2. **Jornada secundária: simulador de custo de importação** (`estado-vazio` → `resumo` → `cockpit`):
   continua útil como módulo auxiliar, mas não deve competir com a jornada principal nesta fase.

O corte é intencional: a primeira entrega precisa parecer um produto único, não um portfólio de features.

## 4. Conceitos novos que os layouts introduzem (ainda não existem no backend)
- **"Confiança da simulação"** (ex.: 82%, "11 de 14 variáveis confirmadas") — precisaria de um score.
- **"Índice de risco / 100"** no cockpit (gauge) — idem, um score agregado dos apontamentos.
- **Margem projetada** — hoje o CTI calcula custo/unitário, não margem de venda (falta preço de venda).
- **Cadastro/trial/reset de senha** — hoje a auth é um login fixo de demo, não multi-usuário real.
Todos são construíveis, mas são **novo escopo**, não reskin do que já existe.

## 5. Decisões em aberto (para o dono do produto)
1. **Naming:** adotar "Despachante de Bolso"/"ComexPilot" como marca oficial? (afeta repo, telas, docs)
2. **Stack de frontend:** Streamlit **não** renderiza estes layouts com fidelidade (nav-rail, gauge, donut,
   landing, auth). Ou (a) frontend web real a partir destes HTMLs + FastAPI sobre a lógica atual, ou
   (b) aproximação parcial no Streamlit. Ver §6.
3. **CTI como módulo secundário:** manter no app atual para apoio interno ou remover da narrativa externa
   até a Fase 2.

## 6. Nota técnica: Streamlit × estes layouts
O app atual é Streamlit (escolha de velocidade para o MVP/demo). Estes layouts pressupõem controle total de
HTML/CSS/JS (barra lateral de ícones, medidor/gauge, donut, página de marketing, telas de autenticação com
força de senha). Streamlit não entrega isso fielmente — forçar via `st.markdown(unsafe_allow_html)` é frágil
e ainda assim não fica igual. O `docs/ARCHITECTURE.md` já aponta **FastAPI** como backend de destino; estes
HTMLs são, na prática, a especificação do frontend web real. O caminho de menor retrabalho é expor a lógica
Python atual (`rag`, `cti`, `processamento`, `llm_extracao`) via FastAPI e transformar estes mockups em
páginas reais ligadas a dados — os arquivos já são HTML+CSS, o que adianta muito o trabalho.

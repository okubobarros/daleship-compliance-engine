# App MVP — Conferência de Comex (Fase 1)

UI mínima (Streamlit) ligada ao RAG calibrado (20.996 unidades, limiar 0.51) e à lógica de
conciliação que espelha o `n8n/workflows/comex_conciliacao.json`. Sem polimento visual — só
a paleta e a fonte Poppins como CSS leve.

## Telas (MVP_PRODUCT_SPEC.md)

1. **Login simples** (usuário/senha do time da trading; sem registro público).
2. **Lista de processos**.
3. **Upload** — Invoice, Packing List e Documento de Transporte. Aceita PDF/imagem/Excel como
   estão; **não pergunta o modal** — o tipo (B/L/AWB/CRT) é detectado no Nó 1.
4. **Detalhe do dossiê** — apontamentos com **a norma citada ao lado** (nunca escondida), mais a
   confirmação rápida e não-bloqueante do tipo de transporte ("Detectamos: … (AWB)" — corrige em 1 clique).
5. **Revisão humana** — aceitar (1 clique) ou corrigir (texto) cada apontamento.
6. **Trilha de auditoria** — eventos append-only por processo.

## Rodar

```bash
mcp-server/.venv/Scripts/streamlit.exe run app/ui.py
```

Precisa de `DATABASE_URL` e `VOYAGE_API_KEY` no `.env` (já usados pelo resto do projeto).
Credenciais: `APP_USERS="usuario:senha,..."` no `.env`; sem isso, usuário de demo `trading` / `demo`.

## Backend (espelha os nós do grafo)

- `extracao.py` — Nó 1: texto de PDF/Excel, **detecção automática** do tipo de transporte, NCM (regex robusto),
  campos de conciliação (heurístico). O Nó 1 "pleno" com LLM é upgrade plugável (quando houver `ANTHROPIC_API_KEY`).
- `processamento.py` — orquestra: extração → conciliação (Nó 3) → para cada NCM, anuência + precedente de
  classificação com citação (Nós 2/5) → INTERRUPT (revisão humana) → log.
- `rag.py` — busca híbrida **síncrona** (reusa o embedder e o limiar `grounding.DISTANCIA_MAXIMA`). Anuência é
  **lexical pelo código NCM** no compilado de TA (cita o órgão anuente exato ou abstém — nunca aponta órgão errado).
- `db.py` — persistência (dossiê, documentos, apontamentos, correções) + log **append-only**.
- `regras_regulatorias.py` + `.yaml` — **flags regulatórios por palavra-chave** (call Bonano): "wi-fi → verificar ANATEL", "carregador → Inmetro", "termômetro → ANVISA". Config-driven (adicionar regra = novo bloco no YAML). Casa por fronteira de palavra + sem acento (evita 'raçao' dentro de 'coraçao'), agrega por regra, e cita o Tratamento Administrativo do órgão. Sempre "verificar", nunca afirma.

## Limitações conhecidas (honestas para a demo)

- Extração de campos é heurística (regex) — o Nó 1 com LLM melhora muito a qualidade. NCM (regex) é robusto.
- Anuência automática é conservadora: cita quando o código NCM está enumerado no compilado (posição/subposição
  de 6-8 dígitos) e abstém caso contrário. O mapeamento NCM→anuência completo virá da tabela por-NCM
  (`ta_lpco_att_imp.xlsx`, ainda não indexada).
- Imagem é aceita e guardada, mas sem OCR (extração de texto só de PDF/Excel).

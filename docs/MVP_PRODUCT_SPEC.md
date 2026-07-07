# Spec de Produto — Fase 1 (Comex-demo)

**Referência:** `ROADMAP.md` (Fase 1), `CLAUDE.md` §2, `ComexPilot.md`, `CUSTOMER_JOURNEY.md`
**Escopo:** esta spec descreve a entrega realista da Fase 1. A jornada principal é **auditoria pré-embarque de documentos**. CTI pode existir como apoio operacional, mas não é a proposta de valor central desta fase.

---

## 1. Objetivo do MVP

Entregar uma demonstração funcional para uma trading real, com foco em reduzir risco operacional antes do embarque.

O sistema precisa:
- Receber documentos de importação.
- Extrair conteúdo útil.
- Confrontar os documentos entre si.
- Produzir apontamentos com norma citada ao lado.
- Exigir revisão humana antes de encerrar o processo.
- Registrar trilha auditável append-only.

## 2. O que dá para construir agora

Com o que já existe no repositório, é realista entregar:

- Login simples do time da trading.
- Lista de dossiês/processos.
- Upload de Invoice, Packing List e documento de transporte.
- Detecção automática do tipo de transporte.
- Extração e conciliação entre documentos.
- Apontamentos com severidade e citação normativa.
- Tela de revisão humana com aceitar/corrigir.
- Trilha de auditoria do processo.

## 3. Fora de escopo da Fase 1

Para evitar diluir a demo, esta fase não inclui:

- Cadastro self-service.
- Reset de senha.
- Multi-tenancy robusto.
- Cobrança automatizada.
- Dashboard executivo.
- App mobile.
- Jornada self-serve de simulação de margem como produto principal.

CTI pode permanecer como módulo interno/extra, mas não deve disputar a home, a navegação ou a narrativa comercial da Fase 1.

## 4. Mapa de telas

```
/                    → login simples
/dossies             → lista de processos
/dossies/novo        → upload de documentos
/dossies/:id         → detalhe do dossiê
/dossies/:id/revisao → revisão humana
/dossies/:id/trilha  → trilha de auditoria
```

## 5. Jornada do usuário

1. O analista entra no sistema com login simples.
2. Vê a lista de processos existentes e cria um novo dossiê.
3. Faz upload dos documentos como vierem, sem exigir padronização prévia.
4. O sistema processa em etapas visíveis: extração, conciliação, checagem normativa e geração de apontamentos.
5. O detalhe do dossiê mostra os achados com a norma citada ao lado, sem esconder a fonte.
6. O analista revisa cada apontamento, aceitando ou corrigindo quando necessário.
7. O sistema registra a decisão e mantém a trilha auditável.

## 6. O que precisa aparecer na interface

### Núcleo
- Status claro de processamento por etapa.
- Lista de apontamentos ordenada por severidade.
- Citação normativa visível ao lado do achado.
- Revisão humana rápida, com 1 clique quando possível.
- Histórico append-only do que foi validado e corrigido.

### Valor percebido
- Mostrar que o sistema economiza tempo e reduz risco.
- Mostrar a fonte normativa sem exigir clique extra.
- Deixar explícito quando não há base suficiente para citar.

## 7. Métricas da Fase 1

- Tempo médio de processamento por dossiê.
- Taxa de apontamentos aceitos sem correção.
- Taxa de correção humana por tipo de erro.
- Taxa de grounding rejeitado por falta de base.
- Erros técnicos de extração ou integração.

## 8. Princípios de UX

- Uma jornada principal, sem competir com outra proposta de valor.
- Fonte normativa sempre visível.
- Revisão humana nunca tratada como detalhe.
- Progressão do fluxo com contexto, não com spinner genérico.

## 9. O que fica para depois

- CTI como fluxo self-service mais rico.
- Cadastro self-service.
- Reset de senha.
- Dashboard executivo.
- Automação de cobrança.
- App mobile.

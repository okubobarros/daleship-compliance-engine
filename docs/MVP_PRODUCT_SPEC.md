# Spec de Produto — Fase 1 (Compliance Engine Embedded para Comex)

**Referência:** `ROADMAP.md` (Fase 1), `CLAUDE.md` §2, `ComexPilot.md`, `CUSTOMER_JOURNEY.md`
**Escopo:** esta spec descreve a entrega realista da Fase 1. A proposta de valor central é um **compliance engine embedded para operações de comércio exterior**, com foco em pré-registro, conferência documental, reconciliação de dados e governança humana. CTI pode existir como apoio operacional, mas não é o núcleo desta fase.

---

## 1. Objetivo do MVP

Entregar uma demonstração funcional para uma trading real, com foco em reduzir risco operacional antes do registro e antes do embarque.

O sistema precisa:
- Receber documentos de importação e anexos operacionais.
- Extrair conteúdo útil e normalizá-lo em entidades comparáveis.
- Confrontar os documentos entre si e com parâmetros internos.
- Aplicar regras de compliance preventivas com justificativa e evidência.
- Exigir revisão humana antes de avançar quando houver exceção.
- Registrar trilha auditável append-only do que foi recebido, inferido, validado e aprovado.

## 2. O que dá para construir agora

Com o que já existe no repositório, é realista entregar:

- Login simples do time da trading.
- Lista de dossiês/processos.
- Upload de Invoice, Packing List, BL/AWB e anexos operacionais.
- Detecção automática do tipo de transporte.
- Extração e normalização de campos críticos.
- Reconciliação entre documentos e cadastro interno.
- Checks preventivos com severidade, justificativa e evidência.
- Tela de revisão humana com aceitar/corrigir/escalar.
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
4. O sistema processa em etapas visíveis: ingestão, extração, normalização, reconciliação, checagem de compliance e geração de pendências.
5. O detalhe do dossiê mostra os achados, a justificativa da regra e a evidência usada, sem esconder a fonte.
6. O analista revisa cada pendência, aceitando, corrigindo ou escalando quando necessário.
7. O sistema registra a decisão, o responsável e o histórico de mudança.

## 6. O que precisa aparecer na interface

### Núcleo
- Status claro de processamento por etapa.
- Lista de pendências e exceções ordenada por criticidade.
- Evidência e justificativa visíveis ao lado do achado.
- Revisão humana rápida, com 1 clique quando possível.
- Histórico append-only do que foi validado, inferido, corrigido e aprovado.

### Valor percebido
- Mostrar que o sistema economiza tempo e reduz risco.
- Mostrar a fonte da decisão sem exigir clique extra.
- Deixar explícito quando não há base suficiente para avançar.

## 7. Métricas da Fase 1

- Tempo médio de processamento por dossiê.
- Taxa de pendências resolvidas sem retrabalho.
- Taxa de correção humana por tipo de exceção.
- Taxa de saída bloqueada por falta de base documental.
- Erros técnicos de extração ou integração.

## 8. Princípios de UX

- Uma jornada principal, sem competir com outra proposta de valor.
- Evidência e justificativa sempre visíveis.
- Revisão humana nunca tratada como detalhe.
- Progressão do fluxo com contexto, não com spinner genérico.
- A interface deve mostrar estado, cobertura e responsabilidade, não só “resultado”.
- A navegação pública não deve usar mock como fallback nem repetir o mesmo ciclo sem uma nova submissão ou reexecução explícita.
- A reconciliação pública só fica liberada quando Invoice e Packing List foram anexados; referência isolada não é suficiente para seguir.
- A tela de resultado precisa se comportar como relatório final: cobertura, criticidade, critérios avaliados, achados e próxima ação. Sem CTA de reexecução na mesma rodada.
- O quarto documento é opcional e existe para elevar a precisão, não para bloquear a jornada quando ausente.

## 8.1. Evolução UX aplicada no produto público

Este bloco registra a leitura prática do que já foi aplicado no app e o que ainda precisa evoluir.

| # | Evolução | Situação |
|---|---|---|
| 1 | Trava por Invoice + Packing List | Aplicada |
| 2 | Documento opcional de reforço (ERP / extra) | Parcial |
| 3 | Loading sem mock passivo | Aplicada |
| 4 | Loading com progresso e mensagens | Parcial |
| 5 | Resultado terminal sem loop de reexecução | Aplicada |
| 6 | Leitura executiva no topo do relatório | Aplicada |
| 7 | Critérios avaliados com evidência e severidade | Aplicada |
| 8 | Próxima ação clara para o usuário | Aplicada |
| 9 | Proveniência real do backend quando houver `dossie_id` | Parcial |
| 10 | Escala para dossiers grandes com agrupamento e priorização | Em evolução |

## 9. O que fica para depois

- CTI como fluxo self-service mais rico.
- Cadastro self-service.
- Reset de senha.
- Dashboard executivo.
- Automação de cobrança.
- App mobile.
- Monitoramento regulatório contínuo com atualização automatizada de fontes.

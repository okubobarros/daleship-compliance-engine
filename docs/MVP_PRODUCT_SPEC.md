# O Que Dá Para Construir Agora — Spec de Produto (Fase 1, Comex-demo)

**Referência:** ROADMAP.md (Fase 1), CUSTOMER_JOURNEY.md, PROJECT_STRUCTURE.md
**Escopo:** isto descreve o que é realista entregar no ciclo de 4 semanas da Fase 1 — não o produto completo de MAPA/Bioinsumos, que vem depois.

---

## 1. O que dá para construir agora, com honestidade

Construindo do zero (não há motor nem workflow n8n pré-existentes a reaproveitar — ver correção em `CLAUDE.md` §2), guiados pelo levantamento de requisitos em `docs/ComexPilot.md`, é realista entregar no ciclo de 4 semanas:

- Upload de documentos de um processo de importação (Invoice, Packing List, B/L).
- Conciliação automática entre esses documentos.
- Verificação de exigência de anuência (LPCO) para 1-2 órgãos.
- Lista de apontamentos, cada um citando a norma exata.
- Tela de revisão humana (aceitar/corrigir).
- Um painel administrativo simples de consumo e qualidade (não um dashboard de BI completo).

**O que não é realista ainda**: multi-tenancy robusto, cobrança automatizada, mobile, notificação por e-mail/WhatsApp, dashboard executivo bonito. Isso é Fase 2+.

## 2. Mapa de URLs (telas do MVP)

```
/                          → login / seleção de organização
/dossies                   → lista de processos (dashboard do analista)
/dossies/novo              → upload de novo processo (Invoice, Packing List, B/L)
/dossies/:id                → detalhe do processo, com status e apontamentos
/dossies/:id/revisao        → tela de revisão humana (aceitar/corrigir apontamento)
/dossies/:id/trilha         → histórico de auditoria daquele processo (quem corrigiu o quê, quando)
/admin                      → painel administrativo (só visível para o time Daleship)
/admin/consumo              → custo de token e chamadas por cliente/dossiê
/admin/qualidade             → taxa de acerto, taxa de correção humana, alertas de grounding
/admin/usuarios              → gestão de acesso (quem da trading tem login)
```

## 3. Jornada do usuário, tela a tela

1. **`/dossies/novo`** — analista sobe os três documentos. Fricção mínima: aceitar PDF, imagem ou Excel como estão, sem exigir formato específico.
2. **Processamento** — enquanto o sistema roda (extração → RAG → verificação → justificativa), a tela mostra progresso claro por etapa, não uma barra de carregamento genérica. Isso já começa a construir confiança antes mesmo do resultado aparecer.
3. **`/dossies/:id`** — resultado: lista de apontamentos, cada um com o trecho da norma citado ao lado, nunca escondido atrás de um clique extra.
4. **`/dossies/:id/revisao`** — analista aceita ou corrige cada apontamento, 1 clique quando possível, campo de texto só quando a correção é substantiva.
5. **`/dossies/:id/trilha`** — qualquer pessoa (inclusive um fiscal, hipoteticamente) pode ver quem validou o quê e quando — essa tela existe desde o dia 1, mesmo que pouco visitada no início, porque é ela que sustenta o argumento de "trilha auditável" na venda.

## 4. Job to be Done por perfil (dentro da trading)

| Perfil | Job funcional | Job emocional |
|---|---|---|
| **Analista de comex (usuário operacional)** | "Preciso saber, antes de submeter, se os documentos batem entre si e se falta anuência" | Não quero ser responsável por um processo parado na alfândega por erro evitável |
| **Gestor/coordenador de comex (comprador econômico)** | "Preciso saber quanto tempo e risco a ferramenta está realmente evitando" | Quero justificar internamente por que vale pagar por isso |
| **Time Daleship (operador do sistema)** | "Preciso saber se o sistema está gastando token demais ou citando errado antes que o cliente perceba" | Não quero descobrir um erro de citação pela reclamação do cliente |

## 5. Features — o que é núcleo vs. o que é "uau"

**Núcleo (sem isso não há produto):**
- Upload e extração de documento.
- Conciliação entre documentos.
- Citação de norma em cada apontamento.
- Revisão humana com correção estruturada.

**"Uau" (o que faz o analista lembrar da demo depois):**
- **Ver a citação aparecer em tempo real, com o trecho normativo destacado ao lado do apontamento** — não é "confie em mim", é "aqui está o artigo exato, veja com seus próprios olhos". Esse é o momento de maior impacto emocional de toda a jornada — é onde o ceticismo profissional vira confiança.
- **Contador visível de "tempo estimado economizado"** aparecendo assim que o processamento termina — não é uma métrica abstrata depois, é gratificação imediata no momento em que o valor foi gerado.
- **Diff visual entre o que o analista teria encontrado sozinho vs. o que o sistema encontrou** — se possível, mostrar isso já na primeira demonstração usando um processo que a trading já processou manualmente antes, comparando o resultado.

## 6. Painel Admin — consumo, acurácia e performance

Esse painel é para o time de vocês, não para o cliente (pelo menos não nesta fase):

### Consumo (controle de custo)
- Tokens consumidos por dossiê processado (referência: `INFRA_COST_GUARDRAILS.md`).
- Custo estimado em R$ por dossiê, comparado ao ticket cobrado — visibilidade de margem em tempo real, não só no fechamento do mês.
- Alerta quando um cliente específico ultrapassa um teto de consumo esperado (sinal de uso anômalo ou de dossiê muito mais complexo que a média).

### Acurácia (a métrica mais importante do negócio)
- **Taxa de rejeição de grounding**: quantas vezes o sistema tentou gerar uma citação sem fonte válida e foi bloqueado internamente (deveria tender a zero; um número alto é sinal de base normativa incompleta, não bug pontual).
- **Taxa de correção humana por apontamento**: quantos apontamentos o analista aceitou sem alteração vs. corrigiu — é o proxy mais direto de acurácia real, e deve cair ao longo do tempo à medida que o sistema aprende com as correções.
- **Distribuição de correções por tipo de erro** — ajuda a decidir onde investir esforço de engenharia a seguir (é mais um problema de extração, de recuperação de norma, ou de verificação?).

### Performance
- Tempo médio de processamento por dossiê, do upload ao resultado.
- Taxa de erro técnico (falha de extração, timeout de API externa como PUCOMEX).
- Uptime simples do serviço.

## 7. Visão diferente por ICP — o que cada perfil deveria ver

| | Analista de comex | Gestor da trading | Time Daleship (admin) |
|---|---|---|---|
| Vê apontamentos e citação | Sim, completo | Resumo agregado | Sim, para debug |
| Vê custo de token/processamento | Não | Não (só o ticket cobrado) | Sim, detalhado |
| Vê trilha de auditoria | Sim, do próprio processo | Sim, agregada | Sim, de todos os clientes |
| Vê taxa de acurácia/correção | Não diretamente | Como "tempo economizado" (linguagem de negócio, não de engenharia) | Sim, como métrica técnica |
| Pode corrigir apontamento | Sim | Não (só visualiza) | Não deveria — corrigir é do cliente, não do time interno |

O princípio por trás dessa tabela: **cada perfil vê a mesma verdade, traduzida na linguagem que importa para ele** — o analista vê a norma, o gestor vê tempo/risco evitado, o time interno vê token e taxa de erro. Nunca misturem esses vocabulários na mesma tela, ou a interface passa a competir por atenção com informação que não é relevante para quem está olhando.

## 8. O que fica para depois desta spec

- Notificações automáticas (e-mail/WhatsApp) de novo apontamento.
- Multi-tenancy completo com onboarding self-service.
- Dashboard executivo com gráfico histórico de ROI acumulado.
- Cobrança automatizada/faturamento dentro do produto.
- App mobile.

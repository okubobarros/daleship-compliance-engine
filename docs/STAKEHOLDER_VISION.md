# Visão Multi-Stakeholder — Tech Founder, UX, Negócio, CIO

> **Nota de escopo (ver CLAUDE.md, seção 5):** este documento descreve a Fase 2 do projeto (MAPA/Anvisa/Ibama — defensivos e bioinsumos). A Fase 1 atual é Comex — consulte `docs/ROADMAP.md` e `docs/MVP_PRODUCT_SPEC.md` para o escopo em execução agora.

**Referência:** ARCHITECTURE.md, PRD.md, CUSTOMER_JOURNEY.md

---

## 1. Visão do Tech Founder — arquitetura e desafios reais

**A aposta técnica central**: explicabilidade com grounding obrigatório (nunca citar sem fonte indexada) não é feature, é a proposta de valor inteira. Se essa parte falhar, não existe produto — por isso o Nó 5 do LangGraph (justificativa) precisa ser o mais testado de todos, com suíte de regressão dedicada a "nunca alucinar citação".

**Maiores desafios, em ordem de risco:**

1. **Instabilidade de fonte de dado, não de modelo.** O SISPA está em rollout (lançado maio/2026), estruturas mudam. O risco maior do projeto não é o LLM errar — é a base normativa ficar desatualizada sem vocês perceberem. Mitigação: pipeline de diff versionado (já em ARCHITECTURE.md) e revisão manual periódica enquanto não há API oficial.
2. **Esforço de ingestão subestimado.** Capturar e estruturar Agrofit + IN SDA + monografias Anvisa + normas Ibama é trabalho de engenharia de dados mais do que de IA — reservem tempo real para isso, não tratem como tarefa trivial de scraping de um dia.
3. **Confiança é binária, não gradual.** Um erro de citação em produção pode custar meses de confiança construída. Tratem qualquer bug de grounding como incidente de produção crítico, com processo de resposta definido antes de precisar dele.
4. **Time pequeno, escopo grande.** Recursos concentrados em poucas pessoas — resistam à tentação de paralelizar demais (RAG + agentes + integração PUCOMEX + UI ao mesmo tempo). Sigam a ordem do ROADMAP.md.

## 2. Visão do UX Sênior — princípios de design

**Princípio 1 — confiança visível, não alegada.** Toda resposta do sistema mostra a fonte junto, nunca escondida atrás de um "saiba mais". O usuário regulatório é cético por formação profissional — a interface precisa recompensar esse ceticismo, não tentar contorná-lo.

**Princípio 2 — correção é o produto, não um afterthought.** A tela de revisão humana (Etapa 3 da jornada) é provavelmente a tela mais usada do sistema no dia a dia — merece o mesmo cuidado de design que a tela de resultado, não menos.

**Princípio 3 — nunca decidir silenciosamente.** Se o sistema não encontrar base normativa para algo, ele diz isso explicitamente ("sem base normativa localizada"), nunca omite ou preenche com inferência não citada. Isso é decisão de UX tanto quanto de engenharia.

**Princípio 4 — progressive disclosure para o dossiê completo.** Um dossiê tem muitos campos; a tela inicial deve mostrar só os apontamentos (o que precisa de atenção), não o dossiê inteiro de uma vez — reduz carga cognitiva do analista.

**Leitura prática do cockpit público:** a experiência precisa evoluir de "subir documento" para "ver base mínima, entender cobertura e tomar decisão". O que ficou documentado como regra de produto:
1. Invoice e Packing List liberam a jornada.
2. O quarto documento é opcional e aumenta precisão. Ex.: ERP / cadastro mestre.
3. Loading precisa parecer processamento, não espera passiva.
4. Resultado precisa encerrar a rodada atual.
5. Achado sem evidência não existe na interface.
6. Critérios avaliados precisam estar visíveis por eixo.
7. A próxima ação precisa ser clara.
8. O backend só aparece como número quando há lastro real.
9. Dossiês grandes precisam ser resumidos sem perder rastreabilidade.
10. Qualquer nova análise começa por nova submissão, não por loop automático.

## 3. Visão de Negócio — onde o produto gera valor real

| Fonte de valor | Como o produto entrega | Como isso vira receita |
|---|---|---|
| Tempo economizado do analista | Triagem automática de lacunas antes da submissão | Justifica ticket por dossiê |
| Redução de exigência de complementação | Citação de norma reduz erro humano de interpretação | Justifica upsell de assinatura de monitoramento |
| Previsibilidade de prazo de aprovação | Histórico de precedente + checklist normativo completo | Argumento central de venda para fabricante |
| Escala sem contratar | Consultoria atende mais clientes com o mesmo time | Justifica modelo B2B2B com desconto por volume |

**Priorização de feature (o que construir primeiro)**: qualquer feature entra no roadmap só se responder "isso aumenta a confiança na citação" ou "isso reduz o tempo de revisão humana" — feature que não toca nenhum dos dois eixos espera.

## 4. Visão do CIO — dados, armazenamento, ativo proprietário

**O ativo mais valioso da empresa não é o modelo, é a base de correções humanas acumuladas.** Toda decisão de arquitetura de dado deve proteger e maximizar a qualidade dessa captura, não só a performance de consulta.

**Onde armazenar, por tipo de dado, priorizando menor custo no início:**

| Dado | Onde no MVP (custo mínimo) | Onde evolui depois |
|---|---|---|
| Base normativa indexada (embeddings) | pgvector no Postgres gerenciado free-tier (ex: Supabase) | Mesmo — não migrar sem necessidade real de escala |
| Dossiês e correções humanas (estruturado) | Mesmo Postgres | Mesmo, com backup automatizado mais robusto |
| Documentos brutos enviados pelo cliente (PDF etc.) | Bucket de object storage free-tier (ex: Supabase Storage ou Cloudflare R2, que tem tier gratuito generoso) | S3 dedicado com política de retenção formalizada |
| Log de auditoria | Tabela append-only no mesmo Postgres | Pode migrar para armazenamento imutável dedicado (WORM) quando exigido por cliente enterprise |

**Como o dado proprietário é gerado e usado**: cada correção humana (tabela `correcoes`) vira, no médio prazo, dado de fine-tuning ou de exemplos few-shot para o Nó 3 (verificação) — mas não façam isso cedo demais; com poucos dados, é melhor usar as correções para ajustar prompts e regras determinísticas do que treinar/fine-tunar um modelo.

**LGPD e confidencialidade**: dado de dossiê de cliente é informação comercialmente sensível (composição de produto, estratégia de registro) — mesmo não sendo dado pessoal no sentido estrito da LGPD, tratem com o mesmo rigor de segurança: isolamento por cliente (multi-tenancy lógica desde o schema, mesmo em banco único), sem compartilhar dado de um cliente no contexto de outro nem para "aprender com precedente" sem anonimização.

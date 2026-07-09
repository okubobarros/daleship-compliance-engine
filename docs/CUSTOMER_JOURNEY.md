# Jornada do Cliente — Do Primeiro Contato ao Uso Recorrente

> **Nota de escopo (ver CLAUDE.md, seção 5):** este documento descreve a Fase 2 do projeto (MAPA/Anvisa/Ibama — defensivos e bioinsumos). A Fase 1 atual é Comex — consulte `docs/ROADMAP.md` e `docs/MVP_PRODUCT_SPEC.md` para o escopo em execução agora.

**Referência:** PRD.md (seção 5, versão resumida) — este documento aprofunda cada etapa com o que o produto precisa entregar e como medir sucesso.

---

## Etapa 0 — Descoberta (antes do produto existir para o cliente)

Canal: consultoria regulatória parceira ou indicação direta a fabricante de genérico.
**O que o cliente sente:** ceticismo — "mais uma ferramenta de IA que promete e não entrega precisão em algo que pode gerar multa".
**O que precisa estar pronto:** um caso real de demonstração (dossiê já registrado, resultado conhecido) para mostrar ao vivo, não slide.

## Etapa 1 — Primeira demonstração (ao vivo, não self-service)

O analista ou consultor vê o sistema processar um dossiê real diante dele.
**Momento de valor**: quando o sistema aponta uma lacuna real e cita a norma exata — é o instante em que a confiança nasce ou morre. Não avancem para produto self-service antes desse momento funcionar de forma consistente.
**Métrica**: taxa de "isso está certo" reconhecida pelo próprio especialista humano na sala.

## Etapa 2 — Onboarding do primeiro dossiê real do cliente

Cliente sobe um dossiê real (não mais o de demonstração).
**Fricção a eliminar**: formato de entrada. No início, aceitem o que o cliente já tem (Word, planilha, PDF) — não exijam que ele se adapte ao formato de vocês primeiro.
**O que o sistema entrega**: lista de apontamentos com citação, classificados por órgão (MAPA/Anvisa/Ibama).

## Etapa 3 — Revisão humana e captura de correção

Analista do cliente (ou consultor parceiro) valida/corrige cada apontamento.
**Design crítico**: a interface nunca deve parecer que está "testando" o analista — deve parecer que está economizando o trabalho dele. Cada correção precisa ser rápida (1 clique quando possível), com campo aberto só quando a correção é substantiva.
**Isso é o momento em que o ativo de dado proprietário nasce** — toda correção vira treino futuro do sistema.

## Etapa 4 — Decisão de compra

Depois de ver o sistema funcionar em 1-2 dossiês reais, o cliente decide pagar.
**O que fecha a venda**: comparação honesta de tempo (quanto tempo levaria manualmente vs. com o sistema) e uma citação de norma que o próprio analista não tinha lembrado — esse é o argumento mais forte, mais que qualquer métrica de "IA".
**Modelo inicial de cobrança**: nos primeiros clientes (design partners), considerem preço simbólico ou desconto agressivo em troca de compromisso de uso real e feedback estruturado — não deem de graça, mas também não tentem maximizar receita nesse estágio.

## Etapa 5 — Uso recorrente

Cliente passa a submeter múltiplos dossiês ao longo do tempo.
**O que gera retenção**: consistência de precisão (se o sistema errar uma citação uma vez, a confiança cai muito mais do que sobe com dez acertos seguidos — tratem erro de citação como bug crítico de prioridade máxima, não como "ainda estamos aprendendo").
**Expansão natural**: monitoramento contínuo pós-registro (alertas de mudança normativa que afetam produtos já registrados) é o gancho de upsell de assinatura recorrente.

## Etapa 6 — Piloto formal com uma trading/consultoria

Quando o produto já tiver passado pelas etapas 1-5 com 1-2 clientes, o piloto formal com uma trading maior segue outro ritmo:
1. Acordo explícito de piloto com critério de sucesso definido antes de começar (ex: "reduzir de X dias para Y horas o tempo de triagem de N dossiês").
2. Acesso a um conjunto real de dossiês históricos da trading para calibrar o sistema antes do teste ao vivo.
3. Sessão de fechamento com os números reais do piloto, não estimativa — é isso que abre a conversa comercial seguinte (contrato ou expansão).

## Contrato de navegação pública

Para a jornada pública do Comex, a navegação precisa respeitar estas regras:
1. `simulacao.html` só avança quando Invoice e Packing List estão anexados; a referência ajuda no contexto, mas não libera a reconciliação sozinha.
2. `loading.html` só executa quando existe um pedido explícito de pré-análise com base documental mínima; sem esse pedido, a tela não usa fallback nem mock e apenas mostra o estado bloqueado.
3. `resultado.html` é o estado final da execução atual; ele precisa exibir leitura executiva, critérios avaliados, achados por severidade e ação recomendada. Não deve existir botão de reexecução que reabra `loading.html` dentro da mesma rodada.
4. Não existe loop automático `loading -> resultado -> loading` sem uma nova submissão, correção ou reexecução explícita do usuário.

## Evolução UX do cockpit e do relatório

Esta seção consolida a evolução de tela e fluxo que o produto público precisa manter. A lógica não é "mostrar que a IA pensou", e sim "mostrar que o usuário já tem base suficiente para agir com segurança".

| # | Ponto de evolução | Status | O que já foi aplicado |
|---|---|---|---|
| 1 | Trava de entrada com base documental mínima | Aplicado | A reconciliação pública só libera com Invoice + Packing List. Referência isolada não basta. |
| 2 | Quarto documento opcional para reforço analítico | Aplicado parcial | O slot de ERP / cadastro mestre existe como reforço de cobertura e precisão. |
| 3 | Fim do fallback passivo com mock | Aplicado | `loading.html` não deve fingir execução sem submissão real. |
| 4 | Loading dinâmico e orientado a progresso | Aplicado parcial | A tela de loading passa a mostrar etapa, mensagem e avanço do processamento. |
| 5 | Resultado como relatório terminal | Aplicado | `resultado.html` não reabre o loop de execução dentro da mesma rodada. |
| 6 | Leitura executiva primeiro | Aplicado | O topo do resultado resume cobertura, criticidade e conclusão para decisão rápida. |
| 7 | Critérios avaliados por eixo | Aplicado | O relatório organiza a análise em critérios claros, com severidade, evidência e ação recomendada. |
| 8 | Evidência visível por achado | Aplicado | Cada achado mostra a base que o sustentou, sem esconder a origem da leitura. |
| 9 | Proveniência do backend e do dossiê | Aplicado parcial | `resultado.html` pode consumir resumo real do backend quando há `dossie_id`; sem isso, não inventa número. |
| 10 | Escala para dossiês grandes e leitura agregada | Em evolução | A UX precisa agrupar itens e destacar exceções críticas para casos com milhares de linhas sem perder rastreabilidade. |

### Regra prática da experiência

- Se faltar documento obrigatório, o sistema bloqueia a próxima ação.
- Se houver base mínima, a interface mostra progresso, cobertura e próximos passos.
- Se o relatório final já foi gerado, a experiência termina ali e qualquer nova análise começa por nova submissão.
- Se houver documento opcional, ele melhora a confiança e a cobertura, mas não substitui a base obrigatória.

---

## Job to be Done — tabela consolidada

| Situação | Job funcional | Job emocional |
|---|---|---|
| Analista monta dossiê manualmente | "Preciso saber, antes de submeter, se falta algo que vai gerar exigência" | Não quero ser responsável por um atraso evitável |
| Consultoria atende múltiplos clientes | "Preciso escalar sem contratar mais analistas seniores" | Quero manter minha margem sem perder qualidade |
| Fabricante espera aprovação | "Preciso saber quando meu produto pode ir a mercado" | Quero prever receita, não só esperar |

## Métricas por etapa (para instrumentar desde o início)

- Etapa 1→2: taxa de conversão de demo para primeiro dossiê real subido.
- Etapa 3: tempo médio de revisão humana por dossiê (deve cair ao longo do tempo, é prova de aprendizado do sistema).
- Etapa 4→5: taxa de recompra/segundo dossiê submetido.
- Etapa 6: se o critério de sucesso definido no piloto foi atingido — sim/não, sem margem de interpretação.

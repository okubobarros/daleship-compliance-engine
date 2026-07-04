# PRD — Motor de Conformidade Embutido para Registro de Defensivos Agrícolas (MVP)

> **Nota de escopo (ver CLAUDE.md, seção 5):** este documento descreve a Fase 2 do projeto (MAPA/Anvisa/Ibama — defensivos e bioinsumos). A Fase 1 atual é Comex — consulte `docs/ROADMAP.md` e `docs/MVP_PRODUCT_SPEC.md` para o escopo em execução agora.

**Versão:** 1.0
**Status:** Draft para construção com Claude Code
**Empresa:** Daleship Ltda.

---

## 1. Contexto e problema

O registro de defensivos agrícolas no Brasil exige avaliação tripartite obrigatória por três órgãos federais — MAPA (agronômico), Anvisa (toxicológico) e Ibama (ambiental). Em maio de 2026 o MAPA lançou o SISPA (Sistema Unificado de Informação, Petição e Avaliação Eletrônica), unificando fluxos antes separados, em cumprimento à Lei nº 14.785/2023. A operação plena do sistema exige adaptação dos fluxos internos dos três órgãos e retreinamento das empresas — o mercado inteiro está reaprendendo o processo ao mesmo tempo.

**A dor real:** montar um dossiê de registro exige cruzar exigências documentais de três órgãos com regras próprias, historicamente heterogêneas, sujeitas a mudança normativa frequente. Empresas sem departamento regulatório robusto (majoritariamente fabricantes de genéricos pós-patente) dependem de processo manual, lento e sujeito a exigência de complementação — cada mês de atraso é faturamento perdido de um produto ainda não liberado.

**Não existe, até o momento, uma ferramenta de IA dedicada a essa dor** (validado por pesquisa de mercado — o ecossistema de agtech brasileiro é robusto mas focado em produtividade agronômica, não em compliance regulatório de registro).

## 2. Objetivo do MVP

Construir uma demonstração funcional, com dados reais, capaz de:
1. Receber os dados de um produto candidato a registro.
2. Cruzar com a base normativa dos três órgãos e com precedentes já registrados.
3. Apontar lacunas documentais e inconsistências, **cada uma citando a norma exata que a exige**.
4. Capturar a correção humana do analista regulatório como dado estruturado.

O MVP não precisa cobrir todas as categorias de defensivo, nem integrar automaticamente com o SISPA. O objetivo é abrir conversa comercial com design partners (fabricantes de genéricos e consultorias regulatórias), não entregar uma plataforma completa.

## 3. Fora de escopo nesta fase (explicitamente)

- Integração automática/API com o SISPA (sistema recém-lançado, sem API pública conhecida).
- Cobertura de todas as famílias de defensivos — MVP cobre uma única categoria/ingrediente ativo de alto volume.
- Roteamento dinâmico multi-LLM para otimização de custo — usar um único modelo forte no MVP.
- Dashboard executivo, relatórios de ROI, faturamento — vem depois da validação de demanda.
- Submissão real de petições — o sistema apoia a montagem e conferência do dossiê, não substitui a submissão oficial.

## 4. Personas / ICP

| Persona | Perfil | Dor principal |
|---|---|---|
| **Analista regulatório (fabricante de genérico)** | Trabalha em empresa sem departamento regulatório grande; monta dossiê manualmente | Tempo gasto cruzando exigências de 3 órgãos; risco de exigência de complementação que atrasa registro |
| **Consultor regulatório agro (canal)** | Presta serviço de montagem de dossiê para múltiplos clientes fabricantes | Precisa escalar atendimento sem contratar mais analistas; margem depende de velocidade |
| **Empresa de bioinsumos** | Segmento novo, trilha regulatória menos pacificada | Ainda mais incerteza normativa, processo menos padronizado |

## 5. Jornada do usuário (MVP)

1. Usuário sobe dados do produto candidato (ingrediente ativo, formulação, dados de eficácia/toxicologia) — via upload de documento ou formulário estruturado.
2. Sistema extrai e estrutura os dados do dossiê.
3. Sistema cruza com Agrofit (precedente de produtos já registrados com o mesmo ingrediente ativo) e com a normativa dos três órgãos.
4. Sistema retorna: lista de lacunas/divergências, cada uma com citação da norma e do órgão responsável.
5. Usuário (analista/consultor) valida ou corrige cada apontamento em interface simples.
6. Correção é registrada de forma estruturada (produto, campo, correção, justificativa, timestamp, autor).

## 6. Requisitos funcionais do MVP

### RF01 — Ingestão de base normativa
O sistema deve indexar, com metadado de fonte e data de vigência: Agrofit, Instruções Normativas MAPA/SDA relevantes (incluindo IN 36/2009 e normas de registro simplificado), monografias toxicológicas da Anvisa, normas ambientais do Ibama aplicáveis a defensivos.

### RF02 — Extração de dossiê de entrada
O sistema deve extrair campos estruturados de um dossiê de produto (ingrediente ativo, formulação, dados de eficácia e toxicologia) a partir de documento enviado pelo usuário.

### RF03 — Cruzamento e verificação
Para cada campo/exigência normativa relevante ao ingrediente ativo em questão, o sistema deve verificar presença, completude e consistência com o precedente do Agrofit.

### RF04 — Justificativa explicável
Cada divergência ou lacuna apontada deve vir acompanhada de citação da norma específica (número da IN, artigo, órgão) que a exige — nunca uma afirmação sem fonte rastreável.

### RF05 — Roteamento por órgão
O sistema deve classificar cada exigência apontada por órgão responsável (MAPA/Anvisa/Ibama), já que a avaliação é tripartite e cada órgão pode gerar exigência isolada.

### RF06 — Captura de correção humana
Interface para o usuário validar ou corrigir cada apontamento do sistema, com registro estruturado da correção (campo, valor sugerido, valor corrigido, justificativa do analista, autor, timestamp).

### RF07 — Log auditável
Toda decisão do sistema e toda correção humana devem ficar registradas em log append-only, nunca sobrescrito.

## 7. Requisitos não funcionais

- **Explicabilidade antes de automação plena**: o sistema nunca decide sozinho — sempre aponta e cita, humano decide.
- **Precisão de citação**: toda referência normativa deve apontar para a fonte indexada real (RF01), nunca gerada livremente pelo LLM sem grounding.
- **Versionamento de norma**: mudança normativa não sobrescreve histórico — cada norma tem data de vigência.
- **LGPD**: dados de produto de cliente tratados como confidenciais; sem retenção além do necessário para o serviço.

## 8. Métricas de sucesso do MVP

- Sistema identifica corretamente pelo menos 80% das lacunas documentais em um conjunto de teste de dossiês já registrados (comparando contra o resultado real conhecido).
- Tempo de análise de um dossiê cai de X dias (baseline manual, a levantar com design partner) para menos de 1 hora de processamento + revisão humana.
- Pelo menos 2 design partners (1 fabricante + 1 consultoria) validam o output como útil em sessão de demonstração ao vivo.

## 9. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| SISPA sem API pública, estrutura de petição pode mudar | Mapear estrutura manualmente no início; tratar como dado a atualizar manualmente, não via integração automática |
| Alucinação de citação normativa | RAG com grounding obrigatório; nunca aceitar citação sem chunk de origem indexado |
| Baixa qualidade de dado do Agrofit para cruzamento | Validar amostra manual antes de confiar no cruzamento automatizado |
| Resistência de analista regulatório em confiar no output de IA | Design de UI que sempre mostra a fonte, nunca esconde o "porquê" |

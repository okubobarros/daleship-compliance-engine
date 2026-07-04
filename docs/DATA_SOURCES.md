# Mapa de Fontes de Dados — Registro de Defensivos Agrícolas

> **Nota de escopo (ver CLAUDE.md, seção 5):** este documento descreve a Fase 2 do projeto (MAPA/Anvisa/Ibama — defensivos e bioinsumos). A Fase 1 atual é Comex — consulte `docs/ROADMAP.md` e `docs/MVP_PRODUCT_SPEC.md` para o escopo em execução agora.

**Referência:** ARCHITECTURE.md, tabela `normas` e `precedentes_agrofit`

Este documento existe para orientar o trabalho de ingestão (scraping/parsing) que precisa ser feito antes de qualquer agente funcionar. Cada fonte deve ser tratada com estratégia própria de atualização.

---

## 1. Agrofit (MAPA) — precedentes de produtos registrados

- **O que é**: catálogo oficial e gratuito de todos os defensivos com registro ativo no Brasil, mantido pelo MAPA.
- **Uso no sistema**: base de precedente — "produtos com este ingrediente ativo já registrados seguiram este padrão de formulação/classificação".
- **Estratégia de captura**: verificar se há exportação em lote/API antes de assumir scraping via UI. Se só houver busca via interface, construir scraper direcionado por ingrediente ativo (não crawlear tudo de uma vez — comecem pela categoria escolhida para o MVP).
- **Frequência de atualização**: mensal é suficiente no MVP — não é uma fonte que muda diariamente.
- **Tabela de destino**: `precedentes_agrofit`.

## 2. Instruções Normativas MAPA/SDA

- **O que é**: regras de registro, incluindo a IN SDA nº 36/2009 (credenciamento e testes) e as normas específicas do registro simplificado.
- **Uso no sistema**: base normativa principal para verificação de exigência documental.
- **Estratégia de captura**: identificar as INs relevantes manualmente no início (não há tantas quanto no comex) e indexar o texto integral, chunkeado por artigo.
- **Frequência de atualização**: monitorar Diário Oficial da União para novas INs ou alterações — o SISPA está em rollout, mudanças são esperadas nos próximos 12-18 meses.
- **Tabela de destino**: `normas` (orgao = 'MAPA').

## 3. Monografias toxicológicas da Anvisa

- **O que é**: classificação toxicológica por ingrediente ativo definida pela Anvisa.
- **Uso no sistema**: verificação da perna toxicológica da avaliação tripartite.
- **Estratégia de captura**: mapear a fonte oficial de publicação das monografias (portal Anvisa); indexar por ingrediente ativo, com metadado de classe toxicológica.
- **Frequência de atualização**: baixa frequência de mudança por ingrediente já monografado; monitorar publicações novas.
- **Tabela de destino**: `normas` (orgao = 'ANVISA').

## 4. Normas ambientais do Ibama para defensivos

- **O que é**: exigências ambientais aplicáveis ao registro (a terceira perna da avaliação tripartite).
- **Uso no sistema**: verificação da perna ambiental.
- **Estratégia de captura**: mapear normas Ibama aplicáveis especificamente a agrotóxicos (não à totalidade do licenciamento ambiental — escopo estreito).
- **Frequência de atualização**: monitorar DOU.
- **Tabela de destino**: `normas` (orgao = 'IBAMA').

## 5. SISPA — estrutura de petição

- **O que é**: a nova plataforma unificada de petição eletrônica (lançada maio/2026), que substitui os três sistemas separados dos órgãos.
- **Uso no sistema**: define o formato de saída que o dossiê processado pelo sistema precisa atender.
- **Estratégia de captura**: **sem API pública conhecida no momento** — mapear manualmente a estrutura de campos e documentos exigidos diretamente na interface do sistema. Tratar como dado a manter atualizado manualmente (não automatizado) até que uma integração oficial esteja disponível.
- **Frequência de atualização**: alta — sistema recém-lançado, fluxos dos três órgãos ainda em adaptação. Revisar manualmente a cada 4-6 semanas nos primeiros meses.
- **Tabela de destino**: não populável em `normas` da mesma forma — tratar como documento de configuração separado (`sispa_template.json` ou equivalente), referenciado pelo Nó 5 do grafo para formatar a saída.

## 6. Diário Oficial da União (DOU)

- **O que é**: fonte de mudança normativa em tempo real para os três órgãos.
- **Uso no sistema**: gatilho de atualização — não é indexado por si só, mas monitorado para detectar quando uma norma já indexada mudou.
- **Estratégia de captura**: pipeline agendado (cron diário) filtrando por palavras-chave relevantes (defensivos, agrotóxicos, MAPA, SDA) e pelos órgãos relevantes.
- **Ação ao detectar mudança**: gerar diff contra a versão indexada, marcar a norma antiga com `data_vigencia_fim`, inserir nova versão — nunca sobrescrever.

## 7. Prioridade de construção para o MVP

Ordem sugerida (do que precisa estar pronto primeiro):

1. Agrofit — sem isso não há precedente para cruzar.
2. IN SDA relevantes ao registro simplificado — é o caminho mais comum para genéricos, o ICP primário do MVP.
3. Monografias Anvisa — só para os ingredientes ativos cobertos no MVP inicial (não a base inteira).
4. Normas Ibama aplicáveis — mesma lógica, escopo estreito primeiro.
5. Estrutura do SISPA — mapeamento manual, pode ser feito em paralelo por não depender de scraping.
6. Pipeline de DOU — pode vir depois do MVP inicial funcionar; não bloqueia a primeira demonstração.

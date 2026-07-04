# Monitoramento de DOU e Publicações Siscomex

**Referência:** DATA_SOURCES.md (seção "Diário Oficial da União")

---

## 1. A boa notícia: não precisam construir o scraper do zero

O governo federal já mantém uma ferramenta open-source pronta para isso: o **Ro-DOU** (`gestaogovbr/Ro-dou` no GitHub), mantido pelo próprio Ministério da Gestão e da Inovação em Serviços Públicos. Ele automatiza a pesquisa no DOU usando a mesma API da Imprensa Nacional que alimenta o buscador oficial (`in.gov.br/consulta`), rodando como DAG do Apache Airflow — ou seja, é literalmente uma ferramenta de "clipping" de diário oficial por palavra-chave, pronta para configurar com os termos de vocês (classificação fiscal, DUIMP, NCM, MAPA, defensivo agrícola etc.).

**Recomendação**: façam fork do Ro-DOU (ou usem como referência de implementação se preferirem reescrever em algo mais simples que Airflow) em vez de construir scraping HTML frágil contra o site do DOU.

## 2. Fonte alternativa/complementar: dados abertos em lote (para histórico)

A Imprensa Nacional publica mensalmente, na primeira terça-feira do mês, um arquivo ZIP com XML de todas as publicações do mês anterior, disponível também via `dados.gov.br` e replicado no `Base dos Dados` (basedosdados.org). Isso é ideal para **backfill histórico** — popular a base normativa com anos anteriores de uma vez, sem precisar rodar o monitoramento em tempo real retroativamente.

## 3. Arquitetura da rotina

```
┌──────────────────────────┐
│ Ro-DOU (ou equivalente)  │  → roda diariamente, filtra por palavras-chave:
│ busca DOU por keyword    │     "classificação fiscal", "NCM", "DUIMP",
└─────────┬─────────────────┘     "defensivo agrícola", "MAPA", "SISPA" etc.
          ▼
┌──────────────────────────┐
│ Parser de ato normativo   │  → identifica tipo (IN, Portaria, Resolução,
│                            │     Circular), órgão emissor, data de vigência
└─────────┬─────────────────┘
          ▼
┌──────────────────────────┐
│ Diff contra base indexada │  → é norma nova ou alteração de norma existente?
└─────────┬─────────────────┘
          ▼
    ┌─────┴─────┐
    ▼           ▼
[Norma nova]  [Norma alterada]
    │           │
    ▼           ▼
INSERT em     UPDATE data_vigencia_fim da versão antiga
`normas`      + INSERT da nova versão
    │           │
    └─────┬─────┘
          ▼
┌──────────────────────────┐
│ Reindexação incremental   │  → só o(s) chunk(s) novo(s)/alterado(s) no pgvector
└─────────┬─────────────────┘
          ▼
┌──────────────────────────┐
│ Alerta ("Radar Regulatório")│ → notifica clientes com produtos/dossiês
│                            │     afetados pela mudança
└──────────────────────────┘
```

## 4. Publicações do Siscomex (notícias/atualizações)

Diferente do DOU, não encontramos API dedicada para as notícias do Portal Único Siscomex sobre DUIMP, anuências, drawback, catálogo de produtos e tratamento administrativo. Tratamento recomendado:

- Monitoramento da página de notícias do Portal Único (`portalunico.siscomex.gov.br`) via checagem periódica (poll) com detecção de conteúdo novo — mais simples que scraping estruturado, porque o objetivo aqui é alerta de leitura humana, não extração de regra estruturada como no DOU.
- Tratar como fonte de **alerta**, não de base normativa formal indexada no RAG — a norma em si (quando publicada oficialmente) chega pelo pipeline do DOU; a notícia do Siscomex serve como sinal antecipado de mudança operacional (ex: "novo módulo do Catálogo de Produtos entra em produção em X data").

## 5. Isso vira feature de produto, não só infraestrutura interna

O mesmo pipeline que mantém a base atualizada pode virar o **"Radar Regulatório"** — uma feature vendável separadamente ou incluída na assinatura de monitoramento contínuo (já prevista na jornada, Etapa 5): cliente recebe alerta quando uma mudança normativa afeta um produto/dossiê que ele já tem em andamento ou já registrado. Isso transforma um custo de manutenção de dado em um diferencial competitivo direto.

## 6. Prioridade de implementação

1. Backfill histórico via arquivos XML em lote (rápido, dá cobertura retroativa imediata).
2. Fork/adaptação do Ro-DOU com as palavras-chave da vertical de defensivos.
3. Pipeline de diff e versionamento (reaproveita schema já definido em ARCHITECTURE.md).
4. Só depois, o monitoramento de notícias do Siscomex (menor prioridade — é sinal complementar, não fonte normativa formal).

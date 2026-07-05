# Golden Eval Set — Recuperação da Base Normativa (Fase 1)

Mede a qualidade de recuperação do `rag_search` e **calibra o limiar semântico**
(`DISTANCIA_MAXIMA`) com número real, não estimativa.

## Rodar

```bash
mcp-server/.venv/Scripts/python.exe eval/run_eval.py
```

Precisa de `VOYAGE_API_KEY` (embeda as queries) e `DATABASE_URL`. Embeda **todas** as
queries numa única chamada Voyage — leve para o rate limit do free tier.

## Arquivos

- `golden_set.yaml` — queries curadas. **positivos**: query no-domínio + `espera`
  (`tipo_documento` + `contem`, substring que deve aparecer no resultado relevante),
  ancorados em conteúdo verificado como presente na base. **negativos**: queries
  genuinamente fora do domínio de comex (IR, previdência, temas aleatórios) — o esperado
  é recuperar **nada** dentro do limiar.
- `run_eval.py` — roda cada query, registra a distância semântica em que o resultado
  relevante aparece (positivos) e a menor distância de qualquer norma (negativos), e faz
  a **varredura de limiar** reportando o T que maximiza a acurácia.

## Resultado da calibração (2026-07-05)

Base: NCM 15.156 (lexical), Soluções de Consulta 5.735, Tratamento Administrativo 99,
RGI 6 (as três últimas com embedding).

- Positivos no-domínio: distância **≤ 0.494**.
- Negativos fora do domínio: distância **≥ 0.518**.
- **Folga: +0.024** (separáveis, mas margem fina).
- `DISTANCIA_MAXIMA` ajustado de 0.65 → **0.51** (ponto médio da folga): **100%** no golden
  set (11/11 positivos recuperados, 6/6 negativos rejeitados), vs 88% no 0.65 (que citava
  "bolo de cenoura" a 0.518). Princípio: citação errada é pior que miss → favorecer rejeitar.

## Achados / fraquezas conhecidas

- **RGI abafada por SC em queries de classificação**: a query "mercadoria importada
  incompleta ou desmontada, como classificar" **não** trouxe a RGI Regra 2 no top-10 — as
  5.735 SCs (todas "Classificação de Mercadorias") dominam o vizinhança semântica. As outras
  3 queries de RGI recuperaram bem (0.29–0.49). Mitigação futura (fora do escopo da
  calibração): recuperação com piso por `tipo_documento` (garantir N resultados de RGI),
  ou reranking por fonte. O item foi **mantido no golden set** como marcador de regressão.
- **Folga estreita (0.024)**: com mais fontes/queries as classes podem se sobrepor.
  Recalibrar ao crescer a base ou o golden set.

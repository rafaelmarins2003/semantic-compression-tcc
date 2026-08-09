# ADR 0002 — Modelo gerador do dataset

| Campo | Valor |
|---|---|
| Status | **Aceita** |
| Data | 2026-08-08 |
| Decide | qual modelo gera o dataset regenerado em inglês ([ADR 0001](0001-idioma-dos-artefatos.md)) |
| Evidência | piloto da [spec 004 §4.1b](../004-camada-de-dados/spec.md), tabela `model_pilot`, run `pilot_v2_en` |

## Decisão

**`glm-5.2:cloud` nos dois estágios** (preprocess e geração de JSON), substituindo
`kimi-k2.6:cloud` + `deepseek-v4-pro:cloud`.

## Evidência

50 amostras estratificadas (30 gitlab_handbook, 20 pet, seed 42), apenas splits
`sft`/`grpo` — o holdout ficou fora para não contaminar a escolha. Pipeline
completo por amostra: preprocess → JSON → DSL → XML → XSD.

| Config | XSD | JSON ok | Nós | Gateways | Lanes | Violações | Erros |
|---|---|---|---|---|---|---|---|
| **glm52** | **96,0%** | 98,0% | 18,4 | 2,86 | 3,12 | 0,16 | 1 |
| controle (kimi+deepseek-pro) | 92,0% | 94,0% | 18,1 | 3,20 | 3,20 | 0,22 | 4 |
| dsflash (`deepseek-v4-flash:0731-cloud`) | 88,0% | 88,0% | 17,9 | 3,61 | 2,86 | 0,18 | 6 |

Tags **datados**, nunca aliases móveis: `deepseek-v4-flash:cloud` também responde,
mas alias que troca de build por baixo torna o número irreproduzível.

## Incerteza — registrada, não resolvida

**A diferença principal está dentro do ruído medido.** 96% contra 92% em XSD são
2 amostras em 50. O próprio piloto mostrou que repetições da mesma amostra a
temperatura 0 divergem (ver ADR 0003): o dsflash flipou validade XSD em 7 de 50
repetições. Uma diferença de 2 amostras não é distinguível dessa variância.

O sinal que sustenta melhor a escolha é o **secundário e consistente**: erros de
pipeline 1 vs 4 vs 6, e a maior taxa de JSON parseável (98% vs 94% vs 88%). Nas
três métricas o GLM lidera na mesma direção.

**Riqueza estrutural não separou os modelos.** No teste de fumaça o GLM extraiu
47 nós contra 9 do controle, o que sugeria extração muito mais rica. Na amostra
de 50 as médias praticamente empatam (18,4 vs 18,1). Aquele caso era outlier.

**Decisão consciente de custo/benefício.** Rodar k=3 para decidir com intervalo
de confiança era a alternativa rigorosa; foi descartada por tempo. A escolha
recai sobre o modelo que lidera todas as métricas, aceitando que a margem não é
estatisticamente sustentada.

## Idioma

Marcadores de português na saída do GLM: 4 de 50 — todos provavelmente falsos
positivos. A heurística original incluía `do` e `com`, que são palavras inglesas
comuns, e marcava rótulos legítimos como "Do the review". Heurística corrigida e
coberta por `tests/data/test_run_model_pilot.py`; os valores gravados em
`model_pilot` foram computados com a versão antiga e estão **inflados**.

A verificação real do idioma continua sendo a conferência manual de 20 amostras
prevista na spec 004 §6, após a regeneração.

## Confirmação após a regeneração completa (2026-08-09)

O piloto media 50 amostras; a base completa deu sinais melhores e um problema
que o piloto não pegou.

**Confiabilidade melhor que o piloto sugeria.** Sobre as 1021 amostras, a falha
real do GLM foi de **1 em 1021 (0,1%)** — um JSON truncado em ~52k caracteres.
A taxa de 3,4% reportada durante a execução estava contaminada por 540 respostas
HTTP 429 de estouro de quota, que são falha de infraestrutura e não de modelo;
foram removidas do banco.

**O GLM produz construções que o gerador anterior não produzia.** Em 20 das 1021
amostras ele emitiu *splits implícitos* — nó comum com mais de uma saída, sem
gateway. O Kimi/DeepSeek nunca produziu isso (0 ocorrências em 1021), então o
`json_to_dsl` nunca havia sido exercitado nesse caminho e descartava as arestas
excedentes. Correlação perfeita entre a construção e a perda: 20/20.

Corrigido por normalização em `graph._normalize_implicit_splits`. Não é motivo
para reverter a escolha do modelo — é um bug latente que a troca revelou, e o
resíduo caiu de 20 casos para 1.

## Consequências

- `DEFAULT_MODELS` dos runners passa a ter `glm-5.2:cloud` à frente.
- Se a regeneração completa degradar frente ao piloto, este ADR é revisto — não
  se ajusta a métrica até o número voltar.
- A escolha do gerador é propriedade documentada do dataset publicado no
  HuggingFace.

# Spec 004 — Camada de dados pronta para avaliação

| Campo | Valor |
|---|---|
| Status | **CONCLUÍDA** (2026-08-09) |
| Tipo | Engenharia (não é experimento) |
| Origem | [ADR 0001](../adr/0001-idioma-dos-artefatos.md) + pontas soltas achadas em 2026-08-08 |
| Desbloqueia | [spec 003](../003-eval-harness/spec.md) — precondições satisfeitas |

> Esta spec **não tem pré-registro, hipóteses nem análise estatística**. Não é
> experimento: é a camada de dados de que o experimento depende. O formato curto
> é deliberado — o valor está no código que ela produz, não no documento.

---

## 1. Objetivo

Deixar o banco em estado utilizável pelo harness de avaliação: base regenerada em
inglês, gold do PMo carregado, colunas de resultado populadas e comparação
XML↔XML disponível.

## 2. Problemas que resolve

| # | Problema | Evidência |
|---|---|---|
| P1 | Base gerada em português contra gold em inglês | ADR 0001 |
| P2 | Gold do PMo nunca carregado | `samples.bpmn_json` NULL em 1021/1021; gold existe só em `data/raw/pmo/` |
| P3 | `samples.dsl` / `xml` NULL ⇒ `export_training()` retorna 0 linhas | quebra AC-1 da 003 e a prioridade 5 (SFT) |
| P4 | Não existe comparação XML↔XML | `topology.compare()` recebe `(json_dict, xml_text)`; gold é BPMN XML |

## 3. Decisões de representação

**Gold do PMo = `data/raw/pmo/bpmn_process/*.bpmn`** (BPMN lógico, sem BPMNDI).
Descartados: `bpmn/` traz layout que não usamos, `pme/` exigiria adaptador de
schema, `simplified_xml/` não é BPMN padrão. Usar BPMN direto permite reusar
`xml_direct_follows` nos dois lados da comparação.

**PME-F1 fica reservado** para a métrica do próprio benchmark sobre o formato
`pme/` (tasks/events/gateways/flows), caso venha a ser implementada. A nossa
métrica de projeção direct-follows passa a se chamar **DF-F1**. Renomear na
spec 003 §3.2 — hoje ela usa "PME-F1" para a df-projetada, o que colidiria com
a métrica publicada do PMo. _(Inferido da estrutura de `data/raw/pmo/pme/`;
confirmar no paper antes de citar comparação com resultados publicados.)_

## 4. Escopo

1. **Prompts traduzidos para inglês** — `configs/prompts/*.md` reescritos
   integralmente em inglês (hoje são PT e é isso que dita a língua da saída),
   com diretiva explícita de idioma e nova `prompt_version`.
1b. **Piloto de seleção do modelo gerador** — a regeneração é a operação mais
   cara de reverter, então o modelo é escolhido *antes* dela e por medição, não
   por reputação. Candidatos verificados na Ollama Cloud: `kimi-k2.6:cloud` +
   `deepseek-v4-pro:cloud` (controle atual), `glm-5.2:cloud` e
   `deepseek-v4-flash:0731-cloud`. Resultado vira ADR 0002.

   Tags **datados**, nunca aliases móveis: `deepseek-v4-flash:cloud` também
   responde, mas um alias que muda de build por baixo tornaria os números da
   tese irreproduzíveis.

   **Métricas do piloto — não DF-F1.** DF-F1 compara o JSON gerado contra o XML
   derivado *desse mesmo* JSON: mede a cadeia determinística e fica ~1,0 para
   qualquer modelo. Não discrimina. O piloto usa, todas determinísticas:

   - taxa de sucesso do pipeline (JSON parseia → DSL → XML → XSD válido);
   - riqueza estrutural: nós, gateways e lanes por processo — um modelo que
     achata tudo em cadeia linear perde decisões e atores;
   - violações das `connection_rules` do próprio prompt;
   - conformidade de idioma (marcadores de português nos rótulos).

   **Amostra: 50 itens estratificados de `sft`/`grpo` apenas.** O holdout fica
   fora: escolher o gerador dos dados de treino olhando o conjunto de avaliação
   seria contaminação.
2. **Regeneração** — reexecutar `preprocess` e `generate_process_json` sobre as
   1021 amostras com o modelo vencedor; reprocessar as etapas determinísticas.
3. **Carga do gold** — migration + loader de `bpmn_process/*.bpmn` para os 53
   itens ativos do PMo.
4. **Persistência de resultados** — popular `samples.dsl`, `samples.xml`,
   `samples.bpmn_json`, `parse_ok`, `xsd_ok` a partir dos runs bem-sucedidos.
5. **`compare_xml(gold_xml, cand_xml)`** em `src/evaluation/topology.py`,
   reusando `xml_direct_follows` + `_prf`.
6. **Recalcular** eixo 2 e TCR sobre a base regenerada.

## 5. Critérios de aceitação

Testes em `tests/evaluation/test_gold.py` e `tests/data/test_persistence.py`.

| ID | Critério | Teste |
|---|---|---|
| AC-1 | Os 53 itens ativos do PMo têm gold carregado; os 2 excluídos não entram. | `test_ac1_gold_loaded_for_active_pmo` |
| AC-2 | Todo gold parseia com `xml_direct_follows` sem exceção e com ≥ 1 aresta. | `test_ac2_gold_parses_with_topology` |
| AC-3 | `compare_xml(gold, gold)` retorna `df_exact=True` e F1 = 1,0 para os 53. | `test_ac3_gold_self_comparison_is_perfect` |
| AC-4 | `export_training('sft')` retorna > 0 pares, todos com `dsl` não nulo. | `test_ac4_export_training_not_empty` |
| AC-5 | `export_training()` nunca retorna item com `split='holdout'`, em nenhum split pedido. | `test_ac5_export_never_leaks_holdout` |
| AC-6 | Prompts contêm diretiva de idioma explícita e `prompt_version` nova. | `test_ac6_prompts_declare_language` |
| AC-7 | `samples.xsd_ok` reflete a validação real: nenhum item marcado `1` falha em `validate_bpmn_xsd`. | `test_ac7_xsd_flag_is_truthful` |

## 6. Verificação não automatizada

**Amostragem de idioma** — após a regeneração, inspecionar manualmente amostras
aleatórias e confirmar rótulos em inglês. Heurística automática de idioma é
frágil demais para virar AC (a primeira versão marcava "Do the review" como
português); fica como conferência registrada aqui com data e resultado.

**2026-08-09 — APROVADO.** Amostragem aleatória (seed 11) sobre
`json_to_dsl_v10_en`, inspecionando pool, lanes e nomes de nós. Todos em inglês
nas duas fontes verificadas. Exemplos:

| Fonte | pool | lanes | nós |
|---|---|---|---|
| gitlab_handbook | Support Ticket Resolution… | Customer, Support Agent | Open Support Ticket |
| pmo | Marketing Campaign Management | Marketing Team, Sales Team | Define Campaign Objectives |
| gitlab_handbook | Co-Create Customer Onboarding | Sales/CSM | Assess Customer Fit |

Nenhum resquício de português. O [ADR 0001](../adr/0001-idioma-dos-artefatos.md)
está cumprido.

## 7. Fora de escopo

- Qualquer coisa da spec 003 (braços, protocolo, análise estatística)
- Implementar a métrica PME do benchmark sobre `pme/`
- Regerar Zenodo como multi-referência — decisão da 003, não desta spec

## 8. Riscos

**O eixo 2 pode piorar após a regeneração.** Os 1015/1021 atuais foram obtidos
sobre a base em português. Se a regeneração degradar, é resultado legítimo e
deve ser investigado antes de seguir para a 003 — não ajustado até voltar ao
número antigo.

**Custo de LLM**: não é restrição financeira (Ollama Cloud por assinatura); o
limite é de taxa — ao bater o teto de 5 horas, a execução espera. Logo os
runners precisam ser **retomáveis**: reexecutar deve pular o que já concluiu,
não recomeçar. `generate_process_json` já filtra por `prompt_version`; confirmar
que o mesmo vale para `preprocess` antes de disparar a base completa.

**Ordem**: itens 1 e 3 da [spec 005](../005-estrutura/spec.md) (achatamento e
autoridade das colunas) vêm **antes** da regeneração — caso contrário os dados
são migrados duas vezes.

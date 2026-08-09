# TODO — roteiro de execução

Atualizado em 2026-08-09. Specs em `specs/`; decisões de alcance amplo em `specs/adr/`.

## Estado atual

**Base ativa**: `json_to_dsl_v10_en` + `dsl_to_xml_v5_en` — 1021 amostras em inglês,
XSD 1021/1021, DF-F1 0,9999, TCR 6,01 (83,4% de redução).

**Pronto e verificado**
- DSL + parser (Lark), transpiler DSL→XML, `json_to_xml` direto, layout/BPMNDI
- Fases 1, 2 e 3 concluídas (estrutura, seleção de modelo, regeneração)
- Fundamentação Teórica: 14 páginas escritas (`article/cadeira_tcc/referencial_teorico/`)
- Introdução: escrita no template oficial; bibliografia oficial com 47 entradas

**Decidido**
- [ADR 0001](specs/adr/0001-idioma-dos-artefatos.md) — artefatos em inglês; monografia em português
- [ADR 0002](specs/adr/0002-modelo-gerador.md) — `glm-5.2:cloud` como gerador
- [ADR 0003](specs/adr/0003-nao-determinismo-temperatura-zero.md) — temperatura 0 não é determinística
- [ADR 0004](specs/adr/0004-estrategia-de-dados.md) — medir antes de coletar; treino é 95,3% GitLab

---

## Fase 1 — Estrutura ([spec 005](specs/005-estrutura/spec.md)) — **CONCLUÍDA**

- [x] Achatado `src/data/manipulation/*` e `src/data/ingestion/*` (profundidade ≤ 3)
- [x] `run_*` padronizado para jobs de lote; `import_*` mantido na ingestão
- [x] `run_materialize`: popula `samples.dsl/xml/bpmn_json/parse_ok/xsd_ok`
- [x] Retomada de `preprocess` filtrando por `prompt_version` (bug E4)
- [x] Comandos atualizados no CLAUDE.md e README

## Fase 2 — Seleção do modelo gerador — **CONCLUÍDA**

- [x] Prompts traduzidos para inglês, com diretiva `<language>` explícita
      (`preprocess_process_v2_en`, `bpmn_json_generator_v2_en`)
- [x] Piloto sobre 50 amostras estratificadas × 3 configurações
- [x] [ADR 0002](specs/adr/0002-modelo-gerador.md) — **glm-5.2:cloud** nos dois estágios
- [x] [ADR 0003](specs/adr/0003-nao-determinismo-temperatura-zero.md) — temperatura 0
      não garante determinismo; `k=1` da spec 003 §6.2 fica em aberto

## Fase 3 — Regeneração em inglês — **CONCLUÍDA** (2026-08-09)

- [x] Estágio 1 `run_preprocess`: 1021/1021
- [x] Estágio 2 `run_generate_json` (glm-5.2): 1021/1021 — 1 falha real de modelo (0,1%)
- [x] `json_to_dsl_v10_en`: 1021/1021 · `dsl_to_xml_v5_en`: 1021/1021 com XSD válido
- [x] `run_materialize`: 1021/1021
- [x] Conferência manual de idioma — aprovada (spec 004 §6)
- [x] Três bugs corrigidos, todos cobertos por teste:
      split implícito descartando arestas · `json_to_dsl` não determinístico entre
      processos · branch vazio de `and` descartado no XML. `df_missing`: 20 → **0**

Números da base atual:

| Métrica | Base PT (antiga) | **Base EN (atual)** |
|---|---|---|
| TCR | 5,08 (80,3%) | **6,01 (83,4%)** |
| DF exatos | 1015/1021 | **1017/1021** |
| DF-F1 médio | 0,9999 | **0,9999** |
| XSD | 1021/1021 | **1021/1021** |

## Fase 4 — Camada de dados ([spec 004](specs/004-camada-de-dados/spec.md))

- [x] Gold do PMo carregado em `gold_models` — 53/53, idempotente
- [x] Multi-referência do Zenodo — 172 alternativas (nota ≥ 4) sobre 24 itens
- [x] `compare_xml(gold, cand)` em `src/evaluation/topology.py`
- [x] MF-F1 separado para `messageFlow` (spec 003 §3.2b)
- [x] AC-1 a AC-3 (`tests/evaluation/test_gold.py`)
- [x] AC-4 a AC-7 (`tests/data/test_persistence.py`) — `export_training` agora
      **recusa** `split='holdout'` em vez de entregar o conjunto de avaliação

**Fase 4 concluída.** `gold_models` com 53 referências; `compare_xml` disponível;
todos os 7 ACs da spec 004 cobertos por teste.

## Fase 5 — Harness de avaliação ([spec 003](specs/003-eval-harness/spec.md))

- [x] Bloqueadores §10 fechados (2026-08-09): C/D removida · dois braços prompted
      (`deepseek-v4-pro` independente + `glm-5.2` gerador) · SA cortada da v1 ·
      `max_tokens` 8192/2048 medido · Zenodo = máx entre refs nota ≥ 4 · k=3
- [ ] Migration `benchmark_eval` + `run_benchmark.py`
- [ ] `tests/evaluation/test_harness_spec.py` (AC-1 a AC-8)
- [ ] **Congelar a spec** (commit datado) e só então rodar A1, A1g, A2, A2g, A3 — 795 gerações

## Fase 6 — Monografia

- [ ] Migrar Fundamentação Teórica do `referencial_teorico` para o template oficial
- [ ] Trabalhos Relacionados — incluir parágrafo compressão de entrada (LLMLingua/Headroom) vs geração; posicionar contra ProMoAI
- [ ] Metodologia — derivar das specs 003/004
- [ ] Resultados e Conclusão — após a Fase 5
- [ ] Substituir lista de siglas do template-exemplo (hoje é do TCC de saúde) por BPMN, DSL, LLM, XSD, TCR, DF-F1
- [ ] Resolver atribuição do PMo: banco diz Kourani 2024, `.bib` usa `brissard2025pmo`
- [ ] Corrigir `\imprimirglossario` (`main.tex:214` usa `\glossarystyle`, removido no glossaries v4)

## Fase 7 — SFT e publicação

- [ ] SFT sobre o pool exato regenerado (QLoRA 4-bit)
- [ ] Publicar dataset + adapter no HuggingFace: model card, datasheet, splits, licença, script de exportação
- [ ] GRPO — opcional, fora do escopo mínimo

---

## Layout / BPMNDI — sob demanda, fora do pipeline

Decidido em 2026-08-08: o layout **não** é materializado no banco. `run_dsl_to_xml`
grava XML lógico; `add_layout` é aplicado só na hora de exportar para inspeção
visual ou via `json_to_xml` (baseline direto).

Motivo: BPMNDI triplica o XML, não alimenta métrica nenhuma (TCR exige XML
lógico por definição normativa, DF-F1 projeta topologia, o gold do PMo é
`bpmn_process` sem DI) e guardá-lo criaria a chance de alguém medir contra a
coluna errada — que é exatamente o erro dos 91% já corrigido.

Se um dia for materializado, tem de ser em **coluna separada**, nunca
sobrescrevendo o XML lógico, senão o AC-4 da spec 003 quebra.

- [x] Branches paralelos vazando da raia — corrigido em 2026-08-08: altura de raia
      passou a ser dimensionada pelo empilhamento real, com topos cumulativos.
      Coberto por `test_parallel_branches_stay_inside_their_lane`.
- [x] Centralização vertical — corrigida em 2026-08-08: nós são centrados na faixa
      do slot, então eventos e tasks compartilham o mesmo centro e as arestas saem
      retas. Coberto por `test_nodes_of_different_sizes_share_a_vertical_center`.

## Em aberto (sem data)

- **Modelo base**: Qwen2.5-Coder-7B está datado; há coders pequenos melhores hoje.
  Trocar **invalida o TCR** — a spec 003 §3.3 fixa o tokenizador do Qwen. Decidir
  antes de escrever o número na tese.
- **PME-F1**: nome reservado para a métrica do benchmark sobre `data/raw/pmo/pme/`.
  Confirmar no paper do PMo antes de comparar com resultados publicados.

PS: sempre que terminar o dia, deixar o TODO atualizado para não perder o ponto
de retomada.

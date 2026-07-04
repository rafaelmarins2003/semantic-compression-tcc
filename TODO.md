# TODO — priorização revisada (2026-07-04)

Estado: pipeline determinístico fechado ponta a ponta (**json_to_dsl_v8** = 1021/1021,
XSD 1021/1021, eixo 2 = **1015/1021 arestas exatas, mean F1 0.9999**, `df_missing`
vazio em 100% — nenhuma aresta perdida). Contaminação do holdout corrigida: `pmo` +
`zenodo` agora são `split='holdout'` (zenodo = mesma fonte do PMo 25–48; nunca entram
em treino). Pool SFT = 772 amostras, das quais **766 com `df_exact=1`**; GRPO =
172/172; holdout = 77/77.

## Ordem de prioridade

1. **Commitar o eixo 2** — `src/evaluation/topology.py`, `run_topology.py`, migração e
   testes estão untracked na branch `feat/json_to_dsl_v7`. Os melhores resultados do
   projeto não podem viver fora do git.
2. ~~[BUG PRIORITÁRIO] Arestas de convergência perdidas~~ **CORRIGIDO (2026-07-04,
   json_to_dsl_v8)**: causa raiz = branch que parava na fronteira do join
   (`end_boundary`) perdia a aresta implícita "cauda → join" quando o join já tinha
   sido emitido dentro de um branch irmão (convergência não-SESE) — o `()`/cauda
   ficava sem alvo. Fix: `_linearize` reporta `hit_boundary` e `_emit_gateway_block`
   materializa `#ref` explícito quando o join não vira continuação. Resultado:
   df_exact 891→**1015**/1021, zero regressões, 3 testes de regressão novos.
   - Resíduo (6 casos, todos já não-exatos na v7): só arestas **extras** (2
     self-loops) — defeito distinto e mais leve (recall 1.0; precisão <1 em 6
     amostras). Investigar depois, baixa prioridade.
3. **Harness de avaliação + baselines (caminho crítico da tese)** — sem isso os
   resultados do modelo não têm "so what":
   - Baseline A: LLM SOTA prompted emitindo BPMN XML direto.
   - Baseline B: LLM SOTA prompted emitindo a DSL.
   - Sistema: Qwen finetunado emitindo a DSL.
   - Avaliar contra o gold do PMo (53); usar Mangler (multi-referência com score de
     especialista, agora no holdout) para tratar ambiguidade de modelagem.
   - TCR: reportar DSL vs XML **com e sem BPMNDI** e vs JSON canônico, tokenizador do
     Qwen declarado. Comparar só contra XML completo inflaria a razão.
4. **Phase 2b — encerrada (2026-07-04):** o bug foi corrigido (item 2); resíduo final
   = 6 amostras com arestas extras. Essas 6 viram prompts de GRPO e uma nota de
   limitações; nenhuma perda de aresta permanece no corpus.
5. **Escrever o capítulo de Metodologia** — ~~agora~~ FEITO em 2026-07-04 (introdução +
   metodologia escritas no template oficial; manter sincronizado se o fix mudar números).
6. **SFT** — Qwen2.5-Coder-7B, QLoRA 4-bit, pares (texto cru, DSL) do pool exato:
   **766** (pós-fix v8; era 666).
7. **[OPCIONAL — GRPO]** Fora do escopo mínimo do TCC; material para artigo futuro.
   Recompensa `r_sint(0.35) + r_sem(0.30) + r_topo(0.25) + r_comp(0.10)`.
   Atenção: r_sem é o elo fraco (LLM-judge/embedding é ruidoso e hackeável a peso
   0.30) — ancorar em overlap de labels com a estrutura pré-processada ou reduzir peso.
8. **Publicar dataset E modelo no HuggingFace** — contribuições citáveis; não existe
   base equivalente aberta. Dataset quando 100% populado; modelo (adapter LoRA + card)
   após o SFT.
9. **Layout/BPMNDI (portar da Vertere) — por último.** BPMNDI é opcional no XSD e
   nenhuma métrica depende dele; serve só para conferência visual dos diagramas.
   O `json_to_xml.py` direto (stub vazio) entra aqui como referência visual/olhômetro.

## Artigo futuro (fora do TCC, anotar na tese como trabalho futuro)

- **Constrained decoding como baseline comparativa**: grammar-constrained decoding do
  JSON canônico (ou da própria DSL) vs DSL finetunada — responde o contra-argumento
  "por que não decodificação restrita?" e vira métrica/experimento de um artigo
  derivado desta tese.
- GRPO completo com a recompensa composta (item 6).

# PS:
Sempre que terminar o dia, deixar o todo para a próxima vez que for entrar para não
esquecer aonde parou.

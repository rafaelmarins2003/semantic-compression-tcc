# Spec 003 — Harness de Avaliação e Baselines

| Campo | Valor |
|---|---|
| Status | **RASCUNHO** — não congelado |
| Congelar em | commit imediatamente anterior à primeira execução do experimento |
| Commit de congelamento | _(preencher: `git rev-parse HEAD`)_ |
| Data de congelamento | _(preencher)_ |
| Prioridade | 3 (CLAUDE.md) |
| Depende de | `json_to_dsl_v10_en`, `dsl_to_xml_v5_en`, `src.evaluation.topology` |

> **Regra de pré-registro.** Depois de congelado, este documento só muda por
> emenda registrada na seção 9. Alterar definição de métrica, braço ou critério
> de análise **após ver resultados** invalida a comparação. Emendas são
> permitidas; emendas silenciosas não.

---

## 1. Objetivo

Medir se gerar **DSL comprimida + transpilação determinística** produz BPMN
melhor do que gerar **XML BPMN diretamente**, sob o mesmo orçamento de modelo,
contra o gold do PMo Benchmark.

Esta é a evidência central da tese. O harness precisa ser reprodutível por
terceiros a partir do repositório e do `data/dataset.db`.

## 2. Precondições

> ⛔ **Bloqueada pela [spec 004](../004-camada-de-dados/spec.md).** Falta carregar
> o gold do PMo e implementar a comparação XML↔XML. A regeneração em inglês
> ([ADR 0001](../adr/0001-idioma-dos-artefatos.md)) já foi concluída.

### Precondições já satisfeitas

Base atual: `json_to_dsl_v10_en` + `dsl_to_xml_v5_en`, 1021 amostras, rótulos em
inglês (conferência registrada na spec 004 §6).

| Precondição | Estado | Evidência |
|---|---|---|
| Transpilação DSL→XML válida | ✅ | XSD 1021/1021 |
| Equivalência topológica JSON↔XML | ✅ | eixo 2: 1017/1021 exatos, df-F1 0,9999 |
| Baseline determinístico JSON→XML direto | ✅ | `src.data.deterministic.json_to_xml` |
| Holdout isolado do treino | ✅ | `split='holdout'` (pmo 53 + zenodo 24 = 77) |

Resíduo do eixo 2: **4 casos não-exatos**, todos só com arestas extras.
`df_missing` está zerado — nenhuma lógica é perdida. Documentar como limitação;
não corrigir durante o experimento.

A troca de gerador ([ADR 0002](../adr/0002-modelo-gerador.md)) expôs três bugs
reais, todos corrigidos e cobertos por teste:
1. splits implícitos descartavam arestas (`graph._normalize_implicit_splits`);
2. `json_to_dsl` não era determinístico entre processos (iteração de `set` sem
   ordenação em `_find_merge_point`);
3. branch vazio de `and` era descartado na emissão do XML, colapsando
   paralelismo em sequência (`transpiler.xml`).

Resultado: `df_missing` foi de 20 casos para zero, superando a base anterior.

## 3. Definições operacionais das métricas

> Cada métrica abaixo estava até aqui registrada **apenas como sigla** no
> CLAUDE.md. As definições desta seção são normativas: o código segue este
> documento, não o contrário.

### 3.1 XSD-Val — validade sintática

Binária, por amostra. `src.transpiler.xsd.validate_bpmn_xsd(xml) == []` contra
`schemas/bpmn20.xsd`. Reportada como taxa sobre o conjunto de avaliação.
Amostra que não valida entra nas demais métricas como **falha total**
(DF-F1 = 0), nunca como dado ausente.

### 3.2 DF-F1 — fidelidade topológica (**métrica primária**)

> Renomeada de "PME-F1" pela [spec 004 §3](../004-camada-de-dados/spec.md): o
> PMo Benchmark tem formato próprio `pme/` (tasks/events/gateways/flows) e
> provavelmente uma métrica homônima. Reservar a sigla evita colisão com
> resultados publicados. Todas as ocorrências de "PME-F1" abaixo referem-se a
> esta métrica de projeção direct-follows.

F1 sobre o multiconjunto *direct-follows* projetado em nós emitíveis, pulando
gateways de roteamento — exatamente `src.evaluation.topology.compare()`, já
implementado e validado no eixo 2.

- Referência: grafo do JSON gold do PMo.
- Candidato: XML gerado pelo braço sob teste.
- Identidade de nó: rótulo normalizado; eventos anônimos colapsam para
  `<start>` / `<end>` / `<catch>` / `<throw>`.

Reusar `compare()` sem alterações. Se o gold exigir adaptação, a mudança entra
como emenda (seção 9), porque afeta retroativamente os números do eixo 2.

### 3.3 TCR — razão de compressão de tokens

```
TCR = tokens(XML_lógico) / tokens(DSL)
```

- **> 1 ⇒ a DSL é mais compacta.** Redução percentual derivada: `1 − 1/TCR`.
- Tokenizador: **o do Qwen2.5-Coder-7B**, o mesmo modelo-alvo. Um tokenizador
  diferente muda o número; fica congelado aqui.
- **O XML do denominador é o XML lógico (`--no-layout`).** O BPMNDI infla o XML
  em várias vezes sem conteúdo semântico; medir TCR contra XML com layout
  inflaria artificialmente o resultado principal da tese. Não fazer.
- TCR é **descritiva, não comparativa entre braços**: só existe para braços que
  emitem DSL. Reportar média e IC95% bootstrap.

> ⚠️ Divergência resolvida aqui: o referencial teórico
> (`subsec:tcr`) define TCR como razão XML/DSL (>1 = melhor). Qualquer texto do
> projeto que use a forma de redução `1 − DSL/XML` deve ser corrigido para
> a forma-razão ou marcado explicitamente como "redução".

#### Medição de referência (2026-08-09, base regenerada em inglês)

Medido sobre os 1021 pares `json_to_dsl_v10_en` / `dsl_to_xml_v5_en`,
tokenizador `Qwen/Qwen2.5-Coder-7B`, IC95% bootstrap pareado (10.000, seed 42):

| Denominador | TCR médio | IC95% | Mediana | Redução |
|---|---|---|---|---|
| **XML lógico** (definição normativa) | **6,01** | [5,96; 6,06] | 5,99 | **83,4%** |
| XML com BPMNDI (*não usar*) | 17,24 | [17,10; 17,38] | 17,26 | 94,2% |

O layout quase triplica o TCR sem acrescentar semântica. **83,4% é o número
honesto**; qualquer valor próximo de 94% no texto veio da variante com layout.

A base anterior em português dava 5,08 (80,3%). O inglês é mais compacto por
rótulo, o que explica a diferença; o número válido é o da base atual.

Reproduzir:
```
uv run --with transformers python -m src.evaluation.run_tcr \
  --source-dsl-version json_to_dsl_v10_en --xml-transpiler-version dsl_to_xml_v5_en
```

### 3.4 SA — adequação semântica (secundária, não determinística)

Único componente não verificável por código. Protocolo:

- LLM-juiz com modelo, prompt e temperatura **congelados** e versionados neste
  diretório (`judge_prompt.md`), julgando (texto-fonte, XML gerado).
- Escala e critérios fixados antes da primeira execução.
- **Checagem de concordância humana**: o autor rotula manualmente uma
  subamostra aleatória de 15 itens; reportar concordância (Cohen's κ) juiz↔humano.
  κ < 0,4 ⇒ SA é reportada como exploratória e **não** sustenta conclusão.
- SA nunca entra em métrica composta neste experimento; é reportada isolada.

### 3.5 Métricas fora da v1

**GED** — cálculo exato é NP-difícil e toda aproximação depende de um modelo de
custo que não está definido no projeto. DF-F1 já mede estrutura. Fica fora da
v1; se voltar, exige emenda com o modelo de custo explícito.

**C/D** — a sigla aparece no CLAUDE.md sem expansão registrada. Ver seção 10:
bloqueia o congelamento até ser definida ou removida.

## 4. Desenho experimental

**Conjunto de avaliação:** os 53 processos do PMo (`split='holdout'`).
Os 24 do Zenodo entram como **multi-referência** para itens PMo 25–48 (mesma
fonte), permitindo reportar ambiguidade de modelagem — não como itens extras.

**Braços** (todos sobre os mesmos 53 itens, comparação pareada):

| ID | Braço | Caminho | Papel |
|---|---|---|---|
| A1 | SOTA → XML direto | texto → XML BPMN | baseline forte, o que se faz hoje |
| A2 | SOTA → DSL → XML | texto → DSL → transpiler | isola o efeito da DSL |
| A3 | Qwen2.5-Coder-7B base → DSL | texto → DSL → transpiler | piso do modelo pequeno |
| A4 | Qwen2.5-Coder-7B SFT → DSL | texto → DSL → transpiler | a proposta da tese |

A4 depende da prioridade 5 (SFT). A1–A3 rodam antes e já sustentam a
comparação DSL vs XML direto; A4 entra como segunda rodada sob o mesmo spec.

**ProMoAI** (Kourani et al. 2024) fica como referência qualitativa de trabalho
relacionado. Reexecutá-lo está fora do escopo v1 — declarar isso no texto em vez
de comparar com números publicados sob protocolo diferente.

## 5. Critérios de aceitação

> ACs descrevem **comportamento do harness**, não resultado do experimento.
> Resultados esperados são hipóteses (seção 6.1) e não viram teste.

Cada AC tem um teste homônimo em `tests/evaluation/test_harness_spec.py`.

| ID | Critério | Teste |
|---|---|---|
| AC-1 | Roda apenas sobre `split='holdout'`; recusa (levanta erro) qualquer `sample_id` presente em `export_training()`. | `test_ac1_refuses_training_samples` |
| AC-2 | XML inválido no XSD produz linha com `xsd_valid=0` e `pme_f1=0.0` — nunca linha ausente nem exceção. | `test_ac2_invalid_xml_scores_zero` |
| AC-3 | Determinismo: duas execuções sobre as mesmas entradas produzem linhas idênticas exceto `created_at`. | `test_ac3_rerun_is_deterministic` |
| AC-4 | TCR usa XML **sem** BPMNDI; XML com layout no mesmo processo dá TCR idêntico. | `test_ac4_tcr_ignores_layout` |
| AC-5 | PME-F1 delega a `topology.compare()` sem reimplementar a projeção. | `test_ac5_pme_delegates_to_topology` |
| AC-6 | Falha de parse da DSL é registrada como `parse_ok=0` e **não** dispara retry no número principal. | `test_ac6_no_silent_retry` |
| AC-7 | Cada linha grava `arm`, `model_id`, `prompt_version`, `spec_commit`, permitindo rastrear o resultado até este documento. | `test_ac7_provenance_columns_present` |
| AC-8 | Reexecução parcial substitui as linhas do par (braço, versão) em vez de duplicar — mesmo contrato de `run_topology.py`. | `test_ac8_rerun_replaces_rows` |

## 6. Protocolo experimental (pré-registro)

### 6.1 Hipóteses

- **H1 (primária):** A2 ≥ A1 em PME-F1 — gerar DSL não perde fidelidade frente a
  gerar XML direto, com o mesmo modelo.
- **H2:** A2 > A1 em XSD-Val — a transpilação determinística garante validade que
  a geração direta não garante.
- **H3:** A4 ≥ A2 em PME-F1 — o modelo pequeno finetunado alcança o SOTA
  prompted, a custo muito menor.
- **H4 (descritiva):** TCR ≥ 2 nos braços com DSL.

Resultado contrário a H1/H3 é **resultado publicável** e deve ser reportado como
tal. O spec existe para tornar esse desfecho reportável em vez de tentador de
esconder.

### 6.2 Parâmetros congelados

| Parâmetro | Valor |
|---|---|
| Temperatura | 0,0 (reduz variância; **não** garante determinismo — [ADR 0003](../adr/0003-nao-determinismo-temperatura-zero.md)) |
| Amostras por item (k) | ⚠️ **em aberto** — `k=1` foi falsificado pelo ADR 0003; fixar antes do congelamento |
| Seed | 42 onde aplicável |
| Retries de parse | 0 no número principal |
| `max_tokens` | _(preencher antes do congelamento)_ |
| Modelo SOTA (A1/A2) | _(fixar id exato e data de acesso)_ |
| Prompts | versionados em `specs/003-eval-harness/prompts/`, hash no banco |

Uma execução secundária com k=5, T=0,7 pode ser reportada como análise de
variância — declarada como secundária, nunca substituindo a principal.

### 6.3 Análise

- Comparações **pareadas** por item (mesmos 53 em todos os braços).
- Teste: Wilcoxon signed-rank pareado, α = 0,05, sobre a métrica primária apenas.
- IC95% por bootstrap pareado (10.000 reamostragens, seed 42).
- Correção para múltiplas comparações entre braços: Holm.
- n = 53 é pequeno: reportar tamanho de efeito e IC, não só p-valor.

### 6.4 Desvios

Qualquer desvio do protocolo durante a execução é registrado na seção 9 com
data, motivo e se ocorreu antes ou depois de observar resultados.

## 7. Invariantes

1. **Holdout nunca entra em treino.** Vale para A4 e para todo SFT futuro.
2. Comparação XML↔XML é sempre topológica + XSD, **nunca igualdade textual**.
3. Resultados vão para `data/dataset.db`, sem JSONL intermediário.
4. Todo número que aparecer na tese tem uma linha correspondente no banco.

## 8. Fora de escopo (v1)

- GED (seção 3.5) · Reexecução do ProMoAI · Constrained decoding como braço
- Qualidade visual do layout como métrica (BPMNDI é para inspeção humana)
- GRPO (prioridade 6, opcional)

## 9. Emendas e desvios

_(vazio até o congelamento)_

| Data | Item alterado | Motivo | Antes/depois de ver resultados |
|---|---|---|---|

## 10. Questões em aberto — **bloqueiam o congelamento**

- [ ] **C/D**: expandir a sigla e dar definição operacional, ou remover do
      CLAUDE.md. Sem isso a lista de métricas da tese fica inconsistente.
- [ ] Fixar o id exato do modelo SOTA para A1/A2 e a data de acesso.
- [ ] Definir escala e prompt do LLM-juiz (SA) — `judge_prompt.md`.
- [ ] Definir `max_tokens` por braço (A1 gera XML longo; limite curto demais
      vira truncamento que se confunde com erro de modelo).
- [ ] Confirmar a regra de multi-referência do Zenodo: melhor score entre
      referências, ou média?
- [ ] **Fixar `k`** e o teste estatístico correspondente, dado o não determinismo
      medido no [ADR 0003](../adr/0003-nao-determinismo-temperatura-zero.md).
      Com k>1 a unidade de análise passa a ser a média por item.

## 11. Rastreabilidade

| Artefato | Caminho |
|---|---|
| Este spec | `specs/003-eval-harness/spec.md` |
| Testes de AC | `tests/evaluation/test_harness_spec.py` |
| Métrica topológica | `src/evaluation/topology.py` |
| Runner existente (padrão a seguir) | `src/evaluation/run_topology.py` |
| Harness novo | `src/evaluation/run_benchmark.py` _(a criar)_ |
| Migração da tabela | `src/data/migrations/create_benchmark_eval.py` _(a criar)_ |
| Constituição do projeto | `CLAUDE.md` |

# Spec 005 — Estrutura de código e autoridade dos dados

| Campo | Valor |
|---|---|
| Status | **ATIVA** |
| Tipo | Refatoração (não é experimento) |
| Precede | regeneração da [spec 004](../004-camada-de-dados/spec.md) — senão os dados migram duas vezes |

> Escopo deliberadamente estreito. "Limpar o código" é atividade sem fim;
> esta spec lista o que está concretamente atrapalhando debugar e para aí.
> Reorganização global de pastas está **fora**.

---

## 1. Diagnóstico

43 arquivos Python, profundidade máxima 4. Os problemas reais medidos:

| # | Problema | Evidência |
|---|---|---|
| E1 | `manipulation/` não carrega significado | `src/data/manipulation/llm/…` e `…/deterministic/…` — nível morto |
| E2 | Runners não se distinguem de bibliotecas pelo nome | `run_json_to_dsl.py` e `run_topology.py` seguem convenção; `dsl_to_xml.py` (393 linhas, batch job) e `preprocess.py` não |
| E3 | Autoridade dos dados indefinida | `samples.dsl` / `bpmn_json` / `xml` NULL em 1021/1021 enquanto os `*_runs` têm tudo; não está claro quem é fonte da verdade |
| E4 | `preprocess` não é regerável | filtra retomada por `stage`, sem `prompt_version` — com prompt novo pularia tudo como concluído (`preprocess.py:69-75`) |

Não há duplicação de lógica de transpilação: `deterministic/dsl_to_xml.py`
delega para `src.transpiler.transpile()` corretamente. O problema é nomenclatura,
não arquitetura.

## 2. Escopo

1. **Achatar** `src/data/manipulation/{llm,deterministic}/` → `src/data/{llm,deterministic}/`
   e `src/data/ingestion/{dataset,web}/` → `src/data/ingestion/`.
2. **Padronizar** `run_*.py` para todo job de lote; bibliotecas ficam sem prefixo.
3. **Definir autoridade**: `samples` passa a ser o estado atual materializado
   (`dsl`, `xml`, `bpmn_json`, `parse_ok`, `xsd_ok`); as tabelas `*_runs`
   permanecem histórico de execução. Escrever o materializador.
4. **Corrigir E4**: incluir `prompt_version` no filtro de retomada de `preprocess`.

## 3. Critérios de aceitação

| ID | Critério | Verificação |
|---|---|---|
| AC-1 | Suíte inteira passa após a movimentação. | `uv run pytest` |
| AC-2 | Nenhum import quebrado ou caminho antigo remanescente. | `rg "data\.manipulation\|ingestion\.(dataset\|web)"` sem resultados |
| AC-3 | Profundidade máxima de `src/` ≤ 3. | `find src -name '*.py' \| awk -F/ 'NF>4'` vazio |
| AC-4 | Todo job de lote tem prefixo explícito — `run_` (processamento) ou `import_` (ingestão); bibliotecas não têm. | inspeção da listagem de `src/` |
| AC-5 | `samples` materializado: para todo run `succeeded`, a coluna correspondente está preenchida. | `test_ac5_samples_materialized` |
| AC-6 | `preprocess` com `prompt_version` nova reprocessa em vez de pular. | `test_ac6_preprocess_regenerates_on_new_prompt` |
| AC-7 | Comandos do CLAUDE.md/README atualizados para os novos caminhos. | conferência manual |

## 3.1 Emenda a AC-4 (antes da execução)

O critério original exigia `run_` para todo job de lote. Os importadores já
seguiam a convenção `import_*`, igualmente explícita e documentada no CLAUDE.md;
renomeá-los seria churn sem ganho de legibilidade. AC-4 passou a aceitar os dois
prefixos. Decidido antes de executar, não para acomodar resultado.

`clean_handbook.py` virou `import_handbook.py` — era o único da ingestão fora da
convenção.

## 4. Fora de escopo

- Redesenho do schema do banco (o padrão tabela-por-estágio é adequado; o que
  faltava era autoridade, não desenho)
- Reorganizar `src/dsl`, `src/transpiler`, `src/evaluation` — já estão coerentes
- Camada de abstração sobre SQLite, DI, ou qualquer generalização especulativa

## 5. Risco

Movimentação de arquivos com regeneração pendente. Mitigação: **executar esta
spec inteira e ver a suíte verde antes de disparar qualquer LLM.**

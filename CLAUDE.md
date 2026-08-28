# Semantic Compression TCC

## Objetivo
Protocolo de compressão semântica para geração de markup XML via LLMs.
Validação empírica com BPMN 2.0. Projeto de pesquisa acadêmica (TCC).

## Stack
- Python 3.12
- uv (gerenciamento de deps)
- Lark (parser EBNF)
- lxml (manipulação XML + validação XSD)
- pytest
- ruff
- networkx (layout hierárquico simplificado quando necessário)

## Regras
- Código de pesquisa: priorizar clareza e reprodutibilidade sobre abstração.
- Sem classes desnecessárias. Funções e módulos simples primeiro.
- Sem dependências extras sem justificativa.
- Cada componente deve ser testável isoladamente.
- Transpiler deve ter 100% de cobertura nos testes de validação XSD.
- Atualizar README quando comandos ou setup mudarem.

## Estrutura
- src/dsl/: gramática EBNF, parser, AST
- src/transpiler/: DSL → BPMN 2.0 XML (parsing, enriquecimento, serialização)
- src/data/: pipeline de dados (limpeza, importação, banco)
- src/training/: scripts de SFT e GRPO (fase posterior)
- src/evaluation/: métricas (TCR, DF-F1, XSD-Val). SA e GED fora da v1; ver spec 003 §3.4-3.5
- data/raw/: datasets brutos (pmo/, pet/, zenodo/, gitlab-handbook/)
- data/dataset.db: SQLite com todos os dados — views por source__stage
- configs/: hiperparâmetros e configurações de experimentos
- experiments/: resultados e checkpoints
- tests/: testes unitários por componente
- docs/registro-tecnico.md: diário de engenharia — decisões, achados, bugs e,
  sobretudo, **o que não foi verificado**. Ler antes de auditar o projeto.
- docs/ideias-pos-defesa.md: ideias de produto/artefato para depois de 30/11.
  Não confundir com Trabalhos Futuros da monografia, que são perguntas de pesquisa.

## Comandos
- instalar: uv sync
- test: uv run pytest
- lint: uv run ruff check .
- format: uv run ruff format .
- parse: uv run python -m src.dsl.parser <arquivo.bpmndsl>
- transpile: uv run python -m src.transpiler.main <arquivo.bpmndsl> -o output.bpmn
- json -> xml: uv run python -m src.data.deterministic.json_to_xml input.json -o output.bpmn
- json -> xml lógico: uv run python -m src.data.deterministic.json_to_xml input.json --no-layout
- importar handbook: uv run python -m src.data.ingestion.import_handbook [--min-score 40]
- importar pmo: uv run python -m src.data.ingestion.import_pmo
- importar pet: uv run python -m src.data.ingestion.import_pet
- importar zenodo: uv run python -m src.data.ingestion.import_zenodo
- materializar samples: uv run python -m src.data.run_materialize [--dry-run]
- carregar gold pmo: uv run python -m src.data.ingestion.import_gold_pmo [--dry-run]
- carregar refs zenodo: uv run python -m src.data.ingestion.import_gold_zenodo [--dry-run]
- TCR do corpus: uv run --with transformers python -m src.evaluation.run_tcr
- TCR por braço: uv run --with transformers python -m src.evaluation.run_tcr --all-arms
- criar tabela do benchmark: uv run python -m src.data.migrations.create_benchmark_eval
- planejar braço: uv run python -m src.evaluation.run_benchmark --arm A2 --dry-run
- executar braço: uv run python -m src.evaluation.run_benchmark --arm A2 --execute
- repontuar sem gerar: uv run python -m src.evaluation.run_benchmark --arm A2 --rescore
- análise estatística: uv run python -m src.evaluation.run_analysis
- tabelas complementares (condicional, MF-F1, teto): uv run python -m src.evaluation.run_tabelas
- instalar deps de inferência local (A3/A4): uv sync --extra training
- diagnóstico de VRAM: uv run python -c "from src.evaluation.local_model import vram_report; print(vram_report())"

## Pipeline de dados (augmentation)

### Seeds disponíveis em data/dataset.db (base ativa = 1021; 26 degradadas excluídas)
| source | stage | split | n | descrição |
|---|---|---|---|---|
| gitlab_handbook | curated | sft | 728 | seções limpas com score procedural ≥ 4 |
| gitlab_handbook | curated | grpo | 172 | seções lineares (score 4+, sem decisões/atores) |
| pmo | descriptions | holdout | 53 | PMo Benchmark — holdout de avaliação, NUNCA treino |
| pet | descriptions | sft | 44 | PET Dataset — documentos com tokens reconstituídos |
| zenodo | descriptions | holdout | 24 | Mangler et al. 2023 — mesma fonte do PMo 25–48; fora de treino para não contaminar o holdout |

Semântica do split: `sft`/`grpo` = treino; `holdout` = só avaliação
(`Database.export_training` filtra por split). Subset SFT de alta confiança:
766 pares com `df_exact=1` no eixo 2 (de 772 sft; v8).

### Fluxo de augmentation
```
seeds (raw text)
    → Kimi K2.6 (pré-processamento estruturado, Ollama Cloud)
    → DeepSeek V4 → canonical BPMN JSON (elements, flows, gateways)
    → json_to_dsl.py (v8) → BPMN-DSL string
    → dsl_to_xml.py / transpiler.xml → BPMN XML lógico
    → transpiler.layout.add_layout → BPMN XML com BPMNDI
    → par (text, dsl) inserido no DB (bpmn_json + dsl columns)
    → SFT (+ GRPO opcional)
```

Baseline determinístico direto:
```
canonical BPMN JSON
    → json_to_xml.py
    → BPMN XML lógico + BPMNDI determinístico
```

Comparações entre JSON→XML e JSON→DSL→XML devem usar equivalência topológica
(`src.evaluation.topology`) e validação XSD, não igualdade textual do XML.

### Classificação BPMN das seções
- **ideal**: steps + decisions + actors → SFT
- **good**: steps + (decisions OR actors) → SFT
- **linear**: steps only → GRPO
- **marginal**: sem steps → descartado

## Estado e ordem de prioridade (2026-07-05 — detalhe em TODO.md)

Feito: gramática+parser (Lark), **json_to_dsl v8** (1021/1021, zero arestas perdidas),
dsl_to_xml v3 (XSD 1021/1021), eixo 2 de avaliação (**1015/1021 exatos, F1 0.9999**),
JSON→XML direto com BPMNDI determinístico e layout comum pós-XML.

1. Commitar o eixo 2 + fix v8 (arquivos untracked/modificados na branch)
2. Bug das arestas de convergência — CORRIGIDO em 2026-07-04 (json_to_dsl_v8,
   891→1015 exatos, zero regressões; resíduo = 6 casos de arestas extras, leve).
3. Harness de avaliação + baselines (SOTA→XML direto, SOTA→DSL, Qwen→DSL) vs gold PMo
4. Escrever capítulo de Metodologia — FEITO (introdução + metodologia no template oficial)
5. SFT (Qwen2.5-Coder-7B, QLoRA 4-bit) sobre o pool exato: 766 pares
6. GRPO — OPCIONAL, fora do escopo mínimo do TCC (material para artigo futuro)
7. Publicar dataset E modelo (adapter LoRA + model card) no HuggingFace
8. Melhorar layout/BPMNDI se necessário para inspeção visual; métricas continuam independentes disso

## Convenções
- Jobs de lote sobre o banco têm prefixo explícito: `run_*` (processamento) ou
  `import_*` (ingestão). Bibliotecas não têm prefixo. `src/` tem profundidade máxima 3.
- Autoridade dos dados: `samples` é o estado atual materializado; as tabelas
  `*_runs` são histórico de execução. Ver `src/data/run_materialize.py`.
- Nomes de variáveis e funções em inglês, comentários podem ser pt-br.
- Um arquivo por responsabilidade. Não crescer módulos além de ~200 linhas.
- Testes espelham a estrutura de src/.
- Commits com prefixo: feat:, fix:, test:, docs:, refactor:

## Contexto de pesquisa
- **PMo Dataset**: 55 processos (53 ativos) de Brissard et al. (2025). **split='holdout' — só avaliação, nunca treino.**
- **PET Dataset**: 44 documentos de processo ativos. Seeds SFT.
- **Zenodo/Mangler**: 24 descrições originais (mesma fonte do PMo 25–48, sem pré-processamento). **split='holdout'** — em treino contaminaria 24 dos 55 itens do PMo. Útil na avaliação: multi-referência com score de especialista (ambiguidade de modelagem).
- **GitLab Handbook**: 728 seções curadas (SFT) + 172 (GRPO). Principal fonte de volume: **95,3% do conjunto de treino** (900 de 944) — medido em 2026-08-09. Ameaça à validade externa: o modelo é treinado quase só no estilo de uma empresa e avaliado contra o PMo, que é outro domínio. Reconhecer explicitamente na monografia; mais dados só ajudam se forem de **fontes diferentes**, não de mais handbook.
- **MaD Dataset**: 30k pares de Li et al. (2023). Baixa variabilidade — deprioritizado; pode ser usado como fallback se volume for insuficiente.
- **Related work chave**: ProMoAI (Kourani et al. 2024, IJCAI demo; `kourani2024promoai` no .bib) — LLM prompted → POWL → BPMN. Posicionar a tese explicitamente contra ele: DSL própria com compressão medida (TCR) + modelo pequeno finetunado + recompensa verificável.
- **Constrained decoding**: contra-argumento a endereçar na tese; como experimento/baseline fica para artigo futuro derivado.
- **Modelo base**: Qwen2.5-Coder-7B-Instruct (Apache 2.0) — variante Instruct, não a base pura; ver spec 003 §6.2
- **Função de recompensa GRPO (etapa OPCIONAL)**: r_sint(0.35) + r_sem(0.30) + r_topo(0.25) + r_comp(0.10). r_sem é o componente frágil (não verificável por código).
- **Publicação**: dataset (quando 100% populado) e modelo SFT no HuggingFace — não existe base equivalente aberta.

## Decisões de design

- **Parser**: lark (EBNF declarativo, não parser manual)
- **XML**: lxml (validação XSD embutida via `lxml.etree`)
- **JSON→XML direto**: `src.data.deterministic.json_to_xml`, reutilizando `load_llm`, IDs XML seguros e validação XSD.
- **Layout**: pós-processador comum em `src.transpiler.layout.add_layout(xml_text)`, com BPMNDI determinístico, remoção simples de ciclos via DFS, ranking longest-path e espaçamento fixo.
- **Training**: LoRA 4-bit com `trl.GRPOTrainer`
- **Schema**: XSD oficial BPMN 2.0 em `schemas/bpmn20.xsd`
- **Storage**: SQLite (`data/dataset.db`) com views `{source}__{stage}` simulando schemas. Sem arquivos JSONL intermediários.
- **Idioma dos artefatos**: rótulos de JSON/DSL/BPMN em **inglês** (a monografia segue em português). Ver [ADR 0001](specs/adr/0001-idioma-dos-artefatos.md).
- **Specs**: `specs/NNN-nome/spec.md` para entregáveis; `specs/adr/` para decisões de alcance amplo. Critérios de aceitação são ligados a testes homônimos.

## Fora de escopo

- Interface web ou CLI elaborada
- Containerização (Docker)
- Tracking de experimentos (MLflow, W&B)
- Type annotations completas / mypy

## Limitações computacionais (Para testes)

- Placa de vídeo: RTX 2080 TI, 11 Gb de VRAM (10,6 GiB utilizáveis)
- Processador: I9 - 9900
- Memória RAM: 24 Gb
- Armazenamento: SSD 1 Tb

## Limitações computacionais (Para treinamento final)

- Usará recurso computacional maior em nuvem (h100 ou derivados melhores)

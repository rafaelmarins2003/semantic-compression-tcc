# Semantic Compression TCC

Projeto acadêmico para avaliar compressão semântica em geração de BPMN 2.0:
texto em linguagem natural -> representação intermediária -> BPMN-DSL -> XML BPMN.

## Setup

```bash
uv sync
uv run pytest
uv run ruff check .
```

## Pipeline de Dados

Os artefatos ficam em `data/`:

- `data/raw/`: datasets brutos.
- `data/dataset.db`: SQLite normalizado com `samples` e `generations`.

Os scripts ficam em `src/data/`:

- `src/data/ingestion/dataset/`: importação de datasets públicos.
- `src/data/ingestion/web/`: coleta e ingestão de fontes web.
- `src/data/manipulation/llm/`: transformações com LLM.
- `src/data/manipulation/deterministic/`: conversões determinísticas entre JSON, DSL e XML.

Comandos principais:

```bash
uv run python -m src.data.ingestion.dataset.import_pmo
uv run python -m src.data.ingestion.dataset.import_pet
uv run python -m src.data.ingestion.dataset.import_zenodo
uv run python -m src.data.ingestion.web.clean_handbook
uv run python -m src.data.manipulation.llm.preprocess --provider gemini --limit 5
uv run python -m src.data.manipulation.deterministic.json_to_xml input.json -o output.bpmn
uv run python -m src.data.manipulation.deterministic.json_to_xml input.json --no-layout
```

O conversor direto `json_to_xml` gera BPMN XML com BPMNDI/layout determinístico
por padrão. Use `--no-layout` apenas quando precisar inspecionar o XML lógico.

Nota metodológica: PMo deve ser tratado como holdout de avaliação, não como treino.

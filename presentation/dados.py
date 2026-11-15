"""Extrai do banco e do transpilador os dados reais usados nos slides.

Uso (a partir da raiz do TCC):
    uv run python internal_tests/apresentacao/dados.py

Gera src/js/data.js com:
- o desfecho de cada uma das 138 gerações (46 itens x 3 repetições) por braço;
- o XML que o transpilador real produz para o exemplo do Código 1 da monografia.

As contagens são conferidas contra as tabelas da monografia (validade e causas
de invalidade). Se o banco mudar, o script falha em vez de gerar um slide errado.
"""

import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from src.data.db import LEAKED_HOLDOUT  # noqa: E402
from src.transpiler.xml import transpile  # noqa: E402
from src.transpiler.xsd import validate_bpmn_xsd  # noqa: E402

DB = ROOT / "data" / "dataset.db"
OUT = HERE / "src" / "js" / "data.js"

# Nome no banco -> nome na monografia.
ARMS = {
    "A1": "A1",
    "A1g": "A1g",
    "A2": "A2",
    "A2g": "A2g",
    "A3": "A3",
    "A3m": "A3m",
    "A4": "A4",
    "X-a2r": "A2r",
}

# Códigos de desfecho: v válida; u referência não declarada; m referência fora
# de posição; s outra sintaxe; o bloco aberto; t truncada; x XML fora do XSD.
EXPECTED = {
    # braço: (válidas, u, m, s, o, t)  -- Tabelas 5.1 e 5.3 da monografia
    "A2": (86, 26, 12, 14, 0, 0),
    "A2g": (73, 21, 20, 23, 1, 0),
    "A2r": (120, 8, 0, 10, 0, 0),
    "A3": (81, 0, 0, 57, 0, 0),
    "A3m": (0, 0, 0, 57, 0, 81),
    "A4": (120, 12, 0, 0, 6, 0),
}
EXPECTED_VALID_XML = {"A1": 135, "A1g": 129}

EXAMPLE_DSL = """process "Order Processing with Retry" {
  start
  -> service "Fetch data" #fetch
  -> service "Validate"
  -> xor "Valid?" {
    [yes] -> service "Process" -> end
    [no]  -> xor "Retry?" {
               [yes] -> #fetch
               [no]  -> end:error "Invalid"
             }
  }
}"""


def outcome(row):
    if row["xsd_valid"]:
        return "v", ""
    if row["truncated"]:
        return "t", ""
    err = row["parse_error"] or ""
    if err.startswith("ValueError: Unresolved DSL ref"):
        return "u", err.rsplit(" ", 1)[-1]
    if "No terminal matches '#'" in err:
        return "m", ""
    if err.startswith("UnexpectedEOF"):
        return "o", ""
    if row["parse_ok"] is None and row["output_xml"]:
        return "x", ""  # braço de XML: saída completa, recusada pelo XSD
    return "s", ""


def item_key(sample_id):
    return int(sample_id.split("_")[1])


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT arm, sample_id, rep, truncated, parse_ok, parse_error, xsd_valid, output_xml "
        "FROM benchmark_eval WHERE sample_id LIKE 'pmo_%'"
    ).fetchall()

    items = sorted(
        {r["sample_id"] for r in rows if r["sample_id"] not in LEAKED_HOLDOUT}, key=item_key
    )
    assert len(items) == 46, len(items)
    pos = {s: i for i, s in enumerate(items)}

    runs, notes = {}, {}
    for db_arm, arm in ARMS.items():
        cells = ["?"] * (46 * 3)
        notes[arm] = {}
        for r in rows:
            if r["arm"] != db_arm or r["sample_id"] not in pos:
                continue
            idx = pos[r["sample_id"]] * 3 + (r["rep"] - 1)
            code, note = outcome(r)
            cells[idx] = code
            if note:
                notes[arm][idx] = note
        assert "?" not in cells, arm
        runs[arm] = "".join(cells)

    for arm, exp in EXPECTED.items():
        got = tuple(runs[arm].count(c) for c in "vumsot")
        assert got == exp, (arm, got, exp)
    for arm, exp in EXPECTED_VALID_XML.items():
        assert runs[arm].count("v") == exp, (arm, runs[arm].count("v"))

    xml = transpile(EXAMPLE_DSL)
    assert validate_bpmn_xsd(xml) == [], "o exemplo deixou de passar no XSD"
    assert len(EXAMPLE_DSL) == 286 and len(xml.strip()) + 1 == 1833, (len(EXAMPLE_DSL), len(xml))

    data = {
        "itens": items,
        "bracos": runs,
        "notas": notes,
        "exemplo": {"dsl": EXAMPLE_DSL, "xml": xml.strip()},
    }
    OUT.write_text(
        "// GERADO por dados.py a partir de data/dataset.db e do transpilador. Não editar.\n"
        "window.DADOS = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )
    for arm, cells in runs.items():
        print(f"{arm:4s} válidas {cells.count('v'):3d}/138  {cells.count('v') / 1.38:5.1f}%")
    print(f"exemplo: DSL {len(EXAMPLE_DSL)} caracteres, XML {len(xml.strip()) + 1} caracteres")
    print(f"escrito: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

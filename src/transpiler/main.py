"""CLI for BPMN-DSL to BPMN XML transpilation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lark.exceptions import UnexpectedInput

from src.transpiler.xml import transpile_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Transpile BPMN-DSL to BPMN XML.")
    parser.add_argument("input", help="Input .bpmndsl file")
    parser.add_argument("-o", "--output", help="Output .bpmn file")
    args = parser.parse_args(argv)

    try:
        xml = transpile_file(args.input)
    except FileNotFoundError:
        print(f"file not found: {args.input}", file=sys.stderr)
        return 1
    except UnexpectedInput as exc:
        print(f"parse error in {args.input}:\n{exc}", file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(xml, encoding="utf-8")
    else:
        print(xml)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

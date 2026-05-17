"""BPMN-DSL parser.

Wraps Lark to parse BPMN-DSL text into a parse tree.
The tree is consumed directly by the transpiler — no separate AST step.

Usage as module:
    from src.dsl.parser import parse, parse_file

    tree = parse('process "P" { start -> task "A" -> end }')
    tree = parse_file("examples/simple.bpmndsl")

Usage as CLI:
    uv run python -m src.dsl.parser examples/simple.bpmndsl
"""

from __future__ import annotations

import sys
from pathlib import Path

from lark import Lark, Tree
from lark.exceptions import UnexpectedInput

_GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"

# Lazy-initialized singleton parser (Earley + dynamic lexer).
# Earley handles the optional and nested constructs cleanly at research scale.
_parser: Lark | None = None


def _get_parser() -> Lark:
    global _parser
    if _parser is None:
        grammar = _GRAMMAR_PATH.read_text(encoding="utf-8")
        _parser = Lark(grammar, parser="earley", lexer="dynamic", ambiguity="resolve")
    return _parser


def parse(text: str) -> Tree:
    """Parse BPMN-DSL source text; raise UnexpectedInput on syntax errors."""
    return _get_parser().parse(text)


def parse_file(path: str | Path) -> Tree:
    """Parse a BPMN-DSL file; raise UnexpectedInput on syntax errors."""
    return parse(Path(path).read_text(encoding="utf-8"))


def unquote(token) -> str:
    """Strip surrounding double-quotes from an ESCAPED_STRING token value."""
    s = str(token)
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.dsl.parser <file.bpmndsl>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    try:
        tree = parse_file(path)
        print(tree.pretty())
    except UnexpectedInput as exc:
        print(f"parse error in {path}:\n{exc}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"file not found: {path}", file=sys.stderr)
        sys.exit(1)

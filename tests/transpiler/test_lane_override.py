from lxml import etree

from src.transpiler.xml import transpile

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}


def _lanes(dsl: str) -> list[tuple[str, list[str]]]:
    """(nome da lane, nomes dos nós), uma entrada por elemento <lane>."""
    root = etree.fromstring(transpile(dsl).encode("utf-8"))
    nomes = {el.get("id"): el.get("name") for el in root.iter() if el.get("name")}
    return [
        (lane.get("name"), [nomes.get(ref.text) for ref in lane.findall("bpmn:flowNodeRef", NS)])
        for lane in root.iter("{%s}lane" % NS["bpmn"])
    ]


def test_lane_prop_overrides_enclosing_lane():
    lanes = dict(
        _lanes(
            'process "P" { @lane "Clerk" {'
            ' start -> task "Register" -> task "Approve" (lane="Manager") -> end "Done" } }'
        )
    )
    assert lanes["Manager"] == ["Approve"]
    assert "Approve" not in lanes["Clerk"]


def test_repeated_lane_block_yields_one_lane():
    lanes = _lanes(
        'process "P" {'
        ' @lane "A" { start -> task "One" }'
        ' @lane "B" { -> task "Two" }'
        ' @lane "A" { -> task "Three" -> end "Done" } }'
    )
    assert lanes == [("A", ["start", "One", "Three", "Done"]), ("B", ["Two"])]

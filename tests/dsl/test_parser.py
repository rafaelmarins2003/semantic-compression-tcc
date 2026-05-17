"""Tests for the BPMN-DSL parser (grammar + lark integration)."""

import pytest
from lark import Tree
from lark.exceptions import UnexpectedInput

from src.dsl.parser import parse, parse_file, unquote

# ── Helpers ───────────────────────────────────────────────────────────────────


def find_all(tree: Tree, rule: str) -> list[Tree]:
    """Collect all subtrees with the given rule name."""
    return list(tree.find_data(rule))


def process_name(tree: Tree) -> str:
    """Return the name of the first process in the tree."""
    proc = next(tree.find_data("process"))
    return unquote(proc.children[0])


# ── Basic structure ───────────────────────────────────────────────────────────


def test_parse_returns_tree():
    tree = parse('process "P" { start -> task "A" -> end }')
    assert isinstance(tree, Tree)
    assert tree.data == "start"


def test_process_name():
    tree = parse('process "My Process" { start -> end }')
    assert process_name(tree) == "My Process"


def test_multiple_processes():
    src = """
    process "P1" { start -> end }
    process "P2" { start -> task "A" -> end }
    """
    tree = parse(src)
    procs = find_all(tree, "process")
    assert len(procs) == 2


# ── Tasks ─────────────────────────────────────────────────────────────────────


def test_simple_linear_task_sequence():
    tree = parse('process "P" { start -> task "A" -> task "B" -> task "C" -> end }')
    tasks = find_all(tree, "task")
    assert len(tasks) == 3
    names = [unquote(t.children[1]) for t in tasks]
    assert names == ["A", "B", "C"]


def test_task_types():
    src = """
    process "P" {
      start ->
      task "Generic" ->
      service "Svc" ->
      user "Usr" ->
      script "Scr" ->
      manual "Man" ->
      end
    }
    """
    tree = parse(src)
    tasks = find_all(tree, "task")
    types = [str(t.children[0]) for t in tasks]
    assert types == ["task", "service", "user", "script", "manual"]


def test_task_with_props():
    tree = parse('process "P" { start -> task "Pay" (performer="finance") -> end }')
    props = find_all(tree, "props")
    assert len(props) == 1
    # props exist and have one prop
    assert len(list(tree.find_data("prop"))) == 1


# ── Events ────────────────────────────────────────────────────────────────────


def test_plain_start_and_end():
    tree = parse('process "P" { start -> end }')
    starts = find_all(tree, "start_event")
    ends = find_all(tree, "end_event")
    assert len(starts) == 1
    assert len(ends) == 1


def test_typed_start_event():
    tree = parse('process "P" { start:message("order-in") -> task "A" -> end }')
    start = next(tree.find_data("start_event"))
    spec = next(start.find_data("event_spec"))
    assert str(spec.children[0]) == "message"
    assert unquote(spec.children[1]) == "order-in"


def test_typed_end_event():
    tree = parse('process "P" { start -> task "A" -> end:error("payment-failed") }')
    end = next(tree.find_data("end_event"))
    spec = next(end.find_data("event_spec"))
    assert str(spec.children[0]) == "error"


def test_catch_and_throw_events():
    src = """
    process "P" {
      start ->
      catch:timer("PT1H") ->
      task "A" ->
      throw:message("done") ->
      end
    }
    """
    tree = parse(src)
    assert len(find_all(tree, "catch_event")) == 1
    assert len(find_all(tree, "throw_event")) == 1


def test_all_event_kinds():
    kinds = ["timer", "message", "error", "signal", "escalation"]
    for kind in kinds:
        src = f'process "P" {{ start:{kind}("x") -> end }}'
        tree = parse(src)
        spec = next(tree.find_data("event_spec"))
        assert str(spec.children[0]) == kind


# ── XOR Gateway ───────────────────────────────────────────────────────────────


def test_xor_gateway_branch_count():
    src = """
    process "P" {
      start ->
      xor "Decision" {
        [condition A] -> task "Path A"
        [condition B] -> task "Path B"
        [default] -> task "Default Path"
      } ->
      end
    }
    """
    tree = parse(src)
    xors = find_all(tree, "xor_gw")
    assert len(xors) == 1
    branches = find_all(xors[0], "branch")
    assert len(branches) == 3


def test_xor_branch_conditions():
    src = """
    process "P" {
      start ->
      xor "Q" {
        [x > 10] -> task "High"
        [default] -> task "Low"
      } ->
      end
    }
    """
    tree = parse(src)
    branches = find_all(tree, "branch")
    conditions = [str(b.children[0]).strip() for b in branches]
    assert "x > 10" in conditions
    assert "default" in conditions


def test_xor_gateway_optional_name():
    # Gateway name is optional
    src = 'process "P" { start -> xor { [c] -> task "A" [default] -> task "B" } -> end }'
    tree = parse(src)
    assert len(find_all(tree, "xor_gw")) == 1


def test_nested_xor_gateways():
    src = """
    process "P" {
      start ->
      xor "Outer" {
        [a] -> xor "Inner" {
          [a1] -> task "A1"
          [a2] -> task "A2"
        }
        [default] -> task "B"
      } ->
      end
    }
    """
    tree = parse(src)
    xors = find_all(tree, "xor_gw")
    assert len(xors) == 2


# ── AND Gateway ───────────────────────────────────────────────────────────────


def test_and_gateway_two_branches():
    src = """
    process "P" {
      start ->
      and "Parallel" {
        task "Branch A",
        task "Branch B"
      } ->
      end
    }
    """
    tree = parse(src)
    ands = find_all(tree, "and_gw")
    assert len(ands) == 1
    branches_root = next(ands[0].find_data("and_branches"))
    # and_branches children are seq nodes
    seqs = [c for c in branches_root.children if isinstance(c, Tree) and c.data == "seq"]
    assert len(seqs) == 2


def test_and_gateway_three_branches():
    src = """
    process "P" {
      start ->
      and {
        task "A",
        task "B" -> task "C",
        task "D"
      } ->
      end
    }
    """
    tree = parse(src)
    branches_root = next(tree.find_data("and_branches"))
    seqs = [c for c in branches_root.children if isinstance(c, Tree) and c.data == "seq"]
    assert len(seqs) == 3


def test_and_with_nested_xor():
    src = """
    process "P" {
      start ->
      and "Parallel" {
        task "A" -> xor "Q" {
          [yes] -> task "B"
          [no]  -> task "C"
        },
        task "D"
      } ->
      end
    }
    """
    tree = parse(src)
    assert len(find_all(tree, "and_gw")) == 1
    assert len(find_all(tree, "xor_gw")) == 1


# ── OR Gateway ────────────────────────────────────────────────────────────────


def test_or_gateway():
    src = """
    process "P" {
      start ->
      or "Inclusive" {
        [cond1] -> task "A"
        [cond2] -> task "B"
      } ->
      end
    }
    """
    tree = parse(src)
    assert len(find_all(tree, "or_gw")) == 1
    assert len(find_all(tree, "branch")) == 2


# ── Subprocess ────────────────────────────────────────────────────────────────


def test_subprocess():
    src = """
    process "P" {
      start ->
      subprocess "Sub Process" {
        task "Inner A" -> task "Inner B"
      } ->
      end
    }
    """
    tree = parse(src)
    subs = find_all(tree, "subprocess")
    assert len(subs) == 1
    assert unquote(subs[0].children[0]) == "Sub Process"
    tasks = find_all(subs[0], "task")
    assert len(tasks) == 2


def test_call_activity():
    tree = parse('process "P" { start -> call "Sub Process" -> end }')
    calls = find_all(tree, "call_activity")
    assert len(calls) == 1
    assert unquote(calls[0].children[0]) == "Sub Process"


# ── Annotations ───────────────────────────────────────────────────────────────


def test_note():
    tree = parse('process "P" { start -> note "This is a note" -> task "A" -> end }')
    notes = find_all(tree, "note")
    assert len(notes) == 1
    assert unquote(notes[0].children[0]) == "This is a note"


# ── Reference ─────────────────────────────────────────────────────────────────


def test_ref():
    src = """
    process "P" {
      start ->
      task "Do Work" ->
      xor "Loop?" {
        [again] -> #"Do Work"
        [done]  -> end
      }
    }
    """
    tree = parse(src)
    refs = find_all(tree, "ref")
    assert len(refs) == 1
    assert unquote(refs[0].children[0]) == "Do Work"


# ── Example files ─────────────────────────────────────────────────────────────


def test_parse_example_simple(examples_dir):
    tree = parse_file(examples_dir / "simple.bpmndsl")
    assert len(find_all(tree, "process")) == 1
    assert len(find_all(tree, "task")) == 6


def test_parse_example_xor_gateway(examples_dir):
    tree = parse_file(examples_dir / "xor_gateway.bpmndsl")
    assert len(find_all(tree, "xor_gw")) == 2
    assert len(find_all(tree, "branch")) >= 3


def test_parse_example_nested_and(examples_dir):
    tree = parse_file(examples_dir / "nested_and.bpmndsl")
    assert len(find_all(tree, "and_gw")) == 1
    assert len(find_all(tree, "xor_gw")) >= 1
    # subprocess appears twice: once in the lane membership block, once in the seq
    assert len(find_all(tree, "subprocess")) == 2
    assert len(find_all(tree, "lane")) == 5  # 5 lanes declared


def test_parse_example_collaboration(examples_dir):
    tree = parse_file(examples_dir / "collaboration.bpmndsl")
    assert len(find_all(tree, "collaboration")) == 1
    assert len(find_all(tree, "pool")) == 2
    assert len(find_all(tree, "lane")) == 3  # Sales, Warehouse, Customer Support
    assert len(find_all(tree, "xor_gw")) == 2


# ── Lanes ─────────────────────────────────────────────────────────────────────


def test_lane_names():
    src = """
    process "P" {
      lane "Alpha" { task "A" }
      lane "Beta"  { task "B", task "C" }
      task "A" -> task "B" -> task "C" -> end
    }
    """
    tree = parse(src)
    lanes = find_all(tree, "lane")
    assert len(lanes) == 2
    names = [unquote(lane.children[0]) for lane in lanes]
    assert names == ["Alpha", "Beta"]


def test_lane_member_count():
    src = """
    process "P" {
      lane "Finance" { task "Pay", task "Reconcile", task "Archive" }
      task "Pay" -> task "Reconcile" -> task "Archive" -> end
    }
    """
    tree = parse(src)
    lane = next(tree.find_data("lane"))
    members = next(lane.find_data("lane_members"))
    assert len(find_all(members, "task")) == 3


def test_lane_with_events():
    src = """
    process "P" {
      lane "Start Lane" { start:message("in"), end }
      lane "Work Lane"  { task "Do Work" }
      start:message("in") -> task "Do Work" -> end
    }
    """
    tree = parse(src)
    assert len(find_all(tree, "lane")) == 2
    start_events = find_all(tree, "start_event")
    assert len(start_events) == 2  # one in lane declaration, one in seq


def test_lane_with_subprocess():
    src = """
    process "P" {
      lane "Ops" {
        subprocess "Sub" { task "Inner" }
      }
      subprocess "Sub" { task "Inner" } -> end
    }
    """
    tree = parse(src)
    assert len(find_all(tree, "lane")) == 1
    subs = find_all(tree, "subprocess")
    assert len(subs) == 2  # one in lane, one in seq


def test_lane_empty():
    # Lanes can be empty (placeholder for future elements)
    src = """
    process "P" {
      lane "Reserved" {}
      lane "Work" { task "A" }
      start -> task "A" -> end
    }
    """
    tree = parse(src)
    assert len(find_all(tree, "lane")) == 2


def test_laneset_without_seq():
    # laneset: seq is optional — valid to declare lanes without explicit flow
    src = """
    process "P" {
      lane "A" { start, task "T", end }
    }
    """
    tree = parse(src)
    assert len(find_all(tree, "lane")) == 1
    assert len(find_all(tree, "laneset")) == 1


# ── Pool ──────────────────────────────────────────────────────────────────────


def test_pool_simple():
    src = """
    pool "Customer" {
      start -> task "Order" -> end:message("ordered")
    }
    """
    tree = parse(src)
    pools = find_all(tree, "pool")
    assert len(pools) == 1
    assert unquote(pools[0].children[0]) == "Customer"


def test_pool_with_lanes():
    src = """
    pool "Company" {
      lane "Sales"   { task "Take Order" }
      lane "Finance" { task "Issue Invoice", end }
      task "Take Order" -> task "Issue Invoice" -> end
    }
    """
    tree = parse(src)
    assert len(find_all(tree, "pool")) == 1
    assert len(find_all(tree, "lane")) == 2
    # 2 unique tasks; each appears in lane membership AND in seq → 4 total
    assert len(find_all(tree, "task")) == 4


def test_pool_and_process_at_top_level():
    src = """
    pool "External" { start -> task "A" -> end }
    process "Internal" { start -> task "B" -> end }
    """
    tree = parse(src)
    assert len(find_all(tree, "pool")) == 1
    assert len(find_all(tree, "process")) == 1


# ── Collaboration ─────────────────────────────────────────────────────────────


def test_collaboration_name():
    src = """
    collaboration "Supply Chain" {
      pool "Buyer"    { start -> task "Order" -> end:message("order-sent") }
      pool "Supplier" { start:message("order-sent") -> task "Fulfill" -> end }
    }
    """
    tree = parse(src)
    collabs = find_all(tree, "collaboration")
    assert len(collabs) == 1
    assert unquote(collabs[0].children[0]) == "Supply Chain"


def test_collaboration_pool_count():
    src = """
    collaboration "C" {
      pool "P1" { start -> end }
      pool "P2" { start -> end }
      pool "P3" { start -> end }
    }
    """
    tree = parse(src)
    assert len(find_all(tree, "pool")) == 3


def test_collaboration_with_message_events():
    src = """
    collaboration "Billing" {
      pool "Client" {
        start -> task "Request Service" -> end:message("request")
      }
      pool "Provider" {
        start:message("request") ->
        task "Process Request" ->
        throw:message("invoice") ->
        end
      }
    }
    """
    tree = parse(src)
    assert len(find_all(tree, "pool")) == 2
    assert len(find_all(tree, "start_event")) == 2
    assert len(find_all(tree, "end_event")) == 2
    assert len(find_all(tree, "throw_event")) == 1


# ── Error cases ───────────────────────────────────────────────────────────────


def test_parse_error_empty_input():
    with pytest.raises(UnexpectedInput):
        parse("")


def test_parse_error_missing_braces():
    with pytest.raises(UnexpectedInput):
        parse('process "P" start -> end')


def test_parse_error_unknown_keyword():
    with pytest.raises(UnexpectedInput):
        parse('process "P" { begin -> task "A" -> finish }')


def test_parse_error_unclosed_gateway():
    with pytest.raises(UnexpectedInput):
        parse('process "P" { start -> xor "G" { [c] -> task "A" -> end }')


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def examples_dir():
    from pathlib import Path

    return Path(__file__).parent.parent.parent / "examples"

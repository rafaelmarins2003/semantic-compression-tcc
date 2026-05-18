"""Tests for BPMN-DSL v2 grammar integration."""

import pytest
from lark import Tree
from lark.exceptions import UnexpectedInput

from src.dsl.parser import parse, parse_file, unquote


def find_all(tree: Tree, rule: str) -> list[Tree]:
    return list(tree.find_data(rule))


def test_parse_returns_tree_with_process_name():
    tree = parse('process "Order Flow" { start "Created" -> end "Closed" }')

    assert tree.data == "start"
    process = next(tree.find_data("process"))
    assert unquote(process.children[0]) == "Order Flow"


def test_parse_task_types_with_ids_and_props():
    tree = parse(
        """
        process "P" {
          start ->
          task "Generic" ->
          user "Review" #review (role="manager") ->
          service "Calculate" ->
          manual "Archive" ->
          script "Notify" ->
          send "Message" ->
          receive "Reply" ->
          rule "Check rule" ->
          end
        }
        """
    )

    tasks = find_all(tree, "task")
    assert [str(task.children[0]) for task in tasks] == [
        "task",
        "user",
        "service",
        "manual",
        "script",
        "send",
        "receive",
        "rule",
    ]
    assert len(find_all(tree, "props")) == 1


def test_parse_named_and_typed_events():
    tree = parse(
        """
        process "P" {
          start:message("order") "Order received" #start_order ->
          catch:timer("PT2H") "Timeout" ->
          throw:signal("done") "Done signal" ->
          end:error "Failed"
        }
        """
    )

    specs = [str(spec.children[0]) for spec in find_all(tree, "event_spec")]
    assert specs == ["message", "timer", "signal", "error"]
    assert len(find_all(tree, "start_event")) == 1
    assert len(find_all(tree, "catch_event")) == 1
    assert len(find_all(tree, "throw_event")) == 1
    assert len(find_all(tree, "end_event")) == 1


def test_parse_generic_intermediate_catch_event():
    tree = parse('process "P" { start -> catch:none "Wait for completion" -> end }')

    spec = next(tree.find_data("event_spec"))
    assert str(spec.children[0]) == "none"
    assert len(find_all(tree, "catch_event")) == 1


def test_parse_xor_with_empty_branch_and_stable_ref():
    tree = parse(
        """
        process "P" {
          start ->
          user "Review" #review ->
          xor "Approved?" #decision {
            [yes] -> service "Persist" -> end "Approved"
            [no] -> ()
            [retry] -> #review
          }
        }
        """
    )

    assert len(find_all(tree, "xor_gw")) == 1
    assert len(find_all(tree, "cond_branch")) == 3
    assert len(find_all(tree, "empty_branch")) == 1
    assert str(find_all(tree, "ref")[0].children[0]) == "review"


def test_parse_and_or_and_event_gateways():
    tree = parse(
        """
        process "P" {
          start ->
          and "Parallel" {
            task "A";
            task "B" -> task "C"
          } ->
          or "Inclusive" {
            [needs x] -> task "X"
            [needs y] -> task "Y"
          } ->
          event "Wait" {
            [:message("approved")] -> catch:message "Approved"
            [:timer("PT30M")] -> catch:timer "Timed out"
          } ->
          end
        }
        """
    )

    assert len(find_all(tree, "and_gw")) == 1
    assert len(find_all(tree, "or_gw")) == 1
    assert len(find_all(tree, "event_gw")) == 1
    assert len(find_all(tree, "event_branch")) == 2


def test_parse_lane_scoped_process_body():
    tree = parse(
        """
        process "P" {
          @lane "Requester" {
            start -> user "Request"
          }
          @lane "Backoffice" {
            -> user "Analyze" -> end
          }
        }
        """
    )

    lanes = find_all(tree, "lane_block")
    assert [unquote(lane.children[0]) for lane in lanes] == ["Requester", "Backoffice"]
    assert len(find_all(tree, "flow")) == 2


def test_parse_subprocess_call_note_and_pool():
    tree = parse(
        """
        pool "Company" {
          start ->
          subprocess "Sub" { task "Inner" -> end } ->
          call "External Process" ->
          note "Manual validation required" ->
          end
        }
        """
    )

    assert len(find_all(tree, "pool")) == 1
    assert len(find_all(tree, "subprocess")) == 1
    assert len(find_all(tree, "call_activity")) == 1
    assert len(find_all(tree, "note")) == 1


def test_parse_collaboration_with_message_flow():
    tree = parse(
        """
        collaboration "Order Collaboration" {
          pool "Customer" {
            start -> send "Send order" #send_order -> end
          }
          pool "Seller" {
            start:message "Receive order" #receive_order ->
            receive "Store order" #store_order ->
            end
          }
          message "Order" from #send_order to #receive_order
        }
        """
    )

    assert len(find_all(tree, "collaboration")) == 1
    assert len(find_all(tree, "pool")) == 2
    assert len(find_all(tree, "message_flow")) == 1


def test_parse_file_uses_v2_grammar(tmp_path):
    path = tmp_path / "sample.bpmndsl"
    path.write_text('process "P" { start -> task "A" -> end }', encoding="utf-8")

    assert len(find_all(parse_file(path), "process")) == 1


def test_legacy_name_refs_are_rejected():
    with pytest.raises(UnexpectedInput):
        parse('process "P" { start -> task "A" -> #"A" }')


def test_v1_lane_declaration_is_rejected():
    with pytest.raises(UnexpectedInput):
        parse('process "P" { lane "Sales" { task "A" } task "A" -> end }')


def test_and_branches_require_semicolon_not_comma():
    with pytest.raises(UnexpectedInput):
        parse('process "P" { start -> and { task "A", task "B" } -> end }')

"""source_grounding 순수 함수 테스트."""

import unittest

from app.agents.validator.source_grounding import (
    collect_valid_source_ids,
    filter_grounded_actions,
    is_action_grounded,
)


def _action(source_ids=None):
    return {"action_id": "A1", "source_ids": source_ids or []}


def _doc(source_id):
    return {"source_id": source_id, "title": "t", "content": "c"}


class CollectValidSourceIdsTest(unittest.TestCase):
    def test_ignores_missing(self) -> None:
        docs = [_doc("SOP-1"), {"title": "no id"}, _doc("SOP-2")]
        self.assertEqual(collect_valid_source_ids(docs), frozenset({"SOP-1", "SOP-2"}))


class IsActionGroundedTest(unittest.TestCase):
    def test_grounded_when_all_source_ids_valid(self) -> None:
        valid = frozenset({"SOP-1", "SOP-2"})
        self.assertTrue(is_action_grounded(_action(["SOP-1"]), valid))
        self.assertTrue(is_action_grounded(_action(["SOP-1", "SOP-2"]), valid))

    def test_not_grounded_when_source_id_missing(self) -> None:
        valid = frozenset({"SOP-1"})
        self.assertFalse(is_action_grounded(_action(["SOP-1", "SOP-FAKE"]), valid))

    def test_not_grounded_when_empty_source_ids(self) -> None:
        valid = frozenset({"SOP-1"})
        self.assertFalse(is_action_grounded(_action([]), valid))


class FilterGroundedActionsTest(unittest.TestCase):
    def test_partitions_actions(self) -> None:
        actions = [_action(["SOP-1"]), _action(["SOP-FAKE"]), _action([])]
        docs = [_doc("SOP-1")]
        grounded, dropped = filter_grounded_actions(actions, docs)
        self.assertEqual(len(grounded), 1)
        self.assertEqual(len(dropped), 2)


if __name__ == "__main__":
    unittest.main()

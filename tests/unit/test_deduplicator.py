"""deduplicator 순수 함수 테스트."""

import unittest

from app.agents.validator.deduplicator import deduplicate_actions, normalize_title


def _action(title="test", source_ids=None, priority="MEDIUM", required=False, previously_failed=False):
    return {
        "action_id": title,
        "title": title,
        "source_ids": source_ids or ["S1"],
        "priority": priority,
        "required": required,
        "previously_failed": previously_failed,
    }


class NormalizeTitleTest(unittest.TestCase):
    def test_removes_case_and_whitespace(self) -> None:
        self.assertEqual(normalize_title("냉각수 확인"), normalize_title(" 냉각수확인 "))
        self.assertEqual(normalize_title("Cool Check"), normalize_title("coolcheck"))


class DeduplicateActionsTest(unittest.TestCase):
    def test_no_duplicates_returns_all(self) -> None:
        actions = [_action("A"), _action("B"), _action("C")]
        result = deduplicate_actions(actions)
        self.assertEqual(len(result), 3)

    def test_same_normalized_title_merged(self) -> None:
        actions = [
            _action("냉각수 확인", source_ids=["SOP-1"]),
            _action("냉각수확인", source_ids=["KOSHA-1"]),
        ]
        result = deduplicate_actions(actions)
        self.assertEqual(len(result), 1)
        self.assertEqual(set(result[0]["source_ids"]), {"SOP-1", "KOSHA-1"})

    def test_priority_upgraded_on_merge(self) -> None:
        actions = [
            _action("check", priority="LOW"),
            _action("check", priority="HIGH"),
        ]
        result = deduplicate_actions(actions)
        self.assertEqual(result[0]["priority"], "HIGH")

    def test_required_ored_on_merge(self) -> None:
        actions = [
            _action("check", required=False),
            _action("check", required=True),
        ]
        result = deduplicate_actions(actions)
        self.assertTrue(result[0]["required"])

    def test_previously_failed_ored_on_merge(self) -> None:
        actions = [
            _action("check", previously_failed=False),
            _action("check", previously_failed=True),
        ]
        result = deduplicate_actions(actions)
        self.assertTrue(result[0]["previously_failed"])

    def test_source_ids_deduplicated_within_merge(self) -> None:
        actions = [
            _action("check", source_ids=["S1", "S2"]),
            _action("check", source_ids=["S2", "S3"]),
        ]
        result = deduplicate_actions(actions)
        self.assertEqual(result[0]["source_ids"], ["S1", "S2", "S3"])


if __name__ == "__main__":
    unittest.main()

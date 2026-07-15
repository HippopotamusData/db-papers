from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validation_policy import quality_issue_severity  # noqa: E402


class ValidationPolicyTests(unittest.TestCase):
    def test_draft_quality_gaps_are_warnings(self) -> None:
        self.assertEqual(quality_issue_severity("draft"), "warning")

    def test_translated_quality_gaps_are_errors(self) -> None:
        self.assertEqual(quality_issue_severity("translated"), "error")

    def test_non_translation_status_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            quality_issue_severity("source_only")


if __name__ == "__main__":
    unittest.main()

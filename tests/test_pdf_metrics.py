from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pdf_metrics  # noqa: E402


class PdfMetricsTests(unittest.TestCase):
    def test_source_word_count_stops_before_references(self) -> None:
        text = (
            "A database-aware system's end-to-end design.\n"
            "9 REFERENCES\n"
            "These bibliography words must not count.\n"
        )
        self.assertEqual(pdf_metrics.source_word_count_from_text(text), 5)

        numbered_bibliography = "Body words.\n9.1 BIBLIOGRAPHY\nIgnored words.\n"
        self.assertEqual(
            pdf_metrics.source_word_count_from_text(numbered_bibliography), 2
        )

    def test_translation_cjk_count_stops_before_references(self) -> None:
        text = "## 1 引言\n数据库系统。\n## 参考文献\n这些字不计入。\n"
        self.assertEqual(pdf_metrics.translation_cjk_count_from_text(text), 7)

        numbered = "## 正文\n数据库。\n## 9.1 Bibliography\n这些字不计入。\n"
        self.assertEqual(pdf_metrics.translation_cjk_count_from_text(numbered), 5)

    def test_abridgement_thresholds_use_exact_integer_comparison(self) -> None:
        high = pdf_metrics.abridgement_candidate_from_counts(49, 100)
        moderate = pdf_metrics.abridgement_candidate_from_counts(50, 100)
        boundary = pdf_metrics.abridgement_candidate_from_counts(75, 100)
        self.assertIn("high mechanical", high or "")
        self.assertIn("moderate mechanical", moderate or "")
        self.assertIsNone(boundary)

    def test_canonical_extractor_classifies_observed_boundary_papers(self) -> None:
        low_latency = pdf_metrics.abridgement_candidate_from_counts(2000, 2737)
        milvus = pdf_metrics.abridgement_candidate_from_counts(7930, 10523)
        self.assertIn("moderate mechanical", low_latency or "")
        self.assertIsNone(milvus)

    def test_wrong_pypdf_version_fails_closed(self) -> None:
        with patch.object(pdf_metrics.pypdf, "__version__", "0.0.0"):
            with self.assertRaisesRegex(ValueError, "pypdf 6.14.2 is required"):
                pdf_metrics._require_pinned_pypdf()


if __name__ == "__main__":
    unittest.main()

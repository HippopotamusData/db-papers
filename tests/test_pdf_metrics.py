from __future__ import annotations

import contextlib
import io
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pdf_metrics  # noqa: E402


class PdfMetricsTests(unittest.TestCase):
    def test_source_word_count_stops_before_references(self) -> None:
        text = (
            "A database-aware system's end-to-end design.\n"
            "9 REFERENCES\n"
            "[1] Smith, J. Bibliography words, 2020.\n"
        )
        self.assertEqual(pdf_metrics.source_word_count_from_text(text), 5)

        numbered_bibliography = (
            "Body words.\n"
            "9.1 BIBLIOGRAPHY\n"
            "1. Smith, J. Ignored words, 2020.\n"
        )
        self.assertEqual(
            pdf_metrics.source_word_count_from_text(numbered_bibliography), 2
        )

    def test_source_word_count_accepts_strong_ocr_i_first_reference(self) -> None:
        text = (
            "Body words before bibliography.\n"
            "REFERENCES\n"
            "[i] K. P. Eswaran, J. N. Gray. Predicate locks. "
            "Technical Report RJ1487, 1974.\n"
            "[2] Information Management System Virtual Storage. IBM, 1975.\n"
            "[3] UNIVAC Data Management System. Sperry Rand, 1973.\n"
        )
        self.assertEqual(pdf_metrics.source_word_count_from_text(text), 4)

    def test_source_word_count_accepts_wrapped_markerless_reference(self) -> None:
        text = (
            "Body words before bibliography.\n"
            "REFERENCES\n"
            "K.P. Eswaran, J.N. Gray, R.A. Lorie, I.L. Traiger, On the\n"
            "Notions of Consistency and Predicate Locks, technical Report\n"
            "RJ.1487, IBM Research Laboratory, November 1974.\n"
            "Information Management System Virtual Storage.\n"
            "IBM Corp., 1975.\n"
        )
        self.assertEqual(pdf_metrics.source_word_count_from_text(text), 4)

    def test_source_word_count_ignores_toc_reference_heading(self) -> None:
        toc = (
            "CONTENTS\n"
            "INTRODUCTION\n"
            "REFERENCES\n"
            + ("Body database systems words.\n" * 20)
            + "REFERENCES\n"
            "[1] Smith, J. Bibliography words, 2020.\n"
        )
        self.assertEqual(
            pdf_metrics.source_word_count_from_text(toc),
            20 * 4 + 2,
        )

    def test_source_word_count_uses_first_real_heading_not_running_headers(self) -> None:
        text = (
            "Body words before bibliography.\n"
            "REFERENCES\n"
            "[1] Smith, J. First citation, 2020.\n"
            "12 References\n"
            "[2] Jones, A. Second citation, 2021.\n"
        )
        self.assertEqual(pdf_metrics.source_word_count_from_text(text), 4)

    def test_source_word_count_does_not_advance_from_real_heading_after_long_gap(
        self,
    ) -> None:
        text = (
            ("Body words.\n" * 30)
            + "REFERENCES\n"
            + "".join(
                f"{index}. Smith, J. Citation entry 2020.\n"
                for index in range(1, 51)
            )
            + "REFERENCES\n"
            + "".join(
                f"{index}. Jones, A. More citations 2021.\n"
                for index in range(51, 71)
            )
        )
        self.assertEqual(
            pdf_metrics.source_word_count_from_text(text),
            30 * 2,
        )

    def test_ambiguous_multiple_reference_headings_fail_closed(self) -> None:
        late_toc = (
            ("Preface words.\n" * 10)
            + "REFERENCES\n"
            + ("Body database words.\n" * 50)
            + "REFERENCES\n"
            + ("Citation words.\n" * 10)
        )
        early_real = (
            ("Body words.\n" * 5)
            + "REFERENCES\n"
            + ("Citation entry.\n" * 60)
            + "REFERENCES\n"
            + ("More citation.\n" * 20)
        )
        for text in (late_toc, early_real):
            with self.subTest(text=text[:30]):
                with self.assertRaisesRegex(ValueError, "References/Bibliography"):
                    pdf_metrics.source_word_count_from_text(text)

    def test_single_toc_reference_heading_cannot_shrink_denominator(self) -> None:
        text = (
            "CONTENTS\n"
            "REFERENCES\n"
            "Introduction and body database words follow.\n"
        )
        with self.assertRaisesRegex(ValueError, "lacks enough nearby entry evidence"):
            pdf_metrics.source_word_count_from_text(text)

    def test_toc_heading_followed_by_numbered_body_sections_is_not_evidence(
        self,
    ) -> None:
        text = (
            "CONTENTS\n"
            "REFERENCES\n"
            "1. INTRODUCTION\n"
            "Body database words.\n"
            "2. RELATED WORK\n"
            "More body words.\n"
        )
        with self.assertRaisesRegex(ValueError, "lacks enough nearby entry evidence"):
            pdf_metrics.source_word_count_from_text(text)

    def test_toc_reference_heading_followed_by_assignment_is_not_evidence(
        self,
    ) -> None:
        text = (
            "CONTENTS\nREFERENCES\n[x] = feature vector\n"
            + ("bodyword " * 80)
            + "\nREFERENCES\n[1] Smith, J. Real paper, 2020.\n"
        )
        self.assertGreater(pdf_metrics.source_word_count_from_text(text), 80)

    def test_toc_reference_heading_followed_by_prose_is_not_author_evidence(
        self,
    ) -> None:
        text = (
            "CONTENTS\nREFERENCES\nIntroduction. We continue with the paper.\n"
            + ("bodyword " * 80)
            + "\nREFERENCES\n[1] Smith, J. Real paper, 2020.\n"
        )
        self.assertGreater(pdf_metrics.source_word_count_from_text(text), 80)

    def test_toc_author_key_citations_are_not_reference_entry_evidence(
        self,
    ) -> None:
        text = (
            "CONTENTS\n"
            "REFERENCES\n"
            "[KNUT73] provides a survey of the basics.\n"
            "[BAYE72] describes an index structure.\n"
            + ("Body database systems words.\n" * 20)
            + "REFERENCES\n"
            "AHO74 AHO, A., AND ULLMAN, J. Algorithms, 1974.\n"
            "KNUT73 KNUTH, D. Sorting and searching, 1973.\n"
        )
        self.assertEqual(
            pdf_metrics.source_word_count_from_text(text),
            91,
        )

    def test_toc_numeric_citations_are_not_reference_entry_evidence(
        self,
    ) -> None:
        text = (
            "CONTENTS\n"
            "REFERENCES\n"
            "[1] provides a survey.\n"
            "[2] describes an index.\n"
            + ("Body database systems words.\n" * 20)
            + "REFERENCES\n"
            "[1] Smith, J. Real paper, 2020.\n"
            "[2] Jones, A. Second real paper, 2021.\n"
        )
        self.assertEqual(
            pdf_metrics.source_word_count_from_text(text),
            87,
        )

    def test_toc_single_citation_prose_cannot_select_reference_heading(
        self,
    ) -> None:
        fake_entries = (
            "[1] In 2020, the system changed.",
            "[1] We use the prior design, with minor changes.",
            "[1] A. Smith proposed the mechanism.",
            "1. In 2020, the system changed.",
            "[1] See the Journal article for details.",
            "[1] See https://example.com for details.",
            "[1] Smith, J. argues that the model is useful.",
            "[1] A. Smith, however, proposed the mechanism.",
            "[1] ACM. We discuss the implementation.",
            "1. Smith, J. argues that the model is useful.",
            "1) A. Smith, however, proposed the mechanism.",
            "1. ACM. We discuss the implementation.",
            "1. Codd, E. introduced the model.",
            'AND BAYER, R., "Indexes", Journal 7, 1974.',
        )
        for fake_entry in fake_entries:
            with self.subTest(fake_entry=fake_entry):
                text = (
                    "CONTENTS\n"
                    "REFERENCES\n"
                    f"{fake_entry}\n"
                    + ("bodyword " * 80)
                    + "\nREFERENCES\n"
                    "[1] Smith, J. Real paper, 2020.\n"
                    "[2] Jones, A. Second real paper, 2021.\n"
                )
                self.assertGreater(
                    pdf_metrics.source_word_count_from_text(text),
                    80,
                )

    def test_pure_letter_author_keys_with_bibliographic_evidence_are_valid(
        self,
    ) -> None:
        text = (
            "Body database words.\n"
            "REFERENCES\n"
            "[CODD] Codd, E. Relational model, 1970.\n"
            "[STONE] Stonebraker, M. Ingres, 1976.\n"
        )
        self.assertEqual(
            pdf_metrics.source_word_count_from_text(text),
            3,
        )

    def test_translation_cjk_count_stops_before_references(self) -> None:
        text = "## 1 引言\n数据库系统。\n## 参考文献\n这些字不计入。\n"
        self.assertEqual(pdf_metrics.translation_cjk_count_from_text(text), 7)

        numbered = "## 正文\n数据库。\n## 9.1 Bibliography\n这些字不计入。\n"
        self.assertEqual(pdf_metrics.translation_cjk_count_from_text(numbered), 5)

    def test_hidden_html_comments_do_not_inflate_translation_coverage(self) -> None:
        text = (
            "正文。\n"
            "<!-- 隐藏中文不应计入覆盖率。\n"
            "更多隐藏内容。 -->\n"
        )
        self.assertEqual(
            pdf_metrics.translation_cjk_count_from_text(text),
            2,
        )

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

    def test_supported_pdf_keeps_deterministic_count(self) -> None:
        reader = Mock(pages=[Mock(extract_text=Mock(return_value="Database systems."))])
        with patch.object(pdf_metrics, "PdfReader", return_value=reader):
            self.assertEqual(pdf_metrics.source_word_count(Path("source.pdf")), 2)

    def test_unsupported_encoding_does_not_return_fallback_count(self) -> None:
        logger = logging.getLogger("pypdf._cmap")
        filters = list(logger.filters)

        def extract() -> str:
            logger.error("Advanced encoding [] not implemented yet")
            return "Fallback database words."

        reader = Mock(pages=[Mock(extract_text=Mock(side_effect=extract))])
        stderr = io.StringIO()
        with patch.object(pdf_metrics, "PdfReader", return_value=reader):
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(pdf_metrics.UnsupportedPdfEncoding):
                    pdf_metrics.source_word_count(Path("source.pdf"))
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(logger.filters, filters)

    def test_unrecognized_pdf_diagnostic_is_not_consumed(self) -> None:
        logger = logging.getLogger("pypdf._cmap")

        def extract() -> str:
            logger.error("Unexpected damaged font")
            return "Database words."

        reader = Mock(pages=[Mock(extract_text=Mock(side_effect=extract))])
        with patch.object(pdf_metrics, "PdfReader", return_value=reader):
            with self.assertLogs(logger, level="ERROR") as captured:
                pdf_metrics.source_word_count(Path("source.pdf"))
        self.assertIn("Unexpected damaged font", captured.output[0])

    def test_empty_text_is_hard_failure_even_with_encoding_diagnostic(self) -> None:
        def extract() -> str:
            logging.getLogger("pypdf._cmap").error(
                "Advanced encoding [] not implemented yet"
            )
            return ""

        reader = Mock(pages=[Mock(extract_text=Mock(side_effect=extract))])
        with patch.object(pdf_metrics, "PdfReader", return_value=reader):
            with self.assertRaisesRegex(ValueError, "produced no source words"):
                pdf_metrics.source_word_count(Path("source.pdf"))

    def test_reader_failure_removes_temporary_diagnostic_filter(self) -> None:
        logger = logging.getLogger("pypdf._cmap")
        filters = list(logger.filters)
        with patch.object(pdf_metrics, "PdfReader", side_effect=OSError("unreadable")):
            with self.assertRaises(OSError):
                pdf_metrics.source_word_count(Path("source.pdf"))
        self.assertEqual(logger.filters, filters)

    def test_cli_reports_unavailable_metric_as_visible_review_candidate(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["pdf_metrics.py", "abridgement", "a.pdf", "b.md"]):
            with patch.object(pdf_metrics, "abridgement_candidate", side_effect=pdf_metrics.UnsupportedPdfEncoding("Advanced encoding [] not implemented yet")):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    self.assertEqual(pdf_metrics.main(), 0)
        self.assertIn("unavailable mechanical abridgement metric", stdout.getvalue())
        self.assertIn("requires direct PDF review", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_keeps_unreadable_pdf_a_hard_failure(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["pdf_metrics.py", "abridgement", "a.pdf", "b.md"]):
            with patch.object(pdf_metrics, "abridgement_candidate", side_effect=OSError("unreadable")):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    self.assertEqual(pdf_metrics.main(), 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("unreadable", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

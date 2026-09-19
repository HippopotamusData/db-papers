"""Bibliography extraction regressions for row-interleaved PDF layout text."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_resources as resources  # noqa: E402


def columns(*texts: str, width: int = 72) -> str:
    lines = [text.split("\n") for text in texts]
    return "\n".join(
        ("".join((part[row] if row < len(part) else "").ljust(width)
                 for part in lines[:-1])
         + (lines[-1][row] if row < len(lines[-1]) else "")).rstrip()
        for row in range(max(map(len, lines)))
    )


class ReferenceReviewRegressionTests(unittest.TestCase):
    def test_right_column_before_heading_and_continuation_are_recovered(self) -> None:
        source = columns(
            "Conclusion.\nOur database is useful.\n\nREFERENCES\n"
            "[1] T. Author. Durable\n    storage protocols. Conference 2001.\n"
            "[2] J. Writer. Query processing. Journal 2002.\n\n",
            "[3] C. Reader. Replicated\n    database systems. Conference 2003.\n"
            "[4] D. Researcher. Scalable storage. Journal 2004.\n\n\n",
        )
        _, section, body = resources._review_source_reference_parts(source)
        entries = resources._reference_entries(section)
        self.assertEqual([key for key, _ in entries], ["1", "2", "3", "4"])
        self.assertIn("database systems. Conference 2003.", dict(entries)["3"])
        self.assertNotIn("Our database", section)
        self.assertNotIn("C. Reader", body)
        translation = "## 参考文献\n" + "\n".join(
            f"[{key}] {text}" for key, text in entries
        )
        self.assertEqual(resources._reference_findings(source, translation), ([], []))
        missing = translation.replace("[3] " + dict(entries)["3"], "")
        errors, _ = resources._reference_findings(source, missing)
        self.assertIn("missing numbered references: 3", errors)

    def test_right_heading_does_not_absorb_left_conclusion(self) -> None:
        source = columns(
            "An unrelated conclusion.\n" * 15,
            "REFERENCES\n[1] J. Writer. Query processing. Journal 2002.\n"
            "[2] C. Reader. Replicated database systems. Conference 2003.\n"
            "[3] D. Researcher. Scalable storage. 2004.\n\n\n",
        )
        _, section, _ = resources._review_source_reference_parts(source)
        self.assertNotIn("conclusion", section)
        self.assertEqual(len(dict(resources._reference_entries(section))["3"]),
                         len("D. Researcher. Scalable storage. 2004."))

    def test_three_columns_with_bibliography_above_heading(self) -> None:
        source = columns(
            "Conclusion and predictions.\n" * 15,
            "Conclusion continued.\n\nReferences\n"
            "1. Able, A. Reliable stores. Conference 2001.\n"
            "2. Baker, B. Scalable databases. Journal 2002.\n\n",
            "3. Carter, C. Distributed protocols. Conference 2003.\n"
            "4. Davis, D. Concurrent transactions. Journal 2004.\n\n\n"
            "These authors work at a university.\n",
        )
        _, section, _ = resources._review_source_reference_parts(source)
        self.assertEqual([key for key, _ in resources._reference_entries(section)],
                         ["1", "2", "3", "4"])
        self.assertNotIn("Conclusion", section)

    def test_ordinal_venue_name_is_not_numeric_ocr_entry(self) -> None:
        section = "[1] Sergey Author. Graph research.\n    7th Intl. Conference, 2001.\n[2] Next Author. Paper. 2002."
        self.assertEqual([key for key, _ in resources._reference_entries(section)], ["1", "2"])
        self.assertIn("7th Intl.", resources._reference_entries(section)[0][1])

    def test_standalone_author_keys_and_page_boundary(self) -> None:
        section = "Ande81a\n    Anderson, T. Fault tolerance. 1981.\n\fGray78a\n    Gray, Jim. Transaction processing. 1978."
        normalized = resources._source_reference_marker_lines(section)
        self.assertEqual([key for key, _ in resources._reference_entries(normalized)],
                         ["ande81a", "gray78a"])
        self.assertIn("\f", normalized)

    def test_damaged_author_key_delimiters_keep_ocr_identity(self) -> None:
        section = "[ BITT831 Bitton, D. Benchmarking database systems. 1983.\n\fICHOUSS] Chou, H. Wisconsin storage. 1985."
        normalized = resources._source_reference_marker_lines(section)
        self.assertEqual([key for key, _ in resources._reference_entries(normalized)],
                         ["bitt831", "ichouss"])

    def test_wrapped_words_do_not_displace_reference_identity_tokens(self) -> None:
        section = "[1] Author, A. Appli-\n    cation of hash tables.\n[2] Other, B. Block-\n    Oriented Processing."
        entries = dict(resources._reference_entries(section))
        self.assertIn("Application", entries["1"])
        self.assertIn("Block- Oriented", entries["2"])

    def test_empty_and_marker_free_text_have_no_layout_columns(self) -> None:
        for text in ("", "Narrative only.", columns("Left prose", "Right prose")):
            self.assertEqual(resources._layout_reference_columns(text), [])

    def test_blank_lines_do_not_truncate_reference_continuation(self) -> None:
        source = columns(
            "REFERENCES\n[1] A. Author. A reference title.\n"
            "[2] B. Writer. A second title.\n\n\n"
            "    Its publication and page range, 123–145.\n",
            "[3] C. Reader. A third reference. Journal 2003.\n"
            "[4] D. Researcher. A fourth reference. Conference 2004.",
        )
        _, section, _ = resources._review_source_reference_parts(source)
        entries = dict(resources._reference_entries(section))
        self.assertIn("123–145", entries["2"])

    def test_intact_parenthesized_acronyms_are_not_ocr_keys(self) -> None:
        for text in ("(UUID) URN Namespace. https://example.org/", "(ACM) 8, 2 (1976), 25–35.", "lands) (SIGMOD ’19). Association for Computing Machinery."):
            self.assertEqual(resources._source_reference_marker_lines(text), text)

    def test_explicit_appendix_boundary_excludes_code(self) -> None:
        section = "[1] A. Author. Title. 2001.\nAppendix A.       QUERIES\nSELECT * FROM T;"
        boundary = resources._source_post_reference_appendix_boundary(section)
        self.assertEqual(section[:boundary].strip(), "[1] A. Author. Title. 2001.")

    def test_split_author_key_year_is_preserved_as_one_marker(self) -> None:
        section = "[BAW+ 09] S. Bellamkonda. Query optimization. 2009."
        entries = resources._reference_entries(resources._source_reference_marker_lines(section))
        self.assertEqual(entries[0][0], "baw+09")

    def test_bold_author_keys_with_plus_are_reference_entries(self) -> None:
        entries = resources._reference_entries("**[ABB+02]** A. Author. Paper. 2002.")
        self.assertEqual(entries[0][0], "abb+02")

    def test_actual_truncated_content_remains_a_review_candidate(self) -> None:
        source = "REFERENCES\n[1] A. Author. A detailed investigation of replicated durable storage protocols, their implementation and evaluation. Proceedings of the Database Conference, 2001.\n[2] B. Writer. Another database paper. Journal 2002."
        errors, risks = resources._reference_findings(source, "## 参考文献\n[1] Alice.\n[2] B. Writer. Another database paper. Journal 2002.")
        self.assertFalse(errors)
        self.assertIn("translation reference content is suspiciously short for: 1", risks)


if __name__ == "__main__":
    unittest.main()

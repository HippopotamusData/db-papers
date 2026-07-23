from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf.errors import PdfReadError, PdfStreamError


ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "scripts"))

import validate_source_pdf  # noqa: E402


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class FakeReader:
    def __init__(self, pages: list[FakePage], *, encrypted: bool = False) -> None:
        self.pages = pages
        self.is_encrypted = encrypted


class BrokenPageTreeReader:
    is_encrypted = False

    @property
    def pages(self) -> list[FakePage]:
        raise PdfReadError("broken page tree")


class SourcePdfValidationTests(unittest.TestCase):
    def fixture(self) -> tuple[Path, Path, tempfile.TemporaryDirectory[str]]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        metadata = root / "paper.yaml"
        metadata.write_text(
            "title: A Reliable Query Processing Engine\n"
            "authors:\n"
            "  - Ada Lovelace\n"
            "  - Grace Hopper\n"
            "year: 2024\n"
            "source_url: https://example.com/paper\n"
            "topics: [query-execution]\n"
            "reading_status: source_only\n",
            encoding="utf-8",
        )
        pdf = root / "source.pdf"
        pdf.write_bytes(b"%PDF-test")
        return metadata, pdf, temporary

    def test_matching_readable_pdf_passes(self) -> None:
        metadata, pdf, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        first = " ".join(
            [
                "A Reliable Query Processing Engine",
                "Ada Lovelace Grace Hopper",
                "abstract database systems query processing execution",
                "one two three four five six seven eight nine ten eleven twelve",
            ]
        )
        last = "references one two three four five six seven eight nine ten"
        with patch.object(
            validate_source_pdf,
            "PdfReader",
            return_value=FakeReader([FakePage(first), FakePage(last)]),
        ):
            self.assertEqual(
                validate_source_pdf.validate_source_pdf(metadata, pdf),
                [],
            )

    def test_wrong_paper_is_rejected(self) -> None:
        metadata, pdf, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        wrong = " ".join(
            [
                "Completely Different Document",
                "Other Person",
                "abstract unrelated content repeated many words for extraction",
                "one two three four five six seven eight nine ten eleven twelve",
            ]
        )
        with patch.object(
            validate_source_pdf,
            "PdfReader",
            return_value=FakeReader([FakePage(wrong), FakePage(wrong)]),
        ):
            errors = validate_source_pdf.validate_source_pdf(metadata, pdf)
        self.assertTrue(any("title tokens" in error for error in errors))
        self.assertTrue(any("authors" in error for error in errors))

    def test_non_pdf_signature_is_rejected_before_parsing(self) -> None:
        metadata, pdf, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        pdf.write_bytes(b"<html>login</html>")
        errors = validate_source_pdf.validate_source_pdf(metadata, pdf)
        self.assertEqual(len(errors), 1)
        self.assertIn("PDF signature", errors[0])

    def test_malformed_pdf_reports_an_error_without_a_traceback(self) -> None:
        metadata, pdf, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        with patch.object(
            validate_source_pdf,
            "PdfReader",
            side_effect=PdfStreamError("stream ended unexpectedly"),
        ):
            errors = validate_source_pdf.validate_source_pdf(metadata, pdf)
        self.assertEqual(len(errors), 1)
        self.assertIn("cannot read PDF", errors[0])
        self.assertIn("stream ended unexpectedly", errors[0])

    def test_lazy_page_tree_error_is_reported_without_a_traceback(self) -> None:
        metadata, pdf, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        with patch.object(
            validate_source_pdf,
            "PdfReader",
            return_value=BrokenPageTreeReader(),
        ):
            errors = validate_source_pdf.validate_source_pdf(metadata, pdf)
        self.assertEqual(len(errors), 1)
        self.assertIn("cannot read PDF", errors[0])
        self.assertIn("broken page tree", errors[0])

    def test_symlink_pdf_is_rejected(self) -> None:
        metadata, pdf, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        linked_pdf = pdf.with_name("linked.pdf")
        linked_pdf.symlink_to(pdf.name)
        errors = validate_source_pdf.validate_source_pdf(metadata, linked_pdf)
        self.assertEqual(len(errors), 1)
        self.assertIn("non-symlink", errors[0])

    def test_tree_mode_rejects_a_broken_source_symlink(self) -> None:
        metadata, pdf, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        paper = root / "papers/query-processing/sample-paper"
        paper.mkdir(parents=True)
        metadata.replace(paper / "paper.yaml")
        pdf.unlink()
        (paper / "source.pdf").symlink_to("missing.pdf")
        count, errors = validate_source_pdf.validate_source_tree(root)
        self.assertEqual(count, 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("non-symlink", errors[0])

    def test_tree_mode_scopes_to_one_paper(self) -> None:
        metadata, pdf, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        paper = root / "papers/query-processing/sample-paper"
        paper.mkdir(parents=True)
        metadata.replace(paper / "paper.yaml")
        pdf.replace(paper / "source.pdf")
        first = " ".join(
            [
                "A Reliable Query Processing Engine",
                "Ada Lovelace Grace Hopper",
                "abstract database systems query processing execution",
                "one two three four five six seven eight nine ten eleven twelve",
            ]
        )
        last = "references one two three four five six seven eight nine ten"
        with patch.object(
            validate_source_pdf,
            "PdfReader",
            return_value=FakeReader([FakePage(first), FakePage(last)]),
        ):
            count, errors = validate_source_pdf.validate_source_tree(
                root,
                "sample-paper",
            )
        self.assertEqual(count, 1)
        self.assertEqual(errors, [])

        count, errors = validate_source_pdf.validate_source_tree(
            root,
            "missing-paper",
        )
        self.assertEqual(count, 0)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
